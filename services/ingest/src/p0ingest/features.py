"""Clean Earth feature engineering and reversible normalization (stage F, #154).

Builds assembled/earth-features-r4.parquet and earth-features-r4-normalized.parquet
from the assembled workflow tables without fabricating data, filling gaps, clipping
outliers, or computing a single scalar site analogy score (AGENTS.md rule 4).

Derived physical features implemented cleanly here:
  - lat_abs_deg: |lat| (deg, geometry)
  - relief_cell_m: elev_max_m - elev_min_m (m, cell elevation relief)
  - polar_day_frac, polar_night_frac: fraction of 12 calendar months with polar_day / polar_night
  - daylight_h_min, daylight_h_mean, daylight_h_max: annual bounds/mean of monthly daylight hours
  - aqua_lst_day_max_k, aqua_lst_night_min_k, aqua_lst_diurnal_mean_k: MYD11C3 ~13:30/~01:30 summaries
  - ati_terra_proxy, ati_aqua_proxy: apparent thermal inertia (1 - albedo_bs_sw_mean) / diurnal_range_k
  - albedo_ws_bs_diff: albedo_ws_sw_mean - albedo_bs_sw_mean (bidirectional vs diffuse SW contrast)
  - vcf_barren_mcd12_diff_pct: vcf_percent_nonvegetated_pct_mean - barren_pct (MOD44B vs MCD12C1)
  - wind_speed_max_annual, wind_speed_seasonal_amp: MERRA-2 peak & seasonal wind spread (m/s)
  - dust_aod_seasonal_amp: MERRA-2 DUEXTTAU seasonal range (max - min monthly mean)
  - burned_pct_annual_mean, burned_pct_annual_max: MCD64A1 monthly burned share summaries (%)
  - eonet_total_events: sum of reported EONET event counts across the 10 hazard categories
  - lst_day_interannual_iqr_mean_k, lst_night_interannual_iqr_mean_k,
    lst_day_2014_2023_p90_k, lst_night_2014_2023_p10_k, lst_years_min_count:
    2014-2023 multi-year thermal volatility and tail bounds (from sites-r4-monthly-spread)
  - palsar_gamma0_hh_db, palsar_gamma0_hv_db, palsar_scene_count, arads_campaign_result_count:
    regional campaign provenance attached explicitly (never inventing unfetched backscatter)
"""
from __future__ import annotations

import json
import math
from typing import Iterable

import polars as pl

from .grid import DERIVED
from .snapshots import REPO, sha256

