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
| S7 / funnel | `Funnel`: verdict = matched/missed/unknown from a band (`lo ≤ x ≤ hi`, or `< hi` if strict) and an optional value; window rule over months (any miss → missed; else empty window or any unknown → unknown; else matched); survival = every must trait matched; funnel class; hard limits remove a site only on a known value over the cap. 11 Props S7a–S7i, S7z (match ⇔ known and inside, unknown ≠ match, tightening a band / adding a must / adding months never adds a site, nice never filters, class ⇔ survival, unknown limit kept, empty window). | Statement **proposed** (W21, #80): definitions and Props only, `lake env lean Analog/Funnel.lean` rc=0 on the pinned toolchain (2026-11-14, local). Not frozen, not proved. | Contract: `site-plan.schema.json` verdict rows (#78). The engine must conform via `golden-verdicts.json`; Lean reals are exact, while the published L4 values are Float32 (numeric policy still open). |
| S8 / closeness | `Closeness`: closeness = Σ over a fixed trait set of ((x−y)/scale)²; Shapley value of that sum game; optional closeness is undefined when a trait is missing. 7 Props S8a–S8g (≥ 0, zero ⇔ identical with nonzero scales, each Shapley share = own term, shares sum to closeness, shares ≥ 0, missing ⇒ unranked, share depends only on its own trait). | Statement **proposed** (W21, #80): `lake env lean Analog/Closeness.lean` rc=0 (2026-11-14, local). Not frozen, not proved. | ADR-0005 D5 bounded exception: past missions only. Does not claim closeness measures scientific similarity, or that the IQR scales are right. |
| S9 / pareto layers | `ParetoLayers`: multi-objective non-scalar Pareto layer peeling (`peelLayer`), unknown observation exclusion (`comparableSites`), and DP recurrence over dominance. 7 Props S9a–S9g (layer pairwise incomparable, strict dominance lowers layer index, equal vectors share layer, exhaustive unique partition, unknown dimension excluded from every layer, mutually incomparable trade-offs share layer 0 for any unused scalar `score` map, peeled layer equals `1 + max` dominating layers). | Statements co-committed at `c4425a0` (2026-11-15, #170; not a separate prior statement-only commit on `main` — governed by owner gate-sequence exception [`ADR-0013`](../docs/decisions/ADR-0013-s9-s10-freeze-gate.md)), unchanged from `c4425a0` through PR #172 HEAD: `Analog/ParetoLayers.lean` (sha256 `877b5362043ce9b1434826b439a0e68e4f65459f93758d23000735a70272168e`); all 7 proved in `Analog/ParetoLayersProofs` (W22, #170): **Lean-clean** on local pinned build (`lake build` rc=0, `Audit.lean` rc=0, `[propext, Classical.choice, Quot.sound]`, zero `sorry`/`admit`). Owner final re-run/acceptance recorded in PR #172. | Runtime link: `services/engine/src/planner/pareto_model.py` (`pareto_layers`, multi-objective target-gap builder with no scalar site score and unknown exclusion). Does not prove Earth/planetary physical unit/support equivalence. |
| S10 / campaign optimizer | `CampaignOpt`: Rockafellar–Uryasev multi-year CVaR campaign allocation (`CampaignProblem`, `EpigraphFeasible`, `CampaignFeasible`). 5 Props S10a–S10e (epigraph LP relaxation tight at `max(0, loss - t)`, tail-scenario screening exactness over `FeasibleWT`, convexity of campaign feasible region, computable `Certificate.subopt_le` dual suboptimality bound over `G_aug = [G_struct; -I]`, simplex sum and cap preservation). | Statements co-committed at `c4425a0` (2026-11-15, #170; not a separate prior statement-only commit on `main` — governed by owner gate-sequence exception [`ADR-0013`](../docs/decisions/ADR-0013-s9-s10-freeze-gate.md)), unchanged from `c4425a0` through PR #172 HEAD: `Analog/CampaignOpt.lean` (sha256 `475d0bda4033b1dfb4ae3963ffaed95129648d606ced9563b15ac6d51d1a12eb`); all 5 proved in `Analog/CampaignOptProofs` (W22, #170): **Lean-clean** on local pinned build (`lake build` rc=0, `Audit.lean` rc=0, `[propext, Classical.choice, Quot.sound]`, zero `sorry`/`admit`). Owner final re-run/acceptance recorded in PR #172. | Runtime link: `services/engine/src/planner/optimizer.py` (Rockafellar–Uryasev LP solver with dual certificate computation and multi-year `cells-r4-monthly-years` tail screening, allocating field days rather than scoring site similarity). |

Historical axiom-audit snapshots: scaffold recorded 8 theorems; prior work plus
Cantelli recorded 28; W2 `eaabc9b` recorded 31, all with only
`propext`, `Classical.choice`, `Quot.sound`, return code zero. These are prior
reports in Git history, not new runs by #43. W9 (#17) adds 15 S6 directives: Audit.lean had 46; #132 added 11 S7 directives; W22 (#170) adds 7 S9 + 5 S10 directives: `Audit.lean` now checks 69 theorems, all with only `propext`, `Classical.choice`, `Quot.sound`, return code zero (`2026-11-15`, local run).
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
