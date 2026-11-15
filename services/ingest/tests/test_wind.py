import json
import unittest

import numpy as np
import pyarrow as pa

from p0ingest import wind

CELLS = ["a", "b"]


def monthly_table():
    return pa.table({"h3": ["a"] * 12 + ["b"] * 12,
                     "month": list(range(1, 13)) * 2})


class WindKeys(unittest.TestCase):
    def test_complete_domain(self):
        self.assertEqual(wind.validate_keys(monthly_table(), CELLS), [])

    def test_wrong_row_count_is_rejected(self):
        rows = monthly_table().to_pylist()[:-1]
        self.assertTrue(wind.validate_keys(pa.Table.from_pylist(rows), CELLS))

    def test_duplicate_month_is_rejected(self):
        rows = monthly_table().to_pylist()
        rows[3] = {"h3": "a", "month": 1}
        self.assertTrue(wind.validate_keys(pa.Table.from_pylist(rows), CELLS))

    def test_invalid_month_is_rejected(self):
        rows = monthly_table().to_pylist()
        rows[0] = {"h3": "a", "month": 13}
        self.assertTrue(wind.validate_keys(pa.Table.from_pylist(rows), CELLS))
        rows[0] = {"h3": "a", "month": 0}
        self.assertTrue(wind.validate_keys(pa.Table.from_pylist(rows), CELLS))

    def test_unknown_cell_is_rejected(self):
        rows = monthly_table().to_pylist()
        rows[0] = {"h3": "c", "month": 1}
        self.assertTrue(wind.validate_keys(pa.Table.from_pylist(rows), CELLS))

    def test_null_key_is_rejected(self):
        rows = monthly_table().to_pylist()
        rows[0] = {"h3": None, "month": 1}
        self.assertTrue(wind.validate_keys(pa.Table.from_pylist(rows), CELLS))
        rows[0] = {"h3": "a", "month": None}
        self.assertTrue(wind.validate_keys(pa.Table.from_pylist(rows), CELLS))

    def test_missing_pair_is_rejected(self):
        rows = [r for r in monthly_table().to_pylist() if not (r["h3"] == "b" and r["month"] == 12)]
        self.assertTrue(wind.validate_keys(pa.Table.from_pylist(rows), CELLS))


class GranuleMonth(unittest.TestCase):
    def test_parses_month_both_collections(self):
        self.assertEqual(wind.month_of("data/snapshots/merra2-m2tmnxflx/"
                                      "MERRA2_400.tavgM_2d_flx_Nx.202301.nc4"), 1)
        self.assertEqual(wind.month_of("data/snapshots/merra2-m2tmnxslv/"
                                      "MERRA2_400.tavgM_2d_slv_Nx.202312.nc4"), 12)

    def test_rejects_wrong_year(self):
        with self.assertRaises(ValueError):
            wind.month_of("MERRA2_400.tavgM_2d_flx_Nx.202201.nc4")

    def test_rejects_invalid_month(self):
        with self.assertRaises(ValueError):
            wind.month_of("MERRA2_400.tavgM_2d_flx_Nx.202313.nc4")
        with self.assertRaises(ValueError):
            wind.month_of("MERRA2_400.tavgM_2d_slv_Nx.202300.nc4")

    def test_rejects_other_name_shape(self):
        with self.assertRaises(ValueError):
            wind.month_of("MERRA2_400.tavg1_2d_flx_Nx.202301.nc4")
        with self.assertRaises(ValueError):
            wind.month_of("MERRA2_400.tavgM_2d_aer_Nx.202301.nc4")

    def test_collection_of(self):
        self.assertEqual(wind.collection_of("MERRA2_400.tavgM_2d_flx_Nx.202301.nc4"), wind.DATASET_FLX)
        self.assertEqual(wind.collection_of("MERRA2_400.tavgM_2d_slv_Nx.202301.nc4"), wind.DATASET_SLV)

    def test_granules_rejects_duplicate_months(self):
        entry = {"datasetId": "merra2-m2tmnxflx", "localPath": "x/MERRA2_400.tavgM_2d_flx_Nx.202301.nc4"}
        orig = wind.load_manifest

        def fake():
            return {"entries": [entry, dict(entry)]}
        wind.load_manifest = fake
        try:
            with self.assertRaises(ValueError):
                wind.granules(wind.DATASET_FLX)
        finally:
            wind.load_manifest = orig

    def test_granules_rejects_filename_collection_mismatch(self):
        entry = {"datasetId": "merra2-m2tmnxflx", "localPath": "MERRA2_400.tavgM_2d_slv_Nx.202301.nc4"}
        orig = wind.load_manifest

        def fake():
            return {"entries": [entry]}
        wind.load_manifest = fake
        try:
            with self.assertRaises(ValueError):
                wind.granules(wind.DATASET_FLX)
        finally:
            wind.load_manifest = orig


