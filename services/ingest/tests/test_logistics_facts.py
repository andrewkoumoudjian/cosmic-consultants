"""#202 logistics facts: synthetic road segments only (no Natural Earth files needed)."""
import math
import unittest

import numpy as np

from p0ingest.logistics_facts import KM_PER_DEG, MAX_RING, SegmentIndex, nearest_road_km, point_segment_km


class SegmentDistance(unittest.TestCase):
    def test_perpendicular_and_endpoint_distances(self):
        seg = np.array([[0.0, 0.0, 1.0, 0.0]])  # along the equator
        self.assertAlmostEqual(point_segment_km(0.5, 0.5, seg)[0], 0.5 * KM_PER_DEG, places=6)   # perpendicular foot
        self.assertAlmostEqual(point_segment_km(0.0, 2.0, seg)[0], 1.0 * KM_PER_DEG, places=6)   # past the end -> endpoint
        self.assertAlmostEqual(point_segment_km(0.0, 0.25, seg)[0], 0.0, places=9)               # on the segment

    def test_longitude_shrinks_with_latitude(self):
        seg = np.array([[1.0, 60.0, 1.0, 61.0]])  # north-south segment 1 deg east of the point
        self.assertAlmostEqual(point_segment_km(60.5, 0.0, seg)[0], KM_PER_DEG * math.cos(math.radians(60.5)), places=6)

    def test_antimeridian_wrap(self):
        seg = np.array([[-179.9, 0.0, -179.9, 1.0]])
        self.assertLess(point_segment_km(0.5, 179.9, seg)[0], 25.0)


class IndexedSearch(unittest.TestCase):
    def test_matches_brute_force(self):
        rng = np.random.default_rng(3)
        start = np.c_[rng.uniform(-30, 30, 400), rng.uniform(-60, 60, 400)]
        step = rng.uniform(-0.3, 0.3, (400, 2))
        segs = np.c_[start, start + step]
        idx = SegmentIndex(segs)
        lat, lon = rng.uniform(-55, 55, 300), rng.uniform(-25, 25, 300)
        got = nearest_road_km(lat, lon, idx)
        for k in range(lat.size):
            brute = point_segment_km(lat[k], lon[k], segs).min()
            limit = MAX_RING * KM_PER_DEG * math.cos(math.radians(min(89.0, abs(lat[k]) + MAX_RING)))
            if brute <= limit:
                self.assertAlmostEqual(got[k], brute, places=6, msg=f"point {k}")
            else:
                self.assertTrue(np.isnan(got[k]), f"point {k} beyond the search radius must be null")

    def test_nothing_nearby_is_null_not_zero(self):
        idx = SegmentIndex(np.array([[100.0, 10.0, 100.5, 10.0]]))
        self.assertTrue(np.isnan(nearest_road_km(np.array([-40.0]), np.array([-60.0]), idx)[0]))


if __name__ == "__main__":
    unittest.main()
