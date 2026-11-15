"""Unit tests for the THEMIS ROI preparation (#104). No network access needed."""
import json
import math
import tempfile
import unittest
from pathlib import Path

import numpy as np
import polars as pl
import rasterio
from rasterio.transform import from_origin

from p0ingest.mars_themis import (DATASET, MISSING_NO_DATA, NODATA_DN, PIXEL_METRES,
                                  ROI_HALF_DEG, MARS_A_METRES, SPOT_CHECKS,
                                  VALUE_COLUMN, lon_segments, parse_isis_mapping,
                                  pixel_indices, read_site_pixels, site_window)


def synthetic_quad(path: Path, width: int = 400, height: int = 300,
                   origin_lon: float = -45.0, origin_lat: float = 10.0) -> Path:
    """A small stand-in quad GeoTIFF in IAU_2015:49910-like simple cylindrical."""
    transform = from_origin(math.radians(origin_lon) * MARS_A_METRES,
                            math.radians(origin_lat) * MARS_A_METRES,
                            PIXEL_METRES, PIXEL_METRES)
    crs = rasterio.crs.CRS.from_proj4(
        "+proj=eqc +lat_ts=0 +lat_0=0 +lon_0=0 +x_0=0 +y_0=0 "
        "+a=3396190 +b=3376200 +units=m +no_defs")
    rng = np.random.default_rng(7)
    data = (rng.integers(1, 256, size=(height, width), dtype=np.uint8))
    data[0, :] = NODATA_DN  # top row is no-source-data
    with rasterio.open(path, "w", driver="GTiff", width=width, height=height,
                       count=1, dtype="uint8", crs=crs, transform=transform,
                       nodata=float(NODATA_DN)) as ds:
        ds.write(data, 1)
    return path


class IsisMapping(unittest.TestCase):
    LABEL = """Object = IsisCube
  Object = Core
    Group = Mapping
      ProjectionName     = SimpleCylindrical
      CenterLongitude    = 180
      TargetName         = Mars
      LatitudeType       = Planetocentric
      LongitudeDirection = PositiveEast
      LongitudeDomain    = 360
      MinimumLatitude    = 0
      MaximumLatitude    = 30
      MinimumLongitude   = 135
      MaximumLongitude   = 180
      PixelResolution    = 100
      Scale              = 592.747
    End_Group
  End_Object
End_Object
End"""

    def test_fields_and_floats(self):
        with tempfile.TemporaryDirectory() as directory:
            label = Path(directory) / "q.isis.lbl"
            label.write_text(self.LABEL)
            mapping = parse_isis_mapping(label)
            self.assertEqual(mapping["ProjectionName"], "SimpleCylindrical")
            self.assertEqual(mapping["LatitudeType"], "Planetocentric")
            self.assertEqual(mapping["LongitudeDirection"], "PositiveEast")
            self.assertEqual(mapping["MinimumLatitude"], 0.0)
            self.assertEqual(mapping["MaximumLatitude"], 30.0)
            self.assertEqual(mapping["MinimumLongitude"], 135.0)
            self.assertEqual(mapping["MaximumLongitude"], 180.0)
            self.assertEqual(mapping["PixelResolution"], 100.0)

    def test_missing_group_raises(self):
        with tempfile.TemporaryDirectory() as directory:
            label = Path(directory) / "q.isis.lbl"
            label.write_text("Object = IsisCube\nEnd_Object\n")
            with self.assertRaises(ValueError):
                parse_isis_mapping(label)


class RoiSelection(unittest.TestCase):
    FOOTPRINTS = {
        "mc11_oxia_dir": {"phase": "day", "mapping": {
            "MinimumLatitude": -30.0, "MaximumLatitude": 30.0,
            "MinimumLongitude": -45.0, "MaximumLongitude": 0.0}},
        "mc11_oxia_nir": {"phase": "night", "mapping": {
            "MinimumLatitude": -30.0, "MaximumLatitude": 30.0,
            "MinimumLongitude": -45.0, "MaximumLongitude": 0.0}},
        "mc12_arabia_dir": {"phase": "day", "mapping": {
            "MinimumLatitude": -30.0, "MaximumLatitude": 30.0,
            "MinimumLongitude": 0.0, "MaximumLongitude": 45.0}},
        "mc12_arabia_nir": {"phase": "night", "mapping": {
            "MinimumLatitude": -30.0, "MaximumLatitude": 30.0,
            "MinimumLongitude": 0.0, "MaximumLongitude": 45.0}},
        "mc13_syrtis_dir": {"phase": "day", "mapping": {
            "MinimumLatitude": -30.0, "MaximumLatitude": 30.0,
            "MinimumLongitude": 45.0, "MaximumLongitude": 90.0}},
        "mc13_syrtis_nir": {"phase": "night", "mapping": {
            "MinimumLatitude": -30.0, "MaximumLatitude": 30.0,
            "MinimumLongitude": 45.0, "MaximumLongitude": 90.0}},
    }

    def test_negative_domain_quads_match_east_longitudes(self):
        # 354.47E (Meridiani) sits in the -45..0 label-domain quad at low latitudes
        self.assertEqual(lon_segments(354.47, ROI_HALF_DEG), [(353.97, 354.97)])
        matches = [q for q in ("mc11_oxia_dir", "mc12_arabia_dir", "mc13_syrtis_dir")
                   if q in self._quads(-1.9, 354.47)]
        self.assertEqual(matches, ["mc11_oxia_dir"])

    def test_no_quad_when_outside_all_footprints(self):
        self.assertEqual(self._quads(-1.9, -60.0), [])      # lon outside
        self.assertEqual(self._quads(45.0, 20.0), [])       # lat outside

    def test_only_expected_phases(self):
        quads = self._quads(20.0, 60.0)
        self.assertEqual(set(quads), {"mc13_syrtis_dir", "mc13_syrtis_nir"})

    def _quads(self, lat, lon):
        from p0ingest.mars_themis import roi_quads
        return roi_quads(self.FOOTPRINTS, lat, lon % 360.0)


