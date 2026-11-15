"""Unit tests for p0ingest.moon_lola pure helpers (#99). No network, no real rasters."""
import io
import struct
import unittest
import zipfile
from pathlib import Path
from tempfile import TemporaryDirectory

import numpy as np
import polars as pl

from p0ingest import moon_lola as m


class ParsePds3LabelTest(unittest.TestCase):
    def test_basic_fields_and_objects(self):
        label = m.parse_pds3_label(
            'PDS_VERSION_ID = "PDS3"\r\n'
            'OBJECT                = IMAGE\r\n'
            '  LINES               = 4\r\n'
            '  LINE_SAMPLES        = 8\r\n'
            '  SAMPLE_TYPE         = LSB_INTEGER\r\n'
            '  SCALING_FACTOR      = 0.00004\r\n'
            '  OFFSET              = 0.0\r\n'
            'END_OBJECT            = IMAGE\r\n'
            'DESCRIPTION = "multi\r\n'
            '  word value"\r\n'
            'END\r\n')
        image = label["objects"]["IMAGE"]
        self.assertEqual(image["LINES"], 4)
        self.assertEqual(image["SAMPLE_TYPE"], "LSB_INTEGER")
        self.assertAlmostEqual(image["SCALING_FACTOR"], 4e-5)
        self.assertEqual(image["OFFSET"], 0.0)

    def test_unit_suffix_stripped(self):
        label = m.parse_pds3_label('A = 60 <m/pix>\r\nEND\r\n')
        self.assertEqual(label["A"], 60)

    def test_list_value(self):
        label = m.parse_pds3_label('MISSION = {"A","B"}\r\nEND\r\n')
        self.assertEqual(label["MISSION"], ["A", "B"])


class StereoGeometryTest(unittest.TestCase):
    def test_calibrated_lbl_xy_fixed_convention(self):
        meta = {"lines": 2000, "samples": 2000, "mapScaleM": 500.0,
                "centerLat": -90.0, "centerLon": 0.0, "radiusM": m.MOON_R_M,
                "lineProjOffsetPx": 999.5, "sampleProjOffsetPx": 999.5}
        cal = m.calibrated_lbl_xy(meta)
        self.assertEqual(cal["xShiftPx"], 0.0)
        self.assertEqual(cal["ySign"], 1.0)
        self.assertLessEqual(cal["worstResidualPx"], 0.5)
        np.testing.assert_allclose(cal["x_m"][[0, -1]],
                                   [(0 - 999.5) * 500.0, (1999 - 999.5) * 500.0])
        np.testing.assert_allclose(cal["y_m"][[0, -1]],
                                   [999.5 * 500.0, (999.5 - 1999) * 500.0])

    def test_calibrated_lbl_xy_rejects_bad_geometry(self):
        meta = {"lines": 200, "samples": 200, "mapScaleM": 1e-6,
                "centerLat": -90.0, "centerLon": 0.0, "radiusM": m.MOON_R_M,
                "lineProjOffsetPx": 99.5, "sampleProjOffsetPx": 99.5}
        with self.assertRaises(ValueError):
            m.calibrated_lbl_xy(meta)

    def test_lbl_latlon_to_pixel_roundtrip_convention(self):
        meta = {"lines": 2000, "samples": 2000, "mapScaleM": 500.0,
                "centerLat": -90.0, "centerLon": 0.0, "radiusM": m.MOON_R_M,
                "lineProjOffsetPx": 999.5, "sampleProjOffsetPx": 999.5}
        cal = m.calibrated_lbl_xy(meta)
        row, col = m.lbl_latlon_to_pixel(meta, cal, -89.0, 0.0)
        # lon 0 north of the south pole is +y; +y maps UP (smaller line index)
        self.assertLess(row, meta["lineProjOffsetPx"])
        self.assertAlmostEqual(col, meta["sampleProjOffsetPx"], delta=1.0)

    def test_min_lat_reach_matches_label_claim(self):
        with TemporaryDirectory() as tmp:
            img = Path(tmp) / "p.img"
            lbl = Path(tmp) / "p.lbl"
            img.write_bytes(struct.pack("<8h", *[100] * 8))
            lbl.write_text(
                'PRODUCT_ID = "T"\r\n'
                'OBJECT = IMAGE\r\n  LINES = 4\r\n  LINE_SAMPLES = 2\r\n'
                '  SAMPLE_TYPE = LSB_INTEGER\r\n  SAMPLE_BITS = 16\r\n'
                '  SCALING_FACTOR = 1.0\r\n  OFFSET = 0.0\r\nEND_OBJECT = IMAGE\r\n'
                'OBJECT = IMAGE_MAP_PROJECTION\r\n  MAP_PROJECTION_TYPE = "POLAR STEREOGRAPHIC"\r\n'
                '  MAP_SCALE = 60 <m/pix>\r\n  A_AXIS_RADIUS = 1737.4 <km>\r\n'
                '  CENTER_LATITUDE = -90 <deg>\r\n  CENTER_LONGITUDE = 0 <deg>\r\n'
                '  LINE_PROJECTION_OFFSET = 1.5 <pix>\r\n  SAMPLE_PROJECTION_OFFSET = 1.5 <pix>\r\n'
                '  COORDINATE_SYSTEM_NAME = "MEAN EARTH/POLAR AXIS OF DE421"\r\n'
                'END_OBJECT = IMAGE_MAP_PROJECTION\r\nEND\r\n')
            arr, meta = m.open_lbl_img(img, lbl)
            self.assertEqual(arr.shape, (4, 2))
            self.assertEqual(meta["mapScaleM"], 60.0)
            self.assertEqual(meta["centerLat"], -90.0)
            # 2x2-pixel canvas, corners ~42.4 m from the pole -> still south of -89.99
            self.assertLess(meta["maxLat"], -89.99)


