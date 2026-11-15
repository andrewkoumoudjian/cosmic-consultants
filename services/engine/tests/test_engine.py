"""Engine tests on SYNTHETIC tables (no real values; real-data spot checks
come with the L4 build). Run: python -m unittest discover -s tests (from
services/engine, with src on PYTHONPATH)."""
from __future__ import annotations

import json
import math
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from planner.logistics import limits, logistics  # noqa: E402
from planner.publish import publish, read_column  # noqa: E402
from planner.request import months_in_window, parse_query, to_query  # noqa: E402
from planner.risks import EONET_CATEGORIES, risks  # noqa: E402
from planner.tables import Tables  # noqa: E402

A, B = "84b2203ffffffff", "8429927ffffffff"  # valid r4 cells; values below are invented

EXAMPLE = {
    "version": 1, "body": "mars", "objectiveId": "OP-5LM", "category": "robotic-mobility-navigation",
    "missionType": "robotic", "months": {"start": 6, "end": 8}, "durationDays": 14, "teamSize": 6,
    "limits": {"access": 240, "protected": 0}, "must": ["terrain", "surfaceMaterial"],
    "sortBy": "terrain", "top": 20, "pins": [A, B],
}


def synthetic() -> Tables:
    cells = {
        A: {"h3": A, "lat": -24.45, "lon": -69.31, "slope_mean_deg": 6.2, "slope_frac_gt30": 0.02, "barren_pct": 71.0, "missing_reason": None},
        B: {"h3": B, "lat": 38.34, "lon": -110.83, "slope_mean_deg": None, "slope_frac_gt30": None, "barren_pct": 40.5,
            "missing_reason": json.dumps({"slope_mean_deg": "no-dem-tile", "slope_frac_gt30": "no-dem-tile"})},
    }
    monthly = {}
    for m in range(1, 13):
        monthly[(A, m)] = {"h3": A, "month": m, "lst_day_k": 300.0 + m, "lst_night_k": 270.0 - m, "polar_night": False,
                           "burned_pct": 0.5 * m}
        monthly[(B, m)] = {"h3": B, "month": m, "lst_day_k": None if m == 7 else 290.0, "lst_night_k": 260.0, "polar_night": False,
                           "burned_pct": None,
                           "missing_reason": json.dumps({"burned_pct": "outside-mcd64a1-tiles",
                                                         **({"lst_day_k": "too-few-lst-pixels"} if m == 7 else {})})}
    ctx = {
        A: {"h3": A, "access_min_median": 95.0, "access_min_p10": 60.0, "airport_km": 85.2, "protected_pct": None,
            "eonet_dustHaze_events": 1, **{f"eonet_{c}_events": 0 for c in EONET_CATEGORIES if c != "dustHaze"},
            "missing_reason": json.dumps({"protected_pct": "licence-restricted"})},
    }
    events = {A: [{"h3": A, "event_id": "SYN_1", "category": "dustHaze", "title": "SYNTHETIC dust event",
                   "start_date": "2023-07-04T00:00:00Z", "source_url": "https://example.org/syn1"}]}
    return Tables(cells, monthly, ctx, events, [{"path": "synthetic", "sha256": "0" * 64}])


class RequestTests(unittest.TestCase):
    def test_example_round_trips(self):
        q = to_query(EXAMPLE)
        self.assertEqual(q, "body=mars&obj=OP-5LM&cat=robotic-mobility-navigation&type=robotic&months=6-8&days=14&team=6"
                            "&lim=access:240,protected:0&must=terrain,surfaceMaterial&sort=terrain&top=20"
                            f"&pins={A},{B}")
        self.assertEqual(parse_query("?" + q), EXAMPLE)

    def test_round_trip_edge_cases(self):
        r = {**EXAMPLE, "months": {"start": 11, "end": 2}, "top": None, "nice": ["thermal"],
             "limits": {"slope": 7.5, "airport": 120},
             "bandEdits": [{"dimension": "terrain", "lo": 0, "hi": 10, "hiStrict": True}, {"dimension": "thermal", "lo": 180.25, "hi": 250}]}
        self.assertEqual(parse_query(to_query(r)), r)

    def test_rejects_unknown_and_repeated_keys(self):
        with self.assertRaises(ValueError):
            parse_query(to_query(EXAMPLE) + "&weights=terrain:0.7")
        with self.assertRaises(ValueError):
            parse_query(to_query(EXAMPLE) + "&body=moon")
        with self.assertRaises(ValueError):
            parse_query("body=mars&obj=OP-5LM&type=robotic")  # no months

    def test_success_criteria_not_in_url(self):
        with self.assertRaises(ValueError):
            to_query({**EXAMPLE, "successCriteria": [{"dimension": "terrain", "text": "x"}]})

    def test_month_window_wraps(self):
        self.assertEqual(months_in_window({"start": 6, "end": 8}), [6, 7, 8])
        self.assertEqual(months_in_window({"start": 11, "end": 2}), [11, 12, 1, 2])
        self.assertEqual(months_in_window({"start": 5, "end": 5}), [5])


