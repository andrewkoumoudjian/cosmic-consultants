#!/usr/bin/env python3
"""Validate contracts (W10, #15), envelopes (W5, #18), and campaigns (W19, #60).

1. Schema check: every data/objectives/*.yaml against contracts/objective.schema.json,
   every site fixture with a readiness block against contracts/site.schema.json, and
   every data/envelopes/*.json against contracts/envelope.schema.json.
2. ARL check: recompute each readiness entry's level from its gate outcomes with the
   rule frozen in proofs/Analog/Readiness.lean (largest k <= 6 with gates 1..k passing;
   gates 1-4 must pass for every required dimension, and there must be at least one),
   and check limitingGate / limitingDimension and the per-dimension rows.
3. Envelope check (W5, #18): lo <= hi per dimension (Envelope.valid, not expressible
   in JSON Schema), every sourceDataset is a registry datasetId in data/catalog/,
   the named dataset covers the envelope's body and lists that dimension, and every
   objective's toleranceSource.envelopeId resolves to a file in data/envelopes/.
4. Campaign check: validate data/campaigns/*.yaml, source refs, source quote text,
   local snapshot hashes, and H3 resolution-4 cells.
5. Planner contracts (W20, #78): data/requirements/trait-map.yaml and the example
   plan-request / site-plan fixtures, with their cross-file rules
   (scripts/planner_contracts.py).
6. --self-test: broken copies of the examples must be rejected.

Exit code 0 only if everything passes. Usage: python3 scripts/validate_contracts.py [--self-test]
"""
from __future__ import annotations

import copy
import hashlib
import glob
import json
import re
import subprocess
import sys
from pathlib import Path

import yaml
import h3
from jsonschema import Draft202012Validator, FormatChecker

import planner_contracts

ROOT = Path(__file__).resolve().parent.parent
DIM_GATES = ["observed", "withinTolerance", "corroborated", "fieldCharacterized"]
SITE_GATES = ["operable", "campaignProven"]
GATES = DIM_GATES + SITE_GATES  # gate k is GATES[k-1]
SITE_FIXTURES = ["data/fixtures/example-site-readiness.json"]


def load_schema(name: str) -> Draft202012Validator:
    schema = json.loads((ROOT / "contracts" / name).read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema, format_checker=FormatChecker())


def schema_errors(v: Draft202012Validator, doc) -> list[str]:
    return [f"{'/'.join(map(str, e.path)) or '<root>'}: {e.message}" for e in v.iter_errors(doc)]


def gate_passes(entry: dict, required: list[str], k: int) -> bool:
    gate = GATES[k - 1]
    if gate in DIM_GATES:
        rows = {r["dimension"]: r for r in entry["gates"]["perDimension"]}
        return bool(required) and all(rows[d][gate]["outcome"] == "pass" for d in required)
    return entry["gates"]["site"][gate]["outcome"] == "pass"


def recompute_arl(entry: dict, required: list[str]) -> int:
    level = 0
    for k in range(1, 7):
        if not gate_passes(entry, required, k):
            break
        level = k
    return level


def readiness_errors(site: dict, objectives: dict) -> list[str]:
    errs = []
    seen = set()
    for i, entry in enumerate(site.get("readiness", [])):
        where = f"readiness[{i}] {entry['objectiveId']}"
        key = (entry["objectiveId"], entry["body"])
        if key in seen:
            errs.append(f"{where}: duplicate objective entry")
        seen.add(key)
        obj = objectives.get(key)
        if obj is None:
            errs.append(f"{where}: no data/objectives row for {key}")
            continue
        if not obj["rateable"]:
            errs.append(f"{where}: objective is not rateable, so it must not get a level (S6g)")
            continue
        required = obj["requiredDimensions"]
        rows = [r["dimension"] for r in entry["gates"]["perDimension"]]
        if sorted(rows) != sorted(required) or len(set(rows)) != len(rows):
            errs.append(f"{where}: perDimension rows {rows} must be exactly the required dimensions {required}")
            continue
        level = recompute_arl(entry, required)
        if entry["arl"] != level:
            errs.append(f"{where}: arl says {entry['arl']} but the gates give {level}")
        want_gate = None if level == 6 else GATES[level]
        if entry["limitingGate"] != want_gate:
            errs.append(f"{where}: limitingGate should be {want_gate}, got {entry['limitingGate']}")
        if want_gate in DIM_GATES:
            failing = [r["dimension"] for r in entry["gates"]["perDimension"] if r[want_gate]["outcome"] != "pass"]
            if entry["limitingDimension"] not in failing:
                errs.append(f"{where}: limitingDimension should be one of {failing}, got {entry['limitingDimension']}")
        elif entry["limitingDimension"] is not None:
            errs.append(f"{where}: limitingDimension must be null when the limiting gate is a site gate or arl is 6")
    return errs


