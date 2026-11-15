"""W31: MERRA-2 10 m wind speed per H3 land cell. Work order W31 (#89).

2023 monthly means of the 10 m wind over each master hexagon, from two MERRA-2
monthly collections (v5.12.4, 0.5 x 0.625 deg native grid):

- merra2-m2tmnxflx (tavgM_2d_flx_Nx, DOI 10.5067/0JRLVL8YV2Y4): the wind
  SPEED fields. SPEED is the product's own monthly mean of the 10 m
  'surface_wind_speed' diagnostic (m s-1), and SPEEDMAX is the monthly mean
  of the hourly maximum of the same field. A real granule was opened and its
  variable list read before this module was written: M2TMNXSLV monthly has
  ONLY U10M/V10M (no speed field); the speed fields live in M2TMNXFLX.
- merra2-m2tmnxslv (tavgM_2d_slv_Nx, DOI 10.5067/AP1B0BA5PD2K): U10M/V10M,
  the monthly means of the 10 m eastward/northward wind COMPONENTS. They are
  carried for direction context only (columns u10m_mean/v10m_mean). The mean
  speed (wind_speed) is NEVER computed from them: |mean U, mean V| is biased
  low by Jensen's inequality, so the speed field is the only legal source.

Output columns, monthly table wind-r4-monthly.parquet (h3, month):
  wind_speed      SPEED monthly mean, m s-1 (the speed field)
  wind_speed_max  SPEEDMAX monthly mean (mean of hourly maxima), m s-1
  u10m_mean      U10M monthly mean (vector component, NOT for speed)
  v10m_mean      V10M monthly mean (vector component, NOT for speed)
  missing_reason JSON; keys are exactly the null value columns of that row

Annual table wind-r4.parquet (h3): wind_speed_mean = mean of the 12 monthly
wind_speed values (NaN dropped), months_used, missing_reason - a simple,
documented summary of the monthly table, nothing else.

Mapping: each master hexagon center (cells-r4.parquet) maps to the NEAREST
native 0.5 x 0.625 deg (361 x 576) grid center, per-axis nearest, latitude
clipped at the exact +/-90 pole rows, longitude wrapped (0.625 divides 360,
so the grid is periodic). Several hexagons share one native cell. The sample
is the nearest-center value, NOT an area-weighted hexagon mean and NOT a
finer-resolution measurement.

Limits (also in the .meta.json): 10 m Earth wind is not the last km of Mars
descent; air density differs (pressureRegime mismatch). MERRA-2 is a
reanalysis, not a direct measurement.

Run (from services/ingest):
  uv run python -m p0ingest.wind fetch   # 24 granules 2023 (12 FLX + 12 SLV)
  uv run python -m p0ingest.wind build   # writes _derived/wind-r4[-monthly].parquet + .meta.json
  uv run python -m p0ingest.wind check   # exit 0 only if every check passes
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

DATASET_FLX = "merra2-m2tmnxflx"          # tavgM_2d_flx_Nx: SPEED, SPEEDMAX
DATASET_SLV = "merra2-m2tmnxslv"          # tavgM_2d_slv_Nx: U10M, V10M
COLLECTION_FLX = "C1276812868-GES_DISC"   # M2TMNXFLX v5.12.4 (catalog row license-verified CC0)
COLLECTION_SLV = "C1276812859-GES_DISC"   # M2TMNXSLV v5.12.4 (catalog row license-verified CC0)
SOURCES = {
    DATASET_FLX: {"collection": COLLECTION_FLX, "shortName": "M2TMNXFLX",
                  "doi": "10.5067/0JRLVL8YV2Y4", "title": "MERRA-2 tavgM_2d_flx_Nx monthly mean, "
                  "Time-Averaged, Single-Level, Assimilation, Surface Flux Diagnostics (M2TMNXFLX v5.12.4)",
                  "file": "tavgM_2d_flx_Nx", "vars": {"SPEED": "surface_wind_speed",
                                                     "SPEEDMAX": "surface_wind_speed"}},
    DATASET_SLV: {"collection": COLLECTION_SLV, "shortName": "M2TMNXSLV",
                  "doi": "10.5067/AP1B0BA5PD2K", "title": "MERRA-2 tavgM_2d_slv_Nx monthly mean, "
                  "Time-Averaged, Single-Level, Assimilation, Single-Level Diagnostics (M2TMNXSLV v5.12.4)",
                  "file": "tavgM_2d_slv_Nx", "vars": {"U10M": "10-meter_eastward_wind",
                                                     "V10M": "10-meter_northward_wind"}},
}
YEAR = 2023
MONTHS = list(range(1, 13))
OUT_MONTHLY = f"wind-r{RES}-monthly"
OUT = f"wind-r{RES}"
_FILE = re.compile(r"\.tavgM_2d_(flx|slv)_Nx\.(\d{4})(\d{2})\.nc4$")
FILL_GUARD = 1e10  # residual values beyond this are fill/missing, whatever the attr says
SPEED_PLAUSIBLE = (0.0, 60.0)   # monthly mean 10 m wind speed, m s-1
GUST_PLAUSIBLE = (0.0, 90.0)    # monthly mean of hourly maxima, m s-1
COMPONENT_PLAUSIBLE = (-60.0, 60.0)  # monthly mean vector components, m s-1


def month_of(local_path: str) -> int:
    """Calendar month (1-12) of a M2TMNXFLX/M2TMNXSLV granule from its .YYYYMM.nc4 name."""
    m = _FILE.search(local_path.split("/")[-1])
    if not m:
        raise ValueError(f"no .tavgM_2d_(flx|slv)_Nx.YYYYMM.nc4 in {local_path}")
    y, mo = int(m.group(2)), int(m.group(3))
    if y != YEAR:
        raise ValueError(f"{local_path}: year {y}, expected {YEAR}")
    if not 1 <= mo <= 12:
        raise ValueError(f"{local_path}: invalid month {mo}")
    return mo


def collection_of(local_path: str) -> str:
    """datasetId of a granule from its filename (flx vs slv), cross-checked with the manifest."""
    m = _FILE.search(local_path.split("/")[-1])
    if not m:
        raise ValueError(f"no .tavgM_2d_(flx|slv)_Nx.YYYYMM.nc4 in {local_path}")
    return DATASET_FLX if m.group(1) == "flx" else DATASET_SLV


def granules(dataset: str) -> dict[int, dict]:
    """Manifest entries for one of the two datasets, keyed by month. Rejects duplicates."""
    if dataset not in SOURCES:
        raise ValueError(f"unknown dataset {dataset!r}, expected one of {sorted(SOURCES)}")
    by_month: dict[int, dict] = {}
    for e in load_manifest()["entries"]:
        if e.get("datasetId") != dataset:
            continue
        mo = month_of(e["localPath"])
        if collection_of(e["localPath"]) != dataset:
            raise ValueError(f"{e['localPath']}: filename collection does not match manifest datasetId {dataset}")
        if mo in by_month:
            raise ValueError(f"two {dataset} granules for month {mo}: "
                             f"{by_month[mo]['localPath']} and {e['localPath']}")
        by_month[mo] = e
    return by_month


def verify_and_read(entry: dict) -> dict:
    """Open one granule, verify it against the documented structure of its collection,
    return the wind fields plus grid/check evidence. Raises on any mismatch."""
    local_path = entry["localPath"]
    dataset = entry["datasetId"]
    src = SOURCES[dataset]
    path = SNAP.parent.parent / local_path
    mo = month_of(local_path)
    checks: list[str] = []
    ds = netCDF4.Dataset(path)
    try:
        for k, want in (("ShortName", src["shortName"]), ("VersionID", "5.12.4"),
                        ("DataResolution", "0.5 x 0.625"),
                        ("identifier_product_doi", src["doi"])):
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
        if not str(tvar.units).startswith(f"minutes since {YEAR}-{mo:02d}-"):
            raise ValueError(f"{local_path}: time units {tvar.units!r}, expected minutes since {YEAR}-{mo:02d}-...")
        checks.append(f"time:units={tvar.units}")
        tval = int(np.array(tvar[:]).ravel()[0])  # minutes after base; label, not an epoch
        begin = getattr(ds, "RangeBeginningDate", "")
        end = getattr(ds, "RangeEndingDate", "")
        last = calendar.monthrange(YEAR, mo)[1]
        if begin != f"{YEAR}-{mo:02d}-01" or end != f"{YEAR}-{mo:02d}-{last:02d}":
            raise ValueError(f"{local_path}: time range {begin}..{end} does not cover month {mo}")
        checks.append(f"time:range={begin}..{end}")
        fields = {}
        for name, want_long_name in src["vars"].items():
            var = ds.variables[name]
            long_name = var.long_name
            units = var.units
            fill = float(var._FillValue)
            if long_name != want_long_name:
                raise ValueError(f"{local_path}: {name} long_name {long_name!r}, expected {want_long_name!r}")
            if units != "m s-1":
                raise ValueError(f"{local_path}: {name} units {units!r}, expected 'm s-1'")
            checks.append(f"deps:{name} long_name/units/fill={fill:g}")
            a = np.array(var[0], dtype=np.float64)  # (361, 576); _FillValue auto-masked to NaN
            a[a > FILL_GUARD] = np.nan              # any residual fill marker stays NaN
            fields[name] = a
        return {"month": mo, "dataset": dataset, "lat": glat, "lon": glon, "fields": fields,
                "n_fill": {k: int(np.isnan(v).sum()) for k, v in fields.items()},
                "n_valid": {k: int(v.size - np.isnan(v).sum()) for k, v in fields.items()},
                "time_units": str(tvar.units), "time_value_minutes": tval,
                "checks": checks}
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


def annual_from_monthly(speed: np.ndarray) -> dict[str, np.ndarray]:
    """Aggregate (ncell, 12) monthly mean speeds to the annual column.

    wind_speed_mean is the mean of the monthly speeds (NaN dropped) - NOT the
    mean speed of the year recomputed from anything else. If a cell has no
    valid month, wind_speed_mean is null and months_used is 0.
    months_used < 12 stays visible in the output: partial-year support is
    exposed, never presented as a complete record.
    """
    speed = np.asarray(speed, dtype=np.float64)
    ncell = speed.shape[0]
    ok = np.isfinite(speed)
    used = ok.sum(axis=1)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)  # all-NaN cells stay NaN
        mean = np.where(used > 0, np.nanmean(speed, axis=1), np.nan) if speed.size else np.full(ncell, np.nan)
    return {"wind_speed_mean": mean, "months_used": used.astype(np.float64)}


VALUE_COLUMNS = ("wind_speed", "wind_speed_max", "u10m_mean", "v10m_mean")


def row_reasons_monthly(vals: dict[str, np.ndarray]) -> list[str]:
    """Per-row missing_reason JSON: keys are exactly that row's null value columns.

    vals maps VALUE_COLUMNS to flat (rows,) arrays in monthly-table order
    (h3 blocks of 12 ascending months, the construction order of the table).
    """
    out = []
    for i in range(len(next(iter(vals.values())))):
        r = {name: "merra2-cell-fill" for name in VALUE_COLUMNS if np.isnan(vals[name][i])}
        out.append(json.dumps(r, sort_keys=True))
    return out


def row_reasons_annual(used: np.ndarray) -> list[str]:
    out = []
    for u in used:
        r = {} if u > 0 else {"wind_speed_mean": "merra2-no-valid-month"}
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
    errors = 0
    for dataset, src in SOURCES.items():
        urls = cmr_granule_urls(src["collection"], f"{YEAR}-01-01T00:00:00Z,{YEAR}-12-31T23:59:59Z", ".nc4")
        by_month: dict[int, str] = {}
        for u in sorted(urls):  # deterministic: if two streams cover one month, the first sorted URL wins
            by_month.setdefault(month_of(u), u)
        print(f"{src['shortName']} {YEAR}: {len(urls)} granule URLs from CMR, {len(by_month)} unique months",
              flush=True)
        for mo in MONTHS:
            if mo not in by_month:
                print(f"FAIL {src['shortName']} month {mo}: no granule URL from CMR", flush=True)
                errors += 1
        for mo in MONTHS:
            if mo not in by_month:
                continue
            try:
                p = fetch(dataset, by_month[mo])
                print(f"ok   {p.name} {p.stat().st_size} B (month {mo})", flush=True)
            except Exception as exc:  # noqa: BLE001 - counted, run stops non-zero
                errors += 1
                print(f"FAIL {by_month[mo]}: {exc}", flush=True)
    print(f"done, {errors} error(s)")
    return 1 if errors else 0


def cmd_build() -> int:
    t0 = time.time()
    ncell_expected = 91_800
    cells_tbl = pq.read_table(DERIVED / f"cells-r{RES}.parquet")
    cells = cells_tbl.column("h3").to_pylist()
    if len(cells) != ncell_expected or len(set(cells)) != ncell_expected:
        print(f"master key set wrong: {len(cells)} rows, {len(set(cells))} unique cells")
        return 1
    lat = cells_tbl.column("lat").to_numpy()
    lon = cells_tbl.column("lon").to_numpy()
    ncell = len(cells)

    vals = {c: np.full((ncell, 12), np.nan) for c in VALUE_COLUMNS}
    source_var = {"wind_speed": ("merra2-m2tmnxflx", "SPEED"), "wind_speed_max": ("merra2-m2tmnxflx", "SPEEDMAX"),
                 "u10m_mean": ("merra2-m2tmnxslv", "U10M"), "v10m_mean": ("merra2-m2tmnxslv", "V10M")}
    grid = None
    ilat = ilon = None
    inputs: list[dict] = []
    granule_checks: list[str] = []
    fills: dict[str, dict[str, int]] = {}
    for dataset in (DATASET_FLX, DATASET_SLV):
        gran = granules(dataset)
        if set(gran) != set(MONTHS):
            print(f"{dataset}: months present {sorted(gran)}; need exactly {MONTHS}; run `fetch` first")
            return 1
        for mo in MONTHS:
            g = verify_and_read(gran[mo])
            if grid is None:
                grid = {"lat": g["lat"], "lon": g["lon"]}
                ilat, ilon = nearest_ij(lat, lon, grid["lat"], grid["lon"])
            elif not (np.array_equal(grid["lat"], g["lat"]) and np.array_equal(grid["lon"], g["lon"])):
                print(f"{dataset} month {mo}: grid changed between granules")
                return 1
            for col, (dset, var) in source_var.items():
                if dset != dataset:
                    continue
                vals[col][:, mo - 1] = g["fields"][var][ilat, ilon]
            fills[f"{dataset}:{mo}"] = g["n_fill"]
            granule_checks.extend(g["checks"])
            inputs.append({"datasetId": dataset, "month": mo, "sourceUrl": gran[mo]["sourceUrl"],
                           "localPath": gran[mo]["localPath"], "sha256": gran[mo]["sha256"],
                           "bytes": gran[mo]["bytes"], "fillCells": g["n_fill"],
                           "validCells": g["n_valid"],
                           "min": {k: float(np.nanmin(v)) for k, v in g["fields"].items()},
                           "max": {k: float(np.nanmax(v)) for k, v in g["fields"].items()}})

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
        "wind_speed": pa.array(vals["wind_speed"].reshape(-1), from_pandas=True),
        "wind_speed_max": pa.array(vals["wind_speed_max"].reshape(-1), from_pandas=True),
        "u10m_mean": pa.array(vals["u10m_mean"].reshape(-1), from_pandas=True),
        "v10m_mean": pa.array(vals["v10m_mean"].reshape(-1), from_pandas=True),
        "missing_reason": pa.array(row_reasons_monthly({c: vals[c].reshape(-1) for c in VALUE_COLUMNS})),
    })
    ann = annual_from_monthly(vals["wind_speed"])
    ann_tbl = pa.table({
        "h3": pa.array(cells),
        "wind_speed_mean": pa.array(ann["wind_speed_mean"], from_pandas=True),
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
        "observable": {
            "wind_speed": "M2TMNXFLX SPEED monthly mean ('surface_wind_speed', units 'm s-1'): the monthly "
                          "mean of the model's 10 m wind-speed field. It is a real speed field - NEVER "
                          "sqrt(meanU^2 + meanV^2), which is biased low by Jensen's inequality.",
            "wind_speed_max": "M2TMNXFLX SPEEDMAX monthly mean (same long_name, units 'm s-1'): the monthly "
                              "mean of the hourly MAXIMUM of the 10 m wind-speed field (mean gust level).",
            "u10m_mean": "M2TMNXSLV U10M monthly mean ('10-meter_eastward_wind', 'm s-1'): VECTOR COMPONENT "
                         "for direction context only; not used for any speed value.",
            "v10m_mean": "M2TMNXSLV V10M monthly mean ('10-meter_northward_wind', 'm s-1'): VECTOR COMPONENT "
                         "for direction context only; not used for any speed value.",
        },
        "units": "m s-1 for all four value columns",
        "sources": {d: {"datasetId": d, "collection": SOURCES[d]["collection"], "archive": "NASA GES DISC (Earthdata)",
                        "title": SOURCES[d]["title"], "doi": SOURCES[d]["doi"],
                        "license": "cc0 (verified in data/catalog/"
                                   + d + ".yaml)",
                        "fieldChoiceEvidence":
                            "M2TMNXSLV monthly granules contain only U10M/V10M (no speed field); the "
                            "monthly SPEED/SPEEDMAX fields live in M2TMNXFLX. Verified by opening real "
                            "granules of both collections and reading their variable lists (issue #89)."}
                    for d in (DATASET_FLX, DATASET_SLV)},
        "nativeGrid": grid_desc,
        "mappingRule": ("each master hexagon center (cells-r4.parquet) maps to the NEAREST native 0.5 x 0.625 "
                        "deg grid center (the MERRA-2 grid box containing/nearest to the hexagon center), "
                        "per-axis nearest, latitude clipped at the exact +/-90 pole rows, longitude wrapped "
                        "modulo 576; several hexagons share one native cell; NOT an area-weighted hexagon "
                        "mean, NOT a finer-resolution measurement"),
        "timeSupport": ("one granule per calendar month of 2023 per collection; the products are the "
                        "calendar-month means of the hourly assimilation statistics"),
        "inputs": inputs,
        "hexSharePerNativeCell": {"min": int(shared.min()), "median": float(np.median(shared)),
                                  "max": int(shared.max()), "nativeCellsUsed": len(per_native)},
        "qaChecks": {"uniqueGranuleStructureCheckStrings": len(set(granule_checks)),
                     "checks": sorted(set(granule_checks))},
        "cleaningRules": {
            "missingWindValues": (f"native cells whose field equals the product fill ({FILL_GUARD:g} guard) "
                                  "become NaN, and missing_reason carries key <column>:merra2-cell-fill "
                                  "exactly for the null columns of that row"),
            "rejectDuplicateMonths": "granules() raises on two manifest granules of one dataset for one month",
            "rejectInvalidMonths": "month_of() rejects names outside 2023-01..2023-12",
            "requireAllTwelve": "build aborts unless exactly months 1..12 are present for both collections",
            "noSpeedFromComponents": "wind_speed/wind_speed_max come only from the M2TMNXFLX SPEED/SPEEDMAX "
                                     "fields; the U10M/V10M components are never combined into a speed",
        },
        "aggregation": {
            "annual": ("wind-r4.parquet is a simple documented summary of the monthly table: wind_speed_mean "
                       "= mean of the 12 monthly wind_speed values (NaN dropped), months_used counts valid "
                       "months and stays visible; no other statistic is invented"),
            "monthly": "no aggregation: the nearest native cell's calendar-month mean",
        },
        "limits": {
            "notMarsDescent": "10 m Earth wind is not the last km of Mars descent; no auto-equivalence to "
                              "the wind_h_edl feature value is claimed",
            "densityDiffers": "air density differs (pressureRegime mismatch): the same speed gives a very "
                              "different dynamic pressure on Mars",
            "reanalysis": "MERRA-2 is a reanalysis (model + assimilated observations), not a direct "
                          "measurement",
            "height": "the fields are the model's 10 m wind diagnostics; wind aloft during descent differs "
                      "(boundary-layer profile, veer)",
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
        meta["nativeFillCellsByGranule"] = fills
        meta["monthsUsedHistogram"] = {str(k): int((ann["months_used"] == k).sum()) for k in range(0, 13)}
        meta["valueRanges"] = ({c: {"min": float(np.nanmin(vals[c])), "max": float(np.nanmax(vals[c]))}
                               for c in VALUE_COLUMNS} if name == OUT_MONTHLY else
                              {c: {"min": float(np.nanmin(tbl[c].to_numpy())),
                                   "max": float(np.nanmax(tbl[c].to_numpy()))}
                               for c in ("wind_speed_mean",)})
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


def cmd_check() -> int:
    import h3

    fails = 0
    cells_tbl = pq.read_table(DERIVED / f"cells-r{RES}.parquet")
    cells = cells_tbl.column("h3").to_pylist()
    m_tbl = pq.read_table(DERIVED / f"{OUT_MONTHLY}.parquet")
    a_tbl = pq.read_table(DERIVED / f"{OUT}.parquet")
    meta = json.loads((DERIVED / f"{OUT_MONTHLY}.meta.json").read_text())

    print("[1] exact master key domain")
    want = set(cells)
    m_h3 = m_tbl.column("h3").to_pylist()
    a_h3 = a_tbl.column("h3").to_pylist()
    ok = (m_tbl.num_rows == 1_101_600 and a_tbl.num_rows == 91_800
          and set(m_h3) == want and set(a_h3) == want
          and len(set(a_h3)) == 91_800
          and not validate_keys(m_tbl, cells))
    in_months = sorted((e["datasetId"], e["month"]) for e in meta["inputs"])
    ok &= in_months == sorted((d, m) for d in (DATASET_FLX, DATASET_SLV) for m in MONTHS)
    for d in (DATASET_FLX, DATASET_SLV):
        for e in sorted((x for x in meta["inputs"] if x["datasetId"] == d), key=lambda x: x["month"]):
            print(f"    {d} month {e['month']:2d}  {e['sha256'][:16]}  {e['localPath'].split('/')[-1]}  "
                  f"fill {e['fillCells']}")
    print(f"    {'PASS' if ok else 'FAIL'}")
    fails += not ok

    print("[2] monthly -> annual aggregation consistency (mean of monthly means)")
    sv = m_tbl.column("wind_speed").to_numpy().reshape(len(cells), 12)
    m_m = m_tbl.column("month").to_numpy().reshape(len(cells), 12)
    month_ok = (m_m[:, 0] == 1).all() and (m_m[:, -1] == 12).all()
    ann = annual_from_monthly(sv)
    am = a_tbl.column("wind_speed_mean").to_numpy()
    mism = int((~(np.isnan(am) & np.isnan(ann["wind_speed_mean"]))
                & ~(am == ann["wind_speed_mean"])).sum())
    mu = a_tbl.column("months_used").to_numpy()
    mu_mism = int((mu != ann["months_used"]).sum())
    print(f"    month order ok {month_ok}; mean mismatches {mism}; months_used mismatches {mu_mism}")
    ok = month_ok and mism == 0 and mu_mism == 0
    print(f"    {'PASS' if ok else 'FAIL'}")
    fails += not ok

    print("[3] missing_reason names exactly the null value columns")
    bad = 0
    for mr, *cvals in zip(m_tbl.column("missing_reason").to_pylist(),
                          *(m_tbl.column(c).to_pylist() for c in VALUE_COLUMNS)):
        r = json.loads(mr)
        nulls = {c for c, v in zip(VALUE_COLUMNS, cvals) if v is None}
        if set(r) != nulls or any(v != "merra2-cell-fill" for v in r.values()):
            bad += 1
    bada = 0
    for mr, u in zip(a_tbl.column("missing_reason").to_pylist(), a_tbl.column("months_used").to_pylist()):
        r = json.loads(mr)
        if u == 0 and r != {"wind_speed_mean": "merra2-no-valid-month"}:
            bada += 1
        if u != 0 and r != {}:
            bada += 1
    codes = {}
    for mr in m_tbl.column("missing_reason").to_pylist():
        for k, v in json.loads(mr).items():
            codes[f"{k}:{v}"] = codes.get(f"{k}:{v}", 0) + 1
    print(f"    monthly mismatches {bad}, annual mismatches {bada}; reason codes {codes or 'none (no null rows)'}")
    ok = bad == bada == 0
    print(f"    {'PASS' if ok else 'FAIL'}")
    fails += not ok

    print("[4] value ranges physically plausible + speed-field sanity (Jensen)")
    ws = m_tbl.column("wind_speed").to_numpy()
    wsm = m_tbl.column("wind_speed_max").to_numpy()
    u = m_tbl.column("u10m_mean").to_numpy()
    v = m_tbl.column("v10m_mean").to_numpy()
    rng_ok = (np.nanmin(ws) >= SPEED_PLAUSIBLE[0] and np.nanmax(ws) <= SPEED_PLAUSIBLE[1]
              and np.nanmin(wsm) >= GUST_PLAUSIBLE[0] and np.nanmax(wsm) <= GUST_PLAUSIBLE[1]
              and np.nanmin(u) >= COMPONENT_PLAUSIBLE[0] and np.nanmax(u) <= COMPONENT_PLAUSIBLE[1]
              and np.nanmin(v) >= COMPONENT_PLAUSIBLE[0] and np.nanmax(v) <= COMPONENT_PLAUSIBLE[1])
    print(f"    wind_speed [{np.nanmin(ws):.4f}, {np.nanmax(ws):.4f}] in {SPEED_PLAUSIBLE}  "
          f"wind_speed_max [{np.nanmin(wsm):.4f}, {np.nanmax(wsm):.4f}] in {GUST_PLAUSIBLE}")
    print(f"    u10m_mean [{np.nanmin(u):.4f}, {np.nanmax(u):.4f}], v10m_mean [{np.nanmin(v):.4f}, "
          f"{np.nanmax(v):.4f}] in {COMPONENT_PLAUSIBLE}")
    # The mean of speeds must dominate the magnitude of the mean vector (Jensen);
    # it holds because wind_speed really is the mean of hourly speeds over the
    # same month the components were averaged over.
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        vec = np.hypot(u, v)
        viol = int(((ws < vec - 1e-6) & np.isfinite(ws) & np.isfinite(vec)).sum())
        spd_from_vec = float(np.nanmax(np.abs(ws - vec)))
    print(f"    cells with wind_speed < |mean vector| (should be impossible for a true speed "
          f"field): {viol}; max |wind_speed - |mean vector|| {spd_from_vec:.4f} m/s (positive = speed "
          f"field above the biased lower bound)")
    ok = rng_ok and viol == 0
    print(f"    {'PASS' if ok else 'FAIL'}")
    fails += not ok

    print("[5] spot checks against the raw granules (five sites)")
    a_pos = {h: i for i, h in enumerate(a_h3)}
    cache = {}
    gran_flx = granules(DATASET_FLX)
    gran_slv = granules(DATASET_SLV)
    glat = glon = None
    spot_ok = True
    for name, (la, lo) in SPOTS.items():
        c = h3.latlng_to_cell(la, lo, RES)
        row = a_pos.get(c)
        if row is None:
            print(f"    {name}: {la},{lo} -> {c} NOT A LAND CELL")
            spot_ok = False
            continue
        if glat is None:
            g0 = verify_and_read(gran_flx[1])
            glat, glon = g0["lat"], g0["lon"]
            cache[DATASET_FLX, 1] = g0["fields"]
        hla = cells_tbl.column("lat")[row].as_py()
        hlo = cells_tbl.column("lon")[row].as_py()
        ii, jj = (int(x[0]) for x in nearest_ij([hla], [hlo], glat, glon))
        print(f"    {name} ({la},{lo}) {c}")
        print(f"      hex center lat {hla:.4f} lon {hlo:.4f} -> native center lat {glat[ii]:.3f} "
              f"lon {glon[jj]:.3f} (idx lat {ii}, lon {jj})")
        # all four January columns recomputed straight from the raw granules
        gs = verify_and_read(gran_slv[1]) if (DATASET_SLV, 1) not in cache else None
        if gs is not None:
            cache[DATASET_SLV, 1] = gs["fields"]
        f_flx = cache[DATASET_FLX, 1]
        f_slv = cache[DATASET_SLV, 1]
        raw = {"wind_speed": f_flx["SPEED"][ii, jj], "wind_speed_max": f_flx["SPEEDMAX"][ii, jj],
               "u10m_mean": f_slv["U10M"][ii, jj], "v10m_mean": f_slv["V10M"][ii, jj]}
        row_off = row * 12
        got = {c0: m_tbl.column(c0)[row_off].as_py() for c0 in VALUE_COLUMNS}
        for c0 in VALUE_COLUMNS:
            r0, g0v = raw[c0], got[c0]
            match = (r0 == g0v) or (np.isnan(r0) and g0v is None)
            if not match:
                spot_ok = False
            print(f"      Jan {c0:15s} raw {r0:9.4f} vs parquet {str(g0v):>9s} "
                  f"{'MATCH' if match else 'MISMATCH'}")
    print(f"    {'PASS' if spot_ok else 'FAIL'}")
    fails += not spot_ok

    print("[6] null summary")
    for c0 in VALUE_COLUMNS:
        n_null = m_tbl.column(c0).null_count
        print(f"    {c0:15s} nulls {n_null} of {m_tbl.num_rows} ({n_null / m_tbl.num_rows:.4%})")
    print(f"    months_used histogram "
          f"{ {str(k): int((a_tbl.column('months_used').to_numpy() == k).sum()) for k in range(0, 13)} }")
    info_ok = (sum(m_tbl.column(c0).null_count for c0 in VALUE_COLUMNS) == 0
               or bool(codes))  # reasons above only when nulls exist
    print(f"    {'PASS' if info_ok else 'FAIL'} (informational)")
    print("ALL PASS" if fails == 0 else f"{fails} CHECK(S) FAILED")
    return 0 if fails == 0 else 1


def main() -> int:
    if len(sys.argv) != 2 or sys.argv[1] not in ("fetch", "build", "check"):
        print("usage: python -m p0ingest.wind fetch|build|check")
        return 2
    return {"fetch": cmd_fetch, "build": cmd_build, "check": cmd_check}[sys.argv[1]]()


if __name__ == "__main__":
    sys.exit(main())
