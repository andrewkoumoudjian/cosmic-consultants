"""Tests for mars_topo (issue #103): labels, pixel mapping, slopes, reasons."""
from __future__ import annotations

import json
import unittest

import numpy as np

from p0ingest import mars_topo as mt


class SlopeTest(unittest.TestCase):
    def test_flat_surface_is_zero_slope(self):
        z = np.full((16, 16), 100.0, dtype=np.float32)
        slope, ok = mt.central_difference_slope(z, span_px=2, gsd_ns_m=10.0,
                                                gsd_ew_m=10.0, wrap_lon=False)
        self.assertTrue(ok[2:-2, 2:-2].all())
        self.assertEqual(float(np.nanmax(slope[2:-2, 2:-2])), 0.0)

    def test_ramp_matches_arctan_dy_dx(self):
        # 50 m rise over 200 m (1 px of 100 m grid) -> arctan(0.25)
        z = (np.tile(np.arange(16), (16, 1)) * 50.0).astype(np.float32)
        slope, ok = mt.central_difference_slope(z, span_px=2, gsd_ns_m=100.0,
                                                gsd_ew_m=100.0, wrap_lon=False)
        # centres 2 px apart: dz = 100 m over a 200 m baseline
        expected = np.degrees(np.arctan(100.0 / 200.0))
        self.assertTrue(ok[2:-2, 2:-2].all())
        self.assertTrue(np.allclose(slope[2:-2, 2:-2], expected, atol=1e-4))

    def test_wrap_lon_joins_edges(self):
        z = (np.tile(np.arange(8), (8, 1)) * 10.0).astype(np.float32)
        slope, ok = mt.central_difference_slope(z, span_px=2, gsd_ns_m=100.0,
                                                gsd_ew_m=100.0, wrap_lon=True)
        # wrapped columns are usable wherever the north-south neighbourhood is
        self.assertTrue(ok[2:-2, 0].all())
        self.assertTrue(ok[2:-2, -1].all())

    def test_span_must_be_even(self):
        with self.assertRaises(ValueError):
            mt.central_difference_slope(np.zeros((8, 8)), span_px=3,
                                        gsd_ns_m=1.0, gsd_ew_m=1.0, wrap_lon=False)

    def test_even_span_for_targets_midband(self):
        self.assertEqual(mt.even_span_for(30.0, 5.0), 6)
        self.assertEqual(mt.even_span_for(3.5, 0.5), 8)
        for target, gsd in ((30.0, 5.0), (3.5, 0.5), (30.0, 20.0), (3.5, 1.0)):
            span = mt.even_span_for(target, gsd)
            baseline = span * gsd
            lo, hi = {30.0: (20.0, 40.0), 3.5: (2.0, 5.0)}[target]
            self.assertGreaterEqual(baseline, lo, (target, gsd, span))
            self.assertLessEqual(baseline, hi + 0.05 * hi, (target, gsd, span))


class ReasonTest(unittest.TestCase):
    def test_json_reason_sorted_keys(self):
        reason = mt.json_reason({"b": "x", "a": "y"})
        self.assertEqual(json.loads(reason), {"a": "y", "b": "x"})
        self.assertLess(reason.index('"a"'), reason.index('"b"'))

    def test_json_reason_empty_is_none(self):
        self.assertIsNone(mt.json_reason({}))

    def test_site_row_null_reason_covers_value_only(self):
        row = mt.site_row_null("s", "coll", "no-data-here")
        self.assertEqual(set(json.loads(row["missing_reason"])), {"value"})
        self.assertEqual(row["value"], None)


