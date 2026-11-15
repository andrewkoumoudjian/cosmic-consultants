# Local checks with saved evidence

Use `scripts/local_checks.py` to save local command logs while hosted CI is
unavailable. It does not fix the account issue in #139 or turn a local result
into a hosted CI pass. No packages, tools, datasets or caches are installed.

From a checkout with dependencies already prepared:

```text
python scripts/local_checks.py --group json
python scripts/local_checks.py --group contracts --group atlas --keep-going
python scripts/local_checks.py --group ingest --python /path/to/prepared/python
python scripts/local_checks.py --group lean --timeout 7200
python scripts/local_checks.py --group atlas --dry-run
python -m unittest discover -s scripts/tests -p test_local_checks.py
```

`--python` accepts an executable path, not a shell command. On Windows, use
the path to the prepared virtual environment's `Scripts/python.exe`.
`--repo` selects another checkout; by default the script uses its own checkout,
regardless of your current directory. `--output` must name a new or empty
directory. Without it, a new system-temp directory is created and printed.
Copy that directory to your review evidence location if it must survive temp cleanup.

| Group | Commands/checks | Environment to prepare first |
|---|---|---|
| json (default) | Parse top-level contracts, fixtures and envelopes as JSON; not schema validation | Python standard library |
| contracts | `python scripts/validate_contracts.py --self-test` | Validator dependencies pinned in `.github/workflows/ci.yml` |
| atlas | `npm run build`, `npm test` if the checkout defines it, `npm run check:mock` | Node/npm and atlas dependencies from its lockfile (`npm ci` separately) |
| ingest | unittest discovery in `services/ingest/tests`, plain and `-O` | Prepared ingest environment per its pyproject and CI workflow |
| lean | sorry/admit text scan, `lake build`, `lake env lean Analog/Audit.lean` | elan/Lake, pinned `proofs/lean-toolchain` and Mathlib/cache already prepared |

The runner is based on `.github/workflows/{ci,atlas,ingest}.yml` at main
`e4925899150634819a4a170202e15b7b5723b9e7`. It records current workflow hashes;
it does not interpret arbitrary YAML or promise to follow future workflow edits.
Compare the planned commands with current workflows before citing parity. The
optional atlas test also covers branches that add a package test script.

Each step has its own merged stdout/stderr log. `receipt.json` records the
checkout revision/tree status, runner hash, local Python/platform, workflow
hashes, selected groups, commands, working directories, actual child return
codes, log hashes, timing and statuses. Dependency versions are **not** verified;
attach your package/tool version output separately. A dirty tree is recorded,
not silently treated as the clean commit. Local operating systems and installed
dependencies can differ from CI's Ubuntu/Python/Node versions.

The runner stops after the first failure unless `--keep-going` is set. Later
steps then say `not-run`; unselected groups are not tested. A child failure,
missing executable, timeout or invalid audit makes the runner exit 1; the
receipt preserves the child's own return code separately. A timeout/missing
command has no invented process return code. Timeout handling terminates the
direct child; descendant tools may need manual cleanup.

For Lean, a successful process alone is insufficient: the audit must emit
theorem lines, all using only `propext`, `Classical.choice`, `Quot.sound`, or
no axioms. Empty output, warnings, unexpected text or custom axioms fail the
audit gate even if Lean returns 0. The source scan is a text check including
comments, matching CI's intent; it is not a proof or an axiom audit by itself.
The owner still reruns the pinned build and audit before accepting a proof.

Keep failed receipts. If the runner is interrupted, its last written receipt
stays `running`; that is incomplete evidence, never a pass. Review logs before
posting them: the runner does not redact what invoked tools choose to print.
No environment-variable dump or credential collection is performed.

In a PR, name the groups actually run, attach their receipt/logs, state the
environment differences and list everything unrun or skipped by underlying
tests. `pass` means those selected commands and gates passed locally; it does
not certify dataset accuracy, the scientific bands, the full product workflow,
or hosted CI. Review the underlying unittest summary for source-dependent skips.
