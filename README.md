# cosmic-consultants

Monorepo for the NASA Space Apps Challenge 2026 — **Identify Earth Locations
that Analog the Permanent Moon Base Locations and Mars**.

Approach: a *certified Pareto analog atlas*. Moon and Mars targets are fixed as
multi-dimensional envelopes; Earth's land surface is screened for matches with
the elimination step proved exact in Lean 4 (screening and suboptimality
certificates ported from the owner's `fastopt` proofs). Sites publish a
per-dimension analogy vector with explicit breakdowns — never a scalar score.

**Pitch direction (2026-11-12, [ADR-0002](docs/decisions/ADR-0002-analog-readiness-levels.md), proposed):**
the atlas is organized around **Analog Readiness Levels** — a TRL-like 0–6
ladder rating how ready each Earth site is to rehearse a specific NASA
Moon-to-Mars objective, with what Earth cannot rehearse listed alongside.
Hackathon plan: [docs/PLAN-hackathon.md](docs/PLAN-hackathon.md) · pitch:
[docs/pitch/PITCH.md](docs/pitch/PITCH.md) · AI disclosure: [AI-USAGE.md](AI-USAGE.md).

## Agents: check in first

Post your identity check-in on the
[agents message board (issue #6)](https://github.com/andrewkoumoudjian/cosmic-consultants/issues/6)
before claiming any work — format in [AGENTS.md](/home/drew/cosmic-consultants/AGENTS.md).
Then think out loud in the
[agents commons (issue #7)](https://github.com/andrewkoumoudjian/cosmic-consultants/issues/7):
questions, ideas, findings and challenges between agents.

## Start here

- [AGENTS.md](/home/drew/cosmic-consultants/AGENTS.md) — binding rules for humans and agents
- [Research inventories](/home/drew/cosmic-consultants/docs/research/01-nasa-data-catalog.md) — NASA APIs (01), challenge brief facts/requirements (02), literature (03), data.nasa.gov (05)
- [Proposal](/home/drew/cosmic-consultants/docs/proposals/04-monorepo-multiagent-lean-proposal.md) · [ADR-0001](/home/drew/cosmic-consultants/docs/decisions/ADR-0001-scope-collaboration-lean-first.md) — decided architecture: both bodies, GitHub Issues as system of record, Lean-first gates
- [Statement ledger](/home/drew/cosmic-consultants/proofs/STATEMENTS.md) — what is defined/proved, and what is not yet
- [Prep runbook 2026-11-13](/home/drew/cosmic-consultants/docs/PREP-2026-11-13.md)
- [Hackathon plan](docs/PLAN-hackathon.md) — ARL product, schedule, backlog W5–W15 (#15–#25), submission checklist
- [Space Apps rules + NASA Moon-to-Mars objectives](docs/research/07-spaceapps-rules-and-m2m-objectives.md) (doc 07)

## Verify the proofs

```bash
cd proofs
lake exe cache get
lake build
lake env lean Analog/Audit.lean   # standard axioms only
```
