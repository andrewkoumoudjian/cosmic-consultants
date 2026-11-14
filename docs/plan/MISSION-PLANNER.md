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
  breakdown of *why* they're close. (Shapley values split a difference fairly
  between its causes, here between traits.)
- It ends with a plan, not a map: a one-page brief you could attach to a
  proposal, with an approval-readiness checklist.
- Every number links back to its source file (NASA, ESA or Copernicus) and its hash.

## The workflow

Each step lists: what the scientist does, what they get back, what the engine
computes, the data it reads, and the UI.

### Step 1. Mission objectives

- **Scientist:** picks the target body (Moon or Mars), a **test category**
  and the specific test (the team's 8 categories, table below), which maps to a
  NASA objective (OP-5LM, SE-3LM, LI-5L to start), or a preset from a past
  campaign. Chooses how many sites to see (all, or the top X). Sets the
  month window (e.g. Jun–Aug), length in days, team size, and hard limits: max
  travel time, avoid protected land, max slope, and so on. Also:
  - **Mission type:** robotic, crewed, or instrument test. It picks which
    requirement presets show up (e.g. crewed adds access and temperature
    limits).
  - **Priorities, without weights.** Each requirement is either **must**
    (filters sites out) or **nice** (shown, never filters). The scientist also
    picks the one trait that sorts the list. Nothing is weighted or added up.
  - **Success criteria.** Per requirement, one line on what "tested" means,
    e.g. "drive 5 km over slopes under 5°".
- **Gets back (requirement verification matrix, team doc):** one row per
  requirement with its band, must/nice, success criterion, and **how it can be
  checked**: `data` (we check it from L1/L1m/L2), `field` (only a field
  measurement can check it, e.g. rock size) or `earth-cannot` (gravity, vacuum
  or thin air, radiation).
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

**Test categories (from the team doc) and what we can support.** "Ready" means
every trait the category needs has an Earth column today or in P0.

| # | Category | Example tests | Traits | Earth data | Ready? |
|---|---|---|---|---|---|
| 1 | Robotic mobility and navigation | autonomous driving, traction, traversability | terrain, surfaceMaterial | slope, elevation range, barren share | yes (P0) |
| 2 | Geology and sampling | rock ID, drilling, coring, mapping | surfaceMaterial, terrain | barren share; GLiM rock types (candidate) | partial (P1 with GLiM) |
| 3 | Resources / ISRU | water-ice detection, regolith, excavation | waterIce, subsurface, surfaceMaterial | permafrost probability; no subsurface | partial |
| 4 | Human habitation and operations | EVA, habitat build, crew traverses | terrain, thermal, operations | slope, monthly temperatures, access | yes (P0, access in L2) |
| 5 | Instrument and sensor testing | spectroscopy, radar, imaging | depends on instrument | as category 1 or 2 | partial |
| 6 | Environmental hazards and resilience | dust, thermal cycling, erosion | thermal, dustProcess | monthly temperature swing; dust blocked | partial |
| 7 | Subsurface exploration | caves, lava tubes | subsurface | none worldwide | no (unknown, said so) |
| 8 | Astrobiology and habitability | biosignatures, extremophiles | waterIce, surfaceMaterial, thermal | partial proxies only | no (P2) |

Categories marked "no" still appear. Their unknown traits are listed, never
hidden.

**"Top X" without a score.** We rank by Pareto layers. (Pareto means: a
place is on the list if no other place is at least as good on every trait and
better on one.) Layer 1 is the places no other place beats on every gap, layer 2 is the same after removing layer 1,
and so on. Inside a layer, the user's chosen trait sorts. "Top 20" means the
first 20 in that order. A layer number is an order, not a score: it never adds
traits together.

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
  trait matches and the place is reachable. Plus:
  - **Logistics notes**, written from the data in plain words: "4 h from the
    nearest city, airport 85 km away, protected land on 30% of the hexagon,
    best months Jun–Aug".
  - **What you can actually test here:** the objective's test list, split
    into "matches here", "misses here" and "can't test on Earth" (team doc:
    "determine what can actually be tested").
  - **Planning fields we can't fill from data:** equipment, infrastructure,
    personnel, permits and costs. There's no worldwide dataset for these, so
    they're a checklist the scientist fills in, prompted by what we do know
    (protected land → "permit needed"; travel time → "cost band" proxy). They
    go into the brief as written, marked "from the scientist".
- **Engine:** `logistics(site, months)`; `season(site, requirements)` returns
  the matching months.
- **Data:** L2 context, L1m.
- **UI:** logistics card with a 12-month strip (green = match + reachable),
  the notes, the test split and the checklist.

### Step 5. Risks

- **Scientist:** checks safety for the chosen months.
- **Gets back:** per hazard type, the notable events NASA's EONET recorded
  near the site (name, date), burned area by month (P1), terrain risk (share
  of slopes over 30°) and the coldest and hottest months from our temperature
  table. Each hazard is its own flag. There's no combined risk score, and no
  hazard rate: EONET is a curated list whose size changes a lot by year.
- **Engine:** `risks(site, months)`.
- **Data:** L2 `eonet_*` and `burned_pct_*`, L1 `slope_frac_gt30`, L1m temperatures.
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
- **Ask the past missions (P1, team doc: "chatbot").** A chat box that answers
  questions **only from the campaign table and its stored sources**. Every
  answer cites campaign rows. If the table doesn't say, it answers "not in our
  records". It runs through `services/api` (the Worker holds any API key, never
  the browser). The team doc asks for a chat box on every step, so the same
  box sits on all 6. On step 1 it answers from the objective rows, trait map
  and presets ("why is the slope limit 5°?"). On steps 2–5 it answers from that
  step's numbers for the open site (L1, L1m, L2 rows plus their sources). It
  never makes up a value.

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
  years and burned area; not EONET, whose coverage changes by year) as scenarios. Minimise the worst 10% (CVaR), which fastopt
  solves directly (`Portfolio(...).optimization(rm="CVaR", obj="MinRisk")`).
