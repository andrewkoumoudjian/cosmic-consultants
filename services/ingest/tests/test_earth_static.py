"""Offline tests for p0ingest.earth_static (W38, issue #97).

Covers: the spherical-sinusoid inverse vs GDAL (rasterio.warp), the
lattice binning of declared MOD44B codes, the histogram median, the
missing_reason <-> null columns exact match, the yearly-series choice
rule, and the parked-domain probe with a mocked HTTP getter.
No network access and no MANIFEST dependency in these tests.
"""
import contextlib
import io
import json
import unittest
from unittest.mock import patch

import numpy as np

from p0ingest import earth_static as es


class Sinusoid(unittest.TestCase):
    def test_forward_inverse_roundtrip(self):
        lat = np.array([-89.5, -45.0, 0.0, 30.0, 60.0, 83.0, 89.5])
        lon = np.array([-179.9, -120.0, -0.5, 0.5, 45.0, 130.0, 179.9])
        x, y = es.forward_sin(lat, lon)
        lat2, lon2 = es.inverse_sin(x, y)
        np.testing.assert_allclose(lat2, lat, atol=1e-9)
        np.testing.assert_allclose(lon2, lon, atol=1e-9)

    def test_inverse_matches_gdal_sinusoid_6371007(self):
        from rasterio.warp import transform
        lat = np.array([-70.0, -23.5, 0.0, 10.0, 45.0, 66.5, 80.0])
        lon = np.array([-100.0, 23.5, 0.0, 23.5, -60.0, 100.0, 15.0])
        x, y = es.forward_sin(lat, lon)
        gx, gy = transform("EPSG:4326",
                           "+proj=sinu +R=6371007.181 +lon_0=0 +lat_0=0 "
                           "+x_0=0 +y_0=0 +units=m",
                           lon.tolist(), lat.tolist())
        np.testing.assert_allclose(x, gx, rtol=0, atol=1e-6)
        np.testing.assert_allclose(y, gy, rtol=0, atol=1e-6)
        lat2, lon2 = es.inverse_sin(np.array(gx), np.array(gy))
        np.testing.assert_allclose(lat2, lat, atol=1e-6)
        np.testing.assert_allclose(lon2, lon, atol=1e-6)

    def test_sphere_from_tile_width(self):
        # the tile width pins R: R*2*pi/36 == 1111950.5197666666 m
        self.assertAlmostEqual(es.SPHERE_R * 2 * np.pi / 36,
                               es.TILE_PX_M * 4800, places=4)