FEATURE_SPECS: dict[str, dict] = {
    # Identifiers & coordinates (unscaled)
    "h3": {"kind": "key", "trait": None, "unit": "h3"},
    "lat": {"kind": "coord", "trait": None, "unit": "deg"},
    "lon": {"kind": "coord", "trait": None, "unit": "deg"},
    "land_pct_mean": {"kind": "observed", "trait": None, "unit": "%"},
    # Terrain & geometry
    "lat_abs_deg": {"kind": "computed", "trait": "operations", "unit": "deg"},
    "elev_mean_m": {"kind": "observed", "trait": "terrain", "unit": "m"},
    "elev_min_m": {"kind": "observed", "trait": "terrain", "unit": "m"},
    "elev_max_m": {"kind": "observed", "trait": "terrain", "unit": "m"},
    "relief_cell_m": {"kind": "computed", "trait": "terrain", "unit": "m"},
    "slope_mean_deg": {"kind": "observed", "trait": "terrain", "unit": "deg"},
    "slope_frac_lt5": {"kind": "observed", "trait": "terrain", "unit": "1"},
    "slope_frac_lt15": {"kind": "observed", "trait": "terrain", "unit": "1"},
    "slope_frac_gt30": {"kind": "observed", "trait": "hazard", "unit": "1"},
    # Illumination
    "sun_noon_elev_min_deg": {"kind": "computed", "trait": "illumination", "unit": "deg"},
    "sun_noon_elev_max_deg": {"kind": "computed", "trait": "illumination", "unit": "deg"},
    "daylight_h_min": {"kind": "computed", "trait": "illumination", "unit": "h"},
    "daylight_h_mean": {"kind": "computed", "trait": "illumination", "unit": "h"},
    "daylight_h_max": {"kind": "computed", "trait": "illumination", "unit": "h"},
    "polar_day_frac": {"kind": "computed", "trait": "illumination", "unit": "1"},
    "polar_night_frac": {"kind": "computed", "trait": "illumination", "unit": "1"},
    "polar_day": {"kind": "yes/no", "trait": "illumination", "unit": "bool"},
    "polar_night": {"kind": "yes/no", "trait": "illumination", "unit": "bool"},
    # Thermal & ATI
    "lst_day_max_k": {"kind": "observed", "trait": "thermal", "unit": "K"},
    "lst_night_min_k": {"kind": "observed", "trait": "thermal", "unit": "K"},
    "lst_diurnal_range_mean_k": {"kind": "observed", "trait": "thermal", "unit": "K"},
    "aqua_lst_day_max_k": {"kind": "observed", "trait": "thermal", "unit": "K"},
    "aqua_lst_night_min_k": {"kind": "observed", "trait": "thermal", "unit": "K"},
    "aqua_lst_diurnal_mean_k": {"kind": "observed", "trait": "thermal", "unit": "K"},
    "ati_terra_proxy": {"kind": "proxy", "trait": "thermal", "unit": "K^-1"},
    "ati_aqua_proxy": {"kind": "proxy", "trait": "thermal", "unit": "K^-1"},
    "lst_day_interannual_iqr_mean_k": {"kind": "observed", "trait": "thermal", "unit": "K"},
    "lst_night_interannual_iqr_mean_k": {"kind": "observed", "trait": "thermal", "unit": "K"},
    "lst_day_2014_2023_p90_k": {"kind": "observed", "trait": "thermal", "unit": "K"},
    "lst_night_2014_2023_p10_k": {"kind": "observed", "trait": "thermal", "unit": "K"},
    "lst_years_min_count": {"kind": "diagnostic", "role": "diagnostic", "trait": None, "unit": "count"},
    # Surface material, albedo, VCF, EMIT mineral proxies
    "albedo_ws_sw_mean": {"kind": "observed", "trait": "surfaceMaterial", "unit": "1"},
    "albedo_bs_sw_mean": {"kind": "observed", "trait": "surfaceMaterial", "unit": "1"},
    "albedo_ws_bs_diff": {"kind": "computed", "trait": "surfaceMaterial", "unit": "1"},
    "barren_pct": {"kind": "observed", "trait": "surfaceMaterial", "unit": "%"},
    "snow_ice_pct": {"kind": "observed", "trait": "surfaceMaterial", "unit": "%"},
    "vcf_percent_tree_cover_pct_mean": {"kind": "observed", "trait": "surfaceMaterial", "unit": "%"},
    "vcf_percent_nontree_vegetation_pct_mean": {"kind": "observed", "trait": "surfaceMaterial", "unit": "%"},
    "vcf_percent_nonvegetated_pct_mean": {"kind": "observed", "trait": "surfaceMaterial", "unit": "%"},
    "vcf_barren_mcd12_diff_pct": {"kind": "computed", "trait": "surfaceMaterial", "unit": "%"},
    "emit_n_observed": {"kind": "diagnostic", "role": "diagnostic", "trait": None, "unit": "count"},
    "emit_has_observation": {"kind": "yes/no", "trait": "surfaceMaterial", "unit": "bool"},
    "emit_min_hydration_share": {"kind": "proxy", "trait": "surfaceMaterial", "unit": "1"},
    "emit_min_hydration_bd_med": {"kind": "proxy", "trait": "surfaceMaterial", "unit": "1"},
    "emit_min_fe_mg_smectite_share": {"kind": "proxy", "trait": "surfaceMaterial", "unit": "1"},
    "emit_min_fe_mg_smectite_bd_med": {"kind": "proxy", "trait": "surfaceMaterial", "unit": "1"},
    "emit_min_al_oh_share": {"kind": "proxy", "trait": "surfaceMaterial", "unit": "1"},
    "emit_min_al_oh_bd_med": {"kind": "proxy", "trait": "surfaceMaterial", "unit": "1"},
    "emit_min_sulfate_share": {"kind": "proxy", "trait": "surfaceMaterial", "unit": "1"},
    "emit_min_sulfate_bd_med": {"kind": "proxy", "trait": "surfaceMaterial", "unit": "1"},
    "emit_min_carbonate_share": {"kind": "proxy", "trait": "surfaceMaterial", "unit": "1"},
    "emit_min_carbonate_bd_med": {"kind": "proxy", "trait": "surfaceMaterial", "unit": "1"},
    "emit_min_mafic_bd_1um_share": {"kind": "proxy", "trait": "surfaceMaterial", "unit": "1"},
    "emit_min_mafic_bd_1um_bd_med": {"kind": "proxy", "trait": "surfaceMaterial", "unit": "1"},
    "emit_min_dust_proxy_share": {"kind": "proxy", "trait": "dustProcess", "unit": "1"},
    "emit_min_dust_proxy_bd_med": {"kind": "proxy", "trait": "dustProcess", "unit": "1"},
    # Subsurface & waterIce
    "permafrost_pct": {"kind": "modeled", "trait": "waterIce", "unit": "%"},
    "regolith_thick_m": {"kind": "modeled", "trait": "subsurface", "unit": "m"},
    "soil_thick_m": {"kind": "modeled", "trait": "subsurface", "unit": "m"},
    "sediment_thick_m": {"kind": "modeled", "trait": "subsurface", "unit": "m"},
    "avg_soil_sed_thick_m": {"kind": "modeled", "trait": "subsurface", "unit": "m"},
    "hillslope_frac_mean": {"kind": "modeled", "trait": "subsurface", "unit": "1"},
    # Dust, wind, hazards, operations
    "dust_aod_mean": {"kind": "reanalysis", "trait": "dustProcess", "unit": "1"},
    "dust_aod_max": {"kind": "reanalysis", "trait": "dustProcess", "unit": "1"},
    "dust_aod_seasonal_amp": {"kind": "reanalysis", "trait": "dustProcess", "unit": "1"},
    "wind_speed_mean": {"kind": "reanalysis", "trait": "operations", "unit": "m/s"},
    "wind_speed_max_annual": {"kind": "reanalysis", "trait": "hazard", "unit": "m/s"},
    "wind_speed_seasonal_amp": {"kind": "reanalysis", "trait": "operations", "unit": "m/s"},
    "burned_pct_annual_mean": {"kind": "observed", "trait": "hazard", "unit": "%"},
    "burned_pct_annual_max": {"kind": "observed", "trait": "hazard", "unit": "%"},
    "eonet_total_events": {"kind": "catalogue", "trait": "hazard", "unit": "count"},
    "access_min_median": {"kind": "modeled", "trait": "operations", "unit": "min"},
    "access_min_p10": {"kind": "modeled", "trait": "operations", "unit": "min"},
    "airport_km": {"kind": "catalogue", "trait": "operations", "unit": "km"},
    "protected_pct": {"kind": "catalogue", "trait": "operations", "unit": "%"},
    # Regional campaign provenance (diagnostic / explicit scope)
    "palsar_scene_count": {"kind": "diagnostic", "role": "diagnostic", "trait": None, "unit": "count"},
    "palsar_gamma0_hh_db": {"kind": "proxy", "trait": "operations", "unit": "dB"},
    "palsar_gamma0_hv_db": {"kind": "proxy", "trait": "waterIce", "unit": "dB"},
    "arads_campaign_result_count": {"kind": "diagnostic", "role": "diagnostic", "trait": None, "unit": "count"},
}


