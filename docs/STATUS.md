# Implementation and decision status

Review baseline: `7ba4941`. Local review package: #43,
`codex/coherence-review`, 2026-11-14 (America/Toronto).

## Decision authority

ADR-0001 is accepted. ADR-0002 and ADR-0003 were accepted by merge #26
(`5da36ce`); their status annotations now correct the stale proposed labels.
Their substantive bodies are preserved as historical decisions.

[ADR-0004](decisions/ADR-0004-evidence-backed-comparison.md) is **proposed**.
The controlling human approved the concrete local changes on 2026-11-14 and
wants team feedback before implementation. This package is being published as a
draft PR; repository adoption remains pending. The redesigned documents describe
a review target, not an already merged policy or working product. Until adoption,
earlier accepted policies remain operative. No merge or implementation is authorized.

## What exists versus what is proposed

| Component | Present at baseline | Proposed target / assurance boundary |
|---|---|---|
| Research | Challenge/source inventories and proposed feature mappings | Choose one task from evidence feasibility; source descriptions are not site measurements. |
| Registry | Candidate YAML, probe helpers/logs, triage and generated summaries | Recheck selected assets/terms at use; HTTP success and text matches do not prove suitability. |
| Scientific snapshots | Registry/documentation evidence; no executed atlas dataset pipeline | Retain selected scientific input bytes and a content-addressed manifest; no fabricated fills. |
| Lean | S1/S2/S4/S5-related definitions/proofs and prior mathematics | Historical build/audit evidence exists; no new proof or local fresh pass in #43. Runtime links remain absent. |
| Contracts | Three legacy JSON schemas | Conceptual replacement in docs/design; executable replacement schemas and validators are not implemented. |
| Fixtures | Five named reference locations | Pending source-backed expectations; none is required to survive Pareto filtering. |
| Ingest / engine | `.gitkeep` placeholders | Python ingest and assessment batch program in future work orders; no runtime or numeric model implemented. |
| ARL / S6 | Historical design proposal accepted through ADR-0002; no implementation | Deferred under proposed ADR-0004; no level assigned and no new theorem claimed. |
| Viewer / API | `.gitkeep` placeholders | Static viewer after one reproducible comparison; API only if needed. |
| CI | Lean build/audit configuration and JSON parsing | Local change captures audit process status directly. JSON parsing is not schema/semantic validation. Hosted CI has not run on this local draft. |

## Existing work and history

PR #40 (measurement lineage) and PR #42 (licence evidence/UTF-8) were open when
the board was read for #43. They remain separate, unmerged and unmodified by this
package. Their scientific conclusions do not become accepted through a reference
here. Do not copy their generated registry changes into this branch.

Old work orders #15–#25 are not silently reassigned or rewritten. The proposed
mapping and dependency changes are in the implementation plan. A local document
is not proof that a remote issue was changed or that another contributor agreed.

## How to verify this draft

Review [the ten-point traceability](design/coherence-review.md),
[contract design](design/evidence-comparison.md),
[guarantee ledger](../proofs/STATEMENTS.md), and
[implementation plan](IMPLEMENTATION-PLAN.md).

Inspect `git diff` in the isolated worktree. Parse fixture JSON and workflow YAML,
check local Markdown links, verify baseline scientific inputs/Lean/contracts are
unchanged and run `git diff --check`. The final review report must name actual
command results. Full Lean build/audit and hosted CI are separate checks; do not
infer a pass from this checklist or from unchanged proof files.
