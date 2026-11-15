"""Assembly (stage A, W29 #69): per-source tables + L3 -> workflow tables.

Spec: docs/plan/DATA-PIPELINE.md §5B. Driven only by data/pipeline/columns.yaml.
Writes data/snapshots/_derived/assembled/:
  sites-r4.parquet                    one row per hexagon (yearly traits)
  sites-r4-normalized.parquet         ADR-0005 D5 robust IQR scaled (x - median) / IQR
  sites-r4-monthly.parquet            one row per hexagon x month
  sites-r4-monthly-normalized.parquet ADR-0005 D5 robust IQR scaled (x - median) / IQR
  sites-r4-monthly-spread.parquet     p10/median/p90 over 2014-2023 (if L1m-years exists)
  hazard-events.parquet               EONET named events per hexagon
  campaign-sites.parquet              past campaigns + their hexagon's values
  trait-scales.json                   median, IQR (s_t of ADR-0005 D5), min, max, n per trait (yearly + monthly)
  data-coverage.json                  objective/test category x trait -> backing columns, null rates
  dataframe-inventory.json            consolidated catalog of prepared Earth/planetary/target frames
  assembly-report.json                counts, null rates, sha256 in/out, join/normalization checks

Assembly only joins, renames to registry names, computes the documented summaries,
and applies reversible ADR-0005 D5 robust scaling. It never fills a gap, clips,
or scores a site.

Run (from services/ingest): uv run python -m p0ingest.assemble
Exit code 0 only if every join check passes.
"""
from __future__ import annotations

import glob
import csv
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import polars as pl
import yaml

from .features import FEATURE_SPECS, build_earth_features, load_optional_regional_sources
from .grid import DERIVED
from .planetary_assemble import build_planetary_targets
from .snapshots import REPO, sha256

REGISTRY = REPO / "data" / "pipeline" / "columns.yaml"
EVIDENCE = REPO / "data" / "pipeline" / "evidence.yaml"
OUT = DERIVED / "assembled"
MIN_YEARS = 5  # spread needs at least this many years with a value (spec §5B)


def load_evidence() -> dict:
    return yaml.safe_load(EVIDENCE.read_text(encoding="utf-8"))


def evidence_problems(reg: dict, evidence: dict) -> list[str]:
    """Evidence descriptors (issue #111, from deferred ADR-0004): every registry column
    needs exactly one valid entry; entries naming no column are rejected."""
    kinds = set(evidence.get("kinds", []))
    entries = evidence.get("columns", {})
    names = [c["name"] for t in reg["tables"].values() for c in t["columns"]]
    problems = [f"{n}: no evidence descriptor" for n in dict.fromkeys(names) if n not in entries]
    problems += [f"{n}: descriptor names no registry column" for n in entries if n not in set(names)]
    if "synthetic" in kinds:
        problems.append("kind 'synthetic' is not allowed in assembled scientific tables")
    for n, e in entries.items():
        if e.get("kind") not in kinds:
            problems.append(f"{n}: kind {e.get('kind')!r} not in {sorted(kinds)}")
        for field in ("support", "family"):
            if not str(e.get(field) or "").strip():
                problems.append(f"{n}: empty {field}")
    return problems


def nonfinite_counts(df: pl.DataFrame) -> dict[str, int]:
    """NaN and +-inf are not nulls and are not values: count them per float column."""
    out = {}
    for c, dt in df.schema.items():
        if dt in (pl.Float32, pl.Float64):
            n = df.filter(pl.col(c).is_nan() | pl.col(c).is_infinite()).height
            if n:
                out[c] = n
    return out


def feature_coverage(features: list[dict], mappings: dict, tables: dict[str, pl.DataFrame],
                     absence_scope: dict | None = None) -> list[dict]:
    """Track every inventory feature without promoting related data to an exact output."""
    ids = [f["feature_id"] for f in features]
    if len(set(ids)) != len(ids) or set(ids) != set(mappings):
        raise ValueError("feature preparation mapping must cover every unique inventory feature exactly once")
    earth_feat_df = tables.get("earth-features-r4")
    planetary_df = tables.get("planetary-targets")
    result = []
    for feature in features:
        mapping = mappings[feature["feature_id"]]
        backing = []
        for ref in mapping.get("relatedColumns", []):
            table, column = ref.split(".", 1)
            frame = tables.get(table)
            present = frame is not None and column in frame.columns
            backing.append({"column": ref, "present": present,
                            "nullRate": frame[column].null_count() / frame.height if present and frame.height else None})
        ef_col = mapping.get("earthFeatureColumn")
        pl_cols = [c for c in mapping.get("planetaryTargetColumns", []) if planetary_df is not None and c in planetary_df.columns]
        has_ef = bool(ef_col and earth_feat_df is not None and ef_col in earth_feat_df.columns)
        relation = feature["earth_match"]
        if relation == "mismatch":
            state = "limitation"
        elif relation == "gap":
            state = "source-gap"
        elif has_ef:
            state = "prepared"
        elif any(x["present"] for x in backing):
            state = "partial-inputs"
        else:
            state = "not-built"
        if state == "source-gap" and not absence_scope:
            raise ValueError(f"{feature['feature_id']}: source-gap features need a dated absenceScope")
        result.append({**feature, "preparationState": state, "implemented": has_ef,
                       **({"earthFeatureColumn": ef_col} if ef_col else {}),
                       **({"planetaryTargetColumns": pl_cols} if pl_cols else {}),
                       **({"absenceScope": absence_scope} if state == "source-gap" else {}),
                       "relatedColumns": backing, "notes": mapping["notes"],
                       "scientificStatus": "prepared-proxy-or-direct" if has_ef else ("proposed" if relation != "mismatch" else "limitation"),
                       "meaning": "Related columns and candidate source names do not establish this feature's quantity, scale or validity."})
    return result


