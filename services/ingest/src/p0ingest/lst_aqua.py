"""W34 (#93): Aqua MYD11C3 V061 monthly LST per hexagon, 2023.

Output: data/snapshots/_derived/aqua-lst-r4-monthly.parquet — one row per land
cell (91,800 H3 res-4 hexagons, exactly the keys of cells-r4.parquet) x 12
months of 2023 = 1,101,600 rows.

Same rules as the Terra L1m table (monthly.py, imported read-only — monthly.py
is NOT edited): 0.05 deg CMG pixel map from grid.py (pixel centre inside the H3
res-4 cell via h3.latlng_to_cell, land share > 0), raw counts < 7500 = fill,
x0.02 K, a monthly median is kept only if >= 25% of the cell's mapped CMG
pixels have a value that month (monthly.py MIN_PIXEL_SHARE), medians.

Overpass times (recorded because they pair with the Terra table): Aqua
(MYD11C3) day/night composites come from overpasses at ~13:30/~01:30 local
solar time; Terra (MOD11C3, cells-r4-monthly.parquet) from ~10:30/~22:30.
Together the two tables give four times of day per month for tsurf_max /
tsurf_min / tsurf_range proxies (monthly composites, NOT daily extremes) and
for thermal-inertia ingredients.

Commands (from services/ingest):
  uv run python -m p0ingest.lst_aqua fetch   # the 12 monthly CMG granules of 2023
  uv run python -m p0ingest.lst_aqua build
  uv run python -m p0ingest.lst_aqua check   # keys, ranges, null reasons, raw spot checks
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone

import h3
import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq

from .grid import DERIVED, RES, cmg_cell_map, group_index, land_percent
from .monthly import MIN_PIXEL_SHARE, YEAR, lst_monthly, month_of, sun_monthly
from .process import _group_stat as group_stat
from .snapshots import SNAP, cmr_granule_urls, fetch, load_manifest, sha256

DATASET = "modis-myd11c3"
COLLECTION = "C2565794044-LPCLOUD"  # MYD11C3 V061 (data/catalog/modis-myd11c3.yaml)
OUT = "aqua-lst-r4-monthly"
# Nullable value columns (missing_reason keys must be exactly the null ones).
NULL_COLS = ("lst_day_k", "lst_night_k", "lst_diurnal_k")
PHYS_RANGE = (150.0, 360.0)  # K; product valid range 7500-65535 counts = 150-1310.7 K
SPOT_WINDOW = 60  # +/- CMG rows/cols scanned around a cell centre for spot checks
SPOT_N = 8  # raw spot checks per check() run (requirement: >= 5)
# Aqua overpass times vs Terra (collection documentation), local solar time.
OVERPASS = {"aqua_day": "~13:30 local solar", "aqua_night": "~01:30 local solar",
            "terra_day": "~10:30 local solar", "terra_night": "~22:30 local solar",
            "note": "Aqua day/night composites from ~13:30/~01:30 local-solar overpasses, Terra "
                    "(cells-r4-monthly.parquet) from ~10:30/~22:30: four times of day per month for "
                    "tsurf_max/min/range proxies (monthly composites, NOT daily extremes) and "
                    "thermal-inertia ingredients"}
DIURNAL_RANGE = (-80.0, 80.0)  # K; day - night medians stay near zero, clouds can invert


def dataset_files() -> list[dict]:
    """The 12 manifest MYD11C3 granules of 2023 (one per month, else error)."""
    files = [e for e in load_manifest()["entries"]
             if e.get("datasetId") == DATASET and f".A{YEAR}" in e["localPath"]]
    months = {month_of(e["localPath"]) for e in files}
    if months != set(range(1, 13)):
        raise ValueError(f"{DATASET}: missing months {sorted(set(range(1, 13)) - months)}; run fetch")
    return sorted(files, key=lambda e: month_of(e["localPath"]))


def cells_r4() -> pq.Table:
    path = DERIVED / "cells-r4.parquet"
    if not path.exists():
        raise FileNotFoundError(
            f"{path}: copy it from the Drive mirror (ccdrive:snapshots/_derived/) first")
    return pq.read_table(path, columns=["h3", "lat"])


def perm_to_r4_order(cells: np.ndarray, hexes_u64: np.ndarray) -> np.ndarray:
    """Permutation from ascending-cell order (grid.group_index) to cells-r4
    row order. Raises if the two cell sets differ."""
    if not np.array_equal(np.sort(hexes_u64), cells):
        raise ValueError(f"cmg pixel-map cells ({len(cells)}) differ from cells-r4.parquet cells "
                         f"({len(hexes_u64)})")
    pos = {int(c): k for k, c in enumerate(cells)}
    return np.array([pos[int(c)] for c in hexes_u64], dtype=np.int64)


def cell_order() -> tuple[list[str], np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """(hexes, lat, order, starts, perm): pixel groups aligned to cells-r4 order.

    grid.group_index groups in ascending uint64 cell order; cells-r4.parquet has
    its own row order, so per-cell columns must be permuted by `perm`. The cell
    sets must be identical (keys are exactly the 91,800)."""
    meta = cells_r4()
    hexes = meta.column("h3").to_pylist()
    lat = np.asarray(meta.column("lat").to_pylist(), dtype=np.float64)
    cellmap, _ = cmg_cell_map()
    order, cells, starts = group_index(cellmap)
    hexes_u64 = np.array([int(h, 16) for h in hexes], dtype=np.uint64)
    perm = perm_to_r4_order(cells, hexes_u64)
    return hexes, lat, order, starts, perm


def median_or_none(vals: np.ndarray | None, n_mapped: int) -> float | None:
    """The 25% coverage rule applied to one cell: median(raw counts) * 0.02 K
    when at least MIN_PIXEL_SHARE of the cell's mapped pixels are valid, else None."""
    n = 0 if vals is None else len(vals)
    if n == 0 or n < MIN_PIXEL_SHARE * n_mapped:
        return None
    return float(np.median(vals)) * 0.02


