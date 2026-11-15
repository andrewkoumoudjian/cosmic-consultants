# cosmic-consultants

Monorepo for the NASA Space Apps Challenge 2026 — **Identify Earth Locations
that Analog the Permanent Moon Base Locations and Mars**.

**Live app: [Analog Atlas](https://cosmic-mission-ui.pages.dev/)**, built from `apps/mission-ui` on the real
`planner-v1` release (Cloudflare Pages). Scientific status: partial.

**What we're building ([ADR-0005](docs/decisions/ADR-0005-mission-planning-workflow.md), owner's call 2026-11-14):**
a **mission planning workflow**. A scientist picks a NASA Moon-to-Mars
objective and the months of the trip, and we take them step by step to a field
plan on Earth: (1) objectives, (2) site finder and compare, (3) gaps and what
Earth can't test, (4) logistics, (5) risks, (6) past analog missions. Per-trait
verdicts (match, miss with the gap, unknown), never a single site score. It
replaces the earlier ARL ladder ([ADR-0002](docs/decisions/ADR-0002-analog-readiness-levels.md), superseded).
Plan: [docs/plan/MISSION-PLANNER.md](docs/plan/MISSION-PLANNER.md). Data
pipeline: [docs/plan/DATA-PIPELINE.md](docs/plan/DATA-PIPELINE.md).
Scope for the 48 hours: [ADR-0003](docs/decisions/ADR-0003-hackathon-delivery-scope.md).
[ADR-0004](docs/decisions/ADR-0004-evidence-backed-comparison.md), a proposed
redesign, was deferred by the owner on 2026-11-14 (#46).

## What works today

You can open the planner, pick a Moon or Mars objective and months, and get every
Earth hexagon's result per trait: **match**, **miss** (with the gap) or
**unknown** (with the reason). Then compare up to three sites, see what Earth
can't test, logistics and risks, and export a brief.

| Piece | Where | Landed in |
|---|---|---|
| Six-step planner in the browser, on real data | `apps/atlas/planner.html` | #132 (PR #149) |
| Planner engine (verdicts, funnel, shortlist, logistics, risks, brief) | `services/engine/src/planner/` | #132 (PR #149), on #85 |
| Release step that publishes hashed data for the browser, plus 459 golden cases checked in both Python and the browser | `planner.release`, `npm run check:planner` | #132 (PR #149) |
| Assembled Earth tables: 91,800 land hexagons, yearly and monthly traits, EONET hazards | `services/ingest` (`p0ingest.assemble`) | #69 (PR #73), refreshed in #127 |
| Six cited past analog campaigns | `data/campaigns/` | #60 (PR #63) |
| Calibration: do past campaign sites pass their own objective? | [docs/qa/CALIBRATION.md](docs/qa/CALIBRATION.md) | #23 (PR #178) |
| Lean proofs S1, S2, S4, S5, S6 and S7 (the funnel rules the engine follows) | `proofs/Analog/` | see [STATEMENTS.md](proofs/STATEMENTS.md) |
| Shared JSON contracts between engine and app | `contracts/` | #78 (PR #79) and earlier |

**What it doesn't do yet**, so nobody over-reads it:
- **No single site score.** That's on purpose (AGENTS.md rule 4).
- **Science is partial.** Source quality checks are still open (#76). Some
  traits have no accepted band yet, so they show as unknown. For Mars OP-5LM
  that means no site gets a Pareto layer (see the calibration write-up).
- **Not in main yet:** S8 proofs (past-mission closeness, PR #140), the campaign
  optimizer (PR #172) and the new feature tables (PR #168).
- **Hosted CI is down** (#139, a billing issue), so checks are run locally with
  saved receipts ([docs/qa/LOCAL-CHECKS.md](docs/qa/LOCAL-CHECKS.md)).

A Lean proof covers the rules on the values it's given. It doesn't show that
the source data or the bands are scientifically right.

Deferred ADR-0004 material, kept for reference: [status](docs/STATUS.md),
[coherence review](docs/design/coherence-review.md), [evidence design](docs/design/evidence-comparison.md),
[implementation plan](docs/IMPLEMENTATION-PLAN.md).
Delivery plan: [docs/PLAN-hackathon.md](docs/PLAN-hackathon.md) · pitch:
[docs/pitch/PITCH.md](docs/pitch/PITCH.md) · AI disclosure: [AI-USAGE.md](AI-USAGE.md).

## Agents: check in first

Post your identity check-in on the
[agents message board (issue #6)](https://github.com/andrewkoumoudjian/cosmic-consultants/issues/6)
before claiming any work — format in [AGENTS.md](AGENTS.md).
Then think out loud in the
[agents commons (issue #7)](https://github.com/andrewkoumoudjian/cosmic-consultants/issues/7):
questions, ideas, findings and challenges between agents.

## Start here

- [AGENTS.md](AGENTS.md) — binding rules for humans and agents
- [Research inventories](docs/research/01-nasa-data-catalog.md) — dated NASA APIs (01), challenge brief (02), literature (03), data.nasa.gov (05)
- [Original proposal](docs/proposals/04-monorepo-multiagent-lean-proposal.md) · [ADR-0001](docs/decisions/ADR-0001-scope-collaboration-lean-first.md) — historical rationale, with successor notices
- [Guarantee ledger](proofs/STATEMENTS.md) — exact mathematical scope and missing runtime/scientific links
- [Prep runbook 2026-11-13](docs/PREP-2026-11-13.md) — historical runbook
- [Mission planner plan](docs/plan/MISSION-PLANNER.md) — **current plan**: 6-step workflow, engine, UI, work orders
- [Data pipeline spec](docs/plan/DATA-PIPELINE.md) — every table, column, source and where it's stored
- [Hackathon plan](docs/PLAN-hackathon.md) — schedule and submission checklist (its ARL product section is superseded)
- [Space Apps rules + NASA Moon-to-Mars objectives](docs/research/07-spaceapps-rules-and-m2m-objectives.md) (doc 07)

## Verify the proofs

```bash
cd proofs
lake exe cache get
lake build
lake env lean Analog/Audit.lean   # standard axioms only
```

## Run the planner on real data

You need the assembled tables in `data/snapshots/_derived/assembled/`. Build
them with `python -m p0ingest.assemble` (`services/ingest`), or copy that folder
from the Drive mirror (`data/catalog/drive-links.json`). The engine checks
every file hash before use and stops on a mismatch.

```bash
# 1. Publish hashed data for the browser (needs pyarrow==18.1.0, pyyaml==6.0.2;
#    use Python 3.12 or 3.13, since pyarrow 18.1.0 has no 3.14 wheel)
cd services/engine
PYTHONPATH=src python -m planner.release ../../data/snapshots/_derived/assembled ../../apps/atlas/public/data/planner-v1

# 2. Build and check the app (Node 22.12 or newer)
cd ../../apps/atlas
npm ci
npm run build
npm test                # share-link codec + workflow tests
npm run check:planner   # 459 golden cases: Python and browser agree; hashes match

# 3. Serve it on your machine, then open http://127.0.0.1:4184/planner.html
cd ../..
python scripts/serve_planner.py apps/atlas/dist
```

### The new planner UI (`apps/planner`, ADR-0012)

Same engine, same data release, a redesigned seven-step flow (React, Base UI,
Motion and a three.js globe via globe.gl). It reads the release from step 1 above.

```bash
cd apps/planner
npm ci
npm run build   # typecheck + Vite build
npm test        # view layer and CSV export agree with the 459 golden cases
npx vite preview --port 4185   # then open http://localhost:4185/
```

The plan lives in the URL, so "Copy link" shares the exact plan. Steps 5–7 have
"Open in JSheets (.csv)", which saves the compared sites as a tidy table for
JSheets or any spreadsheet. The look is described in `apps/planner/DESIGN.md`.

Engine tests and the calibration:

```bash
cd services/engine
PYTHONPATH=src python -m unittest discover -s tests
PYTHONPATH=src python -m planner.calibrate ../../data/snapshots/_derived/assembled --out <dir>
```

## Verify the contracts

```bash
python -m pip install "jsonschema==4.23.0" "pyyaml==6.0.2" "h3==4.1.2"
python scripts/validate_contracts.py --self-test
```

CI runs the same check (`.github/workflows/ci.yml`, `contract-validation` job).
On Python 3.14, use `"pyyaml>=6.0.3"` instead: 6.0.2 has no 3.14 wheel and
needs a C compiler.

## Verify the atlas

```bash
cd apps/atlas
npm ci
npm run build        # type-check + static build
npm test             # share-link codec + workflow tests
npm run check:mock   # the older map's mock sites and no-single-score rule
```

Needs Node 22.12 or newer. The sites in `apps/atlas/mock/` are synthetic, and
the older map page (`index.html`) says so. That page's ARL ladder is superseded
by the planner (ADR-0005). To run every check with saved logs while CI is down:
`python scripts/local_checks.py --group contracts --group atlas --keep-going`.
