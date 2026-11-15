# services/engine: planner engine (W7, #20)

Reads L1, L1m, L2 (`data/snapshots/_derived/*.parquet`) and L3 (`data/objectives`,
`data/requirements/trait-map.yaml`, `data/campaigns`), and writes L4 for the app
plus one site plan per request (`contracts/site-plan.schema.json`, #78).
Spec: `docs/plan/MISSION-PLANNER.md` (Engine) and `docs/plan/DATA-PIPELINE.md` (L4).

**No site scores, ever** (AGENTS.md rule 4). Each trait is match, miss with its
gap, or unknown with its reason.

## What's here now, and what waits

| Module | Does | Status |
|---|---|---|
| `request.py` | plan request ⇄ share-link URL, lossless round-trip; month window with year wrap | done, tested |
| `logistics.py` | step 4 values from L2, plain-words notes, the scientist's checklist, hard-limit outcomes (unknown is never fail) | done, tested |
| `risks.py` | step 5: one row per EONET category with named events + disclaimer, burned area (P1), steep ground, coldest/hottest requested month | done, tested |
| `publish.py` | L4: `cells.bin/json`, `monthly/*.bin`, L3 as JSON, `build-manifest.json` with every sha256; deterministic | done, tested on synthetic tables |
| verdicts, funnel, season, Pareto shortlist, gaps | steps 1–3 + season strip | **waits for the S7 freeze (#80, PR #84)**: rule 1, Lean first |
| precedents + Shapley | step 6 | **waits for the S8 freeze (#80)** |
| `golden-verdicts.json` | ~200 hexagons × objectives for the atlas to reproduce | after verdicts |

## Run

```bash
cd services/engine
python -m unittest discover -s tests -v                 # stdlib only
PYTHONPATH=src python -m planner publish ../../data/snapshots/_derived ../../apps/atlas/public/data/v1
```

`publish` needs `pyarrow` and `pyyaml` (pinned in `pyproject.toml`) and the
`_derived` files from the Drive mirror (see `services/ingest/README.md`).

## Numeric policy (open, needed before golden verdicts)

L4 stores Float32 (DATA-PIPELINE budget), so a value like 6.2 comes back as
6.1999998… (a test pins this). The engine works in float64 and the atlas in
Float32, so a value right at a band edge could get different verdicts in each.
Proposal: compute `golden-verdicts.json` **from the published Float32 values**,
so the engine and the atlas compare the very same numbers. Lean S7 uses exact
reals; this is the "numeric conformance" gap listed in `proofs/STATEMENTS.md`.
