import unittest
import polars as pl

from p0ingest.assemble import Build


class AssemblyValidation(unittest.TestCase):
    def test_updated_doc_categories_and_full_metric_menus_are_retained(self):
        import yaml
        from p0ingest.assemble import REPO
        build = object.__new__(Build)
        build.reg = yaml.safe_load((REPO / "data/pipeline/columns.yaml").read_text())
        report = build.coverage(pl.DataFrame(), pl.DataFrame())
        self.assertEqual(len(report["categories"]), 19)
        self.assertEqual(report["testCatalog"]["selection"]["maxMetrics"], 8)
        for category in ["robotic-mobility-navigation", "geological-exploration-sampling"]:
            self.assertEqual(len(report["categories"][category]["detailedMetricMenuText"]), 12)
            self.assertEqual(report["categories"][category]["dataSupportStatus"], "not-established")
        self.assertEqual(report["planetaryAssemblyStatus"].split(":")[0], "not-built")

    def test_campaign_quotes_and_context_period_survive_assembly(self):
        import json
        import yaml
        from p0ingest.assemble import REPO
        campaigns = [yaml.safe_load(p.read_text()) for p in sorted((REPO / "data/campaigns").glob("*.yaml"))]
        sites = pl.DataFrame({"h3": sorted({c["site"]["h3r4"] for c in campaigns})}).with_columns(pl.lit("{}").alias("missing_reason"))
        build = object.__new__(Build)
        build.report = {"checks": []}
        build.fails = 0
        rows = {r["campaign_id"]: r for r in build.campaigns(sites).to_dicts()}
        for campaign in campaigns:
            row = rows[campaign["campaignId"]]
            self.assertEqual(json.loads(row["source_records"]), campaign["sources"])
            self.assertEqual(json.loads(row["constraint_evidence"]), campaign["publishedConstraints"])
            self.assertEqual(json.loads(row["outcome_evidence"]), campaign["outcome"])
            self.assertEqual(row["hex_feature_period"], "2023 reference context; not measured campaign conditions")

    def test_invalid_month_is_rejected_with_unchanged_row_count(self):
        import tempfile
        from pathlib import Path
        from unittest.mock import patch
        import p0ingest.assemble as assembly
        with tempfile.TemporaryDirectory() as tmp:
            frame = pl.DataFrame({"h3": ["a"] * 12, "month": list(range(1, 12)) + [13]})
            frame.write_parquet(Path(tmp) / "monthly.parquet")
            build = object.__new__(Build)
            build.report = {"inputs": {}, "checks": []}
            build.fails = 0
            build.master = pl.DataFrame({"h3": ["a"]})
            build._cache = {}
            build.reg = {"sources": {"monthly": {"path": "monthly.parquet", "key": ["h3", "month"]}}}
            with patch.object(assembly, "DERIVED", Path(tmp)), patch.object(assembly, "REPO", Path(tmp)):
                build.source("monthly")
            self.assertEqual(build.fails, 1)

    def test_feature_inventory_cannot_drop_a_required_feature(self):
        from p0ingest.assemble import feature_coverage
        features = [{"feature_id": "slope_5m", "earth_match": "direct"}]
        with self.assertRaises(ValueError):
            feature_coverage(features, {}, {})

    def test_related_column_does_not_complete_a_feature(self):
        from p0ingest.assemble import feature_coverage
        features = [{"feature_id": "slope_5m", "earth_match": "direct"}]
        result = feature_coverage(features, {"slope_5m": {"relatedColumns": ["sites.slope_mean_deg"], "notes": "wrong scale"}},
                                  {"sites": pl.DataFrame({"slope_mean_deg": [2.0]})})
        self.assertFalse(result[0]["implemented"])
        self.assertEqual(result[0]["preparationState"], "partial-inputs")

    def test_reason_text_is_not_rewritten(self):
        import json
        from p0ingest.assemble import _reasons_expr
        reason = 'cloud,, mask "unknown"\nnext'
        df = pl.DataFrame({"value": [None], "why": [json.dumps({"thermal": reason})]},
                          schema_overrides={"value": pl.Float64})
        text = df.select((pl.lit("{") + _reasons_expr("why", [("value", "value", "thermal")]) + pl.lit("}")).alias("r"))["r"][0]
        self.assertEqual(json.loads(text), {"value": reason})

    def test_one_null_value_is_a_mismatch(self):
        build = object.__new__(Build)
        build.report = {"inputs": {}, "checks": [], "skipped": []}
        build.fails = 0
        build.master = pl.DataFrame({"h3": ["a"], "cell": [0]})
        build.reg = {"tables": {"x": {"key": ["h3"], "columns": [
            {"name": "value", "from": "source.value", "trait": "thermal", "status": "active"}]}}}
        # The source method returns a changed second read, simulating a changed
        # source value after assembly. This tests the actual equality guard.
        source = pl.DataFrame({"h3": ["a"], "value": [None], "missing_reason": ['{"thermal":"absent"}']},
                              schema_overrides={"value": pl.Float64})
        calls = 0
        original_select = pl.DataFrame.select
        def changed_select(frame, *args, **kwargs):
            nonlocal calls
            result = original_select(frame, *args, **kwargs)
            if any(c.startswith("__src_") for c in result.columns):
                calls += 1
                return result.with_columns(pl.lit(1.0).alias("__src_value"))
            return result
        from unittest.mock import patch
        build.source = lambda sid: source
        with patch.object(pl.DataFrame, "select", changed_select):
            build.table("x")
        self.assertEqual(calls, 1)
        self.assertGreater(build.fails, 0)


