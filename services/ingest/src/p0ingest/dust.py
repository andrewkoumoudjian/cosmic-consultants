"""L1-dust: MERRA-2 DUEXTTAU per H3 land cell. Work order W28 (#68).

2023 monthly means of MERRA-2 tavgM_2d_aer_Nx DUEXTTAU (Dust Extinction AOT
[550 nm], dimensionless) from the 12 M2TMNXAER v5.12.4 granules, one per
month. DUEXTTAU is a reanalysis column-integrated dust extinction optical
depth at 550 nm - an atmospheric aerosol observable, NOT a surface-dust
hazard rate and NOT comparable to a Mars opacity tau.

Mapping: each master hexagon center (from _derived/cells-r4.parquet) is
mapped to the NEAREST native 0.5 x 0.625 deg (361 x 576) grid center,
per-axis nearest, latitude clipped at the two exact pole rows (+/-90) and
longitude wrapped (0.625 deg divides 360, so the grid is periodic; a hexagon
near +/-180 maps to whichever side is nearer). Several hexagons share one
native cell by construction. The sample is the nearest-center value, NOT an
area-weighted hexagon mean and NOT a finer-resolution measurement.

Run (from services/ingest):
  uv run python -m p0ingest.dust fetch   # 12 granules 2023 into data/snapshots/merra2-m2tmnxaer/
  uv run python -m p0ingest.dust build   # writes _derived/dust-r4[-monthly].parquet + .meta.json
  uv run python -m p0ingest.dust check    # exit 0 only if every check passes
"""
from __future__ import annotations

import calendar
import json
import re
import sys
import time
import warnings
from datetime import datetime, timezone

import netCDF4
import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq

from .grid import DERIVED, RES
from .snapshots import SNAP, cmr_granule_urls, fetch, load_manifest, sha256

DATASET = "merra2-m2tmnxaer"
COLLECTION = "C1276812866-GES_DISC"  # M2TMNXAER v5.12.4 (catalog row license-verified CC0)
YEAR = 2023
MONTHS = list(range(1, 13))
OUT_MONTHLY = f"dust-r{RES}-monthly"
OUT = f"dust-r{RES}"
_FILE = re.compile(r"\.tavgM_2d_aer_Nx\.(\d{4})(\d{2})\.nc4$")
EXPECTED_LONG_NAME = "Dust Extinction AOT [550 nm]"  # verified on the actual granules
FILL_GUARD = 1e10  # residual values beyond this are fill/missing, whatever the attr says


def month_of(local_path: str) -> int:
    """Calendar month (1-12) of a M2TMNXAER granule from its .YYYYMM.nc4 name."""
    m = _FILE.search(local_path.split("/")[-1])
    if not m:
        raise ValueError(f"no .tavgM_2d_aer_Nx.YYYYMM.nc4 in {local_path}")
    y, mo = int(m.group(1)), int(m.group(2))
    if y != YEAR:
        raise ValueError(f"{local_path}: year {y}, expected {YEAR}")
    if not 1 <= mo <= 12:
        raise ValueError(f"{local_path}: invalid month {mo}")
    return mo


def granules() -> dict[int, dict]:
    """Manifest entries for merra2-m2tmnxaer, keyed by month. Rejects duplicates."""
    by_month: dict[int, dict] = {}
    for e in load_manifest()["entries"]:
        if e.get("datasetId") != DATASET:
            continue
        mo = month_of(e["localPath"])
        if mo in by_month:
            raise ValueError(f"two {DATASET} granules for month {mo}: "
                             f"{by_month[mo]['localPath']} and {e['localPath']}")
        by_month[mo] = e
    return by_month


