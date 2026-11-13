#!/usr/bin/env python3
"""Dataset registry probe (W3, issue #4).

Reads every data/catalog/*.yaml row, live-probes its resolved source endpoint
and its license text, and writes:

  data/snapshots/registry-probes/<UTC date>/probe-log.json
      one entry per row: URL(s) fetched, UTC time, HTTP status, bytes, sha256,
      extracted metadata, license-evidence matches;
  data/snapshots/registry-probes/<UTC date>/ckan-queues.json
      the data.nasa.gov triage queues of doc 05 §3, full record lists, UNGRADED;
  data/catalog/INDEX.md
      generated summary table (never hand-edit);

and writes back into each YAML only the probe-owned fields:
  source.probedAt, source.probeResult, license.verified.

Nothing else in a row is touched, so descriptive fields stay human-reviewed.
A license is `verified: true` only if every `license.expect` regex matched the
live text at `license.textUrl` (or the row's own probe body when textUrl is
null). Failed probes are recorded as failures, never retried silently away.

Usage:  python3 scripts/registry_probe.py [--no-ckan] [--only <datasetId>...]
"""
from __future__ import annotations

import argparse
import concurrent.futures as cf
import datetime as dt
import hashlib
import html
import json
import pathlib
import re
import threading
import sys
import urllib.error
import urllib.parse
import urllib.request

import yaml

ROOT = pathlib.Path(__file__).resolve().parents[1]
CATALOG = ROOT / "data" / "catalog"
UA = {"User-Agent": "cosmic-consultants-registry-probe/1.0 (+github.com/andrewkoumoudjian/cosmic-consultants)"}
CMR = "https://cmr.earthdata.nasa.gov/search"
CKAN = "https://data.nasa.gov/api/3/action/package_search"
# doc 05 §3 small queues: full record lists are snapshotted for manual grading.
CKAN_FL = "name,title,license_id,metadata_modified,extras_identifier,extras_harvest_source_title,res_url"
CKAN_QUEUES = {
    "regolith": 'q=regolith',
    "landing-site": 'q=%22landing%20site%22',
    "lola": 'q=LOLA',
    "mola": 'q=MOLA',
    "permafrost": 'q=permafrost',
    "crater": 'q=crater',
}


def now() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# data.nasa.gov (CKAN) stalls under concurrent queries: serialize every request to it
# and give it more attempts. Other hosts stay parallel.
_SERIAL = {"data.nasa.gov": threading.Lock()}


def fetch(url: str, limit: int = 25_000_000, tries: int = 2, timeout: int = 90):
    """GET url -> dict(status, bytes, sha256, finalUrl, fetchedAt, body|error, headers)."""
    lock = _SERIAL.get(urllib.parse.urlsplit(url).hostname or "")
    if lock is not None:
        with lock:
            return _fetch(url, limit, max(tries, 3), timeout)
    return _fetch(url, limit, tries, timeout)


def _fetch(url: str, limit: int, tries: int, timeout: int):
    last = None
    for _ in range(tries):
        t = now()
        try:
            req = urllib.request.Request(url, headers=UA)
            with urllib.request.urlopen(req, timeout=timeout) as r:
                body = r.read(limit)
                return {"url": url, "finalUrl": r.geturl(), "fetchedAt": t, "status": r.status,
                        "bytes": len(body), "sha256": hashlib.sha256(body).hexdigest(),
                        "headers": {k.lower(): v for k, v in r.headers.items() if k.lower().startswith("cmr-")},
                        "body": body}
        except urllib.error.HTTPError as e:
            body = e.read(limit) if hasattr(e, "read") else b""
            return {"url": url, "fetchedAt": t, "status": e.code, "bytes": len(body),
                    "sha256": hashlib.sha256(body).hexdigest(), "body": body, "error": f"HTTP {e.code}"}
        except Exception as e:  # noqa: BLE001 - recorded as a failed probe
            last = {"url": url, "fetchedAt": t, "status": None, "error": f"{type(e).__name__}: {e}"}
    return last


