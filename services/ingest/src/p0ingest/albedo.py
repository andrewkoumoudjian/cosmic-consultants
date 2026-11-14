"""W26 (#66): MODIS MCD43C3 v061 shortwave albedo -> the albedo family tables.

Source: "MODIS/Terra+Aqua BRDF/Albedo Albedo Daily L3 Global 0.05Deg CMG
V061" (MCD43C3.061, LP DAAC, DOI 10.5067/MODIS/MCD43C3.061, CC0 by NASA
ESDIS default). Catalog row: data/catalog/modis-mcd43c3-albedo.yaml.

What this source really is (kept honest, no product semantics invented):
- MCD43C3 v061 is a DAILY product. One granule is one day's BRDF/albedo
  retrieval computed from the observations of a 16-day window. For granule
  A<2023><doy> CMR gives time span (doy-8 .. doy+7), e.g. A2023015 =
  2023-01-07T00:00Z .. 2023-01-22T23:59Z. It is NOT an independent daily
  observation, and NOT a calendar-month integrated mean.
- We keep 12 explicitly dated samples: the granule dated the 15th of each
  2023 month. The remaining derivation (a true calendar-month mean over all
  overlapping windows) is deliberately NOT performed; the sampled retrieval is
  retained as what it is.

Outputs (data/snapshots/_derived/, gitignored, mirrored to Drive):
  albedo-r4-monthly.parquet  h3 x 12 months = 1,101,600 rows; exactly the
                            master key set of cells-r4-monthly (h3, month).
                            Columns: h3, month, albedo_ws_sw, albedo_bs_sw,
                            albedo_valid_px, albedo_bs_valid_px, missing_reason.
  albedo-r4.parquet         91,800 rows: h3, albedo_ws_sw_mean,
                            albedo_months_used, albedo_bs_sw_mean,
                            albedo_bs_months_used, missing_reason.

Statistic: median over the hexagon's 0.05 deg CMG land pixels of that dated
retrieval's albedo (white-sky and black-sky shortwave, dimensionless 0-1,
scaled from int). Coverage rule (issue #66): a hexagon's monthly value is
kept only if >= 25% of its CMG land pixels have a valid, best-quality
retrieval that day; otherwise null with reason codes. The denominator is the
hexagon's CMG land-pixel count (cmg_pixels, same as the thermal tables).

Model/proxy limits (explicit): white-sky albedo is the bihemispherical
reflectance in the shortwave band under isotropic (fully diffuse) illumination.
Black-sky is directional-hemispherical under a direct beam at local solar noon.
Neither is a lunar bolometric albedo measurement, neither is a thermal/emissivity
observable, and the two are kept as distinct fields, never mixed.
"""
from __future__ import annotations

import datetime as dt
import json
import re
import sys
import time
from datetime import datetime, timezone

import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq
from pyhdf.SD import SD, SDC

from .grid import DERIVED, RES, cmg_cell_map, group_index
from .snapshots import SNAP, cmr_granule_urls, fetch, load_manifest, sha256

YEAR = 2023
DATASET = "modis-mcd43c3-albedo"
CONCEPT = "C2532068039-LPCLOUD"
MIN_PIXEL_SHARE = 0.25  # issue #66: >= 25% valid CMG-pixel support per hexagon
SCALE = 0.001           # verified from the SDS attributes (scale_factor)
FILL = 32767            # verified _FillValue of the albedo SDS
QA_FILL = 255
QA_BEST = 0             # "best quality, 100% with full inversions" (SDS description)

_DOY_RE = re.compile(r"\.A(\d{4})(\d{3})\.")
_RE_BLOCK = re.compile(r"OBJECT\s*=\s*(\w+)(.*?)END_OBJECT", re.S)
_RE_VALUE = re.compile(r"VALUE\s*=\s*\"?([\w\-:.T ]+)\"?")


def target_doys() -> list[tuple[int, int]]:
    """(month, doy of the 15th) for each month of the base year."""
    return [(m, dt.date(YEAR, m, 15).timetuple().tm_yday) for m in range(1, 13)]


def month_of(local_path: str) -> int:
    m = _DOY_RE.search(local_path)
    if not m:
        raise ValueError(f"no A<year><doy> in {local_path}")
    year, doy = int(m.group(1)), int(m.group(2))
    if year != YEAR:
        raise ValueError(f"{local_path}: year {year}, expected {YEAR}")
    month = (dt.date(year, 1, 1) + dt.timedelta(days=doy - 1)).month
    if dt.date(year, 1, 1) + dt.timedelta(days=doy - 1) == dt.date(YEAR, month, 15):
        return month
    raise ValueError(f"{local_path}: granule dated {doy} is not the 15th of a 2023 month")


