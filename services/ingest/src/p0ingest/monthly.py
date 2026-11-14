"""L1m: cells-r<res>-monthly.parquet, one row per H3 land cell and calendar month.

Spec: docs/plan/DATA-PIPELINE.md §5 (L1m). Built by `process.build()` in the
same pass as L1, so the yearly temperature extremes in L1 are, by
construction, the max/min over these monthly medians (one temperature rule).

Columns (units in the spec):
  h3, month                      hexagon id, month 1-12 of 2023
  lst_day_k, lst_night_k         median over the hexagon's 0.05 deg pixels of
                                 that month's MOD11C3 day / night LST [K]
  lst_diurnal_k                  lst_day_k - lst_night_k when both exist [K]
  lst_valid_pixels               pixels with BOTH a day and a night value that month
  sun_noon_elev_deg, daylight_h  sun geometry on the 15th of the month
  polar_day, polar_night         sun never sets / never rises on the 15th
  dust_aod                       null until MERRA-2 is unblocked
  missing_reason                 JSON text, per row: trait -> short code
"""
from __future__ import annotations

import json
import re
from datetime import date, datetime, timedelta, timezone

import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq
from pyhdf.SD import SD, SDC

from .grid import DERIVED
from .snapshots import SNAP, sha256

LST_SCALE = 0.02  # K per count, MOD11C3 V061; fill 0; valid 7500..65535
YEAR = 2023
# Coverage rule (team choice, docs/plan/DATA-PIPELINE.md §5 L1m): a monthly median
# counts only if at least this share of the hexagon's CMG pixels have a value
# that month. Without it, a cloudy month with 1 clear pixel can set the yearly
# extreme (found in #58: New Guinea highlands, 1 of 65 pixels -> 240 K).
MIN_PIXEL_SHARE = 0.25
_DOY = re.compile(r"\.A(\d{4})(\d{3})\.")


def month_of(local_path: str) -> int:
    """Calendar month of a MOD11C3 granule from its 'A<year><doy>' start date."""
    m = _DOY.search(local_path)
    if not m:
        raise ValueError(f"no A<year><doy> in {local_path}")
    year, doy = int(m.group(1)), int(m.group(2))
    if year != YEAR:
        raise ValueError(f"{local_path}: year {year}, expected {YEAR}")
    return (date(year, 1, 1) + timedelta(days=doy - 1)).month


def read_lst(local_path: str) -> tuple[np.ndarray, np.ndarray]:
    sd = SD(str(SNAP.parent.parent / local_path), SDC.READ)
    day = sd.select("LST_Day_CMG")[:].astype(np.float64)
    night = sd.select("LST_Night_CMG")[:].astype(np.float64)
    day[day < 7500] = np.nan
    night[night < 7500] = np.nan
    return day * LST_SCALE, night * LST_SCALE


def lst_monthly(files: list[dict], order, starts, group_stat):
    """One read of each granule. Returns
    (day[ncell,12], night[ncell,12], nboth[ncell,12], rsum, rn, thin_day, thin_night):
    monthly medians (NaN when fewer than MIN_PIXEL_SHARE of the cell's pixels
    have a value), both-valid pixel counts, the per-pixel sums/counts of
    (day - night) that L1's diurnal column uses, and flags for months dropped
    by the coverage rule."""
    ncell = len(starts)
    size = np.diff(np.append(starts, len(order))).astype(np.float64)  # CMG pixels per cell
    need = MIN_PIXEL_SHARE * size
    day_m = np.full((ncell, 12), np.nan)
    night_m = np.full((ncell, 12), np.nan)
    nboth = np.zeros((ncell, 12))
    thin_day = np.zeros((ncell, 12), dtype=bool)
    thin_night = np.zeros((ncell, 12), dtype=bool)
    seen: set[int] = set()
    rsum = rn = None
    for e in files:
        mo = month_of(e["localPath"])
        if mo in seen:
            raise ValueError(f"two MOD11C3 granules for month {mo}")
        seen.add(mo)
        day, night = read_lst(e["localPath"])
        if rsum is None:
            rsum = np.zeros(day.shape)
            rn = np.zeros(day.shape, dtype=np.int16)
        both = ~np.isnan(day) & ~np.isnan(night)
        rsum[both] += (day - night)[both]
        rn[both] += 1
        dmed, dn = group_stat(day, order, starts, "median")
        nmed, nn = group_stat(night, order, starts, "median")
        day_m[:, mo - 1] = np.where(dn >= need, dmed, np.nan)
        night_m[:, mo - 1] = np.where(nn >= need, nmed, np.nan)
        thin_day[:, mo - 1] = (dn > 0) & (dn < need)
        thin_night[:, mo - 1] = (nn > 0) & (nn < need)
        _, nboth[:, mo - 1] = group_stat(np.where(both, 0.0, np.nan), order, starts, "mean")
    if seen != set(range(1, 13)):
        raise ValueError(f"MOD11C3 months present: {sorted(seen)}; need all 12")
    return day_m, night_m, nboth, rsum, rn, thin_day, thin_night


