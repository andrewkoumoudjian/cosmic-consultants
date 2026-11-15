"""#203 place labels: synthetic polygons and points only (no Natural Earth files needed)."""
import json
import unittest

import numpy as np

from p0ingest.place_names import COLUMNS, EARTH_R_KM, inside_rings, label_cells, locate, nearest


def square(x0, y0, x1, y1):
    return np.array([[x0, y0], [x1, y0], [x1, y1], [x0, y1], [x0, y0]], dtype=float)


def poly(name, rings, **extra):
    pts = np.vstack(rings)
    return {"bbox": (pts[:, 0].min(), pts[:, 1].min(), pts[:, 0].max(), pts[:, 1].max()), "rings": rings, "name": name, **extra}


class Geometry(unittest.TestCase):
    def test_hole_and_multi_part_use_even_odd(self):
        rings = [square(0, 0, 10, 10), square(3, 3, 7, 7), square(20, 0, 22, 2)]  # outer, hole, second part
        lon = np.array([1.0, 5.0, 21.0, 15.0])
        lat = np.array([1.0, 5.0, 1.0, 1.0])
        self.assertEqual(inside_rings(lon, lat, rings).tolist(), [True, False, True, False])

    def test_unclosed_ring_is_closed(self):
        ring = square(0, 0, 4, 4)[:-1]
        self.assertTrue(inside_rings(np.array([2.0]), np.array([2.0]), [ring])[0])

    def test_chunking_does_not_change_the_answer(self):
        rng = np.random.default_rng(7)
        t = np.linspace(0, 2 * np.pi, 3001)[:-1]
        star = np.c_[np.cos(t) * (5 + 2 * np.sin(9 * t)), np.sin(t) * (5 + 2 * np.sin(9 * t))]
        lon, lat = rng.uniform(-8, 8, 5000), rng.uniform(-8, 8, 5000)
        a = inside_rings(lon, lat, [star], chunk=64)
        b = inside_rings(lon, lat, [star], chunk=100000)
        self.assertTrue(np.array_equal(a, b))
        self.assertTrue(0 < a.sum() < a.size)

    def test_locate_counts_overlaps_instead_of_picking(self):
        polys = [((0, 0, 10, 10), [square(0, 0, 10, 10)]), ((5, 5, 15, 15), [square(5, 5, 15, 15)])]
        idx, count = locate(np.array([1.0, 7.0, 20.0]), np.array([1.0, 7.0, 20.0]), polys)
        self.assertEqual(count.tolist(), [1, 2, 0])
        self.assertEqual(idx[0], 0)

    def test_haversine_distance(self):
        # one degree of latitude on the mean-radius sphere
        _, d = nearest(np.array([0.0]), np.array([0.0]), np.array([1.0]), np.array([0.0]))
        self.assertAlmostEqual(d[0], EARTH_R_KM * np.pi / 180, places=6)
        # across the antimeridian is short, not ~360 degrees
        _, d = nearest(np.array([0.0]), np.array([179.9]), np.array([0.0]), np.array([-179.9]))
        self.assertLess(d[0], 25)


