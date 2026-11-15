"""Unit tests for the CRISM MTRDR summary-parameter preparation (#105).

The heavy checks (keys, ranges, missing reasons, raw spot checks) run in the
module's own `check` command against the real snapshots; here we test label
parsing, the pixel geometry derivation, fill handling and the missing-reason
JSON shape with synthetic cubes, plus a snapshot-present integration pass.
"""
import json
import math
import tempfile
import unittest
from pathlib import Path

import numpy as np
import polars as pl

from p0ingest import mars_crism as mc
from p0ingest.snapshots import SNAP

SU_NAME = "XXXX00000000_07_SU000J_MTR3"


def minimal_label(lines, samples, bands=60, corner_drift=0.0, sample_type="PC_REAL"):
    names = '"' + '",\n                               "'.join(mc.SU_BANDS) + '"'
    km_per_deg = 3393.833260758386 * math.pi / 180.0
    dlat = 0.018 / km_per_deg
    dlon = 0.018 / (km_per_deg * math.cos(math.radians(15.0)))
    maxlat, west = 18.5871740, 77.4692050
    return f'''PDS_VERSION_ID = PDS3
DATA_SET_ID = "{mc.BUNDLE_ID}"
PRODUCT_ID = "{SU_NAME}"
OBSERVATION_TYPE = FRT
OBSERVATION_ID = "16#000066A4#"
START_TIME = 2007-06-27T07:10:40.000
STOP_TIME = 2007-06-27T07:11:00.000
SOLAR_LONGITUDE = 123.4
MRO:PHOTOMETRIC_CORR_FLAG = ON
MRO:ATMOSPHERIC_CORR_FLAG = ON
MRO:EMPIRICAL_GEOM_NORM_FLAG = ON
MRO:EMPIRICAL_SMILE_CORR_FLAG = ON
OBJECT = IMAGE_MAP_PROJECTION
  MAP_PROJECTION_TYPE = "EQUIRECTANGULAR"
  A_AXIS_RADIUS = 3393.833260758386 <KILOMETER>
  CENTER_LATITUDE = 15.0000000 <DEGREE>
  CENTER_LONGITUDE = 0.0000000 <DEGREE>
  LINE_FIRST_PIXEL = 1 <PIXEL>
  LINE_LAST_PIXEL = {lines} <PIXEL>
  SAMPLE_FIRST_PIXEL = 1 <PIXEL>
  SAMPLE_LAST_PIXEL = {samples} <PIXEL>
  MAP_RESOLUTION = 3291.7295733
  MAP_SCALE = 0.0180000
  MINIMUM_LATITUDE = {maxlat - dlat * (lines - 1) - corner_drift:.7f} <DEGREE>
  MAXIMUM_LATITUDE = {maxlat:.7f} <DEGREE>
  WESTERNMOST_LONGITUDE = {west:.7f} <DEGREE>
  EASTERNMOST_LONGITUDE = {west + dlon * (samples - 1):.7f} <DEGREE>
  LINE_PROJECTION_OFFSET = 61184.9500000 <PIXEL>
  SAMPLE_PROJECTION_OFFSET = -246317.4944444 <PIXEL>
  COORDINATE_SYSTEM_NAME = "PLANETOCENTRIC"
END_OBJECT = IMAGE_MAP_PROJECTION
OBJECT = IMAGE
  LINES = {lines}
  LINE_SAMPLES = {samples}
  SAMPLE_TYPE = {sample_type}
  SAMPLE_BITS = 32
  BANDS = {bands}
  BAND_STORAGE_TYPE = BAND_SEQUENTIAL
  BAND_NAME = ( {names} )
END_OBJECT = IMAGE
END''', dlat, dlon


class BandAndFeatureMapping(unittest.TestCase):
    def test_official_set_contains_needed_parameters(self):
        self.assertEqual(len(mc.SU_BANDS), len(set(mc.SU_BANDS)))
        self.assertEqual(len(mc.PARAMS), 14)
        for feature, params in mc.FEATURE_PARAMS.items():
            self.assertTrue(params, feature)
            for p in params:
                self.assertIn(p, mc.SU_BANDS)
        self.assertEqual(mc.PARAMS, sorted(mc.PARAMS))

    def test_whole_fill_reason_lists_exactly_null_columns(self):
        keys = set(json.loads(mc.WHOLE_FILL_REASON))
        self.assertEqual(keys, set(mc.PARAMS))
        for v in json.loads(mc.WHOLE_FILL_REASON).values():
            self.assertTrue(v.startswith("fill-"))