def load_objectives(ov: Draft202012Validator) -> tuple[dict, list[str]]:
    objectives: dict[tuple[str, str], dict] = {}
    errs: list[str] = []
    for path in sorted(glob.glob(str(ROOT / "data/objectives/*.yaml"))):
        doc = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
        rel = Path(path).relative_to(ROOT)
        e = schema_errors(ov, doc)
        errs += [f"{rel}: {m}" for m in e]
        print(f"{'OK  ' if not e else 'FAIL'} objective {rel} ({doc.get('objectiveId')}, {doc.get('body')})")
        if not e:
            key = (doc["objectiveId"], doc["body"])
            if key in objectives:
                errs.append(f"{rel}: duplicate objective row {key}")
            objectives[key] = doc
    return objectives, errs


def check_site(sv, objectives, site, label) -> list[str]:
    e = schema_errors(sv, site)
    if not e:
        e = readiness_errors(site, objectives)
    return [f"{label}: {m}" for m in e]


def load_registry() -> dict[str, dict]:
    """datasetId -> catalog row, for every adopted/candidate registry row.

    The template file is skipped: its datasetId is a placeholder, not a real row.
    """
    registry: dict[str, dict] = {}
    for path in sorted(glob.glob(str(ROOT / "data/catalog/*.yaml"))):
        if Path(path).name == "dataset.template.yaml":
            continue
        row = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
        if isinstance(row, dict) and row.get("datasetId"):
            registry[row["datasetId"]] = row
    return registry


def check_envelope(ev, doc, registry, label) -> list[str]:
    """Schema check plus the semantic rules JSON Schema cannot express."""
    errs = [f"{label}: {m}" for m in schema_errors(ev, doc)]
    if errs:
        return errs
    body = doc["body"]
    for i, dim in enumerate(doc["dimensions"]):
        where = f"{label}: dimensions[{i}] ({dim['dimension']})"
        if dim["lo"] > dim["hi"]:
            errs.append(f"{where}: lo {dim['lo']} > hi {dim['hi']} (Envelope.valid needs lo <= hi)")
        row = registry.get(dim["sourceDataset"])
        if row is None:
            errs.append(f"{where}: sourceDataset {dim['sourceDataset']!r} is not a datasetId in data/catalog/")
            continue
        bodies = row.get("bodies") or []
        if body not in bodies:
            errs.append(f"{where}: dataset {dim['sourceDataset']} covers bodies {bodies}, not {body!r}")
        dims = row.get("dimensions") or []
        if dim["dimension"] not in dims:
            errs.append(f"{where}: dataset {dim['sourceDataset']} lists dimensions {dims}, not {dim['dimension']!r}")
    return errs


def load_envelopes(ev, registry) -> tuple[dict[str, dict], list[str]]:
    """envelopeId -> envelope document."""
    envelopes: dict[str, dict] = {}
    errs: list[str] = []
    for path in sorted(glob.glob(str(ROOT / "data/envelopes/*.json"))):
        rel = Path(path).relative_to(ROOT)
        doc = json.loads(Path(path).read_text(encoding="utf-8"))
        e = check_envelope(ev, doc, registry, str(rel))
        errs += e
        bands = ", ".join(f"{d['dimension']} [{d['lo']}, {d['hi']}]" for d in doc.get("dimensions", []))
        print(f"{'OK  ' if not e else 'FAIL'} envelope {rel} ({doc.get('envelopeId')}: {bands})")
        if not e:
            if doc["envelopeId"] in envelopes:
                errs.append(f"{rel}: duplicate envelopeId {doc['envelopeId']}")
            envelopes[doc["envelopeId"]] = doc
    return envelopes, errs


