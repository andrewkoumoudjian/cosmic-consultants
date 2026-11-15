#!/usr/bin/env python3
"""Read-only verification of local payload bytes against a snapshot manifest."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath, PureWindowsPath
from urllib.parse import urlsplit


def digest_file(path):
    digest = hashlib.sha256()
    size = 0
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            size += len(chunk)
            digest.update(chunk)
    return size, digest.hexdigest()


def payload_path(repo, raw):
    if not isinstance(raw, str) or not raw:
        raise ValueError("localPath must be a nonempty string or explicit null")
    normalized = raw.replace("\\", "/")
    parts = PurePosixPath(normalized).parts
    if (PureWindowsPath(raw).drive or normalized.startswith("/") or
            any(p in ("..", ".") or ":" in p for p in normalized.split("/")) or
            len(parts) < 3 or parts[:2] != ("data", "snapshots")):
        raise ValueError("localPath must stay under data/snapshots without traversal or drive syntax")
    path = (repo / Path(*parts)).resolve()
    if not path.is_relative_to((repo / "data/snapshots").resolve()):
        raise ValueError("localPath resolves outside data/snapshots")
    return path


def metadata_errors(entry):
    errors = []
    for key in ("datasetId", "sourceUrl", "fetchedAt"):
        if not isinstance(entry.get(key), str) or not entry[key].strip():
            errors.append(f"{key} must be a nonempty string")
    try:
        url = urlsplit(entry.get("sourceUrl", ""))
        if url.scheme not in ("http", "https", "s3") or not url.netloc:
            errors.append("sourceUrl must be an absolute HTTP(S) or S3 URL")
    except (ValueError, TypeError, AttributeError):
        errors.append("sourceUrl is malformed")
    try:
        stamp = datetime.fromisoformat(entry.get("fetchedAt", "").replace("Z", "+00:00"))
        if stamp.tzinfo is None:
            errors.append("fetchedAt must include a timezone")
    except (ValueError, TypeError, AttributeError):
        errors.append("fetchedAt must be an ISO timestamp")
    if not isinstance(entry.get("sha256"), str) or not re.fullmatch(r"[a-fA-F0-9]{64}", entry["sha256"]):
        errors.append("sha256 must contain 64 hexadecimal characters")
    if not any(isinstance(entry.get(k), str) and entry[k].strip() for k in ("license", "licenseNote")):
        errors.append("license or licenseNote must record the declaration")
    if "licenseVerified" in entry and not isinstance(entry["licenseVerified"], bool):
        errors.append("licenseVerified must be boolean when present")
    unretained = "localPath" in entry and entry["localPath"] is None
    if unretained:
        if "bytes" not in entry or entry["bytes"] is not None:
            errors.append("an unretained payload must explicitly record bytes: null")
        if not isinstance(entry.get("licenseNote"), str) or not entry["licenseNote"].strip():
            errors.append("an unretained payload needs a licenseNote; no bytes can be verified")
    elif type(entry.get("bytes")) is not int or entry["bytes"] < 0:
        errors.append("bytes must be a nonnegative integer for retained payloads")
    return errors


def audit(repo, manifest, datasets=None):
    repo, manifest = repo.resolve(), manifest.resolve()
    raw = manifest.read_bytes()
    document = json.loads(raw)
    report = {"manifest": str(manifest), "manifestSha256": hashlib.sha256(raw).hexdigest(),
              "repo": str(repo), "checkedAt": datetime.now(timezone.utc).isoformat(),
              "scope": {"datasetIds": sorted(datasets) if datasets else "all"},
              "errors": [], "entries": []}
    entries = document.get("entries") if isinstance(document, dict) else None
    if not isinstance(entries, list) or not entries:
        report["errors"].append("manifest entries must be a nonempty list")
        entries = []
    selected = []
    for index, entry in enumerate(entries):
        if not isinstance(entry, dict):
            report["errors"].append(f"entry {index} must be an object")
        elif datasets and not isinstance(entry.get("datasetId"), str):
            report["errors"].append(f"entry {index} has an invalid datasetId; cannot establish requested scope")
        elif not datasets or entry.get("datasetId") in datasets:
            selected.append((index, entry))
    if datasets:
        present = {e.get("datasetId") for _, e in selected}
        for missing in sorted(set(datasets) - present):
            report["errors"].append(f"no entries for requested dataset: {missing}")
    seen = set()
    for index, entry in selected:
        row = {k: entry.get(k) for k in ("datasetId", "localPath", "sourceUrl", "sha256", "bytes",
                                        "license", "licenseNote", "licenseVerified")}
        row.update(index=index, errors=metadata_errors(entry))
        try:
            if entry.get("localPath") is None:
                if "localPath" not in entry:
                    row["errors"].append("localPath must be present (explicit null means unretained)")
                row["status"] = "unretained"
            else:
                path = payload_path(repo, entry["localPath"])
                key = os.path.normcase(str(path))
                if key in seen:
                    row["errors"].append("duplicate resolved localPath in selected entries")
                seen.add(key)
                if row["errors"]:
                    row["status"] = "invalid"
                elif not path.exists():
                    row["status"] = "missing"
                elif not path.is_file():
                    row.update(status="invalid", errors=["localPath is not a regular file"])
                else:
                    before = path.stat()
                    size, digest = digest_file(path)
                    after = path.stat()
                    row.update(actualBytes=size, actualSha256=digest)
                    if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
                        row["errors"].append("payload changed during audit")
                    if size != entry["bytes"]:
                        row["errors"].append("byte size differs from manifest")
                    if digest != entry["sha256"].lower():
                        row["errors"].append("SHA-256 differs from manifest")
                    row["status"] = "mismatch" if row["errors"] else "verified"
        except (OSError, ValueError, RuntimeError) as exc:
            row.update(status="invalid", errors=[*row["errors"], str(exc)])
        if row["errors"] and row["status"] == "unretained":
            row["status"] = "invalid"
        report["entries"].append(row)
    counts = Counter(row["status"] for row in report["entries"])
    report["counts"] = {key: counts[key] for key in ("verified", "missing", "unretained", "invalid", "mismatch")}
    report["selectedEntries"] = len(selected)
    failed = bool(report["errors"] or counts["invalid"] or counts["mismatch"])
    partial = bool(counts["missing"] or counts["unretained"])
    report["status"] = "failed" if failed else "partial" if partial else "verified"
    report["meaning"] = "Local byte integrity only; not licence approval, source quality or scientific acceptance."
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, default=Path(__file__).resolve().parent.parent)
    parser.add_argument("--manifest", type=Path, help="Default: <repo>/data/snapshots/MANIFEST.json")
    parser.add_argument("--dataset", action="append", help="Repeat to audit selected dataset IDs only")
    parser.add_argument("--output", type=Path, help="New report file outside data/snapshots; default: stdout")
    args = parser.parse_args(argv)
    repo = args.repo.resolve()
    output = args.output.resolve() if args.output else None
    if output and output.is_relative_to((repo / "data/snapshots").resolve()):
        parser.error("report output must be outside data/snapshots")
    try:
        report = audit(repo, args.manifest or repo / "data/snapshots/MANIFEST.json", set(args.dataset or []))
        text = json.dumps(report, indent=2) + "\n"
        if output:
            with output.open("x", encoding="utf-8") as stream:
                stream.write(text)
            print(f"{report['status']}: {report['counts']}; report={output}")
        else:
            print(text, end="")
        return {"verified": 0, "failed": 1, "partial": 2}[report["status"]]
    except (OSError, ValueError, TypeError) as exc:
        parser.exit(1, f"audit failed: {exc}\n")


if __name__ == "__main__":
    raise SystemExit(main())
