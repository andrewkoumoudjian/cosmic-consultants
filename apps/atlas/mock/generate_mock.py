#!/usr/bin/env python3
"""Generate the SYNTHETIC mock sites used by the atlas demo (W11, issue #21).

Everything this script writes is invented for the UI demo. It is NOT an
assessment of any real place, and no real measurement is behind it. Real data
arrives later from the ingest lane (#19) and the engine lane (#20); this file
only exists so the map has something to draw while those lanes are working.

The output validates against contracts/site.schema.json, and the ARL level of
every entry is recomputed here with the rule frozen in proofs/Analog/Readiness.lean
(largest k <= 6 whose gates 1..k all pass, gates 1-4 for every required
dimension of the objective). apps/atlas/scripts/check-mock.mjs re-checks both.

Usage: python3 apps/atlas/mock/generate_mock.py
"""
from __future__ import annotations

import json
from pathlib import Path

OUT_DIR = Path(__file__).resolve().parent / "sites"

GATE_NAMES = ["observed", "withinTolerance", "corroborated", "fieldCharacterized"]
SITE_GATES = ["operable", "campaignProven"]
ALL_GATES = GATE_NAMES + SITE_GATES

# Required dimensions per objective, copied from data/objectives/*.yaml.
REQUIRED = {
    "OP-5LM": ["terrain", "surfaceMaterial", "dustProcess", "thermal"],
    "SE-3LM": ["waterIce", "thermal", "subsurface", "illumination"],
    "LI-5L": ["terrain", "illumination"],
}
BODY = {"OP-5LM": "mars", "SE-3LM": "moon", "LI-5L": "moon"}

# Outcome shorthands used in the table below.
P, F, U = "pass", "fail", "unknown"
LETTER = {"P": P, "F": F, "U": U}


def gate(outcome: str, note: str | None = None) -> dict:
    """One gate outcome. Evidence refs are obviously fake placeholders."""
    ref = ["synthetic:mock-grid"] if outcome == P else []
    out: dict = {"outcome": outcome, "evidenceRefs": ref}
    if note:
        out["note"] = note
    return out


def dim_gates(dimension: str, outcomes: str) -> dict:
    """outcomes is a 4-letter string, one letter per gate 1..4."""
    if len(outcomes) != 4:
        raise ValueError(f"{dimension}: need 4 outcomes, got {outcomes!r}")
    notes = {
        U: "SYNTHETIC: no data in the mock grid, so this gate is unknown.",
        F: "SYNTHETIC: mock grid says this dimension is out of tolerance.",
    }
    row = {"dimension": dimension}
    for name, letter in zip(GATE_NAMES, outcomes):
        row[name] = gate(LETTER[letter], notes.get(LETTER[letter]))
    return row


def recompute_arl(per_dimension: list[dict], site_gates: dict) -> int:
    """The frozen rule: largest k <= 6 with gates 1..k passing."""
    level = 0
    for k in range(1, 7):
        if k <= 4:
            ok = all(row[GATE_NAMES[k - 1]]["outcome"] == P for row in per_dimension)
        else:
            ok = site_gates[ALL_GATES[k - 1]]["outcome"] == P
        if not ok:
            break
        level = k
    return level


def build_readiness(objective_id: str, dims: dict[str, str], site_gates: str) -> dict:
    if len(site_gates) != 2:
        raise ValueError("site gates need 2 outcomes")
    per_dimension = [dim_gates(d, dims[d]) for d in REQUIRED[objective_id]]
    site = {name: gate(LETTER[letter]) for name, letter in zip(SITE_GATES, site_gates)}
    arl = recompute_arl(per_dimension, site)
    limiting_gate = None if arl == 6 else ALL_GATES[arl]
    limiting_dimension = None
    if limiting_gate in GATE_NAMES:
        failing = [
            row["dimension"]
            for row in per_dimension
            if row[limiting_gate]["outcome"] != P
        ]
        limiting_dimension = failing[0]
    return {
        "objectiveId": objective_id,
        "body": BODY[objective_id],
        "arl": arl,
        "gates": {"perDimension": per_dimension, "site": site},
        "limitingGate": limiting_gate,
        "limitingDimension": limiting_dimension,
        "statementLedger": "SYNTHETIC-MOCK (not a Lean-checked level)",
    }


