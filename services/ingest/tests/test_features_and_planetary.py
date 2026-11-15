import json
import struct
import unittest

import numpy as np
import polars as pl
import yaml

from p0ingest.assemble import DERIVED, REPO, nonfinite_counts, normalize_frame
from p0ingest.features import EONET_COLS, FEATURE_SPECS, build_earth_features, compute_feature_scales
from p0ingest.planetary_assemble import (
    great_circle_km,
    lookup_moon_geo_unit,
    norm_lon_180,
    norm_lon_360,
    point_in_wkb_polygon,
)


def _make_wkb_polygon(rings: list[list[tuple[float, float]]]) -> bytes:
    parts = [struct.pack("<BII", 1, 3, len(rings))]
    for ring in rings:
        parts.append(struct.pack("<I", len(ring)))
        for x, y in ring:
            parts.append(struct.pack("<dd", x, y))
    return b"".join(parts)


def _make_wkb_multipolygon(polygons: list[list[list[tuple[float, float]]]]) -> bytes:
    parts = [struct.pack("<BII", 1, 6, len(polygons))]
    for rings in polygons:
        parts.append(_make_wkb_polygon(rings))
    return b"".join(parts)


class EarthFeaturesUnitTests(unittest.TestCase):
    def _sample_inputs(self):
        h3s = ["h1", "h2", "h3", "h4", "h5"]
        base_cols = {
            "h3": h3s,
            "lat": [-80.0, -25.0, 0.0, 25.0, 75.0],
            "lon": [10.0, 20.0, 30.0, 40.0, 50.0],
            "land_pct_mean": [100.0, 100.0, 100.0, 100.0, 100.0],
            "elev_mean_m": [100.0, 200.0, 300.0, 400.0, 500.0],
            "elev_min_m": [50.0, 150.0, 250.0, 350.0, 450.0],
            "elev_max_m": [150.0, 260.0, 380.0, 520.0, 610.0],
            "slope_mean_deg": [1.0, 2.0, 3.0, 4.0, 5.0],
            "slope_frac_lt5": [0.9, 0.8, 0.7, 0.6, 0.5],
            "slope_frac_lt15": [1.0, 0.95, 0.9, 0.85, 0.8],
            "slope_frac_gt30": [0.0, 0.01, 0.02, 0.03, 0.04],
            "sun_noon_elev_min_deg": [0.0, 30.0, 66.0, 40.0, 0.0],
            "sun_noon_elev_max_deg": [33.0, 88.0, 90.0, 88.0, 38.0],
            "lst_day_max_k": [250.0, 305.0, 310.0, 300.0, 260.0],
            "lst_night_min_k": [220.0, 275.0, 285.0, 270.0, 230.0],
            "lst_diurnal_range_mean_k": [0.2, 20.0, 15.0, 25.0, None],
            "albedo_ws_sw_mean": [0.8, 0.3, 0.2, 0.25, None],
            "albedo_bs_sw_mean": [0.75, 0.25, 0.18, 0.22, None],
            "barren_pct": [0.0, 90.0, 50.0, 80.0, 10.0],
            "snow_ice_pct": [99.0, 0.0, 0.0, 0.0, 85.0],
            "vcf_percent_tree_cover_pct_mean": [0.0, 2.0, 30.0, 5.0, 0.0],
            "vcf_percent_nontree_vegetation_pct_mean": [0.0, 6.0, 20.0, 15.0, 5.0],
            "vcf_percent_nonvegetated_pct_mean": [100.0, 92.0, 50.0, 80.0, 95.0],
            "emit_n_observed": [None, 12, 4, None, None],
            "emit_min_hydration_share": [None, 0.2, 0.1, None, None],
            "emit_min_hydration_bd_med": [None, 0.05, 0.03, None, None],
            "emit_min_fe_mg_smectite_share": [None, 0.1, 0.05, None, None],
            "emit_min_fe_mg_smectite_bd_med": [None, 0.04, 0.02, None, None],
            "emit_min_al_oh_share": [None, 0.08, 0.04, None, None],
            "emit_min_al_oh_bd_med": [None, 0.03, 0.01, None, None],
            "emit_min_sulfate_share": [None, 0.02, 0.0, None, None],
            "emit_min_sulfate_bd_med": [None, 0.01, None, None, None],
            "emit_min_carbonate_share": [None, 0.05, 0.0, None, None],
            "emit_min_carbonate_bd_med": [None, 0.02, None, None, None],
            "emit_min_mafic_bd_1um_share": [None, 0.03, 0.01, None, None],
            "emit_min_mafic_bd_1um_bd_med": [None, 0.02, 0.01, None, None],
            "emit_min_dust_proxy_share": [None, 0.4, 0.2, None, None],
            "emit_min_dust_proxy_bd_med": [None, 0.06, 0.03, None, None],
            "permafrost_pct": [95.0, None, None, None, 90.0],
            "regolith_thick_m": [None, 5.0, 8.0, 3.0, 2.0],
            "soil_thick_m": [None, 1.0, 2.0, 1.5, 0.5],
            "sediment_thick_m": [None, 3.0, 4.0, 2.0, 1.0],
            "avg_soil_sed_thick_m": [None, 2.5, 3.5, 1.8, 0.9],
            "hillslope_frac_mean": [None, 0.8, 0.9, 0.7, 0.6],
            "dust_aod_mean": [0.01, 0.12, 0.08, 0.06, 0.02],
            "dust_aod_max": [0.03, 0.30, 0.15, 0.12, 0.05],
            "wind_speed_mean": [6.0, 4.0, 3.0, 5.0, 7.0],
            "access_min_median": [None, 300.0, 120.0, 180.0, 900.0],
            "access_min_p10": [None, 200.0, 90.0, 120.0, 600.0],
            "airport_km": [500.0, 120.0, 60.0, 80.0, 300.0],
            "protected_pct": [0.0, 10.0, 25.0, 15.0, 5.0],
            "polar_day": [True, False, False, False, True],
            "polar_night": [True, False, False, False, True],
        }
        for c in EONET_COLS:
            base_cols[c] = [0, 1, 0, 2, 0]
        sites = pl.DataFrame(base_cols).with_columns(
            pl.lit(json.dumps({
                "lst_diurnal_range_mean_k": "missing",
                "albedo_ws_sw_mean": "missing",
                "albedo_bs_sw_mean": "missing",
                "permafrost_pct": "outside-permafrost-domain",
                "regolith_thick_m": "outside-soilgrids-domain",
                "soil_thick_m": "outside-soilgrids-domain",
                "sediment_thick_m": "outside-soilgrids-domain",
                "avg_soil_sed_thick_m": "outside-soilgrids-domain",
                "hillslope_frac_mean": "outside-soilgrids-domain",
                "access_min_median": "no-valid-pixels",
                "access_min_p10": "no-valid-pixels",
                "emit_n_observed": "no-emit-pixels",
                "emit_min_hydration_share": "no-emit-pixels",
                "emit_min_hydration_bd_med": "no-emit-pixels",
                "emit_min_fe_mg_smectite_share": "no-emit-pixels",
                "emit_min_fe_mg_smectite_bd_med": "no-emit-pixels",
                "emit_min_al_oh_share": "no-emit-pixels",
                "emit_min_al_oh_bd_med": "no-emit-pixels",
                "emit_min_sulfate_share": "no-emit-pixels",
                "emit_min_sulfate_bd_med": "no-emit-pixels",
                "emit_min_carbonate_share": "no-emit-pixels",
                "emit_min_carbonate_bd_med": "no-emit-pixels",
                "emit_min_mafic_bd_1um_share": "no-emit-pixels",
                "emit_min_mafic_bd_1um_bd_med": "no-emit-pixels",
                "emit_min_dust_proxy_share": "no-emit-pixels",
                "emit_min_dust_proxy_bd_med": "no-emit-pixels",
            })).alias("missing_reason")
        )
        m_rows = []
        for idx, h in enumerate(h3s):
            for m in (1, 7):
                m_rows.append({
                    "h3": h,
                    "month": m,
                    "daylight_h": float((m + idx) % 24),
                    "polar_day": idx in (0, 4) and m == 1,
                    "polar_night": idx in (0, 4) and m == 7,
                    "aqua_lst_day_k": 260.0 + idx * 10 + m if idx != 4 else None,
                    "aqua_lst_night_k": 230.0 + idx * 10 if idx != 4 else None,
                    "aqua_lst_diurnal_k": 20.0 + idx if idx != 4 else None,
                    "dust_aod": 0.05 + 0.02 * m,
                    "wind_speed": 3.0 + 0.5 * m,
                    "wind_speed_max": 8.0 + m,
                    "burned_pct": 0.0 if m == 1 else float(idx),
                })
        monthly = pl.DataFrame(m_rows)
        spread = pl.DataFrame([
            {
                "h3": h,
                "month": 1,
                "lst_day_p10_k": 290.0,
                "lst_day_p90_k": 300.0 + i,
                "lst_night_p10_k": 265.0 + i,
                "lst_night_p90_k": 272.0 + i,
                "lst_years_with_value": 8,
            }
            for i, h in enumerate(h3s)
        ])
        palsar = pl.DataFrame({
            "h3": ["h2"],
            "scene_urs": [["UR_A", "UR_B"]],
            "gamma0_hh_db": pl.Series([None], dtype=pl.Float64),
            "gamma0_hv_db": pl.Series([None], dtype=pl.Float64),
        })
        return sites, monthly, spread, palsar

    def test_earth_features_missing_reason_and_ati_guard_and_reversibility(self):
        sites, monthly, spread, palsar = self._sample_inputs()
        ef, meta = build_earth_features(
            sites, monthly, spread=spread, palsar=palsar, arads_count_by_h3={"h2": 3}
        )
        self.assertEqual(ef.height, 5)
        self.assertEqual(ef["h3"].to_list(), ["h1", "h2", "h3", "h4", "h5"])
        self.assertEqual(nonfinite_counts(ef), {})

        # h1 has lst_diurnal_range_mean_k = 0.2 <= 0.5 -> ati_terra_proxy must be null (no division blowup)
        self.assertIsNone(ef["ati_terra_proxy"][0])
        self.assertAlmostEqual(ef["ati_terra_proxy"][1], (1.0 - 0.25) / 20.0)
        # h2 has PALSAR provenance count = 2, ARADS count = 3, backscatter remains null
        self.assertEqual(ef["palsar_scene_count"][1], 2)
        self.assertEqual(ef["arads_campaign_result_count"][1], 3)
        self.assertIsNone(ef["palsar_gamma0_hh_db"][1])
        self.assertEqual(ef["eonet_total_events"][3], 2 * len(EONET_COLS))

        # Derived differences are marked computed
        for diff_col in ("relief_cell_m", "albedo_ws_bs_diff", "vcf_barren_mcd12_diff_pct"):
            self.assertEqual(FEATURE_SPECS[diff_col]["kind"], "computed")

        # Every null column equals its JSON missing_reason keys
        feat_cols = [c for c in ef.columns if c not in ("h3", "lat", "lon", "missing_reason")]
        for r in ef.iter_rows(named=True):
            mr = json.loads(r["missing_reason"])
            nulls = {c for c in feat_cols if r[c] is None}
            self.assertEqual(nulls, set(mr.keys()))
            self.assertNotIn("null-without-reason", mr.values())

        # Reversible normalization check
        scales = compute_feature_scales(ef, FEATURE_SPECS)
        norm_ef, info = normalize_frame(ef, scales)
        self.assertEqual(nonfinite_counts(norm_ef), {})
        self.assertNotIn("emit_n_observed", info["scaledColumns"])
        self.assertNotIn("palsar_scene_count", info["scaledColumns"])
        self.assertEqual(norm_ef["emit_n_observed"].to_list(), ef["emit_n_observed"].to_list())
        for col in info["scaledColumns"]:
            sc = scales[col]
            med, iqr = float(sc["median"]), float(sc["iqr"])
            for raw_v, z_v in zip(ef[col].to_list(), norm_ef[col].to_list()):
                if raw_v is None:
                    self.assertIsNone(z_v)
                else:
                    self.assertAlmostEqual(z_v * iqr + med, float(raw_v), places=9)

    def test_missing_spread_and_all_null_eonet_stay_null(self):
        sites, monthly, _, palsar = self._sample_inputs()
        sites = sites.with_columns([pl.lit(None, dtype=pl.Int64).alias(c) for c in EONET_COLS])
        ef, _ = build_earth_features(sites, monthly, spread=None, palsar=palsar)
        self.assertEqual(ef["lst_years_min_count"].null_count(), ef.height)
        self.assertEqual(ef["eonet_total_events"].null_count(), ef.height)
        mr0 = json.loads(ef["missing_reason"][0])
        self.assertEqual(mr0["lst_years_min_count"], "no-monthly-spread-rows")
        self.assertEqual(mr0["eonet_total_events"], "eonet-unavailable")

    def test_partial_null_eonet_stays_null_with_reason(self):
        sites, monthly, spread, palsar = self._sample_inputs()
        sites = sites.with_columns(
            [pl.lit(0, dtype=pl.Int64).alias(EONET_COLS[0])]
            + [pl.lit(None, dtype=pl.Int64).alias(c) for c in EONET_COLS[1:]]
        )
        ef, _ = build_earth_features(sites, monthly, spread=spread, palsar=palsar)
        self.assertEqual(ef["eonet_total_events"].null_count(), ef.height)
        for r in ef.iter_rows(named=True):
            mr = json.loads(r["missing_reason"])
            self.assertEqual(mr["eonet_total_events"], "partial-eonet-categories-missing")