def text_of(body: bytes) -> str:
    t = body.decode("utf-8", "ignore")
    t = re.sub(r"(?is)<(script|style)[^>]*>.*?</\1>", " ", t)
    return html.unescape(re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", t)))


def title_of(body: bytes) -> str | None:
    m = re.search(rb"(?is)<title[^>]*>(.*?)</title>", body)
    return html.unescape(m.group(1).decode("utf-8", "ignore").strip())[:160] if m else None


def strip(f: dict) -> dict:
    return {k: v for k, v in f.items() if k != "body"}


def match_all(patterns: list[str], text: str) -> dict:
    out = {}
    for p in patterns or []:
        m = re.search(p, text, re.I)
        out[p] = text[max(0, m.start() - 80): m.end() + 120] if m else None
    return out


# ---------------------------------------------------------------- probe kinds
def probe_cmr(spec: dict) -> tuple[dict, str, str]:
    cid = spec["conceptId"]
    f = fetch(f"{CMR}/concepts/{cid}.umm_json")
    meta: dict = {}
    if f.get("status") == 200:
        u = json.loads(f["body"])
        rng = (u.get("TemporalExtents") or [{}])[0].get("RangeDateTimes") or [{}]
        hsd = (u.get("SpatialExtent") or {}).get("HorizontalSpatialDomain") or {}
        meta = {"shortName": u.get("ShortName"), "version": u.get("Version"),
                "entryTitle": u.get("EntryTitle"), "doi": (u.get("DOI") or {}).get("DOI"),
                "temporal": [rng[0].get("BeginningDateTime"), rng[-1].get("EndingDateTime")],
                "resolution": (hsd.get("ResolutionAndCoordinateSystem") or {}).get("HorizontalDataResolution"),
                "useConstraints": u.get("UseConstraints"),
                "archiveCenter": [d.get("ShortName") for d in u.get("DataCenters", []) if "ARCHIVER" in d.get("Roles", [])]}
    g = fetch(f"{CMR}/granules.json?collection_concept_id={cid}&page_size=0")
    meta["granuleHits"] = (g.get("headers") or {}).get("cmr-hits")  # header names lower-cased in fetch()
    summary = (f"CMR {cid}: HTTP {f.get('status')}, {meta.get('shortName')} v{meta.get('version')}, "
               f"DOI {meta.get('doi')}, granules {meta.get('granuleHits')}")
    text = json.dumps(meta.get("useConstraints") or {})
    return {"fetches": [strip(f), strip(g)], "meta": meta}, summary, text


def probe_stac(spec: dict) -> tuple[dict, str, str]:
    f = fetch(spec["url"])
    meta = {}
    if f.get("status") == 200:
        c = json.loads(f["body"])
        meta = {"id": c.get("id"), "title": c.get("title"), "license": c.get("license"),
                "extent": c.get("extent")}
    it = fetch(spec["url"].rstrip("/") + "/items?limit=1")
    if it.get("status") == 200:
        j = json.loads(it["body"])
        meta["numberMatched"] = j.get("numberMatched") or (j.get("context") or {}).get("matched")
    summary = (f"STAC {meta.get('id')}: HTTP {f.get('status')}, license {meta.get('license')}, "
               f"items {meta.get('numberMatched')}")
    return {"fetches": [strip(f), strip(it)], "meta": meta}, summary, json.dumps(meta)


def probe_http(spec: dict) -> tuple[dict, str, str]:
    f = fetch(spec["url"])
    body = f.get("body") or b""
    meta = {"title": title_of(body)}
    if spec.get("kind") == "wmts":
        meta["layers"] = len(re.findall(rb"<Layer>", body))
        meta["identifiers"] = re.findall(rb"<ows:Identifier>([^<]+)</ows:Identifier>", body)[:5]
        meta["identifiers"] = [i.decode() for i in meta["identifiers"]]
    txt = text_of(body) if body else ""
    meta["expect"] = match_all(spec.get("expect"), txt)
    ok = f.get("status") == 200 and all(meta["expect"].values())
    summary = (f"HTTP {f.get('status')}, {f.get('bytes')} B, sha256 {str(f.get('sha256'))[:12]}…"
               + (f", layers {meta.get('layers')}" if "layers" in meta else "")
               + ("" if ok else f" — PROBE FAILED ({f.get('error') or 'expectation not met'})"))
    return {"fetches": [strip(f)], "meta": meta, "ok": ok}, summary, txt


KINDS = {"cmr": probe_cmr, "stac": probe_stac, "http": probe_http, "wmts": probe_http}


def probe_row(path: pathlib.Path) -> dict:
    row = yaml.safe_load(path.read_text(encoding="utf-8"))
    spec = row["probe"]
    res, summary, text = KINDS[spec["kind"]](spec)
    lic = row.get("license") or {}
    lic_ev: dict = {}
    if lic.get("expect"):
        if lic.get("textUrl"):
            lf = fetch(lic["textUrl"])
            ltxt = text_of(lf.get("body") or b"")
            if lic["textUrl"].lower().endswith(".pdf"):
                ltxt = (lf.get("body") or b"").decode("latin-1", "ignore")
            lic_ev = {"fetch": strip(lf), "matches": match_all(lic["expect"], ltxt)}
        else:
            lic_ev = {"fetch": "row probe body", "matches": match_all(lic["expect"], text)}
    verified = bool(lic_ev) and all(lic_ev["matches"].values())
    return {"datasetId": row["datasetId"], "file": path.relative_to(ROOT).as_posix(),
            "probe": res, "summary": summary, "license": {"id": lic.get("id"), "verified": verified,
                                                          "evidence": lic_ev}}


def write_back(path: pathlib.Path, entry: dict) -> None:
    """Rewrite only probe-owned scalar lines, preserving layout and comments."""
    s = path.read_text(encoding="utf-8")
    probed = entry["probe"]["fetches"][0].get("fetchedAt")
    s = re.sub(r"(?m)^(  probedAt:).*$", lambda m: f"{m.group(1)} {probed}", s, count=1)
    s = re.sub(r"(?m)^(  probeResult:).*$", lambda m: f"{m.group(1)} {json.dumps(entry['summary'], ensure_ascii=False)}", s, count=1)
    s = re.sub(r"(?m)^(  verified:).*$", lambda m: f"{m.group(1)} {str(entry['license']['verified']).lower()}", s, count=1)
    path.write_text(s, encoding="utf-8")


def ckan_queues() -> dict:
    out = {}
    for name, q in CKAN_QUEUES.items():
        # Full package dicts hang on data.nasa.gov (observed 2026-11-12: rows=1000
        # timed out at 134 s even for a 52-record queue); a field-limited query
        # (`fl`) answers in ~1.4 s.
        f = fetch(f"{CKAN}?{q}&rows=1000&fl={CKAN_FL}", tries=3, timeout=120)
        rec = {"query": q, "fetch": strip(f)}
        if f.get("status") == 200:
            r = json.loads(f["body"])["result"]
            rec["count"] = r["count"]
            rec["records"] = [{
                "name": p.get("name"), "title": p.get("title"), "license_id": p.get("license_id"),
                "metadata_modified": p.get("metadata_modified"),
                "identifier": p.get("identifier"),
                "harvest_source": p.get("harvest_source_title"),
                "first_resource": (p.get("res_url") or [None])[0],
                "grade": None,  # UNGRADED: manual triage per doc 05 §5
            } for p in r["results"]]
        out[name] = rec
    return out


def index_md(entries: list[dict], rows: dict[str, dict], day: str) -> str:
    lines = [f"# Dataset registry index (generated {day} by `scripts/registry_probe.py`; do not hand-edit)", "",
             "Status values: `candidate` (probed, not yet adopted by a work order) · `restricted` (license limits use) · "
             "`unresolved` (endpoint or license not confirmed live). A license counts as verified only when its "
             "expected text was found live (see probe log).", "",
             "| datasetId | body | dimensions | archive | status | license | lic. verified | probe |",
             "|---|---|---|---|---|---|---|---|"]
    for e in sorted(entries, key=lambda e: (rows[e["datasetId"]]["bodies"][0], e["datasetId"])):
        r = rows[e["datasetId"]]
        lines.append(f"| [{e['datasetId']}]({e['datasetId']}.yaml) | {', '.join(r['bodies'])} | "
                     f"{', '.join(r['dimensions']) or '—'} | {r['source']['archive']} | {r.get('status')} | "
                     f"{r['license']['id']} | {'yes' if e['license']['verified'] else 'no'} | {e['summary']} |")
    return "\n".join(lines) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-ckan", action="store_true")
    ap.add_argument("--only", nargs="*")
    a = ap.parse_args()
    paths = sorted(p for p in CATALOG.glob("*.yaml") if p.name != "dataset.template.yaml")
    if a.only:
        paths = [p for p in paths if p.stem in a.only]
    with cf.ThreadPoolExecutor(max_workers=8) as ex:
        entries = list(ex.map(probe_row, paths))
    day = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d")
    out = ROOT / "data" / "snapshots" / "registry-probes" / day
    out.mkdir(parents=True, exist_ok=True)
    log = {"generatedAt": now(), "tool": "scripts/registry_probe.py", "entries": entries}
    (out / "probe-log.json").write_text(json.dumps(log, indent=1, default=str) + "\n", encoding="utf-8")
    for p, e in zip(paths, entries):
        write_back(p, e)
    if not a.only:
        rows = {yaml.safe_load(p.read_text(encoding="utf-8"))["datasetId"]: yaml.safe_load(p.read_text(encoding="utf-8")) for p in paths}
        (CATALOG / "INDEX.md").write_text(index_md(entries, rows, day), encoding="utf-8")
    if not a.no_ckan:
        q = {"generatedAt": now(), "source": CKAN, "note": "Ungraded triage queues (doc 05 §3). "
             "A record here is a lead, never a registry row.", "queues": ckan_queues()}
        (out / "ckan-queues.json").write_text(json.dumps(q, indent=1) + "\n", encoding="utf-8")
    bad = [e for e in entries if not e["probe"].get("ok", True) or any(
        f.get("status") != 200 for f in e["probe"]["fetches"][:1])]
    for e in entries:
        print(f"{e['datasetId']:42s} lic={'Y' if e['license']['verified'] else 'n'}  {e['summary']}")
    print(f"\n{len(entries)} rows probed, {len(bad)} with failed primary probe; log -> {out.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
