# cosmic-consultants

Monorepo for the NASA Space Apps Challenge 2026 — **Identify Earth Locations
that Analog the Permanent Moon Base Locations and Mars**.

**What we're building ([ADR-0002](docs/decisions/ADR-0002-analog-readiness-levels.md), accepted):**
an atlas organized around **Analog Readiness Levels** (ARL). ARL is a 0–6 ladder,
like NASA's technology readiness levels but for test sites. It rates how ready
each Earth site is to rehearse a specific NASA Moon-to-Mars objective. Every
level shows its per-trait vector, the trait that limits it, and what Earth
cannot rehearse (gravity, vacuum or thin air, radiation). Never a single score.
Scope for the 48 hours: [ADR-0003](docs/decisions/ADR-0003-hackathon-delivery-scope.md).
[ADR-0004](docs/decisions/ADR-0004-evidence-backed-comparison.md), a proposed
redesign, was deferred by the owner on 2026-11-14 (#46).

What exists: research, dataset discovery/probe tools, proposed feature mappings,
legacy JSON schemas and selected Lean proofs. The ingest, engine, API and map
directories contain placeholders. There is no executed atlas comparison, ARL
implementation or end-to-end certified runtime. A proof about supplied losses
does not establish scientific accuracy. The generic optimization bound is not a
bound on a site's measurement or analogy error.

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
- [Hackathon plan](docs/PLAN-hackathon.md) — **current plan**: ARL product, schedule, backlog W5–W15 (#15–#25), submission checklist
- [Space Apps rules + NASA Moon-to-Mars objectives](docs/research/07-spaceapps-rules-and-m2m-objectives.md) (doc 07)

## Verify the proofs

```bash
cd proofs
lake exe cache get
lake build
lake env lean Analog/Audit.lean   # standard axioms only
```
