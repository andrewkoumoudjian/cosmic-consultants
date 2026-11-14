# Data pipeline spec (mission planner)

Status: **proposed** (work order #56). Decision: [ADR-0005](../decisions/ADR-0005-mission-planning-workflow.md).
Product plan: [MISSION-PLANNER.md](MISSION-PLANNER.md). Owner of this spec:
Andrew (data pipeline scope).

This is the single description of what data we hold, how it's built, where
it's stored and who reads it. If code or another doc disagrees with this file,
this file wins until a PR changes it. If you find a contradiction, open an
issue, don't route around it.

## 1. The rules (apply to every layer)

1. **Every number traces to a snapshot.** A snapshot is a source file or
   listing with its URL, fetch date, sha256 and licence in
   `data/snapshots/MANIFEST.json`. Nothing is hand-edited (AGENTS.md rule 3).
   One exception is allowed, for sources too big to keep: a **streaming
   ledger**. The MANIFEST holds the hashed listing (URL, fetch date, licence),
   and a ledger file records every piece we read (URL, array sha256). Its own
   sha256 goes in the derived table's `.meta.json`. Copernicus DEM works this
   way: `tileList.txt` is in the MANIFEST, and `terrain-r4-ledger.jsonl.gz`
   lists all 26,450 tiles.
2. **Missing stays missing.** A value we can't compute is `null` and
   `missing_reason` says why (format in §5). We never fill, guess or set a default. The UI
   shows `null` as "unknown", never as "bad".
3. **Measurements and documented derivations only, up to L2.** Layers L0
   to L2 hold measured values in physical units, plus values derived from them
   or computed by a stated method (slope from elevation, sun height from
   latitude, permafrost probability from ESA's model). Each derivation is named
   in the table's `.meta.json`. No verdicts, gaps or scores. Comparing a value
   to a requirement is engine work (L4). Assembly (§5B) may add only the
   summaries it lists (year-to-year spread, trait scales, data coverage).
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
| L1 | Earth traits per hexagon, yearly | `data/snapshots/_derived/cells-r4.parquet` | `p0ingest.process` | assembler |
| L1m | Earth traits per hexagon, per month | `data/snapshots/_derived/cells-r4-monthly.parquet` | `p0ingest.process` + `monthly` | assembler |
| L2 | Context per hexagon: access, protected land, hazards | `data/snapshots/_derived/context-r4.parquet` | `p0ingest.context` | assembler |
| L1+ | Other per-source tables (other years, burned area, albedo, regolith, dust), each cleaned by its own builder (§5A) | `data/snapshots/_derived/<family>-r4*.parquet` | one module per family | assembler |
| L3 | Curated reference tables (objectives, envelopes, trait map, past campaigns) | `data/objectives/`, `data/envelopes/`, `data/requirements/`, `data/campaigns/` | data lane, by PR | assembler, engine |
| A | **Workflow tables**: per-source tables + L3 joined into what each step reads (§5B) | `data/snapshots/_derived/assembled/` | `p0ingest.assemble`, driven by `data/pipeline/columns.yaml` | engine, L4 publish |
| L4 | Published artifacts for the app | `apps/atlas/public/data/v<N>/` + `build-manifest.json` | `services/engine` `publish` (reads A only) | UI |

`_derived/` files are rebuilt from L0, never edited. They're gitignored and
mirrored to Drive (§7). Their `.meta.json` lists every input sha256.

## 3. Which workflow step needs which data

The workflow reads only the assembled tables (§5B). This table says where
their columns come from.

| Step | Needs | Layer | Have it today? |
|---|---|---|---|
| 1 Objectives | objective rows, envelopes, trait map, presets from past campaigns | L3 | objectives + envelopes yes; trait map in this PR; campaigns in #63 (6 cited) |
| 2 Site finder | traits per hexagon (yearly + chosen months) | L1, L1m | L1 yes; L1m in #61 |
| 3 Gaps | same as step 2 + "Earth can't test" lists | L1, L1m, L3 | yes (L1m in #61) |
| 4 Logistics | travel time, protected share, nearest airport, field-season months | L2, L1m | travel time + airports in #62; protected share withheld (licence) |
| 5 Risks | recorded hazard events, burned area by month, temperature extremes, steep ground | L2, L1m, L1 | EONET events in #62; L1m in #61; burned area no (P1) |
| 6 Past missions | cited campaign table with site location and traits | L3 + L1 at the campaign's hexagon | #63: 6 campaigns, each quote checked against a stored source |

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
| NASA EONET v3 (`eonet-v3-events`) | notable natural events with dates and points | L2 `eonet_*` + `_derived/eonet-events-r4.parquet` | 2015–2024 | have (#62); used under NASA's open data policy + EONET disclaimer, owner decision ADR-0006 |
| Travel time to cities 2015 (`travel-time-to-cities-2015`) | minutes to the nearest city | L2 `access_min_*` | 2015 | have (#62); CC BY 3.0 |
| MODIS burned area MCD64A1 (new catalog row) | burned area per month, 500 m | L2 `burned_pct_<month>` | 2015–2024 | probe (P1; better wildfire-by-month source than EONET) |
| WDPA (`wdpa-protected-areas`) | protected-area polygons | L2 `protected_pct` | latest release | probe (licence is `restricted`: may not ship) |
| Airports (new catalog row, e.g. OurAirports) | airport points | L2 `airport_km` | snapshot date | have (#62, `ourairports`, public domain; paved runways only) |
| Campaign source documents (papers, NASA pages) | where and when past campaigns ran | L3 `data/campaigns/` | per campaign | have for 6 campaigns (#63) |

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

Units in brackets. "K" is kelvin, "deg" is degrees.

**`missing_reason`** is a JSON object as text: trait → reason, e.g.
`{"dustProcess": "MERRA-2 ... HTTP 403", "waterIce": "ESA CCI ... fill 255"}`.
*Today* (L1 at `343969b`) it's the same dataset-level object on every row
(`process.py:191`), so it explains why a column can be null but not why *this*
row is. **W17 changes it to per row:** only the traits null in that row, with
a short code (`no-lst-pixels`, `outside-permafrost-model`,
`permafrost-not-modelled`, `no-dem-tile`, `dust-blocked`). Every new table
(L1m, L2) uses the per-row form from the start.

### L1 `cells-r4.parquet` (exists, one row per hexagon)

| Column | Meaning |
|---|---|
| `h3`, `res`, `lat`, `lon` | hexagon id, resolution (4), centre [deg] |
| `cmg_pixels`, `land_pct_mean` | 0.05° pixels in the hexagon that contain some land; mean land share over **those** pixels [%] |
| `lst_day_max_k` | warmest month's daytime ground temperature in 2023 [K]: max over months of L1m `lst_day_k` (rule change, see L1m) |
| `lst_night_min_k` | coldest month's night-time ground temperature in 2023 [K]: min over months of L1m `lst_night_k` (rule change, see L1m) |
| `lst_diurnal_range_mean_k` | per pixel, the mean over months of (day − night); then the median over pixels [K]. It's signed and **can be negative** |
| `lst_months_with_range` | median over pixels of how many months had both a day and a night value. A median, so it can be fractional (e.g. 11.5) |
| `lst_valid_pixels` | pixels with at least one valid month |
| `barren_pct`, `snow_ice_pct`, `water_pct` | land cover shares [%] |
| `permafrost_pct` | mean permafrost probability [%]. Null in two cases: outside the ESA model area (25–85°N, 60–85°S), and inside it where ESA writes fill 255 (not modelled: ocean and warm land). Both are unknown, not 0% |
| `dem_pixels`, `elev_mean_m`, `elev_min_m`, `elev_max_m` | 240 m DEM pixels, elevation [m] |
| `slope_mean_deg`, `slope_frac_lt5`, `slope_frac_lt15`, `slope_frac_gt30` | mean slope [deg], shares of ground flatter than 5°/15°, steeper than 30° [0–1] |
| `sun_noon_elev_max_deg`, `sun_noon_elev_min_deg`, `polar_night`, `polar_day` | yearly noon sun height range [deg], flags |
| `dust_aod_mean` | yearly mean dust optical depth [unitless]; null until MERRA-2 is unblocked |

### L1m `cells-r4-monthly.parquet` (new, one row per hexagon and month: 1,101,600 rows)

| Column | Meaning | Source |
|---|---|---|
| `h3`, `month` | hexagon, month 1–12 of 2023 | — |
| `lst_day_k`, `lst_night_k` | monthly mean day / night ground temperature, median over the hexagon's pixels [K]; null under the coverage rule | MOD11C3 |
| `lst_diurnal_k` | `lst_day_k − lst_night_k` when both exist [K] | MOD11C3 |
| `lst_valid_pixels` | pixels with both values that month | MOD11C3 |
| `sun_noon_elev_deg` | noon sun height on the 15th of the month [deg] | computed |
| `daylight_h` | day length on the 15th [hours] | computed |
| `polar_day`, `polar_night` | sun never sets / never rises on the 15th | computed |
| `dust_aod` | monthly dust optical depth; null until unblocked | MERRA-2 |

**Coverage rule (team choice, found while building #58).** A monthly median
counts only if at least **25%** of the hexagon's pixels have a value that
month. Otherwise it's null, with reason `too-few-lst-pixels`. Without this
rule, a cloudy month with 1 clear pixel out of 65 set a yearly night minimum
of 240.5 K in the New Guinea highlands (the per-pixel rule gave 284.2 K). It
drops 0.52% of hexagon-months.

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
- wildfire by month comes from MCD64A1 burned area once it's in (P1);
- the UI shows EONET's disclaimer next to the events (ADR-0006), and each
  event links to its source (`_derived/eonet-events-r4.parquet`).

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
| `cells.bin` + `cells.json` | `assembled/sites-r4` columns the UI uses, as column arrays (Float32, NaN = null), plus column names, units, null reasons |
| `monthly/<column>.bin` | one `assembled/sites-r4-monthly` (or `-spread`) column for all hexagons × 12 months, loaded only when a step needs it |
| `objectives.json`, `trait-map.json`, `campaigns.json` | L3 tables + `assembled/campaign-sites` as JSON |
| `trait-scales.json`, `data-coverage.json`, `hazard-events.json` | copied from `assembled/` |
| `build-manifest.json` | for every file: sha256, and the sha256 of every L0 snapshot it came from |

Budget: `cells.bin` ≈ 91,800 × 30 columns × 4 bytes ≈ 11 MB raw (~4 MB
gzipped). Each monthly column ≈ 4.4 MB raw.

## 5A. Per-source tables and cleaning (stage C)

**One source family, one builder, one table.** Each source family has its
own module in `services/ingest/src/p0ingest/` and writes its own table to
`_derived/`. Builders never write into another builder's table; the assembler
(§5B) joins them. That way two people can add sources at the same time without
editing the same file.

| Family | Module | Table(s) in `_derived/` | Status |
|---|---|---|---|
| core (temperature, land cover, terrain, permafrost, sun) | `process.py`, `monthly.py`, `terrain.py` | `cells-r4`, `cells-r4-monthly` (= L1, L1m) | on main |
| temperature, other years | `years.py` | `cells-r4-monthly-years` (L1m-years) | #64 |
| context (access, airports, EONET) | `context.py` | `context-r4` (= L2), `eonet-events-r4` | on main |
| burned area | `burned.py` | `burned-r4-monthly` (+ wide `burned_pct_<mm>` in L2) | #65 |
| albedo | `albedo.py` | `albedo-r4`, `albedo-r4-monthly` | #66 |
| regolith thickness | `regolith.py` | `regolith-r4` | #66 |
| dust | `dust.py` | `dust-r4`, `dust-r4-monthly` | #68 |

The old placeholder columns `dust_aod_mean` (L1) and `dust_aod` (L1m) stay
null. Dust lives in `dust-r4*`, and the assembler takes it from there. They're
removed from L1/L1m in a later cleanup PR.

**Every per-source table follows the same contract:**

- one row per H3 r4 land hexagon (the 91,800 of `cells-r4`, same order), or
  per hexagon and month (1,101,600), or per hexagon, year and month; key `h3`
  (+ `month`, `year`);
- physical units only, named in the meta;
- a per-row `missing_reason` (JSON text, trait → short code) for every null;
- a `<table>.meta.json` with: `inputs` (path + sha256 of every input),
  `computed` (one line per column: method and unit), **`cleanRules`** (below),
  `nullRate` per column, and the output's sha256 and size;
- a `check` command that prints row counts, null rates, top codes, sha256s and
  the 5 spot checks, and exits non-zero if anything fails.

**Cleaning happens inside each builder, as written rules, each counted.**
"Cleaning" means turning raw source values into trustworthy physical values,
never changing what was measured. Every rule a builder applies is listed in
`cleanRules` with how many pixels or rows it removed or changed, so a reviewer
can see its effect.

| Rule kind | What it means | Examples (source → rule) |
|---|---|---|
| fill / nodata | drop the source's "no value" markers | MOD11C3 counts < 7500; ESA permafrost 255; travel-time nodata; MCD64A1 −1 (unmapped), −2 (water) |
| scale and offset | raw counts → physical units, as the file says | MOD11C3 × 0.02 K; MCD43C3 scale factor from the file attributes |
| quality flag | drop pixels the producer marks as poor | MCD43C3 BRDF quality layer (#66) |
| valid range | drop values outside the producer's valid range; **never clip** | MOD11C3 valid 7500–65535 |
| coverage | a hexagon value counts only if enough pixels have one | ≥ 25% of the hexagon's pixels (L1m, L1m-years, albedo) |
| dedupe | one record per real thing | EONET: one count per event per hexagon even if several points fall near it; campaigns: one file per campaign id |
| coordinates | one convention everywhere | longitude −180..180, dateline cells split and shifted (context.py), H3 from lat/lon only |
| time | one time base | calendar months 1–12; base year 2023; multi-year tables say their years; EONET start month = first geometry date (UTC) |
| join keys | every table joins on `h3` (+ `month`/`year`) | the 91,800-cell list in `cells-r4` is the master list |

**What cleaning never does:** fill gaps, interpolate, clip outliers, smooth,
or replace a missing value with a default. A value we can't trust becomes
null with a reason. If a strange value is real (e.g. a negative diurnal
range), it stays, and the meta explains it.

## 5B. Assembly (stage A): the tables the workflow reads

`uv run python -m p0ingest.assemble` (#69) joins the per-source tables and the
L3 files into **workflow tables** in `_derived/assembled/`. Assembly only
joins, renames to the registry names, and computes the documented summaries
below. It adds **no verdicts, gaps or scores**: comparing a value to a
requirement stays engine work. It's driven by the **column registry**
`data/pipeline/columns.yaml`: one entry per column (name, unit, source table
and column, cleaning rules, which workflow steps and test categories use it).
A column that isn't in the registry isn't assembled, and a registry column
missing from its source table fails the build.

| Workflow table | One row per | What's in it | Steps |
|---|---|---|---|
| `sites-r4.parquet` | hexagon | every yearly trait from L1, L2, albedo, regolith, dust; `missing_reason` merged across sources | 1 (funnel counts), 2, 3, 4, 5 |
| `sites-r4-monthly.parquet` | hexagon × month | L1m temperatures, sun, plus monthly albedo, dust, burned area | 1 (month window), 2, 3, 5 |
| `sites-r4-monthly-spread.parquet` | hexagon × month | from L1m-years: p10, median, p90 of `lst_day_k` / `lst_night_k` over 2014–2023 (years with a value only; null with `too-few-years` if fewer than 5), and how many years had a value | 4 (field season), 5 (how much a month swings) |
| `hazard-events.parquet` | hexagon × event | EONET named events (title, date, category, source link) | 5 |
| `campaign-sites.parquet` | past campaign | campaign id, name, agency, years, site, its hexagon, and that hexagon's values from `sites-r4` + `sites-r4-monthly` (the campaign's field months, where the source gives them) | 1 (presets), 6 |
| `trait-scales.json` | trait | median, IQR (`s_t` in ADR-0005 D5), min, max and count over all hexagons with a value; yes/no traits marked | 2 (compare), 6 (closeness + Shapley) |
| `data-coverage.json` | objective × trait, and test category × trait | which Earth column backs each trait, its null rate, and `data` / `field` / `earth-cannot` / `none-yet` | 1 (requirement matrix), 3 (gaps) |
| `assembly-report.json` | build | row counts, null rate per column, sha256 of every input and output, join checks | review |

**The 8 test categories (team doc) are joined to data here, not in the UI.**
`data-coverage.json` lists, per category, the traits it needs (MISSION-PLANNER
step 1 table), which columns back them and how complete each is. A category
with a trait we have no column for says `none-yet` for that trait. It's never
hidden.

**Past-mission database (team doc step 6 fields).** `campaign-sites` carries
what the campaign files hold today (name, agency, location, years,
objectives, published constraints, outcomes, sources) plus the site's
environmental conditions from our own tables. The team doc also asks for
instruments tested, field procedures and scientific limitations. Those need
new quoted fields in `contracts/campaign.schema.json` (a later work order),
and stay empty until a source is quoted.

**Join checks the assembler must pass** (printed in `assembly-report.json`):

- every per-source table has exactly the 91,800 `cells-r4` hexagons (and 12
  months, or 10 years × 12 months), with no duplicates;
- every registry column exists in its source and keeps its unit;
- a value never changes in assembly: for each column, assembled = source,
  exactly (checked on all rows);
- `missing_reason` in the assembled row = the union of the source rows'
  reasons, and lists exactly the null columns;
- the 2023 rows of L1m-years equal L1m;
- each campaign's hexagon is the H3 cell of its quoted coordinates.

**L4 publish** reads only `_derived/assembled/`, never the per-source tables,
and converts the workflow tables to the app formats (§5 L4).

## 6. The trait map: Moon/Mars bands to Earth test requirements

The engine compares **Earth columns with Earth-unit bands only** (ADR-0005
D2). `data/requirements/trait-map.yaml` holds, per objective and trait, one
rule:

```yaml
- objectiveId: LI-5L
  dimension: terrain
  earthColumn: slope_mean_deg      # L1 column
  band: {lo: 0, hi: 10}            # Earth units, both ends included
  hiStrict: true                    # optional: value < hi (source says "< 10")
  priority: must                    # must (filters) | nice (shown only)
  unit: deg
  origin: target                    # target | precedent | team | user
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
| Heavy builds (L0 fetch, L1, L1m, terrain) | Andrew's laptop (`drew`), or any machine with ≥ 5 GB free disk and `uv sync` in `services/ingest`. Raw files are about 2 GB. |
| Light jobs (optional) | Oracle instance `instance-20261019-1530` (T3-linked 2026-11-14): aarch64, 2 cores, ~4 GB RAM free, **1.8 GB disk free**, so it never holds raw MODIS or DEM files. It reads our Drive folder with its own remote: `rclone ... gdrive: --drive-root-folder-id 1W4s6X4HTHmF7Xvd8eb1x3FlO-osP07V_` (checked 2026-11-14: rc=0). Nothing runs there on a timer today. EONET and airports are frozen snapshots (new data means a new snapshot), and L2 builds in ~47 s on the laptop. Use it only if a scheduled job is added later (systemd user service; linger is on). |
| Drive mirror state (2026-11-14 18:35Z) | complete: 43 objects, 2.429 GiB. Every MANIFEST snapshot (incl. EONET, travel time, airports, campaign sources) plus `_derived/` L1, L1m, L2 and the EONET event list, each md5-checked after upload. The remotes use rclone's shared Google client id, which rclone says is being retired in 2026; make our own client id if uploads start failing. |
| Looking at the data | JSheets team workbook (DuckDB reads the Parquet files directly), in `research/`, never shipped. See MISSION-PLANNER "Team workbook". |
| Run times (measured 2026-11-14) | L1 53.1 s (`cells-r4.meta.json` `timing.total_s`); terrain 1,038.5 s for the last resumed run (`terrain-r4.meta.json` `secondsThisRun`; the full pass spanned restarts). L1m and L2 targets: under 10 min each. |

## 8. Build order and checks

```text
L0 fetch (each family)  ->  clean + grid (each family's builder, §5A)  ->  per-source tables
                                                                   (cells-r4*, context-r4, burned, albedo, regolith, dust, years)
L3 (PRs, validated by scripts/validate_contracts.py)
per-source tables + L3  ->  assemble (§5B, column registry)  ->  assembled/ workflow tables  ->  mirror to Drive
assembled/  ->  engine publish  ->  L4  ->  atlas
```

Each stage only reads the stage before it. The engine and the UI never read
a per-source table directly.

Checks every build must print (rule 2: paste them in the PR):

- row counts (91,800; 1,101,600 for monthly tables; 11,016,000 for L1m-years),
- each cleaning rule and how many values it removed (`cleanRules`),
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
| 11 | EONET zero events could read as "safe"; EONET counts could read as rates; EONET has no licence of its own | EONET shown as named events only, never a rate (§4.1, L2); use approved by the owner under NASA's open data policy with the disclaimer shown (ADR-0006) |
| 12 | Team doc asks for "top X" sites; rule 4 bans a site score | Pareto layers + one user-chosen trait as tie-break (MISSION-PLANNER step 1) |
| 13 | Team doc's 8 test categories need data we don't have (caves, biology, wind) | Category table in MISSION-PLANNER step 1 marks each one ready / partial / no; missing traits stay unknown |
| 14 | Several people add sources at once, but L1/L1m have one builder (process.py) | One builder and one table per source family; the assembler joins them (§5A, §5B) |
| 15 | L1/L1m have empty `dust_aod*` columns, while dust now comes from `dust-r4*` | The assembler takes dust from `dust-r4*`; the empty columns are dropped from L1/L1m in a cleanup PR |
| 16 | The team doc's past-mission database asks for instruments, procedures and limitations; the campaign schema doesn't have them | `campaign-sites` carries what's quoted today; new quoted fields come with a schema change (later work order) |
