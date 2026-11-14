# Implementation plan — one reproducible evidence-backed comparison

> **Not the current plan.** This came with [ADR-0004](decisions/ADR-0004-evidence-backed-comparison.md), which the owner
> **deferred on 2026-11-14 (#46)**. We are building ARL (ADR-0002/0003); see
> [PLAN-hackathon.md](PLAN-hackathon.md). Kept as a record and as ideas to borrow.

Date: 2026-11-14 (America/Toronto). Work order: #43.
Status: **proposed after the ten local consistency corrections**. This is a plan,
not an implemented engine, approved release or executed experiment. The controlling
human approved the local changes for draft-PR feedback on 2026-11-14. Repository
adoption and implementation remain pending team feedback and further approval.
Implementation work orders must respect verified event rules and coordination.

Inputs: [ADR-0004](decisions/ADR-0004-evidence-backed-comparison.md),
[contract design](design/evidence-comparison.md),
[ten-point traceability](design/coherence-review.md),
[guarantee ledger](../proofs/STATEMENTS.md), and [status](STATUS.md).

## Outcome and scope

Deliver a batch command that recreates feature-level dossiers for a small,
explicit Earth candidate set and one narrow rehearsal task/body/target scenario.
A static viewer reads exactly those artifacts. Every result identifies its input,
requirement and rule versions, shows missingness/uncertainty and Earth limitations,
and states which checks are scientific review, runtime tests or formal guarantees.

Both bodies remain supported in the conceptual model; the first empirical run
validates only its chosen instance. No ARL, global grid, overall similarity score,
automatic discovery claim, solver certificate, Rust/WASM or API is in v0.
Pareto is optional after complete dossiers work. No existing scientific threshold,
known-site ranking or literature claim is adopted automatically.

## M0 — Approval, rule refresh and work-order reconciliation

The controlling human has approved the local diff for a draft PR. Team/owner
review must now approve or revise ADR-0004 and this plan before implementation.
A future merge alone must not conceal which decisions are superseded. Update
accepted/superseded status annotations on explicit adoption.

A0: fetch current official challenge Resources and submission/judging guides with
authenticated TLS, dates and hashes; verify NASA-source eligibility, build window,
prior-work disclosure, presentation requirements and deadline. Do not rely on old
dated counts/rules. Review existing #40/#42 independently; they are not merged by
this package and may change the baseline for later work.

Exit: approved policy and versioned rule-review note; reconciled work orders with
owners, dependencies and acceptance criteria. Stop if event eligibility or scope
is unresolved. No scientific result is generated here.

## M1 — Feasibility before selecting the first task

Research/data owner: compare a few candidate task components using source access,
reuse terms, matching physical quantities, spatial/time support, masks, calibration
requirements and available reference evidence. Record rejection reasons, including
why apparently similar proxies cannot yet be compared.

A possible starting component is terrain traversal over a named slope baseline.
It would assess only that component, not full Mars mobility/EVA readiness. Select
it only if actual Earth and target evidence support the comparison. Select a
bounded candidate set containing a source-backed reference and candidates that
exercise unknown/outside-tolerance outcomes where evidence permits. Do not select
or invent real-site outcomes to fill a test table; synthetic cases cover missing
edge cases separately.

Define taskId/revision, target scenario, candidate geometries, required features,
physical requirements and citations, measurement/statistic/support, comparison
rules, uncertainties and not-testable list. If a proposed dimension has several
features, keep their results separate. Explain why requirements are appropriate
for the rehearsal rather than copying lander engineering limits.

Permit labeled exploration with pinned provenance to discover viable quantities.
Keep exploratory artifacts separate from released results. Freeze a release
protocol before evaluation, including reference expectations and sensitivity
variants. Any subsequent change receives a new model revision and rerun; do not
adjust thresholds merely to retain familiar sites.

Exit: one reviewed, feasible task protocol and source-backed reference expectations.
Stop/narrow if required data or a justified comparison is unavailable. A partial
result with explicit unknowns is acceptable; a fabricated complete model is not.

## M2 — Versioned contracts and semantic validation

Contracts owner: translate docs/design into versioned machine-readable schemas.
Choose explicit versions/ids; retain the three existing schemas as legacy and
document their deprecation/migration. Do not reinterpret old `Envelope.lo/hi` or
force the new pipeline to emit meaningless solver fields.

Implement schemas for measurement, task requirement, comparison rule, assessment/
dossier, corroboration review, shortlist context and run manifest. Prefer small
composable definitions over copied enums. A task must list a nonempty required
feature set; every dossier must resolve every required feature exactly once.

Add semantic validators for cross-record references, unique ids, interval order,
quantity/unit/support compatibility, allowed status/value combinations, uncertainty
and boundary policy, snapshot identity/terms, and shortlist context. JSON parsing
alone is not acceptance. Missing/non-finite/incomparable values cannot become
confirmed fits or numeric zero. Permit usable field evidence without a raster.

Prepare a visibly synthetic fixture suite outside scientific snapshots: valid
minimal records; omitted/duplicate required feature; reversed interval; bad unit;
unknown support; invalid/non-finite value; broken snapshot/rule reference; stale
operability; contradictory evidence; unresolved corroboration. Freeze expected
accept/reject outcomes before engine optimization.

Exit: schema plus semantic tests pass for valid and intentionally invalid cases;
version/migration rules documented. Engine and viewer development depend on this.

## M3 — Bounded ingest and retained evidence

Ingest/data owner: implement only adapters needed by M1. Keep network/raster work
outside assessment functions. Use Python; use Rasterio windowed processing only
where the chosen input requires it. Avoid loading an entire global raster.

Retain exact selected raw bytes (or immutable documented assets), source URLs,
retrieval times, product/asset versions, hashes, applicable terms, QA/source masks,
native support and derivation versions. Store a tracked manifest under
data/snapshots/MANIFEST.json or an explicitly reviewed versioned equivalent.
Choose a durable approved blob location before publication: ignored local bytes
and live source URLs alone are insufficient for a fresh-checkout replay. Test
retrieval of the retained bytes and verification against the manifest.

Derived measurements must preserve valid support, units/statistic, observation
times, uncertainty and lineage completeness. No resampling/filling may masquerade
as new observed coverage. Documentation-page hashes are not scientific-asset hashes.
License-text matches are not blanket publication clearance; review selected terms.

Exit: a bounded measurement set validates against M2; every used value resolves
to retained evidence; replay can run without changing live upstream responses.
Explicitly report absent/invalid measurements and unresolved terms.

## M4 — Readable Python assessment engine

Engine owner: create a packaged Python batch CLI in services/engine with a
reproducible dependency lock/environment during the implementation window. Use
NumPy for array operations where warranted; a simple readable reference evaluator
is the behavioral baseline. No distributed framework or database is required.

Proposed internal responsibilities (names are provisional until the work order):

- input/manifest validation and typed record loading;
- compatibility and physical-fit predicates per frozen comparison rule;
- optional approved feature-loss transforms;
- evidence-review attachment, separate operability/history and limitation records;
- dossier construction, canonical serialization and output manifest.

Keep these functions deterministic and separate from network/filesystem adapters.
Require exact task/model/schema versions. Define inclusivity, finite numeric
representation, conversion precision, uncertainty crossing thresholds, rounding
and equality before execution. Prefer an explicit unknown/uncertain result over
an invented confidence percentage. Do not insert ad hoc epsilon dominance.

Tests must cover field-only usable evidence, invalid/missing inputs, unit/support
conflicts, new contradictory observations, required-feature completeness, no
cross-objective aggregation and no solver/ARL fields. Check source-backed reference
expectations without asserting frontier membership; freeze input/output regression
cases separately from model calibration. Report disagreements.

Exit: one command produces complete, validated dossiers for the M1 universe,
including explicit unknowns; an independent reviewer can trace one feature from
input bytes through requirement/rule to its output. Runtime status is tested,
scientific status reviewed/partial as appropriate; formal conformance is separate.

## M5 — Optional contextual Pareto view

Depends on M4 and a reviewed optional loss model. If the loss model is unjustified,
ship dossiers without Pareto rather than inventing aggregation to enable it.

Keep the complete dossier artifact. Serialize task/body/model, candidate-universe
hash, ordered comparable feature list, eligibility filter, evidence category and
numeric policy. Partition before filtering. Produce included/excluded ids and
reasons; duplicates in vector values do not collapse distinct site identities.

Start with an independent simple reference algorithm on small synthetic sets.
Validate any faster implementation against it, including randomized cases after
deterministic edge cases. Test empty/single sets, equal vectors, dominated reference
sites, context changes and the two-category counterexample in coherence-review.md.
Unknown vectors remain visible but cannot accidentally enter a complete-data view.

Measure runtime and peak memory on the actual bounded input. Avoid a global
all-pairs allocation. Optimize the algorithm/data access before adding Rust. Any
native implementation later must preserve the same contract and reference tests.

Exit: contextual results match the reference, preserve all dossiers and carry no
global-optimality or universal screening claim. Omit this milestone if late.

## M6 — Formal properties linked to the implemented model

Start statement review after M2 semantics; proofs can proceed alongside M3/M4.
Create new statement IDs/modules; never edit frozen S1/S2 to fit the implementation.
Candidate obligations: an absent/incompatible required observation cannot imply
confirmed fit; required features cannot silently disappear; permanent mismatches
cannot enter scored features; contextual shortlist semantics use exactly the
declared universe/features and preserve retained-dossier identity.

Formalize only propositions whose domain, assumptions and intended application
are clear. Prove selected statements and run the pinned build/axiom audit with
direct exit-code capture; owner reruns before accepting a proof claim. Explain the
mapping from runtime representation to mathematical values. If that mapping is
not proved, record conformance as tested or pending even if the abstract theorem
is proved. No `subopt_le` application exists merely because loss values are numeric.

Exit: each claimed guarantee has statement/proof references, actual build/audit
evidence, runtime function/version, representation assumptions and conformance
status. Unfinished proof work blocks that formal claim, not an honestly labeled
tested comparison under ADR-0004. No certified label without the full linkage.

## M7 — Replay, scientific review and minimal viewer

Verify hashes from retained inputs, run in a clean pinned environment with network
disabled during computation, and compare canonical scientific output hashes.
Keep volatile execution timestamps/logs separate from deterministic result bytes.
Have another reviewer assess source suitability, task applicability, proxy limits,
uncertainty and one full trace. Separate calibration cases from independent checks.
Run predeclared sensitivity variants; report changes without choosing the variant
that produces the preferred sites.

Build a static TypeScript viewer in apps/atlas only after a validated dossier is
available. Start with a readable comparison table and a small map; no required
Worker API, reweighting or readiness heatmap. Show task/component, fit states,
units/support, source evidence, uncertainties, dated operability/history and
permanent limitations. Context and exclusions must be visible if Pareto exists.
Mark any development fixture as synthetic and keep it out of empirical results.

Exit: reviewer can regenerate the result and explain every displayed claim.
Document actual tests/proof statuses. Prepare restrained submission copy from the
existing artifacts, verify official rules again and obtain release approval.
Deployment/submission and any PR/merge remain separately authorized actions.

## Existing backlog: proposed migration, not remote edits

| Existing work order | Proposed handling after adoption |
|---|---|
| #1 A0 | Keep; verify current rules and record evidence before dependent work. |
| #5 W4 corpus | Narrow to the selected task and dated search scope; resolve old claim through board/owner first. |
| #15 W10 contracts | Replace ARL extension with M2 record schemas/migration and validators. |
| #16/#17 W8/W9 S6 | Hold ARL work; owner decides whether to supersede with M6's new statement/proof work orders. |
| #18 W5 envelopes | M1 physical task requirements and explicit comparison rules; no raw/loss conflation. |
| #19 W6 ingest | M3 bounded adapters, retained bytes and measurement support. |
| #20 W7 engine | M4 Python dossier evaluation; M5 separate if justified. |
| #21 W11 atlas | M7 artifact viewer; no global-heatmap prerequisite. |
| #22 W12 site evidence | Claim-specific review/search scope, operability/history separate from fit. |
| #23 W15 calibration | Separate synthetic algorithm, scientific reference and regression cases; no mandatory survivors. |
| #24/#25 pitch/submission | Use actual artifacts, verified rules and qualified claims after M7. |

Before revising or closing any issue, read its latest discussion/owner status and
announce the change on #6. One issue/branch/PR per implementation work order; split
these milestones into reviewable lane tasks. No contributor is reassigned by this
table. #43 creates no follow-up implementation issues or PRs automatically.

## First release definition of done

- A documented narrow task with justified physical requirements and a frozen model.
- A bounded named universe; all required features assessed or explicitly unknown.
- Traceable retained inputs, reviewed terms and a successful clean replay.
- Schema/semantic validation, meaningful algorithm/reference/regression checks.
- Explicit scientific review and formal/runtime-conformance status per claim.
- All dossiers preserved; any shortlist has its full comparison context.
- Static display and copy that match the implemented scope and uncertainty.
- Team feedback and explicit approval before implementation, merge or release;
  current approval covers publication of this proposal as a draft PR only.

If these cannot be met, release no fabricated completeness: present the exact
partial research/comparison achieved, with blockers and retained failed evidence.
