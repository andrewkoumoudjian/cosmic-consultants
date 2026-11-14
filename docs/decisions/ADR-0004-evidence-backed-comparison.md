# ADR-0004 — Small reproducible comparisons and explicit guarantee boundaries

Date: 2026-11-14 (America/Toronto). Work order: #43.
Status: **proposed — draft PR for team feedback**. The controlling human approved
the resulting changes on 2026-11-14 and wants others to review the implementation
plan before implementation. No repository adoption, merge or implementation is
authorized by that approval.

On acceptance this ADR supersedes ADR-0001's universal proof-before-exploration
gate and score-certificate promise; ADR-0002's mandatory ARL ladder and global
readiness product; and ADR-0003's three-objective global P0 and unproved-S6
fallback. Unchanged historical decisions and proof statements remain intact.
Until explicit adoption, ADR-0001/0002/0003 remain the accepted baseline.

## Context

The initial proposal reused optimization mathematics before specifying its
scientific application. Later plans added a cumulative readiness ladder and
global map without reconciling field evidence, loss definitions, objective-level
selection and executable guarantees. The user approved correcting all ten issues
and asked for a smaller, reproducible evidence-backed comparison.

ADR-0002 and ADR-0003 were accepted by merge #26 (`5da36ce`), as recorded on
[the coordination board](https://github.com/andrewkoumoudjian/cosmic-consultants/issues/6)
("Merged: hackathon plan", 2026-11-12T19:36:15Z).
If that comment link is unavailable, the adding commit and their original
merge-acceptance clauses are the historical record. This ADR is a new decision,
not an edit to those earlier decision bodies.

## Decisions on adoption

1. **Small first, extensible later.** Validate one narrowly specified rehearsal
   task for one body/target scenario and a bounded, named Earth candidate set.
   Choose it by accessible, reusable and scientifically comparable evidence.
   Support both bodies in the design without requiring simultaneous global runs.
   Global grids, H3, multiple objectives and deployment scale are later choices.
2. **Evidence dossier is the product.** Keep environmental fit at feature level,
   evidence support, operability and campaign history separate. Do not compute an
   overall similarity score or ARL in v0. A future optional ordinal summary needs
   a new ADR and reviewed semantics. Field evidence may support presence, fit and
   corroboration; it is not a gate-4 workaround for missing raster gates.
3. **Separate physical meaning from transformations.** Adopt the conceptual
   measurement → task requirement → comparison rule → assessment model in
   [the contract design](../design/evidence-comparison.md). Define quantity,
   units, support, QA, uncertainty, provenance and absence before a loss transform.
   Physical limits and loss intervals are different objects. No unreviewed
   aggregation of features into broad dimension scores.
4. **Review corroboration claim by claim.** Dataset counts/group labels only
   identify potential checks. Review quantity/scale/time compatibility, upstream
   dependency versions and actual valid support. Keep unresolved lineage explicit.
   A second feature in the same broad dimension is not automatically corroboration.
   More evidence can overturn an assessment. Monotonicity is asserted only under
   explicit preservation of predicates, never for arbitrary new observations.
5. **Shortlists are optional contextual views.** Preserve all candidate dossiers.
   Compute Pareto views only after choosing task/body/model, required feature set,
   eligibility and evidence category. Record that context and every exclusion.
   No global Pareto deletion before partitioning; no comparison of incompatible or
   incomplete vectors. Equal vectors retain distinct site identities.
6. **Reference sites are evidence checks.** Known analogs need not be frontier.
   Distinguish synthetic algorithm tests, source-backed reference expectations,
   and versioned snapshot regression tests. Freeze expectations before evaluation;
   report disagreements and do not tune thresholds to retain familiar sites.
7. **Guarantees must match their object.** Retire the promise that `subopt_le`
   bounds scientific/per-feature score error. It bounds an optimization objective
   gap under its hypotheses. No applicable atlas optimization problem is defined.
   Keep the theorem as prior mathematics. Separate measurement uncertainty,
   model applicability, numerical error and optimization gap. Do not emit legacy
   solver certificates or invented solver residuals for dossier runs.
8. **Two assurance tracks.** Permit provenance-backed exploratory research to
   discover meaningful measurements and assumptions, labeled `exploratory` and
   kept out of released scientific results. Before release, freeze task,
   requirements, conversions, thresholds, candidates, schemas and numeric policy;
   rerun from pinned inputs and review scientific validity separately from code.
   Lean remains the authority for formal claims: statement freeze, pinned build,
   owner rerun and axiom audit are required before claiming a property proved.
   A tested runtime result may be published with an explicit unproved/conformance-
   pending status; it may not be called certified. No unproved theorem is treated
   as a passed release check. A specifically promised formal property blocks that
   claim until its proof and runtime link are established.
9. **Conservative communication.** Say what the task rehearses and cannot rehearse.
   Provenance establishes traceability, not geological correctness. Literature
   absence means only no relevant characterization found in the reviewed sources,
   with dated search scope. Neither universal novelty nor guaranteed campaign
   success/promotion follows. No NASA endorsement or validated readiness scale is
   implied by objective identifiers.
10. **Batch architecture and honest status.** Use a maintained Python batch
    engine with NumPy where useful; separate ingest from assessment and optional
    shortlist computation. Emit versioned static artifacts for a small TypeScript
    viewer. Add Rust only for a measured bottleneck or approved browser-execution
    requirement; add an API only for a demonstrated runtime need. Maintain
    [implementation status](../STATUS.md) and a theorem-to-runtime guarantee ledger.
    Existing contract JSON remains legacy until a versioned migration is reviewed.

## Authority and review

Applicable law/event rules and explicit human constraints are not changed by this
ADR. Verify current challenge/submission rules; retain the recorded pre-window
restriction on new runtime, executable contracts and Lean work until the permitted
build window. This package contains research/design, fixture metadata and CI
maintenance only, not scientific execution or new algorithms.

Within adopted project policy, applicable later ADRs supersede named earlier
decisions. AGENTS.md and current status/plan must reflect that policy. Proposals,
dated runbooks and old issue descriptions are historical context, not competing
specifications. If an instruction conflicts, report and resolve it before the
dependent change; never silently reinterpret a frozen statement.

This draft changes no remote backlog issue, existing PR, accepted Lean statement,
dataset snapshot or feature mapping. Work-order migration is proposed in the
implementation plan. The approved changes may be published as a draft PR for
feedback. Merging, implementation and deployment wait for further explicit approval.

## Alternatives and costs

- Keep the global ARL plan: rejected for the initial implementation because it
  combines unresolved scientific/evidence/access semantics and exceeds established
  data coverage. It remains preserved as historical design.
- Start with the Rust/WASM engine: defer until runtime measurements or an actual
  browser requirement justify the additional build/integration cost.
- Remove formal methods: rejected. Narrow formal claims are valuable, but importing
  mathematics alone does not establish applicability or runtime conformance.
- Retain one composite readiness number: defer. Separate assessments are more
  verbose but expose unknowns and conflicting evidence without false ordering.

## Acceptance evidence and consequences

[Review traceability](../design/coherence-review.md) maps every finding to the
local corrections. [Implementation plan](../IMPLEMENTATION-PLAN.md) defines the
future contracts, ingest, engine, formal and viewer milestones and their checks.
The reviewed draft deliberately implements no new scientific model or runtime.
Existing Lean source/toolchain/manifest and existing executable contract schemas
are unchanged. Test results must identify executed checks versus future acceptance
criteria; no fresh proof-clean claim is made by this decision record.