class BinLayers(unittest.TestCase):
    def test_valid_water_fill_counts(self):
        # five pixels in lattice row 0, cols 0-4: 0/50/100 valid, 200 water, 253 fill
        v = np.array([[0, 50, 200, 253, 100]])
        lat = np.array([[89.975, 89.975, 89.975, 89.975, 89.975]])
        lon = np.array([[-179.975, -179.925, -179.875, -179.825, -179.775]])
        out = es._bin_layers({"percent_tree_cover": v}, lat, lon)
        n = out["lattice"]["percent_tree_cover"]["n"]
        s = out["lattice"]["percent_tree_cover"]["sum"]
        self.assertEqual(int(n[0]), 1)   # 0
        self.assertEqual(int(n[1]), 1)   # 50
        self.assertEqual(int(n[4]), 1)   # 100
        self.assertEqual(int(s[0]), 0)   # 0% is a valid sum, kept
        self.assertEqual(int(s[1]), 50)
        self.assertEqual(int(s[4]), 100)
        self.assertEqual(out["native"]["percent_tree_cover"],
                         {"valid": 3, "water": 1, "fill": 1, "other": 0, "offglobe": 0})

    def test_off_globe_corner_pixels_are_excluded_not_fatal(self):
        # a MODIS SIN tile corner can invert to lon < -180 (off the globe
        # ellipse); water/fill codes there are counted as offglobe, never binned
        v = np.array([[200, 253, 30]])
        lat = np.array([[45.0, 45.0, 45.0]])
        lon = np.array([[-182.7, 185.1, 10.0]])
        out = es._bin_layers({"percent_tree_cover": v}, lat, lon)
        self.assertEqual(out["native"]["percent_tree_cover"]["offglobe"], 2)
        self.assertEqual(out["native"]["percent_tree_cover"]["valid"], 1)
        self.assertEqual(int(out["lattice"]["percent_tree_cover"]["n"].sum()), 1)

    def test_valid_code_off_lattice_raises(self):
        # off the lattice but NOT beyond the ellipse -> geometry bug
        v = np.array([[42]])
        lat = np.array([[95.0]])
        lon = np.array([[10.0]])
        with self.assertRaises(RuntimeError) as cm:
            es._bin_layers({"percent_tree_cover": v}, lat, lon)
        self.assertIn("geometry bug", str(cm.exception))

    def test_codes_outside_declared_set_raise(self):
        v = np.array([[10, 250]])  # 250 is neither valid, water nor fill
        lat = np.array([[89.975, 89.975]])
        lon = np.array([[-179.975, -179.925]])
        with self.assertRaises(RuntimeError) as cm:
            es._bin_layers({"percent_tree_cover": v}, lat, lon)
        self.assertIn("outside", str(cm.exception))

    def test_bins_land_on_one_lattice_pixel_only(self):
        # two corners a fraction apart must land in distinct lattice pixels
        v = np.array([[10, 20]])
        lat = np.array([[0.0001, 0.0999]])
        lon = np.array([[0.0001, 0.0999]])
        out = es._bin_layers({"percent_tree_cover": v}, lat, lon)
        flat_a = int((90.0 - 0.0001) / es.CMG_STEP) * es.CMG_M \
            + int((180.0 + 0.0001) / es.CMG_STEP)
        flat_b = int((90.0 - 0.0999) / es.CMG_STEP) * es.CMG_M \
            + int((180.0 + 0.0999) / es.CMG_STEP)
        n = out["lattice"]["percent_tree_cover"]["n"]
        self.assertEqual(n[flat_a], 1)
        self.assertEqual(n[flat_b], 1)
        self.assertNotEqual(flat_a, flat_b)


class HistMedian(unittest.TestCase):
    # es._hist_median is regolith's, reused with bins shifted +1 so the
    # valid VCF value 0% is not dropped as a fill bin; test that wiring.
    def _medians(self):
        pct = np.array([[0, 10, 10, 25, 25, 100]], dtype=np.int64)
        hist = np.zeros((1, 102), np.int32)
        for v in pct[0]:
            hist[0, v + 1] += 1
        return es._hist_median(hist, np.arange(102, dtype=np.float64) - 1.0)

    def test_even_counts_mean_of_middle_two(self):
        np.testing.assert_allclose(self._medians(), [17.5])

    def test_zero_pct_is_a_value_not_fill(self):
        # five 0% pixels and one 100%: median must be 0, not NaN
        hist = np.zeros((1, 102), np.int32)
        hist[0, 1] = 5   # five lattice pixels at 0%
        hist[0, 101] = 1
        med = es._hist_median(hist, np.arange(102, dtype=np.float64) - 1.0)
        self.assertEqual(med[0], 0.0)

    def test_empty_is_nan(self):
        hist = np.zeros(3, np.int32)
        self.assertTrue(np.isnan(es._hist_median(hist.reshape(1, 3),
                                                 np.arange(3, dtype=np.float64))[0]))


class RowReasons(unittest.TestCase):
    def test_reason_keys_exactly_null_value_cols(self):
        have = np.array([True, False])
        reasons = es.row_reasons(2, have)
        self.assertEqual(json.loads(reasons[0]), {})
        self.assertEqual(json.loads(reasons[1]), {c: es.NO_DATA_CODE
                                                  for c in es.VALUE_COLS})
        self.assertEqual(set(json.loads(reasons[1])), set(es.VALUE_COLS))

    def test_value_cols_are_six(self):
        self.assertEqual(len(es.VALUE_COLS), 6)


