"""Regression tests for p0ingest.burned (issue #65). Pure transformations only:
no network, no Earthdata token. Run:
  uv run python -m unittest tests.test_burned            (normal)
  uv run python -O -m unittest tests.test_burned         (optimized)
"""
import datetime as dt
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import numpy as np
import pyarrow as pa
from pyhdf.SD import SDC, SD

from p0ingest import burned


def tile_name(year, month, h, v, version="2021320073831"):
    doy = (dt.date(year, month, 1) - dt.date(year, 1, 1)).days + 1
    return f"MCD64A1.A{year}{doy:03d}.h{h:02d}v{v:02d}.061.{version}.hdf"


class ParseName(unittest.TestCase):
    def test_month_from_start_doy(self):
        for y in (2015, 2016, 2020, 2024):
            for m in (1, 2, 7, 12):
                name = tile_name(y, m, 31, 10)
                url = f"https://data.lpdaac.earthdatacloud.nasa.gov/x/{name}"
                self.assertEqual(burned.parse_name(url)[0], y)
                self.assertEqual(burned.parse_name(url)[1], m)

    def test_mid_month_granule_is_rejected(self):
        # a reissued granule carrying a mid-month start date must fail loudly
        doy = (dt.date(2019, 9, 10) - dt.date(2019, 1, 1)).days + 1
        url = f"https://x/MCD64A1.A2019{doy:03d}.h31v10.061.2021320073831.hdf"
        with self.assertRaises(ValueError):
            burned.parse_name(url)


class Aggregate(unittest.TestCase):
    def years_shape(self, n=4, cells=3):
        return np.zeros((10, 12, cells), dtype=np.int32)

    def test_mean_of_yearly_shares_and_years_mapped(self):
        burned_a, mapped_a = self.years_shape(), self.years_shape()
        burned_a[0, 6, 0], mapped_a[0, 6, 0] = 2, 8       # 2015 Jul: 25%
        mapped_a[1, 6, 0] = 10                           # 2016 Jul: 0% (unburned, mapped)
        agg = burned.aggregate(burned_a, mapped_a, 3)
        self.assertAlmostEqual(agg["pct"][0, 6], 100 * (0.25 + 0.0) / 2)
        self.assertEqual(agg["years"][0, 6], 2)
        self.assertTrue(np.isnan(agg["pct"][0, 0]))       # no mapped support -> NaN, not zero
        self.assertEqual(agg["years"][0, 0], 0)

    def test_unweighted_mean_not_pooled(self):
        # the issue requires the mean of yearly shares, so a big mapped year cannot
        # drown a small one: mean(1/3, 9/9) = 66.7% != pooled 10/12 = 83.3%
        b, m = self.years_shape(), self.years_shape()
        b[0, 0, 0], m[0, 0, 0] = 1, 3
        b[1, 0, 0], m[1, 0, 0] = 9, 9
        agg = burned.aggregate(b, m, 3)
        self.assertAlmostEqual(agg["pct"][0, 0], 100 * (1 / 3 + 1.0) / 2)
        self.assertAlmostEqual(agg["pct"][0, 0], 66 + 2 / 3)

    def test_water_and_unmapped_never_count(self):
        b, m, pix = self.years_shape(), self.years_shape(), self.years_shape()
        b[0, 0, 0], m[0, 0, 0], pix[0, 0, 0] = 4, 4, 10   # 4 unmapped + 2 water px present
        agg = burned.aggregate(b, m, 3)
        self.assertAlmostEqual(agg["pct"][0, 0], 100.0)     # denominator excludes them
        rows = burned.build_rows(["a", "b", "c"], b, m, pix, np.zeros((3, 12), bool))
        self.assertEqual(rows["missing_reason"][0], "{}")  # value present -> no reason


