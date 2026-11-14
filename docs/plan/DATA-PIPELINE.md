# Data pipeline spec (mission planner)

Status: **proposed** (work order #56). Decision: [ADR-0005](../decisions/ADR-0005-mission-planning-workflow.md).
Product plan: [MISSION-PLANNER.md](MISSION-PLANNER.md). Owner of this spec:
Andrew (data pipeline scope).

This is the single description of what data we hold, how it's built, where
it's stored and who reads it. If code or another doc disagrees with this file,
this file wins until a PR changes it. If you find a contradiction, open an
issue, don't route around it.

## 1. The rules (apply to every layer)

1. **Every number traces to a snapshot.** A snapshot is a downloaded source
   file with its URL, fetch date, sha256 and licence in
   `data/snapshots/MANIFEST.json`. Nothing is hand-edited (AGENTS.md rule 3).
2. **Missing stays missing.** A value we can't compute is `null` and the row's
   `missing_reason` says why. We never fill, guess or set a default. The UI
   shows `null` as "unknown", never as "bad".
3. **Raw measurements only, up to L2.** Layers L0 to L2 hold what was measured,
   in physical units. No verdicts, gaps or scores. Comparing a value to a
   requirement is engine work (L4).
4. **One grid.** Every gridded table uses H3 resolution 4 (about 1,770 km² per
   hexagon, 91,800 land hexagons). The key column is always `h3`.
5. **One time base.** Monthly values use calendar months 1 to 12 of a named
   year. The base year is **2023** for every source unless its row in §4 says
   otherwise.
6. **Licence first.** A source is used only after its licence is checked live
   at fetch time and recorded in its catalog row. `restricted` or `unresolved`
   sources stay out of published artifacts.

## 2. The layers at a glance

| Layer | What | Where (repo path) | Built by | Read by |
|---|---|---|---|---|
| L0 | Raw snapshots, hashed | `data/snapshots/<datasetId>/` + `MANIFEST.json` | `services/ingest` fetchers | L1, L2 builders |
| L1 | Earth traits per hexagon, yearly | `data/snapshots/_derived/cells-r4.parquet` | `p0ingest.process` | engine |
| L1m | Earth traits per hexagon, per month | `data/snapshots/_derived/cells-r4-monthly.parquet` | `p0ingest.monthly` (new) | engine |
| L2 | Context per hexagon: access, protected land, hazards | `data/snapshots/_derived/context-r4.parquet` | `p0ingest.context` (new) | engine |
| L3 | Curated reference tables (objectives, envelopes, trait map, past campaigns) | `data/objectives/`, `data/envelopes/`, `data/requirements/`, `data/campaigns/` | data lane, by PR | engine, UI |
| L4 | Published artifacts for the app | `apps/atlas/public/data/v<N>/` + `build-manifest.json` | `services/engine` `publish` | UI |

`_derived/` files are rebuilt from L0, never edited. They're gitignored and
mirrored to Drive (§7). Their `.meta.json` lists every input sha256.

## 3. Which workflow step needs which data

| Step | Needs | Layer | Have it today? |
|---|---|---|---|
| 1 Objectives | objective rows, envelopes, trait map, presets from past campaigns | L3 | objectives + envelopes yes; trait map in this PR; campaigns no |
| 2 Site finder | traits per hexagon (yearly + chosen months) | L1, L1m | L1 yes; L1m no (built from files we already have) |
| 3 Gaps | same as step 2 + "Earth can't test" lists | L1, L1m, L3 | yes except L1m |
| 4 Logistics | travel time, protected share, nearest airport, field-season months | L2, L1m | no |
| 5 Risks | recorded hazard events, burned area by month, temperature extremes, steep ground | L2, L1m, L1 | L1 yes; rest no |
| 6 Past missions | cited campaign table with site location and traits | L3 + L1 at the campaign's hexagon | no |

## 4. Sources (L0)

Status words: **have** (snapshot hashed), **fetch** (licence OK, not
downloaded), **probe** (licence or endpoint still to check live), **blocked**.

| Source (catalog id) | Gives | Layer / columns | Base period | Status |
|---|---|---|---|---|
| MODIS MOD11C3 v061 (`modis-mod11c3`) | ground temperature day/night, monthly, 0.05° | L1, L1m `lst_*` | 2023 | have (12 files) |
| MODIS MCD12C1 v061 (`modis-mcd12c1`) | land cover shares, yearly, 0.05° | L1 `barren_pct`, `snow_ice_pct`, `water_pct` | 2023 | have |
| Copernicus DEM GLO-30 (`copernicus-dem-glo30`) | elevation, read at 240 m | L1 `elev_*`, `slope_*` | static | have (streamed; tile ledger hashed) |
| ESA CCI permafrost (`esa-cci-permafrost-extent-nh`, `-antarctica`) | permafrost probability | L1 `permafrost_pct` | 2023 | have |
| Sun position (computed) | noon sun height, day length, polar day/night | L1, L1m `sun_*`, `daylight_h`, `polar_*` | 2023 | have (no file needed) |
| MERRA-2 M2TMNXAER (`merra2-m2tmnxaer`) | dust optical depth, monthly | L1 `dust_aod_mean`, L1m `dust_aod` | 2023 | blocked (GES DISC app approval) |
| MODIS MOD11C3, 2014–2022 | same as above, extra years | L1m-years (risk scenarios, optimizer) | 2014–2023 | fetch (P2 only) |
| NASA EONET v3 (`eonet-v3-events`) | notable natural events with dates and points | L2 `eonet_*` | 2015–2024 | probe: API answers (§4.1); no licence statement on the API |
| Travel time to cities 2015 (`travel-time-to-cities-2015`) | minutes to the nearest city | L2 `access_min_*` | 2015 | probe: download link found (§4.1), licence not yet found |
| MODIS burned area MCD64A1 (new catalog row) | burned area per month, 500 m | L2 `burned_pct_<month>` | 2015–2024 | probe (P1; better wildfire-by-month source than EONET) |
| WDPA (`wdpa-protected-areas`) | protected-area polygons | L2 `protected_pct` | latest release | probe (licence is `restricted`: may not ship) |
| Airports (new catalog row, e.g. OurAirports) | airport points | L2 `airport_km` | snapshot date | probe (new row needed) |
| Campaign source documents (papers, NASA pages) | where and when past campaigns ran | L3 `data/campaigns/` | per campaign | to collect |

If WDPA's licence doesn't allow publishing derived numbers, `protected_pct`
stays in L2 for our own checks and L4 ships `null` with reason
`licence-restricted`.

### 4.1 Probe log (2026-11-14, Claude session c153a6ba)

- **EONET:** `GET https://eonet.gsfc.nasa.gov/api/v3/events?status=all&start=2015-01-01&end=2024-12-31&limit=100000`
  at 2026-11-14T17:31Z → HTTP 200, 10,443,929 bytes, 10,086 events. By
  category: wildfires 8,323, severeStorms 919, volcanoes 516, seaLakeIce 134,
  floods 116, waterColor 18, landslides 17, dustHaze 17, earthquakes 15,
  tempExtremes 14, manmade 8, drought 7, snow 5. By first-event year: 2015 331,
  2016 426, 2017 620, 2018 616, 2019 465, 2020 588, 2021 711, 2022 321, 2023 238,
  **2024 5,754**. So EONET's volume swings with how much NASA curated each
  year, and most categories are nearly empty. It can't give hazard rates.
- **Travel time to cities 2015:** the Malaria Atlas Project page
  `https://malariaatlas.org/project-resources/accessibility-to-cities/`
  (HTTP 200) now lists it under "Accessibility to Healthcare" with a download
  link `https://data.malariaatlas.org/geoserver/ows?service=CSW&version=2.0.1&request=DirectDownload&ResourceId=Explorer:2015_accessibility_to_cities_v1.0`.
  No licence text on that page. Licence still to find before use.
- **Airports:** `https://davidmegginson.github.io/ourairports-data/airports.csv`
  → HTTP 200 (text/csv). Licence not yet checked.

## 5. Tables and columns

Units in brackets. "K" is kelvin, "deg" is degrees. Every table also has
`missing_reason` (text, `;`-joined codes such as `no-lst-pixels`,
`outside-permafrost-model`, `dust-blocked`).

### L1 `cells-r4.parquet` (exists, one row per hexagon)

| Column | Meaning |
|---|---|
| `h3`, `res`, `lat`, `lon` | hexagon id, resolution (4), centre [deg] |
| `cmg_pixels`, `land_pct_mean` | 0.05° pixels in the hexagon, mean land share [%] |
| `lst_day_max_k` | warmest month's daytime ground temperature in 2023 [K]: max over months of L1m `lst_day_k` (rule change, see L1m) |
| `lst_night_min_k` | coldest month's night-time ground temperature in 2023 [K]: min over months of L1m `lst_night_k` (rule change, see L1m) |
| `lst_diurnal_range_mean_k`, `lst_months_with_range`, `lst_valid_pixels` | mean day-night swing [K], months it's based on, pixels used |
| `barren_pct`, `snow_ice_pct`, `water_pct` | land cover shares [%] |
| `permafrost_pct` | mean permafrost probability [%]; null outside the ESA model area |
| `dem_pixels`, `elev_mean_m`, `elev_min_m`, `elev_max_m` | 240 m DEM pixels, elevation [m] |
| `slope_mean_deg`, `slope_frac_lt5`, `slope_frac_lt15`, `slope_frac_gt30` | mean slope [deg], shares of ground flatter than 5°/15°, steeper than 30° [0–1] |
| `sun_noon_elev_max_deg`, `sun_noon_elev_min_deg`, `polar_night`, `polar_day` | yearly noon sun height range [deg], flags |
| `dust_aod_mean` | yearly mean dust optical depth [unitless]; null until MERRA-2 is unblocked |

### L1m `cells-r4-monthly.parquet` (new, one row per hexagon and month: 1,101,600 rows)

| Column | Meaning | Source |
|---|---|---|
| `h3`, `month` | hexagon, month 1–12 of 2023 | — |
| `lst_day_k`, `lst_night_k` | monthly mean day / night ground temperature, median over the hexagon's pixels [K] | MOD11C3 |
| `lst_diurnal_k` | `lst_day_k − lst_night_k` when both exist [K] | MOD11C3 |
| `lst_valid_pixels` | pixels with both values that month | MOD11C3 |
| `sun_noon_elev_deg` | noon sun height on the 15th of the month [deg] | computed |
| `daylight_h` | day length on the 15th [hours] | computed |
| `polar_day`, `polar_night` | sun never sets / never rises on the 15th | computed |
| `dust_aod` | monthly dust optical depth; null until unblocked | MERRA-2 |

**One temperature rule for both tables.** Today L1 takes each pixel's
warmest month, then the median over pixels. L1m takes the median over pixels
each month. Those two can give different "warmest" numbers. Decision: L1
`lst_day_max_k` becomes the **max over months of L1m `lst_day_k`**, and
`lst_night_min_k` the **min over months of L1m `lst_night_k`**. The L1 rows
above change meaning in the same PR that builds L1m, and the team doc's
"How we map the Earth" text is updated to match.

Done when: the file has 91,800 × 12 rows, its meta lists the 12 MOD11C3
hashes, and for every hexagon L1 `lst_day_max_k` = max of L1m `lst_day_k` and
L1 `lst_night_min_k` = min of L1m `lst_night_k`, exactly.

### L2 `context-r4.parquet` (new, one row per hexagon)

| Column | Meaning | Source |
|---|---|---|
| `access_min_median`, `access_min_p10` | travel time to the nearest city, median and best 10% of the hexagon [minutes] | travel-time raster |
| `protected_pct` | share of the hexagon inside a protected area [%] | WDPA (if licence allows) |
| `airport_km` | distance from the hexagon centre to the nearest airport with a paved runway [km] | airports |
| `eonet_<category>_events` | EONET events of that category whose point falls in the hexagon or within 50 km of its centre, 2015–2024 [count] | EONET |
| `eonet_<category>_months` | which calendar months those events started in, as a 12-character string of 0/1 (Jan first) | EONET |
| `burned_pct_<month>` | mean share of the hexagon burned in that calendar month, over 2015–2024 [%] (P1) | MCD64A1 |

EONET categories kept: `wildfires`, `volcanoes`, `severeStorms`, `floods`,
`landslides`, `dustHaze`, `earthquakes`, `snow`, `tempExtremes`, `drought`.
**EONET is a list of notable events NASA chose to curate, not a full record**
(see §4.1: 238 events in 2023, 5,754 in 2024). So:

- we show "events recorded by EONET near here", with their names and dates,
  never a rate, a probability or "safe";
- a zero means "none recorded in EONET";
- cold and heat extremes come from L1m temperatures, not EONET;
- wildfire by month comes from MCD64A1 burned area once it's in (P1).

### L3 curated reference tables (data lane, edited by PR, each row cited)

| Table | Path | Schema | Content |
|---|---|---|---|
| Objectives | `data/objectives/*.yaml` | `contracts/objective.schema.json` | NASA M2M objectives, required traits, "Earth can't test" list |
| Envelopes | `data/envelopes/*.json` | `contracts/envelope.schema.json` | Moon/Mars target bands in target units, each cited |
| Trait map | `data/requirements/trait-map.yaml` | `contracts/trait-map.schema.json` (new) | how each target band becomes an Earth-unit test requirement (§6) |
| Past campaigns | `data/campaigns/*.yaml` | `contracts/campaign.schema.json` (new) | one file per campaign (§5.1) |

#### 5.1 Past campaigns (`data/campaigns/<campaignId>.yaml`)

| Field | Meaning |
|---|---|
| `campaignId`, `name`, `agency` | e.g. `hmp-haughton`, "Haughton-Mars Project", NASA/CSA |
| `years` | first and last field season |
| `site` | name, lat, lon, the H3 r4 hexagon it falls in |
| `objectivesExercised` | M2M objective ids it exercised, **each with a quote** from the source |
| `published constraints` | numbers the campaign itself reported (slope limits, temps, durations), each with unit and quote; feeds step 1 presets |
| `outcome` | what worked and what failed, quoted |
| `sources` | URL, fetch date, sha256 of the stored copy in `data/snapshots/campaign-sources/` |

A campaign row with no quotable source isn't added. Seed list (from
`docs/research/03`): HMP Haughton, MDRS Utah, FMARS Devon Island, HI-SEAS Mauna
Loa, Desert RATS Arizona, PISCES Hawaii, ESA PANGAEA Lanzarote, Atacama rover
tests, Antarctic Dry Valleys, Svalbard AMASE, Rio Tinto. NEEMO is listed as
"not land, out of grid".

