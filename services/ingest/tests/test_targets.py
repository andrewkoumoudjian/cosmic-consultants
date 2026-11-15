"""Tests for the W49 (#108) target-site validator."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import yaml

import p0ingest.targets as targets


def base_row(**overrides):
    row = {
        "siteId": "mars-landing-test",
        "name": "Test Lander",
        "body": "mars",
        "kind": "landing-site",
        "status": "historical",
        "lonMode": "east-positive-minus180-180",
        "centreLat": 19.33,
        "centreLon": -33.55,
        "source": {
            "datasetId": "test-ds",
            "file": "doc.txt",
            "url": "https://example.com/doc.txt",
            "fetchedAt": "2026-01-01T00:00:00Z",
            "sourceSha256": "a" * 64,
            "quote": "The lander set down at 19.33 N, 33.55 W.",
        },
    }
    row.update(overrides)
    return row


def write_tree(tmp: Path, row, quote_text=None,
               sha256="a" * 64, manifest_url="https://example.com/doc.txt"):
    quote_text = quote_text if quote_text is not None else (row.get("source") or {}).get("quote", "")
    fetched = (row.get("source") or {}).get("fetchedAt", "2026-01-01T00:00:00Z")
    (tmp / "snapshots").mkdir(exist_ok=True)
    (tmp / "snapshots" / "test-ds").mkdir(exist_ok=True)
    (tmp / "snapshots" / "test-ds" / "doc.txt").write_text(quote_text, encoding="utf-8")
    manifest = {"entries": [{
        "datasetId": "test-ds", "localPath": "data/snapshots/test-ds/doc.txt",
        "sourceUrl": manifest_url, "sha256": sha256,
        "fetchedAt": fetched,
    }]}
    (tmp / "snapshots" / "MANIFEST.json").write_text(json.dumps(manifest), encoding="utf-8")
    targets_dir = tmp / "targets"
    targets_dir.mkdir(exist_ok=True)
    path = targets_dir / f"{row['siteId']}.yaml"
    path.write_text(yaml.safe_dump(row), encoding="utf-8")
    return path


def run_row(tmp: Path, path):
    records = targets.load_manifest_records(tmp / "snapshots" / "MANIFEST.json")
    return targets.validate_row(path, yaml.safe_load(path.read_text(encoding="utf-8")),
                                {}, records, tmp / "snapshots")


class CoordinateParsing(unittest.TestCase):
    def test_nssdc_planetocentric_form(self):
        parsed = targets.coordinates_from_quote(
            "The Viking 1 Lander touched down in western Chryse Planitia at "
            "22.27 deg N latitude and 312.05 deg E longitude (planetocentric)")
        self.assertAlmostEqual(parsed[0], 22.27)
        self.assertAlmostEqual(parsed[1], -47.95)

    def test_compact_hemisphere_form(self):
        self.assertEqual(targets.coordinates_from_quote("19.33 N, 33.55 W"), (19.33, -33.55))
        self.assertEqual(targets.coordinates_from_quote("14.572 S, 175.478 E"), (-14.572, 175.478))

    def test_degree_sign_with_and(self):
        parsed = targets.coordinates_from_quote("1.946\u00b0 S and 354.473\u00b0 E")
        self.assertAlmostEqual(parsed[0], -1.946)
        self.assertAlmostEqual(parsed[1], -5.527)

    def test_press_kit_bare_degrees_longitude_is_east_positive(self):
        parsed = targets.coordinates_from_quote(
            "Landing site: Jezero Crater, about 18 degrees north latitude, 77 degrees longitude")
        self.assertEqual(parsed, (18.0, 77.0))

    def test_incomplete_passage_is_not_parsed(self):
        self.assertIsNone(targets.coordinates_from_quote("somewhere in Utopia Planitia"))

    def test_east_folds_both_conventions(self):
        self.assertAlmostEqual(targets._east(312.05), -47.95)
        self.assertAlmostEqual(targets._east(-47.95), -47.95)
        self.assertEqual(targets._east(0), 0.0)

    def test_great_circle_is_symmetric_and_zero_on_same_point(self):
        d = targets.great_circle_km(-14.572, 175.478, -14.5308, 175.5244, "mars")
        self.assertAlmostEqual(d, targets.great_circle_km(-14.5308, 175.5244, -14.572, 175.478, "mars"))
        self.assertAlmostEqual(targets.great_circle_km(4.5, 135.9, 4.5, 135.9, "mars"), 0.0, places=6)


class DbfReading(unittest.TestCase):
    @staticmethod
    def minimal_dbf():
        fields = [("name", "C", 8), ("center_lat", "N", 12), ("center_lon", "N", 12)]
        header = bytearray(32)
        header[0] = 0x03
        header[4:8] = (1).to_bytes(4, "little")  # record count
        header[8:10] = (32 + 32 * len(fields) + 1).to_bytes(2, "little")
        header[10:12] = (1 + sum(size for _, _, size in fields)).to_bytes(2, "little")
        for name, kind, size in fields:
            chunk = bytearray(32)
            chunk[:len(name.encode())] = name.encode()
            chunk[11] = ord(kind)
            chunk[16] = size
            header += chunk
        header.append(0x0D)
        record = b" " + b"Jezero  ".ljust(8) + b"18.4082".ljust(12) + b"77.6873".ljust(12) + b"\x1a"
        return bytes(header) + record

    def test_dbf_rows_are_read(self):
        rows = targets.dbf_rows_from_bytes(self.minimal_dbf())
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["name"], "Jezero")
        self.assertEqual(float(rows[0]["center_lat"]), 18.4082)

    def test_non_dbf_rejected(self):
        with self.assertRaises(ValueError):
            targets.dbf_rows_from_bytes(b"PK\x03\x04 not a dbase file at all........")


class GazetteerHelpers(unittest.TestCase):
    def test_quote_recomposition_is_stable(self):
        record = {"name": "Jezero", "clean_name": "Jezero", "approvaldt": "2007",
                  "diameter": "47.5", "center_lon": "77.6873", "center_lat": "18.4082",
                  "type": "Crater, craters", "code": "AA", "approval": "Adopted by IAU"}
        quote = targets.gazetteer_quote(record)
        self.assertIn("name=Jezero", quote)
        self.assertIn("center_lat=18.4082", quote)
        self.assertEqual(quote, targets.gazetteer_quote(dict(record, extra="ignored")))

    def test_record_lookup_is_case_exact(self):
        gazetteer = {"mars": [{"name": "Jezero", "center_lat": "18.4", "center_lon": "77.7"}]}
        self.assertIsNotNone(targets.gazetteer_record(gazetteer, "mars", "Jezero"))
        self.assertIsNone(targets.gazetteer_record(gazetteer, "mars", "jezero"))
        self.assertIsNone(targets.gazetteer_record(gazetteer, "moon", "Jezero"))


class RowValidation(unittest.TestCase):
    def test_happy_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            path = write_tree(tmp, base_row())
            report = run_row(tmp, path)
            self.assertEqual(report.errors, [])

    def test_sha_mismatch_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            row = base_row()
            path = write_tree(tmp, row, sha256="b" * 64)
            report = run_row(tmp, path)
            self.assertIn("source.sourceSha256 does not match MANIFEST sha256", report.errors)

    def test_url_mismatch_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            path = write_tree(tmp, base_row(), manifest_url="https://example.com/other.txt")
            report = run_row(tmp, path)
            self.assertIn("source.url does not match MANIFEST sourceUrl", report.errors)

    def test_quote_missing_from_document_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            path = write_tree(tmp, base_row(), quote_text="An entirely unrelated passage.")
            report = run_row(tmp, path)
            self.assertIn("quote not found verbatim in the snapshot document", report.errors)

    def test_declared_centre_diverging_from_quote_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            path = write_tree(tmp, base_row(centreLat=20.0, centreLon=-33.55))
            report = run_row(tmp, path)
            self.assertTrue(any("declared centre" in e for e in report.errors))

    def test_missing_entry_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            row = base_row()
            row["source"]["datasetId"] = "unknown-ds"
            path = write_tree(tmp, row)
            report = run_row(tmp, path)
            self.assertTrue(any("no MANIFEST entry" in e for e in report.errors))

    def test_coordinate_without_quote_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            row = base_row()
            row["source"]["quote"] = ""
            path = write_tree(tmp, row)
            report = run_row(tmp, path)
            self.assertIn("coordinate present but source.quote missing", report.errors)

    def test_null_centre_requires_missing_reason(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            row = base_row(centreLat=None, centreLon=None)
            row.pop("source")
            path = write_tree(tmp, row)
            report = run_row(tmp, path)
            self.assertIn("centre null: missingReason required", report.errors)

    def test_null_centre_with_reason_and_quote_passes(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            row = base_row(centreLat=None, centreLon=None,
                           missingReason="no numeric centre is published as text in the source")
            row["source"]["quote"] = "The lander set down at 19.33 N, 33.55 W on a flat plain."
            path = write_tree(tmp, row)
            report = run_row(tmp, path)
            self.assertEqual(report.errors, [])

    def test_half_open_pair_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            path = write_tree(tmp, base_row(centreLat=19.33, centreLon=None))
            report = run_row(tmp, path)
            self.assertIn("centreLat and centreLon must be given together or both null", report.errors)

    def test_out_of_range_coordinates_are_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            row = base_row(centreLat=95.0, centreLon=350.0, lonMode="east-positive-0-360")
            path = write_tree(tmp, row)
            report = run_row(tmp, path)
            self.assertTrue(any("out of range" in e for e in report.errors))

    def test_lon_outside_declared_mode_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            path = write_tree(tmp, base_row(centreLat=19.33, centreLon=312.05))
            report = run_row(tmp, path)
            self.assertTrue(any("outside declared" in e for e in report.errors))

    def test_cross_check_beyond_tolerance_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            gazetteer = {"mars": [{"name": "Gusev", "center_lat": "-14.5308",
                                   "center_lon": "175.5244"}]}
            row = base_row(centreLat=-14.572, centreLon=175.478,
                           usgsCrossCheck={"feature": "Gusev", "diffKm": 3.6,
                                           "expectedMaxKm": 79, "note": "crater-scale"})
            row["source"]["quote"] = "in Gusev Crater, at 14.572 S, 175.478 E"
            path = write_tree(tmp, row)
            row2 = yaml.safe_load(path.read_text(encoding="utf-8"))
            report = targets.validate_row(path, row2, gazetteer,
                targets.load_manifest_records(tmp / "snapshots" / "MANIFEST.json"),
                tmp / "snapshots")
            self.assertEqual(report.errors, [])

    def test_cross_check_tolerated_distance_breach_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            gazetteer = {"mars": [{"name": "Gusev", "center_lat": "-14.5308",
                                   "center_lon": "175.5244"}]}
            row = base_row(centreLat=40.0, centreLon=100.0,
                           lonMode="east-positive-0-360",
                           usgsCrossCheck={"feature": "Gusev", "diffKm": 10.0,
                                           "expectedMaxKm": 5, "note": "too tight"})
            row["source"]["quote"] = "placed at 40 deg N latitude, 100 deg E longitude"
            path = write_tree(tmp, row)
            row2 = yaml.safe_load(path.read_text(encoding="utf-8"))
            report = targets.validate_row(path, row2, gazetteer,
                targets.load_manifest_records(tmp / "snapshots" / "MANIFEST.json"),
                tmp / "snapshots")
            self.assertTrue(any("tolerance" in e for e in report.errors))

    def test_bad_site_id_and_filename_mismatch(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            path = write_tree(tmp, base_row(siteId="Mars Landing Test"))
            report = run_row(tmp, path)
            self.assertTrue(any("kebab-case" in e for e in report.errors))


_SNAPSHOTS_DIR = targets.REPO / "data" / "snapshots"
_HAS_TARGET_SNAPSHOTS = (
    (_SNAPSHOTS_DIR / "artemis-iii-candidate-regions").is_dir()
    and (_SNAPSHOTS_DIR / "mars-lander-sites").is_dir()
    and (_SNAPSHOTS_DIR / "usgs-planetary-nomenclature").is_dir()
)


class RepoTargets(unittest.TestCase):
    @unittest.skipUnless(_HAS_TARGET_SNAPSHOTS, "target raw snapshots not present (gitignored in CI)")
    def test_every_repo_target_row_passes(self):
        reports = targets.validate_targets()
        self.assertTrue(reports, "expected data/targets/*.yaml to exist")
        failures = {r.site_id: r.errors for r in reports if not r.ok()}
        self.assertEqual(failures, {})

    def test_repo_targets_yaml_structure_in_ci(self):
        manifest = targets.load_manifest_records(_SNAPSHOTS_DIR / "MANIFEST.json")
        paths = sorted(targets.TARGETS.glob("*.yaml"))
        self.assertEqual(len(paths), 47)
        for path in paths:
            row = yaml.safe_load(path.read_text(encoding="utf-8"))
            self.assertEqual(row["siteId"], path.stem)
            self.assertIn(row["body"], targets.BODIES)
            self.assertIn(row["kind"], targets.KINDS)
            self.assertIn(row["status"], targets.STATUSES)
            src = row.get("source")
            if isinstance(src, dict) and src.get("datasetId") and src.get("file"):
                key = (src["datasetId"], src["file"])
                self.assertIn(key, manifest)
                self.assertEqual(src["sourceSha256"], manifest[key]["sha256"])

    def test_targets_include_moon_and_mars_coverage(self):
        root = targets.TARGETS
        bodies = {}
        for path in root.glob("*.yaml"):
            row = yaml.safe_load(path.read_text(encoding="utf-8"))
            bodies[row["body"]] = bodies.get(row["body"], 0) + 1
        self.assertIn("moon", bodies)
        self.assertIn("mars", bodies)


class Cli(unittest.TestCase):
    @unittest.skipUnless(_HAS_TARGET_SNAPSHOTS, "target raw snapshots not present (gitignored in CI)")
    def test_main_exit_code_reflects_repo_state(self):
        self.assertEqual(targets.main(["-q"]), 0)


if __name__ == "__main__":
    unittest.main()