class LogisticsTests(unittest.TestCase):
    def test_limits_unknown_is_never_fail(self):
        t = synthetic()
        out = {l["limit"]: l for l in limits(t, A, EXAMPLE)}
        self.assertEqual(out["access"]["outcome"], "pass")
        self.assertEqual(out["protected"]["outcome"], "unknown")
        self.assertEqual(out["protected"]["reason"]["code"], "licence-restricted")
        slope = limits(t, A, {**EXAMPLE, "limits": {"slope": 5}})[0]
        self.assertEqual((slope["value"], slope["outcome"]), (6.2, "fail"))
        unknown_slope = limits(t, B, {**EXAMPLE, "limits": {"slope": 5}})[0]
        self.assertEqual(unknown_slope["outcome"], "unknown")
        self.assertEqual(unknown_slope["reason"]["code"], "no-dem-tile")

    def test_logistics_values_and_notes(self):
        lg = logistics(synthetic(), A, EXAMPLE)
        self.assertEqual(lg["accessMinMedian"], {"value": 95.0, "unit": "min"})
        self.assertIsNone(lg["protectedPct"]["value"])
        self.assertIn("reason", lg["protectedPct"])
        self.assertEqual(lg["notes"], ["About 1.6 h from the nearest city, nearest paved-runway airport 85 km away, protected-land share unknown."])
        self.assertTrue(all(c["answer"] is None and c["from"] == "scientist" for c in lg["checklist"]))

    def test_no_context_row_is_all_unknown(self):
        lg = logistics(synthetic(), B, EXAMPLE)
        self.assertTrue(all(lg[k]["value"] is None and lg[k]["reason"]["code"] == "no-row-for-hexagon"
                            for k in ("accessMinMedian", "accessMinP10", "airportKm", "protectedPct")))


class RiskTests(unittest.TestCase):
    def test_eonet_rows_and_disclaimer(self):
        rk = risks(synthetic(), A, EXAMPLE)
        self.assertIn("not that none happened", rk["eonetDisclaimer"])
        eonet = {r["hazard"]: r for r in rk["rows"] if r["kind"] == "eonet"}
        self.assertEqual(set(eonet), set(EONET_CATEGORIES))
        self.assertEqual(eonet["dustHaze"]["eventsRecorded"], 1)
        self.assertEqual(eonet["dustHaze"]["events"], [{"eonetId": "SYN_1", "title": "SYNTHETIC dust event", "date": "2023-07-04", "url": "https://example.org/syn1"}])
        self.assertEqual(eonet["wildfires"]["eventsRecorded"], 0)
        self.assertFalse(any("score" in k or "rate" in k for r in rk["rows"] for k in r))

    def test_temperature_extremes_in_window(self):
        rows = {r["hazard"]: r for r in risks(synthetic(), A, EXAMPLE)["rows"]}
        self.assertEqual((rows["coldestMonth"]["month"], rows["coldestMonth"]["value"]), (8, 262.0))
        self.assertEqual((rows["hottestMonth"]["month"], rows["hottestMonth"]["value"]), (8, 308.0))
        self.assertEqual(rows["burnedArea"]["value"], (3.0 + 3.5 + 4.0) / 3)  # L1m burned_pct, months 6-8
        self.assertEqual(rows["steepTerrain"]["value"], 0.02)

    def test_unknown_month_makes_extreme_unknown(self):
        rows = {r["hazard"]: r for r in risks(synthetic(), B, EXAMPLE)["rows"]}
        self.assertIsNone(rows["hottestMonth"]["value"])
        self.assertEqual(rows["hottestMonth"]["reason"]["code"], "too-few-lst-pixels")
        self.assertEqual(rows["coldestMonth"]["value"], 260.0)
        self.assertIsNone(rows["burnedArea"]["value"])  # unknown, not 0
        self.assertEqual(rows["burnedArea"]["reason"]["code"], "outside-mcd64a1-tiles")
        eonet = [r for r in rows.values() if r["kind"] == "eonet"]
        self.assertTrue(all(r["eventsRecorded"] is None and r["reason"]["code"] == "no-row-for-hexagon" for r in eonet))


