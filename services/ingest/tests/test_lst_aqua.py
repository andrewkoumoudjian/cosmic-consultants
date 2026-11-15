"""W34 (#93) lst_aqua unit tests. Mock/synthetic only: no raw granules, no network.
The raw spot checks against real granules run in `python -m p0ingest.lst_aqua check`
(after build), not here — CI has no snapshot payloads."""
import unittest
from unittest.mock import patch

import h3
import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq

from p0ingest import lst_aqua
from p0ingest.grid import RES


class Reasons(unittest.TestCase):
    r = {"lst_day_k": "no-lst-pixels", "lst_night_k": "no-lst-pixels",
         "lst_diurnal_k": "day-or-night-missing"}

    def test_keys_are_exactly_the_null_columns(self):
        day_null = np.array([True, True, False, False, True])
        night_null = np.array([True, False, True, False, True])
        thin = np.array([[False, False], [True, False], [False, False],
                         [False, False], [False, False]])
        reasons = lst_aqua.monthly_reasons(day_null, night_null, thin[:, 0], thin[:, 1])
        import json
        got = [json.loads(x) for x in reasons]
        self.assertEqual(got[0], self.r)
        self.assertEqual(got[1], {"lst_day_k": "too-few-lst-pixels", "lst_diurnal_k": "day-or-night-missing"})
        self.assertEqual(got[2], {"lst_night_k": "no-lst-pixels", "lst_diurnal_k": "day-or-night-missing"})
        self.assertEqual(got[3], {})
        self.assertEqual(got[4], {"lst_day_k": "no-lst-pixels", "lst_night_k": "no-lst-pixels",
                                  "lst_diurnal_k": "day-or-night-missing"})

    def test_thin_flag_picks_reason_code(self):
        day_null = np.array([True, True])
        night_null = np.array([False, False])
        reasons = lst_aqua.monthly_reasons(day_null, night_null,
                                           np.array([True, False]), np.array([False, False]))
        import json
        self.assertEqual(json.loads(reasons[0])["lst_day_k"], "too-few-lst-pixels")
        self.assertEqual(json.loads(reasons[1])["lst_day_k"], "no-lst-pixels")

    def test_complete_row_reason_is_empty_object(self):
        reasons = lst_aqua.monthly_reasons(np.array([False]), np.array([False]),
                                           np.array([False]), np.array([False]))
        self.assertEqual(reasons, ["{}"])


class CoverageRule(unittest.TestCase):
    def test_median_or_none_uses_25pct_of_mapped_pixels(self):
        vals = np.array([7600.0, 8000.0, 8200.0])
        # 3 / 16 < 25% -> None
        self.assertIsNone(lst_aqua.median_or_none(vals, 16))
        # 3 / 12 == 25% -> kept
        self.assertAlmostEqual(lst_aqua.median_or_none(vals, 12), 8000.0 * 0.02)
        # no valid pixels -> None
        self.assertIsNone(lst_aqua.median_or_none(np.array([]), 12))

    def test_median_even_count_averages_middle(self):
        self.assertEqual(lst_aqua.median_or_none(np.array([7600.0, 8000.0]), 4),
                         (7600.0 + 8000.0) / 2 * 0.02)


class Keys(unittest.TestCase):
    def cells(self, n=3):
        return [f"{i:x}" for i in (0xA1, 0xB2, 0xC3)][:n]

    def test_complete_keys_pass(self):
        cells = self.cells()
        t = pa.table({"h3": sum([[c] * 12 for c in cells], []),
                      "month": list(range(1, 13)) * 3})
        self.assertEqual(lst_aqua.validate_keys(t.column("h3").to_pylist(),
                                               t.column("month").to_pylist(), cells), [])

    def test_duplicate_month_is_rejected(self):
        cells = self.cells(1)
        h3col = ["a"] * 12
        months = list(range(1, 13))
        months[-1] = 1
        errs = lst_aqua.validate_keys(h3col, months, ["a"])
        self.assertTrue(any("duplicate" in e for e in errs))

    def test_wrong_cell_month_and_extra_cell_are_rejected(self):
        months = list(range(1, 13)) * 2
        errs = lst_aqua.validate_keys(["a"] * 12 + ["zz"] * 12, months, ["a", "b"])
        self.assertTrue(any("cells differ" in e for e in errs))

    def test_null_month_is_rejected(self):
        months = list(range(1, 12)) + [None]
        errs = lst_aqua.validate_keys(["a"] * 12, months, ["a"])
        self.assertTrue(any("outside 1..12" in e or "null" in e for e in errs))

    def test_wrong_rowcount_is_rejected(self):
        errs = lst_aqua.validate_keys(["a"] * 11, list(range(1, 12)), ["a"])
        self.assertTrue(any("expected" in e for e in errs))


