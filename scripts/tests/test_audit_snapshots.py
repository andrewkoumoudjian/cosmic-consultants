import hashlib
import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "audit_snapshots.py"
spec = importlib.util.spec_from_file_location("audit_snapshots", SCRIPT)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class AuditTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.snap = self.root / "data/snapshots"
        self.snap.mkdir(parents=True)
        self.payload = self.snap / "example.bin"
        self.payload.write_bytes(b"abcd")
        self.entry = {"datasetId": "fixture", "sourceUrl": "https://example.test/data",
                      "fetchedAt": "2026-11-14T00:00:00Z", "sha256": hashlib.sha256(b"abcd").hexdigest(),
                      "bytes": 4, "localPath": "data/snapshots/example.bin", "license": "test-only",
                      "licenseVerified": False}
        self.manifest = self.snap / "MANIFEST.json"

    def audit(self, entries=None, datasets=None):
        self.manifest.write_text(json.dumps({"entries": [self.entry] if entries is None else entries}))
        before = self.manifest.read_bytes()
        result = module.audit(self.root, self.manifest, datasets)
        self.assertEqual(self.manifest.read_bytes(), before)
        return result

    def test_verified_does_not_upgrade_licence_flag(self):
        result = self.audit()
        self.assertEqual(result["status"], "verified")
        self.assertFalse(result["entries"][0]["licenseVerified"])
        self.assertEqual(self.payload.read_bytes(), b"abcd")

    def test_same_size_corruption_is_detected(self):
        self.payload.write_bytes(b"wxyz")
        result = self.audit()
        self.assertEqual(result["counts"]["mismatch"], 1)
        self.assertIn("SHA-256 differs from manifest", result["entries"][0]["errors"])

    def test_size_mismatch_is_detected(self):
        self.entry["bytes"] = 5
        self.assertIn("byte size differs from manifest", self.audit()["entries"][0]["errors"])

    def test_missing_is_partial(self):
        self.entry["localPath"] = "data/snapshots/missing.bin"
        self.assertEqual(self.audit()["status"], "partial")

    def test_intentionally_unretained_is_partial(self):
        self.entry.update(localPath=None, bytes=None, licenseNote="No local copy retained; reuse terms unknown")
        result = self.audit()
        self.assertEqual(result["status"], "partial")
        self.assertEqual(result["counts"]["unretained"], 1)

    def test_bad_paths_are_invalid(self):
        for path in ("data/snapshots/../outside", "/data/snapshots/a", "C:\\data\\snapshots\\a",
                     "data/snapshots/a:stream", "other/a", "\\\\host\\share\\a"):
            with self.subTest(path=path):
                self.entry["localPath"] = path
                self.assertEqual(self.audit()["status"], "failed")

    def test_symlink_cannot_escape_snapshot_directory(self):
        outside = self.root / "outside.bin"
        outside.write_bytes(b"abcd")
        link = self.snap / "link.bin"
        try:
            link.symlink_to(outside)
        except (OSError, NotImplementedError):
            self.skipTest("OS does not allow creation of test symlinks")
        self.entry["localPath"] = "data/snapshots/link.bin"
        self.assertEqual(self.audit()["status"], "failed")

    def test_duplicate_normalized_paths_are_invalid(self):
        other = {**self.entry, "localPath": "data\\snapshots\\example.bin"}
        self.assertEqual(self.audit([self.entry, other])["status"], "failed")

    def test_empty_or_unknown_selection_never_passes(self):
        self.assertEqual(self.audit([])["status"], "failed")
        self.assertEqual(self.audit(datasets={"no-such-dataset"})["status"], "failed")
        invalid = {**self.entry, "datasetId": ["fixture"]}
        self.assertEqual(self.audit([invalid], datasets={"fixture"})["status"], "failed")

    def test_metadata_is_validated(self):
        for key, value in (("sha256", "bad"), ("bytes", True), ("sourceUrl", "relative"),
                           ("fetchedAt", "2026-11-14"), ("datasetId", None)):
            with self.subTest(key=key):
                entry = {**self.entry, key: value}
                self.assertEqual(self.audit([entry])["status"], "failed")

    def test_cli_keeps_partial_exit_and_refuses_overwrite(self):
        self.entry["localPath"] = "data/snapshots/missing.bin"
        self.audit()
        output = self.root / "report.json"
        cmd = [sys.executable, str(SCRIPT), "--repo", str(self.root), "--output", str(output)]
        first = subprocess.run(cmd, capture_output=True, text=True)
        self.assertEqual(first.returncode, 2, first.stderr)
        before = output.read_bytes()
        self.assertEqual(json.loads(before)["status"], "partial")
        second = subprocess.run(cmd, capture_output=True, text=True)
        self.assertEqual(second.returncode, 1)
        self.assertEqual(output.read_bytes(), before)


if __name__ == "__main__":
    unittest.main()