### L4 published artifacts (`apps/atlas/public/data/v<N>/`)

| File | Content |
|---|---|
| `cells.bin` + `cells.json` | L1 + L2 columns the UI uses, as column arrays (Float32, NaN = null), plus column names, units, null reasons |
| `monthly/<column>.bin` | one L1m column for all hexagons × 12 months, loaded only when a step needs it |
| `objectives.json`, `trait-map.json`, `campaigns.json` | L3 tables as JSON |
| `build-manifest.json` | for every file: sha256, and the sha256 of every L0 snapshot it came from |

Budget: `cells.bin` ≈ 91,800 × 30 columns × 4 bytes ≈ 11 MB raw (~4 MB
gzipped). Each monthly column ≈ 4.4 MB raw.

## 6. The trait map: Moon/Mars bands to Earth test requirements

The engine compares **Earth columns with Earth-unit bands only** (ADR-0005
D2). `data/requirements/trait-map.yaml` holds, per objective and trait, one
rule:

```yaml
- objectiveId: LI-5L
  dimension: terrain
  earthColumn: slope_mean_deg      # L1 column
  band: {lo: 0, hi: 10}            # Earth units
  unit: deg
  origin: target                    # target | precedent | user
  basis: "moon-south-pole-v0 terrain: max slope over 100 m <= 10 deg"
  scaleCaveat: "Earth value is a mean over a 240 m grid, the Moon band is a max over 100 m. Same number, different statistic."
  status: proposed                  # proposed | accepted
```

