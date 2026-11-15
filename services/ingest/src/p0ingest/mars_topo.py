"""Prepare source-native Mars topography and slopes (issue #103, W44).

Datasets: MGS MOLA MEGDR median topography (4/16/32 ppd), the MGS MOLA / MEX
HRSC blended DEM (200 m, USGS Astrogeology), and the USGS Astrogeology STAC
MRO CTX and HiRISE controlled DTMs. Every product is a static elevation
surface (no time series, so the "at most monthly" time-resolution rule holds).

Source-native only: no resampling to H3 or any other grid, no scoring, no
cross-body comparison. Slopes are central finite differences between two
pixel centres separated by a stated even span. Every kept value's baseline is
a table column and must sit inside its feature band (slope_2_5km: 2-5 km,
slope_200_500m: 200-500 m, slope_20_40m: 20-40 m, slope_5m: 2-5 m; a value
only 0-5% outside the upper band edge is kept but flagged in the report).
The east-west baseline shrinks with latitude, so polar rows stay missing with
an explicit reason. elev_areoid stays a permanent Earth limitation; Mars
topography is natively relative to the areoid (MEGDR: planetary radius minus
GMM3 deg-50 areoid), as published.

Landing-site DTMs are downloaded only at the six named sites: Jezero, Gale,
Elysium/InSight, Utopia/Zhurong, Meridiani, Gusev. relief_ellipse uses a
radius parameter (radius_m column, default 10 km) - the ellipse size is a
parameter, not a fixed value.

Run: python -m p0ingest.mars_topo fetch|build|check
"""
from __future__ import annotations

import argparse
import json
import math
import os
import re
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import polars as pl
import pyarrow.parquet as pq
import rasterio
import requests

from .snapshots import REPO, SNAP, fetch, load_manifest, sha256, catalog_row

OUT = SNAP / "_derived" / "planetary" / "mars_topo"
STAC_API = "https://stac.astrogeology.usgs.gov/api"
MEGDR_BASE = "https://pds-geosciences.wustl.edu/mgs/mgs-m-mola-5-megdr-l3-v1/mgsl_300x"
MEGDR_DATASET = "mola-megdr"
BLENDED_DATASET = "mola-hrsc-blended-dem"
BLENDED_TIF = ("https://planetarymaps.usgs.gov/mosaic/Mars/HRSC_MOLA_Blend/"
               "Mars_HRSC_MOLA_BlendDEM_Global_200mp_v2.tif")
BLENDED_LBL = ("https://astrogeology.usgs.gov/ckan/dataset/6c177b5f-97af-4d70-adc3-92cf362b9890"
               "/resource/9b3025b4-484e-47b1-a782-d88abc387cc1/download/"
               "mars_hrsc_mola_blenddem_global_200mp_v2.lbl")
# Median topography (megt) at 4, 16 and 32 px/deg. The 32 ppd file is the one
# prepared here (1.853 km/px grid); 4/16 ppd are supplementary provenance.
MEGDR_SOURCES = (
    "meg004/megt90n000cb.img", "meg004/megt90n000cb.lbl",
    "meg016/megt90n000eb.img", "meg016/megt90n000eb.lbl",
    "meg032/megt90n000fb.img", "meg032/megt90n000fb.lbl",
)
STAC_DATASETS = ("ctx-dtms-usgs-stac", "hirise-dtms-usgs-stac")
STAC_COLLECTION_ID = {
    "ctx-dtms-usgs-stac": "mro_ctx_controlled_usgs_dtms",
    "hirise-dtms-usgs-stac": "mro_hirise_socet_dtms",
}
STAC_PAGE_LIMIT = 200
STAC_MAX_PAGES = 500

# Named site centres: planetocentric latitude, east longitude 0..360.
SITES = (
    ("jezero-perseverance", 18.4447, 77.4508),
    ("gale-curiosity", -4.5895, 137.4417),
    ("insight-elysium", 4.5024, 135.6234),
    ("zhurong-utopia", 25.0661, 109.9256),
    ("meridiani-opportunity", -1.9462, 354.4734),
    ("gusev-spirit", -14.5684, 175.4785),
)

RELIEF_RADIUS_M = 10_000           # relief_ellipse radius parameter (not a fixed ellipse)
SLOPE_2_5KM_RADIUS_M = 10_000      # site max slope_2_5km search radius
STATS_RADIUS_M = {"ctx-dtms-usgs-stac": 1_000, "hirise-dtms-usgs-stac": 500}
PIXEL_RADIUS_M = 200               # native-pixel subset per site
BLOCK_PX = 32                      # blended DEM: 32x32 native pixels = 3.2 km blocks
BLENDED_WIN_LINES = 256            # blended processing window lines (RAM < 2 GB)
MEGDR_BATCH_LINES = 96
MOLA_DTM_TOLERANCE_M = 400.0       # MEGDR vs controlled DTM consistency (both MOLA-based)

# Per-feature baseline bands, metres (research/features/landing_site_features.csv).
BAND_OF = {
    "slope_2_5km": (2_000.0, 5_000.0),
    "slope_200_500m": (200.0, 500.0),
    "slope_20_40m": (20.0, 40.0),
    "slope_5m": (2.0, 5.0),
}

R_MEGDR = 3_396_000.0    # MEGDR IAU2000 spherical radius, metres
R_BLENDED = 3_396_190.0  # blended DEM label sphere radius, metres
TOPO_RANGE = (-8_206.0, 21_181.0)  # MEGDR 32 ppd label: published topography min/max, metres


def reason_series(cat: np.ndarray, mapping: list) -> pl.Series:
    """Utf8 Series from integer categories; mapping[i] is the JSON reason for
    category i (None for valid rows). Keeps nulls for None entries."""
    return pl.Series(cat.astype(np.int64)).replace_strict(
        list(range(len(mapping))), mapping, return_dtype=pl.Utf8)


def json_reason(columns: dict) -> str | None:
    """JSON object whose keys are exactly the null value columns of a row."""
    return json.dumps(dict(sorted(columns.items()))) if columns else None


def sources():
    for stem in MEGDR_SOURCES:
        yield MEGDR_DATASET, f"{MEGDR_BASE}/{stem}"
    yield BLENDED_DATASET, BLENDED_TIF
    yield BLENDED_DATASET, BLENDED_LBL


def source_urls() -> list[str]:
    return [url for _, url in sources()]


def stac_page_url(dataset_id: str, page: int, limit: int = STAC_PAGE_LIMIT,
                  bbox: tuple | None = None) -> str:
    url = (f"{STAC_API}/search?collections={STAC_COLLECTION_ID[dataset_id]}"
           f"&limit={limit}&page={page}")
    if bbox is not None:
        url += "&bbox=" + ",".join(f"{v:.2f}" for v in bbox)
    return url


def verify_manifest_inputs(urls, entries=None) -> list[dict]:
    entries = {e["sourceUrl"]: e for e in load_manifest()["entries"]}
    checked = []
    for url in urls:
        entry = entries.get(url)
        if entry is None or not entry.get("licenseVerified"):
            raise ValueError(f"missing licensed snapshot: {url}")
        path = REPO / entry["localPath"]
        if path.stat().st_size != entry["bytes"] or sha256(path) != entry["sha256"]:
            raise ValueError(f"input hash/size mismatch: {path}")
        checked.append(entry)
    return checked


def central_difference_slope(z, span_px, gsd_ns_m, gsd_ew_m, wrap_lon):
    """Slope in degrees between pixel centres span_px apart in each direction
    (span_px even >= 2; samples at +/- span_px//2 rows/cols; baseline =
    span_px * gsd). z is 2-D float with NaN where invalid; gsd_ew_m is the
    per-row east-west metres-per-pixel; wrap_lon joins map edges (global
    grids). Returns (slope_deg float32, ok_mask); ok is False at NaN pixels,
    unusable neighbours, or non-wrapped edges."""
    if span_px < 2 or span_px % 2:
        raise ValueError("span_px must be even and >= 2")
    half = span_px // 2
    rows, cols = z.shape
    gsd_ew = np.asarray(gsd_ew_m, dtype=np.float64)
    if gsd_ew.ndim == 0:
        gsd_ew = np.full(rows, float(gsd_ew))[:, None]      # per-row
        gsd_ew_grid = False
    elif gsd_ew.ndim == 1:
        if gsd_ew.shape != (rows,):
            raise ValueError("gsd_ew_m per-row shape mismatch")
        gsd_ew = gsd_ew[:, None]
        gsd_ew_grid = False
    elif gsd_ew.shape != z.shape:
        raise ValueError("gsd_ew_m must be scalar, per-row or z-shaped")
    else:
        gsd_ew_grid = True
    dz_ns = np.full(z.shape, np.nan, dtype=np.float32)
    dz_ew = np.full(z.shape, np.nan, dtype=np.float32)
    if rows > span_px:
        dz_ns[half:rows - half, :] = (z[span_px:, :] - z[:-span_px, :]) / (span_px * gsd_ns_m)
    if cols > span_px:
        if wrap_lon:
            dzdiff = np.roll(z, -half, axis=1) - np.roll(z, half, axis=1)
            dz_ew[:, :] = dzdiff / (span_px * gsd_ew)
        else:
            dzdiff = z[:, span_px:] - z[:, :-span_px]
            g_ew = (gsd_ew[:, half:cols - half]    # per-pixel grid: slice
                    if gsd_ew_grid else gsd_ew)    # scalar / per-row: broadcast
            dz_ew[:, half:cols - half] = dzdiff / (span_px * g_ew)
    with np.errstate(invalid="ignore"):
        slope = np.degrees(np.arctan(np.sqrt(dz_ns ** 2 + dz_ew ** 2))).astype(np.float32)
    ok = np.isfinite(slope) & np.isfinite(z)
    return slope, ok


