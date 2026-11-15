import json
import tempfile
import unittest
from pathlib import Path

import numpy as np

from p0ingest.mars_ice import (EXPECTED_BINS, NA, RANGES, VALUE_COLUMNS, _expected_grid,
                              _near_set, _spot_picks, clean_grs, read_grs_label,
                              read_grs_table, product_meta, swim_sources)

LABEL = '''PDS_VERSION_ID                 = PDS3\r
RECORD_TYPE                    = FIXED_LENGTH\r
RECORD_BYTES                   = 71\r
DATA_SET_ID                    = "ODY-M-GRS-5-ELEMENTS-V1.0"\r
PRODUCT_ID                     = "H2O_SR_5X5"\r
START_TIME                     = 2002-06-04T00:00:00 \r
STOP_TIME                      = 2005-04-03T00:00:00 \r
OBJECT                         = TABLE\r
  NAME                         = "WATER CONCENTRATION DATA"\r
  ROWS                         = 4\r
  ROW_BYTES                    = 71\r
  COLUMNS                      = 5\r
  OBJECT                       = COLUMN\r
    COLUMN_NUMBER              = 1\r
    NAME                       = "LATITUDE"\r
    DATA_TYPE                  = ASCII_REAL\r
    FORMAT                     = "F5.1"\r
    UNIT                       = "DEGREE"\r
    BYTES                      = 5\r
    START_BYTE                 = 1\r
  END_OBJECT                   = COLUMN\r
  OBJECT                       = COLUMN\r
    COLUMN_NUMBER              = 2\r
    NAME                       = "LONGITUDE"\r
    DATA_TYPE                  = ASCII_REAL\r
    FORMAT                     = "F5.1"\r
    UNIT                       = "DEGREE"\r
    BYTES                      = 5\r
    START_BYTE                 = 16\r
  END_OBJECT                   = COLUMN\r
  OBJECT                       = COLUMN\r
    COLUMN_NUMBER              = 3\r
    NAME                       = "CONCENTRATION"\r
    DATA_TYPE                  = ASCII_REAL\r
    FORMAT                     = "F8.3"\r
    UNIT                       = "WEIGHT PERCENT"\r
    BYTES                      = 8\r
    START_BYTE                 = 29\r
    NOT_APPLICABLE_CONSTANT    = 9999.999\r
  END_OBJECT                   = COLUMN\r
  OBJECT                       = COLUMN\r
    COLUMN_NUMBER              = 4\r
    NAME                       = "SIGMA"\r
    DATA_TYPE                  = ASCII_REAL\r
    FORMAT                     = "F8.3"\r
    UNIT                       = "WEIGHT PERCENT"\r
    BYTES                      = 8\r
    START_BYTE                 = 46\r
    NOT_APPLICABLE_CONSTANT    = 9999.999\r
  END_OBJECT                   = COLUMN\r
  OBJECT                       = COLUMN\r
    COLUMN_NUMBER              = 5\r
    NAME                       = "SIGMA WITH CFS"\r
    DATA_TYPE                  = ASCII_REAL\r
    FORMAT                     = "F8.3"\r
    UNIT                       = "WEIGHT PERCENT"\r
    BYTES                      = 8\r
    START_BYTE                 = 63\r
    NOT_APPLICABLE_CONSTANT    = 9999.999\r
  END_OBJECT                   = COLUMN\r
END_OBJECT                     = TABLE\r
END\r
'''


def write_table(root: Path, rows: list[str]) -> Path:
    table = root / "x.tab"
    table.write_bytes(("\r\n".join(rows) + "\r\n").encode("ascii"))
    return table