def verify_and_read(local_path: str) -> dict:
    """Open one granule, verify it against the documented M2TMNXAER structure,
    return the DUEXTTAU field plus grid/check evidence. Raises on any mismatch."""
    path = SNAP.parent.parent / local_path
    mo = month_of(local_path)
    checks: list[str] = []
    ds = netCDF4.Dataset(path)
    try:
        for k, want in (("ShortName", "M2TMNXAER"), ("VersionID", "5.12.4"),
                        ("DataResolution", "0.5 x 0.625"), ("identifier_product_doi", "10.5067/FH9A0MLJPC7N")):
            got = getattr(ds, k, None)
            if got != want:
                raise ValueError(f"{local_path}: global {k}={got!r}, expected {want!r}")
            checks.append(f"global:{k}={want}")
        dims = {k: len(v) for k, v in ds.dimensions.items()}
        if dims.get("time") != 1 or dims.get("lat") != 361 or dims.get("lon") != 576:
            raise ValueError(f"{local_path}: dimensions {dims}, expected time=1 lat=361 lon=576")
        glat = np.array(ds.variables["lat"][:], dtype=np.float64)
        glon = np.array(ds.variables["lon"][:], dtype=np.float64)
        if glat[0] != -90.0 or glat[-1] != 90.0 or not np.allclose(np.diff(glat), 0.5):
            raise ValueError(f"{local_path}: unexpected latitude axis {glat[:3]}...{glat[-3:]}")
        if glon[0] != -180.0 or glon[-1] != 179.375 or not np.allclose(np.diff(glon), 0.625):
            raise ValueError(f"{local_path}: unexpected longitude axis {glon[:3]}...{glon[-3:]}")
        checks.append("grid:lat[-90..90:0.5](361)")
        checks.append("grid:lon[-180..179.375:0.625](576)")
        tvar = ds.variables["time"]
        tvar.set_auto_mask(False)  # its float32 valid_range cannot cast to int32 data; value is a plain label
        base_month = int(str(tvar.units).split("-")[1])
        if base_month != mo or not str(tvar.units).startswith(f"minutes since {YEAR}-"):
            raise ValueError(f"{local_path}: time units {tvar.units!r}, expected minutes since {YEAR}-{mo:02d}-...")
        checks.append(f"time:units={tvar.units}")
        tval = int(np.array(tvar[:]).ravel()[0])  # minutes after base; label, not an epoch
        begin = getattr(ds, "RangeBeginningDate", "")
        end = getattr(ds, "RangeEndingDate", "")
        last = calendar.monthrange(YEAR, mo)[1]
        if begin != f"{YEAR}-{mo:02d}-01" or end != f"{YEAR}-{mo:02d}-{last:02d}":
            raise ValueError(f"{local_path}: time range {begin}..{end} does not cover month {mo}")
        checks.append(f"time:range={begin}..{end}")
        checks.append("time:unmaskedValueRead=ok")
        var = ds.variables["DUEXTTAU"]
        long_name = var.long_name
        units = var.units
        fill = float(var._FillValue)
        if long_name != EXPECTED_LONG_NAME:
            raise ValueError(f"{local_path}: DUEXTTAU long_name {long_name!r}, expected {EXPECTED_LONG_NAME!r}")
        if units != "1":
            raise ValueError(f"{local_path}: DUEXTTAU units {units!r}, expected '1' (dimensionless AOD)")
        checks.append(f"deps:DUEXTTAU long_name/units/fill={fill:g}")
        a = np.array(var[0], dtype=np.float64)  # (361, 576); _FillValue auto-masked to NaN
        a[a > FILL_GUARD] = np.nan              # any residual fill marker stays NaN
        n_fill = int(np.isnan(a).sum())
        return {"month": mo, "lat": glat, "lon": glon, "aod": a,
                "n_fill": n_fill, "n_valid": int(a.size - n_fill),
                "time_units": str(tvar.units), "time_value_minutes": tval,
                "checks": checks, "fill_value": fill, "long_name": long_name, "units": units}
    finally:
        ds.close()


def nearest_ij(cell_lat, cell_lon, glat, glon) -> tuple[np.ndarray, np.ndarray]:
    """Index of the nearest native grid center for each hexagon center.

    Per-axis nearest on the regular native grid. Latitude: rint((lat-glat0)/d),
    clipped to the 361 rows (the grid has exact +/-90 pole rows, so nothing
    can fall outside). Longitude: rint((lon-glon0)/d) wrapped modulo 576
    (0.625 deg divides 360; a hexagon at 179.99 E and one at 179.99 W share
    grid column 0). Halfway ties round to even (numpy rint): deterministic,
    and no real hexagon center sits exactly halfway in this build.
    """
    glat = np.asarray(glat, dtype=np.float64)
    glon = np.asarray(glon, dtype=np.float64)
    dlat = float(np.diff(glat).min())
    dlon = float(np.diff(glon).min())
    if not (np.allclose(np.diff(glat), np.ptp(glat) / (len(glat) - 1))
            and np.allclose(np.diff(glon), np.ptp(glon) / (len(glon) - 1))):
        raise ValueError("native grid is not uniform; nearest-axis mapping invalid")
    ilat = np.clip(np.rint((np.asarray(cell_lat, dtype=np.float64) - glat[0]) / dlat).astype(np.int64),
                   0, len(glat) - 1)
    ilon = np.mod(np.rint((np.asarray(cell_lon, dtype=np.float64) - glon[0]) / dlon).astype(np.int64),
                  len(glon))
    return ilat, ilon