def fetch_aqua(max_workers: int = 4) -> int:
    """Fetch the 12 monthly 2023 granules (at most 4 parallel downloads)."""
    from concurrent.futures import ThreadPoolExecutor, as_completed

    urls = cmr_granule_urls(COLLECTION, f"{YEAR}-01-01T00:00:00Z,{YEAR}-12-31T23:59:59Z", ".hdf")
    print(f"{DATASET}: {len(urls)} granules for {YEAR}", flush=True)
    errs = 0
    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        futs = {ex.submit(fetch, DATASET, u): u for u in urls}
        for f in as_completed(futs):
            u = futs[f]
            try:
                p = f.result()
                print(f"ok   {p.name} {p.stat().st_size} B", flush=True)
            except Exception as exc:  # noqa: BLE001
                errs += 1
                print(f"FAIL {u}: {exc}", flush=True)
    print(f"done, {errs} error(s)", flush=True)
    return 1 if errs else 0


def monthly_reasons(day_null, night_null, day_thin, night_thin) -> list[str]:
    """Per-row missing_reason: JSON whose keys are EXACTLY that row's null value
    columns (lst_day_k / lst_night_k / lst_diurnal_k). Codes: no-lst-pixels
    (0 valid pixels), too-few-lst-pixels (0 < n < 25% of the cell's pixels);
    lst_diurnal_k is null exactly when day or night is null."""
    out = []
    for dn, nn, td, tn in zip(day_null, night_null, day_thin, night_thin):
        r = {}
        if dn or nn:
            if dn:
                r["lst_day_k"] = "too-few-lst-pixels" if td else "no-lst-pixels"
            if nn:
                r["lst_night_k"] = "too-few-lst-pixels" if tn else "no-lst-pixels"
            r["lst_diurnal_k"] = "day-or-night-missing"
        out.append(json.dumps(r, sort_keys=True))
    return out


def validate_keys(h3col: list, mcol: list, expected_cells: list[str],
                  months_per_cell: int = 12) -> list[str]:
    """[] when keys are exactly expected_cells x 12 months, one row each."""
    errs = []
    if len(h3col) != len(expected_cells) * months_per_cell:
        errs.append(f"rows={len(h3col)}, expected {len(expected_cells) * months_per_cell}")
    if any(h is None or m is None or m < 1 or m > 12 for h, m in zip(h3col, mcol)):
        errs.append("null key or month outside 1..12 present")
    keys = [(h, m) for h, m in zip(h3col, mcol) if h is not None]
    dups = len(keys) - len(set(keys))
    if dups:
        errs.append(f"{dups} duplicate (h3, month) keys")
    got = {h for h in h3col if h is not None}
    exp = set(expected_cells)
    if got != exp:
        errs.append(f"cells differ: extra={sorted(got - exp)[:3]} missing={sorted(exp - got)[:3]}")
    return errs


