"""W26 (#66) checks: transformation regression tests + real-data checks.

Run (normal Python and optimised):
    uv run python -m p0ingest.w26_check
    uv run python -O -m p0ingest.w26_check

Exit code 0 only if every check passes. Evidence lines are printed for the PR.

Sections:
  1. unit: granule date/window parsing (albedo)
  2. unit: per-cell group statistics (median/mean semantics, NaN handling)
  3. unit: histogram-median reconstruction (odd/even counts, empty)
  4. integration: key domains of the three derived tables
  5. integration: yearly albedo == mean of its monthly values, months_used
  6. integration: missing_reason JSON parses on every row
  7. spot checks at the 5 analog sites, against the RAW sources
"""
from __future__ import annotations

import json
import sys

import numpy as np

SITES = [  # name, lat, lon
    ("death-valley", 36.25, -116.83),
    ("haughton", 75.38, -89.68),
    ("atacama", -24.10, -70.02),
    ("mcmurdo", -77.52, 161.85),
    ("mauna-loa", 19.475, -155.608),
]

FAILS: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    print(f"{'PASS' if ok else 'FAIL'}  {name}{(' | ' + detail) if detail else ''}")
    if not ok:
        FAILS.append(name)


def unit_albedo_dates() -> None:
    from .albedo import month_of, target_doys, window_dates
    check("unit: A2023015 is month 1", month_of("x/MCD43C3.A2023015.061.2023024104905.hdf") == 1)
    check("unit: A2023349 is month 12", month_of("MCD43C3.A2023349.061.if.hdf") == 12)
    for bad in ("MCD43C3.A2023093.061.h.hdf",  # 2022-93? actually 2023-93 = Apr 3
                "MCD43C3.A2023014.061.h.hdf",  # not the 15th
                "MCD43C3.A2022015.061.h.hdf"):  # wrong year
        try:
            month_of(bad)
            check(f"unit: {bad} rejected", False)
        except ValueError:
            check(f"unit: {bad} rejected", True)
    w = window_dates("MCD43C3.A2023015.061.x.hdf")
    check("unit: A2023015 window", (w["nominal"], w["windowStart"], w["windowEnd"])
          == ("2023-01-15", "2023-01-07", "2023-01-22"), str(w))
    check("unit: 12 dated samples", [m for m, _ in target_doys()] == list(range(1, 13)))


def _tiny_cells(order, ncell):
    starts = np.array([0, 3])  # cell 0: pixels A,B,C; cell 1: D,E
    return starts


def unit_group_stat() -> None:
    from .albedo import _group_stat
    # cell 0: 3 pixels (1.0, NaN, 2.0)  cell 1: 2 pixels (NaN, 7.0)
    order = np.array([0, 1, 2, 3, 4])
    starts = np.array([0, 3])
    vals = np.array([[1.0, np.nan, 2.0], [np.nan, 7.0, np.nan]]).ravel()
    med, n = _group_stat(vals, order, starts, "median")
    check("unit: median valid pixels", np.allclose(med, [1.5, 7.0]), f"{med}")
    check("unit: median valid counts", (n == [2, 1]).all(), f"{n}")
    mean, n2 = _group_stat(vals, order, starts, "mean")
    check("unit: means over valid", np.allclose(mean, [1.5, 7.0]), f"{mean}")
    empty = np.full(5, np.nan)
    mede, ne = _group_stat(empty, order, starts, "median")
    check("unit: all-NaN stays NaN", np.isnan(mede).all() and (ne == 0).all())


def unit_hist_median() -> None:
    from .regolith import _hist_median
    v = np.arange(52, dtype=np.float64) - 1
    # cell A: three valid pixels 1,2,4 -> median 2 ; cell B: two pixels 3,9 -> 6.0
    h = np.zeros((2, 52), dtype=np.uint32)
    h[0, 2] = 1; h[0, 3] = 1; h[0, 5] = 1      # values 1, 2, 4
    h[1, 4] = 1; h[1, 10] = 1                   # values 3, 9
    med = _hist_median(h.astype(np.int64), v)
    check("unit: hist median odd", med[0] == 2.0, f"{med}")
    check("unit: hist median even = mean of middles", med[1] == 6.0, f"{med}")
    med2 = _hist_median(np.zeros((2, 52), np.int64), v)
    check("unit: hist median empty is NaN", np.isnan(med2).all())


