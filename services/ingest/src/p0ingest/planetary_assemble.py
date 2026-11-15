"""Assemble source-native planetary target profiles across data/targets/*.yaml (#154).

Builds data/snapshots/_derived/assembled/planetary-targets.parquet (and .meta.json)
from the prepared local planetary datasets without resampling to Earth H3 (ADR-0008),
without fabricating gap fills, without cross-body invented transforms, and without
extracting spatially unresolved TES tables ("pending projection review").
"""
from __future__ import annotations

import json
import math
import struct
from pathlib import Path

import numpy as np
import polars as pl
import yaml
from rasterio.crs import CRS
from rasterio.warp import transform as warp_transform

from .grid import DERIVED
from .snapshots import REPO

R_MARS_KM = 3396.0
R_MOON_KM = 1737.4

MOON_LATLONG_CRS = CRS.from_dict({"proj": "latlong", "R": 1_737_400.0})
MOON_STEREO_SOUTH_CRS = CRS.from_proj4(
    "+proj=stere +lat_0=-90 +lat_ts=-90 +lon_0=0 +R=1737400 +units=m +no_defs"
)

# Verified named-site associations between targets with published coordinates
# and the targeted Mars HiRISE/CTX/MEGDR32 DTM summary tables.
TARGET_TO_MARS_TOPO_SITE = {
    "mars-landing-curiosity": "gale-curiosity",
    "mars-feature-gale": "gale-curiosity",
    "mars-landing-perseverance": "jezero-perseverance",
    "mars-feature-jezero": "jezero-perseverance",
    "mars-landing-insight": "insight-elysium",
    "mars-feature-elysium-planitia": "insight-elysium",
    "mars-landing-opportunity": "meridiani-opportunity",
    "mars-feature-meridiani-planum": "meridiani-opportunity",
    "mars-landing-spirit": "gusev-spirit",
    "mars-feature-gusev": "gusev-spirit",
}


def norm_lon_180(lon_deg: float) -> float:
    return ((float(lon_deg) + 180.0) % 360.0) - 180.0


def norm_lon_360(lon_deg: float) -> float:
    return float(lon_deg) % 360.0


def great_circle_km(lat1: float, lon1: float, lat2: np.ndarray, lon2: np.ndarray, radius_km: float) -> np.ndarray:
    phi1 = math.radians(lat1)
    lam1 = math.radians(lon1)
    phi2 = np.radians(lat2)
    lam2 = np.radians(lon2)
    dphi = phi2 - phi1
    dlam = lam2 - lam1
    a = np.sin(dphi / 2.0) ** 2 + math.cos(phi1) * np.cos(phi2) * np.sin(dlam / 2.0) ** 2
    return 2.0 * radius_km * np.arcsin(np.minimum(1.0, np.sqrt(a)))


def _decode_wkb_rings(wkb: bytes) -> list[np.ndarray]:
    """Decode a little-endian WKB Polygon (type 3) into a list of (N, 2) float64 rings."""
    if len(wkb) < 9:
        raise ValueError("truncated WKB polygon")
    endian = "<" if wkb[0] == 1 else ">"
    wkb_type, n_rings = struct.unpack(endian + "II", wkb[1:9])
    if (wkb_type & 0xFF) != 3:
        raise ValueError(f"unsupported WKB geometry type {wkb_type}")
    offset = 9
    rings: list[np.ndarray] = []
    for _ in range(n_rings):
        (n_pts,) = struct.unpack(endian + "I", wkb[offset:offset + 4])
        offset += 4
        n_bytes = n_pts * 16
        arr = np.frombuffer(wkb, dtype=np.dtype(endian + "f8"), count=n_pts * 2, offset=offset).reshape(n_pts, 2)
        rings.append(arr)
        offset += n_bytes
    return rings


def _point_in_ring(lon: float, lat: float, ring: np.ndarray) -> bool:
    if ring.shape[0] < 3:
        return False
    x0 = ring[:-1, 0]
    y0 = ring[:-1, 1]
    x1 = ring[1:, 0]
    y1 = ring[1:, 1]
    cond = (y0 > lat) != (y1 > lat)
    if not np.any(cond):
        return False
    x_intersect = (x1[cond] - x0[cond]) * (lat - y0[cond]) / (y1[cond] - y0[cond]) + x0[cond]
    return bool(np.count_nonzero(lon < x_intersect) % 2 == 1)


def point_in_wkb_polygon(lon: float, lat: float, wkb: bytes) -> bool:
    """True when (lon, lat) falls inside the outer ring and outside any interior holes."""
    rings = _decode_wkb_rings(wkb)
    if not rings or not _point_in_ring(lon, lat, rings[0]):
        return False
    return not any(_point_in_ring(lon, lat, hole) for hole in rings[1:])


def _moon_south_stereo_xy(lat_deg: float, lon_deg: float) -> tuple[float, float]:
    xs, ys = warp_transform(MOON_LATLONG_CRS, MOON_STEREO_SOUTH_CRS, [lon_deg], [lat_deg])
    return float(xs[0]), float(ys[0])


def _clean_float(val: object) -> float | None:
    if val is None:
        return None
    f = float(val)
    return f if math.isfinite(f) else None


def _clean_int(val: object) -> int | None:
    if val is None:
        return None
    return int(val)


def _lookup_line_sample(path: Path, line: int, sample: int, cols: list[str]) -> dict | None:
    res = (
        pl.scan_parquet(path)
        .filter((pl.col("source_line") == line) & (pl.col("source_sample") == sample))
        .select(cols)
        .collect()
    )
    if res.height == 0:
        return None
    return res.to_dicts()[0]


def _nearest_grid_row(
    df: pl.DataFrame,
    lat_col: str,
    lon_col: str,
    lat: float,
    lon: float,
    radius_km: float,
    max_dist_km: float,
    lon_in_360: bool = False,
) -> dict | None:
    if df.height == 0:
        return None
    q_lon = norm_lon_360(lon) if lon_in_360 else norm_lon_180(lon)
    lats = df[lat_col].to_numpy().astype(np.float64)
    lons = df[lon_col].to_numpy().astype(np.float64)
    dists = great_circle_km(lat, q_lon, lats, lons, radius_km)
    idx = int(np.argmin(dists))
    if not math.isfinite(dists[idx]) or float(dists[idx]) > max_dist_km:
        return None
    row = df.row(idx, named=True)
    row["__dist_km"] = float(dists[idx])
    return row


