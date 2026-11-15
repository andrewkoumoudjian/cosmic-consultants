# W15 calibration: do past campaign sites pass their own objective? (#23)

**Short answer:** mostly yes. 36 of 40 frozen trait expectations held across five
cited NASA and partner campaign sites. The two real misses tell us something
about our rules:

- Black Point lava flow (Desert RATS 2010) fails `surfaceMaterial`. Our
  "mostly barren" stand-in comes from a land-cover class, and that class calls
  sparse lava-field scrub "not barren".
- Atacama (ARADS 2019) misses the terrain band by 0.28°. Terrain is only
  *preferred* for OP-5LM, so the site still gets through.

This is a check of our rules against past field practice. It is not a site
score, and it doesn't make the rules scientifically accepted.

## How it was run

1. **Expectations frozen first.** `data/calibration/campaign-expectations.yaml`
   (sha256 `024c37aa…3253c`) was committed as `a906a04` at 11:30:35Z. GitHub's
   branch activity log shows the branch created at `a906a04` at 11:30:36Z; the
   runner commit `916c2cd` is 11:32:13Z, and the next push was 11:34:37Z.
   "No assembled site value was read before the freeze" is the author's
   statement; git can't prove it. Each campaign gets a request (body, objective,
   mission type, months from the quoted dates) plus an expected verdict and
   confidence per trait.
2. **Runner added second.** `services/engine/src/planner/calibrate.py` calls
   the existing `site_plan` and `search` (frozen S7 semantics) on each campaign's
   own r4 hexagon and lines up expected next to observed. It never rewrites the
   expectations. It refuses to run unless the file is marked `frozen`, is
   committed, and is byte-identical to the commit that first added it. A frozen
   expectation the engine doesn't return, or one for a site outside the grid, is
   kept and counted as **not held**, so the denominator can't shrink.
3. **Results committed last.** `data/calibration/results/` holds the full
   JSON (per-month rows included) and the Markdown table.

Two request variants:
- `shipped`: priorities as the trait map ships them. For OP-5LM that makes
  the two traits with no band (dust, thermal) required.
- `bandsOnly`: only banded traits are required. This is also what the atlas
  planner does when you pick an objective (`apps/atlas/src/planner/main.ts:35`).

The campaign→objective links are **our reading**. Every record in
`data/campaigns/` has `objectiveId: null`. All five runs use OP-5LM (surface
mobility, Mars). HI-SEAS IV is **not run**: it's an isolation/microbiome study,
and none of our three objectives covers it.

## Results

| Campaign (site) | terrain (slope mean, 0–5°) | surfaceMaterial (barren %, 50–100) | dust, thermal | Funnel as expected? |
|---|---|---|---|---|
| MDRS crew 89 (Utah) | match, 4.31° | match, 55.9% | unknown (no band) | yes / yes |
| FMARS exp. 12 (Devon Is.) | match, 2.28° | match, 89.3% | unknown (no band) | yes / yes |
| HMP 2015 (Devon Is., same hexagon) | match, 2.28° | match, 89.3% | unknown (no band) | yes / yes |
| Desert RATS 2010 (Black Point, AZ) | match, 2.56° | **miss**, 3.6% (gap 46.4) | unknown (no band) | **no / no** |
| ARADS 2019 (Atacama) | **miss**, 5.28° (gap 0.28) | match, 99.9% | unknown (no band) | yes / yes |

The full table is in `data/calibration/results/CALIBRATION-RESULTS.md`.

Grid-wide, across 91,800 land hexagons (all four held):

| Variant | Matches | Unknown | Misses | Sites with a Pareto layer |
|---|---|---|---|---|
| shipped | 0 | 10,703 | 81,097 | 0 |
| bandsOnly | 10,703 | 0 | 81,097 | 0 |

## What we learned

1. **The surface stand-in excludes a real NASA site.** `barren_pct` is the
   MCD12C1 share of the IGBP "barren" class. Black Point basalt counts as
   grassland/shrubland there, so it scores 3.6% barren, even though NASA ran
   crewed-rover geology traverses on it. The trait-map basis still says "no
   Earth albedo column yet", but ADR-0009 added one. A **post-hoc look** (not
   frozen, not part of the tally) at shortwave white-sky albedo against the Mars
   envelope band (0–0.25) shows the two proxies disagree: Black Point 0.156 (would
   match), Atacama 0.222 (match), MDRS 0.272 (miss), Devon 0.495 (miss). So
   switching to albedo is no easy fix either. Choosing the proxy needs an ADR
   (rule 7).
2. **Terrain misses near the band edge are real but soft.** Atacama's 5.28°
   comes from averaging over a 1,770 km² hexagon that includes the coastal
   escarpment. Terrain is *preferred* for OP-5LM, so the miss shows as a gap and
   doesn't filter the site out. That's how it's designed to work.
3. **With the shipped priorities, OP-5LM matches nowhere.** Dust and thermal
   have no band and default to required, and S7 never counts an unknown as a
   match. The atlas avoids this by starting unbanded traits as preferred. But a
   request with no `must`/`nice` (CLI, API or a hand-built link) returns zero
   matches.
4. **No OP-5LM site ever gets a Pareto layer.** Layers are only computed for
   sites with no unknown trait, and two of the four OP-5LM traits are unknown
   everywhere. The shortlist then falls back to ordering by the sort trait's gap.
   Pitch copy that promises a "Pareto shortlist" for OP-5LM shouldn't, until dust
   and thermal get bands.
5. **Two campaigns share one hexagon.** FMARS and HMP both sit in
   `8402543ffffffff`, so r4 can't tell them apart.

## Limits

- One objective (OP-5LM) was exercised. SE-3LM and LI-5L have no cited
  campaign in `data/campaigns/` yet.
- Five sites is a sanity check, not a statistical calibration.
- Source QA is still partial (#76): the DEM nodata label is inaccurate and
  MOD11C3 QC bits are not filtered. Neither touches a verdict here (thermal has
  no band), but slope comes from the unmasked DEM path.
- Data: the verified assembly whose `assembly-report.json` sha256 is
  `7bf0145e…`, which matches the report in the merged #127 refresh. Input hashes
  are listed in the results file.

## Rerun

```bash
cd services/engine
PYTHONPATH=src python -m planner.calibrate <path>/_derived/assembled --out ../../data/calibration/results
PYTHONPATH=src python -m unittest discover -s tests -p test_calibrate.py
```

Needs `pyarrow==18.1.0` and `pyyaml==6.0.2` (Python ≤ 3.13; 3.14 has no wheel
for that pyarrow).