def integration_keys(res: int = 4) -> None:
    import pyarrow.parquet as pq
    from .snapshots import SNAP
    der = SNAP / "_derived"
    master = pq.read_table(der / f"cells-r{res}.parquet", columns=["h3"])["h3"].to_pylist()
    mset = set(master)
    # albedo yearly
    try:
        ay = pq.read_table(der / f"albedo-r{res}.parquet")
        check("keys: albedo yearly rows == 91,800", ay.num_rows == 91_800, f"{ay.num_rows}")
        check("keys: albedo yearly == master keys", set(ay["h3"].to_pylist()) == mset)
    except FileNotFoundError:
        check("keys: albedo yearly missing (build not run)", False)
    # albedo monthly
    try:
        am = pq.read_table(der / f"albedo-r{res}-monthly.parquet", columns=["h3", "month"])
        check("keys: albedo monthly rows == 1,101,600", am.num_rows == 1_101_600, f"{am.num_rows}")
        keys = list(zip(am["h3"].to_pylist(), am["month"].to_pylist()))
        check("keys: albedo monthly no duplicates", len(set(keys)) == len(keys))
        want = {(h, m) for h in master for m in range(1, 13)}
        check("keys: albedo monthly == master x months 1..12", set(keys) == want)
        check("keys: months valid", set(am["month"].to_pylist()) == set(range(1, 13)))
    except FileNotFoundError:
        check("keys: albedo monthly missing (build not run)", False)
    # regolith
    try:
        rg = pq.read_table(der / f"regolith-r{res}.parquet")
        check("keys: regolith rows == 91,800", rg.num_rows == 91_800, f"{rg.num_rows}")
        check("keys: regolith == master keys", set(rg["h3"].to_pylist()) == mset)
    except FileNotFoundError:
        check("keys: regolith missing (build not run)", False)


def integration_consistency(res: int = 4) -> None:
    import pyarrow.parquet as pq
    from .snapshots import SNAP
    der = SNAP / "_derived"
    try:
        am = pq.read_table(der / f"albedo-r{res}-monthly.parquet")
        ay = pq.read_table(der / f"albedo-r{res}.parquet")
    except FileNotFoundError:
        check("consistency: tables missing (build not run)", False)
        return
    from collections import defaultdict
    ws = defaultdict(dict)
    h3s, mos = am["h3"].to_pylist(), am["month"].to_pylist()
    vals = am["albedo_ws_sw"].to_pylist()
    for h, m, v in zip(h3s, mos, vals):
        if v is not None:
            ws[h][m] = v
    yh = ay["h3"].to_pylist()
    ymean = ay["albedo_ws_sw_mean"].to_pylist()
    ymonths = ay["albedo_months_used"].to_pylist()
    ymap = {h: (v, c) for h, v, c in zip(yh, ymean, ymonths)}
    ok_all = True
    bad = 0
    for h, v, c in zip(yh, ymean, ymonths):
        per = ws.get(h, {})
        if c != len(per):
            ok_all = False; bad += 1; continue
        if per:
            want = sum(per.values()) / len(per)
            if v is None or abs(v - want) > 1e-12:
                ok_all = False; bad += 1
        elif v is not None:
            ok_all = False; bad += 1
    check("consistency: yearly mean == mean of its monthly values, months_used == count", ok_all,
          f"{bad} mismatches")
    # ranges
    ws_all = [x for x in vals if x is not None]
    check("consistency: albedo_ws_sw in [0, 1]", ws_all == [] or (min(ws_all) >= 0 and max(ws_all) <= 1),
          f"min={min(ws_all) if ws_all else None}, max={max(ws_all) if ws_all else None}")
    for tbl, name in ((am, "albedo monthly"), (ay, "albedo yearly")):
        bad = 0
        for r in tbl["missing_reason"].to_pylist():
            if r:
                json.loads(r)
                bad += 0
        check(f"consistency: {name} missing_reason JSON parses", True)
    try:
        rg = pq.read_table(der / f"regolith-r{res}.parquet")
        rt = [x for x in rg["regolith_thick_m"].to_pylist() if x is not None]
        check("consistency: regolith_thick_m in [0, 50] (native cap)", rt == [] or (min(rt) >= 0 and max(rt) <= 50),
              f"min={min(rt) if rt else None}, max={max(rt) if rt else None}")
        st = [x for x in rg["soil_thick_m"].to_pylist() if x is not None]
        check("consistency: soil_thick_m in [0, 4.2]", st == [] or (min(st) >= 0 and max(st) <= 4.2))
        for r in rg["missing_reason"].to_pylist():
            if r:
                json.loads(r)
        check("consistency: regolith missing_reason JSON parses", True)
    except FileNotFoundError:
        check("consistency: regolith table missing (build not run)", False)