def window_dates(local_path: str) -> dict:
    """CMR-verified 16-day window dates for one granule (documented at probe)."""
    m = _DOY_RE.search(local_path)
    doy = int(m.group(2))
    nominal = dt.date(YEAR, 1, 1) + dt.timedelta(days=doy - 1)
    return {"nominal": nominal.isoformat(),
            "windowStart": (nominal - dt.timedelta(days=8)).isoformat(),
            "windowEnd": (nominal + dt.timedelta(days=7)).isoformat()}


def fetch_albedo() -> list[dict]:
    """Download the 12 dated samples (15th of each 2023 month) once."""
    temporal = f"{YEAR}-01-01T00:00:00Z,{YEAR}-12-31T23:59:59Z"
    urls = cmr_granule_urls(CONCEPT, temporal, ".hdf", page_size=2000)
    if not urls:
        raise RuntimeError("CMR returned no MCD43C3 2023 granule links")
    got = []
    for month, doy in target_doys():
        pat = re.compile(rf"\.A{YEAR}{doy:03d}\.")
        hits = [u for u in urls if pat.search(u)]
        if len(hits) != 1:
            raise RuntimeError(f"month {month}: expected exactly 1 granule for "
                               f"{YEAR}-{month:02d}-15, found {len(hits)}")
        p = fetch(DATASET, hits[0])
        got.append(p)
        print(f"ok  m={month:02d} {p.name} {p.stat().st_size} B", flush=True)
    return got


def _group_stat(values: np.ndarray, order, starts, how: str):
    """Per-cell statistic over the CMG pixels of each cell, NaN ignored.
    Same semantics as process._group_stat (kept local so this module does not
    depend on parent-owned code internals)."""
    v = values.ravel()[order].astype(np.float64)
    ncell = len(starts)
    gid = np.repeat(np.arange(ncell), np.diff(np.append(starts, len(order))))
    ok = ~np.isnan(v)
    n = np.bincount(gid[ok], minlength=ncell)
    if how == "mean":
        s = np.bincount(gid[ok], weights=v[ok], minlength=ncell)
        out = np.where(n > 0, s / np.maximum(n, 1), np.nan)
    elif how == "median":
        key = np.lexsort((np.where(ok, v, np.inf), gid))  # NaN (as inf) last
        vs = v[key]
        lo = starts + (np.maximum(n, 1) - 1) // 2
        hi = starts + np.maximum(n, 1) // 2
        out = np.where(n > 0, (vs[lo] + vs[hi]) / 2, np.nan)
    else:
        raise ValueError(how)
    return out, n


def _verify_sds(ds, name: str, scale: float, fill: int, vr: list) -> None:
    a = ds.attributes()
    got = (name, a.get("scale_factor"), a.get("_FillValue"), list(a.get("valid_range", [])))
    want = (name, scale, fill, vr)
    if got != want:
        raise RuntimeError(f"MCD43C3 SDS schema changed: got {got}, expected {want} -- "
                           "re-verify against the LP DAAC user guide before using this file")


def _read_granule(local_path: str) -> dict:
    """One dated sample: white-sky + black-sky shortwave albedo (NaN invalid)
    plus the per-granule QA counting block and the file's own window dates."""
    sd = SD(str(SNAP.parent.parent / local_path), SDC.READ)
    ws = sd.select("Albedo_WSA_shortwave")
    bs = sd.select("Albedo_BSA_shortwave")
    qa = sd.select("Albedo_Quality")
    _verify_sds(ws, "Albedo_WSA_shortwave", SCALE, FILL, [0, 32766])
    _verify_sds(bs, "Albedo_BSA_shortwave", SCALE, FILL, [0, 32766])
    _verify_sds(qa, "Albedo_Quality", None, QA_FILL, [0, 254])  # quality byte: scale_factor attribute absent
    w = ws[:].astype(np.float64)
    b = bs[:].astype(np.float64)
    q = qa[:]
    qa_counts = {int(k): int(n) for k, n in zip(*np.unique(q, return_counts=True))}
    core = sd.attributes().get("CoreMetadata.0", "")
    dates = {}
    for m in _RE_BLOCK.finditer(core):
        name, block = m.group(1), m.group(2)
        vm = _RE_VALUE.search(block)
        if vm and name.startswith("RANGE"):
            dates[name] = vm.group(1).strip()
    sd.end()
    w_present, b_present = (w != FILL), (b != FILL)
    n_nonfill = int((w_present & b_present).sum())
    w_best, b_best = (q == QA_BEST) & w_present, (q == QA_BEST) & b_present
    n_best = int((w_best & b_best).sum())
    w[~w_best] = np.nan
    b[~b_best] = np.nan
    return {"wsa": w * SCALE, "bsa": b * SCALE,
            "qa_counts": qa_counts, "n_best_px": n_best, "n_nonfill_px": n_nonfill,
            "n_best_wsa_px": int(w_best.sum()), "n_best_bsa_px": int(b_best.sum()),
            "window": dates}