class PixelMappingTest(unittest.TestCase):
    def test_megdr32_pixel_centres(self):
        # pixel centre of (0, 0) is (89.984, 0.016); nearest to it is itself
        line, sample = mt.megdr32_latlon_to_pixel(89.984375, 0.015625)
        self.assertEqual((line, sample), (0, 0))

    def test_megdr32_equator_prime_meridian(self):
        line, sample = mt.megdr32_latlon_to_pixel(0.0, 0.0)
        self.assertEqual(sample, 0)
        # pixel centre is within half a pixel of the equator
        self.assertLess(abs(90.0 - (line + 0.5) / 32.0), 0.5 / 32.0 + 1e-9)

    def test_megdr32_lon_wraps(self):
        line1, sample1 = mt.megdr32_latlon_to_pixel(10.0, 359.99)
        line2, sample2 = mt.megdr32_latlon_to_pixel(10.0, 0.0)
        self.assertEqual(sample1, mt.MEGDR_SAMPLES - 1)
        self.assertEqual(sample2, 0)

    def test_blended_px_roundtrip(self):
        label = {"lines": 53347, "samples": 106694, "min_lon": -180.0,
                 "max_lon": 180.0, "min_lat": -90.0, "max_lat": 90.0}
        lat, lon = mt.blended_px_to_latlon(label, 26673.0, 10000.0)
        line, sample = mt.blended_latlon_to_px(label, lat, lon)
        self.assertAlmostEqual(line, 26673.0, places=6)
        self.assertAlmostEqual(sample, 10000.0, places=6)

    def test_blended_lon_e_past_180_maps_into_label_range(self):
        label = {"lines": 53347, "samples": 106694, "min_lon": -180.0,
                 "max_lon": 180.0, "min_lat": -90.0, "max_lat": 90.0}
        # meridiani site: 354.4734 E -> -5.5266 in the -180..180 label frame
        line, sample = mt.blended_latlon_to_px(label, -1.9462, 354.4734)
        lat, lon = mt.blended_px_to_latlon(label, line, sample)
        self.assertAlmostEqual(lon % 360.0, 354.4734, places=3)
        self.assertAlmostEqual(lat, -1.9462, places=6)

    def test_normalise_lon_e(self):
        self.assertAlmostEqual(mt.normalise_lon_e(354.4734), -5.5266)
        self.assertAlmostEqual(mt.normalise_lon_e(-5.5266), -5.5266)
        self.assertAlmostEqual(mt.normalise_lon_e(180.0), -180.0)


class SiteTest(unittest.TestCase):
    def test_six_named_sites_present(self):
        names = [s for s, _, _ in mt.SITES]
        self.assertEqual(names, ["jezero-perseverance", "gale-curiosity",
                                 "insight-elysium", "zhurong-utopia",
                                 "meridiani-opportunity", "gusev-spirit"])

    def test_bbox_selection_wraps_longitudes(self):
        # a CTX DTM tile in -10..0 E contains Meridiani at 354.47 E
        self.assertTrue(mt.site_bbox_contains([-10.0, -2.0, 0.0, 0.0],
                                              -1.9462, 354.4734))
        self.assertFalse(mt.site_bbox_contains([-10.0, -2.0, 0.0, 0.0],
                                               -1.9462, 30.0))

    def test_select_site_dtms_uses_largest_covering_item(self):
        lat0, lon0 = 18.4447, 77.4508  # Jezero, inside 76..78 E
        items = [{"id": "small", "bbox": [76.0, 18.0, 76.01, 18.01],
                  "assets": {"dtm": {"href": "s"}}},
                 {"id": "big", "bbox": [76.0, 18.0, 78.0, 19.0],
                  "assets": {"dtm": {"href": "b"}}}]
        chosen = mt.select_site_dtms("ctx-dtms-usgs-stac", items)
        self.assertEqual(chosen["jezero-perseverance"]["item_id"], "big")
        self.assertEqual(chosen["jezero-perseverance"]["dtm_url"], "b")

    def test_select_site_dtms_absent_site(self):
        chosen = mt.select_site_dtms("ctx-dtms-usgs-stac", [])
        self.assertEqual(chosen, {})

    def test_great_circle_distance_small(self):
        # ~1 degree of latitude on a 3396.19 km sphere
        d = mt.great_circle_distance_m(0.0, 0.0, 1.0, 0.0, mt.R_BLENDED)
        self.assertAlmostEqual(float(d), mt.R_BLENDED * np.pi / 180.0, places=3)


if __name__ == "__main__":
    unittest.main()