def reason_mismatches(table: pa.Table) -> list[str]:
    """Every row's missing_reason keys must be exactly its null value columns."""
    bad = []
    cols = {c: table.column(c).to_pylist() for c in NULL_COLS}
    for i, reason in enumerate(table.column("missing_reason").to_pylist()):
        r = json.loads(reason) if reason else {}
        null_cols = {name for name, v in cols.items() if v[i] is None}
        if set(r) != null_cols:
            bad.append(f"row {i}: reason keys {sorted(r)} != null columns {sorted(null_cols)}")
            if len(bad) >= 5:
                break
    return bad


def build() -> dict:
    """One pass over the 12 granules: monthly medians per cell -> parquet + meta."""
    hexes, lat, order, starts, perm = cell_order()
    files = dataset_files()
    day_m, night_m, nboth, _rsum, _rn, thin_day, thin_night = \
        lst_monthly(files, order, starts, group_stat)

    # permute per-cell outputs from ascending-cell order to the cells-r4 row order
    day_m, night_m = day_m[perm], night_m[perm]
    nboth, thin_day, thin_night = nboth[perm], thin_day[perm], thin_night[perm]

    ncell = len(hexes)
    months = np.tile(np.arange(1, 13, dtype=np.int8), ncell)
    flat = np.reshape
    day_f, night_f = flat(day_m, -1), flat(night_m, -1)
    diurnal = np.where(np.isnan(day_f) | np.isnan(night_f), np.nan, day_f - night_f)
    reasons = monthly_reasons(np.isnan(day_f), np.isnan(night_f),
                              flat(thin_day, -1), flat(thin_night, -1))
    sun = sun_monthly(lat)

    tbl = pa.table({
        "h3": pa.array(np.repeat(hexes, 12)),
        "month": pa.array(months),
        "lst_day_k": pa.array(day_f, from_pandas=True),
        "lst_night_k": pa.array(night_f, from_pandas=True),
        "lst_diurnal_k": pa.array(diurnal, from_pandas=True),
        "lst_valid_pixels": pa.array(flat(nboth, -1).astype(np.int32)),
        "sun_noon_elev_deg": pa.array(flat(sun["sun_noon_elev_deg"], -1)),
        "daylight_h": pa.array(flat(sun["daylight_h"], -1)),
        "polar_day": pa.array(flat(sun["polar_day"], -1)),
        "polar_night": pa.array(flat(sun["polar_night"], -1)),
        "missing_reason": pa.array(reasons),
    })
    meta = {
        "datasetId": DATASET,
        "title": "Aqua MYD11C3 V061 monthly LST per H3 res-4 hexagon (2023)",
        "generatedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "h3Res": RES, "cells": ncell, "rows": ncell * 12, "year": YEAR,
        "keys": "exactly the 91,800 land hexagons of data/snapshots/_derived/cells-r4.parquet, "
                "months 1-12 of 2023",
        "pixelToHexagonRule": "each 0.05 deg CMG pixel with land share > 0 is assigned to the H3 "
                              "res-4 cell containing its pixel centre (h3.latlng_to_cell, grid.py "
                              "cmg_cell_map); medians over those pixels; support counts kept in "
                              "lst_valid_pixels",
        "overpass": OVERPASS,
        "inputs": {DATASET: [{"localPath": e["localPath"], "sha256": e["sha256"],
                              "month": month_of(e["localPath"])} for e in files]},
        "computed": {
            "lst": "per month: median over the hexagon's 0.05 deg CMG pixels of MYD11C3 V061 "
                   "LST_Day_CMG / LST_Night_CMG (x0.02 K, counts < 7500 = fill)",
            "coverageRule": f"a monthly median is kept only if >= {MIN_PIXEL_SHARE:.0%} of the hexagon's "
                            "mapped CMG pixels have a value that month; otherwise null, reason "
                            "too-few-lst-pixels",
            "lstValidPixels": "pixels of the hexagon with BOTH a day and a night value that month",
            "sun": "15th of each month; declination -23.44*cos(2*pi*(doy+10)/365); geometric centre, "
                   "no refraction, no terrain shadows; sensor-independent (same columns as "
                   "cells-r4-monthly.parquet)",
        },
    }
    out = DERIVED / f"{OUT}.parquet"
    tbl = tbl.replace_schema_metadata({"cosmic-consultants": json.dumps(meta)})
    pq.write_table(tbl, str(out), compression="zstd")
    meta.update(path=str(out.relative_to(SNAP.parent.parent)), sha256=sha256(out),
                bytes=out.stat().st_size,
                nulls={c: int(tbl.column(c).null_count) for c in NULL_COLS})
    (DERIVED / f"{OUT}.meta.json").write_text(json.dumps(meta, indent=2) + "\n")
    return meta