class LabelAndGeometry(unittest.TestCase):
    def test_parse_validate_and_pixel_latlon(self):
        lines, samples = 5, 4
        text, dlat, dlon = minimal_label(lines, samples)
        with tempfile.TemporaryDirectory() as d:
            lbl = Path(d) / (SU_NAME + ".LBL")
            lbl.write_text(text)
            meta = mc.parse_scene_label(lbl)
            self.assertEqual(meta["label"]["LINES"], lines)
            self.assertEqual(meta["label"]["BANDS"], 60)
            self.assertEqual(meta["label"]["SAMPLE_BITS"], 32)
            self.assertEqual(meta["productId"], SU_NAME)
            geom = mc.validate_geometry(meta)
            self.assertLess(geom["checks"]["dlat_vs_corners"], 0.002)
            lat, lon = mc.pixel_latlon(meta, geom)
            self.assertAlmostEqual(lat[0], meta["projection"]["MAXIMUM_LATITUDE"], places=6)
            self.assertAlmostEqual(lon[0], meta["projection"]["WESTERNMOST_LONGITUDE"], places=6)
            self.assertAlmostEqual(abs(lat[-1] - meta["projection"]["MINIMUM_LATITUDE"]),
                                   0, delta=0.002)
            self.assertAlmostEqual(abs(lon[-1] - meta["projection"]["EASTERNMOST_LONGITUDE"]),
                                   0, delta=0.002)

    def test_geometry_rejects_moved_corners(self):
        text, _, _ = minimal_label(5, 4, corner_drift=0.05)
        with tempfile.TemporaryDirectory() as d:
            lbl = Path(d) / (SU_NAME + ".LBL")
            lbl.write_text(text)
            meta = mc.parse_scene_label(lbl)
            with self.assertRaises(ValueError):
                mc.validate_geometry(meta)

    def test_rejects_wrong_band_set(self):
        text, _, _ = minimal_label(5, 4)
        text = text.replace("BD1900R2", "BD1900X")
        with tempfile.TemporaryDirectory() as d:
            lbl = Path(d) / (SU_NAME + ".LBL")
            lbl.write_text(text)
            with self.assertRaises(ValueError):
                mc.parse_scene_label(lbl)

    def test_rejects_non_real_sample_type(self):
        text, _, _ = minimal_label(5, 4, sample_type="MSB_INTEGER")
        with tempfile.TemporaryDirectory() as d:
            lbl = Path(d) / (SU_NAME + ".LBL")
            lbl.write_text(text)
            with self.assertRaises(ValueError):
                mc.parse_scene_label(lbl)


class CubeFillHandling(unittest.TestCase):
    def test_fill_nulls_and_missing_reasons_whole_pixel(self):
        lines, samples = 2, 3
        text, _, _ = minimal_label(lines, samples)
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / (SU_NAME + ".LBL")).write_text(text)
            fill = np.float32(mc.FILL)
            cube = np.full((lines, samples, 60), 0.05, dtype="<f4")
            cube[0, 1, 0] = fill
            cube[1, :, :] = fill
            (root / (SU_NAME + ".IMG")).write_bytes(cube.tobytes())
            frame, meta = mc.scene_frame("jezero", "MTRDR/2020/1/" + SU_NAME, directory=root)
            self.assertTrue(meta["uniformPixelWideFill"])
            self.assertEqual(frame.height, lines * samples)
            # valid row keeps its value and an empty reason
            valid = frame.row(0, named=True)
            self.assertAlmostEqual(valid["OLINDEX3"], 0.05, places=6)
            self.assertEqual(valid["missing_reason"], "{}")
            # whole-60-band fill row -> every parameter key present
            whole = frame.row(lines * samples - 1, named=True)
            keys = json.loads(whole["missing_reason"])
            self.assertEqual(set(keys), set(mc.PARAMS))
            self.assertTrue(all(v.startswith("fill-") for v in keys.values()))
            for p in mc.PARAMS:
                self.assertIsNone(whole[p])

    def test_partial_fill_rows_get_exact_keys(self):
        lines, samples = 1, 4
        text, _, _ = minimal_label(lines, samples)
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / (SU_NAME + ".LBL")).write_text(text)
            cube = np.full((1, 4, 60), 0.1, dtype="<f4")
            cube[0, 1, mc.SU_BANDS.index("D2300")] = mc.FILL
            cube[0, 3, :] = mc.FILL
            (root / (SU_NAME + ".IMG")).write_bytes(cube.tobytes())
            frame, meta = mc.scene_frame("gale", "MTRDR/2020/2/" + SU_NAME, directory=root)
            self.assertFalse(meta["uniformPixelWideFill"])
            r1 = frame.row(1, named=True)
            self.assertEqual(set(json.loads(r1["missing_reason"])), {"D2300"})
            self.assertIsNone(r1["D2300"])
            self.assertIsNotNone(r1["BD1900_2"])
            r3 = frame.row(3, named=True)
            self.assertEqual(set(json.loads(r3["missing_reason"])), set(mc.PARAMS))
            r0 = frame.row(0, named=True)
            self.assertEqual(r0["missing_reason"], "{}")


class IntegrationIfSnapshotted(unittest.TestCase):
    TABLE = SNAP / "_derived" / "planetary" / "crism-mtrdr" / "crism-mtrdr-summary.parquet"

    def setUp(self):
        if not self.TABLE.exists():
            self.skipTest("crism-mtrdr-summary table not built in this checkout")

    def test_module_check_passes(self):
        mc.check()  # keys, ranges, footprints, missing reasons, raw spot checks


if __name__ == "__main__":
    unittest.main()