def spot_checks(res: int = 4) -> None:
    import h3
    import pyarrow.parquet as pq
    import rasterio
    from .snapshots import SNAP
    der = SNAP / "_derived"
    try:
        am = pq.read_table(der / f"albedo-r{res}-monthly.parquet")
        ay = pq.read_table(der / f"albedo-r{res}.parquet")
        rg = pq.read_table(der / f"regolith-r{res}.parquet")
    except FileNotFoundError:
        check("spots: derived tables missing (build not run)", False)
        return

    def row_by_h3(tbl, h):
        idx = {v: i for i, v in enumerate(tbl["h3"].to_pylist())}
        i = idx[h]
        return {c: tbl[c][i].as_py() for c in tbl.column_names}

    # raw-source lookups
    from .albedo import _read_granule, month_of
    from .snapshots import load_manifest
    jan = [e for e in load_manifest()["entries"]
           if e.get("datasetId") == "modis-mcd43c3-albedo" and ".A2023015." in e["localPath"]]
    src_ws = src_qa = None
    if jan:
        g = _read_granule(jan[0]["localPath"])
        src_ws, src_bs = g["wsa"], g["bsa"]
    from .grid import cmg_lat, cmg_lon
    tif_paths = {}
    from .regolith import _layer_path
    for nm in ("upland_hill-slope_regolith_thickness.tif",
               "upland_hill-slope_soil_thickness.tif",
               "upland_valley-bottom_and_lowland_sedimentary_deposit_thickness.tif",
               "average_soil_and_sedimentary-deposit_thickness.tif"):
        try:
            tif_paths[nm] = _layer_path(nm)
        except RuntimeError:
            pass

    print("spot checks (h3, derived values, raw-source pixel values at the site):")
    ok_vals = True
    for name, lat, lon in SITES:
        h = h3.latlng_to_cell(lat, lon, res)
        a12 = {}
        idxs = [i for i, v in enumerate(am["h3"].to_pylist()) if v == h]
        for i in idxs:
            a12[am["month"][i].as_py()] = am["albedo_ws_sw"][i].as_py()
        y = row_by_h3(ay, h)
        r = row_by_h3(rg, h)
        # raw cmg pixel at the site for January
        raw_ws = raw_bs = None
        if src_ws is not None:
            i = int(round((90.0 - lat) / 0.05 - 0.5))
            j = int(round((lon + 180.0) / 0.05 - 0.5))
            raw_ws = float(src_ws[i, j]); raw_bs = float(src_bs[i, j])
        # raw regolith pixel at the site
        raw_reg = None
        if tif_paths:
            from rasterio.windows import Window
            with rasterio.open(tif_paths["upland_hill-slope_regolith_thickness.tif"]) as ds:
                # 30" pixel whose cell contains the site (floor of row/col).
                # Product coverage ends at 60 S, so sites south of it have no pixel.
                ri = int((90.0 - lat) * 120.0)
                rj = int((lon + 180.0) * 120.0)
                if 0 <= ri < ds.height and 0 <= rj < ds.width:
                    v = ds.read(1, window=Window(rj, ri, 1, 1))[0, 0]
                    raw_reg = None if v == -1 else int(v)
                else:
                    raw_reg = None  # outside the product grid (no coverage)
        print(f"  {name:13s} lat={lat:8.3f} lon={lon:9.3f} h3={h}")
        print(f"    albedo yearly      : ws_mean={y['albedo_ws_sw_mean']} months={y['albedo_months_used']} "
              f"bs_mean={y['albedo_bs_sw_mean']} reason={y['missing_reason']}")
        jan_ws = a12.get(1)
        print(f"    albedo Jan (dated): ws={jan_ws} | raw A2023015 pixel at site: ws={raw_ws} bs={raw_bs}")
        print(f"    regolith          : thick_m={r['regolith_thick_m']} soil={r['soil_thick_m']} "
              f"sed={r['sediment_thick_m']} avg={r['avg_soil_sed_thick_m']} support={r['regolith_support_px']} "
              f"| raw pixel: {raw_reg} | reason={r['missing_reason']}")
        if name == "mcmurdo":
            ok = (r["regolith_thick_m"] is None
                  and "outside-product-coverage" in (r["missing_reason"] or "{}"))
            check("spots: mcmurdo outside regolith coverage is null with reason", ok)
        else:
            if r["regolith_thick_m"] is None:
                ok_vals = False
    check("spots: 4 non-polar sites have regolith values", ok_vals)


def main() -> int:
    print("== W26 unit tests ==")
    unit_albedo_dates()
    unit_group_stat()
    unit_hist_median()
    print("== W26 integration checks ==")
    integration_keys()
    integration_consistency()
    print("== W26 spot checks ==")
    spot_checks()
    print(f"{'ALL PASS' if not FAILS else 'FAILURES: ' + ', '.join(FAILS)}")
    return 0 if not FAILS else 1


if __name__ == "__main__":
    sys.exit(main())
