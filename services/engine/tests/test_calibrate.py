"""W15 calibration runner tests. Site values are the invented synthetic fixtures
from test_engine; they test the bookkeeping, not any real site."""
import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from test_engine import synthetic, A, B  # noqa: E402

ROOT = Path(__file__).resolve().parents[3]
OUTSIDE = "8400001ffffffff"

EXP = {
    "version": 1, "status": "frozen",
    "variants": {"shipped": {}, "bandsOnly": {"OP-5LM": {"must": ["surfaceMaterial"], "nice": ["terrain", "dustProcess", "thermal"]}}},
    "grid": [{"objectiveId": "OP-5LM", "variant": "shipped", "expected": {"matches": 0, "paretoLayered": 0}}],
    "campaigns": [
        {"campaignId": "site-a", "run": True, "mappingBasis": "test", "monthsBasis": "test",
         "request": {"body": "mars", "objectiveId": "OP-5LM", "missionType": "crewed", "months": {"start": 6, "end": 7}},
         "expected": {"terrain": {"verdict": "match"}, "surfaceMaterial": {"verdict": "match"},
                      "dustProcess": {"verdict": "unknown", "reason": "no-band"}},
         "expectedFunnel": {"shipped": "noMissSomeUnknown", "bandsOnly": "allMatch"}},
        {"campaignId": "site-b", "run": True, "mappingBasis": "test", "monthsBasis": "test",
         "request": {"body": "mars", "objectiveId": "OP-5LM", "missionType": "robotic", "months": {"start": 1, "end": 1}},
         "expected": {"terrain": {"verdict": "match"}, "surfaceMaterial": {"verdict": "match"}},
         "expectedFunnel": {"shipped": "noMissSomeUnknown"}},
        {"campaignId": "site-out", "run": True, "mappingBasis": "test", "monthsBasis": "test",
         "request": {"body": "mars", "objectiveId": "OP-5LM", "missionType": "crewed", "months": {"start": 1, "end": 1}},
         "expected": {"terrain": {"verdict": "match"}}, "expectedFunnel": {"shipped": "allMatch"}},
        {"campaignId": "site-skip", "run": False, "reason": "no objective fits"},
    ],
}


def write_inputs(tmp: Path, exp: dict) -> tuple[Path, Path]:
    import yaml
    camp = tmp / "campaigns"
    camp.mkdir()
    for cid, h3 in (("site-a", A), ("site-b", B), ("site-out", OUTSIDE), ("site-skip", A)):
        (camp / f"{cid}.yaml").write_text(yaml.safe_dump({"campaignId": cid, "site": {"name": cid, "h3r4": h3}}))
    path = tmp / "exp.yaml"
    path.write_text(yaml.safe_dump(exp))
    return path, camp