def monthly_reasons(ws, bs, nws, nbs, required):
    reasons = []
    for w, b, nw, nb, need in zip(ws, bs, nws, nbs, required):
        row = {}
        for name, value, count in [("albedo_ws_sw", w, nw), ("albedo_bs_sw", b, nb)]:
            if np.isnan(value):
                if count == 0: row[name] = "no-best-quality-retrieval"
                elif count < need: row[name] = "too-few-albedo-pixels"
                else: raise ValueError(f"{name}: null despite sufficient source support")
        reasons.append(json.dumps(row, sort_keys=True))
    return reasons


def master_keys(res: int = RES) -> np.ndarray:
    """h3 master key set, exactly the rows of cells-r<res>.parquet (L1)."""
    tbl = pq.read_table(DERIVED / f"cells-r{res}.parquet", columns=["h3"])
    keys = tbl["h3"].to_pylist()
    if len(set(keys)) != len(keys):
        raise RuntimeError("duplicate h3 in cells-r4.parquet")
    return np.array(keys)


def build(res: int = RES) -> dict:
    t0 = time.time()
    files = [e for e in load_manifest()["entries"] if e.get("datasetId") == DATASET]
    files = sorted(files, key=lambda e: e["localPath"])
    months = [month_of(e["localPath"]) for e in files]
    if sorted(months) != list(range(1, 13)):
        raise RuntimeError(f"expected exactly one dated sample per month, got {months}")

    cellmap, _landp = cmg_cell_map(res)
    order, cells, starts = group_index(cellmap)
    size = np.diff(np.append(starts, len(order))).astype(np.float64)
    need = MIN_PIXEL_SHARE * size
    master = master_keys(res)
    grid_hex = np.array([format(int(c), "x") for c in cells])
    if set(master.tolist()) != set(grid_hex.tolist()):
        raise RuntimeError("grid cells and the cells-r4.parquet master key set differ; "
                           "albedo tables must match the master key set exactly")
    pos = {h: i for i, h in enumerate(grid_hex.tolist())}
    perm = np.array([pos[h] for h in master.tolist()])
    hexes = master
    same_order = bool((perm == np.arange(len(hexes))).all())  # else permute after the loop

    ncell = len(hexes)
    ws_m = np.full((ncell, 12), np.nan)
    bs_m = np.full((ncell, 12), np.nan)
    nws = np.zeros((ncell, 12))
    nbs = np.zeros((ncell, 12))
    thin_ws = np.zeros((ncell, 12), dtype=bool)
    inputs, qa_block = [], []
    for e in files:
        raw_path = SNAP.parent.parent / e["localPath"]
        if raw_path.stat().st_size != e["bytes"] or sha256(raw_path) != e["sha256"]:
            raise RuntimeError(f"source input hash/size mismatch: {e['localPath']}")
        mo = month_of(e["localPath"])
        g = _read_granule(e["localPath"])
        exp = window_dates(e["localPath"])
        if (g["window"].get("RANGEBEGINNINGDATE") != exp["windowStart"]
                or g["window"].get("RANGEENDINGDATE") != exp["windowEnd"]):
            raise RuntimeError(f"month {mo}: file-embedded window {g['window']} does not "
                               f"match the CMR-derived window {exp} -- abort")
        wmed, nw = _group_stat(g["wsa"], order, starts, "median")
        bmed, nb = _group_stat(g["bsa"], order, starts, "median")
        ws_m[:, mo - 1] = np.where(nw >= need, wmed, np.nan)
        bs_m[:, mo - 1] = np.where(nb >= need, bmed, np.nan)
        nws[:, mo - 1] = nw
        nbs[:, mo - 1] = nb
        thin_ws[:, mo - 1] = (nw > 0) & (nw < need)
        qa_block.append({"month": mo, "granule": e["localPath"].rsplit("/", 1)[-1],
                         "n_best_px": g["n_best_px"], "n_nonfill_px": g["n_nonfill_px"],
                         "pairedCountGrain": "native pixels where both fields are non-fill; best count also requires QA=0",
                         "n_best_wsa_px": g["n_best_wsa_px"], "n_best_bsa_px": g["n_best_bsa_px"],
                         "qa_counts": g["qa_counts"], "window": g["window"]})
        inputs.append({"localPath": e["localPath"], "sha256": e["sha256"], "month": mo,
                       "nominalDate": window_dates(e["localPath"])["nominal"],
                       "window": g["window"]})

    months = np.tile(np.arange(1, 13, dtype=np.int8), ncell)
    if not same_order:  # keep master row order exactly
        ws_m, bs_m, nws, nbs, thin_ws = (a[perm] for a in (ws_m, bs_m, nws, nbs, thin_ws))
    ws_f = ws_m.reshape(-1)
    bs_f = bs_m.reshape(-1)
    nws_f = nws.reshape(-1)
    thin_f = thin_ws.reshape(-1)
    reasons = monthly_reasons(ws_f, bs_f, nws.reshape(-1), nbs.reshape(-1), np.repeat(need, 12))

    tbl = pa.table({
        "h3": pa.array(np.repeat(hexes, 12)),
        "month": pa.array(months),
        "albedo_ws_sw": pa.array(ws_f, from_pandas=True),
        "albedo_bs_sw": pa.array(bs_f, from_pandas=True),
        "albedo_valid_px": pa.array(nws.reshape(-1).astype(np.int32)),
        "albedo_bs_valid_px": pa.array(nbs.reshape(-1).astype(np.int32)),
        "missing_reason": pa.array(reasons),
    })
    assert tbl.num_rows == 12 * ncell, (tbl.num_rows, 12 * ncell)
    out_m = DERIVED / f"albedo-r{res}-monthly.parquet"
    meta_m = {
        "generatedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "h3Res": res, "cells": int(ncell), "rows": int(tbl.num_rows), "year": YEAR,
        "family": "albedo", "source": "MCD43C3 v061 (LP DAAC, DOI 10.5067/MODIS/MCD43C3.061, CC0)",
        "observable": (
            "shortwave (0.3-5.0 um) broadband white-sky (albedo_ws_sw) and black-sky "
            "(albedo_bs_sw) albedo, dimensionless 0-1, int16 counts x 0.001 "
            "(scale/fill verified from the SDS attributes at read time)"
        ),
        "timeSupport": (
            "MCD43C3 v061 is a DAILY product: one granule = one day's BRDF/albedo "
            "retrieval from a 16-day observation window. This table keeps 12 dated "
            "samples, the granule dated the 15th of each 2023 month (filename A<2023><doy>), "
            "each one 16-day retrieval window (not an independent daily observation, "
            "not a calendar-month integrated mean; the selected windows leave calendar gaps). "
            "Per-sample window dates are read from each file's CoreMetadata "
            "(RANGEBEGINNINGDATE..RANGEENDINGDATE)."
        ),
        "statistic": (
            "median over the hexagon's 0.05 deg CMG land pixels (identical pixel->cell "
            "map as the thermal tables, cmg_h3r4 cache); kept only if >= 25% of those "
            f"pixels ({MIN_PIXEL_SHARE:.0%}, share of cmg_pixels) have a valid "
            "retrieval, else null with reason too-few-albedo-pixels"
        ),
        "qualityRule": (
            f"only Albedo_Quality == {QA_BEST} pixels count ('best quality, 100% with full "
            "inversions', SDS description); pixels with QA 1-5 or fill are dropped. "
            "Both white-sky and black-sky must be non-fill for the pixel to count "
            "(per-field valid-pixel counts are recorded separately)."
        ),
        "modelLimits": (
            "White-sky = bihemispherical reflectance (fully diffuse sky); "
            "black-sky = directional-hemispherical reflectance (direct beam at local "
            "solar noon). These are Earth shortwave reflectance quantities, NOT a "
            "calibrated lunar bolometric measurement and NOT thermal emissivity; the "
            "Moon/Mars regolith/bolometric albedo targets need a proxy mapping which "
            "is engine work, not ingest work."
        ),
        "coverage": {"minPixelShare": MIN_PIXEL_SHARE},
        "inputs": inputs,
        "qaCounts": qa_block,
    }
    tbl_m = tbl.replace_schema_metadata({"cosmic-consultants": json.dumps(meta_m)})
    pq.write_table(tbl_m, out_m, compression="zstd")
    meta_m.update(path=str(out_m.relative_to(SNAP.parent.parent)), sha256=sha256(out_m),
                  bytes=out_m.stat().st_size)
    meta_m["nullRate"] = {c: round(tbl[c].null_count / tbl.num_rows, 4) for c in tbl.column_names if c != "missing_reason"}
    (DERIVED / f"albedo-r{res}-monthly.meta.json").write_text(json.dumps(meta_m, indent=2) + "\n")

    # yearly table on the same master rows
    with np.errstate(all="ignore"):
        ws_mean = np.nanmean(np.where(np.isnan(ws_m), np.nan, ws_m), axis=1)
        bs_mean = np.nanmean(np.where(np.isnan(bs_m), np.nan, bs_m), axis=1)
    ws_n = np.sum(~np.isnan(ws_m), axis=1).astype(np.float64)
    bs_n = np.sum(~np.isnan(bs_m), axis=1).astype(np.float64)
    reasons_y = []
    for wm, bn, wsn in zip(np.isnan(ws_mean), np.isnan(bs_mean), ws_n):
        r = {}
        if wm:
            r["albedo_ws_sw_mean"] = "no-albedo-months" if wsn == 0 else "partial-year"
        if bn:
            r["albedo_bs_sw_mean"] = "no-bs-months"
        reasons_y.append(json.dumps(r, sort_keys=True))
    tbl_y = pa.table({
        "h3": pa.array(hexes),
        "albedo_ws_sw_mean": pa.array(ws_mean, from_pandas=True),
        "albedo_months_used": pa.array(ws_n).cast(pa.int32()),
        "albedo_bs_sw_mean": pa.array(bs_mean, from_pandas=True),
        "albedo_bs_months_used": pa.array(bs_n).cast(pa.int32()),
        "missing_reason": pa.array(reasons_y),
    })
    out_y = DERIVED / f"albedo-r{res}.parquet"
    meta_y = {
        "generatedAt": meta_m["generatedAt"], "h3Res": res, "cells": int(ncell), "year": YEAR,
        "family": "albedo", "source": meta_m["source"],
        "observable": meta_m["observable"],
        "timeSupport": ("mean over the 12 dated monthly samples of the same year "
                        "(each sample a 16-day retrieval window; missing samples are "
                        "skipped, not filled; albedo_months_used gives the count). "
                        "This is a mean of 12 dated retrievals, NOT an annual "
                        "time-integrated mean of incident/reflected energy."),
        "statistic": "mean over the months with a kept median; months_used recorded per row",
        "qualityRule": meta_m["qualityRule"],
        "modelLimits": meta_m["modelLimits"],
        "inputs": inputs,
        "monthlyTable": {"path": meta_m["path"], "sha256": meta_m["sha256"], "bytes": meta_m["bytes"]},
    }
    tbl_y = tbl_y.replace_schema_metadata({"cosmic-consultants": json.dumps(meta_y)})
    pq.write_table(tbl_y, out_y, compression="zstd")
    meta_y.update(path=str(out_y.relative_to(SNAP.parent.parent)), sha256=sha256(out_y),
                  bytes=out_y.stat().st_size,
                  seconds=round(time.time() - t0, 1))
    meta_y["nullRate"] = {c: round(tbl_y[c].null_count / tbl_y.num_rows, 4) for c in tbl_y.column_names if c != "missing_reason"}
    (DERIVED / f"albedo-r{res}.meta.json").write_text(json.dumps(meta_y, indent=2) + "\n")
    return {"monthly": meta_m, "yearly": meta_y}


def main(argv: list[str] | None = None) -> int:
    argv = argv or sys.argv[1:]
    if "--fetch" in argv:
        fetch_albedo()
        return 0
    meta = build()
    print(json.dumps({k: {kk: meta[k][kk] for kk in ("path", "sha256", "bytes", "nullRate")}
                      for k in ("monthly", "yearly")}, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
