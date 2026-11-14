# Evidence-backed comparison: contract design

> **Not the current plan.** This came with [ADR-0004](../decisions/ADR-0004-evidence-backed-comparison.md), which the owner
> **deferred on 2026-11-14 (#46)**. We are building ARL (ADR-0002/0003); see
> [PLAN-hackathon.md](../PLAN-hackathon.md). Kept as a record and as ideas to borrow.

Date: 2026-11-14 (America/Toronto). Work order: #43.
Status: **proposed for local review**, governed on adoption by
[ADR-0004](../decisions/ADR-0004-evidence-backed-comparison.md).
This is a contract migration design, not an executable schema or a frozen Lean
statement. The three existing JSON schemas remain legacy formats. Do not emit
new dossiers against them or silently reinterpret their fields.

## Scope and unit of comparison

Compare a bounded set of Earth sites for one narrowly described rehearsal task.
Record the target body, target region or scenario, task revision and required
features. A broad NASA objective is context, not a complete experimental protocol.
Keep Moon and Mars extensible through the same record structure; validate one
task/body instance first. A site result always belongs to a task/model revision.

The primary output is a dossier. Environmental fit, evidence support, operability
and campaign history are separate assessments. No overall similarity score,
mandatory ARL, or automatic readiness label is produced in the initial product.

## Records to formalize as versioned schemas during implementation

| Record | Required information |
|---|---|
| Measurement | Stable id; site/geometry; feature and physical quantity; value or explicit absence; unit; statistic; acquisition interval and sampling; spatial support/native resolution; QA and valid-data support; source kind; dataset/product/version/asset id and snapshot reference; derivation version; uncertainty and limitations; upstream dependencies and their roles/completeness. |
| Task requirement | Task/body/target identity and revision; required feature ids; physical unit and acceptable interval or categorical condition; spatial/time support; source citation; applicability to the Earth rehearsal; threshold rationale and reviewer. A published mission engineering limit is context until its relevance to this task is justified. |
| Comparison rule | Versioned id; input feature/quantity and unit compatibility; approved conversions; required QA/support; physical matching predicate; uncertainty treatment; optional feature-loss transform and orientation; numerical representation/boundary policy; reviewer and supporting evidence. |
| Feature assessment | Requirement/rule/model/measurement references; fit status; reason; evidence support; uncertainty and optional loss; incompatibilities and breakdowns. Keep both raw measurements and the derivation. |
| Corroboration review | A specific claim and measurement pair; quantity/scale/time/QA compatibility; versioned dependency relationships; review outcome and rationale; reviewer/date/citations. Different features in one dimension are not automatically corroboration. |
| Site dossier | Task and site identity; every required feature assessment; separate operability and campaign-history records; permanent mismatches; other task-specific limitations; literature-search scope; provenance; optional shortlist memberships and guarantee statuses. |
| Run manifest | Input asset hashes/retrieval dates/URLs/reuse terms; requirement/rule/schema/code versions; candidate universe; numeric policy; commands/environment; output hashes; validation results; scientific/runtime/formal statuses. A manifest is provenance, not an optimization certificate. |
| Shortlist context | Task/body/model revision; candidate-universe hash; explicit eligibility filter; ordered feature list; evidence category; loss/comparison policy; duplicate/tie handling; included/excluded ids and reasons. |

Draft field names are design vocabulary, not stable APIs. A contracts work order
must review and freeze machine-readable representations before engine/UI work.
The schema version must change rather than reinterpret legacy `Envelope` fields.

## Assessment states and missingness

Feature fit has the states `within-tolerance`, `outside-tolerance`, `unknown`,
`incomparable`, and `not-testable`. State reasons must be explicit. An absent,
invalid, out-of-coverage or unsupported measurement cannot yield a confirmed fit
or a fabricated numerical loss. Missing uncertainty is also explicit; it is not
zero uncertainty. An unvalidated proxy cannot silently become a direct match.

Evidence support is a structured record, not a rank. Record source kinds (remote
sensing, field, literature, model), claim-specific corroboration (`approved`,
`rejected`, `unresolved`, `not-assessed`) and field-characterization references
separately. Field measurements can establish presence, physical fit and reviewed
corroboration; they do not have to pass through a raster-only ladder first.
Source kind alone supplies no quality or independence guarantee.

Operability is `confirmed`, `restricted`, or `unknown`, with scope, date/season,
access/legal/safety evidence and reviewer. Campaign history is `documented`,
`not-found-in-reviewed-sources`, or `unknown`, with task relevance and dates.
Neither is inferred from environmental fit, and neither is a per-feature level.

Do not introduce an aggregate ARL in v0. Any later optional summary needs a new
ADR, schema and formal statement. If cumulative levels are reconsidered, field
evidence must be eligible for lower gates, site-wide conditions must be included,
and the monotonicity claim must mean preservation of passed predicates. New
contradictory evidence can lower a scientific assessment.

## Physical intervals and optional losses

Requirements are expressed in physical units. A comparison rule first checks
quantity, units, support and quality, then evaluates fit. A numerical loss is a
separate optional transform with a published scale; lower is better and zero
means agreement as defined by that transform. Physical bounds are not loss bounds.

Keep feature-level outputs. Do not average several slopes/material measurements
into a terrain/material loss without a separately reviewed aggregation rule.
Features that are not required for a task do not enter that task's shortlist.
Different models or feature masks cannot be compared by accident.

The numeric policy must specify finite-value checks, representation, interval
inclusivity, uncertainty crossing a boundary, rounding and equality. An epsilon
dominance rule must not inherit theorems about exact dominance without a new
argument; it can change transitivity. Until that policy and conformance checks
exist, report runtime outputs as tested rather than formally verified.

## Corroboration is a reviewed claim

`independenceGroup` is a registry discovery hint. A dependency graph can expose
known overlap; absence of recorded overlap is not proof of independence.
Check the applicable observation/pixel/time support and dependency versions.
Two datasets, different sensors, or two features in a broad dimension do not by
themselves establish independent corroboration of one requirement.

Adopt a pair only after reviewing comparability, known shared inputs, unresolved
lineage and the limited claim supported. `approved` means the named review
criteria were met, not statistically proven independence unless such a result
exists. Preserve contrary observations instead of selecting only agreeing pairs.
PR #40 is relevant proposed research; this design does not merge or automatically
adopt its source-specific conclusions. PR #42's reuse evidence is also separate
from scientific suitability.

## Optional Pareto shortlist

Preserve every assessed candidate and its dossier. A shortlist is a view within
one explicit context, not global deletion. Compare only the same required,
approved loss features under the same model/numeric policy and evidence category.
An evidence category is a named predicate over the structured evidence record
(for example, reviewed corroboration for every required claim), not a new level
or automatic ordering. Its definition is part of the context revision.
Unknown/incomparable/not-testable required features produce an exclusion reason
for that shortlist, not a bad numerical fill or deletion from the candidate set.
Sites excluded from a view remain available for evidence and reference review.

For exact losses, dominance means no worse on every selected coordinate and
strictly better on at least one. Equal vectors retain both site identities.
Changing eligibility, evidence category or required features recomputes the view.
Global filtering before evidence/task partitioning is prohibited.

Known analogs have no privileged frontier membership. Separate synthetic algorithm
tests, source-backed scientific reference cases and frozen regression cases.
Candidate-set changes may legitimately change a reference site's shortlist status.

## Publication and claims

Publish unknowns, source limitations, task-specific applicability and permanent
gravity/pressure/radiation breakdowns alongside every comparison. Provenance
supports traceability; it does not certify geological truth or permission to use
every asset on an archive. Review exact product terms before publishing derived
artifacts. Cite the source and preserve the selected bytes through the manifest.

Literature claims say "no relevant characterization found in the sources reviewed"
and include search date, queries, sources and coverage limits. Absence of a local
record is not evidence that no campaign exists. Further fieldwork can confirm or
refute a proposed analogy; it does not promise promotion or novelty.

## Acceptance conditions for the future contract implementation

- Every required feature appears exactly once per assessment context; omitted
  features, duplicate ids, broken references and invalid intervals are rejected.
- Missing/non-finite/incompatible inputs cannot produce a confirmed match or loss.
- Field evidence can support fit without a global raster; it remains subject to
  the same quantity/support/QA review.
- Physical intervals and losses are distinct typed/versioned records.
- Shortlist context and exclusion reasons are serialized and independently checked.
- A source-backed reference may be dominated without a test failure.
- Schema validation and semantic validators both run; JSON parsing alone is not
  reported as either. Synthetic examples are visibly labeled and never enter
  scientific snapshots or published empirical results.
