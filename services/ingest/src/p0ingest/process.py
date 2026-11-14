"""Build cells-r<res>.parquet: one row per H3 land cell, raw P0 traits, explicit nulls.

Inputs are only files recorded in data/snapshots/MANIFEST.json. A trait we
could not compute is null in its column AND named in `missing_reason`.
"""
from __future__ import annotations

import glob
import hashlib
import json
import time
from datetime import datetime, timezone

import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq
from pyhdf.SD import SD, SDC

from .grid import DERIVED, RES, cell_center, cmg_cell_map, group_index
from .snapshots import SNAP, load_manifest, sha256

LST_SCALE = 0.02  # K per count, MOD11C3 V061; fill 0; valid 7500..65535
OBLIQUITY = 23.44


def _manifest_files(dataset_id: str) -> list[dict]:
    rows = [e for e in load_manifest()["entries"] if e["datasetId"] == dataset_id]
    return sorted(rows, key=lambda e: e["localPath"])


def _group_stat(values: np.ndarray, order, starts, how: str) -> tuple[np.ndarray, np.ndarray]:
    """Per-cell statistic over the CMG pixels of each cell, ignoring NaN.
    Returns (stat, n_valid). stat is NaN where a cell has no valid pixel."""
    v = values.ravel()[order].astype(np.float64)
    ncell = len(starts)
    gid = np.repeat(np.arange(ncell), np.diff(np.append(starts, len(order))))
    ok = ~np.isnan(v)
    n = np.bincount(gid[ok], minlength=ncell)
    if how == "mean":
        s = np.bincount(gid[ok], weights=v[ok], minlength=ncell)
        out = np.where(n > 0, s / np.maximum(n, 1), np.nan)
    elif how == "median":
        key = np.lexsort((np.where(ok, v, np.inf), gid))  # NaN (as inf) last in each cell
        vs = v[key]
        lo = starts + (np.maximum(n, 1) - 1) // 2
        hi = starts + np.maximum(n, 1) // 2
        out = np.where(n > 0, (vs[lo] + vs[hi]) / 2, np.nan)
    else:
        raise ValueError(how)
    return out, n


def thermal():
    files = _manifest_files("modis-mod11c3")
    dmax = nmin = None
    rsum = np.zeros((3600, 7200)); rn = np.zeros((3600, 7200), dtype=np.int16)
    for e in files:
        sd = SD(str(SNAP.parent.parent / e["localPath"]), SDC.READ)
        day = sd.select("LST_Day_CMG")[:].astype(np.float64)
        night = sd.select("LST_Night_CMG")[:].astype(np.float64)
        day[day < 7500] = np.nan; night[night < 7500] = np.nan
        day *= LST_SCALE; night *= LST_SCALE
        dmax = day if dmax is None else np.fmax(dmax, day)
        nmin = night if nmin is None else np.fmin(nmin, night)
        both = ~np.isnan(day) & ~np.isnan(night)
        rsum[both] += (day - night)[both]; rn[both] += 1
    rng = np.where(rn > 0, rsum / np.maximum(rn, 1), np.nan)
    return {"lst_day_max_k": dmax, "lst_night_min_k": nmin, "lst_diurnal_range_mean_k": rng,
            "lst_months_with_range": np.where(rn > 0, rn, np.nan).astype(np.float64)}, files


def landcover():
    files = _manifest_files("modis-mcd12c1")
    sd = SD(str(SNAP.parent.parent / files[0]["localPath"]), SDC.READ)
    pct = sd.select("Land_Cover_Type_1_Percent")
    out = {}
    for name, layer in (("barren_pct", 16), ("snow_ice_pct", 15), ("water_pct", 0)):
        a = pct[:, :, layer].astype(np.float64)
        a[a > 100] = np.nan
        out[name] = a
    return out, files


