"""L1m-years: cells-r<res>-monthly-years.parquet, one row per H3 land cell,
year (2014-2023) and month. Work order W24 (#64).

Same per-month rule as L1m (monthly.py): median over the hexagon's 0.05 deg
MOD11C3 V061 CMG pixels, kept only if >= monthly.MIN_PIXEL_SHARE of those
pixels have a value that month; otherwise null with a reason code. The 2023
rows are therefore identical to L1m (checked by `check`).

Used by step 5 (risks: how much a month swings between years) and the site
optimizer (scenarios over years). Spec: docs/plan/DATA-PIPELINE.md §4-§5.

Run (from services/ingest):
  uv run python -m p0ingest.years fetch   # 108 granules 2014-2022 into data/snapshots/modis-mod11c3/
  uv run python -m p0ingest.years build   # writes _derived/cells-r4-monthly-years.parquet + .meta.json
  uv run python -m p0ingest.years check   # exit 0 only if every check passes
"""
from __future__ import annotations

import json
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, timedelta, timezone

import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq

from .grid import DERIVED, RES, cmg_cell_map, group_index
from .monthly import MIN_PIXEL_SHARE, read_lst
from .process import _group_stat
from .snapshots import SNAP, cmr_granule_urls, fetch, load_manifest, sha256

COLLECTION = "C2565788897-LPCLOUD"  # MOD11C3 V061 (same as fetch_p0.py)
YEARS = list(range(2014, 2024))
_DOY = re.compile(r"\.A(\d{4})(\d{3})\.")
OUT = f"cells-r{RES}-monthly-years"


def year_month(local_path: str) -> tuple[int, int]:
    m = _DOY.search(local_path)
    if not m:
        raise ValueError(f"no A<year><doy> in {local_path}")
    y, doy = int(m.group(1)), int(m.group(2))
    return y, (date(y, 1, 1) + timedelta(days=doy - 1)).month


def granules() -> dict[tuple[int, int], dict]:
    """Manifest entries for MOD11C3, keyed by (year, month). Fails on duplicates."""
    out: dict[tuple[int, int], dict] = {}
    for e in load_manifest()["entries"]:
        if e.get("datasetId") != "modis-mod11c3":
            continue
        ym = year_month(e["localPath"])
        if ym in out:
            raise ValueError(f"two MOD11C3 granules for {ym}: {out[ym]['localPath']} and {e['localPath']}")
        out[ym] = e
    return out


def cmd_fetch() -> int:
    urls = cmr_granule_urls(COLLECTION, "2014-01-01T00:00:00Z,2022-12-31T23:59:59Z", ".hdf")
    print(f"MOD11C3 2014-2022: {len(urls)} granules", flush=True)
    errors = 0
    with ThreadPoolExecutor(max_workers=8) as ex:
        futs = {ex.submit(fetch, "modis-mod11c3", u): u for u in urls}
        for f in as_completed(futs):
            try:
                p = f.result()
                print(f"ok   {p.name} {p.stat().st_size} B", flush=True)
            except Exception as exc:  # noqa: BLE001
                errors += 1
                print(f"FAIL {futs[f]}: {exc}", flush=True)
    print(f"done, {errors} error(s)", flush=True)
    return 1 if errors else 0


