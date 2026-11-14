# Ten-point coherence review: change traceability

> **Not the current plan.** This came with [ADR-0004](../decisions/ADR-0004-evidence-backed-comparison.md), which the owner
> **deferred on 2026-11-14 (#46)**. We are building ARL (ADR-0002/0003); see
> [PLAN-hackathon.md](../PLAN-hackathon.md). Kept as a record and as ideas to borrow.

Date: 2026-11-14 (America/Toronto). Work order: #43.
Status: controlling human approved the local changes; draft PR for team feedback.
Repository adoption, merging and implementation remain pending.

The user approved the ten recommendations and the small-comparison direction.
This package actions the policy/documentation/fixture corrections and specifies
the contract migration. It does not present future engine/schema/Lean work as
completed. [ADR-0004](../decisions/ADR-0004-evidence-backed-comparison.md) is the
proposed superseding decision; original ADR bodies and frozen Lean are preserved.

| # | Finding | Correction in this package | Later implementation check |
|---|---|---|---|
| 1 | Optimization bound advertised as per-feature/scientific score error | ADR-0004 §7; README and pitch remove the promise; guarantee ledger distinguishes optimization, numeric and measurement error. | No legacy solver certificate emitted without a defined optimization and satisfied hypotheses. |
| 2 | Field evidence cannot bypass a cumulative raster-first ladder | Contract design makes field evidence eligible for presence/fit/corroboration; mandatory ARL deferred; doc 08 gate-bypass language removed. | A field-only usable measurement can produce a fit assessment; no fabricated global data. |
| 3 | One ARL mixes fit, evidence, access and campaign history | Separate dossier assessments; no ARL v0. Monotonicity restricted to preserved predicates; new contrary evidence may lower fit. | Conflicting/new evidence changes the relevant assessment without automatic promotion. |
| 4 | Global frontier can remove a higher-evidence candidate | Shortlists operate only within a versioned task/eligibility/evidence context; candidates retained. | The two-category example below retains B in its own context. |
| 5 | Familiar sites required to survive Pareto filtering | Golden fixture keys now identify pending reference cases; synthetic/scientific/regression tests separated. | Dominated reference remains visible and can be absent from shortlist without failure. |
| 6 | Formal screening claims exceed theorem/runtime link | Guarantee ledger lists exact theorem scope, missing links and future invariants; no end-to-end certification claim. | Each claimed runtime property has named implementation, evidence, numeric policy and proof/conformance status. |
| 7 | Physical bounds, losses and dimension aggregation conflated | Contract design separates measurement, physical requirement, comparison rule and assessment. Legacy schemas not reinterpreted. | Reject incompatible units/support and omitted required features; physical interval and optional loss distinct. |
| 8 | Dataset/group counts treated as corroboration | Doc 08 and contract design require review of a specific claim/pair, valid support and dependencies. Existing generated counts remain discovery hints. | Unresolved lineage or a different feature does not automatically pass corroboration. |
| 9 | Missing literature becomes universal novelty; hashes become geology certification | Restrained README/pitch and dated search-scope requirements. Fieldwork can confirm or refute. | All absence statements qualified; source traceability and scientific review recorded separately. |
| 10 | Status, gates and planned checks conflict | Accepted-history annotations; proposed superseding ADR; STATUS page; revised onboarding/plan; direct CI audit exit capture. | Distinguish parsing, schema validation, semantics, runtime tests, formal proof and hosted CI. |

## Counterexamples retained for implementation acceptance

These are **synthetic reasoning cases**, not scientific observations, snapshots
or an executable engine. Values are illustrative and carry no physical unit.

1. Candidate A has loss `(1,1)` and evidence category `single-source`; B has
   `(2,2)` and `reviewed-corroboration`. Assume both fit the illustrative task.
   Global Pareto filtering retains only A. Within B's evidence category B is
   frontier. Required behavior: preserve both dossiers and compute contextual views.
2. The old gate vector `[false,false,false,true,true,true]` has cumulative level
   zero. Field/campaign evidence cannot bypass lower gates under that definition.
   Required behavior: assess usable field evidence directly; do not compute ARL v0.
3. A reference site with `(2,2)` is dominated by another candidate with `(1,1)`.
   Required behavior: the reference dossier stays visible; frontier exclusion is
   permitted and is not a failed scientific reference test.

## Review boundaries

- The controlling human approved this diff for team review. Historical ADR
  acceptance is not repository adoption of ADR-0004, and no claim of consensus
  from other contributors is made.
- Original `.lean` files, toolchain/manifest, contract JSON, catalog rows, feature
  builders/CSVs and snapshots are unchanged. No new thresholds or ratings exist.
- New machine-readable schemas, validators, formal statements and runtime tests
  are scheduled in [the implementation plan](../IMPLEMENTATION-PLAN.md), not
  disguised as completed work here. CI maintenance does not verify a new model.
- Existing issue text is historical until the owner approves its migration.

## Local validation executed for #43

On 2026-11-14 the final local checks returned exit code zero:

```text
PASS 20 UTF-8 files; 4 JSON files + workflow YAML; 5 reference identities/coordinates preserved; 122 protected files unchanged; historical ADR bodies preserved; 59 local Markdown targets; 10/10 finding mappings; successor proposed
PASS audit-shell: 7 mocked success/failure cases, including exact process exit code 7
PASS git diff --check
```

The protected-file comparison covered frozen Lean sources/pins/config, legacy
contract JSON, registry/snapshots and generated feature inputs, normalizing only
Git checkout CRLF/LF differences. The local-link check excluded pre-existing
`/home/drew` links in retained historical documents; those links were not claimed
portable. Reference locations/body associations/topics were preserved, not newly
verified against scientific sources.

The CI shell was exercised with a fake `lake` function: standard axioms, a standard
subset and axiom-free output passed; process failure, empty output, a custom axiom
and trailing unexpected text failed as expected. Git Bash initially could not
start under the sandbox; the same bounded tests passed outside that sandbox.
This tests shell control flow and whitelist handling, not Lean itself. The workflow
now captures Lean's own status directly and labels JSON checks as syntax only.

No actual Lean build/audit, new executable schema validator, engine/scientific run
or hosted CI was executed for this draft. Those results remain unclaimed.