EONET_COLS = [
    "eonet_wildfires_events",
    "eonet_volcanoes_events",
    "eonet_severeStorms_events",
    "eonet_floods_events",
    "eonet_landslides_events",
    "eonet_dustHaze_events",
    "eonet_earthquakes_events",
    "eonet_snow_events",
    "eonet_tempExtremes_events",
    "eonet_drought_events",
]


def _json_reason_fragment(col_name: str, code_expr: pl.Expr) -> pl.Expr:
    encoded = pl.struct(code_expr.alias(col_name)).struct.json_encode().str.strip_prefix("{").str.strip_suffix("}")
    return pl.when(pl.col(col_name).is_null()).then(encoded).otherwise(None)


def _site_reason(src_col: str, fallback: str = "missing-in-sites-r4") -> pl.Expr:
    return pl.coalesce(
        pl.col("__site_mr").str.json_path_match(f"$.{src_col}"),
        pl.lit(fallback),
    )


def compute_feature_scales(df: pl.DataFrame, specs: dict[str, dict] = FEATURE_SPECS) -> dict:
    """Compute ADR-0005 D5 robust IQR statistics compatible with assemble.normalize_frame."""
    scales: dict[str, dict] = {}
    for col in df.columns:
        if col in ("h3", "lat", "lon", "missing_reason"):
            continue
        spec = specs.get(col)
        if spec is None:
            continue
        s = df[col]
        if spec.get("role") == "diagnostic" or spec.get("kind") == "diagnostic":
            scales[col] = {
                "kind": "diagnostic",
                "trait": spec.get("trait"),
                "unit": spec.get("unit"),
                "n": int(s.len() - s.null_count()),
                "inSum": False,
                "scaled": False,
                "unscaledReason": "source-diagnostic",
            }
            continue
        if s.dtype == pl.Boolean or spec.get("kind") == "yes/no":
            scales[col] = {
                "kind": "yes/no",
                "trait": spec.get("trait"),
                "unit": spec.get("unit"),
                "n": int(s.len() - s.null_count()),
                "share_true": None if s.null_count() == s.len() else round(float(s.drop_nulls().mean()), 6),
                "inSum": False,
                "scaled": False,
                "unscaledReason": "boolean",
            }
            continue
        v = s.drop_nulls().cast(pl.Float64)
        if v.len() == 0:
            scales[col] = {
                "kind": "number",
                "trait": spec.get("trait"),
                "unit": spec.get("unit"),
                "n": 0,
                "iqr": None,
                "median": None,
                "inSum": False,
                "scaled": False,
                "unscaledReason": "no-values",
            }
            continue
        q1 = float(v.quantile(0.25, "linear"))
        q3 = float(v.quantile(0.75, "linear"))
        med = float(v.median())
        iqr = q3 - q1
        in_sum = bool(math.isfinite(iqr) and iqr > 0.0)
        scales[col] = {
            "kind": "number",
            "trait": spec.get("trait"),
            "unit": spec.get("unit"),
            "n": int(v.len()),
            "min": float(v.min()),
            "q1": q1,
            "median": med,
            "q3": q3,
            "max": float(v.max()),
            "iqr": iqr,
            "inSum": in_sum,
            "scaled": in_sum,
            **({} if in_sum else {"unscaledReason": "iqr-zero"}),
        }
    return scales