def cmd_build() -> int:
    t0 = time.time()
    gran = granules()
    want = [(y, m) for y in YEARS for m in range(1, 13)]
    missing = [ym for ym in want if ym not in gran]
    if missing:
        print(f"missing granules for {missing}; run `fetch` first")
        return 1
    cellmap, _ = cmg_cell_map(RES)
    order, cells, starts = group_index(cellmap)
    ncell, nym = len(cells), len(want)
    size = np.diff(np.append(starts, len(order))).astype(np.float64)
    need = MIN_PIXEL_SHARE * size
    day = np.full((ncell, nym), np.nan)
    night = np.full((ncell, nym), np.nan)
    thin_d = np.zeros((ncell, nym), dtype=bool)
    thin_n = np.zeros((ncell, nym), dtype=bool)
    for k, ym in enumerate(want):
        d, n = read_lst(gran[ym]["localPath"])
        dmed, dn = _group_stat(d, order, starts, "median")
        nmed, nn = _group_stat(n, order, starts, "median")
        day[:, k] = np.where(dn >= need, dmed, np.nan)
        night[:, k] = np.where(nn >= need, nmed, np.nan)
        thin_d[:, k] = (dn > 0) & (dn < need)
        thin_n[:, k] = (nn > 0) & (nn < need)
        if ym[1] == 12:
            print(f"  {ym[0]} done ({time.time() - t0:.0f}s)", flush=True)

    hexes = np.array([format(int(c), "x") for c in cells])
    flat = lambda a: a.reshape(-1)  # row-major: cell, then (year, month)
    d_f, n_f = flat(day), flat(night)
    reasons = []
    for dnan, nnan, td, tn in zip(np.isnan(d_f), np.isnan(n_f), flat(thin_d), flat(thin_n)):
        parts = []
        if dnan:
            parts.append("day:" + ("too-few-lst-pixels" if td else "no-lst-pixels"))
        if nnan:
            parts.append("night:" + ("too-few-lst-pixels" if tn else "no-lst-pixels"))
        reasons.append(json.dumps({"thermal": ",".join(parts)}, sort_keys=True) if parts else "{}")
    years = np.tile(np.array([y for y, _ in want], dtype=np.int16), ncell)
    months = np.tile(np.array([m for _, m in want], dtype=np.int8), ncell)
    tbl = pa.table({
        "h3": pa.array(np.repeat(hexes, nym)),
        "year": pa.array(years),
        "month": pa.array(months),
        "lst_day_k": pa.array(d_f, from_pandas=True),
        "lst_night_k": pa.array(n_f, from_pandas=True),
        "missing_reason": pa.array(reasons),
    })
    meta = {
        "generatedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "h3Res": RES, "cells": int(ncell), "rows": int(ncell * nym), "years": [YEARS[0], YEARS[-1]],
        "inputs": {"modis-mod11c3": [{"localPath": gran[ym]["localPath"], "sha256": gran[ym]["sha256"],
                                      "year": ym[0], "month": ym[1]} for ym in want]},
        "computed": {
            "lst": "per year and month: median over the hexagon's 0.05 deg CMG pixels of MOD11C3 V061 LST_Day_CMG / LST_Night_CMG (x0.02 K, counts < 7500 = fill); 2023 rows equal L1m exactly",
            "coverageRule": f"kept only if >= {MIN_PIXEL_SHARE:.0%} of the hexagon's CMG pixels have a value that month; otherwise null, reason too-few-lst-pixels (same as L1m)",
        },
    }
    out = DERIVED / f"{OUT}.parquet"
    tbl = tbl.replace_schema_metadata({"cosmic-consultants": json.dumps(meta)})
    pq.write_table(tbl, out, compression="zstd")
    meta.update(path=str(out.relative_to(SNAP.parent.parent)), sha256=sha256(out), bytes=out.stat().st_size,
                runtime_s=round(time.time() - t0, 1))
    meta["nullRate"] = {c: round(tbl[c].null_count / tbl.num_rows, 4) for c in tbl.column_names}
    (DERIVED / f"{OUT}.meta.json").write_text(json.dumps(meta, indent=2) + "\n")
    print(json.dumps({k: meta[k] for k in ("path", "rows", "sha256", "bytes", "runtime_s", "nullRate")}, indent=2))
    return 0


def cmd_check() -> int:
    import pyarrow.compute as pc
    fails = 0
    t = pq.read_table(DERIVED / f"{OUT}.parquet")
    lm = pq.read_table(DERIVED / f"cells-r{RES}-monthly.parquet", columns=["h3", "month", "lst_day_k", "lst_night_k"])
    ncell = len(pc.unique(t["h3"]))
    ok = t.num_rows == 91_800 * 120 and ncell == 91_800
    print(f"[1] rows {t.num_rows:,} (want 11,016,000), cells {ncell:,}: {'PASS' if ok else 'FAIL'}"); fails += not ok

    y23 = t.filter(pc.equal(t["year"], 2023))
    a = {(h, m): (d, n) for h, m, d, n in zip(y23["h3"].to_pylist(), y23["month"].to_pylist(),
                                              y23["lst_day_k"].to_pylist(), y23["lst_night_k"].to_pylist())}
    worst, bad, nullmis = 0.0, 0, 0
    for h, m, d, n in zip(lm["h3"].to_pylist(), lm["month"].to_pylist(), lm["lst_day_k"].to_pylist(), lm["lst_night_k"].to_pylist()):
        d2, n2 = a[(h, m)]
        for x, y in ((d, d2), (n, n2)):
            if (x is None) != (y is None):
                nullmis += 1
            elif x is not None:
                worst = max(worst, abs(x - y))
    ok = nullmis == 0 and worst == 0.0
    print(f"[2] 2023 rows vs L1m: null mismatches {nullmis}, max |diff| {worst} K (exact equality required): {'PASS' if ok else 'FAIL'}"); fails += not ok

    bad = 0
    for d, n, r in zip(t["lst_day_k"].to_pylist(), t["lst_night_k"].to_pylist(), t["missing_reason"].to_pylist()):
        th = json.loads(r).get("thermal", "")
        bad += ("day:" in th) != (d is None) or ("night:" in th) != (n is None)
    print(f"[3] per-row missing_reason mismatches: {bad}: {'PASS' if bad == 0 else 'FAIL'}"); fails += bool(bad)

    spots = {"Death Valley": "8429855ffffffff", "Haughton crater": "840255dffffffff", "Mauna Loa": "845d139ffffffff"}
    print("[4] July day LST by year (K):")
    for name, h in spots.items():
        s = t.filter(pc.and_(pc.equal(t["h3"], h), pc.equal(t["month"], 7)))
        vals = " ".join("--" if v is None else f"{v:.0f}" for v in s["lst_day_k"].to_pylist())
        print(f"    {name:16s} {h}: {vals}")
    print("ALL PASS" if fails == 0 else f"{fails} CHECK(S) FAILED")
    return 0 if fails == 0 else 1


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    sys.exit({"fetch": cmd_fetch, "build": cmd_build, "check": cmd_check}.get(cmd, lambda: (print(__doc__), 2)[1])())