def annual_from_monthly(vals: np.ndarray) -> dict[str, np.ndarray]:
    """Aggregate (ncell, 12) valid-only monthly AOD to the annual columns.

    Mean and max use only documented valid observations (NaN dropped). If a
    cell has no valid month, all three aggregates are null and months_used
    is 0. dust_aod_max_month is the EARLIEST month attaining the maximum
    (np.argmax returns the first occurrence), so ties are explicit and do
    not depend on month order. months_used < 12 stays visible in the output:
    partial-year support is exposed, never presented as a complete record.
    """
    vals = np.asarray(vals, dtype=np.float64)
    ncell = vals.shape[0]
    ok = np.isfinite(vals)
    used = ok.sum(axis=1)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)  # all-NaN cells stay NaN
        mean = np.where(used > 0, np.nanmean(vals, axis=1), np.nan) if vals.size else np.full(ncell, np.nan)
        mx = np.where(used > 0, np.nanmax(vals, axis=1), np.nan) if vals.size else np.full(ncell, np.nan)
    masked = np.where(ok, vals, -np.inf)
    imax = np.argmax(masked, axis=1).astype(np.float64)  # -inf everywhere -> 0, unused when used==0
    max_month = np.where(used > 0, imax + 1.0, np.nan)
    return {"dust_aod_mean": mean, "dust_aod_max": mx, "dust_aod_max_month": max_month,
            "months_used": used.astype(np.float64)}


def row_reasons_monthly(vals: np.ndarray) -> list[str]:
    """Per-row missing_reason: {dustProcess: code} only in rows where dust_aod is null."""
    out = []
    for v in vals.reshape(-1):
        out.append(json.dumps({"dustProcess": "merra2-cell-fill"}, sort_keys=True)
                   if np.isnan(v) else json.dumps({}, sort_keys=True))
    return out


def row_reasons_annual(used: np.ndarray) -> list[str]:
    out = []
    for u in used:
        r = {} if u > 0 else {"dustProcess": "merra2-no-valid-month"}
        out.append(json.dumps(r, sort_keys=True))
    return out


def validate_keys(table: pa.Table, cells: list[str]) -> list[str]:
    """Exact master-key check for the monthly table: every cell exactly once
    per month 1..12, no unknown cells, no null keys, no invalid months."""
    h3 = table.column("h3").to_pylist()
    month = table.column("month").to_pylist()
    want = set(cells)
    problems = []
    if table.num_rows != len(cells) * 12:
        problems.append(f"rows {table.num_rows}, expected {len(cells) * 12}")
    seen: set[tuple[str, int]] = set()
    for h, m in zip(h3, month):
        if h is None or m is None:
            problems.append("null key")
            break
        if h not in want:
            problems.append(f"unknown h3 {h}")
            break
        if not isinstance(m, int) or not 1 <= m <= 12:
            problems.append(f"invalid month {m}")
            break
        if (h, m) in seen:
            problems.append(f"duplicate h3/month {h}/{m}")
            break
        seen.add((h, m))
    if not problems and len(seen) != len(cells) * 12:
        problems.append(f"missing h3/month pairs: {len(cells) * 12 - len(seen)}")
    return problems


def cmd_fetch() -> int:
    urls = cmr_granule_urls(COLLECTION, f"{YEAR}-01-01T00:00:00Z,{YEAR}-12-31T23:59:59Z", ".nc4")
    by_url = {month_of(u): u for u in urls}
    if len(urls) != len(by_url):
        print(f"CMR returned duplicate months for {COLLECTION}: {len(urls)} urls, {len(by_url)} months")
        return 1
    print(f"M2TMNXAER {YEAR}: {len(urls)} granules from CMR", flush=True)
    errors = 0
    for mo in MONTHS:
        if mo not in by_url:
            print(f"FAIL month {mo}: no granule URL from CMR", flush=True)
            errors += 1
    for mo in MONTHS:
        if mo not in by_url:
            continue
        try:
            p = fetch(DATASET, by_url[mo])
            print(f"ok   {p.name} {p.stat().st_size} B (month {mo})", flush=True)
        except Exception as exc:  # noqa: BLE001 - counted, run stops non-zero
            errors += 1
            print(f"FAIL {by_url[mo]}: {exc}", flush=True)
    print(f"done, {errors} error(s)")
    return 1 if errors else 0