class WindowedArithmeticTest(unittest.TestCase):
    def test_disc_stencil_symmetry_and_extent(self):
        st = m.disc_stencil(100.0, 4.0)
        self.assertEqual(len(st), 1961)
        for si in (2, 3):
            self.assertAlmostEqual(sum(t[si] for t in st), 0.0)
        self.assertTrue(all(abs(complex(t[2], t[3])) <= 100.0 + 1e-9 for t in st))
        far = m.disc_stencil(45.0, 60.0)   # radius below one step: centre pixel only
        self.assertEqual(far, [(0, 0, 0.0, 0.0)])

    def test_plane_fit_recovers_ramp_slopes(self):
        n = 120
        step = 4.0
        east = np.tile(np.arange(n) * np.tan(np.radians(30.0)) * step, (n, 1))
        s_east = m.plane_fit_slope_block(east, step, 100.0)
        self.assertAlmostEqual(float(s_east[n // 2, n // 2]), 30.0, places=3)
        north = np.tile((np.arange(n) * np.tan(np.radians(45.0)) * step)[:, None], (1, n))
        self.assertAlmostEqual(float(m.plane_fit_slope_block(north, step, 100.0)[n // 2, n // 2]),
                               45.0, places=3)
        self.assertAlmostEqual(float(m.plane_fit_slope_block(np.zeros((n, n)), step, 100.0)[n // 2, n // 2]),
                               0.0, places=6)

    def test_plane_fit_partial_windows_are_nan(self):
        s = m.plane_fit_slope_block(np.tile(np.arange(40.0), (40, 1)), 4.0, 100.0)
        self.assertTrue(np.isnan(s[0, 0]))
        self.assertTrue(np.isnan(s[10, 10]))   # window needs +-25 px

    def test_plane_fit_hole_poisons_window(self):
        n = 120
        dem = np.tile(np.arange(n) * 0.5, (n, 1))
        dem[60, 60] = np.nan
        s = m.plane_fit_slope_block(dem, 4.0, 100.0)
        self.assertTrue(np.isnan(s[60, 60]))
        self.assertAlmostEqual(float(s[80, 80]), np.degrees(np.arctan(0.5 / 4.0)), places=3)

    def test_box_sums_against_bruteforce(self):
        rng = np.random.default_rng(7)
        v = rng.normal(size=(17, 23))
        v[3, 5] = np.nan
        v[10, 1] = np.nan
        num, den = m.box_sums(v, 2)
        for (i, j) in ((0, 0), (5, 6), (16, 22), (10, 1)):
            r0, r1 = max(0, i - 2), min(17, i + 3)
            c0, c1 = max(0, j - 2), min(23, j + 3)
            w = v[r0:r1, c0:c1]
            self.assertAlmostEqual(num[i, j], np.nansum(w), places=9)
            self.assertEqual(den[i, j], np.isfinite(w).sum())

    def test_edt_matches_bruteforce(self):
        mask = np.zeros((9, 11), dtype=bool)
        mask[2, 3] = True
        mask[7, 9] = True
        d = m.exact_edt_cells(mask)
        for i in range(9):
            for j in range(11):
                brute = min(np.hypot(i - a, j - b) for a in range(9) for b in range(11) if mask[a, b])
                self.assertAlmostEqual(d[i, j], brute, places=9)
        empty = np.zeros((5, 5), dtype=bool)
        self.assertGreater(m.exact_edt_cells(empty)[2, 2], 1e6)


class TableHelpersTest(unittest.TestCase):
    def test_pixel_keys_pairing(self):
        r, s = m._pixel_keys(7, 9, 3)
        np.testing.assert_array_equal(r, [7, 7, 7, 8, 8, 8])
        np.testing.assert_array_equal(s, [0, 1, 2, 0, 1, 2])

    def test_reason_expr_keys_match_nulls(self):
        reasons = {"a": "why-a", "b": "why-b"}
        frame = pl.DataFrame({"a": [1.0, float("nan")], "b": [2.0, 3.0]})
        frame = frame.with_columns([
            pl.when(pl.col("a").is_nan()).then(None).otherwise(pl.col("a")).alias("a"),
        ]).with_columns(m._reason_expr(reasons))
        out = frame["missing_reason"].to_list()
        self.assertEqual(out[0], "{}")
        self.assertEqual(out[1], '{"a":"why-a"}')

    def test_reason_expr_catches_unconverted_nan(self):
        # regression: a float column holding NaN (not null) silently produced
        # '{}' reasons; the psr grid build must convert NaN to null first
        reasons = {"psr_frac_2km": "psr-window-truncated"}
        frame = pl.DataFrame({"psr_frac_2km": [0.5, float("nan")]}).with_columns([
            pl.when(pl.col("psr_frac_2km").is_finite())
            .then(pl.col("psr_frac_2km")).otherwise(None).alias("psr_frac_2km"),
        ]).with_columns(m._reason_expr(reasons))
        self.assertEqual(frame["missing_reason"][0], "{}")
        self.assertEqual(frame["missing_reason"][1], '{"psr_frac_2km":"psr-window-truncated"}')

    def test_keep_any_value_drops_all_null_rows(self):
        frame = pl.DataFrame({"v": [1.0, None], "w": [None, None], "missing_reason": ["{}", "{}"]})
        kept = m._keep_any_value(frame, ["v", "w"])
        self.assertEqual(kept.height, 1)
        self.assertEqual(kept["v"][0], 1.0)


class GazetteerTest(unittest.TestCase):
    def _zip_with(self, path: Path, rows):
        # like the real snapshot: ESRI shapefile with lowercase attributes
        import shapefile
        w = shapefile.Writer(str(path.with_suffix("")), shapeType=shapefile.POINT)
        w.field("name", "C", size=40)
        w.field("center_lat", "N", decimal=6)
        w.field("center_lon", "N", decimal=6)
        w.field("diameter", "N", decimal=3)
        for name, lat, lon, diam in rows:
            w.point(lon, lat)
            w.record(name, lat, lon, diam)
        w.close()
        with zipfile.ZipFile(path, "w") as zf:
            for ext in (".shp", ".shx", ".dbf"):
                zf.write(path.with_suffix(ext), arcname="MOON_nomenclature_center_pts" + ext)

    def test_parses_named_features(self):
        rows = [("Shackleton", -89.67, 0.0, 21.0),
                ("Malapert", -84.93, 12.42, 69.0),
                ("Malapert M", -85.87, 21.32, 8.0)]
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "m.zip"
            self._zip_with(path, rows)
            feats = m.gazetteer_features(["shackleton", "Malapert", "Malapert M"], path=path)
            self.assertEqual(feats["shackleton"], (-89.67, 0.0, 21.0))
            self.assertEqual(feats["Malapert"], (-84.93, 12.42, 69.0))
            self.assertEqual(feats["Malapert M"], (-85.87, 21.32, 8.0))

    def test_m_suffix_fallback(self):
        rows = [("Malapert M", -85.87, 21.32, 8.0)]
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "m.zip"
            self._zip_with(path, rows)
            feats = m.gazetteer_features(["Malapert"], path=path)
            self.assertEqual(feats["Malapert"], (-85.87, 21.32, 8.0))

    def test_non_numeric_diameter_tolerated(self):
        rows = [("Shackleton", -89.67, 0.0, None)]
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "m.zip"
            self._zip_with(path, rows)
            feats = m.gazetteer_features(["Shackleton"], path=path)
            self.assertIsNone(feats["Shackleton"][2])

    def test_missing_feature_raises(self):
        rows = [("Shackleton", -89.67, 0.0, 21.0)]
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "m.zip"
            self._zip_with(path, rows)
            with self.assertRaises(ValueError):
                m.gazetteer_features(["Haworth"], path=path)


class CheckTableTest(unittest.TestCase):
    def _write(self, path: Path, frame: pl.DataFrame):
        path.parent.mkdir(parents=True, exist_ok=True)
        frame.write_parquet(path)

    def test_passes_consistent_table(self):
        frame = pl.DataFrame({
            "source_line": [0, 1], "source_sample": [0, 1],
            "elevation_m": [10.0, None],
            "missing_reason": ['{}', '{"elevation_m":"source-nodata"}'],
        })
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "t.parquet"
            self._write(path, frame)
            saved_tables, saved_range = dict(m.TABLES), dict(m.PHYSICAL_RANGE)
            m.TABLES["t.parquet"] = ("d", ["elevation_m"], {}, ["source_line", "source_sample"])
            m.PHYSICAL_RANGE["elevation_m"] = (-100.0, 100.0)
            try:
                m.check_table(path, "t.parquet", {"rows": 2})
            finally:
                m.TABLES.clear(); m.TABLES.update(saved_tables)
                m.PHYSICAL_RANGE.clear(); m.PHYSICAL_RANGE.update(saved_range)

    def test_rejects_mismatched_reason(self):
        frame = pl.DataFrame({
            "source_line": [0], "source_sample": [0],
            "elevation_m": [10.0],
            "missing_reason": ['{"elevation_m":"source-nodata"}'],
        })
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "t.parquet"
            self._write(path, frame)
            saved_tables, saved_range = dict(m.TABLES), dict(m.PHYSICAL_RANGE)
            m.TABLES["t.parquet"] = ("d", ["elevation_m"], {}, ["source_line", "source_sample"])
            m.PHYSICAL_RANGE["elevation_m"] = (-100.0, 100.0)
            try:
                with self.assertRaises(ValueError):
                    m.check_table(path, "t.parquet", {"rows": 1})
            finally:
                m.TABLES.clear(); m.TABLES.update(saved_tables)
                m.PHYSICAL_RANGE.clear(); m.PHYSICAL_RANGE.update(saved_range)

    def test_rejects_out_of_range(self):
        frame = pl.DataFrame({
            "source_line": [0], "source_sample": [0],
            "elevation_m": [5000.0],
            "missing_reason": ['{}'],
        })
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "t.parquet"
            self._write(path, frame)
            saved_tables, saved_range = dict(m.TABLES), dict(m.PHYSICAL_RANGE)
            m.TABLES["t.parquet"] = ("d", ["elevation_m"], {}, ["source_line", "source_sample"])
            m.PHYSICAL_RANGE["elevation_m"] = (-100.0, 100.0)
            try:
                with self.assertRaises(ValueError):
                    m.check_table(path, "t.parquet", {"rows": 1})
            finally:
                m.TABLES.clear(); m.TABLES.update(saved_tables)
                m.PHYSICAL_RANGE.clear(); m.PHYSICAL_RANGE.update(saved_range)


if __name__ == "__main__":
    unittest.main()
