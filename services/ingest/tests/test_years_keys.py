import unittest

import pyarrow as pa

from p0ingest import years


class TemperatureKeys(unittest.TestCase):
    def table(self):
        return pa.table({"h3": ["a"] * 12 + ["b"] * 12,
                         "year": [2023] * 24,
                         "month": list(range(1, 13)) * 2})

    def test_complete_domain(self):
        self.assertEqual(years.validate_keys(self.table(), ["a", "b"], [2023]), [])

    def test_duplicate_replacing_missing_month_is_rejected(self):
        rows = self.table().to_pylist()
        rows[-1] = rows[-2].copy()
        self.assertTrue(years.validate_keys(pa.Table.from_pylist(rows), ["a", "b"], [2023]))

    def test_wrong_year_is_rejected(self):
        rows = self.table().to_pylist()
        rows[0]["year"] = 2022
        self.assertTrue(years.validate_keys(pa.Table.from_pylist(rows), ["a", "b"], [2023]))

    def test_wrong_month_is_rejected(self):
        rows = self.table().to_pylist()
        rows[0]["month"] = 13
        self.assertTrue(years.validate_keys(pa.Table.from_pylist(rows), ["a", "b"], [2023]))

    def test_unknown_cell_is_rejected(self):
        rows = self.table().to_pylist()
        rows[0]["h3"] = "c"
        self.assertTrue(years.validate_keys(pa.Table.from_pylist(rows), ["a", "b"], [2023]))

    def test_null_key_is_rejected(self):
        rows = self.table().to_pylist()
        rows[0]["month"] = None
        self.assertTrue(years.validate_keys(pa.Table.from_pylist(rows), ["a", "b"], [2023]))


if __name__ == "__main__":
    unittest.main()