def cmd_build() -> int:
    t0 = time.time()
    gran = granules()
    want = set(MONTHS)
    if set(gran) != want:
        print(f"months present {sorted(gran)}; need exactly {MONTHS}; run `fetch` first")
        return 1
    cells_tbl = pq.read_table(DERIVED / f"cells-r{RES}.parquet")
    cells = cells_tbl.column("h3").to_pylist()
    if len(cells) != 91_800 or len(set(cells)) != 91_800:
        print(f"master key set wrong: {len(cells)} rows, {len(set(cells))} unique cells")
        return 1
    lat = cells_tbl.column("lat").to_numpy()
    lon = cells_tbl.column("lon").to_numpy()

    ncell = len(cells)
    vals = np.full((ncell, 12), np.nan)
    grid: dict | None = None
    ilat = ilon = None
    inputs: list[dict] = []
    checks_total = 0
    granule_checks: dict[int, list[str]] = {}
    fills = {}
    time_labels = {}
    for mo in MONTHS:
        g = verify_and_read(gran[mo]["localPath"])
        if grid is None:
            grid = {"lat": g["lat"], "lon": g["lon"]}
            ilat, ilon = nearest_ij(lat, lon, grid["lat"], grid["lon"])
        else:
            if not (np.array_equal(grid["lat"], g["lat"]) and np.array_equal(grid["lon"], g["lon"])):
                print(f"month {mo}: grid changed between granules")
                return 1
        vals[:, mo - 1] = g["aod"][ilat, ilon]
        fills[mo] = g["n_fill"]
        checks_total += len(g["checks"])
        granule_checks[mo] = g["checks"]
        time_labels[mo] = {"timeUnits": g["time_units"], "timeValueMinutes": g["time_value_minutes"]}
        inputs.append({"month": mo, "localPath": gran[mo]["localPath"], "sha256": gran[mo]["sha256"],
                       "bytes": gran[mo]["bytes"], "fillCells": g["n_fill"],
                       "validCells": g["n_valid"], "minAod": float(np.nanmin(g["aod"])),
                       "maxAod": float(np.nanmax(g["aod"])),
                       **time_labels[mo]})

    per_native = {}
    for i, j in zip(ilat.tolist(), ilon.tolist()):
        per_native[(i, j)] = per_native.get((i, j), 0) + 1
    shared = np.array(sorted(per_native.values()))

    prob = validate_keys(pa.table({"h3": np.repeat(cells, 12), "month": np.tile(MONTHS, ncell)}), cells)
    if prob:
        print(f"key validation failed: {prob[:3]}")
        return 1

    monthly_tbl = pa.table({
        "h3": pa.array(np.repeat(np.array(cells), 12)),
        "month": pa.array(np.tile(np.array(MONTHS, dtype=np.int8), ncell)),
        "dust_aod": pa.array(vals.reshape(-1), from_pandas=True),
        "missing_reason": pa.array(row_reasons_monthly(vals)),
    })
    ann = annual_from_monthly(vals)
    ann_tbl = pa.table({
        "h3": pa.array(cells),
        "dust_aod_mean": pa.array(ann["dust_aod_mean"], from_pandas=True),
        "dust_aod_max": pa.array(ann["dust_aod_max"], from_pandas=True),
        "dust_aod_max_month": pa.array(ann["dust_aod_max_month"], from_pandas=True),
        "months_used": pa.array(ann["months_used"].astype(np.int8)),
        "missing_reason": pa.array(row_reasons_annual(ann["months_used"])),
    })

    grid_desc = {
        "lat": {"first": float(grid["lat"][0]), "last": float(grid["lat"][-1]), "step": 0.5, "size": 361,
                "units": "degrees_north"},
        "lon": {"first": float(grid["lon"][0]), "last": float(grid["lon"][-1]), "step": 0.625, "size": 576,
                "units": "degrees_east"},
    }
    common_meta = {
        "generatedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "h3Res": RES, "year": YEAR, "cells": ncell,
        "source": {
            "datasetId": DATASET,
            "collection": COLLECTION,
            "archive": "NASA GES DISC (Earthdata)",
            "title": "MERRA-2 tavgM_2d_aer_Nx monthly mean aerosol diagnostics (M2TMNXAER v5.12.4)",
            "doi": "10.5067/FH9A0MLJPC7N",
            "license": "cc0 (verified in data/catalog/merra2-m2tmnxaer.yaml)",
            "observable": "DUEXTTAU: 'Dust Extinction AOT [550 nm]', units '1' (dimensionless optical depth)",
            "statistic": "calendar-monthly mean of 1-hourly time-averaged assimilation output",
            "spatialSupport": ("nearest native 0.5 x 0.625 deg grid center per axis, latitude clipped at the "
                               "exact +/-90 pole rows, longitude wrapped modulo 576; NOT an area-weighted "
                               "hexagon mean, NOT a finer-resolution measurement; hexagons share native cells"),
            "timeSupport": ("one granule per calendar month of 2023; the file's own time label "
                            "(units + minute offset, month-start for all 12 granules) is recorded "
                            "per input; the data are the calendar-month mean"),
        },
        "nativeGrid": grid_desc,
        "inputs": inputs,
        "hexSharePerNativeCell": {"min": int(shared.min()), "median": float(np.median(shared)),
                                  "max": int(shared.max()), "nativeCellsUsed": len(per_native)},
        "qaChecks": {"perGranuleStructureChecksTotal": checks_total,
                     "checks": {str(mo): granule_checks[mo] for mo in MONTHS}},
        "cleaningRules": {
            "missingDustValues": (f"native cells whose DUEXTTAU equals the product fill ({FILL_GUARD:g} guard) "
                                  "are NaN per month, with missing_reason dustProcess=merra2-cell-fill"),
            "rejectDuplicateMonths": "granules() raises on two manifest granules for one month",
            "rejectInvalidMonths": "month_of() rejects names outside 2023-01..2023-12",
            "requireAllTwelve": "build aborts unless exactly months 1..12 are present",
        },
        "aggregation": {
            "annual": ("dust_aod_mean/dust_aod_max use only documented valid monthly observations (NaN dropped); "
                       "dust_aod_max_month is the earliest month attaining the annual maximum (ties -> earliest); "
                       "months_used counts valid months and STAYS VISIBLE so partial-year support is exposed"),
            "monthly": "no aggregation: the nearest native cell's calendar-month mean",
        },
        "limits": {
            "model": "MERRA-2 is a reanalysis (model + assimilated observations), not a direct measurement",
            "quantity": "column-integrated atmospheric dust extinction optical depth at 550 nm over the whole "
                        "atmospheric column; a proxy for dustiness of the air, NOT surface dust coverage",
            "notMarTau": "NOT equivalent to a Mars nadir opacity tau: different geometry, wavelength and column; "
                         "no auto-equivalence is claimed",
            "noHazardRate": "no dust-hazard-rate or exceedance-frequency computation is made here",
            "resolution": "native 0.5 x 0.625 deg cells (approx 55 x 25-70 km) are coarser than H3 res-4 "
                          "hexagons; the value is representative of the area, not a point measurement",
        },
    }
    for tbl, name, extra_rows in ((monthly_tbl, OUT_MONTHLY, ncell * 12), (ann_tbl, OUT, ncell)):
        meta = dict(common_meta)
        meta["rows"] = extra_rows
        out = DERIVED / f"{name}.parquet"
        tbl = tbl.replace_schema_metadata({"cosmic-consultants": json.dumps(meta, sort_keys=True)})
        pq.write_table(tbl, out, compression="zstd")
        meta["path"] = str(out.relative_to(SNAP.parent.parent))
        meta["sha256"] = sha256(out)
        meta["bytes"] = out.stat().st_size
        meta["nullRate"] = {c: round(tbl[c].null_count / tbl.num_rows, 4) for c in tbl.column_names}
        meta["monthlyNullsByMonth"] = {mo: int(np.isnan(vals[:, mo - 1]).sum()) for mo in MONTHS}
        meta["nativeFillCellsByMonth"] = {str(mo): fills[mo] for mo in MONTHS}
        meta["monthsUsedHistogram"] = {str(k): int((ann["months_used"] == k).sum()) for k in range(0, 13)}
        (DERIVED / f"{name}.meta.json").write_text(json.dumps(meta, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"monthlyRows": ncell * 12, "annualRows": ncell, "seconds": round(time.time() - t0, 1),
                      "nativeCellsUsed": len(per_native), "hexesPerNativeCellMax": int(shared.max()),
                      "monthsUsedHistogram": {str(k): int((ann["months_used"] == k).sum()) for k in range(0, 13)}},
                     indent=1))
    return 0


