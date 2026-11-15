"""Unit tests for p0ingest.moon_spectral (#102).

Offline by construction: synthetic PDS3 labels, synthetic arrays and tmp
files. Raw-fetch verification against live sources happens in
`python -m p0ingest.moon_spectral check` (not here).
"""
from __future__ import annotations

import hashlib
import tempfile
import unittest
from pathlib import Path

import numpy as np
import polars as pl

from p0ingest.moon_spectral import (
    MISSING,
    NOT_FINITE,
    NO_VALID,
    NODATA,
    RANGES,
    TABLES,
    assert_reason_contract,
    boxcar,
    check_minirf_label,
    mask_frame,
    parse_lamp_label,
    pds3_object,
    pds3_scalar,
    read_pc_real,
    real_frames,
    verify_source_md5,
)

MINIRF_LABEL = """PDS_VERSION_ID                 = PDS3
RECORD_BYTES                   = 46080
DATA_SET_ID                    = "LRO-L-MRFLRO-5-GLOBAL-MOSAIC-V1.0"
TARGET_NAME                    = "MOON"
CENTER_FREQUENCY               = 2380000439.72767878 <Hz>
^IMAGE                         = "GLOBAL_CPR_32PPD_SIMP_0C.IMG"
OBJECT                         = IMAGE
  LINES                        = 5760
  LINE_SAMPLES                 = 11520
  SAMPLE_BITS                  = 32
  SAMPLE_TYPE                  = PC_REAL
  MISSING_CONSTANT             = -1.7976931E+308
END_OBJECT                     = IMAGE
OBJECT                         = IMAGE_MAP_PROJECTION
  MAP_PROJECTION_TYPE          = "SIMPLE CYLINDRICAL"
  A_AXIS_RADIUS                = 1737.4 <km>
  CENTER_LATITUDE              = 0.0 <deg>
  CENTER_LONGITUDE             = 0.0 <deg>
END_OBJECT                     = IMAGE_MAP_PROJECTION
END
"""


class Pds3Parsing(unittest.TestCase):
    def test_scalar_extracts_quoted_and_unit_values(self):
        assert pds3_scalar(MINIRF_LABEL, "DATA_SET_ID") == "LRO-L-MRFLRO-5-GLOBAL-MOSAIC-V1.0"
        assert pds3_scalar(MINIRF_LABEL, "CENTER_FREQUENCY") == "2380000439.72767878"
        assert pds3_scalar(MINIRF_LABEL, "A_AXIS_RADIUS") == "1737.4"

    def test_scalar_missing_key_raises(self):
        with self.assertRaises(ValueError):
            pds3_scalar(MINIRF_LABEL, "NOT_PRESENT")

    def test_object_extraction(self):
        image = pds3_object(MINIRF_LABEL, "IMAGE")
        self.assertIn("LINES", image)
        self.assertNotIn("DATA_SET_ID", image)
        projection = pds3_object(MINIRF_LABEL, "IMAGE_MAP_PROJECTION")
        self.assertNotIn("MISSING_CONSTANT", projection)

    def test_minirf_label_accepts_layout(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "label.lbl"
            path.write_text(MINIRF_LABEL)
            spec = check_minirf_label(path)
        self.assertEqual(spec["lines"], 5760)
        self.assertEqual(spec["samples"], 11520)
        self.assertAlmostEqual(spec["frequency_hz"], 2380000439.72767878)

    def test_minirf_label_rejects_changed_layout(self):
        broken = MINIRF_LABEL.replace("LINE_SAMPLES                 = 11520",
                                      "LINE_SAMPLES                 = 11521")
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "label.lbl"
            path.write_text(broken)
            with self.assertRaises(ValueError):
                check_minirf_label(path)

    def test_minirf_label_rejects_wrong_target(self):
        broken = MINIRF_LABEL.replace('"MOON"', '"MARS"')
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "label.lbl"
            path.write_text(broken)
            with self.assertRaises(ValueError):
                check_minirf_label(path)

    def test_lamp_label_accepts_layout_and_rejects_flip(self):
        north = """DATA_SET_ID                    = "LRO-L-LAMP-5-GDR-V1.0"
OBJECT                         = IMAGE
  LINES                        = 2501
  LINE_SAMPLES                 = 2501
  SAMPLE_BITS                  = 32
  SAMPLE_TYPE                  = PC_REAL
  DESCRIPTION                  = "
    Each sample represents off-band to on-band albedo ratio as a
    dimensionless fraction."
END_OBJECT                     = IMAGE
OBJECT                         = IMAGE_MAP_PROJECTION
  MAP_PROJECTION_TYPE          = "POLAR STEREOGRAPHIC"
  MAP_SCALE                    = 240 <m/pix>
  MAP_RESOLUTION               = 126.347 <pix/deg>
  CENTER_LATITUDE              = 90 <deg>
END_OBJECT                     = IMAGE_MAP_PROJECTION
END
"""
        south = north.replace("CENTER_LATITUDE              = 90", "CENTER_LATITUDE              = -90")
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "n.lbl").write_text(north)
            (root / "s.lbl").write_text(south)
            self.assertEqual(parse_lamp_label(root / "n.lbl", "n")["center_latitude"], 90.0)
            self.assertEqual(parse_lamp_label(root / "s.lbl", "s")["center_latitude"], -90.0)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "n.lbl"
            path.write_text(north)  # north label, asked as south
            with self.assertRaises(ValueError):
                parse_lamp_label(path, "s")

    def test_lamp_label_rejects_off_band_relabeling(self):
        tampered = """DATA_SET_ID                    = "LRO-L-LAMP-5-GDR-V1.0"
OBJECT                         = IMAGE
  LINES                        = 2501
  LINE_SAMPLES                 = 2501
  SAMPLE_BITS                  = 32
  SAMPLE_TYPE                  = PC_REAL
  DESCRIPTION                  = "Each sample represents Lyman-alpha albedo."
END_OBJECT                     = IMAGE
OBJECT                         = IMAGE_MAP_PROJECTION
  MAP_PROJECTION_TYPE          = "POLAR STEREOGRAPHIC"
  MAP_SCALE                    = 240 <m/pix>
  MAP_RESOLUTION               = 126.347 <pix/deg>
  CENTER_LATITUDE              = 90 <deg>
END_OBJECT                     = IMAGE_MAP_PROJECTION
END
"""
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "tampered.lbl"
            path.write_text(tampered)
            with self.assertRaises(ValueError):
                parse_lamp_label(path, "n")