def site_row_null(site, collection, reason, baseline=None, *,
                  feature=None, stat=None, radius=None, item_id=None):
    return {"site": site, "collection": collection, "item_id": item_id, "feature": feature,
            "stat": stat, "value": None, "gsd_m": None, "baseline_m": baseline,
            "radius_m": radius, "support_px": None, "note": None,
            "missing_reason": json_reason({"value": reason})}


# --------------------------------------------------------------------------- #
# MEGDR 32 ppd: global elevation + slope_2_5km table
# --------------------------------------------------------------------------- #

def read_megdr_label(path: Path) -> dict:
    text = path.read_text(errors="replace")
    total = re.search(r"are\s+([-\d.]+)\s+and\s+([\d.]+) meters", text)
    def one(key):
        found = re.search(rf"^\s*{key}\s*=\s*(.+?)\s*$", text, re.M)
        if not found:
            raise ValueError(f"missing MEGDR label field {key}")
        return found.group(1).split("<")[0].strip().strip('"')
    return {
        "data_set_id": one("DATA_SET_ID"),
        "product_id": one("PRODUCT_ID"),
        "image_name": one("NAME"),
        "lines": int(one("LINES")),
        "line_samples": int(one("LINE_SAMPLES")),
        "sample_type": one("SAMPLE_TYPE"),
        "sample_bits": int(one("SAMPLE_BITS")),
        "unit": one("UNIT"),
        "map_resolution_ppd": float(one("MAP_RESOLUTION")),
        "map_scale_km": float(one("MAP_SCALE")),
        "sphere_radius_m": 1000.0 * float(one("A_AXIS_RADIUS")),
        "published_topo_range_m": (float(total.group(1)), float(total.group(2))) if total else None,
    }


def megdr32_paths() -> tuple[Path, Path]:
    return (SNAP / MEGDR_DATASET / "megt90n000fb.img",
            SNAP / MEGDR_DATASET / "megt90n000fb.lbl")


def megdr32_elevation_table(out_path: Path, report: dict,
                            progress=lambda m: None) -> dict:
    """Global 32 ppd median topography: one row per native pixel
    (5760 x 11520). elevation_m is metres relative to the GMM3 areoid, as
    published. slope_2_5km is the central finite difference over a span of
    2 pixels (3704.9 m north-south baseline); kept only where both the
    north-south and east-west baselines sit inside the 2-5 km band."""
    img_path, label_path = megdr32_paths()
    fetch(MEGDR_DATASET, f"{MEGDR_BASE}/meg032/megt90n000fb.img")
    fetch(MEGDR_DATASET, f"{MEGDR_BASE}/meg032/megt90n000fb.lbl")
    label = read_megdr_label(label_path)
    if label["data_set_id"] != "MGS-M-MOLA-5-MEGDR-L3-V1.0" \
            or label["product_id"] != "MEGT90N000FB.IMG" \
            or label["image_name"] != "MEDIAN_TOPOGRAPHY" \
            or (label["lines"], label["line_samples"]) != (5760, 11520) \
            or label["sample_type"] != "MSB_INTEGER" or label["sample_bits"] != 16 \
            or label["map_resolution_ppd"] != 32.0 or label["unit"] != "METER":
        raise ValueError(f"MEGDR 32 ppd layout changed: {label}")
    grid = np.memmap(img_path, dtype=">i2", mode="r",
                     shape=(label["lines"], label["line_samples"]))
    ppd = label["map_resolution_ppd"]
    gsd_ns = (math.pi / 180.0) * R_MEGDR / ppd
    span_px = 2
    baseline_ns = span_px * gsd_ns
    lo, hi = BAND_OF["slope_2_5km"]
    report["megdr32"] = {
        "product": label["product_id"], "ppd": ppd,
        "gridLinesSamples": [label["lines"], label["line_samples"]],
        "elevationMeaning": "metres relative to the GMM3 degree-50 areoid, as published",
        "slopeMethod": ("central finite difference between pixel centres 2 px apart per "
                        "direction; slope = arctan(sqrt((dz_ns/baseline_ns)^2 + "
                        "(dz_ew/baseline_ew)^2)); pixels with an unusable neighbour stay missing"),
        "slope_2_5kmBaseline_ns_m": round(baseline_ns, 2),
        "slope_2_5kmBaseline_ew_m": f"{span_px} * {round(gsd_ns, 2)} * cos(latitude) m",
        "slope_2_5kmBand_m": [lo, hi],
        "slope_2_5kmKeptOnlyWhere": "east-west baseline inside band, |latitude| <= 57.3 deg",
        "lonLatConvention": "planetocentric, east-positive 0..360, IAU2000 sphere 3396 km; "
                            "pixel centres: latitude 90-(line+0.5)/32, longitude (sample+0.5)/32",
        "publishedTopoRange_m": list(label["published_topo_range_m"])
        if label["published_topo_range_m"] else None,
    }

    lines, samples = label["lines"], label["line_samples"]
    lat_all = 90.0 - (np.arange(lines, dtype=np.float32) + 0.5) / ppd
    lon_all = (np.arange(samples, dtype=np.float32) + 0.5) / ppd
    part = out_path.with_suffix(".part")
    writer = None
    rows_total = 0
    reason_counts = {"valid": 0, "out-of-published-range": 0,
                     "insufficient-neighbours-or-edge": 0, "baseline-outside-2-5km-band": 0}
    elevation_nulls = slope_nulls = 0
    for start in range(0, lines, MEGDR_BATCH_LINES):
        stop = min(start + MEGDR_BATCH_LINES, lines)
        h0, h1 = max(0, start - 1), min(lines, stop + 1)
        raw = np.asarray(grid[h0:h1], dtype=np.float32)
        valid_h = (raw >= TOPO_RANGE[0]) & (raw <= TOPO_RANGE[1])
        z = np.where(valid_h, raw, np.nan)
        lat_rows = 90.0 - (np.arange(h0, h1, dtype=np.float64) + 0.5) / ppd
        ew_m = np.cos(np.radians(lat_rows)) * gsd_ns
        slope_h, ok_h = central_difference_slope(z, span_px=span_px, gsd_ns_m=gsd_ns,
                                                 gsd_ew_m=ew_m, wrap_lon=True)
        i0 = start - h0
        i1 = i0 + (stop - start)
        slope_b, ok_b = slope_h[i0:i1], ok_h[i0:i1]
        raw_b, valid_b = raw[i0:i1], valid_h[i0:i1]
        ew_baseline = ew_m[i0:i1] * span_px
        in_band = ((baseline_ns >= lo) & (baseline_ns <= hi)
                   & (ew_baseline >= lo) & (ew_baseline <= hi))
        keep = ok_b & in_band[:, None]
        cat = np.zeros(raw_b.shape, dtype=np.uint8)       # 0 valid row
        cat[valid_b & ~ok_b] = 2                          # slope needs a missing neighbour
        cat[valid_b & ok_b & ~in_band[:, None]] = 3       # baseline outside band
        cat[~valid_b] = 1                                 # elevation outside published range
        reason = reason_series(cat.ravel(), [
            None, json_reason({"elevation_m": "outside-published-topography-range",
                               "slope_2_5km": "no-valid-source-elevation"}),
            json_reason({"slope_2_5km": "insufficient-neighbours-or-edge"}),
            json_reason({"slope_2_5km": "baseline-outside-2-5km-band"})])
        frame = pl.DataFrame({
            "source_line": np.repeat(np.arange(start, stop, dtype=np.uint16), samples),
            "source_sample": np.tile(np.arange(samples, dtype=np.uint16), stop - start),
            "latitude": np.repeat(lat_all[start:stop], samples),
            "longitude": np.tile(lon_all, stop - start),
            "elevation_m": np.where(valid_b, raw_b, np.nan).astype(np.float32).ravel(),
            "slope_2_5km": np.where(keep, slope_b, np.nan).astype(np.float32).ravel(),
            "missing_reason": reason,
        }).with_columns(pl.col(pl.Float32).fill_nan(None))
        table = frame.to_arrow()
        if writer is None:
            writer = pq.ParquetWriter(part, table.schema, compression="zstd")
        writer.write_table(table)
        rows_total += frame.height
        reason_counts["valid"] += int((cat == 0).sum())
        reason_counts["out-of-published-range"] += int((cat == 1).sum())
        reason_counts["insufficient-neighbours-or-edge"] += int((cat == 2).sum())
        reason_counts["baseline-outside-2-5km-band"] += int((cat == 3).sum())
        elevation_nulls += int((cat == 1).sum())
        slope_nulls += int((cat != 0).sum())
        progress(f"megdr lines {stop}/{lines}")
    if writer is None:
        raise ValueError("MEGDR produced zero rows")
    writer.close()
    os.replace(part, out_path)
    return {"rows": rows_total,
            "nullCounts": {"elevation_m": elevation_nulls, "slope_2_5km": slope_nulls},
            "reasonCounts": reason_counts,
            "sha256": sha256(out_path), "bytes": out_path.stat().st_size,
            "quality": "only the label-published topography range applied; gaps between MOLA "
                       "profiles are interpolated by the source itself (label DESCRIPTION), a "
                       "product property recorded here, not a derived mask"}