class BuildRows(unittest.TestCase):
    def b(self, pix):
        return (np.zeros((10, 12, 2), dtype=np.int32),
                np.zeros((10, 12, 2), dtype=np.int32), pix)

    def test_reasons_match_nulls_and_coverage(self):
        z = np.zeros((10, 12, 2), dtype=np.int32)
        pix = np.zeros((10, 12, 2), dtype=np.int32)
        pix[0, 0, 1] = 5                                   # cell 1: pixels exist, none mapped
        # cell 0: no pixel at all -> outside tiles
        rows = burned.build_rows(["aa", "bb"], *self.b(pix), np.zeros((2, 12), bool))
        self.assertEqual(json.loads(rows["missing_reason"][0]), {"burnedArea": "outside-mcd64a1-tiles"})
        self.assertEqual(json.loads(rows["missing_reason"][13]), {"burnedArea": "no-mapped-land-in-period"})
        # h3 and month interleaving is cell-major
        self.assertEqual(rows["h3"][:12], ["aa"] * 12)
        self.assertEqual(rows["month"][:12], list(range(1, 13)))

    def test_partial_fetch_failure_flag_keeps_value(self):
        b, m, pix = self.b(np.zeros((10, 12, 2), dtype=np.int32))
        b[0, 0, 0], m[0, 0, 0], pix[0, 0, 0] = 1, 2, 2
        partial = np.zeros((2, 12), bool)
        partial[0, 0] = True
        rows = burned.build_rows(["aa", "bb"], b, m, pix, partial)
        self.assertAlmostEqual(rows["burned_pct"][0], 50.0)  # value stays, honestly labelled
        self.assertEqual(json.loads(rows["missing_reason"][0]),
                         {"burnedAreaSupport": "years-lost-to-granule-fetch-failures"})


class ValidateKeys(unittest.TestCase):
    def table(self, hexes=2):
        h3c = [h for h in "ab"[:hexes] for _ in range(12)]
        months = [m for _ in range(hexes) for m in range(1, 13)]
        return pa.table({"h3": h3c, "month": months})

    def test_exact_domain_passes(self):
        self.assertEqual(burned.validate_keys(self.table(), ["a", "b"]), [])

    def test_duplicate_row_is_rejected(self):
        rows = self.table().to_pylist()
        rows[1] = rows[0]
        self.assertTrue(burned.validate_keys(pa.Table.from_pylist(rows), ["a", "b"]))

    def test_invalid_month_is_rejected(self):
        rows = self.table().to_pylist()
        rows[0]["month"] = 13
        self.assertTrue(burned.validate_keys(pa.Table.from_pylist(rows), ["a", "b"]))

    def test_unknown_cell_is_rejected(self):
        rows = self.table().to_pylist()
        rows[0]["h3"] = "c"
        self.assertTrue(burned.validate_keys(pa.Table.from_pylist(rows), ["a", "b"]))

    def test_null_month_is_rejected(self):
        rows = self.table().to_pylist()
        rows[0]["month"] = None
        self.assertTrue(burned.validate_keys(pa.Table.from_pylist(rows), ["a", "b"]))


class AffectedCells(unittest.TestCase):
    def test_failed_granule_marks_exact_cells_and_month(self):
        with tempfile.TemporaryDirectory() as td:
            idx = np.full((4, 4), -1, dtype=np.int32)
            idx[0, 0], idx[1, 1], idx[2, 2] = 0, 1, 2      # cells 0,1,2 have pixels here
            path = Path(td) / "h31v10.npz"
            np.savez(path, idx=idx)
            with mock.patch.object(burned, "_tilemap_path", return_value=path):
                url = "https://x/" + tile_name(2019, 9, 31, 10)
                affected = burned.affected_cell_months({url: "boom"}, 5)
            self.assertTrue(affected[0, 8] and affected[1, 8] and affected[2, 8])
            self.assertFalse(affected[3, 8])
            self.assertFalse(affected[0, 0])                # other months untouched