class DecodeAndClean(unittest.TestCase):
    def test_read_pc_real_is_little_endian(self):
        # PDS3 PC_REAL is little-endian (MSB_* would be the big-endian kind)
        values = np.array([[1.5, 2.5], [3.5, 4.5]], dtype="<f4")
        values[1, 1] = np.float32(np.nan)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "x.img"
            path.write_bytes(values.tobytes())
            got = read_pc_real(path, 2, 2)
        self.assertEqual(float(got[0, 0]), 1.5)
        self.assertEqual(float(got[1, 0]), 3.5)
        self.assertFalse(np.isfinite(float(got[1, 1])))

    def test_read_pc_real_byte_count_guard(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "short.img"
            path.write_bytes(b"\x00" * 12)
            with self.assertRaises(ValueError):
                read_pc_real(path, 2, 2)

    def test_real_frames_nulls_and_reason(self):
        values = np.arange(6, dtype="<f4").reshape(2, 3)
        values[0, 2] = np.float32(np.nan)
        frames = list(real_frames(values, "cpr_minirf", NOT_FINITE))
        frame = pl.concat(frames)
        self.assertEqual(frame.height, 6)
        self.assertIn("cpr_minirf", frame.columns)
        self.assertIn("missing_reason", frame.columns)
        row = frame.filter((pl.col("source_line") == 0) & (pl.col("source_sample") == 2))
        self.assertIsNone(row.get_column("cpr_minirf").item())
        self.assertEqual(row.get_column("missing_reason").item(), NOT_FINITE)
        # everything else carries the raw value and reason None
        self.assertEqual(frame.get_column("missing_reason").null_count(), 5)
        assert_reason_contract(frame, "cpr_minirf")
        self.assertEqual(float(frame.filter((pl.col("source_line") == 1)
                                            & (pl.col("source_sample") == 0))
                               .get_column("cpr_minirf").item()), 3.0)

    def test_real_frames_masks_declared_missing_sentinel(self):
        # MISSING_CONSTANT -1.7976931e308 truncated to the stored 32-bit real
        # saturates near -FLT_MAX; |v| >= 1e38 must read as the missing constant,
        # never as a physical value
        values = np.full((2, 3), 0.4, dtype="<f4")
        values[1, 2] = np.float32(-3.4028226550889045e+38)
        frames = list(real_frames(values, "cpr_minirf", NOT_FINITE, missing=True))
        frame = pl.concat(frames)
        got = frame.filter((pl.col("source_line") == 1) & (pl.col("source_sample") == 2))
        self.assertIsNone(got.get_column("cpr_minirf").item())
        self.assertEqual(got.get_column("missing_reason").item(), MISSING)
        keep = frame.filter((pl.col("source_line") == 0) & (pl.col("source_sample") == 1))
        self.assertAlmostEqual(float(keep.get_column("cpr_minirf").item()), 0.4, places=5)

    def test_real_frames_keeps_producer_ratio_artifacts(self):
        # declared-QA-only policy: a small negative ratio is data, not null
        values = np.array([[-0.5, 30.0]], dtype="<f4")
        frame = pl.concat(list(real_frames(values, "cpr_minirf", NOT_FINITE, missing=True)))
        self.assertEqual(frame.get_column("missing_reason").null_count(), 2)

    def test_mask_frame_declared_nodata(self):
        values = np.array([[1.0, 2.0], [3.0, 4.0]])
        valid = np.array([[True, False], [True, True]])
        frame = mask_frame(np.array([0, 1], dtype=np.uint16), np.array([0, 1], dtype=np.uint16),
                           values, valid, "feo_wt", NODATA)
        self.assertEqual(frame.height, 4)
        self.assertIsNone(frame.filter((pl.col("source_line") == 0)
                                       & (pl.col("source_sample") == 1)).get_column("feo_wt").item())
        self.assertEqual(frame.filter(pl.col("feo_wt") == 3.0)
                         .get_column("missing_reason").item(), None)
        assert_reason_contract(frame, "feo_wt")

    def test_boxcar_sums_counts(self):
        values = np.array([[1.0, 2.0], [3.0, 4.0]])
        valid = np.array([[True, True], [True, False]])
        sums, counts = boxcar(values, valid, factor=2)
        self.assertEqual(counts.tolist(), [[3]])
        self.assertEqual((sums / counts).tolist(), [[2.0]])

    def test_boxcar_rejects_non_dividing_shape(self):
        with self.assertRaises(ValueError):
            boxcar(np.ones((3, 3)), np.ones((3, 3), dtype=bool), factor=2)


class Contracts(unittest.TestCase):
    def test_tables_share_the_contract_shape(self):
        for name, spec in TABLES.items():
            self.assertIn("source_line", spec["columns"])
            self.assertIn("source_sample", spec["columns"])
            self.assertIn(spec["value"], spec["columns"])
            self.assertIn("missing_reason", spec["columns"])
            self.assertTrue(spec["rows"] > 0)
            # reasons may be an empty set ONLY when the source declares no nodata
            # (lroc-wac-global 8-bit mosaic ships nodata=None -> all-valid rule)
            all_valid_ok = spec is TABLES["lroc-wac-global/lroc-wac-albedo-3ppd.parquet"]
            if not all_valid_ok:
                self.assertTrue(spec["reasons"])

    def test_physical_ranges_guard_corruption(self):
        # ranges are preparation-corruption guards (an endianness/offset error
        # produces +-1e+29..1e+38), not data filters: producer ratio artifacts
        # stay inside the band, garbage does not
        for value, (low, high) in RANGES.items():
            self.assertLess(low, high, value)
            self.assertLessEqual(abs(low), 1e8, value)
            self.assertLess(high, 1e8, value)

    def test_minirf_reason_code_is_not_a_lamp_reason(self):
        # each table declares its own, narrow reason sets (with pytest-style
        # clarity, unittest asserts): they must not share undeclared codes
        self.assertNotIn(MISSING, TABLES["kaguya-mi-59mpp/kaguya-mi-feo-4ppd.parquet"]["reasons"])
        # WAC mosaic ships nodata=None: the honest rule is all-valid, no reasons
        self.assertEqual(TABLES["lroc-wac-global/lroc-wac-albedo-3ppd.parquet"]["reasons"], set())
        self.assertNotIn(NO_VALID, TABLES["lroc-wac-global/lroc-wac-albedo-3ppd.parquet"]["reasons"])
        self.assertNotIn(NODATA, TABLES["minirf-pds/minirf-cpr-32ppd.parquet"]["reasons"])

    def test_verify_source_md5_matches_and_rejects(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            payload = root / "data.bin"
            payload.write_bytes(b"lunar payload bytes")
            md5_path = root / "data.bin.md5"
            digest = hashlib.md5(b"lunar payload bytes").hexdigest()
            md5_path.write_text(f"{digest}  data.bin\n")
            self.assertEqual(verify_source_md5(md5_path, payload), digest)
            md5_path.write_text(f"{'0' * 32}  data.bin\n")
            with self.assertRaises(ValueError):
                verify_source_md5(md5_path, payload)

    def test_missing_reason_contract_catches_breaks(self):
        frame = pl.DataFrame({
            "value": [1.0, None],
            "missing_reason": [None, "source-nodata"],
        })
        assert_reason_contract(frame, "value")
        broken = pl.DataFrame({"value": [1.0, None], "missing_reason": ["x", "source-nodata"]})
        with self.assertRaises(ValueError):
            assert_reason_contract(broken, "value")


if __name__ == "__main__":
    unittest.main()
