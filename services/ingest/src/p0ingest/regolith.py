"""W26 (#66): ORNL DAAC 1304 Pelletier et al. 2016 soil/regolith/sediment
gridded thickness -> regolith-r4.parquet (one row per H3 r4 land cell).

Source: "A Global 1-km Gridded Thickness of Soil, Regolith, and Sedimentary
Deposit Layers" (Pelletier et al. 2016, ORNL DAAC ds_id 1304, DOI
10.3334/ORNLDAAC/1304). Official user guide (stored as a snapshot):
"openly shared, without restriction, in accordance with the EOSDIS Data Use
and Citation Guidance".

What this source really is (kept honest, no product semantics invented):
- Modeled thicknesses of the permeable layers above bedrock, by landform,
  for the "geological present" (one-time estimate; 1900-2015 date range is a
  completeness placeholder). NOT a measured ice-table depth, NOT a lunar
  regolith equivalent; upland regolith thickness is flagged by the guide
  itself as "an experimental product with a high degree of uncertainty".
- Six 30-arcsecond (43,200 x 18,000) GeoTIFF layers, 90 N to 60 S (clipped;
  no Antarctica). Native NoData -1. Valid ranges from the guide (verified
  live against the files): regolith 0-50 m, soil 0-4.2 m, sedimentary deposit
  0-50 m, area+TWI-weighted average 0-50 m. The 50 m maximum is the published
  upper valid bound. Clipping/censoring is not established by that range table.

Outputs (data/snapshots/_derived/): regolith-r4.parquet, 91,800 rows, exactly
the master key set of cells-r4.parquet. Columns:
  h3
  regolith_thick_m          median of upland_hill-slope_regolith_thickness
                            (soil + intact regolith) over the hexagon's
                            valid 30" pixels [m]  <- the regolith trait
  regolith_support_px       valid upland-regolith pixels / upland pixels [0-1]
  soil_thick_m              median of upland_hill-slope_soil_thickness [m]
  soil_support_px           valid soil pixels / upland pixels [0-1]
  sediment_thick_m          median of upland_valley-bottom_and_lowland_
                            sedimentary_deposit_thickness [m]
  avg_soil_sed_thick_m      median of the product's own area+TWI-weighted
                            average_soil_and_sedimentary-deposit layer [m]
  hillslope_frac_mean       mean of the hill-slope area fraction over the
                            product's land pixels [0-1]
  regolith_valid_px, soil_valid_px, sediment_valid_px, avg_valid_px,
                            hillslope_valid_px  actual per-hex counts
  mask_upland_px, mask_lowland_px, mask_lake_px, mask_ice_px
                            30" pixels by land_cover_mask class per hex
  missing_reason            JSON per row: only null traits of that row

Layer medians are over each layer's OWN support (uplands vs valley-bottom +
lowlands); layer distinctions are preserved, never blended into one number
except where the product itself publishes a blended layer (avg_soil_sed).
"""
from __future__ import annotations

import datetime as dt
import json
import sys
import time
from concurrent.futures import ProcessPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq
import rasterio
from rasterio.windows import Window

from .snapshots import SNAP, load_manifest, sha256, fetch

DATASET = "ornl-global-soil-regolith-sediment"
_PROTECTED = ("https://data.ornldaac.earthdata.nasa.gov/protected/global_soil/"
              "Global_Soil_Regolith_Sediment/data/")
_PUBLIC = ("https://data.ornldaac.earthdata.nasa.gov/public/global_soil/"
           "Global_Soil_Regolith_Sediment/data/")

LAYERS = [
    "upland_hill-slope_regolith_thickness.tif",
    "upland_hill-slope_soil_thickness.tif",
    "hill-slope_valley-bottom.tif",
    "upland_valley-bottom_and_lowland_sedimentary_deposit_thickness.tif",
    "land_cover_mask.tif",
    "average_soil_and_sedimentary-deposit_thickness.tif",
]
# the legacy daac.ornl.gov comp path redirects to a URS OAuth login (401 with
# a bearer token); the same PDF is served from the public cloud path
GUIDE_URL = ("https://data.ornldaac.earthdata.nasa.gov/public/global_soil/"
             "Global_Soil_Regolith_Sediment/comp/Global_Soil_Regolith_Sediment.pdf")