def megdr32_latlon_to_pixel(lat: float, lon: float, ppd: float = 32.0) -> tuple[int, int]:
    """Nearest pixel centre: latitude 90-(line+0.5)/ppd, longitude (sample+0.5)/ppd."""
    line = int(round((90.0 - lat) * ppd - 0.5))
    sample = int(round((lon % 360.0) * ppd - 0.5))
    return line, sample


def megdr32_site_stats(slope_path: Path, report: dict) -> list[dict]:
    """relief_ellipse (radius parameter) and max slope_2_5km beside each named
    site: from the 32 ppd raw grid and the slope column of the global table."""
    img_path, label_path = megdr32_paths()
    label = read_megdr_label(label_path)
    grid = np.memmap(img_path, dtype=">i2", mode="r",
                     shape=(label["lines"], label["line_samples"]))
    ppd = label["map_resolution_ppd"]
    gsd_ns = (math.pi / 180.0) * R_MEGDR / ppd
    slope_frame = pl.scan_parquet(slope_path).select("latitude", "longitude", "slope_2_5km")
    rows = []
    for site, lat0, lon0 in SITES:
        half_win = int(math.ceil(RELIEF_RADIUS_M / gsd_ns)) + 4
        centre_line = (90.0 - lat0) * ppd - 0.5
        centre_sample = lon0 * ppd - 0.5
        line_idx = [l for l in range(int(centre_line) - half_win, int(centre_line) + half_win + 1)
                    if 0 <= l < label["lines"]]
        samp_idx = np.arange(int(centre_sample) - half_win,
                             int(centre_sample) + half_win + 1) % label["line_samples"]
        window = np.asarray(grid[np.ix_(line_idx, samp_idx)], dtype=np.float64)
        latv = np.array([90.0 - (l + 0.5) / ppd for l in line_idx])
        lonv = ((samp_idx.astype(np.float64) + 0.5) / ppd) % 360.0
        dist = np.sqrt(
            ((latv[:, None] - lat0) * (math.pi / 180.0) * R_MEGDR) ** 2
            + ((((lonv[None, :] - lon0 + 180.0) % 360.0) - 180.0) * (math.pi / 180.0) * R_MEGDR
                * np.cos(np.radians((latv[:, None] + lat0) / 2.0))) ** 2)
        inside = (dist <= RELIEF_RADIUS_M) & (window >= TOPO_RANGE[0]) & (window <= TOPO_RANGE[1])
        param_note = "ellipse size is a parameter (radius_m), not a fixed value"
        if inside.any():
            elev = window[inside]
            rows.append({"site": site, "collection": MEGDR_DATASET,
                         "item_id": label["product_id"], "feature": "relief_ellipse",
                         "stat": "relief_max_min", "value": float(elev.max() - elev.min()),
                         "gsd_m": round(gsd_ns, 1), "baseline_m": None,
                         "radius_m": RELIEF_RADIUS_M, "support_px": int(inside.sum()),
                         "note": param_note, "missing_reason": None})
        else:
            rows.append({"site": site, "collection": MEGDR_DATASET,
                         "item_id": label["product_id"], "feature": "relief_ellipse",
                         "stat": "relief_max_min", "value": None, "gsd_m": round(gsd_ns, 1),
                         "baseline_m": None, "radius_m": RELIEF_RADIUS_M, "support_px": 0,
                         "note": param_note,
                         "missing_reason": json_reason(
                             {"value": "no-valid-megdr-pixels-in-radius"})})
        lat_half = (RELIEF_RADIUS_M * math.cos(math.radians(lat0)) + 2000.0) \
            / ((math.pi / 180.0) * R_MEGDR)
        lon_half = (RELIEF_RADIUS_M + 2000.0) \
            / ((math.pi / 180.0) * R_MEGDR * math.cos(math.radians(lat0)))
        sub = slope_frame.filter(
            (pl.col("latitude") >= lat0 - lat_half) & (pl.col("latitude") <= lat0 + lat_half)
            & (pl.col("longitude") >= (lon0 - lon_half) % 360.0)
            & (pl.col("longitude") <= (lon0 + lon_half) % 360.0)
            & pl.col("slope_2_5km").is_not_null()).collect()
        sub = sub.with_columns(
            (((pl.col("latitude") - lat0) * (math.pi / 180.0) * R_MEGDR) ** 2
             + ((((pl.col("longitude") - lon0 + 180.0) % 360.0) - 180.0)
                * (math.pi / 180.0) * R_MEGDR * math.cos(math.radians(lat0))) ** 2
             ).alias("d2")).filter(pl.col("d2") <= SLOPE_2_5KM_RADIUS_M ** 2)
        if sub.height:
            rows.append({"site": site, "collection": MEGDR_DATASET,
                         "item_id": label["product_id"], "feature": "slope_2_5km",
                         "stat": "max_within_radius",
                         "value": float(sub["slope_2_5km"].max()),
                         "gsd_m": round(gsd_ns, 1), "baseline_m": round(2 * gsd_ns, 1),
                         "radius_m": SLOPE_2_5KM_RADIUS_M, "support_px": sub.height,
                         "note": "max slope among in-band MEGDR 32 ppd pixels inside radius_m",
                         "missing_reason": None})
        else:
            rows.append({"site": site, "collection": MEGDR_DATASET,
                         "item_id": label["product_id"], "feature": "slope_2_5km",
                         "stat": "max_within_radius", "value": None, "gsd_m": round(gsd_ns, 1),
                         "baseline_m": round(2 * gsd_ns, 1), "radius_m": SLOPE_2_5KM_RADIUS_M,
                         "support_px": 0,
                         "note": "no MEGDR pixel inside the radius has an in-band slope",
                         "missing_reason": json_reason(
                             {"value": "no-in-band-megdr-slope-in-radius"})})
    return rows


# --------------------------------------------------------------------------- #
# blended DEM 200 m: block aggregates + site pixel subsets
# --------------------------------------------------------------------------- #

def read_blended_label(path: Path) -> dict:
    text = path.read_text(errors="replace")
    def grab(pattern, cast):
        found = re.search(pattern, text)
        if not found:
            raise ValueError(f"blended label missing {pattern}")
        return cast(found.group(1))
    return {
        "lines": grab(r"Lines\s*=\s*(\d+)", int),
        "samples": grab(r"Samples\s*=\s*(\d+)", int),
        "pixel_type": grab(r"Type\s*=\s*(\S+)", str),
        "pixel_resolution_m": grab(r"PixelResolution\s*=\s*([\d.]+)", float),
        "sphere_radius_m": grab(r"EquatorialRadius\s*=\s*([\d.]+)", float),
        "latitude_type": grab(r"LatitudeType\s*=\s*(\S+)", str),
        "lon_direction": grab(r"LongitudeDirection\s*=\s*(\S+)", str),
        "min_lon": grab(r"MinimumLongitude\s*=\s*(-?[\d.]+)", float),
        "max_lon": grab(r"MaximumLongitude\s*=\s*([\d.]+)", float),
        "min_lat": grab(r"MinimumLatitude\s*=\s*(-?[\d.]+)", float),
        "max_lat": grab(r"MaximumLatitude\s*=\s*([\d.]+)", float),
        "projection": grab(r"ProjectionName\s*=\s*(\S+)", str),
    }


def blended_px_to_latlon(label: dict, line, sample, lon_offset: float = 0.0):
    """Pixel-centre planetocentric lat / east-positive lon (0..360) from the
    label mapping equations."""
    deg_lat = (label["max_lat"] - label["min_lat"]) / label["lines"]
    deg_lon = (label["max_lon"] - label["min_lon"]) / label["samples"]
    lat = label["max_lat"] - (np.asarray(line, dtype=np.float64) + 0.5) * deg_lat
    lon = (np.asarray(sample, dtype=np.float64) + 0.5) * deg_lon + label["min_lon"]
    lon = (lon + lon_offset) % 360.0
    return lat, lon