class CalibrationTests(unittest.TestCase):
    def setUp(self):
        from planner.publish import load_l3
        self.l3 = load_l3(ROOT)
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

    def run_cal(self, exp=EXP):
        from planner.calibrate import run
        path, camp = write_inputs(Path(self.tmp.name), exp)
        return run(synthetic(), self.l3, path, camp)

    def traits(self, result, cid, variant):
        c = next(c for c in result["campaigns"] if c["campaignId"] == cid)
        return {t["dimension"]: t for t in c["variants"][variant]["traits"]}, c["variants"][variant]["funnel"]

    def test_disagreements_are_kept_with_gap(self):
        res = self.run_cal()
        traits, funnel = self.traits(res, "site-a", "shipped")
        # Synthetic A has slope 6.2 > 5: expected match, observed miss.
        self.assertEqual(traits["terrain"]["observed"], "miss")
        self.assertFalse(traits["terrain"]["agrees"])
        self.assertAlmostEqual(traits["terrain"]["gap"], 1.2, places=5)
        self.assertTrue(traits["surfaceMaterial"]["agrees"])
        self.assertTrue(traits["dustProcess"]["agrees"])
        self.assertIsNone(traits["thermal"]["agrees"])  # nothing frozen for it
        self.assertTrue(funnel["agrees"])  # terrain is nice under shipped priorities
        _, f2 = self.traits(res, "site-a", "bandsOnly")
        self.assertEqual(f2["observed"], "allMatch")

    def test_missing_observation_is_unknown_not_match(self):
        res = self.run_cal()
        traits, funnel = self.traits(res, "site-b", "shipped")
        self.assertEqual(traits["terrain"]["observed"], "unknown")
        self.assertEqual(traits["terrain"]["reason"], "missing-observation")
        self.assertFalse(traits["terrain"]["agrees"])
        self.assertEqual(traits["surfaceMaterial"]["observed"], "miss")  # 40.5 < 50
        self.assertEqual(funnel["observed"], "someMiss")
        self.assertFalse(funnel["agrees"])

    def test_outside_grid_and_not_run_are_reported(self):
        res = self.run_cal()
        by = {c["campaignId"]: c for c in res["campaigns"]}
        self.assertEqual(by["site-out"]["outcome"], "site-outside-grid")
        rows = by["site-out"]["variants"]["shipped"]["traits"]
        self.assertEqual([(r["dimension"], r["agrees"], r["unresolved"]) for r in rows], [("terrain", False, True)])
        self.assertEqual(res["tally"]["campaignsNotEvaluated"], 1)
        self.assertEqual(res["tally"]["campaignsRun"], 2)
        self.assertEqual(by["site-skip"], {"campaignId": "site-skip", "run": False, "reason": "no objective fits"})
        self.assertEqual(res["tally"]["campaignsNotRun"], 1)

    def test_grid_and_tally(self):
        res = self.run_cal()
        g = res["grid"][0]
        self.assertEqual(g["checks"]["matches"], {"expected": 0, "observed": 0, "agrees": True})
        t = res["tally"]
        self.assertEqual((t["traitExpectations"], t["traitAgree"]), (12, 4))  # a: 4 of 6, b: 0 of 4, out: 0 of 2
        self.assertEqual((t["traitUnresolved"], t["funnelUnresolved"]), (2, 1))
        self.assertEqual((t["funnelExpectations"], t["funnelAgree"]), (4, 2))

    def test_no_score_and_markdown(self):
        from planner.calibrate import markdown
        res = self.run_cal()
        text = json.dumps(res).lower()
        self.assertNotIn('"score', text)
        md = markdown(res)
        self.assertIn("not a site score", md)
        self.assertIn("**no**", md)

    def test_expectation_missing_from_engine_is_kept_as_not_held(self):
        from unittest import mock
        import planner.calibrate as cal
        real = cal.site_plan

        def drop_terrain(*args, **kwargs):
            plan = real(*args, **kwargs)
            plan["verdicts"] = [r for r in plan["verdicts"] if r["dimension"] != "terrain"]
            return plan
        with mock.patch.object(cal, "site_plan", drop_terrain):
            res = self.run_cal()
        traits, _ = self.traits(res, "site-a", "shipped")
        self.assertEqual(traits["terrain"]["observed"], "absent-from-engine")
        self.assertFalse(traits["terrain"]["agrees"])
        self.assertTrue(traits["terrain"]["unresolved"])
        self.assertEqual(res["tally"]["traitExpectations"], 12)  # denominator unchanged

    def test_duplicate_engine_dimension_fails(self):
        from unittest import mock
        import planner.calibrate as cal
        real = cal.site_plan

        def dup(*args, **kwargs):
            plan = real(*args, **kwargs)
            plan["verdicts"] = plan["verdicts"] + plan["verdicts"][:1]
            return plan
        with mock.patch.object(cal, "site_plan", dup), self.assertRaises(ValueError):
            self.run_cal()

    def test_freeze_commit_refuses_uncommitted_or_edited_file(self):
        import subprocess
        from planner.calibrate import freeze_commit
        repo = Path(self.tmp.name) / "repo"
        repo.mkdir()
        git = lambda *a: subprocess.run(["git", "-C", str(repo), *a], check=True, capture_output=True)
        git("init", "-q"); git("config", "user.email", "t@example.invalid"); git("config", "user.name", "t")
        f = repo / "exp.yaml"
        f.write_text("status: frozen\n")
        with self.assertRaises(ValueError):
            freeze_commit(repo, f)  # not committed yet
        git("add", "exp.yaml"); git("commit", "-q", "-m", "freeze")
        first = freeze_commit(repo, f)
        f.write_text("status: frozen\nedited: true\n")
        git("commit", "-q", "-am", "edit after freeze")
        with self.assertRaises(ValueError):
            freeze_commit(repo, f)  # later commit changed it, label still says frozen
        f.write_text("status: frozen\n")
        self.assertEqual(freeze_commit(repo, f), first)  # content identical to the freeze again

    def test_unfrozen_expectations_are_refused(self):
        exp = copy.deepcopy(EXP)
        exp["status"] = "draft"
        with self.assertRaises(ValueError):
            self.run_cal(exp)


class FrozenFileTests(unittest.TestCase):
    def test_repo_expectations_validate_against_contract_and_engine(self):
        import yaml
        from jsonschema import Draft202012Validator
        from planner.calibrate import build_request
        from planner.publish import load_l3
        from planner.workflow import requirements
        exp = yaml.safe_load((ROOT / "data/calibration/campaign-expectations.yaml").read_text())
        self.assertEqual(exp["status"], "frozen")
        validator = Draft202012Validator(json.loads((ROOT / "contracts/plan-request.schema.json").read_text()))
        l3 = load_l3(ROOT)
        for c in exp["campaigns"]:
            self.assertTrue((ROOT / f"data/campaigns/{c['campaignId']}.yaml").exists())
            if not c["run"]:
                self.assertTrue(c["reason"])
                continue
            for variant in exp["variants"].values():
                req = build_request(c, variant)
                self.assertEqual(list(validator.iter_errors(req)), [])
                requirements(l3, req)


if __name__ == "__main__":
    unittest.main()