- Output: a table of (site, month, share of days) with each trait's coverage.

This is a plan for field time, not a rating of how alike two places are, so it
fits ADR-0005 D5. Needs L1m for several years. Not built in the hackathon
unless P0 and P1 are done.

## Team workbook in JSheets (exploring, not shipping)

[JSheets](https://github.com/matsonj/jsheets-releases/releases) is a desktop
spreadsheet that runs on DuckDB and has a built-in MCP server, so agents can
build and check workbooks. We use it as the team's shared look at the data,
not in the product:

- **Check the pipeline.** A workbook reads L1, L1m and L2 Parquet straight
  through DuckDB. Pivot tables show null rates per column, per-month values at
  the 5 spot-check places, and the funnel counts per objective. Teammates who
  don't code can see the data and catch odd numbers.
- **Prototype the workflow.** The trait-map bands sit in a sheet. Changing a
  band shows the new funnel counts right away, so the team can try
  thresholds before they go into `trait-map.yaml` by PR.
- **Second check on the engine.** The workbook's match/miss counts per
  objective must equal the engine's `golden-verdicts.json`. A mismatch is a
  bug in one of them.
- **Limits.** JSheets is pre-release (its own notes say to check important
  results against Excel), desktop only, and its licence for redistribution
  isn't checked. So the judges' demo stays the web atlas, workbook numbers are
  never quoted in the pitch, and the workbook file lives in `research/` (where
  nothing ships). The 0.5.2 Linux build publishes a sha256 to check before
  installing.

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

Layout: stepper on the left (1–6), map in the middle, step card on the right.
One plan request drives every step and lives in the URL, so a plan is a
shareable link:

`?body=mars&obj=OP-5LM&type=robotic&months=6-8&days=14&team=6&lim=access:240,protected:0&must=terrain,surfaceMaterial&sort=terrain&top=20&pins=<h3>,<h3>`

| Step | Interactions | Done when |
|---|---|---|
| 1 | presets dropdown; body → category → test; month range; must/nice per row; limits in an "advanced" drawer. The funnel counter updates within 300 ms of any change | changing a band changes the counter, and the URL round-trips the request exactly |
| 2 | map toggles funnel view / trait view; click a hexagon to open it; pin up to 3 (a 4th pin replaces the oldest, with a toast); the shortlist shows top X, sorted by the chosen trait | the three classes match `golden-verdicts.json` for the golden hexagons |
| 3 | open site → gap card; each miss shows its gap and unit; unknowns show their reason | every required trait appears exactly once, in one of the three groups |
| 4 | 12-month strip; the checklist is editable and kept in the URL hash | season months equal the engine's `season()` output for the golden hexagons |
| 5 | one row per hazard; click to expand the EONET event names and dates | rows with 0 events say "none recorded in EONET" |
| 6 | precedent list; hover a Shapley bar to see each trait's share | the shares add up to the total closeness (Shapley sums exactly) |

States: **loading** (skeleton card; the map stays usable), **no data** for a
hexagon (hatched grey, with "unknown" and the reason), **fetch error** (a
banner with retry; never shows stale numbers as current), **nothing passes**
(the counter says which limit removed the most sites, so the user knows what
to loosen).

Export: the brief can be exported at any step. Steps not visited yet are
printed as "not checked yet", never left out silently.

Colours: the three funnel classes, or one trait's gap. Never a count of
matches or a gradient of "goodness". Unknown is hatched grey. Moon/Mars side
panel (Trek WMTS) showing the target the requirement came from (P1).

**Mock vs real (P0 boundary).** The atlas builds against a **mock L4**
(`apps/atlas/mock/l4/`, same files and format as §L4 of the pipeline spec,
values marked synthetic) until W7 publishes the real L4. Switching is one
config line. The mock banner stays up until then.

**What we reuse from the current atlas (`apps/atlas`, merged in #53):**

| Keep | Replace | Remove |
|---|---|---|
| MapLibre 6.18 setup and the GIBS base layer (`map.ts`), DOM helpers (`dom.ts`), objective loading (`objectives.ts`, `scripts/sync-objectives.mjs`), the mock-check script pattern | point-circle site layers in `map.ts` → an H3 hexagon fill layer (hexagon outlines built in the browser from the `h3` ids with `h3-js`, so no geometry download); `dossier.ts` → the six step cards; `types.ts` → types generated from the new contracts | `arl.ts` and the ARL legend (ARL is superseded) |

`apps/atlas/README.md` still says "the map code does not change" (lines
80–85). W11b corrects it, since that file belongs to the atlas lane.

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
| W17 | L1m monthly table + L1 temperature rule change + per-row `missing_reason` | ingest | W16 |
| W18 | L2 context: EONET hazards, travel time, airports, WDPA (licence first) | ingest | W16 |
| W19 | Past campaigns table (cited) + `campaign.schema.json` | data + contracts | W16 |
| W20 | New contracts: `plan-request`, `trait-map`, `site-plan` | contracts | W16 |
| W21 | S7 funnel statement (frozen) then proof | proofs | W20 |
| W7 (#20) | Planner engine: requirements, verdicts, shortlist, gaps, season, risks, precedents, publish | engine | W17, W18, W20, W21 statement |
| W11b | Atlas stepper (steps 1–6) on mock L4, then real; hexagon layer; README fix | atlas | W20 |
| W15 (#23) | Calibration against past campaigns: does each campaign's own site match its objective? | data | W7, W19 |
| W22 | fastopt optimizer (P2) | engine | W7 |
| W23 | JSheets team workbook over L1/L1m/L2 (exploring only) | research | W17 |

## Open questions for the owner

1. Approve the two bounded exceptions in ADR-0005 D5 (Shapley closeness,
   optimizer)?
2. Is "approval readiness" OK as the honest version of "Congress chances"?
3. Product name (placeholder: Proving Grounds).