NROW, NCOL = 18_000, 43_200
STEP = 1.0 / 120.0            # 30 arcsec, verified live from ds.res
FILL = -1                     # native NoData of the thickness layers (guide + files)
REGOLITH_BIN = 52             # int8 values -1..50 -> bin = value + 1
SOIL_BIN = 422                # float32 values -1 or 0.00-4.20 on a 0.01 m grid
ROWS_PER_BLOCK = 900


def fetch_regolith() -> list:
    """Download the six GeoTIFFs + public .sha256 sidecars + user guide once."""
    got = []
    for name in LAYERS:
        p = fetch(DATASET, _PROTECTED + name)
        print(f"ok  tif {p.name} {p.stat().st_size} B", flush=True)
        got.append(p)
    for name in LAYERS:
        p = fetch(DATASET, _PUBLIC + name + ".sha256")
        print(f"ok  sidecar {p.name} {p.stat().st_size} B", flush=True)
    p = fetch(DATASET, GUIDE_URL)
    print(f"ok  guide {p.name} {p.stat().st_size} B", flush=True)
    return got


def _layer_path(name: str) -> Path:
    rel = [e["localPath"] for e in load_manifest()["entries"]
           if e.get("datasetId") == DATASET and e["localPath"].endswith(name)]
    if not rel:
        raise RuntimeError(f"{name}: not in MANIFEST for {DATASET}")
    return SNAP.parent.parent / rel[0]


def _manifest_block() -> list:
    return [{"localPath": e["localPath"], "sha256": e["sha256"], "bytes": e["bytes"]}
            for e in load_manifest()["entries"] if e.get("datasetId") == DATASET]


def _verify_georef(ds):
    if ds.shape != (NROW, NCOL) or abs(ds.res[0] - STEP) > 1e-9 or ds.crs.to_epsg() != 4326:
        raise RuntimeError(f"unexpected georeferencing in {ds.name}: shape={ds.shape}, "
                           f"res={ds.res}, crs={ds.crs}")


def _row_cells(args):
    """H3 r4 cell id (int) for every non-ocean pixel of one 30" mask row, 0 = ocean."""
    row, res = args
    import h3
    import rasterio
    with rasterio.open(_layer_path("land_cover_mask.tif")) as ds:
        _verify_georef(ds)
        mask = ds.read(1, window=Window(0, row, NCOL, 1)).ravel()
    cols = np.nonzero(mask)[0]  # 1-D -> column indices
    lat = 90.0 - STEP * (row + 0.5)
    lon = -180.0 + STEP * (cols + 0.5)
    cells = np.zeros(NCOL, dtype=np.uint64)
    cells[cols] = [int(h3.latlng_to_cell(lat, float(lo), res), 16) for lo in lon]
    return row, cells


def cell_map(master_int: np.ndarray, res: int = 4) -> np.ndarray:
    """Build (or reuse) the 30" pixel -> H3 cell map, non-ocean pixels only."""
    from .grid import DERIVED
    cache = DERIVED / f"ornl-p1304-cells-r{res}.npy"
    if cache.exists():
        return np.load(cache, mmap_mode="r")
    cells_arr = np.lib.format.open_memmap(cache, mode="w+", dtype=np.uint64,
                                          shape=(NROW, NCOL))
    # rows to compute: any non-ocean pixel; cheap scan per row block
    rows_with_land = []
    with rasterio.open(_layer_path("land_cover_mask.tif")) as ds:
        for r0 in range(0, NROW, ROWS_PER_BLOCK):
            m = ds.read(1, window=Window(0, r0, NCOL, ROWS_PER_BLOCK))
            hits = np.nonzero((m != 0).sum(axis=1))[0]
            rows_with_land += (hits + r0).tolist()
    jobs = [(int(r), res) for r in rows_with_land]
    with ProcessPoolExecutor() as ex:
        for row, cells in ex.map(_row_cells, jobs, chunksize=24):
            cells_arr[row, :] = cells
    cells_arr.flush()
    return cells_arr


def master_keys(res: int) -> np.ndarray:
    tbl = pq.read_table(SNAP / "_derived" / f"cells-r{res}.parquet", columns=["h3"])
    keys = tbl["h3"].to_pylist()
    if len(set(keys)) != len(keys):
        raise RuntimeError("duplicate h3 in cells-r4.parquet")
    return np.array(keys)