# ---------------------------------------------------------------- raw spot check

def cell_pixel_values(cell: str, fields: dict[str, np.ndarray]) -> tuple[dict[str, np.ndarray], int]:
    """Independent pixel lookup for one hexagon: all CMG pixels whose centre maps
    to `cell`, recomputed here via h3.latlng_to_cell (NOT the cached cmg map),
    inside a +/- SPOT_WINDOW rows/cols box around the cell centre. Returns
    (valid raw values per field, n_mapped land pixels)."""
    lat0, lon0 = h3.cell_to_latlng(cell)
    i0 = int(round((90.0 - lat0 - 0.025) / 0.05))
    j0 = int(round((lon0 + 180.0 - 0.025) / 0.05))
    landp = land_percent()
    vals: dict[str, list[float]] = {}
    n_mapped = 0
    for i in range(max(0, i0 - SPOT_WINDOW), min(3600, i0 + SPOT_WINDOW + 1)):
        lat = 90.0 - 0.025 - i * 0.05
        for j in range(max(0, j0 - SPOT_WINDOW), min(7200, j0 + SPOT_WINDOW + 1)):
            if landp[i, j] <= 0:
                continue
            if h3.latlng_to_cell(lat, -180.0 + 0.025 + j * 0.05, RES) == cell:
                n_mapped += 1
                for name, arr in fields.items():
                    v = float(arr[i, j])
                    if 7500 <= v <= 65535:
                        vals.setdefault(name, []).append(v)
    return {k: np.asarray(v) for k, v in vals.items()}, n_mapped


def spot_check_one(cols: dict, i: int, files: list[dict]) -> str:
    """One raw spot check for table row i (cell, month from cols): recompute both
    monthly medians straight from the granule and compare with the table.
    Returns 'PASS ...' or 'FAIL ...'."""
    from pyhdf.SD import SD, SDC

    cell, mo = cols["h3"][i], int(cols["month"][i])
    f = next(e for e in files if month_of(e["localPath"]) == mo)
    sd = SD(str(SNAP.parent.parent / f["localPath"]), SDC.READ)
    raw = {"day": sd.select("LST_Day_CMG")[:].astype(np.float64),
           "night": sd.select("LST_Night_CMG")[:].astype(np.float64)}
    sd.end()
    raw_vals, n_mapped = cell_pixel_values(cell, raw)
    need = MIN_PIXEL_SHARE * n_mapped
    parts = []
    for side, col in (("day", "lst_day_k"), ("night", "lst_night_k")):
        want = cols[col][i]
        got = median_or_none(raw_vals.get(side), n_mapped)
        n_valid = len(raw_vals[side]) if side in raw_vals else 0
        if (got is None) != (want is None):
            return (f"FAIL {side} {cell} m{mo}: table={want} raw={got} "
                    f"(n_valid={n_valid}, n_mapped={n_mapped}, need={need:.1f})")
        if got is not None and abs(got - want) > 1e-9:
            return f"FAIL {side} {cell} m{mo}: table={want} != raw {got}"
        if got is not None:
            parts.append(f"{side}={got:.2f}K")
    return f"{cell} m{mo}: raw match ({', '.join(parts)}, n_mapped={n_mapped})"