SPOTS = {
    "Death Valley (Badwater)": (36.25, -116.83),
    "Haughton crater (Devon Island)": (75.38, -89.68),
    "Atacama (Yungay)": (-24.10, -70.02),
    "McMurdo Dry Valleys (Wright Valley)": (-77.52, 161.85),
    "Mauna Loa (summit)": (19.475, -155.608),
}
SAHARA = {"Sahara (central)": (23.0, 10.0)}


def cmd_check() -> int:
    import h3

    fails = 0
    cells_tbl = pq.read_table(DERIVED / f"cells-r{RES}.parquet")
    cells = cells_tbl.column("h3").to_pylist()
    m_tbl = pq.read_table(DERIVED / f"{OUT_MONTHLY}.parquet")
    a_tbl = pq.read_table(DERIVED / f"{OUT}.parquet")
    meta = json.loads((DERIVED / f"{OUT_MONTHLY}.meta.json").read_text())

    print(f"[1] exact master key domain")
    want = set(cells)
    m_h3 = m_tbl.column("h3").to_pylist()
    a_h3 = a_tbl.column("h3").to_pylist()
    ok = (m_tbl.num_rows == 1_101_600 and a_tbl.num_rows == 91_800
          and set(m_h3) == want and set(a_h3) == want
          and len(set(a_h3)) == 91_800
          and not validate_keys(m_tbl, cells))
    in_months = sorted(e["month"] for e in meta["inputs"])
    ok &= in_months == MONTHS
    for e in sorted(meta["inputs"], key=lambda e: e["month"]):
        print(f"    month {e['month']:2d}  {e['sha256'][:16]}  {e['localPath'].split('/')[-1]}  "
              f"fill {e['fillCells']}  [{e['minAod']:.4f}, {e['maxAod']:.4f}]")
    print(f"    {'PASS' if ok else 'FAIL'}")
    fails += not ok

    print(f"[2] monthly -> annual aggregation consistency (exact)")
    mv = m_tbl.column("dust_aod").to_numpy().reshape(len(cells), 12)
    m_m = m_tbl.column("month").to_numpy().reshape(len(cells), 12)
    assert (m_m[:, 0] == 1).all() and (m_m[:, -1] == 12).all()
    ann = annual_from_monthly(mv)
    mism = lambda x, y: int((~(np.isnan(x) & np.isnan(y)) & ~(x == y)).sum())
    e1 = mism(a_tbl.column("dust_aod_mean").to_numpy(), ann["dust_aod_mean"])
    e2 = mism(a_tbl.column("dust_aod_max").to_numpy(), ann["dust_aod_max"])
    me = a_tbl.column("dust_aod_max_month").to_numpy()
    e3 = mism(me, ann["dust_aod_max_month"])
    e4 = int((a_tbl.column("months_used").to_numpy() != ann["months_used"]).sum())
    # earliest-month tie rule, re-derived independently
    dup = 0
    okmm = np.isfinite(me)
    first = np.argmax(np.where(np.isfinite(mv), mv, -np.inf), axis=1).astype(float) + 1.0
    dup = int((okmm & (me != np.where(np.isnan(me), np.nan, first))).sum())
    print(f"    mean mismatches {e1}, max mismatches {e2}, max_month mismatches {e3} (+{dup} tie-rule), "
          f"months_used mismatches {e4}")
    ok = e1 == e2 == e3 == e4 == dup == 0
    print(f"    {'PASS' if ok else 'FAIL'}")
    fails += not ok

    print(f"[3] missing_reason names exactly the null traits")
    bad = 0
    for mr, v in zip(m_tbl.column("missing_reason").to_pylist(), mv.reshape(-1)):
        r = json.loads(mr)
        isnull = bool(np.isnan(v))
        if isnull and r != {"dustProcess": "merra2-cell-fill"}:
            bad += 1
        if not isnull and r != {}:
            bad += 1
    bada = 0
    for mr, mu in zip(a_tbl.column("missing_reason").to_pylist(), a_tbl.column("months_used").to_pylist()):
        r = json.loads(mr)
        if mu == 0 and r != {"dustProcess": "merra2-no-valid-month"}:
            bada += 1
        if mu != 0 and r != {}:
            bada += 1
    codes = {}
    for mr in m_tbl.column("missing_reason").to_pylist():
        for k, v in json.loads(mr).items():
            codes[f"{k}:{v}"] = codes.get(f"{k}:{v}", 0) + 1
    print(f"    monthly mismatches {bad}, annual mismatches {bada}; reason codes {codes or 'none (no null rows)'}")
    ok = bad == bada == 0
    print(f"    {'PASS' if ok else 'FAIL'}")
    fails += not ok

    print(f"[4] spot checks against the raw granules (five sites + Sahara)")
    gran = granules()
    glat = None
    cache = {}
    a_pos = {h: i for i, h in enumerate(a_h3)}
    for name, (la, lo) in {**SPOTS, **SAHARA}.items():
        c = h3.latlng_to_cell(la, lo, RES)
        row = a_pos.get(c)
        if row is None:
            print(f"    {name}: {la},{lo} -> {c} NOT A LAND CELL")
            continue
        if glat is None:
            g0 = verify_and_read(gran[1]["localPath"])
            glat, glon = g0["lat"], g0["lon"]
            cache[1] = g0["aod"]
        # the master row's hexagon center (not the probe point) drives the mapping
        hla = cells_tbl.column("lat")[row].as_py()
        hlo = cells_tbl.column("lon")[row].as_py()
        pair = nearest_ij([hla], [hlo], glat, glon)
        ii, jj = int(pair[0][0]), int(pair[1][0])
        vals12 = mv[row]
        raw_jan = cache[1][ii, jj]
        print(f"    {name} ({la},{lo}) {c}")
        print(f"      hex center lat {hla:.4f} lon {hlo:.4f} -> native center lat {glat[ii]:.3f} "
              f"lon {glon[jj]:.3f} (idx lat {ii}, lon {jj}); "
              f"raw Jan DUEXTTAU {raw_jan:.6f} vs parquet Jan {vals12[0]:.6f} "
              f"{'MATCH' if raw_jan == vals12[0] or (np.isnan(raw_jan) and np.isnan(vals12[0])) else 'MISMATCH'}")
        print(f"      months: " + " ".join(f"{m}:{v:.4f}" for m, v in enumerate(vals12, 1) if np.isfinite(v)))
        print(f"      annual mean {a_tbl.column('dust_aod_mean')[row].as_py():.6f} "
              f"max {a_tbl.column('dust_aod_max')[row].as_py():.6f} "
              f"max_month {a_tbl.column('dust_aod_max_month')[row].as_py()} "
              f"months_used {a_tbl.column('months_used')[row].as_py()}")
    print(f"[5] native mapping counts")
    ilat, ilon = nearest_ij(cells_tbl.column("lat").to_numpy(), cells_tbl.column("lon").to_numpy(), glat, glon)
    u, cnt = np.unique(np.stack([ilat, ilon]), axis=1, return_counts=True)
    gran_slice = cache[1][ilat, ilon]
    print(f"    hexes on native cells: min {cnt.min()}, median {float(np.median(cnt)):.1f}, max {cnt.max()}; "
          f"native cells used {u.shape[1]} of {361 * 576}")
    print(f"    pole rows used: lat -90 {int((ilat == 0).sum())} hexes, lat +90 {int((ilat == 360).sum())} hexes")
    print(f"    wrap column 0 (lon -180): {int((ilon == 0).sum())} hexes; column 575 (lon 179.375): "
          f"{int((ilon == 575).sum())} hexes")
    ok = True  # counts are informational; consistency already checked in [2]
    print(f"    info only")
    total_null = int(np.isnan(mv).sum())
    print(f"[6] nulls: {total_null} of {mv.size} cell-months "
          f"({total_null / mv.size:.4%}); months_used histogram "
          f"{ {str(k): int((a_tbl.column('months_used').to_numpy() == k).sum()) for k in range(0, 13)} }")
    print("ALL PASS" if fails == 0 else f"{fails} CHECK(S) FAILED")
    return 0 if fails == 0 else 1


def main() -> int:
    if len(sys.argv) != 2 or sys.argv[1] not in ("fetch", "build", "check"):
        print("usage: python -m p0ingest.dust fetch|build|check")
        return 2
    return {"fetch": cmd_fetch, "build": cmd_build, "check": cmd_check}[sys.argv[1]]()


if __name__ == "__main__":
    sys.exit(main())