def _reasons_expr(src_reason: str, items: list[tuple[str, str, str | None]]) -> pl.Expr:
    """Per-row JSON {assembled column: reason} listing exactly the null columns.
    items = (assembled name, source column, trait). The reason is the source
    row's code for that column, else for its trait, else 'null-without-reason'."""
    def one(name: str, col: str, trait: str | None) -> pl.Expr:
        by_col = pl.col(src_reason).str.json_path_match(f"$.{col}")
        by_trait = pl.col(src_reason).str.json_path_match(f"$.{trait}") if trait else pl.lit(None, pl.String)
        code = pl.coalesce(by_col, by_trait, pl.lit("null-without-reason"))
        encoded = pl.struct(code.alias(name)).struct.json_encode().str.strip_prefix("{").str.strip_suffix("}")
        return pl.when(pl.col(name).is_null()).then(encoded).otherwise(None)
    fragment = pl.concat_str([one(*it) for it in items], separator=",", ignore_nulls=True)
    return pl.when(fragment != "").then(fragment).otherwise(None)


class Build:
    def __init__(self) -> None:
        self.reg = yaml.safe_load(REGISTRY.read_text(encoding="utf-8"))
        self.report: dict = {"generatedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                             "registry": {"path": str(REGISTRY.relative_to(REPO)), "sha256": sha256(REGISTRY)},
                             "inputs": {}, "outputs": {}, "checks": [], "skipped": [], "nullRate": {}}
        self.fails = 0
        self.master = pl.read_parquet(DERIVED / "cells-r4.parquet", columns=["h3"]).with_row_index("cell")
        self._cache: dict[str, pl.DataFrame] = {}

    # ---- helpers -----------------------------------------------------------
    def check(self, name: str, ok: bool, detail: str = "") -> None:
        self.report["checks"].append({"check": name, "pass": bool(ok), "detail": detail})
        print(f"  {'PASS' if ok else 'FAIL'} {name}" + (f": {detail}" if detail else ""), flush=True)
        self.fails += not ok

    def source(self, sid: str) -> pl.DataFrame | None:
        if sid in self._cache:
            return self._cache[sid]
        meta = self.reg["sources"][sid]
        path = DERIVED / meta["path"]
        if not path.exists():
            self._cache[sid] = None
            return None
        df = pl.read_parquet(path)
        self.report["inputs"][sid] = {"path": str(path.relative_to(REPO)), "sha256": sha256(path), "rows": df.height}
        key = meta["key"]
        if sid != "eonet-events-r4":
            per_cell = {("h3",): 1, ("h3", "month"): 12, ("h3", "year", "month"): 120}[tuple(key)]
            n_dup = df.height - df.select(key).unique().height
            unknown = df.join(self.master, on="h3", how="anti").height
            bad_time = 0
            if "month" in key:
                bad_time += df.filter(~pl.col("month").is_between(1, 12)).height
            if "year" in key:
                bad_time += df.filter(~pl.col("year").is_between(2014, 2023)).height
            null_keys = sum(df[k].null_count() for k in key)
            ok = df.height == self.master.height * per_cell and n_dup == 0 and unknown == 0 and bad_time == 0 and null_keys == 0
            self.check(f"{sid}: keys complete and unique", ok,
                       f"{df.height:,} rows (want {self.master.height * per_cell:,}), {n_dup} duplicate keys, {unknown} unknown hexagons, {bad_time} invalid times, {null_keys} null keys")
        self._cache[sid] = df
        return df

    def write(self, name: str, df: pl.DataFrame) -> None:
        OUT.mkdir(parents=True, exist_ok=True)
        p = OUT / f"{name}.parquet"
        df.write_parquet(p, compression="zstd")
        bad = nonfinite_counts(df)
        self.check(f"{name}: no NaN or infinite values (nulls carry reasons)", not bad,
                   ", ".join(f"{c}:{n}" for c, n in bad.items()) or "all float columns finite")
        self.report["outputs"][name] = {"path": str(p.relative_to(REPO)), "sha256": sha256(p),
                                        "bytes": p.stat().st_size, "rows": df.height, "columns": df.width}
        self.report["nullRate"][name] = {c: round(df[c].null_count() / max(df.height, 1), 6) for c in df.columns}

    # ---- workflow tables from the registry ---------------------------------
    def table(self, tname: str) -> pl.DataFrame:
        spec = self.reg["tables"][tname]
        key = spec["key"]
        base = self.master if key == ["h3"] else self.master.join(
            pl.DataFrame({"month": pl.Series(range(1, 13), dtype=pl.Int8)}), how="cross")
        out = base
        reasons = []
        by_src: dict[str, list[dict]] = {}
        for c in spec["columns"]:
            by_src.setdefault(c["from"].split(".")[0], []).append(c)
        for sid, cols in by_src.items():
            src = self.source(sid)
            if src is None:
                for c in cols:
                    if c["status"] == "active":
                        self.check(f"{tname}.{c['name']}: source present", False, f"{sid} missing but status active")
                    else:
                        self.report["skipped"].append({"table": tname, "column": c["name"], "source": sid,
                                                       "why": "planned; source table not built yet"})
                continue
            missing = [c for c in cols if c["from"].split(".", 1)[1] not in src.columns]
            for c in missing:
                self.check(f"{tname}.{c['name']}: column in source", False, f"{c['from']} not found")
            cols = [c for c in cols if c not in missing]
            rcol = f"__mr_{sid}"
            sel = [pl.col(k) for k in key] + [pl.col(c["from"].split(".", 1)[1]).alias(c["name"]) for c in cols]
            sel.append((pl.col("missing_reason") if "missing_reason" in src.columns else pl.lit("{}")).alias(rcol))
            if "month" in key:
                src = src.with_columns(pl.col("month").cast(pl.Int8))
            out = out.join(src.select(sel), on=key, how="left")
            reasons.append(_reasons_expr(rcol, [(c["name"], c["from"].split(".", 1)[1], c.get("reasonKey") or c.get("trait")) for c in cols]))
            # value check: every assembled value equals its source value, exactly
            back = out.select(key + [c["name"] for c in cols]).join(
                src.select([pl.col(k) for k in key] + [pl.col(c["from"].split(".", 1)[1]).alias(f"__src_{c['name']}") for c in cols]),
                on=key, how="inner")
            bad = 0
            for c in cols:
                a, b = pl.col(c["name"]), pl.col(f"__src_{c['name']}")
                bad += back.filter(~a.eq_missing(b)).height
            self.check(f"{tname} <- {sid}: values unchanged", bad == 0, f"{len(cols)} columns, {bad} differing cells")
        out = out.with_columns(
            (pl.lit("{") + pl.concat_str(reasons, separator=",", ignore_nulls=True).fill_null("") + pl.lit("}")).alias("missing_reason")
        )
        out = out.sort(["cell"] + [k for k in key if k != "h3"]).drop([c for c in out.columns if c.startswith("__mr_")] + ["cell"])
        # missing_reason lists exactly the null columns, and never 'null-without-reason'
        data_cols = [c for c in out.columns if c not in key and c != "missing_reason"]
        nulls = out.select(pl.sum_horizontal([pl.col(c).is_null().cast(pl.Int32) for c in data_cols]).alias("n"),
                           pl.col("missing_reason").str.count_matches('":"').alias("r"),
                           pl.col("missing_reason").str.contains("null-without-reason").alias("w"))
        self.check(f"{tname}: missing_reason lists exactly the null columns",
                   nulls.filter(pl.col("n") != pl.col("r")).height == 0 and not nulls["w"].any(),
                   f"{nulls.filter(pl.col('n') != pl.col('r')).height} rows differ, {int(nulls['w'].sum())} null without a source reason")
        json_ok = out["missing_reason"].str.json_decode(infer_schema_length=None).null_count() == 0
        self.check(f"{tname}: missing_reason is valid JSON", json_ok)
        return out

    # ---- derived summaries --------------------------------------------------
    def spread(self) -> pl.DataFrame | None:
        spec = self.reg["derived"]["sites-r4-monthly-spread"]
        yrs = self.source(spec["from"])
        if yrs is None:
            self.report["skipped"].append({"table": "sites-r4-monthly-spread", "source": spec["from"],
                                           "why": "planned; L1m-years not built yet"})
            return None
        stat = {"p10": lambda c: pl.col(c).quantile(0.10, interpolation="linear"),
                "median": lambda c: pl.col(c).median(),
                "p90": lambda c: pl.col(c).quantile(0.90, interpolation="linear"),
                "count": lambda c: pl.col(c).count()}
        aggs = [stat[c["stat"]](c["of"]).alias(c["name"]) for c in spec["columns"]]
        aggs += [pl.col(o).count().alias(f"__n_{o}") for o in {c["of"] for c in spec["columns"]}]
        g = yrs.with_columns(pl.col("month").cast(pl.Int8)).group_by(["h3", "month"]).agg(aggs)
        fix, reason = [], []
        for c in spec["columns"]:
            if c["stat"] == "count":
                fix.append(pl.col(c["name"]).cast(pl.Int16))
                continue
            few = pl.col(f"__n_{c['of']}") < MIN_YEARS
            fix.append(pl.when(few).then(None).otherwise(pl.col(c["name"])).alias(c["name"]))
            reason.append(pl.when(few).then(pl.lit(f'"{c["name"]}":"too-few-years"')).otherwise(None))
        g = g.with_columns(fix).with_columns(
            (pl.lit("{") + pl.concat_str(reason, separator=",", ignore_nulls=True).fill_null("") + pl.lit("}")).alias("missing_reason"))
        g = self.master.join(pl.DataFrame({"month": pl.Series(range(1, 13), dtype=pl.Int8)}), how="cross").join(
            g, on=["h3", "month"], how="left").sort(["cell", "month"]).drop(["cell"] + [c for c in g.columns if c.startswith("__n_")])
        self.check("spread: one row per hexagon x month", g.height == self.master.height * 12, f"{g.height:,} rows")
        # 2023 rows of L1m-years must equal L1m (spec §5B join check)
        lm = self.source("cells-r4-monthly").select("h3", pl.col("month").cast(pl.Int8), "lst_day_k", "lst_night_k")
        y23 = yrs.filter(pl.col("year") == 2023).select("h3", pl.col("month").cast(pl.Int8), "lst_day_k", "lst_night_k")
        j = lm.join(y23, on=["h3", "month"], how="inner", suffix="_y")
        bad = sum(j.filter(~pl.col(c).eq_missing(pl.col(c + "_y"))).height
                  for c in ("lst_day_k", "lst_night_k"))
        self.check("L1m-years 2023 == L1m", bad == 0 and j.height == lm.height, f"{bad} differing values over {j.height:,} rows")
        return g

    def campaigns(self, sites: pl.DataFrame) -> pl.DataFrame:
        rows = []
        for p in sorted(glob.glob(str(REPO / "data" / "campaigns" / "*.yaml"))):
            d = yaml.safe_load(Path(p).read_text(encoding="utf-8"))
            rows.append({"campaign_id": d["campaignId"], "name": d["name"], "agency": ", ".join(d["agency"]),
                         "year_first": d["years"]["first"], "year_last": d["years"]["last"],
                         "site_name": d["site"]["name"], "site_lat": float(d["site"]["lat"]), "site_lon": float(d["site"]["lon"]),
                         "h3": d["site"]["h3r4"], "objectives": json.dumps([o["text"] for o in d["objectivesExercised"]]),
                         "outcomes": json.dumps([{"kind": o["kind"], "text": o["text"]} for o in d["outcome"]]),
                         "constraints": json.dumps([{k: o[k] for k in ("what", "value", "unit")} for o in d["publishedConstraints"]]),
                         "sources": json.dumps([s["url"] for s in d["sources"]]),
                         "source_records": json.dumps(d["sources"], ensure_ascii=False),
                         "objective_evidence": json.dumps(d["objectivesExercised"], ensure_ascii=False),
                         "constraint_evidence": json.dumps(d["publishedConstraints"], ensure_ascii=False),
                         "outcome_evidence": json.dumps(d["outcome"], ensure_ascii=False),
                         "explicit_unknowns": json.dumps(d["nulls"], ensure_ascii=False),
                         "hex_feature_period": "2023 reference context; not measured campaign conditions",
                         "test_mapping_status": "not-mapped-to-structured-test-ids",
                         "file": str(Path(p).relative_to(REPO))})
        df = pl.DataFrame(rows)
        import h3
        bad = [r["campaign_id"] for r in rows if h3.latlng_to_cell(r["site_lat"], r["site_lon"], 4) != r["h3"]]
        self.check("campaigns: hexagon = H3 cell of the quoted coordinates", not bad, f"{len(rows)} campaigns; bad: {bad}")
        out = df.join(sites.rename({c: f"hex_{c}" for c in sites.columns if c != "h3"}), on="h3", how="left", maintain_order="left")
        not_land = out.filter(pl.col("hex_missing_reason").is_null())["campaign_id"].to_list()
        self.check("campaigns: every site is a land hexagon", not not_land, f"not in the 91,800 cells: {not_land}")
        return out

    def table_scales(self, table_name: str, df: pl.DataFrame) -> dict:
        """Compute ADR-0005 D5 robust location/scale statistics for a workflow table."""
        res = {}
        spec = {c["name"]: c for c in self.reg["tables"][table_name]["columns"]}
        for name, c in spec.items():
            if name not in df.columns or name in ("lat", "lon"):
                continue
            s = df[name]
            if c.get("role") == "diagnostic":
                res[name] = {"kind": "diagnostic", "trait": c["trait"], "unit": c["unit"],
                             "n": s.len() - s.null_count(), "inSum": False, "scaled": False,
                             "unscaledReason": "source-diagnostic", "note": "Source support or calendar diagnostic; retained in native units."}
                continue
            if s.dtype == pl.Boolean:
                res[name] = {
                    "kind": "yes/no", "trait": c["trait"], "unit": c["unit"], "n": s.len() - s.null_count(),
                    "share_true": None if s.null_count() == s.len() else round(float(s.drop_nulls().mean()), 6),
                    "scaled": False, "unscaledReason": "boolean",
                    "note": "left out of the closeness sum; shown as same/different (ADR-0005 D5)",
                }
                continue
            v = s.drop_nulls().cast(pl.Float64)
            if v.len() == 0:
                res[name] = {
                    "kind": "number", "trait": c["trait"], "unit": c["unit"], "n": 0, "iqr": None,
                    "inSum": False, "scaled": False, "unscaledReason": "no-values", "note": "no values yet",
                }
                continue
            q1, q3 = float(v.quantile(0.25, "linear")), float(v.quantile(0.75, "linear"))
            med = float(v.median())
            iqr = q3 - q1
            in_sum = bool(iqr > 0)
            res[name] = {
                "kind": "number", "trait": c["trait"], "unit": c["unit"], "n": v.len(),
                "min": float(v.min()), "q1": q1, "median": med, "q3": q3, "max": float(v.max()), "iqr": iqr,
                "inSum": in_sum, "scaled": in_sum,
                **({} if in_sum else {"unscaledReason": "iqr-zero"}),
                "note": "IQR over all rows with a value; s_t in ADR-0005 D5" + ("" if in_sum else "; IQR is 0, so shown as same/different"),
            }
        return res

    def scales(self, sites: pl.DataFrame) -> dict:
        return self.table_scales("sites-r4", sites)

    def normalize_and_check(self, tname: str, df: pl.DataFrame, tbl_scales: dict) -> tuple[pl.DataFrame, dict]:
        """Build the ADR-0005 D5 robust IQR normalized DataFrame and verify reversibility + null parity."""
        norm_df, info = normalize_frame(df, tbl_scales)
        key_cols = [k for k in self.reg["tables"].get(tname, {}).get("key", ["h3"]) if k in df.columns]
        same_rows = norm_df.height == df.height and norm_df.columns == df.columns
        if same_rows and key_cols:
            same_keys = bool(norm_df.select([pl.col(k).eq_missing(df[k]).all() for k in key_cols]).row(0) == tuple([True] * len(key_cols)))
        else:
            same_keys = False
        self.check(f"{tname}-normalized: row count, schema order, and keys match raw", same_rows and same_keys,
                   f"{norm_df.height:,} rows, {norm_df.width} cols, {len(info['scaledColumns'])} scaled")
        null_mismatches = [
            c for c in df.columns
            if not norm_df[c].is_null().eq(df[c].is_null()).all()
        ]
        mr_ok = "missing_reason" not in df.columns or bool((norm_df["missing_reason"] == df["missing_reason"]).all())
        self.check(f"{tname}-normalized: null masks and missing_reason match raw",
                   not null_mismatches and mr_ok,
                   f"mismatched columns={null_mismatches}, missing_reason_ok={mr_ok}")
        diagnostic_bad = [
            col for col, sc in tbl_scales.items() if sc.get("kind") == "diagnostic"
            and (norm_df[col].dtype != df[col].dtype or not norm_df[col].equals(df[col]))
        ]
        self.check(f"{tname}-normalized: diagnostics keep source values and types",
                   not diagnostic_bad, f"mismatched columns={diagnostic_bad}")
        rt_bad: list[str] = []
        stat_bad: list[str] = []
        for col in info["scaledColumns"]:
            sc = tbl_scales[col]
            med, iqr = float(sc["median"]), float(sc["iqr"])
            raw_v = df[col].drop_nulls().cast(pl.Float64)
            z_v = norm_df[col].drop_nulls().cast(pl.Float64)
            tol = max(1e-9, 1e-10 * max(abs(float(raw_v.max())), abs(float(raw_v.min())), abs(med), iqr))
            max_err = float((z_v * iqr + med - raw_v).abs().max())
            if max_err > tol:
                rt_bad.append(f"{col}:{max_err:.3e}>{tol:.3e}")
            z_med = float(z_v.median())
            z_iqr = float(z_v.quantile(0.75, "linear")) - float(z_v.quantile(0.25, "linear"))
            if abs(z_med) > 1e-9 or abs(z_iqr - 1.0) > 1e-9:
                stat_bad.append(f"{col}(med={z_med:.2e},iqr={z_iqr:.6f})")
        self.check(f"{tname}-normalized: robust IQR round-trip & scale (median=0, IQR=1)",
                   not rt_bad and not stat_bad,
                   f"round_trip_err={rt_bad or 'none'}, stat_err={stat_bad or 'none'}")
        return norm_df, info

    def _check_missing_reason_json(self, name: str, df: pl.DataFrame, value_cols: list[str]) -> None:
        nulls = df.select(
            pl.sum_horizontal([pl.col(c).is_null().cast(pl.Int32) for c in value_cols]).alias("n"),
            pl.col("missing_reason").str.count_matches('":"').alias("r"),
            pl.col("missing_reason").str.contains("null-without-reason").alias("w"),
        )
        self.check(
            f"{name}: missing_reason lists exactly the null columns",
            nulls.filter(pl.col("n") != pl.col("r")).height == 0 and not nulls["w"].any(),
            f"{nulls.filter(pl.col('n') != pl.col('r')).height} rows differ, {int(nulls['w'].sum())} null without reason",
        )
        json_ok = df["missing_reason"].str.json_decode(infer_schema_length=None).null_count() == 0
        self.check(f"{name}: missing_reason is valid JSON", json_ok)

    def coverage(
        self,
        sites: pl.DataFrame,
        monthly: pl.DataFrame,
        earth_features: pl.DataFrame | None = None,
        planetary_targets: pl.DataFrame | None = None,
    ) -> dict:
        cols = [c | {"table": t} for t in self.reg["tables"] for c in self.reg["tables"][t]["columns"]]
        evidence = load_evidence()
        def backing(trait: str) -> list[dict]:
            out = []
            for c in cols:
                if c["trait"] != trait:
                    continue
                df = sites if c["table"] == "sites-r4" else monthly
                present = c["name"] in df.columns
                nr = round(df[c["name"]].null_count() / df.height, 6) if present else None
                ev = evidence["columns"].get(c["name"], {})
                out.append({"column": c["name"], "table": c["table"], "status": c["status"] if present else "planned",
                            "nullRate": nr, "kind": ev.get("kind"), "family": ev.get("family")})
            return out
        def kind(trait: str) -> str:
            if trait in self.reg["earthCannot"]:
                return "earth-cannot"
            b = backing(trait)
            return "data" if any(x["nullRate"] is not None and x["nullRate"] < 1 for x in b) else "none-yet"
        tm = yaml.safe_load((REPO / "data" / "requirements" / "trait-map.yaml").read_text(encoding="utf-8"))["rules"]
        objectives = {}
        for p in sorted(glob.glob(str(REPO / "data" / "objectives" / "*.yaml"))):
            d = yaml.safe_load(Path(p).read_text(encoding="utf-8"))
            rows = []
            for t in d["requiredDimensions"]:
                rule = next((r for r in tm if r["objectiveId"] == d["objectiveId"] and r["dimension"] == t), None)
                col = rule and rule.get("earthColumn")
                df = None
                for c in cols:
                    if c["name"] == col:
                        df = sites if c["table"] == "sites-r4" else monthly
                nr = round(df[col].null_count() / df.height, 6) if df is not None and col in df.columns else None
                rows.append({"trait": t, "earthColumn": col, "band": rule.get("band") if rule else None,
                             "columnNullRate": nr,
                             "checkedBy": kind(t) if col else ("none-yet" if t not in self.reg["earthCannot"] else "earth-cannot"),
                             "bandStatus": "set" if rule and rule.get("band") else "no band yet (unknown)"})
            for m in d.get("notTestableOnEarth", []):
                rows.append({"trait": m["mismatch"], "earthColumn": None, "band": None, "columnNullRate": None,
                             "checkedBy": "earth-cannot", "bandStatus": "permanent breakdown", "why": m["why"]})
            objectives[d["objectiveId"]] = {"body": d["body"], "title": d["title"], "traits": rows}
        test_path = REPO / "data/pipeline/test-categories.yaml"
        test_catalog = yaml.safe_load(test_path.read_text(encoding="utf-8"))
        test_rows = test_catalog["categories"]
        if len(test_rows) != test_catalog["sourceCategoryCount"] or len({c["categoryId"] for c in test_rows}) != len(test_rows):
            raise ValueError("test categories must preserve every source category exactly once")
        categories = {}
        for c in test_rows:
            categories[c["categoryId"]] = {**c,
                "traits": {t: {"checkedBy": kind(t), "columns": backing(t)} for t in c["traits"]}}
        feature_path = REPO / "research/features/landing_site_features.csv"
        mapping_path = REPO / "data/pipeline/feature-preparation.yaml"
        with feature_path.open(encoding="utf-8", newline="") as stream:
            features = list(csv.DictReader(stream))
        preparation = yaml.safe_load(mapping_path.read_text(encoding="utf-8"))
        table_map: dict[str, pl.DataFrame] = {"sites-r4": sites, "sites-r4-monthly": monthly}
        if earth_features is not None:
            table_map["earth-features-r4"] = earth_features
        if planetary_targets is not None:
            table_map["planetary-targets"] = planetary_targets
        full = feature_coverage(features, preparation["features"], table_map,
                                preparation.get("absenceScope"))
        for category in categories.values():
            category["featureCompleteness"] = "not-established"
            category["note"] = "Trait-column availability is not evidence that all tests in this category can be performed."
        planetary_status = (
            f"executed: {planetary_targets.height} source-native target profiles in assembled/planetary-targets.parquet (TES excluded pending projection review)"
            if planetary_targets is not None
            else "not-built: generic envelopes are not measured per-target feature tables"
        )
        return {"objectives": objectives, "categories": categories, "earthCannot": self.reg["earthCannot"],
                "columnEvidence": evidence["columns"],
                "evidenceNote": "kind/support/family describe each stored column. Shared family means not independent. "
                                "Family counts are discovery hints only; corroboration needs a per-claim review.",
                "featureInventory": {"path": str(feature_path.relative_to(REPO)), "sha256": sha256(feature_path),
                                     "mappingSha256": sha256(mapping_path), "count": len(full)},
                "features": full, "workflowModules": preparation["workflowModules"],
                "additionalEvidenceGaps": preparation["additionalEvidenceGaps"],
                "testCatalog": {"source": test_catalog["source"], "selection": test_catalog["selection"],
                                "detailedMenus": test_catalog.get("detailedMenus", []),
                                "sha256": sha256(test_path), "count": len(categories)},
                "planetaryAssemblyStatus": planetary_status,
                "campaignTestAssemblyStatus": "partial: quoted records preserved; source extraction of historical test conditions remains #74"}

    def dataframe_inventory(self, norm_summary: dict) -> dict:
        """Inventory assembled Earth dataframes, source tables, planetary tables, and L3 reference data."""
        per_source = {}
        for sid, meta in self.reg["sources"].items():
            p = DERIVED / meta["path"]
            per_source[sid] = {
                "path": str(p.relative_to(REPO)),
                "present": p.exists(),
                **({"bytes": p.stat().st_size, "sha256": sha256(p)} if p.exists() else {}),
                "issue": meta.get("issue"),
                "key": meta["key"],
            }
        planetary_dir = DERIVED / "planetary"
        planetary = []
        if planetary_dir.exists():
            for p in sorted(planetary_dir.rglob("*.parquet")):
                pf = pl.read_parquet_schema(p)
                planetary.append({
                    "path": str(p.relative_to(REPO)),
                    "bytes": p.stat().st_size,
                    "sha256": sha256(p),
                    "columns": list(pf.keys()),
                    "note": "native planetary coordinates preserved; no Earth H3 assignment (ADR-0008)",
                })
        return {
            "generatedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "normalizationMethod": "ADR-0005 D5 robust IQR: (x - median) / IQR; diagnostics (ADR-0010), booleans, coordinates, and IQR=0 unscaled; nulls preserved",
            "earthAssembled": {k: v for k, v in self.report["outputs"].items() if k in (
                "sites-r4", "sites-r4-normalized", "sites-r4-monthly", "sites-r4-monthly-normalized",
                "sites-r4-monthly-spread", "earth-features-r4", "earth-features-r4-normalized",
                "hazard-events", "campaign-sites")},
            "planetaryAssembled": {k: v for k, v in self.report["outputs"].items() if k == "planetary-targets"},
            "normalization": norm_summary,
            "earthPerSource": per_source,
            "planetaryPreparedLocal": planetary,
            "curatedReference": {
                "catalogDatasets": len([p for p in (REPO / "data/catalog").glob("*.yaml") if p.name != "dataset.template.yaml"]),
                "targets": len(list((REPO / "data/targets").glob("*.yaml"))),
                "campaigns": len(list((REPO / "data/campaigns").glob("*.yaml"))),
                "objectives": len(list((REPO / "data/objectives").glob("*.yaml"))),
                "envelopes": len(list((REPO / "data/envelopes").glob("*.json"))),
            },
        }

    # ---- run ----------------------------------------------------------------
    def run(self) -> int:
        t0 = time.time()
        problems = evidence_problems(self.reg, load_evidence())
        self.check("evidence descriptors: every column has a valid kind/support/family", not problems,
                   "; ".join(problems[:5]) or f"{len(load_evidence()['columns'])} columns")
        print("[sites-r4]", flush=True)
        sites = self.table("sites-r4")
        self.write("sites-r4", sites)
        print("[sites-r4-monthly]", flush=True)
        monthly = self.table("sites-r4-monthly")
        self.write("sites-r4-monthly", monthly)
        print("[sites-r4-monthly-spread]", flush=True)
        sp = self.spread()
        if sp is not None:
            self.write("sites-r4-monthly-spread", sp)
        print("[hazard-events]", flush=True)
        ev = self.source("eonet-events-r4")
        if ev is not None:
            unknown = ev.join(self.master, on="h3", how="anti").height
            dup = ev.height - ev.select("h3", "event_id", "category").unique().height
            self.check("hazard-events: hexagons known, one row per (hexagon, event, category)", unknown == 0 and dup == 0,
                       f"{ev.height:,} rows, {unknown} unknown hexagons, {dup} duplicates")
            self.write("hazard-events", ev)
        print("[campaign-sites]", flush=True)
        self.write("campaign-sites", self.campaigns(sites))
        print("[earth-features-r4]", flush=True)
        palsar, arads_counts = load_optional_regional_sources()
        earth_feats, earth_feat_meta = build_earth_features(
            sites, monthly, spread=sp, palsar=palsar, arads_count_by_h3=arads_counts,
        )
        ef_keys_ok = (
            earth_feats.height == self.master.height
            and bool(earth_feats["h3"].eq(self.master["h3"]).all())
        )
        self.check("earth-features-r4: one row per land hexagon matching master key order", ef_keys_ok,
                   f"{earth_feats.height:,} rows, {earth_feats.width} columns")
        self._check_missing_reason_json(
            "earth-features-r4",
            earth_feats,
            [c for c in earth_feats.columns if c not in ("h3", "lat", "lon", "missing_reason")],
        )
        self.write("earth-features-r4", earth_feats)
        print("[planetary-targets]", flush=True)
        planetary_df, planetary_meta = build_planetary_targets()
        expected_targets = len(list((REPO / "data" / "targets").glob("*.yaml")))
        self.check(
            "planetary-targets: one row per target YAML and no Earth H3 assignment",
            planetary_df.height == expected_targets and "h3" not in planetary_df.columns,
            f"{planetary_df.height} targets (want {expected_targets}), {planetary_df.width} columns",
        )
        self.check(
            "planetary-targets: TES thermal inertia remains null pending projection review",
            planetary_df["mars_tes_ti_day_si"].null_count() == planetary_df.height
            and planetary_df["mars_tes_ti_night_si"].null_count() == planetary_df.height,
        )
        pl_value_cols = [
            c for c in planetary_df.columns
            if c not in ("target_id", "name", "body", "kind", "status", "lon_mode", "has_numeric_centre", "missing_reason")
        ]
        self._check_missing_reason_json("planetary-targets", planetary_df, pl_value_cols)
        self.write("planetary-targets", planetary_df)
        print("[normalize: sites-r4, sites-r4-monthly, earth-features-r4]", flush=True)
        yearly_scales = self.table_scales("sites-r4", sites)
        monthly_scales = self.table_scales("sites-r4-monthly", monthly)
        earth_feat_scales = earth_feat_meta["scales"]
        sites_norm, sites_norm_info = self.normalize_and_check("sites-r4", sites, yearly_scales)
        self.write("sites-r4-normalized", sites_norm)
        monthly_norm, monthly_norm_info = self.normalize_and_check("sites-r4-monthly", monthly, monthly_scales)
        self.write("sites-r4-monthly-normalized", monthly_norm)
        ef_norm, ef_norm_info = self.normalize_and_check("earth-features-r4", earth_feats, earth_feat_scales)
        self.write("earth-features-r4-normalized", ef_norm)
        print("[trait-scales, data-coverage, dataframe-inventory]", flush=True)
        OUT.mkdir(parents=True, exist_ok=True)
        from .clean_audit import build as cleaning_audit
        cleaning_result = cleaning_audit()
        quality = {"scientificStatus": cleaning_result["scientificStatus"], "warnings": cleaning_result["warnings"],
                   "completeInputFilterAccounting": cleaning_result["completeInputFilterAccounting"], "followupIssue": 76}
        self.report["sourceQuality"] = quality
        scales_doc = {
            **yearly_scales,
            "_meta": {
                "formula": "(x - median) / iqr",
                "spec": "ADR-0005 D5",
                "zeroIqrRule": "left unscaled when iqr == 0",
                "booleanRule": "left unscaled (yes/no)",
                "diagnosticRule": "source support and calendar diagnostics stay in native units (ADR-0010)",
                "nullRule": "preserved as null; never filled",
            },
            "_tables": {
                "sites-r4": yearly_scales,
                "sites-r4-monthly": monthly_scales,
                "earth-features-r4": earth_feat_scales,
            },
        }
        cov_doc = self.coverage(sites, monthly, earth_features=earth_feats, planetary_targets=planetary_df)
        cov_doc["sourceQuality"] = quality
        for name, obj in (
            ("trait-scales", scales_doc),
            ("earth-feature-scales", earth_feat_meta),
            ("planetary-targets.meta", planetary_meta),
            ("data-coverage", cov_doc),
        ):
            p = OUT / f"{name}.json"
            p.write_text(json.dumps(obj, indent=2, default=float) + "\n", encoding="utf-8")
            self.report["outputs"][name] = {"path": str(p.relative_to(REPO)), "sha256": sha256(p), "bytes": p.stat().st_size}
        cleaning = OUT / "cleaning-report.json"
        self.report["outputs"]["cleaning-report"] = {"path": str(cleaning.relative_to(REPO)), "sha256": sha256(cleaning), "bytes": cleaning.stat().st_size}
        inv_doc = self.dataframe_inventory({
            "sites-r4": sites_norm_info,
            "sites-r4-monthly": monthly_norm_info,
            "earth-features-r4": ef_norm_info,
        })
        inv_path = OUT / "dataframe-inventory.json"
        inv_path.write_text(json.dumps(inv_doc, indent=2, default=float) + "\n", encoding="utf-8")
        self.report["outputs"]["dataframe-inventory"] = {"path": str(inv_path.relative_to(REPO)), "sha256": sha256(inv_path), "bytes": inv_path.stat().st_size}
        self.report["normalization"] = {
            "sites-r4": sites_norm_info,
            "sites-r4-monthly": monthly_norm_info,
            "earth-features-r4": ef_norm_info,
        }
        self.report["runtime_s"] = round(time.time() - t0, 1)
        self.report["result"] = "ALL PASS" if self.fails == 0 else f"{self.fails} CHECK(S) FAILED"
        (OUT / "assembly-report.json").write_text(json.dumps(self.report, indent=2, default=float) + "\n", encoding="utf-8")
        print(f"skipped (planned, source not built yet): {len(self.report['skipped'])}")
        for s in self.report["skipped"]:
            print(f"  - {s.get('table')}.{s.get('column', '*')} from {s['source']}")
        for k, v in self.report["outputs"].items():
            print(f"  {k:29s} {v.get('rows', ''):>10} rows  {v['sha256'][:16]}  {v['bytes']:,} B")
        print(self.report["result"], f"({self.report['runtime_s']} s)")
        return 0 if self.fails == 0 else 1