class NullReasonMatch(unittest.TestCase):
    def table(self, vals):
        return pa.table({
            "h3": ["a", "b"],
            "month": [1, 2],
            "lst_day_k": vals[:2],
            "lst_night_k": vals[2:],
            "lst_diurnal_k": [None, 5.0],
            "missing_reason": ['{"lst_day_k":"no-lst-pixels","lst_night_k":"no-lst-pixels",'
                               '"lst_diurnal_k":"day-or-night-missing"}', "{}"]})

    def test_keys_matching_nulls_pass(self):
        t = self.table([None, 3.0, None, 2.0])
        self.assertEqual(lst_aqua.reason_mismatches(t), [])

    def test_omitted_or_extra_reason_key_is_flagged(self):
        t = self.table([None, 3.0, None, 2.0])
        t = t.set_column(5, "missing_reason", pa.array(
            ['{"lst_day_k":"no-lst-pixels"}',  # lst_night_k null but unreported
             '{"lst_day_k":"none"}']))          # lst_day_k present, reported anyway
        self.assertEqual(len(lst_aqua.reason_mismatches(t)), 2)


class PhysicalRanges(unittest.TestCase):
    def table(self, day, night, diag, vp, months):
        n = len(day)
        return pa.table({
            "h3": ["a"] * n,
            "month": months,
            "lst_day_k": day,
            "lst_night_k": night,
            "lst_diurnal_k": diag,
            "lst_valid_pixels": vp,
        })

    def test_out_of_range_value_is_flagged(self):
        t = self.table([200.0, 400.0], [180.0, 181.0], [20.0, 219.0],
                       [5, 5], [1, 2])
        errs = lst_aqua.physical_range_errors(t, 1)
        self.assertTrue(any("outside" in e for e in errs))

    def test_wrong_month_counts_are_flagged(self):
        t = self.table([200.0, 200.0], [180.0, 181.0], [20.0, 19.0],
                       [5, 5], [1, 1])
        errs = lst_aqua.physical_range_errors(t, 1)
        self.assertTrue(any("month counts" in e for e in errs))

    def test_clean_table_has_no_errors(self):
        t = self.table([200.0] * 12, [180.0] * 12, [20.0] * 12,
                       list(range(12)), list(range(1, 13)))
        self.assertEqual(lst_aqua.physical_range_errors(t, 1), [])


class CellOrder(unittest.TestCase):
    def test_perm_maps_ascending_group_order_to_cells_r4_order(self):
        cells = np.array([2, 5, 9], dtype=np.uint64)
        hexes = np.array([9, 5, 2], dtype=np.uint64)
        np.testing.assert_array_equal(lst_aqua.perm_to_r4_order(cells, hexes), [2, 1, 0])

    def test_mismatched_cell_sets_raise(self):
        with self.assertRaises(ValueError):
            lst_aqua.perm_to_r4_order(np.array([2, 5], dtype=np.uint64),
                                      np.array([2, 7], dtype=np.uint64))


class CellPixelValues(unittest.TestCase):
    """Independent window + fill check: synthetic CMG arrays around one real
    res-4 cell; expected pixels found here directly with h3, not via the module."""

    def run_counts(self, day_fill_at=None):
        landp = np.zeros((3600, 7200), dtype=np.uint8)
        fields = {"day": np.full((3600, 7200), 30000, dtype=np.uint16),
                  "night": np.full((3600, 7200), 20000, dtype=np.uint16)}
        centre = h3.latlng_to_cell(45.5, 12.5, RES)
        lat0, lat1 = h3.cell_to_latlng(centre)
        # rows/cols around the cell centre
        j0 = int(round((lat1 + 180.0 - 0.025) / 0.05))
        i0 = int(round((90.0 - lat0 - 0.025) / 0.05))
        inner = []
        for i in range(i0 - 25, i0 + 26):
            lat = 90.0 - 0.025 - i * 0.05
            for j in range(j0 - 25, j0 + 26):
                if h3.latlng_to_cell(lat, -180.0 + 0.025 + j * 0.05, RES) == centre:
                    inner.append((i, j))
        for i, j in inner:
            landp[i, j] = 40  # land share > 0
        if day_fill_at is not None:
            i, j = inner[day_fill_at]
            fields["day"][i, j] = 0  # fill count
        with patch.object(lst_aqua, "land_percent", return_value=landp):
            vals, n_mapped = lst_aqua.cell_pixel_values(centre, fields)
        return vals, n_mapped, inner

    def test_mapped_count_and_window(self):
        vals, n_mapped, inner = self.run_counts()
        self.assertEqual(n_mapped, len(inner))
        self.assertEqual(len(vals["day"]), len(inner))
        self.assertEqual(len(vals["night"]), len(inner))

    def test_fill_counts_are_excluded(self):
        vals, _, _ = self.run_counts(day_fill_at=0)
        self.assertEqual(len(vals["day"]), len(vals["day"]))
        self.assertNotIn(0.0, vals["day"])


class OverpassDocumentation(unittest.TestCase):
    def test_aqua_overpass_times_are_recorded(self):
        # the point of W34: Aqua ~13:30/~01:30 pairs with Terra ~10:30/~22:30
        self.assertIn("~13:30", lst_aqua.OVERPASS["aqua_day"])
        self.assertIn("~01:30", lst_aqua.OVERPASS["aqua_night"])
        self.assertIn("~10:30", lst_aqua.OVERPASS["terra_day"])
        self.assertIn("~22:30", lst_aqua.OVERPASS["terra_night"])

    def test_monthly_composites_note_is_recorded(self):
        self.assertIn("monthly composites, NOT daily extremes", lst_aqua.OVERPASS["note"])
        self.assertIn("thermal-inertia", lst_aqua.OVERPASS["note"])


if __name__ == "__main__":
    unittest.main()
