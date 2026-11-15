"""Exercise actual child-process failures and audit-output rejection."""
import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "local_checks.py"
spec = importlib.util.spec_from_file_location("local_checks", SCRIPT)
checks = importlib.util.module_from_spec(spec)
spec.loader.exec_module(checks)


class LocalChecksTests(unittest.TestCase):
    def child(self, code, audit=False, timeout=10):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            step = {"name": "probe", "group": "test", "command": [sys.executable, "-c", code],
                    "cwd": str(root), "audit": audit}
            result = checks.run_step(step, root, timeout)
            return result, (root / "probe.log").read_text(encoding="utf-8")

    def test_failure_keeps_real_returncode_and_both_streams(self):
        result, log = self.child("import sys; print('out'); print('err',file=sys.stderr); sys.exit(7)")
        self.assertEqual((result["status"], result["returncode"]), ("fail", 7))
        self.assertIn("out", log)
        self.assertIn("err", log)
        self.assertEqual(len(result["logSha256"]), 64)

    def test_failed_lean_process_cannot_pass_on_good_looking_output(self):
        result, _ = self.child("import sys; print(\"'T' depends on axioms: [propext]\"); sys.exit(9)", audit=True)
        self.assertEqual((result["status"], result["returncode"]), ("fail", 9))

    def test_empty_or_nonstandard_audit_is_not_success(self):
        for code in ("pass", "print(\"'T' depends on axioms: [sorryAx]\")", "print('unexpected warning')"):
            with self.subTest(code=code):
                result, _ = self.child(code, audit=True)
                self.assertEqual((result["status"], result["returncode"]), ("fail", 0))
                self.assertIn("error", result)

    def test_standard_audit_is_accepted(self):
        result, _ = self.child("print(\"'T' depends on axioms: [propext, Classical.choice, Quot.sound]\"); print(\"'U' does not depend on any axioms\")", audit=True)
        self.assertEqual(result["status"], "pass")

    def test_timeout_retains_partial_output_without_inventing_returncode(self):
        result, log = self.child("import time; print('checkpoint',flush=True); time.sleep(10)", timeout=0.5)
        self.assertEqual(result["status"], "timeout")
        self.assertIsNone(result["returncode"])
        self.assertIn("checkpoint", log)

    def test_missing_command_is_error(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            result = checks.run_step({"name": "missing", "command": [str(root / 'no-such-program')],
                                     "cwd": str(root)}, root, 10)
            self.assertEqual(result["status"], "error")
            self.assertIsNone(result["returncode"])

    def test_cli_records_failure_and_preserves_existing_evidence(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / ".github/workflows").mkdir(parents=True)
            (root / ".github/workflows/ci.yml").write_text("name: test")
            (root / "contracts").mkdir()
            (root / "contracts/bad.json").write_text("{broken")
            output = root / "evidence"
            cmd = [sys.executable, str(SCRIPT), "--repo", str(root), "--output", str(output)]
            first = subprocess.run(cmd, capture_output=True, text=True)
            self.assertEqual(first.returncode, 1, first.stderr)
            before = (output / "receipt.json").read_bytes()
            receipt = json.loads(before)
            self.assertEqual(receipt["status"], "fail")
            self.assertEqual(receipt["results"][0]["returncode"], 1)
            second = subprocess.run(cmd, capture_output=True, text=True)
            self.assertEqual(second.returncode, 2)
            self.assertEqual((output / "receipt.json").read_bytes(), before)

    def test_cli_fail_fast_and_keep_going_never_hide_failure(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / ".github/workflows").mkdir(parents=True)
            (root / ".github/workflows/ci.yml").write_text("name: test")
            (root / "contracts").mkdir()
            (root / "contracts/bad.json").write_text("{broken")
            (root / "scripts").mkdir()
            (root / "scripts/validate_contracts.py").write_text("print('fixture validator ran')")
            for keep in (False, True):
                with self.subTest(keep=keep):
                    output = root / ("continued" if keep else "stopped")
                    cmd = [sys.executable, str(SCRIPT), "--repo", str(root), "--output", str(output),
                           "--group", "json", "--group", "contracts"]
                    if keep:
                        cmd.append("--keep-going")
                    child = subprocess.run(cmd, cwd=root.parent, capture_output=True, text=True)
                    self.assertEqual(child.returncode, 1, child.stderr)
                    receipt = json.loads((output / "receipt.json").read_text())
                    self.assertEqual(receipt["status"], "fail")
                    self.assertEqual(receipt["results"][1]["status"], "pass" if keep else "not-run")
                    if keep:
                        self.assertIn("fixture validator ran", (output / "contracts-self-test.log").read_text())

    def test_dry_run_writes_no_evidence_or_checks(self):
        with tempfile.TemporaryDirectory() as folder:
            output = Path(folder) / "unused"
            child = subprocess.run([sys.executable, str(SCRIPT), "--dry-run", "--output", str(output)],
                                   cwd=folder, capture_output=True, text=True)
            self.assertEqual(child.returncode, 0, child.stderr)
            self.assertEqual(json.loads(child.stdout)[0]["name"], "json-syntax")
            self.assertFalse(output.exists())

    def test_engine_cli_runs_both_modes_from_engine_directory(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            workflows = root / ".github/workflows"
            workflows.mkdir(parents=True)
            (workflows / "ci.yml").write_text("name: fixture")
            engine_workflow = workflows / "engine.yml"
            engine_workflow.write_text("name: engine fixture")
            tests = root / "services/engine/tests"
            tests.mkdir(parents=True)
            (tests / "test_probe.py").write_text(
                "import sys, unittest\nfrom pathlib import Path\n"
                "class Probe(unittest.TestCase):\n"
                " def test_context(self):\n"
                "  print('optimization='+str(sys.flags.optimize))\n"
                "  self.assertEqual(Path.cwd().name, 'engine')\n"
            )
            output = root / "evidence"
            child = subprocess.run([sys.executable, str(SCRIPT), "--repo", str(root), "--group", "engine",
                                    "--output", str(output)], cwd=root.parent, capture_output=True, text=True)
            self.assertEqual(child.returncode, 0, child.stderr + child.stdout)
            receipt = json.loads((output / "receipt.json").read_text())
            self.assertEqual([r["status"] for r in receipt["results"]], ["pass", "pass"])
            self.assertEqual(receipt["workflows"]["engine.yml"],
                             checks.hashlib.sha256(engine_workflow.read_bytes()).hexdigest())
            self.assertIn("optimization=0", (output / "engine.log").read_text())
            self.assertIn("optimization=1", (output / "engine-optimized.log").read_text())


if __name__ == "__main__":
    unittest.main()