def normalize_frame(
    df: pl.DataFrame,
    tbl_scales: dict,
    key_cols: tuple[str, ...] = ("h3", "month", "lat", "lon", "missing_reason"),
) -> tuple[pl.DataFrame, dict]:
    """Apply ADR-0005 D5 robust IQR normalization (x - median) / iqr cleanly without filling nulls."""
    exprs: list[pl.Expr] = []
    scaled_cols: list[str] = []
    unscaled_cols: dict[str, str] = {}
    for col in df.columns:
        if col in key_cols:
            unscaled_cols[col] = "key-or-coord"
            continue
        sc = tbl_scales.get(col)
        if sc is None:
            unscaled_cols[col] = "no-scale-entry"
            continue
        if sc.get("kind") == "diagnostic":
            unscaled_cols[col] = "source-diagnostic"
            continue
        if sc.get("kind") == "yes/no":
            unscaled_cols[col] = "boolean"
            continue
        iqr = sc.get("iqr")
        med = sc.get("median")
        if iqr is None or med is None or sc.get("n", 0) == 0:
            unscaled_cols[col] = "no-values"
            continue
        if float(iqr) <= 0.0:
            unscaled_cols[col] = "iqr-zero"
            continue
        exprs.append(((pl.col(col).cast(pl.Float64) - float(med)) / float(iqr)).alias(col))
        scaled_cols.append(col)
    norm_df = df.with_columns(exprs) if exprs else df.clone()
    return norm_df, {"method": "robust-iqr-adr0005-d5", "formula": "(x - median) / iqr",
                     "scaledColumns": scaled_cols, "unscaledColumns": unscaled_cols}


if __name__ == "__main__":
    sys.exit(Build().run())