A trait with no rule is `unknown` for that objective. It is never skipped
silently. The UI lets the user edit any band; a user edit sets
`origin: user`.

## 7. Where things run and live

| What | Where |
|---|---|
| Source of truth for file identity | `data/snapshots/MANIFEST.json` (git) |
| Raw + derived files | gitignored locally; mirrored to Drive folder `1W4s6X4HTHmF7Xvd8eb1x3FlO-osP07V_` with the same layout as `data/snapshots/` |
| Drive tooling | rclone remote `ccdrive`; `scripts/drive_sync.sh` copies, never deletes; `restore` re-checks every sha256 |
| Builds | any machine with `uv sync` in `services/ingest`. The Oracle instance is the always-on builder and uploader once it's linked to T3 (pending). |
| Looking at the data | JSheets team workbook (DuckDB reads the Parquet files directly), in `research/`, never shipped. See MISSION-PLANNER "Team workbook". |
| Run times today | L1 ≈ 1.5 min + terrain ≈ 30 min (cached). L1m and L2 targets: under 10 min each. |

## 8. Build order and checks

```text
L0 fetch  ->  L1 / L1m (process, monthly)  ->  L2 (context)  ->  validate  ->  mirror to Drive
L3 (PRs, validated by scripts/validate_contracts.py)
L1 + L1m + L2 + L3  ->  engine publish  ->  L4  ->  atlas
```

