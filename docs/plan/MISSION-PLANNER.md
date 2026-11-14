# Mission planner: the plan (engine, data pipeline, UI)

Status: **proposed** (work order #56). Decision: [ADR-0005](../decisions/ADR-0005-mission-planning-workflow.md)
(replaces ARL). Data details: [DATA-PIPELINE.md](DATA-PIPELINE.md). Team doc:
"nasa space apps 2026", IDEA tab (workflow table).

## In one sentence

A scientist says what they want to test for the Moon or Mars, and when; we take
them step by step to a field plan on Earth: where, which months, what it can and
can't rehearse, how to get there, what could go wrong, and who has done
something like it before.

## Why this is different from other teams

Most teams will show a "looks like Mars" map. Ours starts from the
**mission**, not the place:

- It starts from NASA's own Moon-to-Mars objectives and the dates of the trip.
  The answer changes by month (cold-dark tests in winter, low-sun tests near the
  poles), so the season is part of the result.
- It never hides the bad news. Each trait shows match, miss (and by how much)
  or unknown. And it always lists what Earth can't test: gravity, air
  pressure, radiation.
- It links to the past: the closest earlier analog campaigns, with a Shapley
  breakdown of *why* they're close.
- It ends with a plan, not a map: a one-page brief you could attach to a
  proposal, with an approval-readiness checklist.
- Every number links back to a NASA file and its hash.

## The workflow

Each step lists: what the scientist does, what they get back, what the engine
computes, the data it reads, and the UI.

### Step 1. Mission objectives

- **Scientist:** picks the target body (Moon or Mars) and a NASA objective
  (OP-5LM, SE-3LM, LI-5L to start), or a preset from a past campaign. Sets the
  month window (e.g. Jun–Aug), length in days, team size, and hard limits: max
  travel time, avoid protected land, max slope, and so on.
- **Gets back:** the test requirements as a table, one row per trait (Earth
  units, where each band came from, the caveat), plus a live funnel counter:
  "91,800 places → 12,400 pass your limits → 310 match every requirement".
- **Engine:** `requirements(objective, preset, edits)` builds the table from
  the trait map; `funnel(requirements, limits, months)` returns counts per
  stage.
- **Data:** L3 objectives, envelopes, trait map, campaign presets. L1 + L1m for
  the counter.
- **UI:** left-hand stepper (1–6). Form with presets, core dropdowns and an
  "advanced" panel (team doc: hybrid funnel). Funnel counter on top.

### Step 2. Site finder and compare

- **Scientist:** looks at the map, clicks places, pins up to 3 to compare.
- **Gets back:** a map in one of two views. *Funnel view* puts each hexagon in
  one of three classes for the chosen months: "every requirement matches",
  "at least one miss" or "no miss but something unknown". *Trait view* colours
  by the gap on one trait the user picks. Then the
  Pareto shortlist (places no other place beats on every gap), sortable by one
  trait at a time, and a side-by-side table of up to 3 sites with per-month
  values.
- **Engine:** `verdicts(cells, requirements, months)` gives per hexagon and
  trait: `match` / `miss` + gap / `unknown`. `shortlist(verdicts)` gives the
  Pareto set (S2, already proved). `compare(sites)`.
- **Data:** L1, L1m (chosen months), L4 `cells.bin`.
- **UI:** map (GIBS base layer, hexagons), shortlist panel, compare drawer.

### Step 3. Gaps and limits

- **Scientist:** opens a site.
- **Gets back:** per trait, what holds and what breaks, with the gap in real
  units ("night ground temperature 251 K, 8 K warmer than the requirement"),
  which traits are unknown and why, and the "Earth can't test this" list for
  the objective, each with a one-line reason.
- **Engine:** `gaps(site, requirements, months)`.
- **Data:** L1, L1m, L3 objective `notTestableOnEarth`.
- **UI:** gap card. Matches, misses and unknowns in three groups.

### Step 4. Logistics

- **Scientist:** checks if a team can get there and work.
- **Gets back:** travel time to the nearest city, nearest airport, share of
  protected land, and the **field-season months**: months where every required
  trait matches and the place is reachable.
- **Engine:** `logistics(site, months)`; `season(site, requirements)` returns
  the matching months.
- **Data:** L2 context, L1m.
- **UI:** logistics card with a 12-month strip (green = match + reachable).

### Step 5. Risks

- **Scientist:** checks safety for the chosen months.
- **Gets back:** per hazard type (wildfire, volcano, storm, dust, flood,
  landslide, snow, extreme temperature, earthquake), past events by month, plus
  terrain risk (share of slopes over 30°) and cold or heat extremes. Each
  hazard is its own flag. There's no combined risk score.
- **Engine:** `risks(site, months)`.
- **Data:** L2 `hazard_*`, L1 `slope_frac_gt30`, L1m temperatures.
- **UI:** risk card, one row per hazard type, with "EONET is a curated list: 0
  means none recorded, not none happened".

### Step 6. Past missions

- **Scientist:** wants to know who has done this before.
- **Gets back:** the past campaigns that exercised the same objective, and the
  ones whose site is closest in traits to the chosen site. For each: name,
  agency, years, what they tested, what worked and failed (quoted), and a
  **Shapley breakdown** of closeness: which traits make the two sites alike or
  different.
- **Engine:** `precedents(site, objective)`. Closeness is the squared distance
  over traits both sites have, each trait scaled by its spread across all land
  hexagons (interquartile range). Because the squared distance is a sum of
  per-trait terms, each trait's Shapley value is exactly its own term. Traits
  missing on either side are left out and listed.
- **Data:** L3 campaigns, L1 at each campaign's hexagon.
- **UI:** precedent list. Each item has a bar split by trait, using the
  Shapley values.

### Output: mission plan brief

One page, exportable (Markdown/PDF): objective, months, chosen site(s), the
requirement table with verdicts, field-season months, logistics, risks,
precedents, "Earth can't test" list, approval-readiness checklist, data sources
with hashes.

## Add-ons

### Approval readiness (instead of "Congress approval chances")

We don't predict whether Congress or NASA will approve a mission. There's no
data to back a probability, and judges would spot it. Instead we show a
checklist reviewers care about. Each item is yes / no / unknown, with a source:

- Tied to a named NASA Moon-to-Mars objective.
- A NASA or partner campaign has used a similar site before (step 6).
- There's a field-season window inside the requested months (step 4).
- No protected land, or the permit route is known (step 4).
- Hazards in the chosen months are known and listed (step 5).
- Cost band: travel time and airport distance as stated proxies, not a budget.

### Campaign optimizer with QUARCC fastopt (plan only, P2)

For a campaign that tests several objectives across several sites, choose how
to split field days across (site, month) pairs:

- Variables: share of field days per (site, month), at least 0, adding to 1.
- Coverage constraints: for each required trait, the share of days at
  (site, month) pairs where it matches is at least a minimum. These are
  fastopt group constraints (`groups`, `group_lower`).
- Caps: max share per site or month (team capacity), as box bounds.
- Cost: a linear term from travel time (stated proxy).
- Risk: days lost to bad conditions in each past year (2014–2023, from L1m
  years and EONET) as scenarios. Minimise the worst 10% (CVaR), which fastopt
  solves directly (`Portfolio(...).optimization(rm="CVaR", obj="MinRisk")`).
- Output: a table of (site, month, share of days) with each trait's coverage.

This is a plan for field time, not a rating of how alike two places are, so it
fits ADR-0005 D5. Needs L1m for several years. Not built in the hackathon
unless P0 and P1 are done.

## Engine

- **Where:** `services/engine/` as a Python package `planner`. It reads L1,
  L1m, L2, L3 and writes L4 (`publish`).
- **In the browser:** steps 1–3 must react instantly, so the atlas recomputes
  verdicts in TypeScript over `cells.bin`. To keep the two copies honest, the
  Python engine writes `golden-verdicts.json` (about 200 hexagons × all
  objectives) and the atlas test suite must reproduce it exactly.
- **Lean first:** S7 (funnel) is frozen before the verdict code is written:
  - verdict is `match` only if the value is known and inside the band;
  - `unknown` never counts as `match`;
  - tightening a band or adding a requirement never adds a site to the
    surviving set or to the shortlist's candidates.
  The Pareto shortlist reuses the proved S2 statements.

## UI

- Stepper on the left (1–6), map in the middle, step card on the right.
- Step 1 has the funnel counter. Every later step reads the same request
  (objective, months, limits), kept in the URL so a plan can be shared as a
  link.
- Colours: the three funnel classes, or one trait's gap. Never a count of
  matches or a gradient of "goodness". Unknown is hatched grey.
- Moon/Mars side panel (Trek WMTS) showing the target the requirement came
  from (P1).
- Export button on every step writes the brief.

## Priorities

| Priority | What |
|---|---|
| **P0** (demo) | Steps 1–3 for the 3 objectives, with months (L1m). Steps 4–5 with what we can source by Sunday noon. Brief export. |
| **P1** | Step 6 with at least 6 cited campaigns + Shapley. Approval checklist. Trek side panel. |
| **P2** | fastopt campaign optimizer. Extra years of MOD11C3. Dust when MERRA-2 is unblocked. |

## Work orders

| W | What | Lane | Depends on |
|---|---|---|---|
| W16 (#56) | This plan + ADR-0005 + trait map v0 | docs | — |
| W17 | L1m monthly table + L1 temperature rule change | ingest | W16 |
| W18 | L2 context: EONET hazards, travel time, airports, WDPA (licence first) | ingest | W16 |
| W19 | Past campaigns table (cited) + `campaign.schema.json` | data + contracts | W16 |
| W20 | New contracts: `plan-request`, `trait-map`, `site-plan` | contracts | W16 |
| W21 | S7 funnel statement (frozen) then proof | proofs | W20 |
| W7 (#20) | Planner engine: requirements, verdicts, shortlist, gaps, season, risks, precedents, publish | engine | W17, W18, W20, W21 statement |
| W11b | Atlas stepper (steps 1–6) on mock L4, then real | atlas | W20 |
| W15 (#23) | Calibration against past campaigns: does each campaign's own site match its objective? | data | W7, W19 |
| W22 | fastopt optimizer (P2) | engine | W7 |

## Open questions for the owner

1. Approve the two bounded exceptions in ADR-0005 D5 (Shapley closeness,
   optimizer)?
2. Is "approval readiness" OK as the honest version of "Congress chances"?
3. Product name (placeholder: Proving Grounds).
