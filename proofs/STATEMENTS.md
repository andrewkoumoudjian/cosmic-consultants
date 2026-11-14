# Guarantee ledger: mathematics, runtime and scientific scope

Review correction: 2026-11-14, work order #43. Baseline `7ba4941`.
The `.lean` files and their frozen statements are unchanged. This ledger corrects
application claims; it does not freeze new statements or claim a fresh compiler
pass. [ADR-0004](../docs/decisions/ADR-0004-evidence-backed-comparison.md) was
**deferred by the owner on 2026-11-14 (#46)**; ADR-0001/0002/0003 govern the build.

## Existing formal results

| ID | Exact scope | Historical formal evidence | Runtime / scientific link |
|---|---|---|---|
| S1 | `Semantics`: real-valued loss vectors, loss envelopes, breakdown flags and dominance definitions/lemmas. | Recorded Lean-clean in scaffold `333c4cd`. | No measurement-to-loss implementation. Loss nonnegativity, dimension identities, mismatch completeness and missing-data handling are not all enforced by these types. |
| S5 | Moon/Mars share `TargetEnvelope` structure. | Definition/type construction, not an empirical cross-body equivalence theorem. | Does not establish compatible physical quantities, shared feature meaning or valid target instances. |
| S2 generic | `Screening`: conditional CVaR and worst-realisation optimization results. | Ported from FastOpt; historical audit. | No atlas algorithm/optimization instantiation. Prior solver comments do not describe an engine in this repository. |
| S2 atlas | `Atlas`/`AtlasProofs`: nonnegative weighted monotonicity; every finite candidate has a coordinatewise-no-worse frontier representative; no non-frontier candidate is a unique weighted minimizer. | Statements frozen at `42cfe45`; proofs merged as `eaabc9b`. | No executable screening procedure, physical loss construction or numeric conformance. Zero weights allow ties. Context/feature selection is external to these Props. |
| S3 generic | `Certificate.subopt_le`: optimization-objective gap bound under first-order inequality, feasibility, multiplier and residual hypotheses. | Ported proof, historical audit. | Not a measurement, numerical-roundoff or per-feature analogy-error bound. No applicable atlas optimization problem is specified. |
| S3 atlas (historical proposed obligation) | Original plan to have engine certificates satisfy `subopt_le`. | Never implemented or proved. | Out of hackathon scope (ADR-0003). Do not emit solver fields or advertise this guarantee without a new application design. |
| S4 | A candidate dominated by another member of the chosen set is not frontier. | `Semantics.not_frontier_of_dominated`, historical audit. | Does not prove a runtime computes that set/frontier correctly. |
| Prior corpus | Imported mathematical lemmas; some candidate modules deliberately not imported. | Dispositions in doc 06. | No application validity inferred from theorem names/imports. |
| S6 / ARL | `Readiness`: gate outcomes `pass/fail/unknown`; ARL = largest `k ≤ 6` with gates 1..k passing (gates 1–4 per required dimension, 5–6 per site); 15 Props S6a–S6u (weakest link, monotone, no compensation, site can't lift, unknown ≠ fail, cumulative + maximal, mismatch/irrelevant dims ignored, not rateable → no level, empty/all-unknown → 0). | Statement **frozen** at `28b166a` (#48). All 15 proved in `ReadinessProofs` (W9, #17): **Lean-clean** on the agent's local run (build exit 0; audit exit 0, only standard axioms). Owner re-run pending (AGENTS.md rule 1). | No engine computes it yet. Lean checks the ladder logic only, never whether a gate outcome is right about the real world. `limitingDimension`/`limitingGate` are not stated. |

Historical axiom-audit snapshots: scaffold recorded 8 theorems; prior work plus
Cantelli recorded 28; W2 `eaabc9b` recorded 31, all with only
`propext`, `Classical.choice`, `Quot.sound`, return code zero. These are prior
reports in Git history, not new runs by #43. W9 (#17) adds 15 S6 directives: Audit.lean now has 46, all
`propext`, `Classical.choice`, `Quot.sound`, return code zero (2026-11-14, local run).
No accepted proof may use `sorry`, `admit`, custom axioms or an unapproved escape.
Use the pinned toolchain and record the process return code itself.

`Atlas.lean` also mentions an agreement theorem between cell frontier and frontier
on the loss image as a W2 obligation. That theorem is not in AtlasProofs. It is a
remaining supporting obligation, not silently supplied by the three S2 proofs.

## Required application guarantees for the proposed product

These are review obligations, **not frozen Lean statements or completed checks**.
No single S3 proof can discharge all of them.

| Obligation | Future implementation | Required evidence / current status |
|---|---|---|
| Measurement meaning and provenance | Ingest adapters + manifest | Selected bytes/hashes, units/support/QA/uncertainty/dependencies; scientific review. Not implemented. |
| Physical fit and optional loss | Comparison rules in engine | Frozen rule, unit/support checks, boundary behavior, source-backed reference and synthetic tests. No physical interval silently treated as loss interval. Not implemented. |
| Required-feature completeness and missingness | Contract semantic validator + engine | Reject omissions/duplicates/broken refs; unknown/incompatible inputs cannot imply confirmed fit or fabricated losses. Target for new formal statements after semantics review. |
| Corroboration | Pair-specific evidence review | Compatible claim/quantity/support, lineage, reviewer/date/rationale; group counts alone insufficient. Not implemented. |
| Contextual shortlist | Optional engine view | Explicit universe/filter/ordered features/evidence category; preserve dossiers and equal-vector site identities. Compare optimized implementation with a simple independent reference. Not implemented. |
| Numeric conformance | Numeric policy + engine/checker | State finite representation, boundaries/rounding/uncertainty; connect exact Lean reals to runtime comparisons before claiming formal conformance. No implicit epsilon theorem. |
| Reproducible outputs | Batch runner + independent verifier | Pinned inputs/model/code, deterministic canonical output hashes, no unexplained network access during replay; manifest/semantic validation. Not implemented. |
| Claim-specific proof | New named Lean modules + runtime linkage | Freeze statement, prove, build/audit on pin, identify implementation and conformance check. Until then label tested/reviewed/unproved separately. |

Release records separate model revision, runtime validation, scientific review,
formal proof and runtime conformance. Provenance is not scientific validation;
passing tests are not a proof; a mathematical proof is not a verified application.
The contract design and implementation plan specify the next review boundaries.