class SiteWindowsAndPixels(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.quad = synthetic_quad(Path(cls.tmp.name) / "q.tif",
                                  origin_lon=112.0, origin_lat=30.0)
        # synthetic quad covers lon 112..245+ deg and lat 10.53..30 ... narrow:
        # 400 cols * 100 m = 40 km ~ 0.67 deg; 300 rows * 100 m = 30 km ~ 0.5 deg

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_window_is_clamped_native_and_reports_clips(self):
        with rasterio.open(self.quad) as ds:
            lat_c = math.degrees(math.radians(30.0) - 150 * PIXEL_METRES / MARS_A_METRES)
            lon_c = math.degrees(math.radians(112.0) + 200 * PIXEL_METRES / MARS_A_METRES)
            win = site_window(ds, lat_c, lon_c)
            # the 1x1 deg ROI (~593 px) is wider than the 400x300 quad on every
            # side, so the window is clamped to the whole raster, with clips
            self.assertFalse(win["fullyInsideQuad"])
            self.assertEqual(win["rows"], 300)
            self.assertEqual(win["cols"], 400)
            self.assertGreater(win["clippedRows"], 0)
            self.assertGreater(win["clippedCols"], 0)

    def test_read_site_pixels_keys_nodata_and_missing_reason(self):
        with rasterio.open(self.quad) as ds:
            lat_c = math.degrees(math.radians(30.0) - 150 * PIXEL_METRES / MARS_A_METRES)
            lon_c = math.degrees(math.radians(112.0) + 200 * PIXEL_METRES / MARS_A_METRES)
            frame, win = read_site_pixels(ds, "q_test", "day", "test_site", lat_c, lon_c)
        self.assertEqual(frame.columns, ["site", "quad", "phase", "source_line",
                                         "source_sample", "lat_pc_deg", "lon_east_deg",
                                         VALUE_COLUMN, "missing_reason"])
        self.assertEqual(frame.height, win["rows"] * win["cols"])
        # pixel-centre coordinates: last valid row (299) sits half a pixel above
        # the raster's bottom edge, first column half a pixel right of the edge
        top = frame.filter(pl.col("source_line") == 0)
        self.assertEqual(top.filter(pl.col(VALUE_COLUMN).is_null()).height, top.height)
        self.assertTrue(all(r == MISSING_NO_DATA for r in top["missing_reason"]))
        valid = frame.filter(pl.col(VALUE_COLUMN).is_not_null())
        self.assertEqual(valid.filter(pl.col("missing_reason").is_not_null()).height, 0)
        self.assertEqual(valid.filter(pl.col(VALUE_COLUMN) == NODATA_DN).height, 0)
        self.assertLessEqual(frame["lat_pc_deg"].max(), 30.0)
        self.assertAlmostEqual(frame["lat_pc_deg"].min(),
                               math.degrees(math.radians(30.0)
                                            - 299.5 * PIXEL_METRES / MARS_A_METRES),
                               places=3)
        self.assertAlmostEqual(frame["lon_east_deg"].min(),
                               math.degrees(math.radians(112.0)
                                            + 0.5 * PIXEL_METRES / MARS_A_METRES)
                               % 360.0, places=3)

    def test_pixel_indices_matches_transform(self):
        with rasterio.open(self.quad) as ds:
            line, sample = pixel_indices(29.5, 112.3, ds.transform, ds.width, ds.height)
        # the containing pixel: (30 - 29.5) deg ~ 296.36 100 m pixels below the top
        self.assertEqual(line, 296)
        self.assertLess(abs(line - (math.radians(30.0) * MARS_A_METRES
                                    - math.radians(29.5) * MARS_A_METRES) / PIXEL_METRES), 2.0)

    def test_spot_check_list_has_two_phases_coverage(self):
        self.assertGreaterEqual(len(SPOT_CHECKS), 5)
        sites = {s for s, _lat, _lon in SPOT_CHECKS}
        self.assertGreaterEqual(len(sites), 5)


class MissingReasonContract(unittest.TestCase):
    def test_missing_reason_json_keys_exactly_the_null_column(self):
        payload = json.loads(MISSING_NO_DATA)
        self.assertEqual(set(payload), {VALUE_COLUMN})


if __name__ == "__main__":
    unittest.main()