class AssembledInputTests(unittest.TestCase):
    """Tables.from_parquet reads the assembled tables (#127), not the per-source files."""

    def test_requires_assembled_sites_and_monthly(self):
        from planner.tables import input_paths
        with tempfile.TemporaryDirectory() as d:
            derived = Path(d)
            (derived / "cells-r4.parquet").write_bytes(b"")  # per-source file alone is not enough
            with self.assertRaises(FileNotFoundError) as e:
                input_paths(derived)
            self.assertIn("p0ingest.assemble", str(e.exception))
            (derived / "assembled").mkdir()
            for name in ("sites-r4.parquet", "sites-r4-monthly.parquet"):
                (derived / "assembled" / name).write_bytes(b"")
            paths = input_paths(derived)  # hazard-events is optional
            self.assertEqual(paths["sites"], derived / "assembled" / "sites-r4.parquet")
            self.assertEqual(paths["events"], derived / "assembled" / "hazard-events.parquet")

    @unittest.skipUnless(__import__("importlib").util.find_spec("pyarrow"), "pyarrow not installed (CI is stdlib only)")
    def test_reads_assembled_parquet_with_column_keyed_reasons(self):
        import pyarrow as pa
        import pyarrow.parquet as pq
        with tempfile.TemporaryDirectory() as d:
            out = Path(d) / "assembled"
            out.mkdir()
            pq.write_table(pa.table({"h3": [A, B], "dust_aod_mean": [0.12, None], "access_min_median": [95.0, None],
                                     "missing_reason": ["{}", json.dumps({"dust_aod_mean": "no-merra2-cell", "access_min_median": "outside-raster"})]}),
                           out / "sites-r4.parquet")
            pq.write_table(pa.table({"h3": [A] * 12, "month": list(range(1, 13)), "burned_pct": [1.0] * 12,
                                     "missing_reason": ["{}"] * 12}), out / "sites-r4-monthly.parquet")
            pq.write_table(pa.table({"h3": [A], "event_id": ["SYN_1"], "category": ["dustHaze"]}), out / "hazard-events.parquet")
            t = Tables.from_parquet(Path(d))
        self.assertIs(t.context, t.cells)  # L2 columns live in sites-r4
        self.assertEqual(t.cells[A]["dust_aod_mean"], 0.12)
        self.assertEqual(t.monthly[(A, 7)]["burned_pct"], 1.0)
        self.assertEqual([e["event_id"] for e in t.events[A]], ["SYN_1"])
        self.assertEqual([i["path"] for i in t.inputs], [f"data/snapshots/_derived/assembled/{n}.parquet"
                                                         for n in ("sites-r4", "sites-r4-monthly", "hazard-events")])
        lg = logistics(t, B, EXAMPLE)
        self.assertEqual(lg["accessMinMedian"]["reason"]["code"], "outside-raster")  # not "not-in-source"
        l3 = {"objectives": [], "trait-map": {}, "campaigns": []}
        with tempfile.TemporaryDirectory() as o:
            publish(t, l3, Path(o))
            meta = json.loads((Path(o) / "cells.json").read_text(encoding="utf-8"))
        self.assertEqual(meta["nullReasons"]["dust_aod_mean"], {"no-merra2-cell": 1})
        self.assertNotIn("not-in-source", json.dumps(meta["nullReasons"]["access_min_median"]))


class PublishTests(unittest.TestCase):
    def test_publish_is_deterministic_and_keeps_nulls(self):
        l3 = {"objectives": [{"objectiveId": "OP-5LM"}], "trait-map": {"version": 0, "rules": []}, "campaigns": []}
        with tempfile.TemporaryDirectory() as d1, tempfile.TemporaryDirectory() as d2:
            m1 = publish(synthetic(), l3, Path(d1), synthetic=True)
            m2 = publish(synthetic(), l3, Path(d2), synthetic=True)
            self.assertEqual(m1, m2)
            self.assertEqual(sorted(m1["files"]), sorted(["cells.bin", "cells.json", "campaigns.json", "objectives.json",
                                                         "trait-map.json", "monthly/monthly.json"]
                                                        + [f"monthly/{c}.bin" for c in ("lst_day_k", "lst_night_k", "lst_diurnal_k",
                                                           "sun_noon_elev_deg", "daylight_h", "polar_day", "polar_night", "dust_aod",
                                                           "burned_pct")]))
            meta = json.loads((Path(d1) / "cells.json").read_text(encoding="utf-8"))
            self.assertEqual(meta["h3"], sorted([A, B]))
            slope = dict(zip(meta["h3"], read_column(Path(d1), "slope_mean_deg")))
            self.assertAlmostEqual(slope[A], 6.2, places=5)
            self.assertIsNone(slope[B])
            self.assertEqual(meta["nullReasons"]["slope_mean_deg"], {"no-dem-tile": 1})
            self.assertEqual(meta["nullReasons"]["protected_pct"], {"licence-restricted": 1, "no-row-for-hexagon": 1})
            raw = (Path(d1) / "monthly" / "lst_day_k.bin").read_bytes()
            self.assertEqual(len(raw), 2 * 12 * 4)
            import hashlib
            for rel, digest in m1["files"].items():
                self.assertEqual(hashlib.sha256((Path(d1) / rel).read_bytes()).hexdigest(), digest)
            self.assertTrue(meta["synthetic"])

    def test_float32_rounding_is_visible(self):
        """Float32 cannot hold every float64: 6.2 comes back as 6.19999980926...
        The atlas therefore must compute verdicts from these same Float32 values,
        and golden-verdicts.json must be computed from them too (README)."""
        l3 = {"objectives": [], "trait-map": {}, "campaigns": []}
        with tempfile.TemporaryDirectory() as d:
            publish(synthetic(), l3, Path(d))
            v = dict(zip(json.loads((Path(d) / "cells.json").read_text())["h3"], read_column(Path(d), "slope_mean_deg")))[A]
        self.assertNotEqual(v, 6.2)
        self.assertTrue(math.isclose(v, 6.2, rel_tol=1e-6))


if __name__ == "__main__":
    unittest.main()
