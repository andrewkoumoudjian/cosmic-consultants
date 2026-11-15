"""Unit tests for p0ingest.moon_geology (issue #98, W39 moon geology).

Synthetic fixtures only - no raw snapshot downloads needed.
"""
import json
import struct
import unittest
from types import SimpleNamespace

import numpy as np

from p0ingest.moon_geology import (
    MOON_RADIUS_M,
    _prj_check,
    decode_wkb,
    meters_to_degrees,
    parse_pit_page,
    polygon_parts,
    polygon_wkb_degrees,
)


def _shape(points, parts):
    return SimpleNamespace(points=[tuple(p) for p in points], parts=parts)


class RingNesting(unittest.TestCase):
    def test_outer_hole_island_and_degenerate(self):
        big = [(0, 0), (0, 100), (100, 100), (100, 0), (0, 0)]
        hole = [(10, 10), (20, 10), (20, 20), (10, 20), (10, 10)]
        island = [(12, 12), (13, 12), (13, 13), (12, 13), (12, 12)]
        stray = [(500, 500), (501, 501)]  # degenerate: fewer than 4 points
        points = big + hole + island + stray
        parts = [0, len(big), len(big) + len(hole), len(big) + len(hole) + len(island)]
        polys, n_vertices, n_rings, n_degenerate = polygon_parts(_shape(points, parts))
        self.assertEqual(n_rings, 3)
        self.assertEqual(n_degenerate, 1)
        self.assertEqual(n_vertices, len(big) + len(hole) + len(island))
        self.assertEqual(len(polys), 2)
        outer, holes = polys[0]
        self.assertEqual(len(outer.pts), len(big))
        self.assertEqual(len(holes), 1)
        self.assertEqual(len(holes[0].pts), len(hole))
        outer2, holes2 = polys[1]
        self.assertEqual(len(outer2.pts), len(island))
        self.assertEqual(holes2, [])

    def test_winding_independent_nesting(self):
        # same hole geometry, opposite winding: must give the same result
        for flip in (False, True):
            big = [(0, 0), (0, 100), (100, 100), (100, 0), (0, 0)]
            hole = [(10, 10), (10, 20), (20, 20), (20, 10), (10, 10)]
            if flip:
                hole = hole[::-1]
            points = big + hole
            parts = [0, len(big)]
            polys, _, _, _ = polygon_parts(_shape(points, parts))
            self.assertEqual(len(polys), 1)
            self.assertEqual(len(polys[0][1]), 1)


class WkbRoundtrip(unittest.TestCase):
    def _polygons(self):
        big = [(0.0, 0.0), (0.0, 100.0), (100.0, 100.0), (100.0, 0.0), (0.0, 0.0)]
        hole = [(10.0, 10.0), (10.0, 20.0), (20.0, 20.0), (20.0, 10.0), (10.0, 10.0)]
        island = [(12.0, 12.0), (12.0, 13.0), (13.0, 13.0), (13.0, 12.0), (12.0, 12.0)]
        points = big + hole + island
        parts = [0, len(big), len(big) + len(hole)]
        return polygon_parts(_shape(points, parts))[0]

    def test_multipolygon_roundtrip_degrees(self):
        polygons = self._polygons()
        wkb = polygon_wkb_degrees(polygons)
        kind, decoded = decode_wkb(wkb)
        self.assertEqual(kind, "MultiPolygon")
        self.assertEqual(len(decoded), 2)
        outer = decoded[0][0]
        self.assertEqual(outer.shape, (6, 2))  # 4 source vertices + closure = 6? source is 5 with closure
        expected_first = meters_to_degrees(np.array(polygons[0][0].pts, dtype=np.float64))
        np.testing.assert_allclose(outer[: len(expected_first)], expected_first, atol=1e-12)
        self.assertEqual(len(decoded[0]), 2)  # outer + hole
        self.assertEqual(len(decoded[1]), 1)  # island only
        np.testing.assert_allclose(outer[-1], outer[0], atol=1e-12)  # closure

    def test_single_polygon_kind(self):
        ring = [(10.0, 10.0), (10.0, 20.0), (20.0, 20.0), (20.0, 10.0), (10.0, 10.0)]
        fixture = SimpleNamespace(pts=np.array(ring), area=-100.0)
        kind, decoded = decode_wkb(polygon_wkb_degrees([(fixture, [])]))
        self.assertEqual(kind, "Polygon")
        self.assertEqual(len(decoded), 1)
        np.testing.assert_allclose(
            decoded[0][0], np.rad2deg(np.vstack([np.array(ring), np.array(ring)[:1]]) / MOON_RADIUS_M),
            atol=1e-12)

    def test_wkb_header_bytes(self):
        polygons = self._polygons()
        wkb = polygon_wkb_degrees(polygons)
        little_endian, geom_type, n = struct.unpack("<BII", wkb[:9])
        self.assertEqual(little_endian, 1)
        self.assertEqual(geom_type, 6)
        self.assertEqual(n, 2)


