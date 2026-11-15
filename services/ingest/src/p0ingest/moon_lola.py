"""W40 (#99): LOLA south-pole polar products, source-native polar-stereographic grids.

Prepares the Barker et al. 2023 south-pole LDEM/LDEC/LPSR/LDRM rasters (PGDA
product 90), the Mazarico et al. 2016 average solar illumination and
Earth-visibility maps (PDS Geosciences copies of the PGDA product 69 IMGs),
and the coarse global LOLA GDR (ldem_4, cylindrical). The USGS gazetteer Moon
centre-points zip is fetched to validate placement of named south-polar
features (Shackleton, Malapert, Haworth, Shoemaker, de Gerlache).

Everything stays on its native grid. Raster tables are keyed by zero-based
(source_line, source_sample) with the exact pixel-centre projection recorded
in the preparation report (same convention as planetary.py); the 1 km PSR
table and the GDR table carry explicit geometric keys. No value is resampled
to another grid and none to Earth H3. Three quantities are computed here
because the products do not publish them (psr_frac_2km, psr_dist_km) or publish
no 2 km layer (slope_2km_eva); every window and method is stated in the
preparation report. Time resolution: static products.

Run: python -m p0ingest.moon_lola fetch|build|check
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import io
import json
import math
import re
import zipfile
from pathlib import Path
from tempfile import TemporaryDirectory

import numpy as np
import polars as pl
import rasterio as rio
from rasterio.warp import transform as warp_transform

from .planetary import write_batches
from .snapshots import REPO, SNAP, fetch, load_manifest, sha256

OUT = SNAP / "_derived" / "planetary"
PGDA = "https://pgda.gsfc.nasa.gov/data/LOLA_20mpp/"
PDS_ILL = ("https://pds-geosciences.wustl.edu/lro/lro-l-lola-3-rdr-v1/"
           "lrolol_1xxx/extras/illumination/img/")
PDS_GDR = ("https://pds-geosciences.wustl.edu/lro/lro-l-lola-3-rdr-v1/"
           "lrolol_1xxx/data/lola_gdr/cylindrical/img/")
GAZETTEER = "https://planetarynames.wr.usgs.gov/shapefiles/MOON_nomenclature_center_pts.zip"
MOON_R_M = 1_737_400.0

LDEM_2023 = "lola-south-pole-ldem-2023"
ILLUM = "lola-polar-illumination"
GDR = "lola-gdr"
NOMENCLATURE = "usgs-planetary-nomenclature"

# table name -> (snapshot dir, value columns, per-column missing reason, key columns)
TABLES = {
    "ldem-80s-20mpp.parquet": (LDEM_2023, ["elevation_m", "lola_spot_count", "psr_2023"],
                               {"elevation_m": "source-nodata", "lola_spot_count": "source-nodata",
                                "psr_2023": "source-nodata"}, ["source_line", "source_sample"]),
    "ldrm-80s-50mpp.parquet": (LDEM_2023, ["slope_100m_deg", "rough_rms_100m_m"],
                               {"slope_100m_deg": "source-nodata", "rough_rms_100m_m": "source-nodata"},
                               ["source_line", "source_sample"]),
    "ldem-60s-240mpp.parquet": (LDEM_2023, ["elevation_m", "slope_2km_eva_deg"],
                                {"elevation_m": "source-nodata", "slope_2km_eva_deg": "incomplete-window"},
                                ["source_line", "source_sample"]),
    "psr-2km-1kmgrid.parquet": (LDEM_2023, ["psr_frac_2km", "psr_dist_km"],
                                {"psr_frac_2km": "psr-window-truncated", "psr_dist_km": "psr-window-truncated"},
                                ["x_m", "y_m"]),
    "avgvisib-85s-060m.parquet": (ILLUM, ["illum_frac_pct", "earth_vis_pct"],
                                  {"illum_frac_pct": "source-nodata", "earth_vis_pct": "source-nodata"},
                                  ["source_line", "source_sample"]),
    "avgvisib-75s-120m.parquet": (ILLUM, ["illum_frac_pct", "earth_vis_pct"],
                                  {"illum_frac_pct": "source-nodata", "earth_vis_pct": "source-nodata"},
                                  ["source_line", "source_sample"]),
    "ldem-gdr-4ppd.parquet": (GDR, ["elevation_m"],
                              {"elevation_m": "source-no-data-constant"}, ["lat_deg", "lon_deg"]),
}

PHYSICAL_RANGE = {
    "elevation_m": (-11000.0, 11000.0),
    "lola_spot_count": (0.0, 1e6),
    "psr_2023": (0.0, 1.0),
    "slope_100m_deg": (0.0, 90.0),
    "rough_rms_100m_m": (0.0, 5000.0),
    "slope_2km_eva_deg": (0.0, 90.0),
    "psr_frac_2km": (0.0, 1.0),
    "psr_dist_km": (0.0, 5000.0),
    "illum_frac_pct": (0.0, 100.0),
    "earth_vis_pct": (0.0, 100.0),
}


def sources():
    for name in ("LDEM_80S_20MPP_ADJ.TIF", "LDEC_80S_20MPP_ADJ.TIF",
                 "LPSR_80S_20MPP_ADJ.TIF", "LDRM_80S_50MPP_ADJ_SLP_100M.TIF",
                 "LDRM_80S_50MPP_ADJ_RMSD_100M.TIF", "LDEM_60S_240MPP_ADJ.TIF"):
        yield LDEM_2023, PGDA + name
    for kind in ("85s_060m", "75s_120m"):
        for tag in ("", "_earth"):
            for ext in ("img", "lbl"):
                yield ILLUM, PDS_ILL + f"avgvisib_{kind}_201608{tag}.{ext}"
    for ext in ("img", "lbl", "xml"):
        yield GDR, PDS_GDR + f"ldem_4.{ext}"
    yield NOMENCLATURE, GAZETTEER


def verify_inputs() -> tuple[list[dict], list[str]]:
    """Every source file must sit in MANIFEST with matching hash/size and a verified licence.

    The only allowed gap is LDEC_80S_20MPP_ADJ.TIF (LOLA spot counts) when the
    fetch was deferred: local file absent AND no MANIFEST entry -> returned as a
    gap; a present-but-unlicensed or hash-mismatched LDEC still raises.
    """
    entries = {e["sourceUrl"]: e for e in load_manifest()["entries"]}
    checked = []
    gaps = []
    for dataset, url in sources():
        fname = url.rsplit("/", 1)[-1]
        deferred = fname == "LDEC_80S_20MPP_ADJ.TIF" \
            and not (SNAP / LDEM_2023 / fname).exists()
        e = entries.get(url)
        if e is None or e["datasetId"] != dataset or not e["licenseVerified"]:
            if deferred and e is None:
                gaps.append(url)
                continue
            raise ValueError(f"missing licensed snapshot: {url}")
        path = REPO / e["localPath"]
        if path.stat().st_size != e["bytes"] or sha256(path) != e["sha256"]:
            raise ValueError(f"input hash/size mismatch: {path}")
        checked.append(e)
    return checked, gaps


# ---------------------------------------------------------------- PDS3 labels

def parse_pds3_label(text: str) -> dict:
    """Minimal PDS3 parser: KEY = VALUE lines; OBJECT groups kept per group."""
    label: dict = {}
    objects: dict[str, dict] = {}
    current = None
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("/*"):
            continue
        if line.startswith("END_OBJECT"):
            current = None
            continue
        m = re.match(r"^OBJECT\s*=\s*\"?([A-Za-z0-9_]+)\"?\s*$", line)
        if m:
            current = m.group(1)
            objects.setdefault(current, {})
            continue
        if line.startswith("END"):
            current = None
            continue
        m = re.match(r"^([A-Z0-9_]+)\s*=\s*(.*)$", line)
        if not m:
            continue
        key, raw = m.group(1), m.group(2).strip()
        if (raw.startswith("(") and raw.endswith(")")) or \
                (raw.startswith("{") and raw.endswith("}")):
            value = [v.strip().strip('"') for v in raw[1:-1].split(",") if v.strip()]
        elif raw.startswith('"') and raw.endswith('"'):
            value = raw[1:-1]
        else:
            value = raw.split("<")[0].strip().strip('"')
            try:
                value = int(value)
            except ValueError:
                try:
                    value = float(value)
                except ValueError:
                    pass
        target = objects[current] if current is not None else label
        target[key] = value
    label["objects"] = objects
    return label


def open_lbl_img(img: Path, lbl: Path) -> tuple[np.ndarray, dict]:
    """LSB int16 PDS3 IMG + label -> (memmap, meta) for the illumination maps."""
    label = parse_pds3_label(lbl.read_text(errors="replace"))
    image = label["objects"]["IMAGE"]
    proj = label["objects"]["IMAGE_MAP_PROJECTION"]
    if image["SAMPLE_TYPE"] != "LSB_INTEGER" or int(image["SAMPLE_BITS"]) != 16:
        raise ValueError("unexpected illumination byte layout")
    if str(proj.get("MAP_PROJECTION_TYPE", "")).upper().split("  ")[0].strip() != "POLAR STEREOGRAPHIC":
        raise ValueError("unexpected illumination projection")
    lines, samples = int(image["LINES"]), int(image["LINE_SAMPLES"])
    if img.stat().st_size != lines * samples * 2:
        raise ValueError(f"illumination image byte count differs from label: {img}")
    scale_m = float(proj["MAP_SCALE"])  # label unit is m/pix for these products
    meta = {
        "product": str(label.get("PRODUCT_ID", img.stem)),
        "dataSourceSet": str(label.get("DATA_SET_ID", "")),
        "lines": lines, "samples": samples,
        "scaling": float(image["SCALING_FACTOR"]),
        "mapScaleM": scale_m,
        "centerLat": float(proj["CENTER_LATITUDE"]),
        "centerLon": float(proj["CENTER_LONGITUDE"]),
        "radiusM": float(proj["A_AXIS_RADIUS"]) * 1000.0,
        "lineProjOffsetPx": float(proj["LINE_PROJECTION_OFFSET"]),
        "sampleProjOffsetPx": float(proj["SAMPLE_PROJECTION_OFFSET"]),
        "frame": str(proj.get("COORDINATE_SYSTEM_NAME", "per label")),
    }
    # latitude reach of the canvas, from the corner pixel-centre distance:
    d = max(math.hypot(r - meta["lineProjOffsetPx"], s - meta["sampleProjOffsetPx"])
            for r in (0.0, lines - 1.0) for s in (0.0, samples - 1.0))
    theta = math.degrees(2.0 * math.atan(d * scale_m / (2.0 * meta["radiusM"])))
    meta["minLat"] = round(meta["centerLat"], 4)
    meta["maxLat"] = round(meta["centerLat"] + theta, 4)
    return np.memmap(img, dtype="<i2", mode="r", shape=(lines, samples)), meta


def _stereo_crs(meta: dict):
    from rasterio.crs import CRS
    return CRS.from_proj4(
        f"+proj=stere +lat_0={meta['centerLat']} +lat_ts={meta['centerLat']} "
        f"+lon_0={meta['centerLon']} +R={meta['radiusM']:g} +units=m +no_defs")


def _latlong_crs(radius_m: float):
    from rasterio.crs import CRS
    return CRS.from_dict({"proj": "latlong", "R": radius_m})


def calibrated_lbl_xy(meta: dict) -> dict:
    """Pixel-centre x/y arrays for a PDS3 polar-stereographic label product.

    Uses the PDS3 DSMAP relations (sample = SAMPLE_PROJECTION_OFFSET + x/scale,
    line = LINE_PROJECTION_OFFSET - y/scale, 0-based pixel centres, line down
    = y negative). Verified empirically: with this convention a 60 m
    avgvisib window's DN==0 (never sunlit) mask agrees 97.6% with the
    independent 2023 LPSR mask; both mirrored conventions drop to <=79%.
    Arbitrary test points need not land on pixel centres, so no residual
    threshold is asserted here; the check enforces in-canvas mapping only.
    """
    target = _stereo_crs(meta)
    lats = [-85.6, -87.0, -89.0, -89.9]
    lons = [0.0, 90.0, 180.0, 270.0]
    xs, ys = warp_transform(_latlong_crs(meta["radiusM"]), target, lons, lats)
    scale = meta["mapScaleM"]
    worst = 0.0
    for _lat, _lon, x, y in zip(lats, lons, xs, ys):
        col = x / scale + meta["sampleProjOffsetPx"]
        row = meta["lineProjOffsetPx"] - y / scale
        if not (0 <= round(col) < meta["samples"] and 0 <= round(row) < meta["lines"]):
            raise ValueError("polar-stereographic mapping falls outside the canvas")
        worst = max(worst, abs(col - round(col)), abs(row - round(row)))
    col0 = np.arange(meta["samples"], dtype=np.float64)
    row0 = np.arange(meta["lines"], dtype=np.float64)
    x_m = (col0 - meta["sampleProjOffsetPx"]) * scale
    y_m = (meta["lineProjOffsetPx"] - row0) * scale
    return {"xShiftPx": 0.0, "ySign": 1.0, "worstResidualPx": worst,
            "x_m": x_m, "y_m": y_m}


def lbl_latlon_to_pixel(meta: dict, cal: dict, lat: float, lon: float) -> tuple[int, int]:
    x, y = warp_transform(_latlong_crs(meta["radiusM"]), _stereo_crs(meta), [lon], [lat])
    col = int(round(x[0] / meta["mapScaleM"] + meta["sampleProjOffsetPx"] - cal["xShiftPx"]))
    row = int(round(meta["lineProjOffsetPx"] - cal["ySign"] * y[0] / meta["mapScaleM"]))
    return row, col


def cog_latlon_to_pixel(ds, lat: float, lon: float) -> tuple[int, int]:
    x, y = warp_transform(_latlong_crs(MOON_R_M), ds.crs, [lon], [lat])
    col_f, row_f = ~ds.transform * (x[0], y[0])
    col, row = int(math.floor(col_f)), int(math.floor(row_f))
    if not (0 <= row < ds.height and 0 <= col < ds.width):
        raise ValueError(f"({lat}, {lon}) is outside {ds.name}")
    return row, col


def cog_pixel_xy(ds) -> tuple[np.ndarray, np.ndarray]:
    tr = ds.transform
    x_m = tr.c + (np.arange(ds.width, dtype=np.float64) + 0.5) * tr.a
    y_m = tr.f + (np.arange(ds.height, dtype=np.float64) + 0.5) * tr.e
    return x_m, y_m


def read_block(ds, start: int, stop: int) -> np.ndarray:
    win = rio.windows.Window(0, start, ds.width, stop - start)
    return ds.read(1, window=win)


# ------------------------------------------------------- windowed arithmetic

def disc_stencil(radius_m: float, step_m: float) -> list[tuple[int, int, float, float]]:
    """Pixel offsets (di, dj, x_m, y_m) whose centre lies within radius_m."""
    n = int(math.floor(radius_m / step_m + 1e-9))
    return [(di, dj, dj * step_m, di * step_m)
            for di in range(-n, n + 1) for dj in range(-n, n + 1)
            if math.hypot(di * step_m, dj * step_m) <= radius_m + 1e-9]


def plane_fit_slope_block(dem: np.ndarray, step_m: float, radius_m: float) -> np.ndarray:
    """Least-squares plane slope (deg) over native pixels whose centre lies
    within radius_m (map metres) of the output pixel; x = dj*step_m east,
    y = -di*step_m north. The stencil is centre-symmetric so the slope from
    the 2x2 normal system decouples from the constant term. Windows with any
    missing native pixel (raster edge/nodata) return NaN.
    """
    stencil = disc_stencil(radius_m, step_m)
    if abs(sum(t[2] for t in stencil)) > 1e-9 or abs(sum(t[3] for t in stencil)) > 1e-9:
        raise ValueError("stencil not centre-symmetric in map metres")
    pad_r = max(abs(t[0]) for t in stencil)
    pad_c = max(abs(t[1]) for t in stencil)
    h, w = dem.shape
    padded = np.full((h + 2 * pad_r, w + 2 * pad_c), np.nan)
    padded[pad_r:pad_r + h, pad_c:pad_c + w] = dem
    valid = np.isfinite(padded)
    dem0 = np.where(valid, padded, 0.0)
    sxx = sum(t[2] * t[2] for t in stencil)
    syy = sum(t[3] * t[3] for t in stencil)
    sxy = sum(t[2] * t[3] for t in stencil)
    det = sxx * syy - sxy * sxy
    if det <= 0:
        raise ValueError("degenerate plane-fit normal matrix")
    complete = np.ones((h, w), dtype=bool)
    z_x = np.zeros((h, w))
    z_y = np.zeros((h, w))
    for di, dj, wx, wy in stencil:
        view = dem0[pad_r + di: pad_r + di + h, pad_c + dj: pad_c + dj + w]
        z_x += view * wx
        z_y += view * wy
        complete &= valid[pad_r + di: pad_r + di + h, pad_c + dj: pad_c + dj + w]
    za = (syy * z_x - sxy * z_y) / det
    zb = (sxx * z_y - sxy * z_x) / det
    slope = np.degrees(np.arctan(np.hypot(za, zb)))
    slope[~complete] = np.nan
    return slope


def box_sums(values: np.ndarray, half: int) -> tuple[np.ndarray, np.ndarray]:
    """Nan-aware window sums over +-half rows/cols (exact integral images).
    Returns (weighted sum over finite entries, count of finite entries)."""
    known = np.isfinite(values).astype(np.float64)
    vs = np.where(np.isfinite(values), values, 0.0)

    def integ(a):
        return np.pad(np.cumsum(np.cumsum(a, axis=0), axis=1), ((1, 0), (1, 0)))

    iv, ik = integ(vs), integ(known)
    rows = np.arange(values.shape[0])
    cols = np.arange(values.shape[1])
    r0, r1 = np.maximum(rows - half, 0), np.minimum(rows + half + 1, values.shape[0])
    c0, c1 = np.maximum(cols - half, 0), np.minimum(cols + half + 1, values.shape[1])
    num = iv[r1][:, c1] - iv[r0][:, c1] - iv[r1][:, c0] + iv[r0][:, c0]
    den = ik[r1][:, c1] - ik[r0][:, c1] - ik[r1][:, c0] + ik[r0][:, c0]
    return num, den


def exact_edt_cells(mask: np.ndarray) -> np.ndarray:
    """Exact Euclidean distance transform on a square unit-pitch cell grid:
    distance between cell centres to the nearest True cell.
    Felzenszwalb & Huttenlocher lower envelope, rows then columns."""
    f = np.where(mask, 0.0, 1e18)
    for i in range(f.shape[0]):
        f[i] = _edt_1d_sq(f[i])
    out = np.empty_like(f)
    for j in range(f.shape[1]):
        out[:, j] = _edt_1d_sq(f[:, j])
    return np.sqrt(out)


def _edt_1d_sq(f: np.ndarray) -> np.ndarray:
    n = f.size
    d = np.empty(n)
    v = np.zeros(n, dtype=np.int64)
    z = np.full(n + 1, np.inf)
    z[0] = -np.inf
    k = 0
    for q in range(1, n):
        fq = f[q] + q * q
        s = (fq - (f[v[k]] + v[k] * v[k])) / (2.0 * (q - v[k]))
        while s <= z[k]:
            k -= 1
            s = (fq - (f[v[k]] + v[k] * v[k])) / (2.0 * (q - v[k]))
        k += 1
        v[k] = q
        z[k] = s
        z[k + 1] = np.inf
    k = 0
    for q in range(n):
        while z[k + 1] < q:
            k += 1
        d[q] = (q - v[k]) ** 2 + f[v[k]]
    return d


# ------------------------------------------------------------- table helpers

def _pixel_keys(start: int, stop: int, width: int) -> tuple[np.ndarray, np.ndarray]:
    return (np.repeat(np.arange(start, stop, dtype=np.int32)[:, None], width, axis=1).ravel(),
            np.tile(np.arange(width, dtype=np.int32), stop - start))


def _reason_expr(reasons: dict[str, str]) -> pl.Expr:
    segs = [pl.when(pl.col(c).is_null()).then(pl.lit(f'"{c}":"{reasons[c]}"')).otherwise(None)
            for c in reasons]
    return (pl.lit("{") + pl.concat_str(segs, separator=",", ignore_nulls=True).fill_null("")
            + pl.lit("}")).alias("missing_reason")


def _keep_any_value(frame: pl.DataFrame, cols: list[str]) -> pl.DataFrame:
    return (frame.with_columns(pl.any_horizontal([pl.col(c).is_not_null() for c in cols]).alias("__k"))
                 .filter(pl.col("__k")).drop("__k"))


def _reuse_meta(path: Path, name: str) -> dict | None:
    """Idempotent builds: if the table parquet already exists, reuse it (check()
    re-verifies hash/rows/contract and spot checks later)."""
    if not path.exists():
        return None
    lf = pl.scan_parquet(path)
    value_cols = TABLES[name][1]
    rows = lf.select(pl.len()).collect().item()
    nulls = lf.select([pl.col(c).null_count().alias(c) for c in value_cols]
                      + [pl.col("missing_reason").null_count().alias("missing_reason")]).collect().row(0, named=True)
    reasons = {str(k): int(v) for k, v in
               lf.group_by("missing_reason").len().collect().iter_rows()}
    return {"rows": rows, "sha256": sha256(path), "bytes": path.stat().st_size,
            "nullCounts": nulls, "reasonCounts": reasons}


# ---------------------------------------------------------- build: 20 m layer

def _null_mask(values: np.ndarray, nodata) -> np.ndarray:
    m = ~np.isfinite(values.astype(np.float64))
    if nodata is not None and math.isfinite(float(nodata)):
        m |= values == np.asarray(nodata, dtype=values.dtype)
    return m


def build_elevation_table(out_dir: Path, ldem, ldec, lpsr) -> dict:
    path = out_dir / "ldem-80s-20mpp.parquet"
    reused = _reuse_meta(path, "ldem-80s-20mpp.parquet")
    if reused is not None:
        return reused
    reasons = dict(TABLES["ldem-80s-20mpp.parquet"][2])
    if ldec is None:
        reasons["lola_spot_count"] = "source-not-fetched"

    def frames():
        step = 512
        for start in range(0, ldem.height, step):
            stop = min(start + step, ldem.height)
            dem = read_block(ldem, start, stop).astype(np.float32).ravel()
            if ldec is not None:
                cnt = read_block(ldec, start, stop).ravel()
            else:
                cnt = np.full(dem.shape, -1, dtype=np.int32)
            psr = read_block(lpsr, start, stop).ravel()
            keys_r, keys_s = _pixel_keys(start, stop, ldem.width)
            dem_null = _null_mask(dem, ldem.nodata)
            cnt_null = np.full(dem.shape, True) if ldec is None else (
                _null_mask(cnt.astype(np.float64), ldec.nodata)
                if np.issubdtype(cnt.dtype, np.floating) else cnt == ldec.nodata)
            psr_null = _null_mask(psr.astype(np.float64), lpsr.nodata)
            frame = pl.DataFrame({
                "source_line": keys_r, "source_sample": keys_s,
                "__e": dem, "__c": cnt.astype(np.int64), "__p": psr.astype(np.float64),
            })
            frame = frame.with_columns([
                pl.when(pl.Series(dem_null)).then(None)
                .otherwise(pl.col("__e")).alias("elevation_m"),
                pl.when(pl.Series(cnt_null)).then(None)
                .otherwise(pl.col("__c").cast(pl.Int64)).alias("lola_spot_count"),
                pl.when(pl.Series(psr_null)).then(None)
                .otherwise((pl.col("__p") > 0).cast(pl.Int8)).alias("psr_2023"),
            ]).drop(["__e", "__c", "__p"])
            frame = frame.with_columns(_reason_expr(reasons))
            yield _keep_any_value(frame, ["elevation_m", "lola_spot_count", "psr_2023"])

    return write_batches(path, frames())


def build_roughness_table(out_dir: Path) -> dict:
    reused = _reuse_meta(out_dir / "ldrm-80s-50mpp.parquet", "ldrm-80s-50mpp.parquet")
    if reused is not None:
        return reused
    raw = SNAP / LDEM_2023
    slp = rio.open(raw / "LDRM_80S_50MPP_ADJ_SLP_100M.TIF")
    rms = rio.open(raw / "LDRM_80S_50MPP_ADJ_RMSD_100M.TIF")
    if (slp.width, slp.height, slp.transform) != (rms.width, rms.height, rms.transform):
        raise ValueError("LDRM slope/roughness grids differ")
    if abs(abs(slp.transform.a) - 50.0) > 1.0:
        raise ValueError(f"unexpected LDRM pixel size {slp.transform.a}")
    path = out_dir / "ldrm-80s-50mpp.parquet"
    reasons = TABLES["ldrm-80s-50mpp.parquet"][2]

    def frames():
        step = 1024
        for start in range(0, slp.height, step):
            stop = min(start + step, slp.height)
            s = read_block(slp, start, stop).astype(np.float32).ravel()
            r = read_block(rms, start, stop).astype(np.float32).ravel()
            keys_r, keys_s = _pixel_keys(start, stop, slp.width)
            s_null = _null_mask(s, slp.nodata)
            r_null = _null_mask(r, rms.nodata)
            frame = pl.DataFrame({
                "source_line": keys_r, "source_sample": keys_s,
                "__s": s, "__r": r,
            })
            frame = frame.with_columns([
                pl.when(pl.Series(s_null)).then(None)
                .otherwise(pl.col("__s")).alias("slope_100m_deg"),
                pl.when(pl.Series(r_null)).then(None)
                .otherwise(pl.col("__r")).alias("rough_rms_100m_m"),
            ]).drop(["__s", "__r"]).with_columns(_reason_expr(reasons))
            yield _keep_any_value(frame, ["slope_100m_deg", "rough_rms_100m_m"])

    return write_batches(path, frames())


def build_240mpp_table(out_dir: Path) -> dict:
    reused = _reuse_meta(out_dir / "ldem-60s-240mpp.parquet", "ldem-60s-240mpp.parquet")
    if reused is not None:
        return reused
    ds = rio.open(SNAP / LDEM_2023 / "LDEM_60S_240MPP_ADJ.TIF")
    step = abs(ds.transform.a)
    path = out_dir / "ldem-60s-240mpp.parquet"

    def frames():
        step_rows, border = 1024, int(math.ceil(1000.0 / step)) + 1
        for start in range(0, ds.height, step_rows):
            stop = min(start + step_rows, ds.height)
            lo, hi = max(0, start - border), min(ds.height, stop + border)
            patch = read_block(ds, lo, hi).astype(np.float64)
            if ds.nodata is not None:
                patch = np.where(patch == ds.nodata, np.nan, patch)
            slope = plane_fit_slope_block(patch, step, 1000.0)
            core = slope[start - lo: start - lo + (stop - start), 0: ds.width]
            dem = read_block(ds, start, stop).astype(np.float32).ravel()
            keys_r, keys_s = _pixel_keys(start, stop, ds.width)
            dem_null = _null_mask(dem, ds.nodata)
            frame = pl.DataFrame({
                "source_line": keys_r, "source_sample": keys_s,
                "__e": dem, "__sf": core.astype(np.float32).ravel(),
                "__sm": np.isfinite(core).ravel(),
            })
            frame = frame.with_columns([
                pl.when(pl.Series(dem_null)).then(None)
                .otherwise(pl.col("__e")).alias("elevation_m"),
                pl.when(pl.col("__sm")).then(pl.col("__sf")).otherwise(None)
                .alias("slope_2km_eva_deg"),
            ]).drop(["__e", "__sf", "__sm"])
            frame = frame.with_columns(_reason_expr(TABLES["ldem-60s-240mpp.parquet"][2]))
            yield _keep_any_value(frame, ["elevation_m", "slope_2km_eva_deg"])

    return write_batches(path, frames())


def build_psr_grid_table(out_dir: Path, lpsr) -> dict:
    reused = _reuse_meta(out_dir / "psr-2km-1kmgrid.parquet", "psr-2km-1kmgrid.parquet")
    if reused is not None:
        return reused
    """psr_frac_2km and psr_dist_km on a 1 km cell grid, aggregated exactly
    from the native 20 m LPSR mask (window stated; no value resampling)."""
    step = abs(lpsr.transform.a)
    if abs(step - 20.0) > 1.0:
        raise ValueError(f"unexpected LPSR pixel size {step}")
    half = int(round(1000.0 / step))
    x_m, y_m = cog_pixel_xy(lpsr)
    cx, cy = x_m[len(x_m) // 2], y_m[len(y_m) // 2]
    k = int(math.floor(min(len(x_m), len(y_m)) * step / 2 / 1000.0))
    cell_x = np.arange(-k, k + 1, dtype=np.float64) * 1000.0 + cx
    cell_y = np.arange(-k, k + 1, dtype=np.float64) * 1000.0 + cy
    rows_i = np.abs(cell_y[:, None] - y_m[None, :]).argmin(axis=1)
    cols_i = np.abs(cell_x[:, None] - x_m[None, :]).argmin(axis=1)
    known_frac = np.zeros((cell_y.size, cell_x.size), dtype=bool)
    frac = np.full((cell_y.size, cell_x.size), np.nan)
    done = np.zeros(cell_y.size, dtype=bool)
    step_rows = 512
    for start in range(0, lpsr.height, step_rows):
        stop = min(start + step_rows, lpsr.height)
        lo, hi = max(0, start - half), min(lpsr.height, stop + half)
        strip = read_block(lpsr, lo, hi).astype(np.float64)
        if lpsr.nodata is not None:
            strip = np.where(strip == lpsr.nodata, np.nan, strip)
        values = np.where(np.isfinite(strip), (strip > 0).astype(np.float64), np.nan)
        num, den = box_sums(values, half)
        col_bad = (cols_i - half < 0) | (cols_i + half >= lpsr.width)
        for out_r in np.flatnonzero((rows_i >= start) & (rows_i < stop)):
            if done[out_r]:
                continue
            r = int(rows_i[out_r]) - lo
            f = num[r, cols_i] / np.maximum(den[r, cols_i], 1.0)
            f[den[r, cols_i] == 0] = np.nan
            f[col_bad] = np.nan
            if int(rows_i[out_r]) - half < 0 or int(rows_i[out_r]) + half >= lpsr.height:
                f[:] = np.nan
            frac[out_r] = f
            known_frac[out_r] = np.isfinite(frac[out_r])
            done[out_r] = True
    if not done.all():
        raise ValueError("some 1 km cells never computed; block loop incomplete")
    sources_mask = known_frac & (frac > 0)
    if not sources_mask.any():
        raise ValueError("no PSR cells found; LPSR read failed?")
    dist_cells = exact_edt_cells(sources_mask)
    dist = np.where(known_frac, dist_cells, np.nan)
    frame = pl.DataFrame({
        "x_m": np.repeat(cell_x[None, :], cell_y.size, axis=0).ravel(),
        "y_m": np.repeat(cell_y[:, None], cell_x.size, axis=1).ravel(),
        "psr_frac_2km": np.where(known_frac, frac, np.nan).ravel(),
        "psr_dist_km": dist.ravel(),
    })
    frame = (frame.with_columns([
        pl.when(pl.col(c).is_finite()).then(pl.col(c)).otherwise(None).alias(c)
        for c in ("psr_frac_2km", "psr_dist_km")
    ]).with_columns(_reason_expr(TABLES["psr-2km-1kmgrid.parquet"][2])))
    result = write_batches(out_dir / "psr-2km-1kmgrid.parquet", iter([frame]))
    result.update({
        "body": "Moon",
        "product": "derived from LPSR_80S_20MPP_ADJ.TIF (PSR mask, Barker et al. 2023)",
        "grid": (f"1 km square cell grid in the same south-polar stereographic map metres as the LPSR "
                 f"canvas; cell centres anchored at the canvas centre and spaced 1000 m "
                 f"({cell_x.size}x{cell_y.size} cells); each statistic uses the native 20 m pixels "
                 f"around the nearest pixel centre"),
        "units": "psr_frac_2km: fraction 0..1; psr_dist_km: km, cell centre to cell centre",
        "timeSupport": "static (Barker et al. 2023)",
        "derived": {
            "psr_frac_2km": (f"fraction of the native 20 m LPSR pixels inside a square window of "
                             f"+-1000 m in map metres centred on the cell centre ({2 * half + 1} px box, "
                             f"nan-aware mean). Square window, not the circular window the LDRM products "
                             f"use - stated explicitly"),
            "psr_dist_km": ("straight-line distance from each 1 km cell centre to the centre of the "
                            "nearest 1 km cell with psr_frac_2km > 0, exact Euclidean distance transform "
                            "(Felzenszwalb-Huttenlocher). Quantised to the 1 km cell grid: true distance "
                            "to the PSR boundary is at most ~0.71 km smaller"),
        },
        "missingReason": {"psr_frac_2km": "psr-window-truncated (cell window clipped at the raster edge)",
                          "psr_dist_km": "psr-window-truncated (cell window clipped at the raster edge)"},
        "madeUnder": ("areal aggregation of the native LPSR mask to the 2 km feature support; no "
                      "resampling to other grids, no Earth H3"),
    })
    return result


def build_south_pole(report: dict) -> None:
    out_dir = OUT / LDEM_2023
    out_dir.mkdir(parents=True, exist_ok=True)
    raw = SNAP / LDEM_2023
    ldem = rio.open(raw / "LDEM_80S_20MPP_ADJ.TIF")
    ldec_path = raw / "LDEC_80S_20MPP_ADJ.TIF"
    ldec = rio.open(ldec_path) if ldec_path.exists() else None
    lpsr = rio.open(raw / "LPSR_80S_20MPP_ADJ.TIF")
    for other, name in [(lpsr, "LPSR")] + ([(ldec, "LDEC")] if ldec is not None else []):
        if (other.width, other.height) != (ldem.width, ldem.height) \
                or other.transform != ldem.transform or other.crs != ldem.crs:
            raise ValueError(f"{name} grid differs from LDEM_80S_20MPP")
    px = abs(ldem.transform.a)
    if abs(px - 20.0) > 1.0:
        raise ValueError(f"unexpected LDEM pixel size {px}")
    x_m, y_m = cog_pixel_xy(ldem)
    grid_meta = (f"South polar stereographic, {px:g} m/px, pixel centres, canvas {ldem.width}x"
                 f"{ldem.height}; south-polar-stereographic CRS from the GeoTIFF (DE421 MOON_ME); "
                 f"x_m = {ldem.transform.c} + (sample + 0.5) * {abs(ldem.transform.a):g}, "
                 f"y_m = {ldem.transform.f} + (line + 0.5) * {ldem.transform.e:g}")

    elev = build_elevation_table(out_dir, ldem, ldec, lpsr)
    elev.update({
        "body": "Moon",
        "product": "LDEM_80S_20MPP_ADJ + LDEC_80S_20MPP_ADJ + LPSR_80S_20MPP_ADJ (Barker et al. 2023 set)",
        "grid": grid_meta,
        "units": ("elevation_m: metres; lola_spot_count: LOLA shots per pixel (native support count, "
                  "0 = fully interpolated); psr_2023: binary 0/1"),
        "timeSupport": "static (Barker et al. 2023 adjusted-track set, DE421 MOON_ME)",
        "pixelRule": ("keys are zero-based pixel indices of the native canvas; elevation at the finest "
                      "practical resolution offered by the product (20 m/px, raw 2.6 GB, chosen to stay "
                      "under the 20 GB local raw cap); rows whose every value is nodata (canvas corners "
                      "outside the 80S cap) are dropped"),
        "reference": "Barker et al. 2023 Planet. Sci. J. 4:183, doi:10.3847/PSJ/acf3e1",
    })
    report["outputs"]["ldem-80s-20mpp.parquet"] = elev

    rough = build_roughness_table(out_dir)
    slp = rio.open(raw / "LDRM_80S_50MPP_ADJ_SLP_100M.TIF")
    rough.update({
        "body": "Moon",
        "product": "LDRM_80S_50MPP_ADJ_SLP_100M + LDRM_80S_50MPP_ADJ_RMSD_100M",
        "grid": (f"South polar stereographic, {abs(slp.transform.a):g} m/px, pixel centres, canvas "
                 f"{slp.width}x{slp.height}; same CRS family as LDEM"),
        "layers": {
            "slope_100m_deg": ("published slope of the least-squares plane inside a circular window of "
                               "diameter 100 m (baseline 100 m), 50 m/px grid"),
            "rough_rms_100m_m": ("published RMS height deviation between a central point and the "
                                 "surrounding annulus of diameter 100 m, 50 m/px grid"),
        },
        "units": "slope_100m_deg: degrees; rough_rms_100m_m: metres",
        "timeSupport": "static (Barker et al. 2023)",
        "reference": "Barker et al. 2023 PSJ 4:183",
    })
    report["outputs"]["ldrm-80s-50mpp.parquet"] = rough

    t240 = build_240mpp_table(out_dir)
    d60 = rio.open(raw / "LDEM_60S_240MPP_ADJ.TIF")
    t240.update({
        "body": "Moon",
        "product": "LDEM_60S_240MPP_ADJ + derived slope",
        "grid": (f"South polar stereographic, {abs(d60.transform.a):g} m/px, pixel centres, canvas "
                 f"{d60.width}x{d60.height}; same CRS family as LDEM"),
        "units": "elevation_m: metres; slope_2km_eva_deg: degrees",
        "timeSupport": "static (Barker et al. 2023)",
        "derived": {
            "slope_2km_eva_deg": (
                "least-squares plane fit over all native pixels whose centre lies within 1000 m of the "
                f"output pixel centre in map-projection metres ({len(disc_stencil(1000.0, abs(d60.transform.a)))} px "
                "stencil, diameter ~= 2 km baseline). The product publishes plane-fit slopes only up to "
                "a 1600 m baseline, so the 2 km EVA baseline is computed here exactly as declared; the "
                "published 1600 m layer was NOT relabelled"),
        },
        "note": ("EVA slope support is 2 km; the 240 m/px canvas keeps the window arithmetic exact and "
                 "cheap while covering the full 60S-90S extent"),
    })
    report["outputs"]["ldem-60s-240mpp.parquet"] = t240

    report["outputs"]["psr-2km-1kmgrid.parquet"] = build_psr_grid_table(out_dir, lpsr)


# ------------------------------------------------- build: GDR and illumination

def build_gdr(report: dict) -> None:
    out_dir = OUT / GDR
    out_dir.mkdir(parents=True, exist_ok=True)
    raw = SNAP / GDR
    lbl = parse_pds3_label((raw / "ldem_4.lbl").read_text(encoding="utf-8"))
    image = lbl["objects"]["IMAGE"]
    proj = lbl["objects"]["IMAGE_MAP_PROJECTION"]
    if image["SAMPLE_TYPE"] != "LSB_INTEGER" or int(image["SAMPLE_BITS"]) != 16:
        raise ValueError("unexpected ldem_4 byte layout")
    scale, offset = float(image["SCALING_FACTOR"]), float(image["OFFSET"])
    if scale != 0.5 or offset != MOON_R_M:
        raise ValueError(f"unexpected ldem_4 scaling {scale} / offset {offset}; review label")
    lines, samples = int(image["LINES"]), int(image["LINE_SAMPLES"])
    res = lines / 180.0
    if samples != 360 * res:
        raise ValueError("ldem_4 is not square in px/deg")
    if proj["MAP_PROJECTION_TYPE"] != "SIMPLE CYLINDRICAL":
        raise ValueError("unexpected ldem_4 projection")
    arr = np.asarray(np.memmap(raw / "ldem_4.img", dtype="<i2", mode="r",
                               shape=(lines, samples)))
    # label: DN * SCALING_FACTOR + OFFSET = radius in metres on the 1737.4 km sphere
    values = arr.astype(np.float64) * scale + offset - MOON_R_M
    null = arr == -32768
    dmin = float(image["MINIMUM"]) * scale + offset - MOON_R_M
    dmax = float(image["MAXIMUM"]) * scale + offset - MOON_R_M
    if null.sum() == 0 and (abs(values.min() - dmin) > 5.0 or abs(values.max() - dmax) > 5.0):
        raise ValueError(f"ldem_4 extrema {values.min():.0f}/{values.max():.0f} differ from label")
    lat = 90.0 - (np.arange(lines, dtype=np.float64) + 0.5) / res
    lon = (np.arange(samples, dtype=np.float64) + 0.5) / res - 180.0
    LAT, LON = np.meshgrid(lat, lon, indexing="ij")
    df = pl.DataFrame({
        "lat_deg": LAT.ravel().astype(np.float32),
        "lon_deg": LON.ravel().astype(np.float32),
        "elevation_m": np.where(null, np.nan, values).ravel().astype(np.float32),
        "__null": null.ravel(),
    }).with_columns([
        pl.when(pl.col("__null")).then(None).otherwise(pl.col("elevation_m")).alias("elevation_m"),
        pl.when(pl.col("__null")).then(pl.lit('{"elevation_m":"source-no-data-constant"}'))
        .otherwise(pl.lit("{}")).alias("missing_reason"),
    ]).drop("__null")
    result = write_batches(out_dir / "ldem-gdr-4ppd.parquet", iter([df]))
    result.update({
        "body": "Moon",
        "product": str(lbl["PRODUCT_ID"]),
        "grid": (f"SIMPLE CYLINDRICAL, {res:g} px/deg ({lines}x{samples}), planetocentric, north-up, "
                 f"lon -180..180 east-positive; lat_deg column = 90 - (line + 0.5)/{res:g}, "
                 f"lon_deg column = (sample + 0.5)/{res:g} - 180 (LINE_PROJECTION_OFFSET "
                 f"{proj['LINE_PROJECTION_OFFSET']}, SAMPLE_PROJECTION_OFFSET "
                 f"{proj['SAMPLE_PROJECTION_OFFSET']}, {proj.get('COORDINATE_SYSTEM_NAME', '')}); "
                 f"scaling {scale} m/DN, offset {offset} (radius), {int(null.sum())} null-DN pixels"),
        "units": "elevation_m: metres relative to the radius-1737.4 km reference sphere (radius minus datum)",
        "timeSupport": "static LOLA GDR (mission-accumulated)",
        "derived": {},
        "missingReason": {"elevation_m": "source-no-data-constant (DN -32768)"},
        "rowsNull": int(null.sum()),
        "pixelRule": "keys are pixel centres of the native grid; no interpolation across grid nodes",
        "plannedFeature": "relief_ellipse (elevation range inside an ellipse; computed downstream)",
    })
    report["outputs"]["ldem-gdr-4ppd.parquet"] = result


def build_illumination_tables(report: dict) -> None:
    out_dir = OUT / ILLUM
    out_dir.mkdir(parents=True, exist_ok=True)
    for kind in ("85s_060m", "75s_120m"):
        stem = f"avgvisib_{kind}_201608"
        table_name = f"avgvisib-{kind.replace('_', '-')}.parquet"
        sun, sun_meta = open_lbl_img(SNAP / ILLUM / f"{stem}.img", SNAP / ILLUM / f"{stem}.lbl")
        earth, earth_meta = open_lbl_img(SNAP / ILLUM / f"{stem}_earth.img",
                                         SNAP / ILLUM / f"{stem}_earth.lbl")
        for a, b, name in ((sun_meta, earth_meta, "earth"), (earth_meta, sun_meta, "sun")):
            if (a["lines"], a["samples"]) != (b["lines"], b["samples"]) \
                    or a["lineProjOffsetPx"] != b["lineProjOffsetPx"] \
                    or a["sampleProjOffsetPx"] != b["sampleProjOffsetPx"]:
                raise ValueError(f"{stem}: {name} grid differs from its companion")
        cal = calibrated_lbl_xy(sun_meta)
        cal_earth = calibrated_lbl_xy(earth_meta)
        if abs(cal["xShiftPx"] - cal_earth["xShiftPx"]) > 1e-9 or cal["ySign"] != cal_earth["ySign"]:
            raise ValueError(f"{stem}: sun/earth pixel conventions disagree")
        path = out_dir / table_name
        reused = _reuse_meta(path, table_name)
        if reused is not None:
            report["outputs"][table_name] = reused
            continue
        sun_raw = np.asarray(sun)
        earth_raw = np.asarray(earth)
        sun_v = (sun_raw.astype(np.float64) * sun_meta["scaling"] * 100.0)
        earth_v = (earth_raw.astype(np.float64) * earth_meta["scaling"] * 100.0)
        reasons = TABLES[table_name][2]

        def frames():
            step = 512
            for start in range(0, sun_meta["lines"], step):
                stop = min(start + step, sun_meta["lines"])
                keys_r, keys_s = _pixel_keys(start, stop, sun_meta["samples"])
                frame = pl.DataFrame({
                    "source_line": keys_r, "source_sample": keys_s,
                    "__s": sun_v[start:stop].ravel(), "__e": earth_v[start:stop].ravel(),
                })
                sun_null = (sun_raw[start:stop] < 0).ravel()
                earth_null = (earth_raw[start:stop] < 0).ravel()
                frame = frame.with_columns([
                    pl.when(pl.Series(sun_null)).then(None)
                    .otherwise(pl.col("__s").cast(pl.Float32)).alias("illum_frac_pct"),
                    pl.when(pl.Series(earth_null)).then(None)
                    .otherwise(pl.col("__e").cast(pl.Float32)).alias("earth_vis_pct"),
                ]).drop(["__s", "__e"]).with_columns(_reason_expr(reasons))
                yield _keep_any_value(frame, ["illum_frac_pct", "earth_vis_pct"])

        result = write_batches(path, frames())
        result.update({
            "body": "Moon",
            "product": f"{sun_meta['product']} + {earth_meta['product']} ({sun_meta['dataSourceSet']})",
            "grid": (f"South polar stereographic, {sun_meta['mapScaleM']:g} m/px, pixel centres "
                     f"(pixel-registered), canvas {sun_meta['lines']}x{sun_meta['samples']}, "
                     f"{sun_meta['frame']}; x/y of pixel (line, sample): "
                     f"x_m = (sample - {sun_meta['sampleProjOffsetPx'] - cal['xShiftPx']:g}) * "
                     f"{sun_meta['mapScaleM']:g}, y_m = "
                     f"({'LIN...' if cal['ySign'] > 0 else 'row'})"
                     f"({sun_meta['lineProjOffsetPx']} - line) * {sun_meta['mapScaleM']:g}; convention "
                     f"calibrated against PROJ (xShiftPx={cal['xShiftPx']}, ySign={cal['ySign']}, "
                     f"worst residual {cal['worstResidualPx']:.3f} px)"),
            "units": ("illum_frac_pct: percent of simulation timesteps the pixel is at least partly "
                      "sunlit (DN * scaling * 100), 0..100; earth_vis_pct: percent of timesteps Earth "
                      "is above the local horizon (LOLA DEM horizons), 0..100"),
            "timeSupport": (f"static multi-year simulation of the {sun_meta['minLat']}.."
                            f"{sun_meta['maxLat']} deg cap (2016 release of the Mazarico et al. 2011 "
                            f"method, LDEM-based, DE421)"),
            "derived": {"earth_vis_pct": "companion _EARTH product; horizons derived from LOLA DEM"},
            "gaps": {
                "sun_elev_min": ("not published in this product family; minimum sun elevation stays a "
                                 "recorded gap, not computed or filled"),
                "product78_horizons": ("PGDA product 78 (5 m/pix site DEMs, Barker 2021) publishes DEMs, "
                                       "slopes and clones only - no standalone horizon files; the "
                                       "horizon-driven Earth-visibility product used here is the "
                                       "product-69 AVGVISIB_*_EARTH map; recorded on #99 and the PR"),
            },
            "missingReason": {"illum_frac_pct": "source-nodata (DN < 0)",
                              "earth_vis_pct": "source-nodata (DN < 0)"},
        })
        report["outputs"][table_name] = result


# ------------------------------------------------------------------ pipeline

def build() -> dict:
    inputs, gaps = verify_inputs()
    report = {
        "generatedAt": dt.datetime.now(dt.timezone.utc).isoformat(),
        "inputs": sorted(e["localPath"] for e in inputs),
        "runtimeStatus": "executed",
        "scientificStatus": "executed-unreviewed",
        "scope": ("LOLA south-pole and coarse global grids on their native projections; no resampling "
                  "to other grids or to Earth H3; no scoring, ranking or cross-body comparison; "
                  "time resolution: static products (at-most-monthly rule satisfied)"),
        "memoryPlan": "rasterio window reads + polars batched ParquetWriter, single process, <~2 GB working set",
        "outputs": {},
    }
    if gaps:
        report["gaps"] = [
            {"url": u, "reason": ("fetch deferred (orchestrator priority change: engine/workflow over "
                                  "coverage; large LDEC raster not fetched locally), so lola_spot_count "
                                  "is null with missing_reason 'source-not-fetched'; "
                                  "elevation/PSR columns are unaffected")}
            for u in gaps
        ]
    build_south_pole(report)
    build_gdr(report)
    build_illumination_tables(report)
    (OUT / LDEM_2023 / "preparation-report.json").write_text(json.dumps(report, indent=2) + "\n")
    return report


# ---------------------------------------------------------------------- check

def check() -> None:
    inputs, gaps = verify_inputs()
    report = json.loads((OUT / LDEM_2023 / "preparation-report.json").read_text())
    for name, meta in report["outputs"].items():
        path = OUT / TABLES[name][0] / name
        if sha256(path) != meta["sha256"] or path.stat().st_size != meta["bytes"]:
            raise ValueError(f"output hash/size mismatch: {name}")
        check_table(path, name, meta)
    spot_checks()
    note = f", {len(gaps)} deferred raw fetch(es): {gaps}" if gaps else ""
    print(f"check: PASS ({len(report['outputs'])} tables, {len(inputs)} licensed raw inputs{note})", flush=True)


def check_table(path: Path, name: str, meta: dict) -> None:
    _, value_cols, _reasons, key_cols = TABLES[name]
    lf = pl.scan_parquet(path)
    n = lf.select(pl.len()).collect().item()
    if n != meta["rows"]:
        raise ValueError(f"{name}: row count {n} != {meta['rows']}")
    for c in value_cols:
        lo, hi = PHYSICAL_RANGE[c]
        bad = lf.select(((pl.col(c) < lo) | (pl.col(c) > hi)).fill_null(False).sum()).collect().item()
        if bad:
            raise ValueError(f"{name}.{c}: {bad} rows outside physical range [{lo}, {hi}]")
    # streamed missing-reason contract: object keys == exactly that row's null value columns
    mismatches = 0
    bad_shape = 0
    step = 5_000_000
    for start in range(0, n, step):
        sl = lf.slice(start, step).select(*value_cols, "missing_reason").collect()
        mr = sl["missing_reason"]
        if mr.null_count() or not (mr.str.starts_with("{") & mr.str.ends_with("}")).all():
            bad_shape += int(mr.null_count() + (~((mr.str.starts_with("{") & mr.str.ends_with("}"))
                                                  .fill_null(False))).sum())
            continue
        for c in value_cols:
            mismatches += int((sl[c].is_null() != mr.str.contains(f'"{c}":"')).sum())
    if bad_shape:
        raise ValueError(f"{name}: {bad_shape} rows with a null or non-JSON-object missing_reason")
    if mismatches:
        raise ValueError(f"{name}: {mismatches} rows where missing_reason keys != null value columns")
    sampled = 64 if n > 5_000_000 else 1
    dup_q = lf.with_row_index("__i").filter((pl.col("__i") % pl.lit(sampled)) == 0) \
        .group_by(key_cols).len().filter(pl.col("len") > 1).select(pl.len())
    dups = dup_q.collect().item()
    if dups:
        raise ValueError(f"{name}: {dups} duplicate keys")
    print(f"PASS {name}: {n:,} rows; ranges/missing-reasons/keys OK", flush=True)


# ------------------------------------------------------------------ gazetteer

def _norm_name(s: str) -> str:
    return "".join(ch for ch in s.lower() if ch.isalnum())


def gazetteer_features(names: list[str], path: Path | None = None) -> dict[str, tuple[float, float, float | None]]:
    """Named features from the USGS Moon centre-points snapshot -> (lat, lon, diam_km).

    The snapshot is an ESRI shapefile (MOON_nomenclature_center_pts.zip) with
    lowercase attributes: name, center_lat, center_lon, diameter (km, or a
    non-numeric marker), longitude 0..360 east, latitude north-positive.
    Exact name matches win; for requested peaks whose Gazetteer name carries
    an M-suffix (e.g. "Malapert M"), the M-suffixed record is the fallback.
    """
    import shapefile  # pyshp

    if path is None:
        path = SNAP / NOMENCLATURE / "MOON_nomenclature_center_pts.zip"
    if not path.exists():
        raise FileNotFoundError(path)
    wanted = {_norm_name(n): n for n in names}
    out: dict[str, tuple[float, float, float | None]] = {}
    cands: dict[str, list[tuple[str, float, float, float | None, bool]]] = {k: [] for k in wanted}
    with zipfile.ZipFile(path) as zf, TemporaryDirectory() as tmp:
        shp = dbf = None
        for member in zf.namelist():
            low = member.lower()
            if low.endswith(".shp"):
                shp = Path(tmp) / "g.shp"
            elif low.endswith(".dbf"):
                dbf = Path(tmp) / "g.dbf"
        if shp is None or dbf is None:
            raise ValueError(f"gazetteer zip lacks shp/dbf members: {path}")
        shp.write_bytes(zf.read(next(m for m in zf.namelist() if m.lower().endswith(".shp"))))
        dbf.write_bytes(zf.read(next(m for m in zf.namelist() if m.lower().endswith(".dbf"))))
        reader = shapefile.Reader(shp=str(shp), dbf=str(dbf))
        fields = [f[0].lower() for f in reader.fields[1:]]
        if not ("name" in fields and "center_lat" in fields and "center_lon" in fields):
            raise ValueError(f"gazetteer attributes differ from expectation: {fields}")
        i_name, i_lat, i_lon = fields.index("name"), fields.index("center_lat"), fields.index("center_lon")
        i_diam = fields.index("diameter") if "diameter" in fields else None
        for rec in reader.iterRecords():
            name = str(rec[i_name]).strip()
            if not name:
                continue
            key = _norm_name(name)
            if key not in wanted and not (key.endswith("m") and key[:-1] in wanted):
                continue
            lat = float(rec[i_lat])
            lon = float(rec[i_lon]) - 360.0 if float(rec[i_lon]) > 180.0 else float(rec[i_lon])
            diam = None
            if i_diam is not None:
                try:
                    diam = float(rec[i_diam])
                except (TypeError, ValueError):
                    diam = None
            cands[key if key in wanted else key[:-1]].append((name, lat, lon, diam))
    for key, req in wanted.items():
        got = cands.get(key, [])
        if not got:
            raise ValueError(f"gazetteer lacks {req!r}")
        exact = [g for g in got if _norm_name(g[0]) == key]
        m_suffixed = [g for g in got if _norm_name(g[0]) == key + "m"]
        pick = exact[0] if exact else (m_suffixed[0] if m_suffixed else sorted(got, key=lambda g: g[0])[0])
        out[req] = (pick[1], pick[2], pick[3])
    return out


# ------------------------------------------------------------------ spot checks

def _raw_value_at(ds, row: int, col: int) -> float:
    val = float(ds.read(1, window=rio.windows.Window(col, row, 1, 1))[0, 0])
    if ds.nodata is not None and val == ds.nodata:
        return float("nan")
    return val


def _annulus_median(ds, row: int, col: int, r_in_m: float, r_out_m: float) -> float:
    px = abs(ds.transform.a)
    r_in, r_out = int(r_in_m / px), int(r_out_m / px)
    pad = r_out + 1
    win = rio.windows.Window(col - pad, row - pad, 2 * pad + 1, 2 * pad + 1)
    patch = ds.read(1, window=win).astype(np.float64)
    if ds.nodata is not None:
        patch = np.where(patch == ds.nodata, np.nan, patch)
    yy, xx = np.mgrid[-pad:pad + 1, -pad:pad + 1]
    ring = (np.hypot(yy, xx) >= r_in) & (np.hypot(yy, xx) <= r_out)
    vals = patch[ring & np.isfinite(patch)]
    return float(np.median(vals)) if vals.size else float("nan")


def spot_checks() -> None:
    """>= 5 raw spot checks at named south-polar features."""
    raw = SNAP / LDEM_2023
    ldem = rio.open(raw / "LDEM_80S_20MPP_ADJ.TIF")
    ldec_path = raw / "LDEC_80S_20MPP_ADJ.TIF"
    ldec = rio.open(ldec_path) if ldec_path.exists() else None
    lpsr = rio.open(raw / "LPSR_80S_20MPP_ADJ.TIF")
    slp = rio.open(raw / "LDRM_80S_50MPP_ADJ_SLP_100M.TIF")
    feats = gazetteer_features(["Shackleton", "Malapert", "Haworth", "Shoemaker",
                                "de Gerlache", "Cabeus"])
    tbl = pl.scan_parquet(OUT / LDEM_2023 / "ldem-80s-20mpp.parquet")

    def table_row(row: int, col: int) -> dict:
        sel = tbl.filter((pl.col("source_line") == row)
                         & (pl.col("source_sample") == col)).collect()
        if sel.height != 1:
            raise ValueError(f"elevation table pixel ({row},{col}): {sel.height} rows")
        return {c: sel[c][0] for c in sel.columns}

    # 1) Shackleton: named point maps to a valid pixel; floor below the rim annulus;
    #    table elevation AND raw LDEC spot count both tally (count only if the
    #    deferred LDEC raster is present locally)
    lat, lon, _ = feats["Shackleton"]
    row, col = cog_latlon_to_pixel(ldem, lat, lon)
    t = table_row(row, col)
    raw_elev = _raw_value_at(ldem, row, col)
    if t["elevation_m"] is None or not math.isclose(t["elevation_m"], raw_elev, abs_tol=1e-4):
        raise ValueError(f"Shackleton: table {t['elevation_m']} != raw {raw_elev}")
    if ldec is not None:
        raw_cnt = _raw_value_at(ldec, row, col)
        if not (math.isnan(raw_cnt) and t["lola_spot_count"] is None) \
                and int(raw_cnt) != t["lola_spot_count"]:
            raise ValueError(f"Shackleton: table count {t['lola_spot_count']} != raw {raw_cnt}")
    elif t["lola_spot_count"] is not None:
        raise ValueError("Shackleton: lola_spot_count set although LDEC was not fetched")
    rim = _annulus_median(ldem, row, col, 2500, 6000)
    if not (np.isfinite(raw_elev) and raw_elev < rim - 100.0):
        raise ValueError(f"Shackleton floor {raw_elev:.0f} m not below rim {rim:.0f} m")
    print(f"spot 1 OK: Shackleton ({lat:.2f},{lon:.2f}) floor {raw_elev:.0f} m vs rim {rim:.0f} m, "
          f"count {t['lola_spot_count']}; table==raw", flush=True)

    # 2) Shackleton floor: >90% PSR in raw LPSR 2023 and the table flag agrees
    #    (crater radius ~10.5 km, so a +-400 m ring is interior; raw probe of the
    #    centre window may not always be perfectly shadowed, the annulus median
    #    below in spot 1 is the elevation test)
    pad = 20
    win = rio.windows.Window(col - pad, row - pad, 2 * pad + 1, 2 * pad + 1)
    psr_patch = lpsr.read(1, window=win).astype(np.float64)
    if lpsr.nodata is not None:
        psr_patch = np.where(psr_patch == lpsr.nodata, np.nan, psr_patch)
    frac_psr = float(np.nanmean(np.where(np.isfinite(psr_patch), (psr_patch > 0).astype(float), np.nan)))
    if frac_psr < 0.9:
        raise ValueError(f"Shackleton floor ring only {frac_psr:.0%} PSR in raw LPSR_2023")
    if table_row(row, col)["psr_2023"] != 1:
        raise ValueError("table psr_2023 at Shackleton != 1")
    print(f"spot 2 OK: Shackleton floor {frac_psr:.0%} PSR (raw), table psr_2023=1", flush=True)

    # 3) Malapert: illumination + Earth visibility table == raw at the label-mapped pixel
    lat, lon, _ = feats["Malapert"]
    im, im_meta = open_lbl_img(SNAP / ILLUM / "avgvisib_85s_060m_201608.img",
                               SNAP / ILLUM / "avgvisib_85s_060m_201608.lbl")
    cal = calibrated_lbl_xy(im_meta)
    irow, icol = lbl_latlon_to_pixel(im_meta, cal, lat, lon)
    dn_sun = int(np.asarray(im)[irow, icol])
    dn_earth = int(_illum_dn(SNAP / ILLUM, "avgvisib_85s_060m_201608_earth", irow, icol))
    if dn_sun < 0 or dn_earth < 0:
        raise ValueError(f"Malapert pixel ({irow},{icol}) is nodata in the raw illumination maps")
    isel = pl.scan_parquet(OUT / ILLUM / "avgvisib-85s-060m.parquet").filter(
        (pl.col("source_line") == irow) & (pl.col("source_sample") == icol)).collect()
    if isel.height != 1:
        raise ValueError(f"illumination table lacks Malapert pixel ({irow},{icol})")
    exp_sun, exp_earth = dn_sun * im_meta["scaling"] * 100.0, dn_earth * im_meta["scaling"] * 100.0
    if not (math.isclose(isel["illum_frac_pct"][0], exp_sun, abs_tol=1e-5)
            and math.isclose(isel["earth_vis_pct"][0], exp_earth, abs_tol=1e-5)):
        raise ValueError(f"Malapert illum mismatch: table {isel['illum_frac_pct'][0]}/"
                         f"{isel['earth_vis_pct'][0]} vs raw {exp_sun}/{exp_earth}")
    phys = 85.0 <= exp_sun <= 95.0 and 20.0 <= exp_earth <= 90.0
    if not phys:
        print(f"spot 3 NOTE: Malapert values {exp_sun:.2f}%/{exp_earth:.2f}% outside expected band", flush=True)
    print(f"spot 3 OK: Malapert illum {exp_sun:.2f}% / earth-vis {exp_earth:.2f}%, table==raw", flush=True)

    # 4) slope_100m at Malapert: table == raw
    lrow, lcol = cog_latlon_to_pixel(slp, lat, lon)
    raw_slope = _raw_value_at(slp, lrow, lcol)
    ssel = pl.scan_parquet(OUT / LDEM_2023 / "ldrm-80s-50mpp.parquet").filter(
        (pl.col("source_line") == lrow) & (pl.col("source_sample") == lcol)).collect()
    if ssel.height != 1 or not math.isclose(ssel["slope_100m_deg"][0], raw_slope, abs_tol=1e-4):
        raise ValueError(f"Malapert slope_100m table {ssel['slope_100m_deg'][0]} != raw {raw_slope}")
    print(f"spot 4 OK: Malapert slope_100m {raw_slope:.4f} deg, table==raw", flush=True)

    # 5) Tycho (outside the polar canvases, so GDR-only): the table value at the
    #    crater equals the raw DN-derived value; physical sanity: negative (below datum)
    gdr_lbl = parse_pds3_label((SNAP / GDR / "ldem_4.lbl").read_text())
    glines = int(gdr_lbl["objects"]["IMAGE"]["LINES"])
    gsamples = int(gdr_lbl["objects"]["IMAGE"]["LINE_SAMPLES"])
    garr = np.asarray(np.memmap(SNAP / GDR / "ldem_4.img", dtype="<i2", mode="r",
                                shape=(glines, gsamples))).astype(np.float64)
    g_scale = float(gdr_lbl["objects"]["IMAGE"]["SCALING_FACTOR"])
    g_off = float(gdr_lbl["objects"]["IMAGE"]["OFFSET"])
    g_res = glines / 180.0
    grow = int(round((90.0 + 43.31) * g_res - 0.5))
    gcol = int(round((11.36 + 180.0) * g_res - 0.5))
    gval = garr[grow, gcol] * g_scale + g_off - MOON_R_M
    if int(garr[grow, gcol]) == -32768:
        raise ValueError("Tycho GDR pixel is the null constant")
    tsel = pl.scan_parquet(OUT / GDR / "ldem-gdr-4ppd.parquet").filter(
        (pl.col("lat_deg") == float(np.float32(90.0 - (grow + 0.5) / g_res)))
        & (pl.col("lon_deg") == float(np.float32((gcol + 0.5) / g_res - 180.0)))).collect()
    if tsel.height != 1 or tsel["elevation_m"][0] is None \
            or not math.isclose(tsel["elevation_m"][0], gval, abs_tol=0.5):
        raise ValueError(f"GDR table at Tycho pixel ({grow},{gcol}) = {tsel['elevation_m'][0] if tsel.height else 'missing'}, raw {gval}")
    print(f"spot 5 OK: Tycho GDR pixel ({grow},{gcol}) elev {gval:.1f} m, table==raw", flush=True)

    # 6) Haworth, Shoemaker, de Gerlache: placement resolves to valid table pixels
    for name in ("Haworth", "Shoemaker", "de Gerlache"):
        flat, flon, _d = feats[name]
        prow, pcol = cog_latlon_to_pixel(ldem, flat, flon)
        t = table_row(prow, pcol)
        if t["elevation_m"] is None:
            raise ValueError(f"{name}: no elevation at ({prow},{pcol})")
        print(f"spot 6 OK: {name} ({flat:.2f},{flon:.2f}) -> pixel ({prow},{pcol}), "
              f"elev {t['elevation_m']:.0f} m, count {t['lola_spot_count']}", flush=True)

    # 7) psr_frac_2km: recompute the box mean from raw for one grid cell
    cell = pl.read_parquet(OUT / LDEM_2023 / "psr-2km-1kmgrid.parquet")
    c0 = cell.filter(pl.col("psr_frac_2km").is_not_null()).row(0, named=True)
    px20 = abs(ldem.transform.a)
    crow = int(round((c0["y_m"] - ldem.transform.f) / ldem.transform.e - 0.5))
    ccol = int(round((c0["x_m"] - ldem.transform.c) / ldem.transform.a - 0.5))
    half = int(round(1000.0 / px20))
    lo, hi = max(0, crow - half), min(ldem.height, crow + half + 1)
    clo, chi = max(0, ccol - half), min(ldem.width, ccol + half + 1)
    patch = lpsr.read(1, window=rio.windows.Window(clo, lo, chi - clo, hi - lo)).astype(np.float64)
    if lpsr.nodata is not None:
        patch = np.where(patch == lpsr.nodata, np.nan, patch)
    nb = int(np.isfinite(patch).sum())
    recomputed = float((patch > 0).sum() / nb) if nb else float("nan")
    if not (math.isfinite(recomputed) and math.isclose(recomputed, c0["psr_frac_2km"], abs_tol=1e-6)):
        raise ValueError(f"psr_frac_2km at ({c0['x_m']},{c0['y_m']}): table {c0['psr_frac_2km']} "
                         f"!= recomputed {recomputed}")
    print(f"spot 7 OK: psr_frac_2km {recomputed:.4f} recomputed from raw matches table", flush=True)

    # 8) illumination grid convention: the never-sunlit (DN==0) mask must agree with
    #    the independent 2023 LPSR mask over a 24x24 km window between Shackleton
    #    and de Gerlache (validates the PDS3 line/sample convention; mirrors fail)
    xg, yg = np.meshgrid(np.arange(-12000.0, 12000.0, 60.0), np.arange(15600.0, 39600.0, 60.0))
    lon8, lat8 = warp_transform(_stereo_crs(im_meta), _latlong_crs(im_meta["radiusM"]),
                                xg.ravel(), yg.ravel())
    col8 = np.round(im_meta["sampleProjOffsetPx"] + np.asarray(xg).ravel() / im_meta["mapScaleM"]).astype(int)
    row8 = np.round(im_meta["lineProjOffsetPx"] - np.asarray(yg).ravel() / im_meta["mapScaleM"]).astype(int)
    illum_shadow = np.asarray(im)[row8, col8] == 0
    qcol8 = np.floor((xg.ravel() - lpsr.transform.c) / lpsr.transform.a).astype(int)
    qrow8 = np.floor((yg.ravel() - lpsr.transform.f) / lpsr.transform.e).astype(int)
    lpatch8 = lpsr.read(1, window=rio.windows.Window(int(qcol8.min()), int(qrow8.min()),
                                                     int(qcol8.max()) - int(qcol8.min()) + 1,
                                                     int(qrow8.max()) - int(qrow8.min()) + 1))
    lmask8 = lpatch8[np.clip(qrow8 - int(qrow8.min()), 0, lpatch8.shape[0] - 1),
                     np.clip(qcol8 - int(qcol8.min()), 0, lpatch8.shape[1] - 1)] > 0
    agreement = float((illum_shadow == lmask8).mean())
    if agreement < 0.9:
        raise ValueError(f"illumination convention cross-check failed: mask agreement {agreement:.3f}")
    print(f"spot 8 OK: illum-vs-LPSR mask agreement {agreement:.4f} over {illum_shadow.size} px "
          f"(mirrors score <=0.79)", flush=True)


def _illum_dn(illum_dir: Path, stem: str, row: int, col: int) -> float:
    arr, _meta = open_lbl_img(illum_dir / f"{stem}.img", illum_dir / f"{stem}.lbl")
    return float(arr[row, col])


def main():
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument("action", choices=["fetch", "build", "check"])
    action = parser.parse_args().action
    if action == "fetch":
        for dataset, url in sources():
            print(fetch(dataset, url), flush=True)
    elif action == "build":
        report = build()
        for name, meta in report["outputs"].items():
            print(name, f"{meta.get('rows'):,}", meta.get("sha256"), flush=True)
    else:
        check()


if __name__ == "__main__":
    main()
