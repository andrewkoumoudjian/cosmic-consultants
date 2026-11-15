"""Unit tests for moon_diviner (#100): synthetic sources, no network."""
import tempfile
import unittest
from pathlib import Path

import numpy as np
import polars as pl

from p0ingest.moon_diviner import (INVALID, UNKNOWN, band_edges, bin_gcp_columns,
                                   character_batches, gcp_missing_reason, gdr_batches,
                                   read_character_label, read_gdr_label, resolve_offset,
                                   write_batches)

PDS4 = '''<Product_Observational xmlns="http://pds.nasa.gov/pds4/pds/v1">
  <File_Area_Observational><File><file_name>x.tab</file_name></File>
  <Table_Character><offset>8</offset><records>2</records>
  <record_delimiter>Carriage-Return Line-Feed</record_delimiter><Record_Character>
  <fields>2</fields><record_length>14</record_length>
  <Field_Character><name>temp_max</name><field_location>1</field_location><field_length>5</field_length><data_type>ASCII_Real</data_type><unit>Kelvin</unit><description>Surface maximum</description></Field_Character>
  <Field_Character><name>ice_depth</name><field_location>9</field_location><field_length>4</field_length><data_type>ASCII_Real</data_type><unit>meter</unit><description>Model depth</description><Special_Constants><invalid_constant>-999</invalid_constant></Special_Constants></Field_Character>
  </Record_Character></Table_Character></File_Area_Observational></Product_Observational>'''

PDS3 = '''PDS_VERSION_ID            = "PDS3"
DATA_SET_ID               = "LRO-L-DLRE-5-GDR-V1.0"
PRODUCT_ID                = "DGDR_TEST_IMG.IMG"
DESCRIPTION               = "test"

OBJECT                    = UNCOMPRESSED_FILE
FILE_NAME                 = "DGDR_TEST_IMG.IMG"
RECORD_TYPE               = FIXED_LENGTH
FILE_RECORDS              = 2
RECORD_BYTES              = 6
^IMAGE                    = "DGDR_TEST_IMG.IMG"

 OBJECT                   = IMAGE
  NAME                    = "STANDARD CF"
  LINES                   = 2
  LINE_SAMPLES            = 3
  SAMPLE_TYPE             = LSB_INTEGER
  SAMPLE_BITS             = 16
  UNIT                    = NONE
  SCALING_FACTOR          = 0.001
  OFFSET                  = 0.00
  DERIVED_MINIMUM              = 7.0
  DERIVED_MAXIMUM              = 9.4
  MISSING_CONSTANT        = -32768
 END_OBJECT               = IMAGE

END_OBJECT                = UNCOMPRESSED_FILE

OBJECT                    = IMAGE_MAP_PROJECTION
 MAP_PROJECTION_TYPE          = "SIMPLE CYLINDRICAL"
 MAP_RESOLUTION               = 32 <pix/degree>
 MAXIMUM_LATITUDE             = 60 <deg>
 MINIMUM_LATITUDE             = -60 <deg>
END_OBJECT                = IMAGE_MAP_PROJECTION

END'''


class BandEdges(unittest.TestCase):
    def test_band_edges_and_rejections(self):
        self.assertEqual(band_edges("90s80s"), (-90.0, -80.0))
        self.assertEqual(band_edges("20s10s"), (-20.0, -10.0))
        self.assertEqual(band_edges("00n10n"), (0.0, 10.0))
        self.assertEqual(band_edges("80n90n"), (80.0, 90.0))
        for bad in ("00n10s", "5n15n", "10n10n", "80s90s"):
            with self.assertRaises(ValueError):
                band_edges(bad)


