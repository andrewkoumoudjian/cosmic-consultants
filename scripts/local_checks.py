#!/usr/bin/env python3
"""Run explicit local checks and retain logs; never install dependencies."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path


GROUPS = ("json", "contracts", "atlas", "ingest", "lean")
WORKFLOWS = ("ci.yml", "atlas.yml", "ingest.yml")
AUDIT_LINE = re.compile(
    r"^'[^']+' (?:depends on axioms: \[(?:(?:propext|Classical\.choice|Quot\.sound)"
    r"(?:, (?:propext|Classical\.choice|Quot\.sound))*)?\]|does not depend on any axioms)$"
)


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def audit_error(output):
    lines = output.splitlines()
    if not lines:
        return "Lean audit emitted no theorem audit results"
    if any(AUDIT_LINE.fullmatch(line) is None for line in lines):
        return "Lean audit contains unexpected output or non-standard axioms"
    return None


def internal_check(kind, root):
    if kind == "json":
        files = sorted(p for folder in ("contracts", "data/fixtures", "data/envelopes")
                       for p in (root / folder).glob("*.json"))
        if not files:
            raise ValueError("No contract/fixture/envelope JSON files found")
        for path in files:
            json.loads(path.read_text(encoding="utf-8"))
        print(f"all contract/fixture/envelope JSON parses ({len(files)} files); not schema validation")
    else:
        files = sorted((root / "proofs/Analog").rglob("*.lean"))
        if not files:
            raise ValueError("No Lean source files found")
        found = []
        for path in files:
            if path.name == "Audit.lean":
                continue
            for line, text in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
                if re.search(r"\b(?:sorry|admit)\b", text):
                    found.append(f"{path.relative_to(root)}:{line}:{text}")
        if found:
            raise ValueError("sorry/admit found:\n" + "\n".join(found))
        print("No sorry/admit tokens found outside Audit.lean (text scan, not a proof)")


def plan(root, groups, python):
    steps = []

    def add(group, name, command, cwd=root, audit=False):
        steps.append({"group": group, "name": name, "command": command,
                      "cwd": str(cwd), "audit": audit})

    script = str(Path(__file__).resolve())
    for group in groups:
        if group == "json":
            add(group, "json-syntax", [python, script, "--repo", str(root), "--internal", "json"])
        elif group == "contracts":
            add(group, "contracts-self-test", [python, "scripts/validate_contracts.py", "--self-test"])
        elif group == "atlas":
            npm = shutil.which("npm") or "npm"
            cwd = root / "apps/atlas"
            add(group, "atlas-build", [npm, "run", "build"], cwd)
            package = json.loads((cwd / "package.json").read_text(encoding="utf-8"))
            if "test" in package.get("scripts", {}):
                add(group, "atlas-tests", [npm, "test"], cwd)
            add(group, "atlas-mock", [npm, "run", "check:mock"], cwd)
        elif group == "ingest":
            for options, name in (([], "ingest"), (["-O"], "ingest-optimized")):
                add(group, name, [python, *options, "-m", "unittest", "discover", "-s",
                                  "services/ingest/tests", "-p", "test_*.py"])
        elif group == "lean":
            add(group, "lean-source-scan", [python, script, "--repo", str(root), "--internal", "lean-scan"])
            lake = shutil.which("lake") or "lake"
            add(group, "lean-build", [lake, "build"], root / "proofs")
            add(group, "lean-audit", [lake, "env", "lean", "Analog/Audit.lean"], root / "proofs", audit=True)
    return steps


def run_step(step, output, timeout):
    log = output / (step["name"] + ".log")
    result = {**step, "started": utc_now(), "log": str(log), "returncode": None}
    start = time.monotonic()
    try:
        with log.open("wb") as stream:
            child = subprocess.run(step["command"], cwd=step["cwd"], stdin=subprocess.DEVNULL,
                                   stdout=stream, stderr=subprocess.STDOUT, timeout=timeout, check=False)
        result["returncode"] = child.returncode
        result["status"] = "pass" if child.returncode == 0 else "fail"
        if child.returncode == 0 and step.get("audit"):
            error = audit_error(log.read_text(encoding="utf-8", errors="replace"))
            if error:
                result.update(status="fail", error=error)
    except subprocess.TimeoutExpired:
        result.update(status="timeout", error=f"Command exceeded {timeout} seconds")
    except OSError as exc:
        result.update(status="error", error=str(exc))
    result["finished"] = utc_now()
    result["elapsedSeconds"] = round(time.monotonic() - start, 3)
    result["logSha256"] = hashlib.sha256(log.read_bytes()).hexdigest() if log.exists() else None
    return result


def git_value(root, *args):
    try:
        result = subprocess.run(["git", "-C", str(root), *args], capture_output=True,
                                text=True, timeout=10, check=False)
        return {"returncode": result.returncode, "output": result.stdout.strip(),
                "error": result.stderr.strip()}
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {"returncode": None, "output": "", "error": str(exc)}


def write_receipt(path, receipt):
    pending = path.with_suffix(".tmp")
    pending.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    pending.replace(path)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, default=Path(__file__).resolve().parent.parent)
    parser.add_argument("--group", action="append", choices=GROUPS, help="Repeat to select groups; default: json only")
    parser.add_argument("--python", default=sys.executable, help="Python executable with dependencies already installed")
    parser.add_argument("--output", type=Path, help="New or empty directory; default: a new system-temp directory")
    parser.add_argument("--timeout", type=float, default=1800, help="Seconds per command; default: 1800")
    parser.add_argument("--keep-going", action="store_true", help="Continue after failures; overall result still fails")
    parser.add_argument("--dry-run", action="store_true", help="Print planned commands without running checks or writing logs")
    parser.add_argument("--internal", choices=("json", "lean-scan"), help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    root = args.repo.resolve()
    if not (root / ".github/workflows/ci.yml").is_file():
        parser.error("--repo must contain .github/workflows/ci.yml")
    if not args.timeout > 0 or args.timeout == float("inf"):
        parser.error("--timeout must be finite and positive")
    if args.internal:
        internal_check(args.internal, root)
        return 0
    groups = list(dict.fromkeys(args.group or ["json"]))
    steps = plan(root, groups, args.python)
    if args.dry_run:
        print(json.dumps(steps, indent=2))
        return 0
    output = args.output.resolve() if args.output else Path(tempfile.mkdtemp(prefix="cosmic-local-checks-"))
    if output.exists() and (not output.is_dir() or any(output.iterdir())):
        parser.error("--output must be new or empty; existing evidence will not be overwritten")
    output.mkdir(parents=True, exist_ok=True)
    receipt = {"formatVersion": 1, "started": utc_now(), "status": "running", "repo": str(root),
               "revision": git_value(root, "rev-parse", "HEAD"),
               "tree": git_value(root, "status", "--porcelain", "--untracked-files=normal"),
               "runnerSha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
               "runnerPython": sys.version, "platform": sys.platform, "groups": groups,
               "workflows": {}, "results": []}
    for name in WORKFLOWS:
        path = root / ".github/workflows" / name
        receipt["workflows"][name] = hashlib.sha256(path.read_bytes()).hexdigest() if path.exists() else None
    report = output / "receipt.json"
    write_receipt(report, receipt)
    print(f"Evidence: {report}", flush=True)
    failed = False
    for step in steps:
        if failed and not args.keep_going:
            receipt["results"].append({**step, "status": "not-run", "returncode": None})
        else:
            result = run_step(step, output, args.timeout)
            receipt["results"].append(result)
            print(f"{step['name']}: {result['status']} (child returncode={result['returncode']})", flush=True)
            failed = failed or result["status"] != "pass"
        write_receipt(report, receipt)
    receipt.update(status="fail" if failed else "pass", finished=utc_now())
    write_receipt(report, receipt)
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