def _hist_median(hist: np.ndarray, values: np.ndarray) -> np.ndarray:
    """Exact median per hex from a per-hex histogram (mean of the two middle
    values for even counts, same convention as the other ingest tables).
    Bin 0 is the native fill/NoData count and NEVER counts as a value: the
    median is over valid pixels only. For row i with k-th 0-based order
    statistic t, the value falls in the first bin j whose cumulative count
    exceeds t."""
    hist = hist[:, 1:]  # drop the fill bin
    values = values[1:]
    hist = hist.astype(np.int64, copy=False)
    tot = hist.sum(axis=1)
    med = np.full(hist.shape[0], np.nan)
    have = tot > 0
    if not have.any():
        return med
    cum = np.cumsum(hist[have], axis=1)
    lo_bin = (cum <= ((tot[have] - 1) // 2)[:, None]).sum(axis=1)
    hi_bin = (cum <= (tot[have] // 2)[:, None]).sum(axis=1)
    np.clip(lo_bin, 0, hist.shape[1] - 1, out=lo_bin)
    np.clip(hi_bin, 0, hist.shape[1] - 1, out=hi_bin)
    med[have] = (values[lo_bin] + values[hi_bin]) / 2
    return med


def build(res: int = 4) -> dict:
    import rasterio
    from .grid import DERIVED, RES
    t0 = time.time()
    for entry in _manifest_block():
        path = SNAP.parent.parent / entry["localPath"]
        if path.stat().st_size != entry["bytes"] or sha256(path) != entry["sha256"]:
            raise RuntimeError(f"source input hash/size mismatch: {entry['localPath']}")
    master = master_keys(res)
    n = len(master)
    master_int = np.array([int(h, 16) for h in master.tolist()], dtype=np.uint64)
    sorted_cells = np.sort(master_int)
    inv = np.argsort(master_int)  # sorted position -> master row index

    cells_map = cell_map(master_int, res)

    hist_r = np.zeros((n, REGOLITH_BIN), dtype=np.uint32)
    hist_s = np.zeros((n, SOIL_BIN), dtype=np.uint32)
    hist_d = np.zeros((n, REGOLITH_BIN), dtype=np.uint32)
    hist_a = np.zeros((n, REGOLITH_BIN), dtype=np.uint32)
    hist_m = np.zeros((n, 5), dtype=np.uint32)       # land_cover_mask classes 0..4
    h_sum = np.zeros(n)                              # hill-slope fraction sums
    h_cnt = np.zeros(n, dtype=np.int64)
    dropped_cells = 0                                 # land pixels whose hex is not master
    quant_err = 0.0
    outside_inputs = 0

    with rasterio.open(_layer_path("land_cover_mask.tif")) as mds, \
         rasterio.open(_layer_path("upland_hill-slope_regolith_thickness.tif")) as rds, \
         rasterio.open(_layer_path("upland_hill-slope_soil_thickness.tif")) as sds, \
         rasterio.open(_layer_path("upland_valley-bottom_and_lowland_sedimentary_deposit_thickness.tif")) as dds, \
         rasterio.open(_layer_path("hill-slope_valley-bottom.tif")) as fds, \
         rasterio.open(_layer_path("average_soil_and_sedimentary-deposit_thickness.tif")) as ads:
        for ds in (mds, rds, sds, dds, fds, ads):
            _verify_georef(ds)
        for r0 in range(0, NROW, ROWS_PER_BLOCK):
            w = Window(0, r0, NCOL, min(ROWS_PER_BLOCK, NROW - r0))
            mask = mds.read(1, window=w)
            cells = np.asarray(cells_map[r0:r0 + w.height])
            land = cells != 0
            px_cells = cells[land]
            pos = np.searchsorted(sorted_cells, px_cells)
            ok = (pos < n) & (sorted_cells[np.minimum(pos, n - 1)] == px_cells)
            dropped_cells += int((~ok).sum())
            cid = inv[pos[ok]]                       # master row index per pixel
            cv = mask[land][ok]                       # mask class per pixel
            if len(cid):
                hist_m += np.bincount(cid * 5 + cv, minlength=n * 5).reshape(n, 5).astype(np.uint32)
            for name, ds, hist, bins in (
                    ("r", rds, hist_r, REGOLITH_BIN),
                    ("d", dds, hist_d, REGOLITH_BIN),
                    ("a", ads, hist_a, REGOLITH_BIN)):
                v = ds.read(1, window=w)[land][ok].astype(np.int64)
                hist += np.bincount(cid * bins + (v + 1), minlength=n * bins).reshape(n, bins).astype(np.uint32)
            sv = sds.read(1, window=w)[land][ok]
            valid = sv != FILL
            svn = sv[valid].astype(np.float64)
            b = np.rint(svn * 100.0).astype(np.int64) + 1  # bin 0 = fill
            quant_err = max(quant_err, float(np.abs(svn * 100.0 - np.rint(svn * 100.0)).max()) if len(svn) else 0.0)
            if quant_err > 1e-3:
                raise RuntimeError("soil layer is not on a 0.01 m grid; the SOIL_BIN "
                                   "histogram would quantize -- inspect the file first")
            hist_s += np.bincount(cid[valid] * SOIL_BIN + b, minlength=n * SOIL_BIN).reshape(n, SOIL_BIN).astype(np.uint32)
            fv = fds.read(1, window=w)[land][ok]
            on_land = (cv == 1) | (cv == 2)
            h_sum += np.bincount(cid[on_land], weights=fv[on_land].astype(np.float64), minlength=n)
            h_cnt += np.bincount(cid[on_land], minlength=n)

    v_b = np.arange(REGOLITH_BIN, dtype=np.float64) - 1      # bin value: -1..50
    v_s = (np.arange(SOIL_BIN, dtype=np.float64) - 1) / 100.0  # -1..4.20
    reg_med = _hist_median(hist_r.astype(np.int64), v_b)
    soil_med = _hist_median(hist_s.astype(np.int64), v_s)
    sed_med = _hist_median(hist_d.astype(np.int64), v_b)
    avg_med = _hist_median(hist_a.astype(np.int64), v_b)

    up = hist_m[:, 1].astype(np.float64)
    low = hist_m[:, 2].astype(np.float64)
    lake = hist_m[:, 3].astype(np.float64)
    ice = hist_m[:, 4].astype(np.float64)
    land_px = up + low
    rval = hist_r[:, 1:].sum(axis=1).astype(np.float64)
    sval = hist_s[:, 1:].sum(axis=1).astype(np.float64)
    dval = hist_d[:, 1:].sum(axis=1).astype(np.float64)
    aval = hist_a[:, 1:].sum(axis=1).astype(np.float64)
    hmean = np.where(h_cnt > 0, h_sum / np.maximum(h_cnt, 1), np.nan)
    rsup = np.where(up > 0, rval / np.maximum(up, 1), np.nan)
    ssup = np.where(up > 0, sval / np.maximum(up, 1), np.nan)

    reasons = []
    for i in range(n):
        r = {}
        if land_px[i] == 0:
            code = "outside-product-coverage"
        else:
            code = None
        if np.isnan(reg_med[i]):
            if code:
                r["regolith_thick_m"] = code
            elif up[i] == 0:
                r["regolith_thick_m"] = "no-upland-pixels"
            else:
                r["regolith_thick_m"] = "regolith-all-fill"
        if np.isnan(soil_med[i]):
            if code:
                r["soil_thick_m"] = code
            elif up[i] == 0:
                r["soil_thick_m"] = "no-upland-pixels"
            else:
                r["soil_thick_m"] = "soil-all-fill"
        if np.isnan(sed_med[i]):
            r["sediment_thick_m"] = code or "sediment-all-fill"
        if np.isnan(avg_med[i]):
            r["avg_soil_sed_thick_m"] = code or "avg-all-fill"
        if np.isnan(hmean[i]):
            r["hillslope_frac_mean"] = code or "no-land-pixels"
        reasons.append(json.dumps(r, sort_keys=True))

    tbl = pa.table({
        "h3": pa.array(master),
        "regolith_thick_m": pa.array(reg_med, from_pandas=True),
        "regolith_support_px": pa.array(rsup, from_pandas=True),
        "soil_thick_m": pa.array(soil_med, from_pandas=True),
        "soil_support_px": pa.array(ssup, from_pandas=True),
        "sediment_thick_m": pa.array(sed_med, from_pandas=True),
        "avg_soil_sed_thick_m": pa.array(avg_med, from_pandas=True),
        "hillslope_frac_mean": pa.array(hmean, from_pandas=True),
        "regolith_valid_px": pa.array(rval.astype(np.int32)),
        "soil_valid_px": pa.array(sval.astype(np.int32)),
        "sediment_valid_px": pa.array(dval.astype(np.int32)),
        "avg_valid_px": pa.array(aval.astype(np.int32)),
        "hillslope_valid_px": pa.array(h_cnt.astype(np.int32)),
        "mask_upland_px": pa.array(up.astype(np.int32)),
        "mask_lowland_px": pa.array(low.astype(np.int32)),
        "mask_lake_px": pa.array(lake.astype(np.int32)),
        "mask_ice_px": pa.array(ice.astype(np.int32)),
        "missing_reason": pa.array(reasons),
    })
    out = SNAP / "_derived" / f"regolith-r{res}.parquet"
    meta = {
        "generatedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "h3Res": res, "cells": int(n), "family": "regolith",
        "source": ("Pelletier et al. 2016, ORNL DAAC 1304 (DOI 10.3334/ORNLDAAC/1304), "
                   "openly shared without restriction per the ORNL DAAC dataset page"),
        "observable": (
            "modeled thickness of the permeable layers above bedrock [m] at the "
            "'geological present', by landform layer: upland regolith (soil + intact "
            "regolith), upland soil, upland valley-bottom + lowland sedimentary "
            "deposit, and the product's own area+TWI-weighted average of soil and "
            "sedimentary deposit"
        ),
        "statistic": (
            "exact per-hexagon median from per-hex value histograms over the "
            f"30-arcsec pixels of each layer's own support (mean of the two middle "
            "values for even pixel counts); support fractions and raw pixel counts "
            "are separate columns"
        ),
        "spatialSupport": (
            "30 arcsec (1/120 deg, verified from ds.res), 43,200x18,000, EPSG:4326, "
            "90 N to 60 S (product clipped, no Antarctica)"
        ),
        "timeSupport": (
            "static one-time estimate for the geological present; the guide's "
            "1900-2015 range is a completeness placeholder (CMR sets 1900-01-01). "
            "No time dimension in these outputs."
        ),
        "qualityRule": (
            f"native fill {FILL} kept as null (never 0); valid ranges verified live "
            "against the files: regolith 0-50 m (int8), soil 0-4.2 m (float32, checked "
            "on a 0.01 m grid during the pass), sedimentary deposit 0-50 m (int8), "
            "weighted average 0-50 m (int8). The guide's value table declares an "
            "upper valid bound of 50 m. Values at that bound are counted over "
            "mapped master-cell pixels; the table does not establish clipping "
            "or censoring, and these are not global native-raster totals."
        ),
        "modelLimits": (
            "Model output, not a measurement: calibrated on US/European soil-thickness "
            "datasets and US groundwater-well depths-to-bedrock (guide §1, §5). The "
            "upland regolith layer is 'an experimental product with a high degree of "
            "uncertainty' (guide §2). NOT a measured ice-table depth and NOT "
            "equivalent to lunar regolith thickness; any Moon/Mars regolith-thickness "
            "comparison needs an explicit proxy mapping (engine work)."
        ),
        "inputs": _manifest_block(),
        "computed": {
            "median": "exact per-hex histogram median (0.01 m bins for soil, 1 m bins int8 for byte layers)",
            "valuesAtPublishedMaximum": {
                "regolith_at_50m_px": int(hist_r[:, 51].sum()),
                "sediment_at_50m_px": int(hist_d[:, 51].sum()),
                "avg_at_50m_px": int(hist_a[:, 51].sum()),
                "soil_at_4.2m_px": int(hist_s[:, 421].sum()),
            },
            "dropped_pixels_outside_master_hexes": int(dropped_cells),
            "soil_quantization_check_max_err_m": float(quant_err / 100.0),
        },
    }
    tbl = tbl.replace_schema_metadata({"cosmic-consultants": json.dumps(meta)})
    pq.write_table(tbl, out, compression="zstd")
    meta.update(path=str(out.relative_to(SNAP.parent.parent)), sha256=sha256(out),
                bytes=out.stat().st_size, seconds=round(time.time() - t0, 1))
    meta["nullRate"] = {c: round(tbl[c].null_count / n, 4) for c in tbl.column_names if c != "missing_reason"}
    (SNAP / "_derived" / f"regolith-r{res}.meta.json").write_text(json.dumps(meta, indent=2) + "\n")
    return meta


def main(argv: list[str] | None = None) -> int:
    argv = argv or sys.argv[1:]
    if "--fetch" in argv:
        fetch_regolith()
        return 0
    meta = build()
    print(json.dumps({k: meta[k] for k in ("path", "sha256", "bytes", "nullRate", "seconds")}, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