class Projection(unittest.TestCase):
    def test_exact_inverse_at_known_point(self):
        pts = np.array([[MOON_RADIUS_M * np.radians(30.0), MOON_RADIUS_M * np.radians(-45.0)]])
        np.testing.assert_allclose(meters_to_degrees(pts), [[30.0, -45.0]], atol=1e-12)

    def test_equator_central_meridian_unchanged(self):
        np.testing.assert_allclose(
            meters_to_degrees(np.array([[0.0, 0.0], [1000.0, -1000.0]])),
            [[0.0, 0.0], [np.rad2deg(1000.0 / MOON_RADIUS_M), -np.rad2deg(1000.0 / MOON_RADIUS_M)]],
            atol=1e-15,
        )


class PrjCheck(unittest.TestCase):
    def test_accepts_declared_projection(self):
        prj = ('PROJCS["Moon2000_EquidistantCylindrical_clon0",GEOGCS["GCS_Moon_2000"],'
               '"1737400.0","Standard_Parallel_1",0.0,PROJECTION["Equirectangular"],'
               'UNIT["Meter",1.0]]')
        _prj_check(prj)

    def test_rejects_other_projection(self):
        with self.assertRaises(ValueError):
            _prj_check('PROJCS["Moon2000_PlateCarree_clon0"]')


class PitPageParsing(unittest.TestCase):
    FULL_PAGE = """
    Test Pit
    Mare Pit: Test Crater
    Latitude 14.0917 ° N
    Longitude 303.2299 ° E
    Inner pit diameter 45 m × 40 m
    Funnel diameter N/A
    Long axis azimuth 270 °
    Depth 30 m Funnel diameter N/A
    """

    def test_full_page_values(self):
        row = parse_pit_page(self.FULL_PAGE, 11)
        self.assertEqual(row["pit_name"], "Test Pit")
        self.assertEqual(row["pit_class_host"], "Mare Pit: Test Crater")
        self.assertEqual(row["page_number"], 11)
        self.assertEqual(row["lat_deg"], 14.0917)
        self.assertEqual(row["lon_deg_east"], 303.2299)
        self.assertEqual(row["lat_source"], "14.0917°N")
        self.assertEqual(row["lon_source"], "303.2299°E")
        self.assertEqual(row["inner_max_diameter_m"], 45.0)
        self.assertEqual(row["inner_min_diameter_m"], 40.0)
        self.assertIsNone(row["funnel_max_diameter_m"])
        self.assertIsNone(row["funnel_min_diameter_m"])
        self.assertEqual(row["long_axis_azimuth_deg"], 270.0)
        self.assertEqual(row["depth_m"], 30.0)
        missing = json.loads(row["missing_reason"])
        self.assertEqual(sorted(missing), ["funnel_max_diameter_m", "funnel_min_diameter_m"])

    def test_non_east_longitude_rejected(self):
        with self.assertRaises(ValueError):
            parse_pit_page(self.FULL_PAGE.replace("303.2299 ° E", "133.2299 ° W"), 5)

    def test_missing_latitude_returns_none(self):
        self.assertIsNone(parse_pit_page("Intro page\nNo coordinates here", 2))

    def test_threshold_prefix_value_kept_verbatim(self):
        page = self.FULL_PAGE.replace("Depth 30 m", "Depth >30 m")
        row = parse_pit_page(page, 12)
        self.assertEqual(row["depth_m"], 30.0)
        self.assertEqual(row["depth_m_source"], ">30")


if __name__ == "__main__":
    unittest.main()