class NearestCenter(unittest.TestCase):
    # synthetic 5-lat x 8-lon grid: lat -60..60 step 30, lon -180..135 step 45 (wraps 360)
    glat = np.array([-60.0, -30.0, 0.0, 30.0, 60.0])
    glon = np.array([-180.0, -135.0, -90.0, -45.0, 0.0, 45.0, 90.0, 135.0])

    def test_interior_exact_and_middle(self):
        ilat, ilon = wind.nearest_ij([0.0], [-90.0], self.glat, self.glon)
        self.assertEqual((int(ilat[0]), int(ilon[0])), (2, 2))

    def test_longitude_wraparound_both_sides_of_dateline(self):
        ilat, ilon = wind.nearest_ij([0.0, 0.0], [179.9, -179.9], self.glat, self.glon)
        self.assertEqual(int(ilon[0]), 0)   # 179.9 E -> grid column 0 (lon -180)
        self.assertEqual(int(ilon[1]), 0)   # 179.9 W -> same column, wraps the other way
        ilat2, ilon2 = wind.nearest_ij([0.0, 0.0], [150.0, -150.0], self.glat, self.glon)
        self.assertEqual(int(ilon2[0]), 7)  # 150 E -> 135
        self.assertEqual(int(ilon2[1]), 1)  # 150 W -> -135

    def test_poles_clip_to_end_rows(self):
        ilat, _ = wind.nearest_ij([89.0, -89.0, 59.0], [0.0, 0.0, 0.0], self.glat, self.glon)
        self.assertEqual([int(x) for x in ilat], [4, 0, 4])

    def test_out_of_range_latitude_is_clipped_not_wrapped(self):
        ilat, _ = wind.nearest_ij([90.0, -90.0], [0.0, 0.0], self.glat, self.glon)
        self.assertEqual([int(x) for x in ilat], [4, 0])

    def test_halfway_ties_are_deterministic(self):
        i0, _ = wind.nearest_ij(np.full(500, 15.0), np.zeros(500), self.glat, self.glon)
        self.assertEqual(int(i0.min()), int(i0.max()))  # rint half-to-even: stable across the array

    def test_nonuniform_grid_raises(self):
        with self.assertRaises(ValueError):
            wind.nearest_ij([0.0], [0.0], np.array([-2.0, 0.0, 1.0]), self.glon)


class AnnualAggregation(unittest.TestCase):
    def test_mean_of_monthly_speeds(self):
        vals = np.array([[3.0, 4.0, 5.0, 4.0, 3.0, 2.0, 2.0, 3.0, 4.0, 5.0, 4.0, 3.0],
                         [np.nan, 7.0, np.nan, np.nan, np.nan, np.nan, np.nan, np.nan,
                          np.nan, np.nan, np.nan, np.nan]])
        ann = wind.annual_from_monthly(vals)
        self.assertEqual(ann["months_used"].tolist(), [12.0, 1.0])
        self.assertAlmostEqual(ann["wind_speed_mean"][0], vals[0].mean())
        self.assertAlmostEqual(ann["wind_speed_mean"][1], 7.0)

    def test_all_invalid_months_stay_null_and_partial_year_is_counted(self):
        vals = np.full((2, 12), np.nan)
        vals[1, 4] = 2.5
        ann = wind.annual_from_monthly(vals)
        self.assertEqual(ann["months_used"].tolist()[0], 0)
        self.assertTrue(np.isnan(ann["wind_speed_mean"][0]))
        self.assertEqual(ann["months_used"].tolist()[1], 1)  # partial-year support stays visible
        self.assertAlmostEqual(ann["wind_speed_mean"][1], 2.5)