class Decode(unittest.TestCase):
    def write_hdf(self, bd):
        self.tmp = tempfile.TemporaryDirectory()
        path = str(Path(self.tmp.name) / "g.hdf")
        sd = SD(path, SDC.WRITE | SDC.CREATE)
        sds = sd.create("Burn Date", 22, (2400, 2400))
        sds[:] = bd
        sds.endaccess()
        sd.end()
        return path

    def decode_one(self, bd, h, v, n_cells=10):
        # tilemap: pixels (0,0)->5, (0,1)->6, (0,2)->7, (0,3)->8; everything else -1
        idx = np.full((2400, 2400), -1, dtype=np.int32)
        for j, cell in ((0, 5), (1, 6), (2, 7), (3, 8)):
            idx[0, j] = cell
        tilemap = mock.patch.object(burned, "_tilemap", return_value=idx)
        path = self.write_hdf(bd)
        self.addCleanup(self.tmp.cleanup)
        with tilemap:
            return burned.decode(path, h, v, n_cells)

    def test_counts_by_burn_date_class(self):
        bd = np.full((2400, 2400), -2, dtype=np.int16)     # water default
        bd[0, 0] = 244                                      # burned (DOY inside the month)
        bd[0, 1] = -1                                       # unmapped land
        bd[0, 2] = 0                                        # mapped, unburned land
        res = self.decode_one(bd, 31, 10)
        self.assertEqual(list(res["cells"]), [5, 6, 7, 8])
        self.assertEqual(list(res["burned"]), [1, 0, 0, 0])
        self.assertEqual(list(res["mapped"]), [1, 0, 1, 0])  # burned and unburned land, never -1/-2
        self.assertEqual(list(res["unmapped"]), [0, 1, 0, 0])
        self.assertEqual(list(res["water"]), [0, 0, 0, 1])   # the unmapped water cell (0,3)

    def test_out_of_range_and_shape_are_rejected(self):
        bd = np.full((2400, 2400), -2, dtype=np.int16)
        bd[0, 0] = 400                                      # outside valid_range [0, 366]
        with self.assertRaises(RuntimeError):
            self.decode_one(bd, 31, 10)
        with self.assertRaises(RuntimeError):
            self.decode_one(np.zeros((1200, 1200), dtype=np.int16), 31, 10)


class ResumeAlignment(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.paths = [burned.CHECKPOINT, burned.PARTIAL]
        burned.CHECKPOINT = Path(self.dir.name) / "ck.npz"
        burned.PARTIAL = Path(self.dir.name) / "partial.jsonl"

    def tearDown(self):
        burned.CHECKPOINT, burned.PARTIAL = self.paths
        self.dir.cleanup()

    def ledger(self, n, nbytes=100):
        return "".join(json.dumps({"url": f"https://x/{i}.hdf", "bytes": nbytes}) + "\n"
                       for i in range(n))

    def test_resume_aligns_ledger_with_checkpoint(self):
        # 3 lines committed; 2 more written after the checkpoint -> dropped, refetched
        burned.PARTIAL.write_text(self.ledger(5))
        arrays = {k: np.full((10, 12, 4), 7, dtype=np.int32) for k in ("burned", "mapped", "unmapped", "water")}
        np.savez(burned.CHECKPOINT, ledger_lines=3, **arrays)
        r = burned.Run([], 1, 4)
        r.resume()
        self.assertEqual(r.resumed, 3)
        self.assertEqual(len(r.done), 3)
        self.assertEqual(burned.PARTIAL.read_text(), self.ledger(3))   # uncommitted lines gone
        self.assertEqual(r.sum_bytes, 300)

    def test_refuses_to_skip_when_ledger_shorter_than_checkpoint(self):
        burned.PARTIAL.write_text(self.ledger(1))
        arrays = {k: np.zeros((10, 12, 4), dtype=np.int32) for k in ("burned", "mapped", "unmapped", "water")}
        np.savez(burned.CHECKPOINT, ledger_lines=3, **arrays)
        r = burned.Run([], 1, 4)
        with self.assertRaises(RuntimeError):
            r.resume()

    def test_no_checkpoint_starts_clean(self):
        burned.PARTIAL.write_text(self.ledger(2))
        r = burned.Run([], 1, 4)
        r.resume()
        self.assertEqual(r.resumed, 0)
        self.assertEqual(burned.PARTIAL.read_text(), "")


class GranuleListDedup(unittest.TestCase):
    def test_repeated_tile_month_would_be_refused(self):
        # simulate the fatal path: the same (year, month, h, v) appearing twice
        url = "https://x/" + tile_name(2019, 9, 31, 10)
        keys = [burned.parse_name(url), burned.parse_name(url)]
        self.assertEqual(len(keys) - len(set(keys)), 1)


if __name__ == "__main__":
    unittest.main()