# ---------------------------------------------------------------- check

def physical_range_errors(tbl: pa.Table, ncell: int) -> list[str]:
    errs = []
    for c in ("lst_day_k", "lst_night_k"):
        a = np.asarray(tbl.column(c).to_pylist(), dtype=np.float64)
        ok = np.isnan(a) | ((a >= PHYS_RANGE[0]) & (a <= PHYS_RANGE[1]))
        if (~ok).any():
            errs.append(f"{c}: {int((~ok).sum())} values outside {PHYS_RANGE} K, e.g. {a[~ok][:3]}")
    a = np.asarray(tbl.column("lst_diurnal_k").to_pylist(), dtype=np.float64)
    ok = np.isnan(a) | ((a >= DIURNAL_RANGE[0]) & (a <= DIURNAL_RANGE[1]))
    if (~ok).any():
        errs.append(f"lst_diurnal_k: {int((~ok).sum())} values outside {DIURNAL_RANGE} K, "
                    f"e.g. {a[~ok][:3]}")
    vp = np.asarray(tbl.column("lst_valid_pixels").to_pylist())
    if (vp < 0).any() or (vp > 50_000).any():
        errs.append(f"lst_valid_pixels out of range: min={vp.min()} max={vp.max()}")
    mu, mc = np.unique(np.asarray(tbl.column("month").to_pylist()), return_counts=True)
    if not (np.array_equal(mu, np.arange(1, 13)) and (mc == ncell).all()):
        errs.append(f"month counts wrong: {dict(zip(mu.tolist(), mc.tolist()))}")
    return errs


def check() -> int:
    """Exact keys / physical ranges / null reasons / >=5 raw spot checks. 0 = pass."""
    errs: list[str] = []
    out = DERIVED / f"{OUT}.parquet"
    if not out.exists():
        print(f"FAIL {out}: not built (run build first)")
        return 1
    tbl = pq.read_table(out)
    expected_cells = cells_r4().column("h3").to_pylist()
    ncell = len(expected_cells)

    key_errs = validate_keys(tbl.column("h3").to_pylist(), tbl.column("month").to_pylist(),
                             expected_cells)
    for e in key_errs:
        print("FAIL", e)
    if not key_errs:
        print(f"PASS keys: rows={tbl.num_rows} = {ncell} cells x 12 months, exactly the "
              f"cells-r4 cells, no duplicate keys")
    errs += key_errs

    rng_errs = physical_range_errors(tbl, ncell)
    for e in rng_errs:
        print("FAIL", e)
    if not rng_errs:
        print(f"PASS ranges: all lst in {PHYS_RANGE} K; lst_valid_pixels sane; each month exactly "
              f"{ncell} rows")
    errs += rng_errs

    mism = reason_mismatches(tbl)
    for m in mism:
        print("FAIL", m)
    if not mism:
        n_null = sum(tbl.column(c).null_count for c in NULL_COLS)
        print(f"PASS nulls: {n_null} null value cells; missing_reason keys match null columns exactly")
    errs += mism

    files = dataset_files()
    cols = {c: tbl.column(c).to_pylist() for c in ("h3", "month", "lst_day_k", "lst_night_k")}
    idx = [i for i in range(0, ncell * 12)
           if (cols["lst_day_k"][i] is not None or cols["lst_night_k"][i] is not None)]
    step = max(1, len(idx) // SPOT_N)
    picks = sorted(set(idx[::step][:SPOT_N]) | {idx[-1]})[:SPOT_N]
    for i in picks:
        res = spot_check_one(cols, i, files)
        print(res)
        if res.startswith("FAIL"):
            errs.append(res)
    print(f"{'PASS' if not errs else 'FAIL'} overall: {len(errs)} error(s); "
          f"{len(picks)} raw spot checks (need >= 5)")
    return 0 if not errs else 1


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv == ["fetch"]:
        return fetch_aqua()
    if argv == ["build"]:
        meta = build()
        print(json.dumps({k: meta[k] for k in ("datasetId", "rows", "cells", "sha256", "bytes",
                                               "path", "nulls")}, indent=1))
        return 0
    if argv == ["check"]:
        return check()
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main())