class MarsIceGRS(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp()
        root = Path(self.root)
        (root / "x.lbl").write_text(LABEL)
        # h2o_sr_5x5 fixed layout: lat 1-5, lon 16-20, conc 29-36, sigma 46-53,
        # sigma-with-CFS 63-70 (70 payload chars, CR LF terminator, 72-byte stride).
        def row(lat, lon, conc, sig, scf):
            return (f"{lat:5.1f}" + " " * 10 + f"{lon:5.1f}" + " " * 8
                    + f"{conc:8.3f}" + " " * 9 + f"{sig:8.3f}" + " " * 9 + f"{scf:8.3f}")
        # row 1 fully NA, row 2 has a published negative concentration,
        # rows 3-4 clean.
        self.rows = [
            row(-87.5, 2.5, NA, NA, 0.263),
            row(-87.5, 7.5, -1.500, 0.230, NA),
            row(22.5, 12.5, 3.842, 0.340, 0.420),
            row(27.5, 357.5, 7.398, 0.667, 0.861),
        ]
        self.table_path = write_table(root, self.rows)
        self.spec = read_grs_label(root / "x.lbl")

    def tearDown(self):
        import shutil
        shutil.rmtree(self.root)

    def test_label_fields_and_bounds(self):
        self.assertEqual(self.spec["rows"], 4)
        self.assertEqual(self.spec["recordBytes"], 71)
        self.assertEqual([c["name"] for c in self.spec["columns"]],
                         ["LATITUDE", "LONGITUDE", "CONCENTRATION", "SIGMA", "SIGMA WITH CFS"])
        self.assertEqual(self.spec["columns"][2]["invalid"], 9999.999)
        self.assertEqual(self.spec["columns"][0]["unit"], "DEGREE")
        self.assertEqual(self.spec["columns"][-1]["start"], 62)  # zero-based
        # a row-count/byte-count contradiction must be caught against the table
        text = LABEL.replace("ROWS                         = 4", "ROWS                         = 9")
        (Path(self.root) / "y.lbl").write_text(text)
        with self.assertRaises(ValueError):
            read_grs_table(self.table_path, read_grs_label(Path(self.root) / "y.lbl"))
        # a truncated table must be caught too
        short = Path(self.root) / "z.tab"
        short.write_bytes("\r\n".join(self.rows[:3]).encode("ascii") + b"\r\n")
        with self.assertRaises(ValueError):
            read_grs_table(short, self.spec)

    def test_na_nulls_and_missing_reason_keys(self):
        table = clean_grs(read_grs_table(self.table_path, self.spec),
                          "grs-weh-5deg-smoothed.parquet")
        self.assertEqual(table["weh_wt_pct"].to_list(), [None, -1.5, 3.842, 7.398])
        self.assertEqual(table["weh_sigma_wt_pct"].to_list(), [None, 0.230, 0.340, 0.667])
        self.assertEqual(table["weh_sigma_cfs_wt_pct"].to_list(), [0.263, None, 0.420, 0.861])
        # the published negative concentration is retained, not nulled
        self.assertEqual(table["source_concentration"].to_list()[1], -1.5)
        self.assertEqual(set(json.loads(table["missing_reason"][0])),
                         {"weh_wt_pct", "weh_sigma_wt_pct"})
        row0 = json.loads(table["missing_reason"][0])
        self.assertEqual(row0, {"weh_wt_pct": "source-na-9999.999", "weh_sigma_wt_pct": "source-na-9999.999"})
        row1 = json.loads(table["missing_reason"][1])
        self.assertEqual(row1, {"weh_sigma_cfs_wt_pct": "source-na-9999.999"})
        self.assertIsNone(table["missing_reason"][2])
        # null keys are exactly the null value columns of that row
        for row in table.iter_rows(named=True):
            keys = set(json.loads(row["missing_reason"])) if row["missing_reason"] else set()
            nulls = {k for k, v in row.items() if k not in ("missing_reason",) and v is None
                     and not k.startswith("source_") and k not in ("latitude", "longitude")}
            self.assertEqual(keys, nulls)

    def test_value_column_mapping(self):
        self.assertEqual(VALUE_COLUMNS["grs-weh-5deg-smoothed.parquet"][0], "weh_wt_pct")
        self.assertEqual(VALUE_COLUMNS["grs-weh-2deg-unsmoothed.parquet"][0], "weh_wt_pct")
        self.assertEqual(VALUE_COLUMNS["grs-th-5deg-smoothed.parquet"][0], "th_ppm")
        self.assertEqual(VALUE_COLUMNS["grs-k-5deg-smoothed.parquet"][0], "k_ppm")
        self.assertEqual(VALUE_COLUMNS["grs-kth-ratio-5deg-smoothed.parquet"][0],
                         "kth_ratio_ppm_as_labelled")

    def test_grid_helpers_and_ranges_are_documented(self):
        lat, lon = _expected_grid("grs-weh-5deg-smoothed.parquet")
        self.assertEqual(len(lat), 36)   # -87.5 .. 87.5 step 5
        self.assertEqual(len(lon), 72)   # 2.5 .. 357.5 step 5
        self.assertTrue(_near_set(lat, lat))          # self-consistency
        self.assertFalse(_near_set(lat, lat[:-1]))    # length mismatch rejected
        lat2, lon2 = _expected_grid("grs-weh-2deg-unsmoothed.parquet")
        self.assertEqual(len(lat2), 88)
        self.assertEqual(len(lon2), 180)
        # every product has a documented plausibility range and value columns
        for name in VALUE_COLUMNS:
            self.assertIn(name, RANGES)
            self.assertIn(name, EXPECTED_BINS)
            self.assertEqual(len(VALUE_COLUMNS[name]), 3)

    def test_meta_records_model_depth_and_scale(self):
        spec = {"columns": self.spec["columns"]}
        meta = product_meta("grs-weh-5deg-smoothed.parquet", spec, "h2o_sr_5x5")
        self.assertEqual(meta["body"], "Mars")
        self.assertEqual(meta["key"], ["latitude", "longitude"])
        self.assertIn("model", meta["modelStatus"].lower())
        self.assertIn("~1 m", meta["sensingDepth"])
        self.assertEqual(meta["sourceProduct"], "h2o_sr_5x5")
        self.assertIn("timeSupport", meta)

    def test_spot_pick_helper_covers_five_rows(self):
        picks = _spot_picks(2592)
        self.assertEqual(len(picks), 5)
        self.assertEqual(len(set(picks)), 5)
        self.assertTrue(all(0 <= p < 2592 for p in picks))

    def test_swim_sources_empty_while_unprobed(self):
        self.assertEqual(swim_sources(), [])


if __name__ == "__main__":
    unittest.main()