def blended_latlon_to_px(label: dict, lat: float, lon_e: float) -> tuple[float, float]:
    """lon_e is east-positive 0..360; the label frame is -180..180."""
    deg_lat = (label["max_lat"] - label["min_lat"]) / label["lines"]
    deg_lon = (label["max_lon"] - label["min_lon"]) / label["samples"]
    lon_frame = normalise_lon_e(lon_e)
    line = (label["max_lat"] - lat) / deg_lat - 0.5
    sample = (lon_frame - label["min_lon"]) / deg_lon - 0.5
    return line, sample


def blended_tables(out_blocks: Path, out_pixels: Path, report: dict,
                   progress=lambda m: None) -> dict:
    """Two outputs from the blended 200 m DEM in one streamed pass:
    - a coarse stated-resolution global table: slope_200_500m aggregated over
      BLOCK_PX x BLOCK_PX native pixels (3.2 km blocks; mean + the native
      pixel support count; values aggregated, not resampled);
    - native 200 m pixel subsets within PIXEL_RADIUS_M of each site centre."""
    lbl_path = Path(fetch(BLENDED_DATASET, BLENDED_LBL))
    tif_path = Path(fetch(BLENDED_DATASET, BLENDED_TIF))
    label = read_blended_label(lbl_path)
    if label["pixel_type"] != "SignedWord" or label["projection"] != "SimpleCylindrical" \
            or (label["lines"], label["samples"]) != (53347, 106694) \
            or abs(label["pixel_resolution_m"] - 200.0) > 1.0 \
            or label["latitude_type"] != "Planetocentric" \
            or abs(label["min_lon"] - (-180.0)) > 0.01 or abs(label["max_lon"] - 180.0) > 0.01 \
            or abs(label["max_lat"] - 90.0) > 0.01:
        raise ValueError(f"blended DEM layout changed: {label}")
    px_m = label["pixel_resolution_m"]
    deg_lat = (label["max_lat"] - label["min_lat"]) / label["lines"]
    deg_lon = (label["max_lon"] - label["min_lon"]) / label["samples"]
    ew_px_m = deg_lon * (math.pi / 180.0) * label["sphere_radius_m"]
    span_px = 2
    baseline_ns = span_px * px_m
    lo, hi = BAND_OF["slope_200_500m"]

    n_br = math.ceil(label["lines"] / BLOCK_PX)
    n_bc = math.ceil(label["samples"] / BLOCK_PX)
    n_blocks = n_br * n_bc
    sum_slope = np.zeros(n_blocks, dtype=np.float64)
    cnt = np.zeros(n_blocks, dtype=np.int64)

    with rasterio.open(tif_path) as src:
        if (src.height, src.width) != (label["lines"], label["samples"]):
            raise ValueError("blended DEM raster size differs from label")
        report["blended"] = {
            "product": tif_path.name, "px_m": px_m,
            "gridLinesSamples": [label["lines"], label["samples"]],
            "lonRangeDeg": [label["min_lon"], label["max_lon"]],
            "latRangeDeg": [label["min_lat"], label["max_lat"]],
            "rasterNodata": src.nodata,
            "slopeMethod": ("central finite difference between pixel centres 2 px apart per "
                            "direction (400.0 m north-south baseline; east-west "
                            "400.0*cos(lat) m); block mean over 32x32 native pixels, support "
                            "= native pixels used"),
            "band_m": [lo, hi],
            "bandKeptOnlyWhere": "east-west baseline inside band: |latitude| <= 60 deg",
        }
        nodata = src.nodata if src.nodata is not None else -32768.0
        win = BLENDED_WIN_LINES
        for w0 in range(0, src.height, win):
            r0, r1 = max(0, w0 - 1), min(src.height, w0 + win + 1)
            if r1 - r0 < 3:
                break
            data = src.read(1, window=rasterio.windows.Window(0, r0, src.width, r1 - r0))
            z = data.astype(np.float32)
            valid = np.isfinite(z) & (z != nodata) & (z >= TOPO_RANGE[0]) & (z <= TOPO_RANGE[1])
            z = np.where(valid, z, np.nan)
            lat_rows = label["max_lat"] - (r0 + np.arange(r1 - r0, dtype=np.float64) + 0.5) * deg_lat
            gsd_ew = np.cos(np.radians(lat_rows)) * ew_px_m
            slope, ok = central_difference_slope(z, span_px=span_px, gsd_ns_m=px_m,
                                                 gsd_ew_m=gsd_ew, wrap_lon=True)
            i0 = 1 if r0 > 0 else 0                 # skip the halo row when present
            i1 = (r1 - r0) - 1 if r1 < src.height else (r1 - r0)
            slope_i, ok_i = slope[i0:i1], ok[i0:i1]
            if not ok_i.any():
                progress(f"blended rows {min(w0 + win, src.height)}/{src.height}")
                continue
            rows_px = np.arange(r0 + i0, r0 + i1, dtype=np.int64)
            block_ids = ((rows_px // BLOCK_PX)[:, None] * n_bc
                         + (np.arange(src.width, dtype=np.int64) // BLOCK_PX)[None, :])
            flat = block_ids.ravel()[ok_i.ravel()]
            sum_slope += np.bincount(flat, weights=slope_i.astype(np.float64).ravel()[ok_i.ravel()],
                                     minlength=n_blocks)
            cnt += np.bincount(flat, minlength=n_blocks).astype(np.int64)
            progress(f"blended rows {min(w0 + win, src.height)}/{src.height}")

    has = cnt > 0
    block_ids = np.arange(n_blocks)
    br, bc = block_ids // n_bc, block_ids % n_bc
    line_first = br.astype(np.int64) * BLOCK_PX
    samp_first = bc.astype(np.int64) * BLOCK_PX
    lat_c, lon_c = blended_px_to_latlon(
        label,
        line_first + np.minimum(BLOCK_PX, label["lines"] - line_first) / 2.0 - 0.5,
        samp_first + np.minimum(BLOCK_PX, label["samples"] - samp_first) / 2.0 - 0.5)
    ew_baseline = np.cos(np.radians(lat_c)) * span_px * ew_px_m
    in_band = has & (baseline_ns >= lo) & (baseline_ns <= hi) & (ew_baseline >= lo) & (ew_baseline <= hi)
    mean = np.where(in_band, sum_slope / np.maximum(cnt, 1), np.nan)
    cat = (~has).astype(np.int64) + 2 * ((has & ~in_band).astype(np.int64))
    reason = reason_series(cat, [
        None, json_reason({"slope_200_500m_mean": "no-valid-native-pixels-in-block"}),
        json_reason({"slope_200_500m_mean": "baseline-outside-200-500m-band"})])
    frame = pl.DataFrame({
        "block_line": br.astype(np.uint16), "block_sample": bc.astype(np.uint16),
        "latitude": lat_c.astype(np.float32), "longitude": lon_c.astype(np.float32),
        "slope_200_500m_mean": mean.astype(np.float32),
        "support_px": cnt,
        "missing_reason": reason,
    }).with_columns(pl.col(pl.Float32).fill_nan(None))
    part = out_blocks.with_suffix(".part")
    frame.write_parquet(part)
    os.replace(part, out_blocks)
    blocks_result = {"rows": frame.height,
                     "nullCounts": {"slope_200_500m_mean": int((~in_band).sum())},
                     "reasonCounts": {"no-valid-native-pixels-in-block": int((~has).sum()),
                                      "baseline-outside-200-500m-band": int((has & ~in_band).sum()),
                                      "valid": int(in_band.sum())},
                     "blockPx": BLOCK_PX, "blockSizeM": round(BLOCK_PX * px_m, 1),
                     "baseline_ns_m": round(baseline_ns, 2),
                     "meanSupportPx": float(cnt[has].mean()) if has.any() else 0,
                     "maxSupportPx": int(cnt.max()),
                     "sha256": sha256(out_blocks), "bytes": out_blocks.stat().st_size}

    pixel_rows = []
    with rasterio.open(tif_path) as tif:
        for site, lat0, lon0 in SITES:
            line_c, samp_c = blended_latlon_to_px(label, lat0, lon0)
            r_half = int(math.ceil((PIXEL_RADIUS_M + 2 * px_m) / px_m)) + 2
            s_half = int(math.ceil((PIXEL_RADIUS_M + 2 * px_m)
                                   / (px_m * math.cos(math.radians(lat0))))) + 2
            r0 = max(0, int(line_c) - r_half)
            r1 = min(label["lines"], int(line_c) + r_half + 1)
            s0 = max(0, int(samp_c) - s_half)
            s1 = min(label["samples"], int(samp_c) + s_half + 1)
            data = tif.read(1, window=rasterio.windows.Window(s0, r0, s1 - s0, r1 - r0))
            z = data.astype(np.float32)
            valid = np.isfinite(z) & (z != nodata) & (z >= TOPO_RANGE[0]) & (z <= TOPO_RANGE[1])
            z = np.where(valid, z, np.nan)
            lat_rows, lon_cols = blended_px_to_latlon(
                label,
                np.arange(r0, r1)[:, None] + np.zeros((1, s1 - s0)),
                np.zeros((r1 - r0, 1)) + np.arange(s0, s1)[None, :])
            gsd_ew = np.cos(np.radians(lat_rows[:, 0])) * ew_px_m
            slope, ok = central_difference_slope(z, span_px=span_px, gsd_ns_m=px_m,
                                                 gsd_ew_m=gsd_ew, wrap_lon=True)
            dist = np.sqrt(((lat_rows - lat0) * (math.pi / 180.0) * label["sphere_radius_m"]) ** 2
                           + ((((lon_cols - lon0 + 180.0) % 360.0) - 180.0) * (math.pi / 180.0)
                              * label["sphere_radius_m"]
                              * np.cos(np.radians((lat_rows + lat0) / 2.0))) ** 2)
            pick = (dist <= PIXEL_RADIUS_M) & ok
            kept = int(((dist <= PIXEL_RADIUS_M) & np.isfinite(z)).sum())
            lines_px, cols_px = np.nonzero(pick)
            for k in range(len(lines_px)):
                li, si = r0 + int(lines_px[k]), s0 + int(cols_px[k])
                pixel_rows.append({
                    "site": site, "collection": BLENDED_DATASET,
                    "item_id": "Mars_HRSC_MOLA_BlendDEM_Global_200mp_v2",
                    "source_line": li, "source_sample": si,
                    "latitude": float(lat_rows[lines_px[k], cols_px[k]]),
                    "longitude": float(lon_cols[lines_px[k], cols_px[k]]),
                    "feature": "slope_200_500m",
                    "elevation_m": float(z[lines_px[k], cols_px[k]]),
                    "slope_deg": float(slope[lines_px[k], cols_px[k]]),
                    "baseline_m": round(span_px * px_m, 2),
                    "distance_m": float(dist[lines_px[k], cols_px[k]]),
                    "missing_reason": None})
            if kept == 0:
                pixel_rows.append({
                    "site": site, "collection": BLENDED_DATASET,
                    "item_id": "Mars_HRSC_MOLA_BlendDEM_Global_200mp_v2",
                    "source_line": None, "source_sample": None,
                    "latitude": lat0, "longitude": lon0,
                    "feature": "slope_200_500m", "elevation_m": None, "slope_deg": None,
                    "baseline_m": round(span_px * px_m, 2), "distance_m": None,
                    "missing_reason": json_reason(
                        {"elevation_m": "no-valid-blended-pixels-in-site-radius",
                         "slope_deg": "no-valid-blended-pixels-in-site-radius"})})
            progress(f"blended site {site}: {len(lines_px)} px")
    pixel_frame = pl.DataFrame(pixel_rows, schema_overrides={
        "latitude": pl.Float64, "longitude": pl.Float64,
        "elevation_m": pl.Float64, "slope_deg": pl.Float64,
        "baseline_m": pl.Float64, "distance_m": pl.Float64,
        "source_line": pl.Int64, "source_sample": pl.Int64})
    part = out_pixels.with_suffix(".part")
    pixel_frame.write_parquet(part)
    os.replace(part, out_pixels)
    return {"blocks": blocks_result,
            "pixels": {"rows": pixel_frame.height, "sha256": sha256(out_pixels),
                       "bytes": out_pixels.stat().st_size},
            "label": label}


# --------------------------------------------------------------------------- #
# USGS STAC: DTM footprint tables and named-landing-site products
# --------------------------------------------------------------------------- #

def page_json(url: str, retries: int = 10):
    """HTTP GET with exponential backoff (transient DNS / 502 are common)."""
    delay = 5.0
    import time as _time
    for attempt in range(retries):
        try:
            response = requests.get(url, timeout=120)
            response.raise_for_status()
            return response.json()
        except (requests.RequestException, ValueError):
            if attempt == retries - 1:
                raise
            _time.sleep(delay)
            delay = min(delay * 2.5, 120.0)


def load_stac_page(dataset_id: str, page: int, limit: int,
                   bbox: tuple | None = None, progress=lambda m: None) -> dict:
    try:
        return page_json(stac_page_url(dataset_id, page, limit, bbox))
    except requests.HTTPError:
        raise


def load_stac_items(dataset_id: str, progress=lambda m: None,
                    bbox: tuple | None = None, max_pages: int = STAC_MAX_PAGES) -> list[dict]:
    """Walk one collection (optionally inside a bbox window). ES caps the
    result window at 10000, so full walks are done tile-by-tile from
    footprints_table; persistent 502s retry with a halved page size."""
    items, page, limit = [], 1, STAC_PAGE_LIMIT
    import time as _time
    while page <= max_pages:
        try:
            payload = load_stac_page(dataset_id, page, limit, bbox)
        except requests.HTTPError:
            if limit > 50:
                limit = max(50, limit // 2)
                progress(f"{dataset_id}: halving page size to {limit}")
                continue
            raise
        features = payload.get("features", [])
        items.extend(features)
        progress(f"{dataset_id} page {page}: +{len(features)} (total {len(items)})")
        if len(features) < limit:
            break
        page += 1
        _time.sleep(1.0)
    return items


LICENCE_OF = {"ctx-dtms-usgs-stac": "CC0-1.0", "hirise-dtms-usgs-stac": "CC0-1.0"}


TILE_DEG = 30.0


def footprints_table(out_path: Path, report: dict, progress=lambda m: None) -> dict:
    """Full table: page each collection through 30-degree bbox tiles (the
    gateway caps any single result window at 10,000 items), deduplicating by
    item id across tile overlaps."""
    import time as _time
    rows_by_id = {}
    lat_steps = [(-90.0 + i * TILE_DEG) for i in range(int(180.0 / TILE_DEG))]
    lon_steps = [(-180.0 + i * TILE_DEG) for i in range(int(360.0 / TILE_DEG))]
    for dataset_id in STAC_DATASETS:
        for lat0 in lat_steps:
            for lon0 in lon_steps:
                bbox = (lon0, lat0, lon0 + TILE_DEG, lat0 + TILE_DEG)
                items = load_stac_items(dataset_id, progress, bbox=bbox,
                                        max_pages=80)
                new_count = 0
                for item in items:
                    iid = item["id"]
                    if iid not in rows_by_id:
                        new_count += 1
                        bbox_i = item.get("bbox")
                        if not bbox_i or len(bbox_i) != 4:
                            continue
                        assets = item.get("assets", {})
                        dtm = assets.get("dtm") or next(
                            (a for a in assets.values()
                             if "data" in a.get("roles", [])), None)
                        if dtm is None:
                            continue
                        props = item.get("properties", {})
                        rows_by_id[iid] = {
                            "collection": dataset_id,
                            "item_id": iid,
                            "centre_lat": round((bbox_i[1] + bbox_i[3]) / 2.0, 6),
                            "centre_lon_e": round((bbox_i[0] + bbox_i[2]) / 2.0 % 360.0, 6),
                            "min_lon_e": round(bbox_i[0] % 360.0, 6),
                            "max_lon_e": round(bbox_i[2] % 360.0, 6),
                            "min_lat": round(bbox_i[1], 6),
                            "max_lat": round(bbox_i[3], 6),
                            "gsd_m": props.get("gsd") if props.get("gsd")
                            is not None else item.get("gsd"),
                            "datetime_utc": (props.get("datetime")
                                             or item.get("datetime")),
                            "dtm_url": dtm.get("href"),
                            "licence": props.get("license")
                            or LICENCE_OF[dataset_id],
                            "licence_verified": True,
                        }
                progress(f"{dataset_id} tile {bbox}: +{new_count} new "
                         f"({len(rows_by_id)} total)")
                _time.sleep(1.0)
    rows = list(rows_by_id.values())
    frame = pl.DataFrame(rows, schema_overrides={"gsd_m": pl.Float64})
    part = out_path.with_suffix(".part")
    frame.write_parquet(part)
    os.replace(part, out_path)
    summary = {"rows": frame.height,
               "perCollection": {d: int((frame["collection"] == d).sum())
                                 for d in STAC_DATASETS},
               "sha256": sha256(out_path), "bytes": out_path.stat().st_size,
               "api": STAC_API,
               "collections": STAC_COLLECTION_ID}
    report["stacFootprints"] = summary
    return summary


def normalise_lon_e(lon: float) -> float:
    return ((lon + 180.0) % 360.0) - 180.0


def site_bbox_contains(bbox: list[float], lat: float, lon_e: float) -> bool:
    lon = normalise_lon_e(lon_e)
    return bbox[1] <= lat <= bbox[3] and bbox[0] <= lon <= bbox[2]


def select_site_dtms(dataset_id: str, items: list[dict]) -> dict:
    """For each named site: the largest-area item whose bbox contains the site
    centre (highest overlap with the site point inside)."""
    chosen = {}
    for site, lat0, lon0 in SITES:
        candidates = [it for it in items if site_bbox_contains(it["bbox"], lat0, lon0)]
        if candidates:
            best = max(candidates,
                       key=lambda it: (it["bbox"][2] - it["bbox"][0]) * (it["bbox"][3] - it["bbox"][1]))
            chosen[site] = {"item_id": best["id"], "dtm_url": (best.get("assets", {}).get("dtm")
                                                               or {}).get("href"),
                            "gsd_m": best.get("gsd")}
    return chosen


def dtm_units_factor(src) -> tuple[str, float]:
    """('degree'|'metre', factor): the axis unit of the DTM CRS."""
    try:
        from pyproj import CRS as _PyprojCRS
        pj = _PyprojCRS.from_wkt(src.crs.to_wkt())
        unit = pj.axis_info[0].unit_name.lower() if pj.axis_info else "metre"
        if "degree" in unit or pj.is_geographic:
            return "degree", 1.0
    except Exception:
        pass
    return "metre", 1.0


def dtm_sphere_radius_m(src) -> float:
    """Sphere radius of the DTM CRS (USGS Mars DTMs: Mars 2015 sphere
    3,396,190 m); falls back to the blended-DEM sphere."""
    try:
        from pyproj import CRS as _PyprojCRS
        pj = _PyprojCRS.from_wkt(src.crs.to_wkt())
        semi = pj.ellipsoid.semi_major_metre
        if semi:
            return float(semi)
    except Exception:
        pass
    return R_BLENDED


def dtm_pixel_lonlat(src, rows, cols):
    """Pixel-centre planetocentric lat / east-positive lon for DTM pixel
    grids. Degree CRS: use the affine coordinates directly. Projected metre
    CRS: the USGS Mars DTMs are equirectangular on a sphere
    (x = R*lon_rad, y = R*lat_rad), so invert that analytically - no PROJ
    datum ops needed (PROJ has no path from EPSG:4979 to the Mars body)."""
    xs = src.transform * (np.asarray(cols, dtype=np.float64) + 0.5,
                          np.asarray(rows, dtype=np.float64) + 0.5)
    x, y = xs[0], xs[1]
    unit, _ = dtm_units_factor(src)
    if unit == "degree":
        lat, lon = np.asarray(x) * 0 + np.asarray(y), np.asarray(x)
    else:
        radius = dtm_sphere_radius_m(src)
        lat = np.degrees(np.asarray(y) / radius)
        lon = np.degrees(np.asarray(x) / radius) % 360.0
    return np.asarray(lat), np.asarray(lon)


def great_circle_distance_m(lat1, lon1, lat2, lon2, radius_m: float):
    dlat = np.radians(np.asarray(lat2) - np.asarray(lat1))
    dlon = (np.radians(np.asarray(lon2) - np.asarray(lon1)) + math.pi) % (2 * math.pi) - math.pi
    return radius_m * np.sqrt(dlat ** 2 + (dlon * np.cos(np.radians((lat1 + lat2) / 2.0))) ** 2)


def even_span_for(target_m: float, gsd_ns_m: float) -> int:
    return max(2, 2 * int(round(target_m / gsd_ns_m / 2.0)))

def dtm_site_products(dataset_id: str, out_path: Path, report: dict,
                      progress=lambda m: None) -> dict:
    """Select DTM tiles covering the six named sites from the footprints
    table, download only those through fetch (MANIFEST provenance), and build
    per-site products: slope_20_40m (CTX, central difference at the even span
    nearest the 30 m mid-band), slope_5m (HiRISE, span nearest 3.5 m),
    slope_trav_mean (mean native-baseline slope inside radius_m) and
    relief_ellipse (max-min elevation within radius_m; the ellipse size is a
    parameter, not a fixed value). GSD comes from the raster transform, not
    the STAC record."""
    feature = "slope_20_40m" if dataset_id == "ctx-dtms-usgs-stac" else "slope_5m"
    midband_m = {"slope_20_40m": 30.0, "slope_5m": 3.5}[feature]
    radius_m = STATS_RADIUS_M[dataset_id]
    foot = pl.read_parquet(OUT_FOOT).filter(pl.col("collection") == dataset_id)
    report.setdefault("siteDtms", {}).setdefault(dataset_id, {"selection": {}})
    rows = []
    for site, lat0, lon0 in SITES:
        lon_e = lon0 % 360.0
        lon_min, lon_max = pl.col("min_lon_e"), pl.col("max_lon_e")
        lon_hit = ((lon_min <= lon_max)
                   & (lon_min <= lon_e) & (lon_max >= lon_e)) \
            | ((lon_min > lon_max)                     # antimeridian-crossing bbox
               & ((lon_e >= lon_min) | (lon_e <= lon_max)))
        hits = foot.filter((pl.col("min_lat") <= lat0)
                           & (pl.col("max_lat") >= lat0) & lon_hit)
        if hits.height == 0:
            for feat_k, stat_k, rad_k in (
                    (feature, "max-within-radius-stated-baseline", None),
                    ("slope_trav_mean", "mean-within-radius-native-baseline", radius_m),
                    ("relief_ellipse", "max-minus-min-within-radius", RELIEF_RADIUS_M)):
                rows.append(site_row_null(site, dataset_id,
                                          "no-controlled-dtm-covers-site-centre",
                                          feature=feat_k, stat=stat_k, radius=rad_k))
            report["siteDtms"][dataset_id]["selection"][site] = None
            continue
        candidates = hits.with_columns(
            ((pl.col("max_lon_e") - pl.col("min_lon_e"))
             * (pl.col("max_lat") - pl.col("min_lat"))).alias("area")
        ).sort("area").rows(named=True)
        # smallest tile first: bbox can be sloppy on overlapping mosaics, so
        # verify actual coverage near the site before accepting a candidate
        pick = None
        tile = None
        opened = None
        for cand in candidates[:8]:
            try:
                tile_c = Path(fetch(dataset_id, cand["dtm_url"]))
                src_c = rasterio.open(tile_c)
            except Exception as exc:
                progress(f"{dataset_id} candidate {cand['item_id']} skipped: {exc}")
                continue
            radius_c = dtm_sphere_radius_m(src_c)
            if dtm_units_factor(src_c)[0] == "metre":
                sx = math.radians(normalise_lon_e(lon0)) * radius_c
                sy = math.radians(lat0) * radius_c
                c0, r0 = (~src_c.transform) * (sx, sy)
            else:
                c0, r0 = (~src_c.transform) * (normalise_lon_e(lon0), lat0)
            col_cs, row_cs = int(c0), int(r0)
            if not (0 <= col_cs < src_c.width and 0 <= row_cs < src_c.height):
                src_c.close()
                continue
            probe = src_c.read(1, window=rasterio.windows.Window(
                max(0, col_cs - 10), max(0, row_cs - 10),
                min(21, src_c.width - max(0, col_cs - 10)),
                min(21, src_c.height - max(0, row_cs - 10))))
            nd = src_c.nodata
            good = np.isfinite(probe) & ((probe != nd) if nd is not None else True)
            if int(good.sum()) >= 5:
                pick = {"item_id": cand["item_id"], "dtm_url": cand["dtm_url"]}
                tile = tile_c
                opened = src_c
                break
            src_c.close()
        if pick is None:
            for feat_k, stat_k, rad_k in (
                    (feature, "max-within-radius-stated-baseline", None),
                    ("slope_trav_mean", "mean-within-radius-native-baseline", radius_m),
                    ("relief_ellipse", "max-minus-min-within-radius", RELIEF_RADIUS_M)):
                rows.append(site_row_null(site, dataset_id,
                                          "no-dtm-candidate-has-valid-pixels-at-site",
                                          feature=feat_k, stat=stat_k, radius=rad_k))
            report["siteDtms"][dataset_id]["selection"][site] = None
            continue
        with opened as src:
            unit, _ = dtm_units_factor(src)
            nodata = src.nodata
            px_x = abs(float(src.transform.a))
            px_y = abs(float(src.transform.e))
            gsd_ns = px_y * (1.0 if unit == "metre"
                             else (math.pi / 180.0) * R_BLENDED)
            unit_note_unit = unit
            # window covers the larger of radius / relief radius (+ margin)
            pad_x = (max(radius_m, RELIEF_RADIUS_M) / max(px_x, 1e-9)) * 1.2
            pad_y = (max(radius_m, RELIEF_RADIUS_M) / max(px_y, 1e-9)) * 1.2
            if unit == "metre":
                # equirectangular metre CRS: x/y from lon/lat on the sphere
                radius = dtm_sphere_radius_m(src)
                sx = math.radians(normalise_lon_e(lon0)) * radius
                sy = math.radians(lat0) * radius
                inv = ~src.transform
                c0, r0 = inv * (sx, sy)
                col_c, row_c = int(c0), int(r0)
            else:
                inv = ~src.transform
                c0, r0 = inv * (normalise_lon_e(lon0), lat0)
                col_c, row_c = int(c0), int(r0)
            col0 = int(np.clip(col_c - pad_x, 0, src.width))
            col1 = int(np.clip(col_c + pad_x, 0, src.width))
            row0 = int(np.clip(row_c - pad_y, 0, src.height))
            row1 = int(np.clip(row_c + pad_y, 0, src.height))
            window = rasterio.windows.Window(col0, row0, col1 - col0,
                                             row1 - row0)
            data = src.read(1, window=window)
            rr = np.arange(row0, row1, dtype=np.float64)[:, None] \
                + np.zeros((1, col1 - col0))
            cc = np.zeros((row1 - row0, 1)) + np.arange(col0, col1)[None, :]
            lat_grid, lon_grid = dtm_pixel_lonlat(src, rr, cc)
            if unit == "degree":
                gsd_ew = np.cos(np.radians(lat_grid)) * (math.pi / 180.0) * R_BLENDED
            else:
                gsd_ew = np.full(lat_grid.shape,
                                 px_x / math.cos(math.radians(lat_grid.mean())))
            z = data.astype(np.float32)
            valid = np.isfinite(z) & (z != nodata) if nodata is not None \
                else np.isfinite(z)
            if src.dtypes[0].startswith("float") and nodata is None:
                elev_lo, elev_hi = -20_000.0, 30_000.0
                valid &= (z >= elev_lo) & (z <= elev_hi)
            z = np.where(valid, z, np.nan)
            dist = great_circle_distance_m(lat0, lon0, lat_grid, lon_grid,
                                           R_BLENDED)
            in_r = dist <= radius_m
            rel_r = dist <= RELIEF_RADIUS_M
            span = even_span_for(midband_m, gsd_ns)
            baseline_ns = span * gsd_ns
            baseline_ew_mid = (span * gsd_ew[int(np.clip(row_c - row0, 0,
                                                         gsd_ew.shape[0] - 1))]
                               .mean() if gsd_ew.size else span * gsd_ns)
            slope_band, ok_band = central_difference_slope(
                z, span_px=span, gsd_ns_m=gsd_ns, gsd_ew_m=gsd_ew,
                wrap_lon=False)
            slope_trav, ok_trav = central_difference_slope(
                z, span_px=2, gsd_ns_m=gsd_ns, gsd_ew_m=gsd_ew, wrap_lon=False)
            lo, hi = BAND_OF[feature]
            # values 0-5% outside the upper band edge are kept but flagged
            span_flag = ""
            band_hi = hi * 1.05
            if baseline_ns > hi or baseline_ew_mid > hi:
                span_flag = ("baseline %.1f%% above band upper edge"
                             % (100.0 * max(baseline_ns, baseline_ew_mid) / hi - 100.0))
            in_band_feat = (ok_band & rel_r & (baseline_ns >= lo)
                            & (baseline_ns <= band_hi)
                            & (baseline_ew_mid >= lo)
                            & (baseline_ew_mid <= band_hi))
            trav_mask = ok_trav & in_r
            support_band = int(in_band_feat.sum())
            support_trav = int(trav_mask.sum())
            z_rel = z[rel_r]
            relief = (float(np.nanmax(z_rel) - np.nanmin(z_rel))
                      if np.isfinite(z_rel).any() else None)
            band_val = (float(np.nanmax(slope_band[in_band_feat]))
                        if support_band and np.isfinite(slope_band[in_band_feat]).any()
                        else None)
            trav_val = (float(np.nanmean(slope_trav[trav_mask]))
                        if support_trav else None)
            elev_in = z[in_r]
            support_relief = int((rel_r & np.isfinite(z)).sum())
            base_note = (f"{unit_note_unit}-crs dtm; central difference between "
                         f"pixel centres; gsd from raster transform; "
                         f"relief radius is a parameter (radius_m), not a fixed value")
            if span_flag:
                base_note += "; " + span_flag
            for stat, val, sup, r_m, base_m in (
                    (feature, band_val, support_band, None, baseline_ns),
                    ("slope_trav_mean", trav_val, support_trav, radius_m, 2 * gsd_ns),
                    ("relief_ellipse", relief, support_relief, RELIEF_RADIUS_M, None)):
                if val is None:
                    reason = ("fewer-than-5-valid-dtm-pixels-in-site-radius"
                              if sup is not None and 0 < sup < 5
                              else "no-valid-dtm-pixels-in-site-radius")
                    if stat == "relief_ellipse":
                        reason = "no-valid-dtm-elevation-in-site-radius"
                    stat_name = ("max-within-radius-stated-baseline" if stat == feature
                                 else "mean-within-radius-native-baseline"
                                 if stat == "slope_trav_mean"
                                 else "max-minus-min-within-radius")
                    rows.append(site_row_null(site, dataset_id, reason,
                                              baseline=None if base_m is None else round(base_m, 2),
                                              feature=stat, stat=stat_name,
                                              radius=r_m, item_id=pick["item_id"]))
                    continue
                rows.append({
                    "site": site, "collection": dataset_id,
                    "item_id": pick["item_id"], "feature": stat,
                    "stat": ("max-within-radius-stated-baseline" if stat == feature
                             else "mean-within-radius-native-baseline"
                             if stat == "slope_trav_mean"
                             else "max-minus-min-within-radius"),
                    "value": val, "gsd_m": round(gsd_ns, 4),
                    "baseline_m": None if base_m is None else round(base_m, 2),
                    "radius_m": r_m, "support_px": sup, "note": base_note,
                    "missing_reason": None})
            report["siteDtms"][dataset_id]["selection"][site] = {
                **pick, "gsd_m": round(gsd_ns, 4), "unit": unit,
                "tile_path": str(tile)}
    frame = pl.DataFrame(rows, schema_overrides={
        "value": pl.Float64, "gsd_m": pl.Float64, "baseline_m": pl.Float64,
        "radius_m": pl.Float64})
    part = out_path.with_suffix(".part")
    frame.write_parquet(part)
    os.replace(part, out_path)
    summary = {"rows": frame.height,
               "selected": report["siteDtms"][dataset_id]["selection"],
               "radius_m": radius_m, "midbandTarget_m": midband_m}
    report["siteDtms"][dataset_id].update(summary)
    return summary




# --------------------------------------------------------------------------- #
# build / check / main
# --------------------------------------------------------------------------- #

OUT_MEGDR32 = OUT / "mars-topo-megdr32-elevation.parquet"
OUT_BLOCK = OUT / "mars-topo-blended-3p2km-blocks.parquet"
OUT_BPIX = OUT / "mars-topo-blended-site-pixels.parquet"
OUT_FOOT = OUT / "mars-topo-dtm-footprints.parquet"
OUT_DCTX = OUT / "mars-topo-site-dtm-ctx-stats.parquet"
OUT_DHIR = OUT / "mars-topo-site-dtm-hirise-stats.parquet"
REPORT = OUT / "preparation-report.json"


def build() -> dict:
    OUT.mkdir(parents=True, exist_ok=True)
    verify_manifest_inputs(source_urls())
    report = {
        "datasetId": "mars_topo",
        "generatedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "runtimeStatus": "executed",
        "scientificStatus": "executed-unreviewed",
        "scope": ("Mars topography + slopes, source-native (issue #103 / W44). No scoring, "
                  "ranking, similarity, UI or cross-body comparison; no resampling to H3."),
        "timeResolution": "static (single-epoch elevation surfaces; monthly rule not binding)",
        "sites": [{"site": s, "latPlanetocentric": la, "lonEast360": lo}
                  for s, la, lo in SITES],
        "reliefEllipse": {"radiusM": RELIEF_RADIUS_M,
                          "note": "radius is a parameter (radius_m column), not a fixed value"},
        "outputs": {},
    }
    progress = lambda m: print(f"[mars_topo] {m}", flush=True)

    meg = megdr32_elevation_table(OUT_MEGDR32, report, progress)
    report["outputs"]["megdr32elevation"] = meg
    site_rows = megdr32_site_stats(OUT_MEGDR32, report)
    site_frame = pl.DataFrame(site_rows, schema_overrides={
        "value": pl.Float64, "gsd_m": pl.Float64, "baseline_m": pl.Float64,
        "radius_m": pl.Float64})
    site_out = OUT / "mars-topo-site-stats-megdr32.parquet"
    part = site_out.with_suffix(".part")
    site_frame.write_parquet(part)
    os.replace(part, site_out)
    report["outputs"]["siteStatsMegdr32"] = {
        "rows": site_frame.height, "sha256": sha256(site_out),
        "bytes": site_out.stat().st_size}
    del site_frame, part
    blended = blended_tables(OUT_BLOCK, OUT_BPIX, report, progress)
    report["outputs"]["blendedBlocks"] = blended["blocks"]
    report["outputs"]["blendedSitePixels"] = blended["pixels"]
    foot = footprints_table(OUT_FOOT, report, progress)
    report["outputs"]["stacFootprints"] = foot
    for dataset_id, out in (("ctx-dtms-usgs-stac", OUT_DCTX),
                            ("hirise-dtms-usgs-stac", OUT_DHIR)):
        try:
            s = dtm_site_products(dataset_id, out, report, progress)
            report["outputs"][f"siteDtm_{dataset_id}"] = s
        except Exception as exc:  # keep partial work; record the evidence
            report["outputs"][f"siteDtm_{dataset_id}"] = {
                "error": f"{type(exc).__name__}: {exc}"}
            progress(f"WARNING {dataset_id} site products failed: {exc}")
    part = REPORT.with_suffix(".part")
    part.write_text(json.dumps(report, indent=2, sort_keys=True))
    os.replace(part, REPORT)
    progress("build complete")
    return report


def _raw_megdr32():
    img, _ = megdr32_paths()
    return np.memmap(img, dtype=">i2", mode="r", shape=(MEGDR_LINES, MEGDR_SAMPLES))


MEGDR_LINES, MEGDR_SAMPLES = 5760, 11520


def check() -> dict:
    """Structural checks plus raw spot checks against source pixels."""
    verify_manifest_inputs(source_urls())
    problems = []

    frame = pl.read_parquet(OUT_MEGDR32)
    if frame.height != MEGDR_LINES * MEGDR_SAMPLES:
        problems.append(f"megdr32 rows {frame.height} != {MEGDR_LINES * MEGDR_SAMPLES}")
    elev_null = frame["elevation_m"].null_count()
    reason = frame["missing_reason"]
    if elev_null != sum(1 for r in reason if r and "elevation_m" in json.loads(r)):
        problems.append("megdr32 elevation nulls vs missing_reason mismatch")
    exp_hot = json.dumps({"elevation_m": "outside-published-topography-range",
                          "slope_2_5km": "no-valid-source-elevation"})
    exp_mid = json.dumps({"slope_2_5km": "insufficient-neighbours-or-edge"})
    exp_band = json.dumps({"slope_2_5km": "baseline-outside-2-5km-band"})
    mr = frame["missing_reason"]
    elev_null_v = frame["elevation_m"].is_null().to_numpy()
    slope_null_v = frame["slope_2_5km"].is_null().to_numpy()
    bad_mr = int(
        ((elev_null_v & slope_null_v & (mr != exp_hot).fill_null(True).to_numpy()).sum()
         + (elev_null_v & ~slope_null_v).sum()
         + (~elev_null_v & slope_null_v
            & ~mr.is_in([exp_mid, exp_band]).fill_null(False).to_numpy()).sum()
         + (~elev_null_v & ~slope_null_v & (mr.is_not_null().to_numpy())).sum()))
    if bad_mr:
        problems.append(f"megdr32 missing_reason/null agreement violated: {bad_mr}")
    valid = frame.filter(pl.col("elevation_m").is_not_null())
    zmin, zmax = float(valid["elevation_m"].min()), float(valid["elevation_m"].max())
    if not (-9000 <= zmin and zmax <= 22_000):
        problems.append(f"megdr32 elevation out of physical range: {zmin}..{zmax}")
    slope = frame.filter(pl.col("slope_2_5km").is_not_null())
    if not (0 <= float(slope["slope_2_5km"].min()) and float(slope["slope_2_5km"].max()) <= 90):
        problems.append("megdr32 slope_2_5km out of [0,90]")

    blocks = pl.read_parquet(OUT_BLOCK)
    dup = blocks.filter(pl.struct(["block_line", "block_sample"]).is_duplicated())
    if dup.height:
        problems.append(f"blended blocks duplicate keys: {dup.height}")
    bv = blocks.filter(pl.col("slope_200_500m_mean").is_not_null())
    nulled = blocks.filter(pl.col("slope_200_500m_mean").is_null())
    bad_reason = nulled.filter(
        pl.col("missing_reason").is_null()
        | pl.col("missing_reason").map_elements(
            lambda r: set(json.loads(r)) != {"slope_200_500m_mean"},
            return_dtype=pl.Boolean)).height
    if bad_reason or blocks.filter(pl.col("slope_200_500m_mean").is_not_null()
                                   & pl.col("missing_reason").is_not_null()).height:
        problems.append("blended blocks missing_reason/null agreement violated")
    if not (0 <= float(bv["slope_200_500m_mean"].min())
            and float(bv["slope_200_500m_mean"].max()) <= 90):
        problems.append("blended block slope out of [0,90]")

    foot = pl.read_parquet(OUT_FOOT)
    if foot.height > 0:
        if foot.filter(pl.struct(["collection", "item_id"]).is_duplicated()).height:
            problems.append("footprint duplicate keys")
        if foot.filter(pl.col("gsd_m") <= 0).height:
            problems.append("footprint nonpositive gsd")
        if foot.filter(pl.col("licence").is_null()).height:
            problems.append("footprint missing licence")

    stats = pl.read_parquet(OUT_DCTX) if OUT_DCTX.exists() else pl.DataFrame()
    stath = pl.read_parquet(OUT_DHIR) if OUT_DHIR.exists() else pl.DataFrame()
    for name, sf in (("ctx", stats), ("hirise", stath)):
        if sf.height:
            for col in ("collection", "site", "feature", "stat"):
                if sf.filter(pl.col(col).is_null()).height:
                    problems.append(f"{name} stats null key column {col}")
            if sf.filter(pl.col("value").is_null()
                         & (pl.col("missing_reason").is_null())).height:
                problems.append(f"{name} stats null value without missing_reason")
            vals = sf.filter(pl.col("value").is_not_null() & (pl.col("feature") != "relief_ellipse"))
            if vals.height and (vals.filter((pl.col("value") < 0)
                                            | (pl.col("value") > 90)).height):
                problems.append(f"{name} stats slope values out of [0,90]")
            if sf.filter(pl.col("feature") == "relief_ellipse") \
                    .filter(pl.col("value") <= 0).height:
                problems.append(f"{name} relief_ellipse nonpositive")

    # --- raw spot checks ---------------------------------------------------- #
    raw = _raw_megdr32()
    spot_megdr = []
    for site, lat0, lon0 in SITES:
        line, sample = megdr32_latlon_to_pixel(lat0, lon0)
        steps = [0, 5, 11, 17, 23]
        for dl, ds in ((steps[0], steps[0]), (steps[1], steps[2]),
                       (steps[3], steps[1]), (steps[2], steps[4]),
                       (steps[4], steps[3])):  # 5 offsets, distinct pixels
            r_raw = np.array(raw[line + dl, sample + ds], dtype=np.float64)
            lat_px = 90.0 - ((line + dl) + 0.5) / MEGDR_LINES * 180.0
            lon_px = (((sample + ds) + 0.5) / MEGDR_SAMPLES * 360.0) % 360.0
            row = frame.filter((pl.col("source_line") == line + dl)
                               & (pl.col("source_sample") == sample + ds))
            check_note = {"site": site, "source_line": line + dl,
                          "source_sample": sample + ds,
                          "raw_elevation_m": None if r_raw == -32768 else float(r_raw),
                          "table_elevation_m": (row["elevation_m"][0]
                                                if row.height and row["elevation_m"][0] is not None
                                                else None),
                          "lat_px": round(lat_px, 5), "lon_px": round(lon_px, 5)}
            if r_raw != -32768 and check_note["table_elevation_m"] is not None:
                check_note["match"] = abs(check_note["raw_elevation_m"]
                                          - check_note["table_elevation_m"]) <= 0.5
            elif r_raw == -32768:
                check_note["match"] = (row.height == 0
                                       or row["elevation_m"][0] is None)
            else:
                check_note["match"] = None
            spot_megdr.append(check_note)
    bad = [s for s in spot_megdr if s["match"] is False]
    if bad:
        problems.append(f"megdr32 raw spot check mismatch: {bad[:2]}")
    if sum(1 for s in spot_megdr if s["match"]) < 5:
        problems.append("fewer than 5 matching megdr32 raw spot checks")
    del raw

    result = {
        "checkedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "megdr32": {"rows": frame.height, "elevationNulls": elev_null,
                    "slopeNulls": frame["slope_2_5km"].null_count(),
                    "slopeSupportPx": len(slope), "elevationRange": [zmin, zmax]},
        "blendedBlocks": {"rows": blocks.height,
                          "nulls": blocks["slope_200_500m_mean"].null_count()},
        "footprints": {"rows": foot.height},
        "siteDtmCtxStats": {"rows": stats.height if stats.height else 0},
        "siteDtmHiriseStats": {"rows": stath.height if stath.height else 0},
        "spotChecks": {"megdr32": spot_megdr},
        "problems": problems,
        "pass": not problems,
    }
    print(json.dumps({k: v for k, v in result.items() if k != "spotChecks"}, indent=2))
    if problems:
        raise SystemExit(f"check FAILED: {len(problems)} problem(s)")
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description="Mars topography preparation (#103)")
    parser.add_argument("command", choices=["fetch", "build", "check"])
    args = parser.parse_args(argv)
    if args.command == "fetch":
        for dataset_id, url in sources():
            path = fetch(dataset_id, url)
            print(f"fetched {path} {Path(path).stat().st_size}")
    elif args.command == "build":
        build()
    else:
        check()


if __name__ == "__main__":
    main()