def _empty_profile(
    tid: str,
    name: str,
    body: str,
    kind: str,
    status: str,
    lat: float | None,
    lon_raw: float | None,
    lon_mode: str | None,
    schema_cols: list[tuple[str, pl.DataType]],
) -> dict:
    row: dict = {
        "target_id": tid,
        "name": name,
        "body": body,
        "kind": kind,
        "status": status,
        "centre_lat_deg": _clean_float(lat),
        "centre_lon_raw": _clean_float(lon_raw),
        "centre_lon_e_180": norm_lon_180(lon_raw) if lon_raw is not None else None,
        "centre_lon_e_360": norm_lon_360(lon_raw) if lon_raw is not None else None,
        "lon_mode": lon_mode,
        "has_numeric_centre": lat is not None and lon_raw is not None,
    }
    for col, _ in schema_cols:
        row[col] = None
    return row


def _build_schema_cols() -> list[tuple[str, pl.DataType]]:
    return [
        # Shared top-level geometric/thermal/roughness/radar/radiation/chemistry/geology probes
        ("target_elevation_m", pl.Float64),
        ("target_elevation_source", pl.String),
        ("target_slope_local_deg", pl.Float64),
        ("target_slope_local_source", pl.String),
        ("target_slope_2km_deg", pl.Float64),
        ("target_slope_2km_source", pl.String),
        ("target_rough_rms_m", pl.Float64),
        ("target_rough_rms_source", pl.String),
        ("target_tsurf_max_k", pl.Float64),
        ("target_tsurf_min_k", pl.Float64),
        ("target_tsurf_range_k", pl.Float64),
        ("target_tsurf_support_bins", pl.Int32),
        # Mars-specific profiles
        ("mars_topo_site", pl.String),
        ("mars_site_slope_5m_deg", pl.Float64),
        ("mars_site_slope_20_40m_deg", pl.Float64),
        ("mars_site_slope_trav_mean_deg", pl.Float64),
        ("mars_site_slope_2_5km_deg", pl.Float64),
        ("mars_site_relief_hirise_m", pl.Float64),
        ("mars_site_relief_megdr_m", pl.Float64),
        ("mars_blended_slope_200_500m_deg", pl.Float64),
        ("mars_blended_slope_support_px", pl.Int32),
        ("mars_tes_ti_day_si", pl.Float64),
        ("mars_tes_ti_night_si", pl.Float64),
        ("mars_grs_weh_2deg_wt_pct", pl.Float64),
        ("mars_grs_weh_5deg_wt_pct", pl.Float64),
        ("mars_grs_th_ppm", pl.Float64),
        ("mars_grs_k_ppm", pl.Float64),
        ("mars_grs_kth_ratio", pl.Float64),
        ("mars_cdod_ann", pl.Float64),
        ("mars_cdod_p95", pl.Float64),
        ("mars_cdod_storm_freq", pl.Float64),
        ("mars_wind_edl_10m_mean_ms", pl.Float64),
        ("mars_wind_edl_10m_max_ms", pl.Float64),
        ("mars_wind_edl_8km_mean_ms", pl.Float64),
        ("mars_wind_edl_8km_max_ms", pl.Float64),
        ("mars_crism_obs_count", pl.Int32),
        ("mars_crism_bd1900_med", pl.Float64),
        ("mars_crism_d2300_med", pl.Float64),
        ("mars_crism_bd2210_med", pl.Float64),
        ("mars_crism_sindex2_med", pl.Float64),
        ("mars_crism_olindex3_med", pl.Float64),
        ("mars_crism_lcpindex2_med", pl.Float64),
        ("mars_crism_hcpindex2_med", pl.Float64),
        ("mars_crism_bd2500_med", pl.Float64),
        ("mars_themis_day_ir_dn_med", pl.Float64),
        ("mars_themis_night_ir_dn_med", pl.Float64),
        ("mars_caves_within_100km", pl.Int32),
        ("mars_nearest_cave_km", pl.Float64),
        # Moon-specific profiles
        ("moon_lola_spot_count", pl.Int32),
        ("moon_psr_2023", pl.Int8),
        ("moon_psr_frac_2km", pl.Float64),
        ("moon_psr_dist_km", pl.Float64),
        ("moon_illum_frac_pct", pl.Float64),
        ("moon_earth_vis_pct", pl.Float64),
        ("moon_illum_source", pl.String),
        ("moon_cf_position_um", pl.Float64),
        ("moon_rock_abund_div", pl.Float64),
        ("moon_prp_temp_avg_k", pl.Float64),
        ("moon_prp_temp_max_k", pl.Float64),
        ("moon_prp_ice_depth_m", pl.Float64),
        ("moon_lamp_lya_offon", pl.Float64),
        ("moon_lend_setn_rate_rel", pl.Float64),
        ("moon_lend_csetn_rate_rel", pl.Float64),
        ("moon_lend_csetn_2009_rate_rel", pl.Float64),
        ("moon_lpgrs_feo_wt", pl.Float64),
        ("moon_lpgrs_k", pl.Float64),
        ("moon_lpgrs_th", pl.Float64),
        ("moon_lpgrs_tio2", pl.Float64),
        ("moon_kaguya_feo_wt", pl.Float64),
        ("moon_minirf_cpr", pl.Float64),
        ("moon_wac_albedo_dn", pl.Float64),
        ("moon_pits_within_100km", pl.Int32),
        ("moon_nearest_pit_km", pl.Float64),
        ("moon_geo_unit_code", pl.String),
        ("moon_geo_unit_name", pl.String),
        ("moon_geo_unit_era", pl.String),
        ("moon_geo_unit_material", pl.String),
    ]


MARS_ONLY_COLS = {
    "mars_topo_site", "mars_site_slope_5m_deg", "mars_site_slope_20_40m_deg",
    "mars_site_slope_trav_mean_deg", "mars_site_slope_2_5km_deg",
    "mars_site_relief_hirise_m", "mars_site_relief_megdr_m",
    "mars_blended_slope_200_500m_deg", "mars_blended_slope_support_px",
    "mars_tes_ti_day_si", "mars_tes_ti_night_si",
    "mars_grs_weh_2deg_wt_pct", "mars_grs_weh_5deg_wt_pct",
    "mars_grs_th_ppm", "mars_grs_k_ppm", "mars_grs_kth_ratio",
    "mars_cdod_ann", "mars_cdod_p95", "mars_cdod_storm_freq",
    "mars_wind_edl_10m_mean_ms", "mars_wind_edl_10m_max_ms",
    "mars_wind_edl_8km_mean_ms", "mars_wind_edl_8km_max_ms",
    "mars_crism_obs_count", "mars_crism_bd1900_med", "mars_crism_d2300_med",
    "mars_crism_bd2210_med", "mars_crism_sindex2_med", "mars_crism_olindex3_med",
    "mars_crism_lcpindex2_med", "mars_crism_hcpindex2_med", "mars_crism_bd2500_med",
    "mars_themis_day_ir_dn_med", "mars_themis_night_ir_dn_med",
    "mars_caves_within_100km", "mars_nearest_cave_km",
}