def build_earth_features(
    sites: pl.DataFrame,
    monthly: pl.DataFrame,
    spread: pl.DataFrame | None = None,
    palsar: pl.DataFrame | None = None,
    arads_count_by_h3: dict[str, int] | None = None,
) -> tuple[pl.DataFrame, dict]:
    """Assemble clean Earth feature frame on the exact sites-r4 row key order."""
    base = sites.with_row_index("__row_order").rename({"missing_reason": "__site_mr"})

    # 1. Clean monthly aggregates -> annual cell features (no gap filling)
    m_agg = monthly.group_by("h3").agg([
        pl.col("daylight_h").min().alias("daylight_h_min"),
        pl.col("daylight_h").mean().alias("daylight_h_mean"),
        pl.col("daylight_h").max().alias("daylight_h_max"),
        pl.col("polar_day").cast(pl.Float64).mean().alias("polar_day_frac"),
        pl.col("polar_night").cast(pl.Float64).mean().alias("polar_night_frac"),
        pl.col("aqua_lst_day_k").max().alias("aqua_lst_day_max_k"),
        pl.col("aqua_lst_night_k").min().alias("aqua_lst_night_min_k"),
        pl.col("aqua_lst_diurnal_k").mean().alias("aqua_lst_diurnal_mean_k"),
        (pl.col("dust_aod").max() - pl.col("dust_aod").min()).alias("dust_aod_seasonal_amp"),
        pl.col("wind_speed_max").max().alias("wind_speed_max_annual"),
        (pl.col("wind_speed").max() - pl.col("wind_speed").min()).alias("wind_speed_seasonal_amp"),
        pl.col("burned_pct").mean().alias("burned_pct_annual_mean"),
        pl.col("burned_pct").max().alias("burned_pct_annual_max"),
    ])
    df = base.join(m_agg, on="h3", how="left")

    # 2. Multi-year spread summaries (2014-2023)
    if spread is not None:
        sp_agg = spread.group_by("h3").agg([
            (pl.col("lst_day_p90_k") - pl.col("lst_day_p10_k")).mean().alias("lst_day_interannual_iqr_mean_k"),
            (pl.col("lst_night_p90_k") - pl.col("lst_night_p10_k")).mean().alias("lst_night_interannual_iqr_mean_k"),
            pl.col("lst_day_p90_k").max().alias("lst_day_2014_2023_p90_k"),
            pl.col("lst_night_p10_k").min().alias("lst_night_2014_2023_p10_k"),
            pl.col("lst_years_with_value").min().cast(pl.Int16).alias("lst_years_min_count"),
        ])
        df = df.join(sp_agg, on="h3", how="left")
    else:
        df = df.with_columns([
            pl.lit(None, dtype=pl.Float64).alias("lst_day_interannual_iqr_mean_k"),
            pl.lit(None, dtype=pl.Float64).alias("lst_night_interannual_iqr_mean_k"),
            pl.lit(None, dtype=pl.Float64).alias("lst_day_2014_2023_p90_k"),
            pl.lit(None, dtype=pl.Float64).alias("lst_night_2014_2023_p10_k"),
            pl.lit(None, dtype=pl.Int16).alias("lst_years_min_count"),
        ])

    # 3. Regional PALSAR & ARADS campaign provenance
    if palsar is not None:
        p_sub = palsar.select([
            pl.col("h3"),
            pl.lit(True).alias("__in_palsar_scope"),
            pl.col("scene_urs").list.len().cast(pl.Int32).alias("palsar_scene_count"),
            pl.col("gamma0_hh_db").cast(pl.Float64).alias("palsar_gamma0_hh_db"),
            pl.col("gamma0_hv_db").cast(pl.Float64).alias("palsar_gamma0_hv_db"),
        ])
        df = df.join(p_sub, on="h3", how="left").with_columns([
            pl.col("__in_palsar_scope").fill_null(False),
            pl.col("palsar_scene_count").fill_null(0).cast(pl.Int32),
        ])
    else:
        df = df.with_columns([
            pl.lit(False).alias("__in_palsar_scope"),
            pl.lit(0, dtype=pl.Int32).alias("palsar_scene_count"),
            pl.lit(None, dtype=pl.Float64).alias("palsar_gamma0_hh_db"),
            pl.lit(None, dtype=pl.Float64).alias("palsar_gamma0_hv_db"),
        ])

    if arads_count_by_h3:
        ar_df = pl.DataFrame({
            "h3": list(arads_count_by_h3.keys()),
            "arads_campaign_result_count": pl.Series(list(arads_count_by_h3.values()), dtype=pl.Int32),
        })
        df = df.join(ar_df, on="h3", how="left").with_columns(
            pl.col("arads_campaign_result_count").fill_null(0).cast(pl.Int32)
        )
    else:
        df = df.with_columns(pl.lit(0, dtype=pl.Int32).alias("arads_campaign_result_count"))

    # 4. Derived physical features (explicit guard against tiny/zero diurnal range or missing albedo)
    df = df.with_columns([
        pl.col("lat").abs().alias("lat_abs_deg"),
        (pl.col("elev_max_m") - pl.col("elev_min_m")).alias("relief_cell_m"),
        (pl.col("albedo_ws_sw_mean") - pl.col("albedo_bs_sw_mean")).alias("albedo_ws_bs_diff"),
        (pl.col("vcf_percent_nonvegetated_pct_mean") - pl.col("barren_pct")).alias("vcf_barren_mcd12_diff_pct"),
        pl.col("emit_n_observed").is_not_null().alias("emit_has_observation"),
        pl.when(
            pl.col("albedo_bs_sw_mean").is_not_null()
            & pl.col("lst_diurnal_range_mean_k").is_not_null()
            & (pl.col("lst_diurnal_range_mean_k") > 0.5)
        )
        .then((1.0 - pl.col("albedo_bs_sw_mean")) / pl.col("lst_diurnal_range_mean_k"))
        .otherwise(None)
        .alias("ati_terra_proxy"),
        pl.when(
            pl.col("albedo_bs_sw_mean").is_not_null()
            & pl.col("aqua_lst_diurnal_mean_k").is_not_null()
            & (pl.col("aqua_lst_diurnal_mean_k") > 0.5)
        )
        .then((1.0 - pl.col("albedo_bs_sw_mean")) / pl.col("aqua_lst_diurnal_mean_k"))
        .otherwise(None)
        .alias("ati_aqua_proxy"),
        pl.when(pl.all_horizontal([pl.col(c).is_not_null() for c in EONET_COLS]))
        .then(pl.sum_horizontal([pl.col(c).cast(pl.Int64) for c in EONET_COLS]))
        .otherwise(pl.lit(None, dtype=pl.Int64))
        .alias("eonet_total_events"),
    ])

    ordered_cols = list(FEATURE_SPECS.keys())
    # Build exact per-column missing_reason fragments before projecting out helper columns
    direct_site_cols = [c for c in ordered_cols if c in sites.columns and c not in ("h3", "lat", "lon")]
    frags: list[pl.Expr] = []
    for c in direct_site_cols:
        frags.append(_json_reason_fragment(c, _site_reason(c)))

    frags.extend([
        _json_reason_fragment("lat_abs_deg", pl.lit("missing-lat")),
        _json_reason_fragment("relief_cell_m", pl.coalesce(
            pl.col("__site_mr").str.json_path_match("$.elev_max_m"),
            pl.col("__site_mr").str.json_path_match("$.elev_min_m"),
            pl.lit("missing-dem-extrema"),
        )),
        _json_reason_fragment("daylight_h_min", pl.lit("no-valid-monthly-daylight")),
        _json_reason_fragment("daylight_h_mean", pl.lit("no-valid-monthly-daylight")),
        _json_reason_fragment("daylight_h_max", pl.lit("no-valid-monthly-daylight")),
        _json_reason_fragment("polar_day_frac", pl.lit("no-valid-monthly-polar-flag")),
        _json_reason_fragment("polar_night_frac", pl.lit("no-valid-monthly-polar-flag")),
        _json_reason_fragment("aqua_lst_day_max_k", pl.lit("no-valid-aqua-lst-months")),
        _json_reason_fragment("aqua_lst_night_min_k", pl.lit("no-valid-aqua-lst-months")),
        _json_reason_fragment("aqua_lst_diurnal_mean_k", pl.lit("no-valid-aqua-lst-months")),
        _json_reason_fragment(
            "ati_terra_proxy",
            pl.when(pl.col("albedo_bs_sw_mean").is_null())
            .then(pl.lit("missing-albedo-bs-sw"))
            .when(pl.col("lst_diurnal_range_mean_k").is_null())
            .then(pl.lit("missing-terra-diurnal-range"))
            .otherwise(pl.lit("nonpositive-or-small-diurnal-range")),
        ),
        _json_reason_fragment(
            "ati_aqua_proxy",
            pl.when(pl.col("albedo_bs_sw_mean").is_null())
            .then(pl.lit("missing-albedo-bs-sw"))
            .when(pl.col("aqua_lst_diurnal_mean_k").is_null())
            .then(pl.lit("no-valid-aqua-lst-months"))
            .otherwise(pl.lit("nonpositive-or-small-diurnal-range")),
        ),
        _json_reason_fragment(
            "albedo_ws_bs_diff",
            pl.when(pl.col("albedo_ws_sw_mean").is_null())
            .then(_site_reason("albedo_ws_sw_mean", "missing-albedo-ws"))
            .otherwise(_site_reason("albedo_bs_sw_mean", "missing-albedo-bs")),
        ),
        _json_reason_fragment(
            "vcf_barren_mcd12_diff_pct",
            pl.when(pl.col("vcf_percent_nonvegetated_pct_mean").is_null())
            .then(_site_reason("vcf_percent_nonvegetated_pct_mean", "no-vcf-lattice-px"))
            .otherwise(_site_reason("barren_pct", "missing-barren-pct")),
        ),
        _json_reason_fragment(
            "lst_day_interannual_iqr_mean_k",
            pl.lit("no-monthly-spread-table" if spread is None else "too-few-years-across-all-months"),
        ),
        _json_reason_fragment(
            "lst_night_interannual_iqr_mean_k",
            pl.lit("no-monthly-spread-table" if spread is None else "too-few-years-across-all-months"),
        ),
        _json_reason_fragment(
            "lst_day_2014_2023_p90_k",
            pl.lit("no-monthly-spread-table" if spread is None else "too-few-years-across-all-months"),
        ),
        _json_reason_fragment(
            "lst_night_2014_2023_p10_k",
            pl.lit("no-monthly-spread-table" if spread is None else "too-few-years-across-all-months"),
        ),
        _json_reason_fragment("lst_years_min_count", pl.lit("no-monthly-spread-rows")),
        _json_reason_fragment("dust_aod_seasonal_amp", pl.lit("no-valid-dust-months")),
        _json_reason_fragment("wind_speed_max_annual", pl.lit("no-valid-wind-months")),
        _json_reason_fragment("wind_speed_seasonal_amp", pl.lit("no-valid-wind-months")),
        _json_reason_fragment("burned_pct_annual_mean", pl.lit("mcd64-unmapped-or-water")),
        _json_reason_fragment("burned_pct_annual_max", pl.lit("mcd64-unmapped-or-water")),
        _json_reason_fragment(
            "eonet_total_events",
            pl.when(pl.any_horizontal([pl.col(c).is_not_null() for c in EONET_COLS]))
            .then(pl.lit("partial-eonet-categories-missing"))
            .otherwise(pl.lit("eonet-unavailable")),
        ),
        _json_reason_fragment(
            "palsar_gamma0_hh_db",
            pl.when(pl.col("__in_palsar_scope")).then(pl.lit("scene-batch-unfetched")).otherwise(pl.lit("outside-palsar-campaign-clusters")),
        ),
        _json_reason_fragment(
            "palsar_gamma0_hv_db",
            pl.when(pl.col("__in_palsar_scope")).then(pl.lit("scene-batch-unfetched")).otherwise(pl.lit("outside-palsar-campaign-clusters")),
        ),
        _json_reason_fragment("palsar_scene_count", pl.lit("outside-palsar-campaign-clusters")),
        _json_reason_fragment("arads_campaign_result_count", pl.lit("no-arads-records")),
    ])

    out = (
        df.sort("__row_order")
        .with_columns(
            (pl.lit("{") + pl.concat_str(frags, separator=",", ignore_nulls=True).fill_null("") + pl.lit("}")).alias("missing_reason")
        )
        .select(ordered_cols + ["missing_reason"])
    )

    scales = compute_feature_scales(out, FEATURE_SPECS)
    meta = {
        "rows": out.height,
        "columns": out.width,
        "featureSpecs": FEATURE_SPECS,
        "scales": scales,
        "nullCounts": {c: int(out[c].null_count()) for c in out.columns},
    }
    return out, meta


def load_optional_regional_sources() -> tuple[pl.DataFrame | None, dict[str, int]]:
    palsar_path = DERIVED / "palsar-r4-sites.parquet"
    palsar = pl.read_parquet(palsar_path) if palsar_path.exists() else None
    arads_counts: dict[str, int] = {}
    arads_path = DERIVED / "campaign-measurements/arads-2019-results.parquet"
    camp_yaml = REPO / "data/campaigns/atacama-arads-2019.yaml"
    if arads_path.exists() and camp_yaml.exists():
        import yaml
        camp = yaml.safe_load(camp_yaml.read_text(encoding="utf-8"))
        arads_df = pl.read_parquet(arads_path)
        if arads_df.height > 0:
            arads_counts[camp["site"]["h3r4"]] = arads_df.height
    return palsar, arads_counts
