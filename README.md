# cosmic-consultants

Monorepo for the NASA Space Apps Challenge 2026 — **Identify Earth Locations
that Analog the Permanent Moon Base Locations and Mars**.

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

What exists (main at `343969b`): research, dataset registry and probes, JSON
contracts, Lean proofs (S1, S2, S4, S5, S6), the Earth trait table for 91,800
hexagons (`services/ingest`, #54) and the atlas map on mock data (`apps/atlas`,
#53). Not built yet: the monthly and context tables, the past-campaign table,
the planner engine and the workflow UI (see the plan's work orders). A proof
about supplied losses does not establish scientific accuracy.

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
npm run check:mock   # mock sites, ARL rule, no-single-score rule
```

CI runs the same two checks (`.github/workflows/atlas.yml`). Needs Node 22.12
or newer. The sites in `apps/atlas/mock/` are synthetic, and the app says so.
