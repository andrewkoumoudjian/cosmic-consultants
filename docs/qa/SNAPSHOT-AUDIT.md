# Audit local snapshot integrity

`scripts/audit_snapshots.py` checks local payload sizes and streaming SHA-256
hashes against `data/snapshots/MANIFEST.json`. It uses Python's standard library
and never downloads, copies, repairs or writes snapshot data. It is separate
from source-QA rebuilds in #76 and per-dataset scientific validation.

```text
python scripts/audit_snapshots.py --output /existing/evidence-directory/audit.json
python scripts/audit_snapshots.py --dataset campaign-sources
python scripts/audit_snapshots.py --dataset mola-megdr --dataset lamp
python -m unittest discover -s scripts/tests -p test_audit_snapshots.py
```

Use an actual dataset ID from the manifest. `--repo` selects a checkout; the
default is the script's own checkout, regardless of your current directory.
`--manifest` selects another manifest file. Payload paths are always resolved
relative to `--repo`, not relative to the alternate manifest. Without `--output`,
the JSON report goes to stdout. An output file must be new, its parent must
already exist, and it must be outside `data/snapshots`.

| Overall result | Exit code | Meaning |
|---|---|---|
| verified | 0 | Every selected entry has valid common metadata and local bytes matching the recorded size/hash |
| failed | 1 | Invalid metadata/path, duplicate selected path, unreadable payload, or size/hash mismatch; inspect row errors |
| partial | 2 | No detected integrity error, but one or more selected payloads are missing or explicitly unretained |

CLI usage errors can also return 2 without an audit report. Read the report's
status and scope, not just the shell code. A failed audit can also contain
missing files; failures take precedence over partial coverage. An empty manifest
or an unknown requested dataset fails rather than producing an empty success.

The report records the manifest's own SHA-256, timestamp, selected dataset scope,
each entry's expected and observed size/hash, and coverage counts. Hashes use
bounded-memory streaming. Files whose size or modification time changes during
the check fail; freeze the input set for a reproducible audit. Concurrent writers
can still create filesystem races, so this is not a substitute for a frozen build.

Paths must stay under the checkout's `data/snapshots` tree; traversal, absolute
paths, drive/alternate-stream syntax and resolved symlink escapes are rejected.
Both slash forms in existing manifests are supported. Duplicate resolved paths
in the selected scope fail even if their declarations agree. Common metadata
requires dataset, absolute source URL, timezone-aware fetch timestamp, SHA-256,
byte count, and a licence declaration or note. No network or registry lookup
is performed to establish the truth of that declaration.

The manifest has intentionally omitted local copies too: explicit `localPath:
null`, `bytes: null` and a licence note are reported as **unretained**, not as
corrupt or verified. Streamed/deleted raw payloads whose paths remain recorded
are **missing** on this machine. A clean Git checkout usually lacks most raw
files; its audit therefore remains partial. This says nothing about a Drive
mirror's availability or integrity.

Licence declarations and `licenseVerified` are copied as recorded. A matching
hash never upgrades an unverified licence, grants permission to redistribute,
or establishes scientific quality. The auditor does not check derived tables,
quote fidelity, feature coverage, physical units, source QA masks, target bands,
field safety or proof/runtime conformance. Keep the manifest hash, report and
the exact dataset scope with any integrity claim; a selected-subset success
does not certify the rest of the manifest.