def normalize_quote(text: str) -> str:
    """Ignore layout whitespace introduced by PDF extraction, not wording."""
    text = re.sub(r"(?<=\w)\u00ad\s+(?=\w)", "", text).replace("\u00ad", "")
    text = re.sub(r"(?<=\w)-\s+(?=\w)", "", text)
    return re.sub(r"\s+", " ", text).strip()


def source_text(path: Path) -> str:
    if path.suffix.lower() == ".pdf":
        extracts = []
        for mode in ("-raw", "-layout"):
            result = subprocess.run(["pdftotext", mode, str(path), "-"], capture_output=True, text=True)
            if result.returncode:
                raise RuntimeError(result.stderr.strip() or f"pdftotext exited {result.returncode}")
            extracts.append(result.stdout)
        return "\n".join(extracts)
    return path.read_text(encoding="utf-8", errors="replace")


def campaign_quote_rows(doc: dict):
    yield "site.quote", doc["site"]["quote"], doc["site"]["sourceRef"]
    for key in ("objectivesExercised", "publishedConstraints", "outcome"):
        for i, row in enumerate(doc.get(key, [])):
            yield f"{key}[{i}].quote", row["quote"], row["sourceRef"]
    for i, row in enumerate(doc.get("evidence", [])):
        yield f"evidence[{i}].quote", row["quote"], row["sourceRef"]


def check_campaign(cv, doc: dict, label: str, manifest_by_source: dict) -> list[str]:
    errs = [f"{label}: {m}" for m in schema_errors(cv, doc)]
    if errs:
        return errs
    site = doc["site"]
    cell = h3.latlng_to_cell(site["lat"], site["lon"], 4)
    if site["h3r4"] != cell:
        errs.append(f"{label}: h3r4 {site['h3r4']} != computed {cell}")
    refs = {row["ref"]: row for row in doc["sources"]}
    if len(refs) != len(doc["sources"]):
        errs.append(f"{label}: duplicate source ref")
    for _, _, ref in campaign_quote_rows(doc):
        if ref not in refs:
            errs.append(f"{label}: quote points to missing sourceRef {ref!r}")
    texts: dict[str, str] = {}
    for ref, source in refs.items():
        local = source["localPath"]
        key = (source["url"], source["sha256"], local)
        if key not in manifest_by_source:
            errs.append(f"{label}: source {ref} is absent from snapshots/MANIFEST.json")
        if local is None:
            continue
        path = ROOT / local
        if not path.is_file():
            print(f"     SKIP campaign {doc['campaignId']} source payload absent: {local}")
            continue
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        if digest != source["sha256"]:
            errs.append(f"{label}: {local} SHA-256 {digest} != declared {source['sha256']}")
        try:
            texts[ref] = normalize_quote(source_text(path))
        except (OSError, RuntimeError) as exc:
            errs.append(f"{label}: cannot read quote source {local}: {exc}")
    for field, quote, ref in campaign_quote_rows(doc):
        text = texts.get(ref)
        if text is not None and normalize_quote(quote) not in text:
            errs.append(f"{label}: {field} quote is not verbatim in stored source {refs[ref]['localPath']}")
    return errs


def load_campaigns(cv) -> tuple[list[dict], list[str]]:
    errs: list[str] = []
    manifest_path = ROOT / "data/snapshots/MANIFEST.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest_by_source = {
        (row.get("sourceUrl"), row.get("sha256"), row.get("localPath")): row
        for row in manifest.get("entries", [])
    }
    campaigns = []
    seen_ids = set()
    for path_str in sorted(glob.glob(str(ROOT / "data/campaigns/*.yaml"))):
        path = Path(path_str)
        rel = path.relative_to(ROOT)
        doc = yaml.safe_load(path.read_text(encoding="utf-8"))
        e = check_campaign(cv, doc, str(rel), manifest_by_source)
        errs += e
        campaign_id = doc.get("campaignId") if isinstance(doc, dict) else None
        if campaign_id in seen_ids:
            errs.append(f"{rel}: duplicate campaignId {campaign_id}")
        seen_ids.add(campaign_id)
        campaigns.append(doc)
        print(f"{'OK  ' if not e else 'FAIL'} campaign {rel} ({campaign_id})")
    return campaigns, errs