class PlanetaryGeometryUnitTests(unittest.TestCase):
    def test_wkb_polygon_with_hole_and_lon_wrapping(self):
        # Outer square [0..10] x [0..10], hole [3..7] x [3..7]
        wkb = _make_wkb_polygon([
            [(0.0, 0.0), (10.0, 0.0), (10.0, 10.0), (0.0, 10.0), (0.0, 0.0)],
            [(3.0, 3.0), (7.0, 3.0), (7.0, 7.0), (3.0, 7.0), (3.0, 3.0)],
        ])
        self.assertTrue(point_in_wkb_polygon(1.5, 1.5, wkb))
        self.assertFalse(point_in_wkb_polygon(5.0, 5.0, wkb))
        self.assertFalse(point_in_wkb_polygon(12.0, 5.0, wkb))
        self.assertAlmostEqual(norm_lon_180(354.473), -5.527, places=6)
        self.assertAlmostEqual(norm_lon_360(-33.55), 326.45, places=6)
        d = great_circle_km(0.0, 0.0, np.array([0.0]), np.array([180.0]), 1737.4)[0]
        self.assertAlmostEqual(float(d), np.pi * 1737.4, places=4)

    def test_wkb_multipolygon_and_smallest_area_geo_tie_break(self):
        multi_wkb = _make_wkb_multipolygon([
            [[(0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 1.0), (0.0, 0.0)]],
            [[(4.0, 4.0), (5.0, 4.0), (5.0, 5.0), (4.0, 5.0), (4.0, 4.0)]],
        ])
        self.assertTrue(point_in_wkb_polygon(0.5, 0.5, multi_wkb))
        self.assertTrue(point_in_wkb_polygon(4.5, 4.5, multi_wkb))
        self.assertFalse(point_in_wkb_polygon(2.5, 2.5, multi_wkb))

        big_wkb = _make_wkb_polygon([[(0.0, 0.0), (10.0, 0.0), (10.0, 10.0), (0.0, 10.0), (0.0, 0.0)]])
        small_wkb = _make_wkb_polygon([[(2.0, 2.0), (3.0, 2.0), (3.0, 3.0), (2.0, 3.0), (2.0, 2.0)]])
        # Big outer polygon listed before small nested polygon; smallest area_geo must win
        polys = pl.DataFrame({
            "unit_code": ["BIG", "SMALL", "MULTI"],
            "unit_name": ["Big Basin", "Small Crater", "Multi Unit"],
            "unit_era": ["Imbrian", "Copernican", "Nectarian"],
            "unit_material": ["plains", "crater", "highlands"],
            "area_geo": [100.0, 1.0, 2.0],
            "lon_min": [0.0, 2.0, 0.0],
            "lon_max": [10.0, 3.0, 5.0],
            "lat_min": [0.0, 2.0, 0.0],
            "lat_max": [10.0, 3.0, 5.0],
            "geometry": [big_wkb, small_wkb, multi_wkb],
        })
        hit_nested = lookup_moon_geo_unit(polys, 2.5, 2.5)
        self.assertIsNotNone(hit_nested)
        self.assertEqual(hit_nested["unit_code"], "SMALL")

        hit_multi = lookup_moon_geo_unit(polys, 0.5, 0.5)
        self.assertIsNotNone(hit_multi)
        self.assertEqual(hit_multi["unit_code"], "MULTI")