# --- The mock roster -------------------------------------------------------
# Each entry: id, name, lat/lon, permanent mismatches, per-dimension losses,
# and one readiness block per objective (the objectives left out are the ones
# the demo shows as "not rated" in grey).
SITES = [
    {
        "siteId": "synthetic-atacama-plateau",
        "name": "SYNTHETIC demo cell - Atacama-like high plateau",
        "lat": -24.6,
        "lon": -69.9,
        "cellSizeKm": 20,
        "mismatches": ["gravity", "pressureRegime"],
        "losses": {
            "terrain": (0.18, False),
            "surfaceMaterial": (0.22, False),
            "dustProcess": (0.31, False),
            "thermal": (0.27, False),
            "illumination": (0.44, False),
            "waterIce": (0.95, True),
            "subsurface": (0.9, True),
            "operations": (0.35, False),
        },
        "readiness": {
            "OP-5LM": ({"terrain": "PPPP", "surfaceMaterial": "PPPP", "dustProcess": "PPUU", "thermal": "PPUU"}, "PU"),
            "SE-3LM": ({"waterIce": "UUUU", "thermal": "UUUU", "subsurface": "UUUU", "illumination": "UUUU"}, "PU"),
            "LI-5L": ({"terrain": "PPUU", "illumination": "PPUU"}, "PU"),
        },
    },
    {
        "siteId": "synthetic-hanksville-badlands",
        "name": "SYNTHETIC demo cell - desert badlands like Hanksville",
        "lat": 38.7,
        "lon": -110.7,
        "cellSizeKm": 15,
        "mismatches": ["pressureRegime", "radiation"],
        "losses": {
            "terrain": (0.12, False),
            "surfaceMaterial": (0.2, False),
            "dustProcess": (0.29, False),
            "thermal": (0.25, False),
            "illumination": (0.15, False),
            "waterIce": (0.88, True),
            "subsurface": (0.33, False),
            "operations": (0.16, False),
        },
        "readiness": {
            "OP-5LM": ({"terrain": "PPPU", "surfaceMaterial": "PPUU", "dustProcess": "PPUU", "thermal": "PPUU"}, "PU"),
            "SE-3LM": ({"waterIce": "UUUU", "thermal": "UUUU", "subsurface": "UUUU", "illumination": "UUUU"}, "PU"),
            "LI-5L": ({"terrain": "PPPP", "illumination": "PPPP"}, "PU"),
        },
    },
    {
        "siteId": "synthetic-devon-island-cold-desert",
        "name": "SYNTHETIC demo cell - polar cold desert like Devon Island",
        "lat": 75.3,
        "lon": -89.5,
        "cellSizeKm": 30,
        "mismatches": ["pressureRegime", "radiation"],
        "losses": {
            "terrain": (0.21, False),
            "surfaceMaterial": (0.14, False),
            "dustProcess": (0.4, False),
            "thermal": (0.13, False),
            "illumination": (0.17, False),
            "waterIce": (0.09, False),
            "subsurface": (0.24, False),
            "operations": (0.41, False),
        },
        "readiness": {
            "OP-5LM": ({"terrain": "PPUU", "surfaceMaterial": "UUUU", "dustProcess": "UUUU", "thermal": "PPUU"}, "PU"),
            "SE-3LM": ({"waterIce": "PPPP", "thermal": "PPPP", "subsurface": "PPPU", "illumination": "PPPU"}, "PU"),
            "LI-5L": ({"terrain": "PPPU", "illumination": "PPPP"}, "PU"),
        },
    },
    {
        "siteId": "synthetic-mcmurdo-cold-desert",
        "name": "SYNTHETIC demo cell - Antarctic cold desert like McMurdo",
        "lat": -77.85,
        "lon": 166.67,
        "cellSizeKm": 25,
        "mismatches": ["pressureRegime", "radiation"],
        "losses": {
            "terrain": (0.19, False),
            "surfaceMaterial": (0.16, False),
            "dustProcess": (0.62, False),
            "thermal": (0.11, False),
            "illumination": (0.23, False),
            "waterIce": (0.07, False),
            "subsurface": (0.5, False),
            "operations": (0.28, False),
        },
        "readiness": {
            "OP-5LM": ({"terrain": "PPUU", "surfaceMaterial": "UUUU", "dustProcess": "UUUU", "thermal": "PPUU"}, "PU"),
            "SE-3LM": ({"waterIce": "PPPU", "thermal": "PPPU", "subsurface": "UUUU", "illumination": "PPUU"}, "PU"),
            "LI-5L": ({"terrain": "PPPP", "illumination": "PPPP"}, "UU"),
        },
    },
    {
        "siteId": "synthetic-bolivian-altiplano",
        "name": "SYNTHETIC demo cell - high dry plateau like the Altiplano",
        "lat": -18.0,
        "lon": -67.5,
        "cellSizeKm": 18,
        "mismatches": ["gravity", "pressureRegime"],
        "losses": {
            "terrain": (0.15, False),
            "surfaceMaterial": (0.19, False),
            "dustProcess": (0.3, False),
            "thermal": (0.21, False),
            "illumination": (0.26, False),
            "waterIce": (0.93, True),
            "subsurface": (0.36, False),
            "operations": (0.3, False),
        },
        "readiness": {
            "OP-5LM": ({"terrain": "PPPP", "surfaceMaterial": "PPPP", "dustProcess": "PPPU", "thermal": "PPPU"}, "PU"),
            "SE-3LM": ({"waterIce": "UUUU", "thermal": "UUUU", "subsurface": "UUUU", "illumination": "UUUU"}, "PU"),
            "LI-5L": ({"terrain": "PPPU", "illumination": "PPUU"}, "PU"),
        },
    },
    {
        "siteId": "synthetic-ladakh-high-desert",
        "name": "SYNTHETIC demo cell - cold high desert like Ladakh",
        "lat": 34.2,
        "lon": 77.6,
        "cellSizeKm": 12,
        "mismatches": ["gravity", "pressureRegime"],
        "losses": {
            "terrain": (0.28, False),
            "surfaceMaterial": (0.4, False),
            "dustProcess": (0.55, False),
            "thermal": (0.36, False),
            "illumination": (0.2, False),
            "waterIce": (0.72, True),
            "subsurface": (0.44, False),
            "operations": (0.22, False),
        },
        "readiness": {
            "OP-5LM": ({"terrain": "PPPP", "surfaceMaterial": "PPUU", "dustProcess": "PUUU", "thermal": "PPUU"}, "PU"),
            "SE-3LM": ({"waterIce": "UUUU", "thermal": "UUUU", "subsurface": "UUUU", "illumination": "UUUU"}, "PU"),
            "LI-5L": ({"terrain": "PFUU", "illumination": "PPUU"}, "PU"),
        },
    },
    {
        "siteId": "synthetic-namib-desert",
        "name": "SYNTHETIC demo cell - gravel desert like the Namib",
        "lat": -23.5,
        "lon": 15.0,
        "cellSizeKm": 20,
        "mismatches": ["gravity", "pressureRegime"],
        "losses": {
            "terrain": (0.08, False),
            "surfaceMaterial": (0.11, False),
            "dustProcess": (0.13, False),
            "thermal": (0.12, False),
            "illumination": (0.18, False),
            "waterIce": (0.96, True),
            "subsurface": (0.29, False),
            "operations": (0.14, False),
        },
        "readiness": {
            "OP-5LM": ({"terrain": "PPPP", "surfaceMaterial": "PPPP", "dustProcess": "PPPP", "thermal": "PPPP"}, "PP"),
            "SE-3LM": ({"waterIce": "UUUU", "thermal": "UUUU", "subsurface": "UUUU", "illumination": "UUUU"}, "PU"),
            "LI-5L": ({"terrain": "PPPU", "illumination": "PPUU"}, "PP"),
        },
    },
    {
        "siteId": "synthetic-greenland-ice-sheet",
        "name": "SYNTHETIC demo cell - ice sheet like Greenland",
        "lat": 72.0,
        "lon": -40.0,
        "cellSizeKm": 40,
        "mismatches": ["pressureRegime", "radiation"],
        "losses": {
            "terrain": (0.3, False),
            "surfaceMaterial": (0.25, False),
            "dustProcess": (0.7, False),
            "thermal": (0.15, False),
            "illumination": (0.42, False),
            "waterIce": (0.04, False),
            "subsurface": (0.6, False),
            "operations": (0.48, False),
        },
        "readiness": {
            "OP-5LM": None,
            "SE-3LM": ({"waterIce": "PPPU", "thermal": "PPPP", "subsurface": "UUUU", "illumination": "PPUU"}, "PU"),
            "LI-5L": ({"terrain": "PPUU", "illumination": "PFUU"}, "PU"),
        },
    },
    {
        "siteId": "synthetic-svalbard-cold-ridge",
        "name": "SYNTHETIC demo cell - cold ridge like Svalbard",
        "lat": 78.2,
        "lon": 15.6,
        "cellSizeKm": 22,
        "mismatches": ["pressureRegime", "radiation"],
        "losses": {
            "terrain": (0.16, False),
            "surfaceMaterial": (0.23, False),
            "dustProcess": (0.66, False),
            "thermal": (0.14, False),
            "illumination": (0.19, False),
            "waterIce": (0.1, False),
            "subsurface": (0.26, False),
            "operations": (0.32, False),
        },
        "readiness": {
            "OP-5LM": None,
            "SE-3LM": ({"waterIce": "PPPP", "thermal": "PPPU", "subsurface": "PPPU", "illumination": "PPPU"}, "PU"),
            "LI-5L": ({"terrain": "PPPP", "illumination": "PPPP"}, "PU"),
        },
    },
    {
        "siteId": "synthetic-hawaii-lava-field",
        "name": "SYNTHETIC demo cell - young lava field like Hawaii",
        "lat": 19.6,
        "lon": -155.6,
        "cellSizeKm": 10,
        "mismatches": ["gravity", "pressureRegime"],
        "losses": {
            "terrain": (0.35, False),
            "surfaceMaterial": (0.24, False),
            "dustProcess": (0.33, False),
            "thermal": (0.2, False),
            "illumination": (0.22, False),
            "waterIce": (0.9, True),
            "subsurface": (0.18, False),
            "operations": (0.38, False),
        },
        "readiness": {
            "OP-5LM": ({"terrain": "PFUU", "surfaceMaterial": "PPUU", "dustProcess": "PPUU", "thermal": "PPUU"}, "PU"),
            "SE-3LM": None,
            "LI-5L": ({"terrain": "PPUU", "illumination": "PPUU"}, "PU"),
        },
    },
    {
        "siteId": "synthetic-ocean-control-cell",
        "name": "SYNTHETIC demo cell - open ocean (a deliberate non-analog)",
        "lat": 30.0,
        "lon": -40.0,
        "cellSizeKm": 50,
        "mismatches": ["gravity", "pressureRegime", "radiation"],
        "losses": {
            "terrain": (1.0, True),
            "surfaceMaterial": (1.0, True),
            "dustProcess": (1.0, True),
            "thermal": (0.95, True),
            "illumination": (0.9, True),
            "waterIce": (0.95, True),
            "subsurface": (1.0, True),
            "operations": (1.0, True),
        },
        "readiness": {
            "OP-5LM": ({"terrain": "UUUU", "surfaceMaterial": "UUUU", "dustProcess": "UUUU", "thermal": "UUUU"}, "UU"),
            "SE-3LM": ({"waterIce": "UUUU", "thermal": "UUUU", "subsurface": "UUUU", "illumination": "UUUU"}, "UU"),
            "LI-5L": ({"terrain": "UUUU", "illumination": "UUUU"}, "UU"),
        },
    },
]