if __name__ == "__main__":
    unittest.main()


class EvidenceDescriptors(unittest.TestCase):
    """Issue #111: ideas adopted from deferred ADR-0004 (measurement kind/support, claim-specific
    independence, non-finite rejection, dated absence scope). No scoring, ranking or Pareto."""

    def setUp(self):
        import yaml
        from p0ingest.assemble import REPO, load_evidence
        self.reg = yaml.safe_load((REPO / "data/pipeline/columns.yaml").read_text())
        self.ev = load_evidence()

    def test_every_registry_column_has_a_valid_descriptor(self):
        from p0ingest.assemble import evidence_problems
        self.assertEqual(evidence_problems(self.reg, self.ev), [])

    def test_missing_unknown_invalid_and_synthetic_are_rejected(self):
        import copy
        from p0ingest.assemble import evidence_problems
        ev = copy.deepcopy(self.ev)
        del ev["columns"]["albedo_ws_sw"]
        ev["columns"]["not_a_column"] = {"kind": "observed", "support": "x", "family": "y"}
        ev["columns"]["lat"]["kind"] = "guess"
        ev["columns"]["lon"]["support"] = " "
        ev["columns"]["slope_mean_deg"]["family"] = ""
        text = "\n".join(evidence_problems(self.reg, ev))
        for needle in ("albedo_ws_sw: no evidence descriptor", "not_a_column: descriptor names no registry column",
                       "lat: kind 'guess'", "lon: empty support", "slope_mean_deg: empty family"):
            self.assertIn(needle, text)
        ev = copy.deepcopy(self.ev)
        ev["kinds"].append("synthetic")
        self.assertIn("synthetic", "\n".join(evidence_problems(self.reg, ev)))

    def test_nan_and_infinity_are_not_nulls_and_are_counted(self):
        from p0ingest.assemble import nonfinite_counts
        df = pl.DataFrame({"a": [1.0, None, float("nan")], "b": [float("inf"), 2.0, -float("inf")], "c": [1, 2, 3]})
        self.assertEqual(nonfinite_counts(df), {"a": 1, "b": 2})
        self.assertEqual(nonfinite_counts(pl.DataFrame({"a": [1.0, None]})), {})

    def test_source_gap_features_carry_a_dated_absence_scope_and_never_a_claim_of_absence(self):
        import csv
        import yaml
        from p0ingest.assemble import REPO, feature_coverage
        prep = yaml.safe_load((REPO / "data/pipeline/feature-preparation.yaml").read_text())
        with (REPO / "research/features/landing_site_features.csv").open(encoding="utf-8", newline="") as f:
            feats = list(csv.DictReader(f))
        out = feature_coverage(feats, prep["features"], {}, prep["absenceScope"])
        gaps = [x for x in out if x["preparationState"] == "source-gap"]
        self.assertTrue(gaps)
        for g in gaps:
            self.assertRegex(g["absenceScope"]["searchedOn"], r"^\d{4}-\d{2}-\d{2}$")
            self.assertIn("not evidence that none exists", g["absenceScope"]["statement"])
        with self.assertRaises(ValueError):
            feature_coverage(feats, prep["features"], {})
        self.assertTrue(all("absenceScope" not in x for x in out if x["preparationState"] != "source-gap"))

    def test_coverage_exposes_kind_family_and_the_not_corroboration_note(self):
        import yaml
        from p0ingest.assemble import REPO
        build = object.__new__(Build)
        build.reg = yaml.safe_load((REPO / "data/pipeline/columns.yaml").read_text())
        report = build.coverage(pl.DataFrame(), pl.DataFrame())
        self.assertIn("Family counts are discovery hints only", report["evidenceNote"])
        self.assertEqual(report["columnEvidence"]["regolith_thick_m"]["kind"], "modeled")
        backed = [b for c in report["categories"].values() for t in c["traits"].values() for b in t["columns"]]
        self.assertTrue(all(b["kind"] and b["family"] for b in backed))