def permafrost():
    """ESA CCI Permafrost v5.0 2023 PFR (% probability) block-averaged from
    0.01 deg to the 0.05 deg CMG grid. Outside the two product domains
    (NH 25-85 N, Antarctica 60-85 S) stays NaN: unknown, not zero."""
    out = np.full((3600, 7200), np.nan)
    used = []
    for ds_id, top in (("esa-cci-permafrost-extent-nh", 85.0), ("esa-cci-permafrost-extent-antarctica", -60.0)):
        files = _manifest_files(ds_id); used += files
        import rasterio
        path = SNAP.parent.parent / files[0]["localPath"]
        with rasterio.open(f"netcdf:{path}:PFR") as v:
            a = v.read(1).astype(np.float64)
        a[a > 100] = np.nan
        h, w = a.shape
        blk = a.reshape(h // 5, 5, w // 5, 5)
        with np.errstate(invalid="ignore"):
            m = np.nanmean(blk, axis=(1, 3))
        r0 = int(round((90.0 - top) / 0.05))
        out[r0:r0 + m.shape[0], :] = m
    return out, used


def terrain_columns(cells_hex: np.ndarray, res: int):
    """Merge the terrain pass (terrain.py) if it has run; else None."""
    npz = DERIVED / f"terrain-r{res}.npz"
    if not npz.exists():
        return None
    t = np.load(npz)
    assert (t["h3"] == cells_hex).all(), "terrain pass built on a different grid"
    return {k: t[k] for k in t.files if k != "h3"}, json.loads((DERIVED / f"terrain-r{res}.meta.json").read_text())


def illumination(lat: np.ndarray) -> dict[str, np.ndarray]:
    """Computed from latitude only (no dataset): noon sun elevation range over a
    year and whether the cell gets polar night/day. Ignores terrain shadowing."""
    a = np.abs(lat)
    noon_max = np.minimum(90.0, 90.0 - a + OBLIQUITY)
    noon_min = 90.0 - a - OBLIQUITY
    return {"sun_noon_elev_max_deg": noon_max, "sun_noon_elev_min_deg": noon_min,
            "polar_night": noon_min < 0, "polar_day": a > 90.0 - OBLIQUITY}


def build(res: int = RES) -> dict:
    t0 = time.time(); timing = {}
    cellmap, landp = cmg_cell_map(res); order, cells, starts = group_index(cellmap)
    timing["grid_s"] = round(time.time() - t0, 1)
    cols: dict[str, np.ndarray] = {}
    lat = np.empty(len(cells)); lon = np.empty(len(cells))
    for i, c in enumerate(cells):
        lat[i], lon[i] = cell_center(c)
    cols["cmg_pixels"] = np.diff(np.append(starts, len(order))).astype(np.float64)
    cols["land_pct_mean"], _ = _group_stat(landp.astype(np.float64), order, starts, "mean")
    used = {}

    t = time.time(); th, f = thermal(); used["modis-mod11c3"] = f
    for k, v in th.items():
        cols[k], _ = _group_stat(v, order, starts, "median")
    cols["lst_valid_pixels"] = _group_stat(th["lst_diurnal_range_mean_k"], order, starts, "mean")[1].astype(np.float64)
    timing["thermal_s"] = round(time.time() - t, 1)

    t = time.time(); lc, f = landcover(); used["modis-mcd12c1"] = f
    for k, v in lc.items():
        cols[k], _ = _group_stat(v, order, starts, "mean")
    timing["landcover_s"] = round(time.time() - t, 1)

    t = time.time(); pf, f = permafrost(); used["esa-cci-permafrost"] = f
    cols["permafrost_pct"], _ = _group_stat(pf, order, starts, "mean")
    timing["permafrost_s"] = round(time.time() - t, 1)

    hexes = np.array([format(int(c), "x") for c in cells])
    terr = terrain_columns(hexes, res)
    if terr is not None:
        tcols, tmeta = terr
        cols.update(tcols)
        used["copernicus-dem-glo30"] = [{"localPath": tmeta["ledger"], "sha256": sha256(SNAP.parent.parent / tmeta["ledger"])}]

    ill = illumination(lat)
    # Dimensions with no input yet: explicit nulls + reason (rule 3, issue #19 kill criterion).
    missing = {
        "dustProcess": "MERRA-2 M2TMNXAER: GES DISC returns HTTP 403 (Earthdata app not approved yet, 2026-11-14)",
        "waterIce": ("ESA CCI permafrost v5.0 2023 covers only 25-85 N and 60-85 S, and inside that it writes "
                     "fill 255 where it did not model (ocean and warm land, e.g. Montreal). Fill is unknown, not 0%. "
                     "PFR is MODIS-LST-driven, so it is not independent of the thermal columns"),
        "subsurface": "no global Earth subsurface dataset in P0",
        "operations": "accessibility/WDPA not ingested yet (gate 5 deferred)",
    }
    n = len(cells)
    table = {
        "h3": pa.array(hexes),
        "res": pa.array(np.full(n, res, dtype=np.int8)),
        "lat": pa.array(lat), "lon": pa.array(lon),
    }
    for k, v in cols.items():
        table[k] = pa.array(v, from_pandas=True)  # NaN -> null
    for k, v in ill.items():
        table[k] = pa.array(v)
    table["dust_aod_mean"] = pa.nulls(n, pa.float64())
    if terr is not None:
        nt = int(np.isnan(cols["slope_mean_deg"]).sum())
        missing["terrain"] = (f"{nt} cells ({nt / n:.2%}) have no GLO-30 sample: mostly coastal edge cells, small "
                              "islands, the Caspian Sea area and cells beyond 84 deg, where no tile is listed or no "
                              "tile pixel lands on the cell's land pixels")
    if terr is None:
        missing["terrain"] = "Copernicus GLO-30 overview pass not run yet"
        for k in ("dem_pixels", "elev_mean_m", "elev_min_m", "elev_max_m", "slope_mean_deg",
                  "slope_frac_lt5", "slope_frac_lt15", "slope_frac_gt30"):
            table[k] = pa.nulls(n, pa.float64())
    table["missing_reason"] = pa.array([json.dumps(missing, sort_keys=True)] * n)
    tbl = pa.table(table)

    out = DERIVED / f"cells-r{res}.parquet"
    meta = {
        "generatedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "h3Res": res, "cells": n,
        "inputs": {k: [{"localPath": e["localPath"], "sha256": e["sha256"]} for e in v] for k, v in used.items()},
        "computed": {"illumination": "latitude-only solar geometry, obliquity 23.44 deg, no terrain shadowing"},
        "missing": missing,
    }
    tbl = tbl.replace_schema_metadata({"cosmic-consultants": json.dumps(meta)})
    pq.write_table(tbl, out, compression="zstd")
    timing["total_s"] = round(time.time() - t0, 1)
    meta.update(path=str(out.relative_to(SNAP.parent.parent)), sha256=sha256(out), bytes=out.stat().st_size, timing=timing)
    meta["nullRate"] = {c: round(tbl[c].null_count / n, 4) for c in tbl.column_names}
    (DERIVED / f"cells-r{res}.meta.json").write_text(json.dumps(meta, indent=2) + "\n")
    return meta


if __name__ == "__main__":
    m = build()
    print(json.dumps({k: m[k] for k in ("path", "cells", "sha256", "bytes", "timing", "nullRate")}, indent=1))