class Labels(unittest.TestCase):
    def setUp(self):
        self.admin0 = [poly("Alpha", [square(0, 0, 10, 10)], a3="ALP"),
                       poly("Beta", [square(10, 0, 20, 10)], a3="BET"),
                       poly("Overlap", [square(15, 5, 25, 15)], a3="OVL")]
        self.admin1 = [poly("North Alpha", [square(0, 5, 10, 10)])]
        self.places = [{"name": "Alphaville", "lat": 7.0, "lon": 2.0}]

    def run_cells(self, lat, lon):
        return label_cells(np.array(lat, float), np.array(lon, float), self.admin0, self.admin1, self.places)

    def test_labels_and_explicit_nulls(self):
        r = self.run_cells([7.2, 2.0, 7.0, -30.0], [2.0, 5.0, 17.0, -30.0])
        # cell 0: inside Alpha and North Alpha, 22 km from Alphaville
        self.assertEqual((r["place_country"][0], r["place_country_a3"][0], r["place_admin1"][0], r["place_nearest"][0]),
                         ("Alpha", "ALP", "North Alpha", "Alphaville"))
        self.assertAlmostEqual(r["place_nearest_km"][0], EARTH_R_KM * np.radians(0.2), places=2)
        self.assertEqual(json.loads(r["missing_reason"][0]), {})
        # cell 1: Alpha but no admin-1 polygon and no place within 50 km
        self.assertEqual(r["place_country"][1], "Alpha")
        self.assertIsNone(r["place_admin1"][1])
        self.assertEqual(json.loads(r["missing_reason"][1]), {
            "place_admin1": "centre-outside-admin1-polygons",
            "place_nearest": "no-populated-place-within-50km", "place_nearest_km": "no-populated-place-within-50km"})
        # cell 2: inside two admin-0 polygons -> null, never a guess
        self.assertIsNone(r["place_country"][2])
        self.assertEqual(json.loads(r["missing_reason"][2])["place_country"], "centre-in-several-admin0-polygons")
        # cell 3: open sea -> every column null, each with a reason
        self.assertTrue(all(r[c][3] is None for c in COLUMNS))
        self.assertEqual(set(json.loads(r["missing_reason"][3])), set(COLUMNS))

    def test_polygon_with_blank_name_is_a_reasoned_null(self):
        # Natural Earth has a few admin-1 polygons with an empty name and some "-99" codes
        self.admin1 = [poly("", [square(0, 5, 10, 10)])]
        self.admin0[0]["a3"] = "-99"
        r = self.run_cells([7.2], [2.0])
        self.assertIsNone(r["place_admin1"][0])
        self.assertIsNone(r["place_country_a3"][0])
        self.assertEqual(r["place_country"][0], "Alpha")
        self.assertEqual(json.loads(r["missing_reason"][0]), {
            "place_admin1": "admin1-polygon-has-no-name", "place_country_a3": "admin0-polygon-has-no-value"})

    def test_missing_reason_lists_exactly_the_null_columns(self):
        r = self.run_cells([7.2, 2.0, 7.0, -30.0, 1.0], [2.0, 5.0, 17.0, -30.0, 12.0])
        for i in range(5):
            nulls = {c for c in COLUMNS if r[c][i] is None}
            self.assertEqual(set(json.loads(r["missing_reason"][i])), nulls, f"row {i}")


class AssemblerLabelRole(unittest.TestCase):
    def test_label_columns_stay_text_and_unscaled(self):
        import polars as pl
        from p0ingest.assemble import Build, normalize_frame
        build = object.__new__(Build)
        build.reg = {"tables": {"probe": {"columns": [
            {"name": "aod", "trait": "dustProcess", "unit": "1"},
            {"name": "place_country", "trait": None, "unit": "text", "role": "label"},
            {"name": "place_nearest_km", "trait": None, "unit": "km", "role": "label"}]}}}
        frame = pl.DataFrame({"h3": ["a", "b", "c", "d"], "aod": [0.1, 0.2, 0.3, None],
                              "place_country": ["Chile", None, "Canada", "Chile"],
                              "place_nearest_km": [12.9, None, 30.4, 45.3]})
        scales = build.table_scales("probe", frame)
        norm, info = normalize_frame(frame, scales)
        self.assertEqual(info["scaledColumns"], ["aod"])
        self.assertEqual(info["unscaledColumns"]["place_country"], "label")
        self.assertEqual(info["unscaledColumns"]["place_nearest_km"], "label")
        self.assertTrue(norm["place_country"].equals(frame["place_country"]))
        self.assertTrue(norm["place_nearest_km"].equals(frame["place_nearest_km"]))
        self.assertFalse(scales["place_nearest_km"]["inSum"])


if __name__ == "__main__":
    unittest.main()