class FillHandling(unittest.TestCase):
    def build_vals(self):
        return {"wind_speed": np.array([np.nan, 2.0, np.nan, np.nan]),
                "wind_speed_max": np.array([np.nan, 4.0, np.nan, 2.0]),
                "u10m_mean": np.array([np.nan, 1.0, np.nan, np.nan]),
                "v10m_mean": np.array([np.nan, 1.0, 2.0, np.nan])}

    def test_reason_keys_are_exactly_the_null_columns(self):
        reasons = wind.row_reasons_monthly(self.build_vals())
        self.assertEqual(json.loads(reasons[0]),
                         {"wind_speed": "merra2-cell-fill", "wind_speed_max": "merra2-cell-fill",
                          "u10m_mean": "merra2-cell-fill", "v10m_mean": "merra2-cell-fill"})
        self.assertEqual(json.loads(reasons[1]), {})  # no nulls -> no reason keys
        self.assertEqual(json.loads(reasons[2]),
                         {"wind_speed": "merra2-cell-fill", "wind_speed_max": "merra2-cell-fill",
                          "u10m_mean": "merra2-cell-fill"})  # v10m is valid here
        self.assertEqual(json.loads(reasons[3]),
                         {"wind_speed": "merra2-cell-fill", "u10m_mean": "merra2-cell-fill",
                          "v10m_mean": "merra2-cell-fill"})  # wind_speed_max is valid here

    def test_annual_reasons_mirror_the_null_aggregate(self):
        used = np.array([0.0, 12.0, 1.0])
        reasons = wind.row_reasons_annual(used)
        self.assertEqual(json.loads(reasons[0]), {"wind_speed_mean": "merra2-no-valid-month"})
        self.assertEqual(json.loads(reasons[1]), {})
        self.assertEqual(json.loads(reasons[2]), {})


class NativeGuard(unittest.TestCase):
    def test_fill_guard_bounds_valid_values(self):
        self.assertTrue(np.nanmax(np.array([0.0, 42.0])) < wind.FILL_GUARD)
        self.assertFalse(np.array([1e15]) < wind.FILL_GUARD)

    def test_plausible_ranges_bracket_expected_wind_values(self):
        self.assertEqual(wind.SPEED_PLAUSIBLE[0], 0.0)
        self.assertGreater(wind.SPEED_PLAUSIBLE[1], 40.0)   # monthly means well under hurricane force
        self.assertLess(wind.GUST_PLAUSIBLE[1], 120.0)      # monthly mean of hourly maxima
        self.assertEqual(wind.COMPONENT_PLAUSIBLE, (-60.0, 60.0))


class SpeedFieldSemantics(unittest.TestCase):
    def test_mean_of_speeds_dominates_magnitude_of_mean_vector(self):
        # Jensen: E[sqrt(u^2+v^2)] >= sqrt(E[u]^2 + E[v]^2); a table mixing the
        # two up would break this and lose the sense of the speed field.
        rng_u = np.array([1.0, 2.0, 3.0, -1.0, 0.5])   # hourly-ish samples
        rng_v = np.array([2.0, -2.0, 1.0, 0.0, 1.5])
        mean_of_speeds = np.hypot(rng_u, rng_v).mean()
        mag_of_mean = np.hypot(rng_u.mean(), rng_v.mean())
        self.assertGreaterEqual(mean_of_speeds, mag_of_mean)

    def test_column_sources_are_declared_consistently(self):
        for col, (dset, var) in {"wind_speed": ("merra2-m2tmnxflx", "SPEED"),
                                "wind_speed_max": ("merra2-m2tmnxflx", "SPEEDMAX"),
                                "u10m_mean": ("merra2-m2tmnxslv", "U10M"),
                                "v10m_mean": ("merra2-m2tmnxslv", "V10M")}.items():
            self.assertIn(dset, ("merra2-m2tmnxflx", "merra2-m2tmnxslv"))
            self.assertIn(var, wind.SOURCES[dset]["vars"])
        self.assertIn("SPEED", wind.SOURCES["merra2-m2tmnxflx"]["vars"])     # the mean speed is a speed field
        self.assertNotIn("SPEED", wind.SOURCES["merra2-m2tmnxslv"]["vars"])  # SLV monthly has no speed field


if __name__ == "__main__":
    unittest.main()