MOON_ONLY_COLS = {
    "moon_lola_spot_count", "moon_psr_2023", "moon_psr_frac_2km", "moon_psr_dist_km",
    "moon_illum_frac_pct", "moon_earth_vis_pct", "moon_illum_source",
    "moon_cf_position_um", "moon_rock_abund_div",
    "moon_prp_temp_avg_k", "moon_prp_temp_max_k", "moon_prp_ice_depth_m",
    "moon_lamp_lya_offon", "moon_lend_setn_rate_rel", "moon_lend_csetn_rate_rel",
    "moon_lend_csetn_2009_rate_rel",
    "moon_lpgrs_feo_wt", "moon_lpgrs_k", "moon_lpgrs_th", "moon_lpgrs_tio2",
    "moon_kaguya_feo_wt", "moon_minirf_cpr", "moon_wac_albedo_dn",
    "moon_pits_within_100km", "moon_nearest_pit_km",
    "moon_geo_unit_code", "moon_geo_unit_name", "moon_geo_unit_era", "moon_geo_unit_material",
}


def build_planetary_targets(pdir: Path | None = None, targets_dir: Path | None = None) -> tuple[pl.DataFrame, dict]:
    """Build native planetary target profiles across every YAML in data/targets."""
    pdir = pdir or (DERIVED / "planetary")
    targets_dir = targets_dir or (REPO / "data" / "targets")
    schema_cols = _build_schema_cols()
    all_feature_cols = [c for c, _ in schema_cols] + ["centre_lat_deg", "centre_lon_raw", "centre_lon_e_180", "centre_lon_e_360"]

    # Load compact / shared Mars tables once
    mars_megdr_stats = pl.read_parquet(pdir / "mars_topo/mars-topo-site-stats-megdr32.parquet")
    mars_ctx_stats = pl.read_parquet(pdir / "mars_topo/mars-topo-site-dtm-ctx-stats.parquet")
    mars_hirise_stats = pl.read_parquet(pdir / "mars_topo/mars-topo-site-dtm-hirise-stats.parquet")
    mars_grs_weh2 = pl.read_parquet(pdir / "ody-grs-pds/grs-weh-2deg-unsmoothed.parquet")
    mars_grs_weh5 = pl.read_parquet(pdir / "ody-grs-pds/grs-weh-5deg-smoothed.parquet")
    mars_grs_th = pl.read_parquet(pdir / "ody-grs-pds/grs-th-5deg-smoothed.parquet")
    mars_grs_k = pl.read_parquet(pdir / "ody-grs-pds/grs-k-5deg-smoothed.parquet")
    mars_grs_kth = pl.read_parquet(pdir / "ody-grs-pds/grs-kth-ratio-5deg-smoothed.parquet")
    mars_cdod = pl.read_parquet(pdir / "mars-dust-climatology-lmd/cdod-annual.parquet")
    mars_wind = pl.read_parquet(pdir / "mars-climate-database-v62/wind-edl-ls-maps.parquet")
    mars_themis_day = pl.read_parquet(pdir / "themis-ir-controlled-mosaics/themis-ir-day-rois.parquet")
    mars_themis_night = pl.read_parquet(pdir / "themis-ir-controlled-mosaics/themis-ir-night-rois.parquet")
    mars_caves = pl.read_parquet(pdir / "mgc3-mars-caves/cave-candidates.parquet")
    mars_blended_lf = pl.scan_parquet(pdir / "mars_topo/mars-topo-blended-3p2km-blocks.parquet")
    mars_crism_lf = pl.scan_parquet(pdir / "crism-mtrdr/crism-mtrdr-summary.parquet")

    # Load compact / shared Moon tables once
    moon_gdr = pl.read_parquet(pdir / "lola-gdr/ldem-gdr-4ppd.parquet")
    moon_psr_2km = pl.read_parquet(pdir / "lola-south-pole-ldem-2023/psr-2km-1kmgrid.parquet")
    moon_tsurf = pl.read_parquet(pdir / "diviner-l4/gcp-tsurf.parquet")
    moon_prp_south = pl.read_parquet(pdir / "diviner-south-prp.parquet")
    moon_lend_s_2011 = pl.read_parquet(pdir / "lend/lend-rdr-alds-20111211.parquet")
    moon_lend_e_2011 = pl.read_parquet(pdir / "lend/lend-rdr-alde-20111211.parquet")
    moon_lend_n_2011 = pl.read_parquet(pdir / "lend/lend-rdr-aldn-20111211.parquet")
    moon_lend_s_2009 = pl.read_parquet(pdir / "lend/lend-rdr-alds-20090915.parquet")
    moon_lend_e_2009 = pl.read_parquet(pdir / "lend/lend-rdr-alde-20090915.parquet")
    moon_lend_n_2009 = pl.read_parquet(pdir / "lend/lend-rdr-aldn-20090915.parquet")
    moon_lpgrs_2deg = pl.read_parquet(pdir / "lp-grs-pds/lpgrs-high1-elem-abundance-2deg.parquet")
    moon_pits = pl.read_parquet(pdir / "lroc-pits-atlas/pits.parquet")
    moon_geo_polys = pl.read_parquet(pdir / "unified-geologic-map-moon/geo-units-polygons.parquet")

    moon_20m_path = pdir / "lola-south-pole-ldem-2023/ldem-80s-20mpp.parquet"
    moon_50m_path = pdir / "lola-south-pole-ldem-2023/ldrm-80s-50mpp.parquet"
    moon_240m_path = pdir / "lola-south-pole-ldem-2023/ldem-60s-240mpp.parquet"
    moon_vis85_path = pdir / "lola-polar-illumination/avgvisib-85s-060m.parquet"
    moon_vis75_path = pdir / "lola-polar-illumination/avgvisib-75s-120m.parquet"
    moon_lamp80s_path = pdir / "lamp/lamp-gdr-ratio-albedo-80s.parquet"
    moon_lamp80n_path = pdir / "lamp/lamp-gdr-ratio-albedo-80n.parquet"
    moon_cf_path = pdir / "diviner-l4/cf-position.parquet"
    moon_rock_path = pdir / "diviner-l4/rock-abundance.parquet"
    moon_kaguya_path = pdir / "kaguya-mi-59mpp/kaguya-mi-feo-4ppd.parquet"
    moon_minirf_path = pdir / "minirf-pds/minirf-cpr-32ppd.parquet"
    moon_wac_path = pdir / "lroc-wac-global/lroc-wac-albedo-3ppd.parquet"

    def _mars_stat(tbl: pl.DataFrame, site: str, feature: str) -> float | None:
        sub = tbl.filter((pl.col("site") == site) & (pl.col("feature") == feature) & pl.col("value").is_not_null())
        if sub.height == 0:
            return None
        return _clean_float(sub["value"][0])

    rows: list[dict] = []
    for path in sorted(targets_dir.glob("*.yaml")):
        t = yaml.safe_load(path.read_text(encoding="utf-8"))
        tid = str(t["siteId"])
        name = str(t["name"])
        body = str(t["body"]).lower()
        kind = str(t.get("kind", ""))
        status = str(t.get("status", ""))
        lat = _clean_float(t.get("centreLat"))
        lon_raw = _clean_float(t.get("centreLon"))
        lon_mode = t.get("lonMode")

        row = _empty_profile(tid, name, body, kind, status, lat, lon_raw, lon_mode, schema_cols)
        reasons: dict[str, str] = {}

        if lat is None or lon_raw is None:
            for col in all_feature_cols:
                if col in ("centre_lat_deg", "centre_lon_raw", "centre_lon_e_180", "centre_lon_e_360"):
                    reasons[col] = "no-numeric-centre"
                elif body == "mars" and col in MOON_ONLY_COLS:
                    reasons[col] = "moon-only-quantity"
                elif body == "moon" and col in MARS_ONLY_COLS:
                    reasons[col] = "mars-only-quantity"
                else:
                    reasons[col] = "no-numeric-centre"
            row["missing_reason"] = json.dumps(reasons, sort_keys=True, separators=(",", ":"))
            rows.append(row)
            continue

        lon180 = norm_lon_180(lon_raw)
        lon360 = norm_lon_360(lon_raw)

        if body == "mars":
            for col in MOON_ONLY_COLS:
                reasons[col] = "moon-only-quantity"

            # TES remains un-extracted pending projection review (ADR-0008)
            reasons["mars_tes_ti_day_si"] = "tes-projection-conflict-pending-review"
            reasons["mars_tes_ti_night_si"] = "tes-projection-conflict-pending-review"
            reasons["target_tsurf_max_k"] = "not-in-local-mars-snapshot"
            reasons["target_tsurf_min_k"] = "not-in-local-mars-snapshot"
            reasons["target_tsurf_range_k"] = "not-in-local-mars-snapshot"
            reasons["target_tsurf_support_bins"] = "not-in-local-mars-snapshot"
            reasons["target_rough_rms_m"] = "not-in-local-mars-snapshot"
            reasons["target_rough_rms_source"] = "not-in-local-mars-snapshot"

            # Blended 3.2 km blocks (Mars slope 200-500 m baseline)
            dlon = 0.25
            b_cand = mars_blended_lf.filter(
                (pl.col("latitude").is_between(lat - 0.25, lat + 0.25))
                & (pl.col("longitude").is_between(lon180 - dlon, lon180 + dlon))
                & pl.col("slope_200_500m_mean").is_not_null()
            ).collect()
            b_hit = _nearest_grid_row(b_cand, "latitude", "longitude", lat, lon180, R_MARS_KM, 10.0)
            if b_hit is not None:
                row["mars_blended_slope_200_500m_deg"] = _clean_float(b_hit["slope_200_500m_mean"])
                row["mars_blended_slope_support_px"] = _clean_int(b_hit["support_px"])
                row["target_slope_local_deg"] = row["mars_blended_slope_200_500m_deg"]
                row["target_slope_local_source"] = "mars-topo-blended-3p2km-blocks"
            else:
                reasons["mars_blended_slope_200_500m_deg"] = "outside-blended-block-coverage"
                reasons["mars_blended_slope_support_px"] = "outside-blended-block-coverage"

            # Named site DTM/MEGDR32 summaries
            topo_site = TARGET_TO_MARS_TOPO_SITE.get(tid)
            if topo_site is not None:
                row["mars_topo_site"] = topo_site
                row["mars_site_slope_5m_deg"] = _mars_stat(mars_hirise_stats, topo_site, "slope_5m")
                row["mars_site_slope_20_40m_deg"] = _mars_stat(mars_ctx_stats, topo_site, "slope_20_40m")
                row["mars_site_slope_trav_mean_deg"] = _mars_stat(mars_hirise_stats, topo_site, "slope_trav_mean")
                if row["mars_site_slope_trav_mean_deg"] is None:
                    row["mars_site_slope_trav_mean_deg"] = _mars_stat(mars_ctx_stats, topo_site, "slope_trav_mean")
                row["mars_site_slope_2_5km_deg"] = _mars_stat(mars_megdr_stats, topo_site, "slope_2_5km")
                row["mars_site_relief_hirise_m"] = _mars_stat(mars_hirise_stats, topo_site, "relief_ellipse")
                row["mars_site_relief_megdr_m"] = _mars_stat(mars_megdr_stats, topo_site, "relief_ellipse")
                if row["mars_site_slope_2_5km_deg"] is not None:
                    row["target_slope_2km_deg"] = row["mars_site_slope_2_5km_deg"]
                    row["target_slope_2km_source"] = "mars-topo-site-stats-megdr32"
                if row["mars_site_slope_5m_deg"] is not None and row["target_slope_local_deg"] is None:
                    row["target_slope_local_deg"] = row["mars_site_slope_5m_deg"]
                    row["target_slope_local_source"] = "mars-topo-site-dtm-hirise-stats"
                for col in (
                    "mars_site_slope_5m_deg", "mars_site_slope_20_40m_deg",
                    "mars_site_slope_trav_mean_deg", "mars_site_slope_2_5km_deg",
                    "mars_site_relief_hirise_m", "mars_site_relief_megdr_m",
                ):
                    if row[col] is None:
                        reasons[col] = "no-valid-dtm-pixels-for-baseline"
            else:
                for col in (
                    "mars_topo_site", "mars_site_slope_5m_deg", "mars_site_slope_20_40m_deg",
                    "mars_site_slope_trav_mean_deg", "mars_site_slope_2_5km_deg",
                    "mars_site_relief_hirise_m", "mars_site_relief_megdr_m",
                ):
                    reasons[col] = "outside-named-mars-topo-dtm-sites"

            if row["target_slope_local_deg"] is None:
                reasons["target_slope_local_deg"] = reasons.get("mars_blended_slope_200_500m_deg", "outside-blended-block-coverage")
                reasons["target_slope_local_source"] = reasons["target_slope_local_deg"]
            if row["target_slope_2km_deg"] is None:
                reasons["target_slope_2km_deg"] = "outside-named-mars-topo-dtm-sites"
                reasons["target_slope_2km_source"] = "outside-named-mars-topo-dtm-sites"
            reasons["target_elevation_m"] = "no-global-megdr32-elevation-parquet"
            reasons["target_elevation_source"] = "no-global-megdr32-elevation-parquet"

            # Mars ODY GRS
            w2 = _nearest_grid_row(mars_grs_weh2, "latitude", "longitude", lat, lon360, R_MARS_KM, 150.0, lon_in_360=True)
            row["mars_grs_weh_2deg_wt_pct"] = _clean_float(w2["weh_wt_pct"]) if w2 is not None else None
            w5 = _nearest_grid_row(mars_grs_weh5, "latitude", "longitude", lat, lon360, R_MARS_KM, 300.0, lon_in_360=True)
            row["mars_grs_weh_5deg_wt_pct"] = _clean_float(w5["weh_wt_pct"]) if w5 is not None else None
            th = _nearest_grid_row(mars_grs_th, "latitude", "longitude", lat, lon360, R_MARS_KM, 300.0, lon_in_360=True)
            row["mars_grs_th_ppm"] = _clean_float(th["th_ppm"]) if th is not None else None
            k = _nearest_grid_row(mars_grs_k, "latitude", "longitude", lat, lon360, R_MARS_KM, 300.0, lon_in_360=True)
            row["mars_grs_k_ppm"] = _clean_float(k["k_ppm"]) if k is not None else None
            kth = _nearest_grid_row(mars_grs_kth, "latitude", "longitude", lat, lon360, R_MARS_KM, 300.0, lon_in_360=True)
            row["mars_grs_kth_ratio"] = _clean_float(kth["kth_ratio_ppm_as_labelled"]) if kth is not None else None
            for col in ("mars_grs_weh_2deg_wt_pct", "mars_grs_weh_5deg_wt_pct", "mars_grs_th_ppm", "mars_grs_k_ppm", "mars_grs_kth_ratio"):
                if row[col] is None:
                    reasons[col] = "outside-grs-coverage-or-null-cell"

            # Mars dust climatology
            cdod_hit = _nearest_grid_row(mars_cdod, "lat", "lon", lat, lon180, R_MARS_KM, 350.0)
            if cdod_hit is not None:
                row["mars_cdod_ann"] = _clean_float(cdod_hit["cdod_ann"])
                row["mars_cdod_p95"] = _clean_float(cdod_hit["cdod_p95"])
                row["mars_cdod_storm_freq"] = _clean_float(cdod_hit["cdod_storm_freq"])
            for col in ("mars_cdod_ann", "mars_cdod_p95", "mars_cdod_storm_freq"):
                if row[col] is None:
                    reasons[col] = "outside-cdod-grid"

            # Mars Climate Database v6.2 wind EDL (10 m and 8000 m)
            w_sub = mars_wind.filter(pl.col("altitude_m") == 10.0)
            w_pts = w_sub.select("lat", "lon").unique()
            w_hit = _nearest_grid_row(w_pts, "lat", "lon", lat, lon180, R_MARS_KM, 350.0)
            if w_hit is not None:
                w10 = mars_wind.filter(
                    (pl.col("lat") == w_hit["lat"]) & (pl.col("lon") == w_hit["lon"]) & (pl.col("altitude_m") == 10.0)
                )["wind_edl_ms"]
                w8k = mars_wind.filter(
                    (pl.col("lat") == w_hit["lat"]) & (pl.col("lon") == w_hit["lon"]) & (pl.col("altitude_m") == 8000.0)
                )["wind_edl_ms"]
                if w10.len() > 0:
                    row["mars_wind_edl_10m_mean_ms"] = _clean_float(w10.mean())
                    row["mars_wind_edl_10m_max_ms"] = _clean_float(w10.max())
                if w8k.len() > 0:
                    row["mars_wind_edl_8km_mean_ms"] = _clean_float(w8k.mean())
                    row["mars_wind_edl_8km_max_ms"] = _clean_float(w8k.max())
            for col in ("mars_wind_edl_10m_mean_ms", "mars_wind_edl_10m_max_ms", "mars_wind_edl_8km_mean_ms", "mars_wind_edl_8km_max_ms"):
                if row[col] is None:
                    reasons[col] = "outside-mcd-wind-grid"

            # CRISM MTRDR summary within 5 km
            cr_cand = mars_crism_lf.filter(
                pl.col("latitude").is_between(lat - 0.2, lat + 0.2)
                & pl.col("longitude").is_between(lon180 - 0.25, lon180 + 0.25)
            ).collect()
            crism_cols = [
                ("mars_crism_bd1900_med", "BD1900_2"),
                ("mars_crism_d2300_med", "D2300"),
                ("mars_crism_bd2210_med", "BD2210_2"),
                ("mars_crism_sindex2_med", "SINDEX2"),
                ("mars_crism_olindex3_med", "OLINDEX3"),
                ("mars_crism_lcpindex2_med", "LCPINDEX2"),
                ("mars_crism_hcpindex2_med", "HCPINDEX2"),
                ("mars_crism_bd2500_med", "BD2500_2"),
            ]
            if cr_cand.height > 0:
                dists = great_circle_km(lat, lon180, cr_cand["latitude"].to_numpy(), cr_cand["longitude"].to_numpy(), R_MARS_KM)
                cr_in = cr_cand.filter(pl.Series(dists <= 5.0))
                if cr_in.height > 0:
                    row["mars_crism_obs_count"] = int(cr_in.height)
                    for out_col, src_col in crism_cols:
                        med = _clean_float(cr_in[src_col].drop_nulls().median()) if cr_in[src_col].null_count() < cr_in.height else None
                        row[out_col] = med
                        if med is None:
                            reasons[out_col] = "all-crism-pixels-null-in-radius"
                else:
                    row["mars_crism_obs_count"] = 0
                    for out_col, _ in crism_cols:
                        reasons[out_col] = "outside-crism-mtrdr-footprints"
            else:
                row["mars_crism_obs_count"] = 0
                for out_col, _ in crism_cols:
                    reasons[out_col] = "outside-crism-mtrdr-footprints"

            # THEMIS IR controlled ROI samples within 5 km
            for out_col, tbl in (("mars_themis_day_ir_dn_med", mars_themis_day), ("mars_themis_night_ir_dn_med", mars_themis_night)):
                d = great_circle_km(lat, lon360, tbl["lat_pc_deg"].to_numpy(), tbl["lon_east_deg"].to_numpy(), R_MARS_KM)
                in_roi = tbl.filter(pl.Series(d <= 5.0))
                if in_roi.height > 0:
                    row[out_col] = _clean_float(in_roi["ir_brightness_dn"].median())
                else:
                    reasons[out_col] = "outside-themis-roi-footprints"

            # MGC3 caves
            cdist = great_circle_km(lat, lon180, mars_caves["latitude_deg"].to_numpy(), mars_caves["longitude_deg"].to_numpy(), R_MARS_KM)
            row["mars_caves_within_100km"] = int(np.count_nonzero(cdist <= 100.0))
            row["mars_nearest_cave_km"] = _clean_float(np.min(cdist)) if cdist.size > 0 else None

        elif body == "moon":
            for col in MARS_ONLY_COLS:
                reasons[col] = "mars-only-quantity"

            xm, ym = _moon_south_stereo_xy(lat, lon180)
            in_20m = -304_000.0 <= xm < 304_000.0 and -304_000.0 < ym <= 304_000.0
            in_240m = -931_200.0 <= xm < 931_200.0 and -931_200.0 < ym <= 931_200.0

            # Elevation + PSR 20m / 240m / 4ppd GDR
            if in_20m:
                s20 = int(math.floor((xm + 304_000.0) / 20.0))
                l20 = int(math.floor((304_000.0 - ym) / 20.0))
                hit20 = _lookup_line_sample(moon_20m_path, l20, s20, ["elevation_m", "lola_spot_count", "psr_2023"])
                if hit20 is not None:
                    row["target_elevation_m"] = _clean_float(hit20["elevation_m"])
                    if row["target_elevation_m"] is not None:
                        row["target_elevation_source"] = "lola-south-pole-ldem-80s-20mpp"
                    row["moon_lola_spot_count"] = _clean_int(hit20["lola_spot_count"])
                    row["moon_psr_2023"] = _clean_int(hit20["psr_2023"])
            if row["moon_lola_spot_count"] is None:
                reasons["moon_lola_spot_count"] = "outside-80s-20m-grid"
            if row["moon_psr_2023"] is None:
                reasons["moon_psr_2023"] = "outside-80s-20m-grid"

            if in_240m:
                s240 = int(math.floor((xm + 931_200.0) / 240.0))
                l240 = int(math.floor((931_200.0 - ym) / 240.0))
                hit240 = _lookup_line_sample(moon_240m_path, l240, s240, ["elevation_m", "slope_2km_eva_deg"])
                if hit240 is not None:
                    if row["target_elevation_m"] is None and hit240["elevation_m"] is not None:
                        row["target_elevation_m"] = _clean_float(hit240["elevation_m"])
                        row["target_elevation_source"] = "lola-south-pole-ldem-60s-240mpp"
                    row["target_slope_2km_deg"] = _clean_float(hit240["slope_2km_eva_deg"])
                    if row["target_slope_2km_deg"] is not None:
                        row["target_slope_2km_source"] = "lola-south-pole-ldem-60s-240mpp"
            if row["target_slope_2km_deg"] is None:
                reasons["target_slope_2km_deg"] = "outside-60s-240m-grid"
                reasons["target_slope_2km_source"] = "outside-60s-240m-grid"

            if row["target_elevation_m"] is None:
                gdr_hit = _nearest_grid_row(moon_gdr, "lat_deg", "lon_deg", lat, lon180, R_MOON_KM, 12.0)
                if gdr_hit is not None:
                    row["target_elevation_m"] = _clean_float(gdr_hit["elevation_m"])
                    row["target_elevation_source"] = "lola-gdr-4ppd"
            if row["target_elevation_m"] is None:
                reasons["target_elevation_m"] = "no-valid-lola-elevation"
                reasons["target_elevation_source"] = "no-valid-lola-elevation"

            # LDRM 50 m slope (100 m baseline) & RMS roughness
            if in_20m:
                s50 = int(math.floor((xm + 304_000.0) / 50.0))
                l50 = int(math.floor((304_000.0 - ym) / 50.0))
                hit50 = _lookup_line_sample(moon_50m_path, l50, s50, ["slope_100m_deg", "rough_rms_100m_m"])
                if hit50 is not None:
                    row["target_slope_local_deg"] = _clean_float(hit50["slope_100m_deg"])
                    if row["target_slope_local_deg"] is not None:
                        row["target_slope_local_source"] = "lola-south-pole-ldrm-80s-50mpp"
                    row["target_rough_rms_m"] = _clean_float(hit50["rough_rms_100m_m"])
                    if row["target_rough_rms_m"] is not None:
                        row["target_rough_rms_source"] = "lola-south-pole-ldrm-80s-50mpp"
            if row["target_slope_local_deg"] is None:
                reasons["target_slope_local_deg"] = "outside-80s-50m-grid" if not in_20m else "nodata-in-ldrm-50m"
                reasons["target_slope_local_source"] = reasons["target_slope_local_deg"]
            if row["target_rough_rms_m"] is None:
                reasons["target_rough_rms_m"] = "outside-80s-50m-grid" if not in_20m else "nodata-in-ldrm-50m"
                reasons["target_rough_rms_source"] = reasons["target_rough_rms_m"]

            # 1 km PSR fraction & distance grid
            d_psr = np.hypot(moon_psr_2km["x_m"].to_numpy() - xm, moon_psr_2km["y_m"].to_numpy() - ym)
            idx_psr = int(np.argmin(d_psr))
            if float(d_psr[idx_psr]) <= 1_500.0:
                psr_row = moon_psr_2km.row(idx_psr, named=True)
                row["moon_psr_frac_2km"] = _clean_float(psr_row["psr_frac_2km"])
                row["moon_psr_dist_km"] = _clean_float(psr_row["psr_dist_km"])
            if row["moon_psr_frac_2km"] is None:
                reasons["moon_psr_frac_2km"] = "outside-80s-psr-1km-grid"
            if row["moon_psr_dist_km"] is None:
                reasons["moon_psr_dist_km"] = "outside-80s-psr-1km-grid"

            # LOLA polar illumination & Earth visibility
            s60, l60 = round(xm / 60.0 + 2528.5), round(2528.5 - ym / 60.0)
            s120, l120 = round(xm / 120.0 + 3811.5), round(3811.5 - ym / 120.0)
            if 0 <= s60 < 5058 and 0 <= l60 < 5058:
                hvis = _lookup_line_sample(moon_vis85_path, l60, s60, ["illum_frac_pct", "earth_vis_pct"])
                if hvis is not None:
                    row["moon_illum_frac_pct"] = _clean_float(hvis["illum_frac_pct"])
                    row["moon_earth_vis_pct"] = _clean_float(hvis["earth_vis_pct"])
                    row["moon_illum_source"] = "lola-avgvisib-85s-060m"
            elif 0 <= s120 < 7624 and 0 <= l120 < 7624:
                hvis = _lookup_line_sample(moon_vis75_path, l120, s120, ["illum_frac_pct", "earth_vis_pct"])
                if hvis is not None:
                    row["moon_illum_frac_pct"] = _clean_float(hvis["illum_frac_pct"])
                    row["moon_earth_vis_pct"] = _clean_float(hvis["earth_vis_pct"])
                    row["moon_illum_source"] = "lola-avgvisib-75s-120m"
            if row["moon_illum_frac_pct"] is None:
                reasons["moon_illum_frac_pct"] = "outside-polar-illumination-grid"
                reasons["moon_earth_vis_pct"] = "outside-polar-illumination-grid"
                reasons["moon_illum_source"] = "outside-polar-illumination-grid"

            # Diviner GCP tsurf (global 0.5 deg)
            g_hit = _nearest_grid_row(moon_tsurf, "clat", "clon", lat, lon180, R_MOON_KM, 30.0)
            if g_hit is not None:
                row["target_tsurf_max_k"] = _clean_float(g_hit["tsurf_max"])
                row["target_tsurf_min_k"] = _clean_float(g_hit["tsurf_min"])
                row["target_tsurf_range_k"] = _clean_float(g_hit["tsurf_range"])
                row["target_tsurf_support_bins"] = _clean_int(g_hit["support_bins"])
            for col in ("target_tsurf_max_k", "target_tsurf_min_k", "target_tsurf_range_k", "target_tsurf_support_bins"):
                if row[col] is None:
                    reasons[col] = "outside-or-empty-diviner-gcp"

            # Diviner 32ppd (-60..+60)
            if -60.0 <= lat <= 60.0:
                ldiv = min(3839, max(0, int(math.floor((60.0 - lat) * 32.0))))
                sdiv = min(11519, max(0, int(math.floor(lon360 * 32.0))))
                hcf = _lookup_line_sample(moon_cf_path, ldiv, sdiv, ["cf_position"])
                hrock = _lookup_line_sample(moon_rock_path, ldiv, sdiv, ["rock_abund_div"])
                if hcf is not None:
                    row["moon_cf_position_um"] = _clean_float(hcf["cf_position"])
                if hrock is not None:
                    row["moon_rock_abund_div"] = _clean_float(hrock["rock_abund_div"])
                if row["moon_cf_position_um"] is None:
                    reasons["moon_cf_position_um"] = "diviner-cf-nodata"
                if row["moon_rock_abund_div"] is None:
                    reasons["moon_rock_abund_div"] = "diviner-rock-nodata"
            else:
                reasons["moon_cf_position_um"] = "outside-60N-60S-diviner-grid"
                reasons["moon_rock_abund_div"] = "outside-60N-60S-diviner-grid"

            # Diviner south PRP
            if lat <= -75.0:
                prp_hit = _nearest_grid_row(moon_prp_south, "tri_clat", "tri_clon", lat, lon180, R_MOON_KM, 15.0)
                if prp_hit is not None:
                    row["moon_prp_temp_avg_k"] = _clean_float(prp_hit["temp_avg"])
                    row["moon_prp_temp_max_k"] = _clean_float(prp_hit["temp_max"])
                    row["moon_prp_ice_depth_m"] = _clean_float(prp_hit["ice_depth"])
                for col in ("moon_prp_temp_avg_k", "moon_prp_temp_max_k", "moon_prp_ice_depth_m"):
                    if row[col] is None:
                        reasons[col] = "outside-or-sentinel-in-south-prp"
            else:
                for col in ("moon_prp_temp_avg_k", "moon_prp_temp_max_k", "moon_prp_ice_depth_m"):
                    reasons[col] = "outside-south-prp-coverage"

            # LAMP far-UV off/on ratio poleward of 80
            slamp, llamp = round(xm / 240.0 + 1250.0), round(1250.0 - ym / 240.0)
            if lat <= -80.0 and 0 <= slamp < 2501 and 0 <= llamp < 2501:
                hlamp = _lookup_line_sample(moon_lamp80s_path, llamp, slamp, ["lya_offon"])
                if hlamp is not None:
                    row["moon_lamp_lya_offon"] = _clean_float(hlamp["lya_offon"])
            elif lat >= 80.0 and moon_lamp80n_path.exists():
                pass
            if row["moon_lamp_lya_offon"] is None:
                reasons["moon_lamp_lya_offon"] = "outside-80s-lamp-grid" if lat > -80.0 else "non-finite-lamp-pixel"

            # LEND ALD epithermal neutron rates (nominal 20090915 + science 20111211 epochs)
            lend_2011 = moon_lend_s_2011 if lat <= -80.0 else (moon_lend_n_2011 if lat >= 80.0 else moon_lend_e_2011)
            lend_2009 = moon_lend_s_2009 if lat <= -80.0 else (moon_lend_n_2009 if lat >= 80.0 else moon_lend_e_2009)
            max_lend_km = 25.0 if abs(lat) >= 80.0 else 45.0
            lhit_2011 = _nearest_grid_row(lend_2011, "lat_deg", "lon_deg", lat, lon180, R_MOON_KM, max_lend_km)
            lhit_2009 = _nearest_grid_row(lend_2009, "lat_deg", "lon_deg", lat, lon180, R_MOON_KM, max_lend_km)
            if lhit_2011 is not None:
                row["moon_lend_csetn_rate_rel"] = _clean_float(lhit_2011["csetn_rate_rel"])
            if lhit_2009 is not None:
                row["moon_lend_setn_rate_rel"] = _clean_float(lhit_2009["setn_rate_rel"])
                row["moon_lend_csetn_2009_rate_rel"] = _clean_float(lhit_2009["csetn_rate_rel"])
            if row["moon_lend_setn_rate_rel"] is None:
                reasons["moon_lend_setn_rate_rel"] = "lend-20090915-zero-exposure-or-outside"
            if row["moon_lend_csetn_rate_rel"] is None:
                reasons["moon_lend_csetn_rate_rel"] = "lend-20111211-zero-exposure-or-outside"
            if row["moon_lend_csetn_2009_rate_rel"] is None:
                reasons["moon_lend_csetn_2009_rate_rel"] = "lend-20090915-zero-exposure-or-outside"

            # LP-GRS 2 deg elemental abundance box
            lp_sub = moon_lpgrs_2deg.filter(
                (pl.col("min_lat") <= lat) & (lat <= pl.col("max_lat"))
                & (pl.col("min_lon") <= lon180) & (lon180 <= pl.col("max_lon"))
            )
            if lp_sub.height > 0:
                lp = lp_sub.row(0, named=True)
                row["moon_lpgrs_feo_wt"] = _clean_float(lp["w_feo"])
                row["moon_lpgrs_k"] = _clean_float(lp["w_k"])
                row["moon_lpgrs_th"] = _clean_float(lp["w_th"])
                row["moon_lpgrs_tio2"] = _clean_float(lp["tio2"])
            for col in ("moon_lpgrs_feo_wt", "moon_lpgrs_k", "moon_lpgrs_th", "moon_lpgrs_tio2"):
                if row[col] is None:
                    reasons[col] = "outside-lpgrs-2deg-box"

            # Kaguya MI FeO 4 ppd (-50..+50)
            if -50.0 <= lat <= 50.0:
                lkag = min(399, max(0, int(math.floor((50.0 - lat) * 4.0))))
                skag = min(1439, max(0, int(math.floor((lon180 + 180.0) * 4.0))))
                hkag = _lookup_line_sample(moon_kaguya_path, lkag, skag, ["feo_wt"])
                if hkag is not None:
                    row["moon_kaguya_feo_wt"] = _clean_float(hkag["feo_wt"])
                if row["moon_kaguya_feo_wt"] is None:
                    reasons["moon_kaguya_feo_wt"] = "kaguya-nodata"
            else:
                reasons["moon_kaguya_feo_wt"] = "outside-50N-50S-kaguya-grid"

            # Mini-RF 32 ppd S-band CPR
            lmrf = min(5759, max(0, int(math.floor((90.0 - lat) * 32.0))))
            smrf = min(11519, max(0, int(math.floor((lon180 + 180.0) * 32.0))))
            hmrf = _lookup_line_sample(moon_minirf_path, lmrf, smrf, ["cpr_minirf"])
            if hmrf is not None:
                row["moon_minirf_cpr"] = _clean_float(hmrf["cpr_minirf"])
            if row["moon_minirf_cpr"] is None:
                reasons["moon_minirf_cpr"] = "minirf-missing-constant"

            # LROC WAC 3 ppd grayscale DN
            wac_step = 101.0 * (360.0 / 109164.0)
            lwac = min(539, max(0, int(math.floor((90.0 - lat) / wac_step))))
            swac = min(1079, max(0, int(math.floor((lon180 + 180.0) / wac_step))))
            hwac = _lookup_line_sample(moon_wac_path, lwac, swac, ["albedo_wac_dn"])
            if hwac is not None:
                row["moon_wac_albedo_dn"] = _clean_float(hwac["albedo_wac_dn"])
            if row["moon_wac_albedo_dn"] is None:
                reasons["moon_wac_albedo_dn"] = "outside-wac-3ppd-grid"

            # LROC Pits Atlas
            pdist = great_circle_km(lat, lon360, moon_pits["lat_deg"].to_numpy(), moon_pits["lon_deg_east"].to_numpy(), R_MOON_KM)
            row["moon_pits_within_100km"] = int(np.count_nonzero(pdist <= 100.0))
            row["moon_nearest_pit_km"] = _clean_float(np.min(pdist)) if pdist.size > 0 else None

            # Unified Geologic Map of the Moon 1:5M WKB point-in-polygon
            cand_geo = moon_geo_polys.filter(
                (pl.col("lon_min") <= lon180) & (lon180 <= pl.col("lon_max"))
                & (pl.col("lat_min") <= lat) & (lat <= pl.col("lat_max"))
            )
            for poly_row in cand_geo.iter_rows(named=True):
                if point_in_wkb_polygon(lon180, lat, poly_row["geometry"]):
                    row["moon_geo_unit_code"] = poly_row["unit_code"]
                    row["moon_geo_unit_name"] = poly_row["unit_name"]
                    row["moon_geo_unit_era"] = poly_row["unit_era"]
                    row["moon_geo_unit_material"] = poly_row["unit_material"]
                    break
            for col in ("moon_geo_unit_code", "moon_geo_unit_name", "moon_geo_unit_era", "moon_geo_unit_material"):
                if row[col] is None:
                    reasons[col] = "outside-geologic-map-polygons"

        # Verify every null column has an explicit reason
        for col in all_feature_cols:
            if row[col] is None and col not in reasons:
                reasons[col] = "null-without-reason"
            elif row[col] is not None and col in reasons:
                reasons.pop(col, None)
        row["missing_reason"] = json.dumps(reasons, sort_keys=True, separators=(",", ":"))
        rows.append(row)

    base_schema = {
        "target_id": pl.String,
        "name": pl.String,
        "body": pl.String,
        "kind": pl.String,
        "status": pl.String,
        "centre_lat_deg": pl.Float64,
        "centre_lon_raw": pl.Float64,
        "centre_lon_e_180": pl.Float64,
        "centre_lon_e_360": pl.Float64,
        "lon_mode": pl.String,
        "has_numeric_centre": pl.Boolean,
        **dict(schema_cols),
        "missing_reason": pl.String,
    }
    out = pl.DataFrame(rows, schema=base_schema)
    meta = {
        "rows": out.height,
        "columns": out.width,
        "withNumericCentre": int(out.filter(pl.col("has_numeric_centre")).height),
        "withoutNumericCentre": int(out.filter(~pl.col("has_numeric_centre")).height),
        "marsCount": int(out.filter(pl.col("body") == "mars").height),
        "moonCount": int(out.filter(pl.col("body") == "moon").height),
        "scope": "Native planetary target profiles from local derived snapshots; zero Earth H3 assignment (ADR-0008); TES excluded pending projection review.",
        "nullCounts": {c: int(out[c].null_count()) for c in out.columns},
    }
    return out, meta
