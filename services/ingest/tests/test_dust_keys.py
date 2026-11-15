import unittest

import numpy as np
import pyarrow as pa

from p0ingest import dust

CELLS = ["a", "b"]


def monthly_table():
    return pa.table({"h3": ["a"] * 12 + ["b"] * 12,
                     "month": list(range(1, 13)) * 2})


class DustKeys(unittest.TestCase):
    def test_complete_domain(self):
        self.assertEqual(dust.validate_keys(monthly_table(), CELLS), [])

    def test_wrong_row_count_is_rejected(self):
        rows = monthly_table().to_pylist()[:-1]
        self.assertTrue(dust.validate_keys(pa.Table.from_pylist(rows), CELLS))

    def test_duplicate_month_is_rejected(self):
        rows = monthly_table().to_pylist()
        rows[3] = {"h3": "a", "month": 1}
        self.assertTrue(dust.validate_keys(pa.Table.from_pylist(rows), CELLS))

    def test_invalid_month_is_rejected(self):
        rows = monthly_table().to_pylist()
        rows[0] = {"h3": "a", "month": 13}
        self.assertTrue(dust.validate_keys(pa.Table.from_pylist(rows), CELLS))
        rows[0] = {"h3": "a", "month": 0}
        self.assertTrue(dust.validate_keys(pa.Table.from_pylist(rows), CELLS))

    def test_unknown_cell_is_rejected(self):
        rows = monthly_table().to_pylist()
        rows[0] = {"h3": "c", "month": 1}
        self.assertTrue(dust.validate_keys(pa.Table.from_pylist(rows), CELLS))

    def test_null_key_is_rejected(self):
        rows = monthly_table().to_pylist()
        rows[0] = {"h3": None, "month": 1}
        self.assertTrue(dust.validate_keys(pa.Table.from_pylist(rows), CELLS))
        rows[0] = {"h3": "a", "month": None}
        self.assertTrue(dust.validate_keys(pa.Table.from_pylist(rows), CELLS))

    def test_missing_pair_is_rejected(self):
        rows = [r for r in monthly_table().to_pylist() if not (r["h3"] == "b" and r["month"] == 12)]
        self.assertTrue(dust.validate_keys(pa.Table.from_pylist(rows), CELLS))


class GranuleMonth(unittest.TestCase):
    def test_parses_month(self):
        self.assertEqual(dust.month_of("data/snapshots/merra2-m2tmnxaer/"
                                       "MERRA2_400.tavgM_2d_aer_Nx.202301.nc4"), 1)
        self.assertEqual(dust.month_of("MERRA2_400.tavgM_2d_aer_Nx.202312.nc4"), 12)

    def test_rejects_wrong_year(self):
        with self.assertRaises(ValueError):
            dust.month_of("MERRA2_400.tavgM_2d_aer_Nx.202201.nc4")

    def test_rejects_invalid_month(self):
        with self.assertRaises(ValueError):
            dust.month_of("MERRA2_400.tavgM_2d_aer_Nx.202313.nc4")
        with self.assertRaises(ValueError):
            dust.month_of("MERRA2_400.tavgM_2d_aer_Nx.202300.nc4")

    def test_rejects_other_name_shape(self):
        with self.assertRaises(ValueError):
            dust.month_of("MERRA2_400.tavg1_2d_aer_Nx.202301.nc4")

    def test_granules_rejects_duplicate_months(self):
        entry = {"datasetId": "merra2-m2tmnxaer", "localPath": "x/MERRA2_400.tavgM_2d_aer_Nx.202301.nc4"}
        orig = dust.load_manifest

        def fake():
            return {"entries": [entry, dict(entry)]}
        dust.load_manifest = fake
        try:
            with self.assertRaises(ValueError):
                dust.granules()
        finally:
            dust.load_manifest = orig