class ChooseSeries(unittest.TestCase):
    @staticmethod
    def _tiles(year, tiles):
        return [{"granule": f"MOD44B.{year}065.{t}.061.2026097000000"} for t in tiles]

    def test_picks_newest_series_matching_previous_tile_set(self):
        rows = (self._tiles("A2026", ["h00v01"])                          # 1 tile: partial
                + self._tiles("A2025", ["h00v01", "h00v02", "h00v03"])
                + self._tiles("A2024", ["h00v01", "h00v02", "h00v03"]))
        year, info = es.choose_series(rows)
        self.assertEqual(year, "A2025")
        self.assertTrue(info["complete"])
        self.assertIn("matches A2024", info["rule"])

    def test_falls_back_to_floored_series(self):
        rows = (self._tiles("A2025", [f"h00v{v:02d}" for v in range(2, 292)])   # 290 tiles
                + self._tiles("A2024", ["h00v01"]))                              # 1 tile
        year, info = es.choose_series(rows)
        self.assertEqual(year, "A2025")
        self.assertFalse(info["complete"])


def fake_get_factory(responses):
    def fake_get(url, timeout=60):
        r = responses[url]
        return FakeResponse(status=r[0], text=r[1], url=url)
    return fake_get


class FakeResponse:
    def __init__(self, status, text, url):
        self.status_code = status
        self.text = text
        self.url = url
        self.content = text.encode()

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


class Probes(unittest.TestCase):
    def test_probe_eid_detects_parked_redirect(self):
        body = ("<html><script>window.location.href = \"/lander\";</script></html>")
        with patch.object(es, "_http_get", fake_get_factory(
                {es.EID_URL: (200, body)})):
            p = es.probe_eid()
        self.assertFalse(p["reachable"])
        self.assertTrue(p["parked"])
        self.assertEqual(p["httpStatus"], 200)
        self.assertLess(p["bytes"], 500)

    def test_probe_eid_marks_genuine_page_reachable(self):
        body = "<html>" + "x" * 2000 + "</html>"
        with patch.object(es, "_http_get", fake_get_factory(
                {es.EID_URL: (200, body)})):
            p = es.probe_eid()
        self.assertTrue(p["reachable"])
        self.assertFalse(p["parked"])

    def test_write_probes_covers_both_blocked_sources(self):
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as tmp:
            with patch.object(es, "_http_get", fake_get_factory(
                    {es.EID_URL: (200, "<x/>" + "y" * 600),
                     "https://nsidc.org/data/ggd318/versions/2": (200, "ok" * 500),
                     "https://daacdata.apps.nsidc.org/public/DATASETS/ggd318/": (401, "denied"),
                     es.GGD318_GUIDE: (200, "guide" * 500)})), \
                 patch.object(es, "DERIVED", Path(tmp)):
                ev = es.write_probes()
        self.assertIn("earth-impact-database", ev)
        self.assertIn("nsidc-ggd318-permafrost", ev)
        self.assertIn("verdict", ev["nsidc-ggd318-permafrost"])
        self.assertIn("blocked", ev["nsidc-ggd318-permafrost"]["verdict"])


class ManifestSideEffects(unittest.TestCase):
    def test_fetch_entrypoint_finds_no_hdf_guard_message(self):
        # series_on_disk must refuse to build from an empty MANIFEST
        with patch.object(es, "_all_manifest_hdfs", return_value=[]):
            sorry = False
            try:
                es.series_on_disk()
            except RuntimeError as exc:
                self.assertIn("--fetch", str(exc))
                sorry = True
            self.assertTrue(sorry)


if __name__ == "__main__":
    unittest.main()
