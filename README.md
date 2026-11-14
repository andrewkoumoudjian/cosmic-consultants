# cosmic-consultants

Monorepo for the NASA Space Apps Challenge 2026 — **Identify Earth Locations
that Analog the Permanent Moon Base Locations and Mars**.

**Local redesign for review (#43):** compare a small, named set of Earth sites
for one specific exploration rehearsal task using reproducible evidence. Each
site dossier separates feature-level environmental fit, supporting evidence,
operability, campaign history and what Earth cannot reproduce. An optional
Pareto shortlist is a contextual view; it never deletes candidate evidence.

[ADR-0004](docs/decisions/ADR-0004-evidence-backed-comparison.md) proposes this
direction. The controlling human approved this change set for team feedback;
repository adoption remains pending. ADR-0001/0002/0003
are the accepted historical baseline; the ARL/global-atlas proposal is preserved
in those records. This is a draft review proposal; implementation and merging
remain on hold pending team feedback and explicit approval.

What exists: research, dataset discovery/probe tools, proposed feature mappings,
legacy JSON schemas and selected Lean proofs. The ingest, engine, API and map
directories contain placeholders. There is no executed atlas comparison, ARL
implementation or end-to-end certified runtime. A proof about supplied losses
does not establish scientific accuracy. The generic optimization bound is not a
bound on a site's measurement or analogy error.

Review [status](docs/STATUS.md), [the ten corrections](docs/design/coherence-review.md),
[contract design](docs/design/evidence-comparison.md), and
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

- [AGENTS.md](AGENTS.md) — coordination rules and the pending policy transition
- [Research inventories](docs/research/01-nasa-data-catalog.md) — dated NASA APIs (01), challenge brief (02), literature (03), data.nasa.gov (05)
- [Original proposal](docs/proposals/04-monorepo-multiagent-lean-proposal.md) · [ADR-0001](docs/decisions/ADR-0001-scope-collaboration-lean-first.md) — historical rationale, with successor notices
- [Guarantee ledger](proofs/STATEMENTS.md) — exact mathematical scope and missing runtime/scientific links
- [Prep runbook 2026-11-13](docs/PREP-2026-11-13.md) — historical runbook, not the redesign execution order
- [Hackathon plan](docs/PLAN-hackathon.md) — bounded proposed deliverable and rules-verification checklist
- [Space Apps rules + NASA Moon-to-Mars objectives](docs/research/07-spaceapps-rules-and-m2m-objectives.md) (doc 07)

## Verify the proofs

```bash
cd proofs
lake exe cache get
lake build
lake env lean Analog/Audit.lean   # standard axioms only
```
