"""Checks for W17 (#58). Run: uv run python -m p0ingest.check_monthly [--old OLD_L1.parquet]

Exit code 0 only if every check passes. Prints:
  1. row counts (L1 91,800; L1m 1,101,600) and the 12 MOD11C3 inputs by month
  2. one temperature rule: L1 extremes == max/min of L1m monthly medians, exactly
  3. per-row missing_reason lists exactly the traits that are null in that row
  4. (with --old) how much the rule change moved L1 extremes vs the previous build
  5. spot checks at 5 known places
"""
from __future__ import annotations

import argparse
import json
import sys

import h3
import numpy as np
import pyarrow.parquet as pq

from .grid import DERIVED, RES

SPOTS = {
    "Death Valley (Badwater)": (36.25, -116.83),
    "Haughton crater (Devon Island)": (75.38, -89.68),
    "Atacama (Yungay)": (-24.10, -70.02),
    "McMurdo Dry Valleys (Wright Valley)": (-77.52, 161.85),
    "Mauna Loa (summit)": (19.475, -155.608),
}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--old", help="previous cells-r4.parquet, to report the effect of the rule change")
    a = ap.parse_args()
    fails = 0
    l1 = pq.read_table(DERIVED / f"cells-r{RES}.parquet").to_pandas()
    lm = pq.read_table(DERIVED / f"cells-r{RES}-monthly.parquet").to_pandas()
    meta = json.loads((DERIVED / f"cells-r{RES}-monthly.meta.json").read_text())

    print(f"[1] L1 rows {len(l1):,}; L1m rows {len(lm):,}; L1m cells x 12 = {lm.h3.nunique() * 12:,}")
    ok = len(l1) == 91_800 and len(lm) == 1_101_600 and lm.h3.nunique() == len(l1)
    months = sorted(e["month"] for e in meta["inputs"]["modis-mod11c3"])
    ok &= months == list(range(1, 13))
    for e in sorted(meta["inputs"]["modis-mod11c3"], key=lambda e: e["month"]):
        print(f"    month {e['month']:2d}  {e['sha256'][:16]}  {e['localPath'].split('/')[-1]}")
    print(f"    {'PASS' if ok else 'FAIL'}"); fails += not ok

    g = lm.groupby("h3")
    agg = g.agg(dmax=("lst_day_k", "max"), nmin=("lst_night_k", "min")).reindex(l1.h3)
    d1, dm = l1.lst_day_max_k.to_numpy(), agg.dmax.to_numpy()
    n1, nm = l1.lst_night_min_k.to_numpy(), agg.nmin.to_numpy()
    def mism(x, y):
        both_nan = np.isnan(x) & np.isnan(y)
        return int((~both_nan & ~(x == y)).sum())
    md, mn = mism(d1, dm), mism(n1, nm)
    print(f"[2] one temperature rule: day-max mismatches {md}, night-min mismatches {mn} (exact equality, NaN==NaN)")
    print(f"    {'PASS' if md == mn == 0 else 'FAIL'}"); fails += bool(md or mn)

    bad = 0
    lat = l1.lat.to_numpy()
    in_model = ((lat >= 25) & (lat <= 85)) | ((lat >= -85) & (lat <= -60))
    for i, (mr, dx, nx, bp, pf, sl) in enumerate(zip(l1.missing_reason, d1, n1, l1.barren_pct, l1.permafrost_pct, l1.slope_mean_deg)):
        r = json.loads(mr)
        want = {"dustProcess"}
        if np.isnan(dx) or np.isnan(nx): want.add("thermal")
        if bp != bp: want.add("surfaceMaterial")
        if sl != sl: want.add("terrain")
        if pf != pf:
            want.add("waterIce")
            if r.get("waterIce") != ("permafrost-not-modelled" if in_model[i] else "outside-permafrost-model"):
                bad += 1
        bad += set(r) != want
    badm = 0
    for mr, dx, nx in zip(lm.missing_reason, lm.lst_day_k, lm.lst_night_k):
        r = json.loads(mr)
        badm += ("thermal" in r) != (dx != dx or nx != nx)
        if "thermal" in r:
            badm += ("day:" in r["thermal"]) != (dx != dx) or ("night:" in r["thermal"]) != (nx != nx)
    print(f"[3] per-row missing_reason mismatches: L1 {bad}, L1m {badm}")
    thin = lm.missing_reason.str.contains("too-few-lst-pixels").sum()
    print(f"    L1m rows with a month dropped by the coverage rule: {thin:,} ({thin / len(lm):.2%})")
    codes: dict[str, int] = {}
    for mr in l1.missing_reason:
        for k, v in json.loads(mr).items():
            codes[f"{k}:{v}"] = codes.get(f"{k}:{v}", 0) + 1
    for k, v in sorted(codes.items(), key=lambda kv: -kv[1]):
        print(f"    {k:45s} {v:6d} rows")
    print(f"    {'PASS' if bad == badm == 0 else 'FAIL'}"); fails += bool(bad or badm)

    if a.old:
        old = pq.read_table(a.old).to_pandas().set_index("h3").reindex(l1.h3)
        for col in ("lst_day_max_k", "lst_night_min_k"):
            diff = l1[col].to_numpy() - old[col].to_numpy()
            diff = diff[~np.isnan(diff)]
            q = np.percentile(diff, [1, 50, 99])
            print(f"[4] rule change {col}: new - old over {len(diff):,} cells: p1 {q[0]:+.2f} K, median {q[1]:+.2f} K, "
                  f"p99 {q[2]:+.2f} K, max |diff| {np.abs(diff).max():.2f} K")

    print("[5] spot checks (monthly: Jan / Apr / Jul / Oct)")
    l1i = l1.set_index("h3"); lmi = lm.set_index(["h3", "month"])
    for name, (la, lo) in SPOTS.items():
        c = h3.latlng_to_cell(la, lo, RES)
        if c not in l1i.index:
            print(f"    {name}: {la},{lo} -> {c} NOT A LAND CELL"); continue
        r = l1i.loc[c]
        mo = [lmi.loc[(c, m)] for m in (1, 4, 7, 10)]
        temps = " | ".join(f"{m.lst_day_k:.0f}/{m.lst_night_k:.0f}K sun {m.sun_noon_elev_deg:.0f}deg {m.daylight_h:.1f}h"
                           f"{' PN' if m.polar_night else ''}{' PD' if m.polar_day else ''}" for m in mo)
        print(f"    {name} ({la},{lo}) {c}: dayMax {r.lst_day_max_k:.1f}K nightMin {r.lst_night_min_k:.1f}K "
              f"slope {r.slope_mean_deg:.1f}deg barren {r.barren_pct:.0f}% pf {r.permafrost_pct if r.permafrost_pct == r.permafrost_pct else 'null'}")
        print(f"      {temps}")
    print("ALL PASS" if fails == 0 else f"{fails} CHECK(S) FAILED")
    return 0 if fails == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
