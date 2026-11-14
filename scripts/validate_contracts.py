#!/usr/bin/env python3
"""Validate contracts (W10, #15) and target envelopes (W5, #18).

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
4. --self-test: broken copies of the example must be rejected.

Exit code 0 only if everything passes. Usage: python3 scripts/validate_contracts.py [--self-test]
"""
from __future__ import annotations

import copy
import glob
import json
import sys
from pathlib import Path

import yaml
from jsonschema import Draft202012Validator, FormatChecker

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


def main() -> int:
    ov, sv = load_schema("objective.schema.json"), load_schema("site.schema.json")
    ev = load_schema("envelope.schema.json")
    objectives, errs = load_objectives(ov)
    registry = load_registry()
    envelopes, env_errs = load_envelopes(ev, registry)
    errs += env_errs
    errs += check_objective_envelopes(objectives, envelopes)
    for rel in SITE_FIXTURES:
        site = json.loads((ROOT / rel).read_text(encoding="utf-8"))
        e = check_site(sv, objectives, site, rel)
        errs += e
        levels = ", ".join(f"{r['objectiveId']}=ARL {r['arl']}" for r in site.get("readiness", []))
        print(f"{'OK  ' if not e else 'FAIL'} site {rel} ({levels})")
    if "--self-test" in sys.argv:
        errs += self_test(sv, objectives)
        errs += self_test_envelopes(ev, registry)
    for m in errs:
        print("ERROR", m)
    print("all contracts valid" if not errs else f"{len(errs)} error(s)")
    return 0 if not errs else 1


if __name__ == "__main__":
    sys.exit(main())
