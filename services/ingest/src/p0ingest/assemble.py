"""Assembly (stage A, W29 #69): per-source tables + L3 -> workflow tables.

Spec: docs/plan/DATA-PIPELINE.md §5B. Driven only by data/pipeline/columns.yaml.
Writes data/snapshots/_derived/assembled/:
  sites-r4.parquet                 one row per hexagon (yearly traits)
  sites-r4-monthly.parquet         one row per hexagon x month
  sites-r4-monthly-spread.parquet  p10/median/p90 over 2014-2023 (if L1m-years exists)
  hazard-events.parquet            EONET named events per hexagon
  campaign-sites.parquet           past campaigns + their hexagon's values
  trait-scales.json                median, IQR (s_t of ADR-0005 D5), min, max, n per trait
  data-coverage.json               objective/test category x trait -> backing columns, null rates
  assembly-report.json             counts, null rates, sha256 in/out, join checks

Assembly only joins, renames to registry names and computes the summaries the
spec lists. It never changes a value, fills a gap or scores a site.

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

from .grid import DERIVED
from .snapshots import REPO, sha256

REGISTRY = REPO / "data" / "pipeline" / "columns.yaml"
OUT = DERIVED / "assembled"
MIN_YEARS = 5  # spread needs at least this many years with a value (spec §5B)


def feature_coverage(features: list[dict], mappings: dict, tables: dict[str, pl.DataFrame]) -> list[dict]:
    """Track every inventory feature without promoting related data to an exact output."""
    ids = [f["feature_id"] for f in features]
    if len(set(ids)) != len(ids) or set(ids) != set(mappings):
        raise ValueError("feature preparation mapping must cover every unique inventory feature exactly once")
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
        relation = feature["earth_match"]
        state = "limitation" if relation == "mismatch" else "source-gap" if relation == "gap" else (
            "partial-inputs" if any(x["present"] for x in backing) else "not-built")
        result.append({**feature, "preparationState": state, "implemented": False,
                       "relatedColumns": backing, "notes": mapping["notes"],
                       "scientificStatus": "proposed" if relation != "mismatch" else "limitation",
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

    def scales(self, sites: pl.DataFrame) -> dict:
        res = {}
        spec = {c["name"]: c for c in self.reg["tables"]["sites-r4"]["columns"]}
        for name, c in spec.items():
            if name not in sites.columns or name in ("lat", "lon"):
                continue
            s = sites[name]
            if s.dtype == pl.Boolean:
                res[name] = {"kind": "yes/no", "trait": c["trait"], "unit": c["unit"], "n": s.len() - s.null_count(),
                             "share_true": None if s.null_count() == s.len() else round(float(s.drop_nulls().mean()), 6),
                             "note": "left out of the closeness sum; shown as same/different (ADR-0005 D5)"}
                continue
            v = s.drop_nulls().cast(pl.Float64)
            if v.len() == 0:
                res[name] = {"kind": "number", "trait": c["trait"], "unit": c["unit"], "n": 0, "iqr": None,
                             "note": "no values yet"}
                continue
            q1, q3 = v.quantile(0.25, "linear"), v.quantile(0.75, "linear")
            res[name] = {"kind": "number", "trait": c["trait"], "unit": c["unit"], "n": v.len(),
                         "min": v.min(), "q1": q1, "median": v.median(), "q3": q3, "max": v.max(), "iqr": q3 - q1,
                         "inSum": bool(q3 - q1 > 0),
                         "note": "IQR over all land hexagons with a value; s_t in ADR-0005 D5" + ("" if q3 - q1 > 0 else "; IQR is 0, so shown as same/different")}
        return res

    def coverage(self, sites: pl.DataFrame, monthly: pl.DataFrame) -> dict:
        cols = [c | {"table": t} for t in self.reg["tables"] for c in self.reg["tables"][t]["columns"]]
        def backing(trait: str) -> list[dict]:
            out = []
            for c in cols:
                if c["trait"] != trait:
                    continue
                df = sites if c["table"] == "sites-r4" else monthly
                present = c["name"] in df.columns
                nr = round(df[c["name"]].null_count() / df.height, 6) if present else None
                out.append({"column": c["name"], "table": c["table"], "status": c["status"] if present else "planned",
                            "nullRate": nr})
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
        full = feature_coverage(features, preparation["features"], {"sites-r4": sites, "sites-r4-monthly": monthly})
        for category in categories.values():
            category["featureCompleteness"] = "not-established"
            category["note"] = "Trait-column availability is not evidence that all tests in this category can be performed."
        return {"objectives": objectives, "categories": categories, "earthCannot": self.reg["earthCannot"],
                "featureInventory": {"path": str(feature_path.relative_to(REPO)), "sha256": sha256(feature_path),
                                     "mappingSha256": sha256(mapping_path), "count": len(full)},
                "features": full, "workflowModules": preparation["workflowModules"],
                "additionalEvidenceGaps": preparation["additionalEvidenceGaps"],
                "testCatalog": {"source": test_catalog["source"], "selection": test_catalog["selection"],
                                "sha256": sha256(test_path), "count": len(categories)},
                "planetaryAssemblyStatus": "not-built: generic envelopes are not measured per-target feature tables",
                "campaignTestAssemblyStatus": "partial: quoted records preserved; source extraction of historical test conditions remains #74"}

    # ---- run ----------------------------------------------------------------
    def run(self) -> int:
        t0 = time.time()
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
        print("[trait-scales, data-coverage]", flush=True)
        OUT.mkdir(parents=True, exist_ok=True)
        for name, obj in (("trait-scales", self.scales(sites)), ("data-coverage", self.coverage(sites, monthly))):
            p = OUT / f"{name}.json"
            p.write_text(json.dumps(obj, indent=2, default=float) + "\n", encoding="utf-8")
            self.report["outputs"][name] = {"path": str(p.relative_to(REPO)), "sha256": sha256(p), "bytes": p.stat().st_size}
        self.report["runtime_s"] = round(time.time() - t0, 1)
        self.report["result"] = "ALL PASS" if self.fails == 0 else f"{self.fails} CHECK(S) FAILED"
        (OUT / "assembly-report.json").write_text(json.dumps(self.report, indent=2, default=float) + "\n", encoding="utf-8")
        print(f"skipped (planned, source not built yet): {len(self.report['skipped'])}")
        for s in self.report["skipped"]:
            print(f"  - {s.get('table')}.{s.get('column', '*')} from {s['source']}")
        for k, v in self.report["outputs"].items():
            print(f"  {k:26s} {v.get('rows', ''):>10} rows  {v['sha256'][:16]}  {v['bytes']:,} B")
        print(self.report["result"], f"({self.report['runtime_s']} s)")
        return 0 if self.fails == 0 else 1


if __name__ == "__main__":
    sys.exit(Build().run())