def check_objective_envelopes(objectives, envelopes) -> list[str]:
    """Every toleranceSource.envelopeId must resolve; report which required
    dimensions the envelope does not bound (those stay unknown, not failed)."""
    errs: list[str] = []
    for (objective_id, body), obj in sorted(objectives.items()):
        env_id = (obj.get("toleranceSource") or {}).get("envelopeId")
        if env_id is None:
            print(f"     objective {objective_id} ({body}): no envelopeId; gate 2 is unknown for every required dimension")
            continue
        env = envelopes.get(env_id)
        if env is None:
            errs.append(f"objective {objective_id} ({body}): toleranceSource.envelopeId {env_id!r} is not an envelope in data/envelopes/")
            continue
        if env["body"] != body:
            errs.append(f"objective {objective_id} ({body}): envelope {env_id} is for body {env['body']!r}")
        bounded = {d["dimension"] for d in env["dimensions"]}
        required = obj.get("requiredDimensions", [])
        missing = [d for d in required if d not in bounded]
        covered = [d for d in required if d in bounded]
        print(f"     objective {objective_id} ({body}): envelope {env_id} bounds {covered or 'none'}; unknown for {missing or 'none'}")
    return errs


def self_test(sv, objectives) -> list[str]:
    base = json.loads((ROOT / SITE_FIXTURES[0]).read_text(encoding="utf-8"))
    cases = []
    c = copy.deepcopy(base); c["readiness"][0]["arl"] = 2; cases.append(("arl too high", c))
    c = copy.deepcopy(base); c["readiness"][0]["overallReadiness"] = 3; cases.append(("cross-objective aggregate field", c))
    c = copy.deepcopy(base); c["readiness"][0]["gates"]["perDimension"].pop(); cases.append(("missing required dimension row", c))
    c = copy.deepcopy(base); c["readiness"][0]["gates"]["perDimension"][0]["observed"]["outcome"] = "unknown"; cases.append(("unknown at gate 1 but arl 1", c))
    c = copy.deepcopy(base); c["readiness"][0]["limitingDimension"] = "terrain"; cases.append(("wrong limiting dimension", c))
    c = copy.deepcopy(base); c["readiness"][0]["gates"]["perDimension"][0]["observed"]["outcome"] = "maybe"; cases.append(("bad outcome value", c))
    c = copy.deepcopy(base); c["readiness"][0]["arl"] = 7; cases.append(("arl above 6", c))
    c = copy.deepcopy(base); c["readiness"][0]["body"] = "mars"; cases.append(("objective rated for the wrong body", c))
    errs = []
    for name, doc in cases:
        found = check_site(sv, objectives, doc, name)
        print(f"{'OK  ' if found else 'FAIL'} self-test rejects: {name}" + (f"  [{found[0]}]" if found else ""))
        if not found:
            errs.append(f"self-test: broken fixture was accepted: {name}")
    return errs


def self_test_envelopes(ev, registry) -> list[str]:
    base = json.loads((ROOT / "data/envelopes/mars-reference-v0.json").read_text(encoding="utf-8"))
    cases = []
    c = copy.deepcopy(base); c["dimensions"][0]["lo"] = 99; cases.append(("lo above hi", c))
    c = copy.deepcopy(base); c["dimensions"][0]["sourceDataset"] = "no-such-dataset"; cases.append(("sourceDataset not in the registry", c))
    c = copy.deepcopy(base); c["dimensions"][0]["dimension"] = "notADimension"; cases.append(("unknown dimension name", c))
    c = copy.deepcopy(base); c["body"] = "earth"; cases.append(("body with no registry dataset", c))
    c = copy.deepcopy(base); c["dimensions"][0]["sourceDataset"] = "lola-south-pole-ldem-2023"; cases.append(("moon dataset in a mars envelope", c))
    c = copy.deepcopy(base); c.pop("weightFamily"); cases.append(("missing weightFamily", c))
    errs = []
    for name, doc in cases:
        found = check_envelope(ev, doc, registry, name)
        print(f"{'OK  ' if found else 'FAIL'} self-test rejects: {name}" + (f"  [{found[0]}]" if found else ""))
        if not found:
            errs.append(f"self-test: broken envelope was accepted: {name}")
    return errs