class PrpCharacterTable(unittest.TestCase):
    def test_fixed_width_offsets_and_declared_exclusion(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            label = root / "x.xml"
            label.write_text(PDS4)
            header = b"comment\n"                         # 8 bytes -> offset already 8
            record = b"  120   -999\r\n"                   # 12 content + CRLF = recordBytes
            record2 = ("  250" + "   " + "  10").encode() + b"\r\n"
            (root / "x.tab").write_bytes(header + record + record2)
            spec = read_character_label(label)
            self.assertEqual(spec["offset"], 8)
            self.assertEqual(spec["recordBytes"], 14)
            self.assertEqual(spec["fields"][1]["invalid"], [-999.0])
            frames = list(character_batches(root / "x.tab", spec, batch_size=1))
            self.assertEqual(frames[0]["temp_max"].to_list(), [120.0])
            self.assertEqual(frames[0]["ice_depth"].to_list(), [None])
            self.assertEqual(frames[0]["ice_depth_source_value"].to_list(), [-999.0])
            self.assertEqual(frames[1]["ice_depth"].to_list(), [10.0])
            self.assertEqual(frames[1]["source_record"].to_list(), [1])
            with (root / "x.tab").open("ab") as stream:
                stream.write(b"junk")
            with self.assertRaises(ValueError):
                list(character_batches(root / "x.tab", spec))

    def test_offset_resolution_from_trailing_bytes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            label = root / "x.xml"
            label.write_text(PDS4.replace("<offset>8</offset>", ""))
            (root / "x.tab").write_bytes(b"c" * 14 + b"  120   -999\r\n" + ("  250" + "   " + "  10").encode() + b"\r\n")
            spec = resolve_offset(root / "x.tab", read_character_label(label))
            self.assertEqual(spec["offset"], 14)
            (root / "short.tab").write_bytes(b"too short")
            with self.assertRaises(ValueError):
                resolve_offset(root / "short.tab", read_character_label(label) | {"offset": None})


class GcpBinning(unittest.TestCase):
    @staticmethod
    def _band(clon, clat, ltim, tbol):
        return bin_gcp_columns(np.asarray(clon, dtype=np.float64), np.asarray(clat, dtype=np.float64),
                               np.asarray(ltim, dtype=np.float64), np.asarray(tbol, dtype=np.float64),
                               0.0, 10.0)

    def test_native_grid_decode_nulls_and_summary(self):
        clon = np.repeat([-179.75, -179.25], 4)
        clat = np.full(8, 0.25)
        ltim = np.tile([0.12, 0.38, 0.62, 0.88], 2)
        tbol = np.array([100.0, 350.0, UNKNOWN, 200.0, 110.0, INVALID, 120.0, 300.0])
        native, summary, stats = self._band(clon, clat, ltim, tbol)
        self.assertEqual(native.height, 8)
        self.assertEqual(native["clat_bin"].unique().to_list(), [180])
        self.assertEqual(native["clon_bin"].unique().to_list(), [0, 1])
        self.assertEqual(native["tbol"].null_count(), 2)
        rows = {r["ltim_bin"]: r for r in native.filter(pl.col("clon_bin") == 0).iter_rows(named=True)}
        self.assertEqual(rows[0]["tbol"], 100.0)
        self.assertEqual(rows[2]["tbol"], None)
        self.assertEqual(rows[2]["missing_reason"], "source-no-observation")
        self.assertEqual(rows[1]["tbol"], 350.0)
        self.assertEqual(rows[3]["missing_reason"], None)
        top = summary.filter((pl.col("clat_bin") == 180) & (pl.col("clon_bin") == 0)).row(0, named=True)
        self.assertEqual(top["tsurf_max"], 350.0)
        self.assertEqual(top["tsurf_min"], 100.0)
        self.assertEqual(top["support_bins"], 3)
        self.assertAlmostEqual(top["tsurf_range"], 250.0, places=3)
        self.assertEqual(stats, {"invalid": 1, "unknown": 1})

    def test_all_invalid_cell_gets_nulls_with_reason(self):
        clon = np.full(4, -179.75)
        clat = np.full(4, 0.25)
        ltim = np.array([0.12, 0.38, 0.62, 0.88])
        tbol = np.full(4, UNKNOWN)
        native, summary, _ = self._band(clon, clat, ltim, tbol)
        row = summary.row(0, named=True)
        self.assertEqual(row["support_bins"], 0)
        for key in ("tsurf_max", "tsurf_min", "tsurf_range"):
            self.assertIsNone(row[key])
        import json
        self.assertEqual(sorted(json.loads(row["missing_reason"]).keys()),
                         ["tsurf_max", "tsurf_min", "tsurf_range"])

    def test_missing_reason_json_lists_exactly_null_columns(self):
        keys = sorted(__import__("json").loads(
            pl.DataFrame({"tsurf_max": [None], "tsurf_min": [1.0], "tsurf_range": [None]})
            .with_columns(gcp_missing_reason())["missing_reason"][0]))
        self.assertEqual(keys, ["tsurf_max", "tsurf_range"])
        self.assertEqual(__import__("json").loads(
            pl.DataFrame({"tsurf_max": [1.0], "tsurf_min": [1.0], "tsurf_range": [1.0]})
            .with_columns(gcp_missing_reason())["missing_reason"][0]), {})

    def test_off_grid_and_physical_range_rejected(self):
        with self.assertRaises(ValueError):
            self._band([-179.77], [0.25], [0.12], [300.0])          # off-grid longitude
        with self.assertRaises(ValueError):
            self._band([-179.75], [0.25], [0.5], [300.0])           # off-grid local time
        with self.assertRaises(ValueError):
            self._band([-179.75], [25.25], [0.12], [300.0])         # latitude outside band
        with self.assertRaises(ValueError):
            self._band([-179.75], [0.25], [0.12], [-10.0])          # unphysical temperature
        with self.assertRaises(ValueError):
            self._band([-179.75], [0.25], [1.0], [300.0])           # 1.0 is not a bin centre


class GdrMaps(unittest.TestCase):
    def test_label_scaling_missing_and_batches(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            label = root / "dgdr_std_cf_clc_cyl_032_img.lbl"
            label.write_text(PDS3)
            image = root / "dgdr_std_cf_clc_cyl_032_img.img"
            dnp = np.array([[7500, 8000, -32768], [9000, -1, 7600]], dtype="<i2")
            image.write_bytes(dnp.tobytes())
            spec = read_gdr_label(label, image, "dgdr_std_cf_clc_cyl_032_img")
            self.assertEqual(spec["shape"], (2, 3))
            self.assertEqual(spec["missing"], -32768)
            frames = list(gdr_batches(image, spec, "cf_position", batch_lines=1))
            self.assertEqual(len(frames), 2)
            first = frames[0].to_dicts()
            self.assertEqual([r["source_line"] for r in first], [0, 0, 0])
            self.assertEqual([r["source_sample"] for r in first], [0, 1, 2])
            self.assertAlmostEqual(first[0]["cf_position"], 7.5, places=5)
            self.assertIsNone(first[2]["cf_position"])
            self.assertEqual(first[2]["missing_reason"], "source-missing-constant")
            second = frames[1].to_dicts()
            self.assertEqual(second[0]["cf_position"], 9.0)
            self.assertEqual(second[1]["source_dn"], -1)
            self.assertEqual(second[1]["missing_reason"], "outside-label-derived-range")
            self.assertIsNone(second[1]["cf_position"])
            (root / "short.lbl").write_text(PDS3)
            (root / "short.img").write_bytes(b"x")
            with self.assertRaises(ValueError):
                read_gdr_label(root / "short.lbl", root / "short.img", "dgdr_std_cf_clc_cyl_032_img")

    def test_wrong_image_name_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            label = root / "x.lbl"
            label.write_text(PDS3.replace('NAME                    = "STANDARD CF"',
                                          'NAME                    = "ROCK ABUNDANCE"'))
            image = root / "x.img"
            image.write_bytes(np.zeros((2, 3), dtype="<i2").tobytes())
            with self.assertRaises(ValueError):
                read_gdr_label(label, image, "dgdr_std_cf_clc_cyl_032_img")


class WriteBatches(unittest.TestCase):
    def test_atomic_write_counts_and_duplicate_columns_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            good = root / "good.parquet"
            meta = write_batches(good, iter([pl.DataFrame({"a": [1, 2]})]))
            self.assertEqual(meta["rows"], 2)
            self.assertEqual(meta["nullCounts"], {"a": 0})
            self.assertTrue(good.exists() and not good.with_suffix(".part").exists())
            import pyarrow.compute as pc
            table = pl.read_parquet(good).to_arrow()
            self.assertEqual(table.num_rows, 2)
            empty = root / "empty.parquet"
            with self.assertRaises(ValueError):
                write_batches(empty, iter([]))


if __name__ == "__main__":
    unittest.main()