Checks every build must print (rule 2: paste them in the PR):

- row counts (91,800; 1,101,600 for L1m),
- null rate per column, with the top `missing_reason` codes,
- sha256 of every input and output,
- L1/L1m agreement (§5),
- 5 spot checks at known places (Death Valley, Haughton, Atacama, McMurdo Dry
  Valleys, Mauna Loa), printed with lat/lon and values.

## 9. Contradictions found and how they're settled

| # | Contradiction | Settled by |
|---|---|---|
| 1 | ARL ladder vs the team's 6-step workflow | ADR-0005 replaces ARL |
| 2 | Team table says "final suitability score", "risk score", "ranked list"; AGENTS.md rule 4 bans single scores | No site score. Pareto shortlist, sort by one trait, risk shown per hazard type (ADR-0005 D3) |
| 3 | Moon/Mars bands are in target units; Earth columns measure other things | Trait map (§6): Earth-unit bands with a stated basis and caveat |
| 4 | "Previous mission intelligence" vs team note "presets replace previous mission intelligence" | Both: the campaign table feeds presets (step 1) **and** precedents (step 6) |
| 5 | Logistics and risks merged ("operational readiness") vs listed apart | Two UI steps, one shared L2 table |
| 6 | Mission time matters, but L1 is yearly | L1m monthly table; step 1 picks months |
| 7 | L1 yearly extremes vs L1m monthly values could disagree | L1 extremes are rebuilt from L1m (§5) |
| 8 | Permafrost is built from MODIS temperatures, so it can't confirm temperature | Never used as a second source for temperature |
| 9 | ESA permafrost fill could read as 0% | Outside the model area it's null with a reason |
| 10 | WDPA licence is restricted | Ship null + `licence-restricted` unless the licence allows derived numbers |
| 11 | EONET zero events could read as "safe"; EONET counts could read as rates | EONET shown as named events only, never a rate (§4.1, L2) |
| 12 | Team doc asks for "top X" sites; rule 4 bans a site score | Pareto layers + one user-chosen trait as tie-break (MISSION-PLANNER step 1) |
| 13 | Team doc's 8 test categories need data we don't have (caves, biology, wind) | Category table in MISSION-PLANNER step 1 marks each one ready / partial / no; missing traits stay unknown |
