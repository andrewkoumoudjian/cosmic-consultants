# ADR-0005: The product is a mission planning workflow (replaces ARL)

Date: 2026-11-14. Status: **proposed** in work order #56. It takes effect when
the owner merges it. Decided by the owner (Andrew Koumoudjian) on 2026-11-14:
"you can supersede all the ARLs in the repo… our final plan is the mission
planning workflow."

Replaces: [ADR-0002](ADR-0002-analog-readiness-levels.md) (ARL) in full, and
the priority list in [ADR-0003](ADR-0003-hackathon-delivery-scope.md) D4.
ADR-0003 D2 (static-first, Python engine allowed) and D5 (freeze times) still
stand. [ADR-0001](ADR-0001-scope-collaboration-lean-first.md) is unchanged.
The full plan is in [`docs/plan/MISSION-PLANNER.md`](../plan/MISSION-PLANNER.md)
and the data pipeline spec in [`docs/plan/DATA-PIPELINE.md`](../plan/DATA-PIPELINE.md).

## Why

The team's planning doc settled on a workflow: a scientist starts from what they
want to test and ends with a field plan. The ARL ladder answered one question
("how ready is this place for this objective?"). It did not cover mission
timing, logistics, risks or past missions. Gates 4 to 6 also needed field
evidence we can't collect in a weekend. The workflow keeps the good parts of
ARL (per-trait honesty, "unknown" is never "bad", "Earth can't test this")
and drops the ladder.

## Decisions

**D1. Six steps, one plan.** Every screen, engine function and data table
belongs to one step:

1. Mission objectives: target body, NASA objective, month window, length,
   team size, hard limits.
2. Site finder and compare: which places meet the test requirements in that
   window. Compare up to 3 side by side.
3. Gaps: per trait, match, miss (and by how much) or unknown. Plus what Earth
   can't test at all.
4. Logistics: access time, protected land, field-season months.
5. Risks: natural hazards and harsh conditions, month by month.
6. Past missions: the closest earlier analog campaigns, and why they are close.

The output is a one-page **mission plan brief** the scientist can export.

**D2. Requirements are written in Earth units.** A test requirement is a band
on one Earth column, such as "night ground temperature ≤ 243 K". Each band says
where it came from: `target` (a number from a cited Moon/Mars envelope),
`precedent` (a number a cited past campaign reported), `team` (our stated
choice, with the reason written next to it) or `user` (set in the app). The
rules live in `data/requirements/trait-map.yaml`. The engine only ever compares Earth numbers with Earth-unit bands. This
removes the Moon-vs-Earth unit clash flagged in `data/envelopes/README.md`.

**D3. Per-trait verdicts, no site score.** For each site and requirement the
verdict is `match`, `miss` (with the gap: how far outside the band, in the
trait's unit) or `unknown` (no data or no band). There is **no single score
for a site**. The shortlist is the sites that pass the hard limits and that no
other site beats on every gap at once (the Pareto shortlist, already proved in
`proofs/Analog/Atlas*.lean`). The user can sort the shortlist by one trait at a
time. Sorting by one trait is not a combined score.

**D4. "Earth can't test this" is always shown.** Gravity, air pressure and
radiation are permanent mismatches. Each objective lists which ones matter for
it, and the brief prints them.

**D5. Two numbers that combine traits are allowed, always with their parts.**

- *Past-mission closeness (step 6).* The distance between a site and a past
  campaign site, over the traits both have. It is always shown split per trait
  with Shapley values (each trait's share of the difference). For our squared
  distance the Shapley value of a trait is exactly its own term, so the split
  is exact, not an estimate.
- *Campaign optimizer (plan only, P2).* The cost and risk of a multi-site field
  plan, solved with QUARCC `fastopt`. It plans field days. It never rates how
  Moon-like or Mars-like a place is.

Nothing else may add, average or weight traits into one number.

**D6. Approval readiness is a checklist, not a probability.** The "Congress
approval chances" idea becomes a checklist of things reviewers look for (tied
to a NASA objective, precedent at a similar site, permits, a season window,
cost band). Each item is yes / no / unknown with a source. We have no data to
calibrate a probability of approval, so we don't show one.

**D7. Lean.** The new concepts get one new statement, S7 (funnel): verdicts per
trait, `unknown` never counts as `match`, and tightening or adding a
requirement never adds sites to the shortlist. S7 is frozen before engine code
computes verdicts (AGENTS.md rule 1). The proved S6 (ARL) files stay in
`proofs/` as finished work (rule 6), but the product no longer uses them.

**D8. Contracts.** New schemas: `plan-request`, `trait-map`, `campaign`,
`site-plan` (contracts lane). `site.schema.json` `readiness[]` stays optional
for old fixtures and is no longer produced.

## What changes in the repo

- AGENTS.md rule 4: the ARL exception is replaced by D5's two bounded
  exceptions.
- ADR-0002 status line: "superseded by ADR-0005".
- `docs/PLAN-hackathon.md`: banner pointing to the new plan.
- W7 (#20) is re-scoped to the planner engine (see the plan's work orders).
  W15 (#23) calibrates against past campaigns instead of expected ARLs.

## Consequences

- The atlas becomes a stepper (steps 1 to 6) around the map. The ARL legend
  goes.
- Data work grows: a monthly trait table, a context table for logistics and
  risks, and a cited past-campaign table. See the pipeline spec.
- Thresholds are still our choice where no source pins them. Every one says so
  and the user can change it.