def sun_monthly(lat: np.ndarray) -> dict[str, np.ndarray]:
    """Sun geometry on the 15th of each month of 2023, from latitude only.
    Declination: delta = -23.44 deg * cos(2*pi*(doy + 10) / 365). Geometric sun
    centre, no refraction, no terrain shadows. Shapes are [ncell, 12]."""
    doy = np.array([date(YEAR, m, 15).timetuple().tm_yday for m in range(1, 13)], dtype=np.float64)
    dec = -23.44 * np.cos(2 * np.pi * (doy + 10) / 365.0)  # deg
    phi = np.radians(lat)[:, None]
    d = np.radians(dec)[None, :]
    noon = 90.0 - np.abs(lat[:, None] - dec[None, :])
    cos_w0 = -np.tan(phi) * np.tan(d)
    polar_day = cos_w0 <= -1.0
    polar_night = cos_w0 >= 1.0
    w0 = np.degrees(np.arccos(np.clip(cos_w0, -1.0, 1.0)))
    return {"sun_noon_elev_deg": noon, "daylight_h": 2.0 * w0 / 15.0,
            "polar_day": polar_day, "polar_night": polar_night, "declination_deg": dec}


def write_monthly(hexes: np.ndarray, lat: np.ndarray, day_m, night_m, nboth, thin_day, thin_night,
                  files: list[dict], res: int, dust_reason: str) -> dict:
    ncell = len(hexes)
    sun = sun_monthly(lat)
    months = np.tile(np.arange(1, 13, dtype=np.int8), ncell)
    flat = lambda a: a.reshape(-1)  # row-major: cell, then month
    day_f, night_f = flat(day_m), flat(night_m)
    diurnal = np.where(np.isnan(day_f) | np.isnan(night_f), np.nan, day_f - night_f)

    reasons = []
    for dn, nn, td, tn in zip(np.isnan(day_f), np.isnan(night_f), flat(thin_day), flat(thin_night)):
        r = {"dustProcess": "dust-blocked"}
        parts = []
        if dn:
            parts.append("day:" + ("too-few-lst-pixels" if td else "no-lst-pixels"))
        if nn:
            parts.append("night:" + ("too-few-lst-pixels" if tn else "no-lst-pixels"))
        if parts:
            r["thermal"] = ",".join(parts)
        reasons.append(json.dumps(r, sort_keys=True))

    tbl = pa.table({
        "h3": pa.array(np.repeat(hexes, 12)),
        "month": pa.array(months),
        "lst_day_k": pa.array(day_f, from_pandas=True),
        "lst_night_k": pa.array(night_f, from_pandas=True),
        "lst_diurnal_k": pa.array(diurnal, from_pandas=True),
        "lst_valid_pixels": pa.array(flat(nboth).astype(np.int32)),
        "sun_noon_elev_deg": pa.array(flat(sun["sun_noon_elev_deg"])),
        "daylight_h": pa.array(flat(sun["daylight_h"])),
        "polar_day": pa.array(flat(sun["polar_day"])),
        "polar_night": pa.array(flat(sun["polar_night"])),
        "dust_aod": pa.nulls(ncell * 12, pa.float64()),
        "missing_reason": pa.array(reasons),
    })
    meta = {
        "generatedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "h3Res": res, "cells": int(ncell), "rows": int(ncell * 12), "year": YEAR,
        "inputs": {"modis-mod11c3": [{"localPath": e["localPath"], "sha256": e["sha256"],
                                      "month": month_of(e["localPath"])} for e in files]},
        "computed": {
            "lst": "per month: median over the hexagon's 0.05 deg CMG pixels of MOD11C3 V061 LST_Day_CMG / LST_Night_CMG (x0.02 K, counts < 7500 = fill)",
            "coverageRule": f"a monthly median is kept only if >= {MIN_PIXEL_SHARE:.0%} of the hexagon's CMG pixels have a value that month; otherwise null, reason too-few-lst-pixels",
            "sun": "15th of each month; declination -23.44*cos(2*pi*(doy+10)/365); geometric centre, no refraction, no terrain shadows",
            "declination_deg": [round(float(x), 3) for x in sun["declination_deg"]],
        },
        "missing": {"dustProcess": dust_reason},
    }
    out = DERIVED / f"cells-r{res}-monthly.parquet"
    tbl = tbl.replace_schema_metadata({"cosmic-consultants": json.dumps(meta)})
    pq.write_table(tbl, out, compression="zstd")
    meta.update(path=str(out.relative_to(SNAP.parent.parent)), sha256=sha256(out), bytes=out.stat().st_size)
    meta["nullRate"] = {c: round(tbl[c].null_count / tbl.num_rows, 4) for c in tbl.column_names}
    (DERIVED / f"cells-r{res}-monthly.meta.json").write_text(json.dumps(meta, indent=2) + "\n")
    return meta