def self_test_campaigns(cv) -> list[str]:
    """Broken copies of a campaign must be rejected. The quote case uses a
    temporary source file, so it runs in CI where snapshots are absent."""
    import tempfile
    base = yaml.safe_load((ROOT / "data/campaigns/hmp-2015.yaml").read_text(encoding="utf-8"))
    src = base["sources"][0]
    with tempfile.TemporaryDirectory() as tmp:
        text = Path(tmp) / "source.txt"
        text.write_text("Habitat Site Coordinates: 75o 26' N, 89o 52' W. Nothing else here.", encoding="utf-8")
        fake = {"url": src["url"], "sha256": hashlib.sha256(text.read_bytes()).hexdigest(), "localPath": str(text)}
        manifest = {(fake["url"], fake["sha256"], fake["localPath"]): {}}
        def with_fake(doc):
            doc["sources"][0].update(fake)
            doc["site"]["quote"] = "Habitat Site Coordinates: 75o 26' N, 89o 52' W"
            return doc
        def relevant(found):
            # The tiny fake source cannot contain the other quotes; only the site quote counts.
            return [f for f in found if "quote is not verbatim" not in f or "site.quote" in f]
        control = relevant(check_campaign(cv, with_fake(copy.deepcopy(base)), "control", manifest))
        print(f"{'OK  ' if not control else 'FAIL'} self-test control: unbroken campaign passes" + (f"  [{control[0]}]" if control else ""))
        errs = [f"self-test: control campaign rejected: {control[0]}"] if control else []
        cases = []
        c = with_fake(copy.deepcopy(base)); c["site"]["h3r4"] = "8402545ffffffff"; cases.append(("h3r4 is not the cell of lat/lon", c))
        c = with_fake(copy.deepcopy(base)); c["outcome"][0]["sourceRef"] = "no-such-ref"; cases.append(("quote points to a missing sourceRef", c))
        c = with_fake(copy.deepcopy(base)); c["sources"][0]["sha256"] = "0" * 64; cases.append(("source hash not in the manifest / file", c))
        c = with_fake(copy.deepcopy(base)); c["site"]["quote"] = "Habitat Site Coordinates: 76o 26' N"; cases.append(("site quote not verbatim in the source", c))
        c = with_fake(copy.deepcopy(base)); c["outcome"][0]["kind"] = "success"; cases.append(("bad outcome kind", c))
        c = with_fake(copy.deepcopy(base)); c["evidence"] = c["evidence"][:2]; cases.append(("fewer than 3 evidence quotes", c))
        for name, doc in cases:
            found = relevant(check_campaign(cv, doc, name, manifest))
            print(f"{'OK  ' if found else 'FAIL'} self-test rejects: {name}" + (f"  [{found[0]}]" if found else ""))
            if not found:
                errs.append(f"self-test: broken campaign was accepted: {name}")
    return errs


def main() -> int:
    ov, sv = load_schema("objective.schema.json"), load_schema("site.schema.json")
    cv = load_schema("campaign.schema.json")
    ev = load_schema("envelope.schema.json")
    objectives, errs = load_objectives(ov)
    registry = load_registry()
    envelopes, env_errs = load_envelopes(ev, registry)
    errs += env_errs
    errs += check_objective_envelopes(objectives, envelopes)
    _, campaign_errs = load_campaigns(cv)
    errs += campaign_errs
    errs += planner_contracts.run(objectives)
    for rel in SITE_FIXTURES:
        site = json.loads((ROOT / rel).read_text(encoding="utf-8"))
        e = check_site(sv, objectives, site, rel)
        errs += e
        levels = ", ".join(f"{r['objectiveId']}=ARL {r['arl']}" for r in site.get("readiness", []))
        print(f"{'OK  ' if not e else 'FAIL'} site {rel} ({levels})")
    if "--self-test" in sys.argv:
        errs += self_test(sv, objectives)
        errs += self_test_envelopes(ev, registry)
        errs += self_test_campaigns(cv)
        errs += planner_contracts.self_test(objectives)
    for m in errs:
        print("ERROR", m)
    print("all contracts valid" if not errs else f"{len(errs)} error(s)")
    return 0 if not errs else 1


if __name__ == "__main__":
    sys.exit(main())