def build_site(spec: dict) -> dict:
    analogy = []
    for dimension, (loss, breakdown) in spec["losses"].items():
        row = {"dimension": dimension, "loss": loss, "breakdown": breakdown, "datasetRefs": []}
        if breakdown:
            row["breakdownReason"] = "SYNTHETIC: this dimension breaks down for this objective."
        analogy.append(row)
    readiness = []
    for objective_id, entry in spec["readiness"].items():
        if entry is None:
            # Deliberately not rated for this objective: the map shows it grey.
            continue
        dims, site_gates = entry
        readiness.append(build_readiness(objective_id, dims, site_gates))
    return {
        "siteId": spec["siteId"],
        "name": spec["name"],
        "geometry": {
            "centroidLat": spec["lat"],
            "centroidLon": spec["lon"],
            "cellSizeKm": spec["cellSizeKm"],
        },
        "analogy": analogy,
        "permanentMismatches": spec["mismatches"],
        "explorationUse": ["SYNTHETIC mock demo cell. Not a real assessment."],
        "readiness": readiness,
        "provenance": {
            "statementLedger": "SYNTHETIC-MOCK (not a Lean-checked level)",
            "snapshots": [],
        },
    }


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for spec in SITES:
        site = build_site(spec)
        path = OUT_DIR / f"{spec['siteId']}.json"
        path.write_text(json.dumps(site, indent=2) + "\n", encoding="utf-8")
        levels = ", ".join(f"{r['objectiveId']}=ARL {r['arl']}" for r in site["readiness"])
        print(f"wrote {path.name} ({levels})")
    print(f"{len(SITES)} synthetic mock sites written to {OUT_DIR}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