class AssembledParquetsContractTests(unittest.TestCase):
    def test_columns_evidence_and_feature_prep_consistency(self):
        reg = yaml.safe_load((REPO / "data/pipeline/columns.yaml").read_text(encoding="utf-8"))
        self.assertIn("emit-min-r4", reg["sources"])
        self.assertIn("vcf-r4", reg["sources"])
        self.assertEqual(reg["derived"]["sites-r4-monthly-spread"]["status"], "active")
        sites_cols = {c["name"]: c for c in reg["tables"]["sites-r4"]["columns"]}
        for col in ("emit_n_observed", "emit_min_hydration_share", "vcf_percent_nonvegetated_pct_mean"):
            self.assertEqual(sites_cols[col]["status"], "active")

        prep = yaml.safe_load((REPO / "data/pipeline/feature-preparation.yaml").read_text(encoding="utf-8"))
        ef_cols = {f.get("earthFeatureColumn") for f in prep["features"].values() if f.get("earthFeatureColumn")}
        self.assertTrue(ef_cols.issubset(set(FEATURE_SPECS.keys())))

    def test_assembled_outputs_on_disk_when_present(self):
        ef_path = DERIVED / "assembled" / "earth-features-r4.parquet"
        pl_path = DERIVED / "assembled" / "planetary-targets.parquet"
        sp_path = DERIVED / "assembled" / "sites-r4-monthly-spread.parquet"
        if not (ef_path.exists() and pl_path.exists()):
            self.skipTest("assembled outputs not built in this checkout")

        sp = pl.read_parquet(sp_path)
        self.assertEqual(sp.height, 91_800 * 12)

        ef = pl.read_parquet(ef_path)
        ef_norm = pl.read_parquet(DERIVED / "assembled" / "earth-features-r4-normalized.parquet")
        self.assertEqual(ef.height, 91_800)
        self.assertEqual(ef_norm.height, 91_800)
        self.assertEqual(nonfinite_counts(ef), {})
        self.assertEqual(nonfinite_counts(ef_norm), {})
        self.assertFalse(ef["missing_reason"].str.contains("null-without-reason").any())
        self.assertGreater(ef.filter(pl.col("arads_campaign_result_count") > 0).height, 0)
        self.assertEqual(ef.filter(pl.col("palsar_scene_count") > 0).height, 35)

        pt = pl.read_parquet(pl_path)
        self.assertEqual(pt.height, 47)
        self.assertNotIn("h3", pt.columns)
        self.assertEqual(nonfinite_counts(pt), {})
        self.assertEqual(pt["mars_tes_ti_day_si"].null_count(), 47)
        self.assertEqual(pt["mars_tes_ti_night_si"].null_count(), 47)
        self.assertFalse(pt["missing_reason"].str.contains("null-without-reason").any())
        shackleton = pt.filter(pl.col("target_id") == "moon-feature-shackleton").row(0, named=True)
        self.assertAlmostEqual(shackleton["moon_psr_frac_2km"], 1.0, places=3)
        self.assertLess(shackleton["target_elevation_m"], -2500.0)


if __name__ == "__main__":
    unittest.main()