class NearestCenter(unittest.TestCase):
    # synthetic 5-lat x 8-lon grid: lat -60..60 step 30, lon -45..26.25? use lon -45..45 step 11.25*? simpler:
    glat = np.array([-60.0, -30.0, 0.0, 30.0, 60.0])
    glon = np.array([-180.0, -135.0, -90.0, -45.0, 0.0, 45.0, 90.0, 135.0])  # step 45, wraps 360

    def test_interior_exact_and_middle(self):
        ilat, ilon = dust.nearest_ij([0.0], [-90.0], self.glat, self.glon)
        self.assertEqual((int(ilat[0]), int(ilon[0])), (2, 2))

    def test_longitude_wraparound_both_sides_of_dateline(self):
        ilat, ilon = dust.nearest_ij([0.0, 0.0], [179.9, -179.9], self.glat, self.glon)
        self.assertEqual(int(ilon[0]), 0)   # 179.9 E -> grid column 0 (lon -180)
        self.assertEqual(int(ilon[1]), 0)   # 179.9 W -> same column, wraps the other way
        ilat2, ilon2 = dust.nearest_ij([0.0, 0.0], [150.0, -150.0], self.glat, self.glon)
        self.assertEqual(int(ilon2[0]), 7)  # 150 E -> 135
        self.assertEqual(int(ilon2[1]), 1)  # 150 W -> -135

    def test_poles_clip_to_end_rows(self):
        ilat, _ = dust.nearest_ij([89.0, -89.0, 59.0], [0.0, 0.0, 0.0], self.glat, self.glon)
        self.assertEqual([int(x) for x in ilat], [4, 0, 4])

    def test_out_of_range_latitude_is_clipped_not_wrapped(self):
        ilat, _ = dust.nearest_ij([90.0, -90.0], [0.0, 0.0], self.glat, self.glon)
        self.assertEqual([int(x) for x in ilat], [4, 0])

    def test_halfway_ties_are_deterministic(self):
        i0, _ = dust.nearest_ij(np.full(500, 15.0), np.zeros(500), self.glat, self.glon)
        self.assertEqual(int(i0.min()), int(i0.max()))  # rint half-to-even: stable across the array

    def test_nonuniform_grid_raises(self):
        with self.assertRaises(ValueError):
            dust.nearest_ij([0.0], [0.0], np.array([-2.0, 0.0, 1.0]), self.glon)


class AnnualAggregation(unittest.TestCase):
    def test_mean_max_and_earliest_tie_month(self):
        vals = np.array([[0.10, 0.30, 0.30, 0.20, 0.10, 0.10, 0.20, 0.25, 0.25, 0.05, 0.05, 0.10],
                         [np.nan, 0.40, np.nan, np.nan, np.nan, np.nan, np.nan, np.nan,
                          np.nan, np.nan, np.nan, np.nan]])
        ann = dust.annual_from_monthly(vals)
        self.assertEqual(ann["months_used"].tolist(), [12.0, 1.0])
        self.assertAlmostEqual(ann["dust_aod_mean"][0], vals[0].mean())
        self.assertAlmostEqual(ann["dust_aod_max"][0], 0.30)
        self.assertEqual(ann["dust_aod_max_month"][0], 2)  # tie 0.30 at months 2 and 3 -> earliest
        self.assertAlmostEqual(ann["dust_aod_max"][1], 0.40)
        self.assertEqual(ann["dust_aod_max_month"][1], 2)

    def test_all_invalid_months_stay_null_and_partial_year_is_counted(self):
        vals = np.full((2, 12), np.nan)
        vals[1, 4] = 0.22
        ann = dust.annual_from_monthly(vals)
        self.assertEqual(ann["months_used"].tolist()[0], 0)
        self.assertTrue(np.isnan(ann["dust_aod_mean"][0]) and np.isnan(ann["dust_aod_max"][0])
                        and np.isnan(ann["dust_aod_max_month"][0]))
        self.assertEqual(ann["months_used"].tolist()[1], 1)  # partial-year support stays visible
        self.assertAlmostEqual(ann["dust_aod_mean"][1], 0.22)


class FillHandling(unittest.TestCase):
    def test_fill_marks_do_not_reach_output_as_nearest_values(self):
        n = 4
        vals = np.full((n, 12), np.nan)
        vals[0, 0] = 0.5
        reasons = dust.row_reasons_monthly(vals)
        self.assertIn('{"dustProcess": "merra2-cell-fill"}', reasons)
        self.assertIn("{}", reasons)
        ann = dust.annual_from_monthly(vals)
        self.assertEqual(ann["months_used"][0], 1)
        reasons_a = dust.row_reasons_annual(ann["months_used"])
        self.assertIn('{"dustProcess": "merra2-no-valid-month"}', reasons_a)
        self.assertEqual(reasons_a.count("{}"), 1)  # only the cell with one valid month carries no reason


class NativeGuard(unittest.TestCase):
    def test_fill_guard_bounds_valid_values(self):
        self.assertTrue(np.nanmax(np.array([0.0, 0.9])) < dust.FILL_GUARD)
        self.assertFalse(np.array([1e15]) < dust.FILL_GUARD)


if __name__ == "__main__":
    unittest.main()
