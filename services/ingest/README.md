# services/ingest — W6 (#19): Earth P0 traits per H3 cell

`python -m p0ingest.clean_audit` writes the #69 cleaning report. The assembler
also runs it. It replays the current 2023 LST/land-cover thresholds against
hashed raw inputs, counts output nulls separately and preserves unavailable
historical input counts as unknown. The report exposes two current source
quality gaps: MOD11C3 QC bits are not filtered, and the terrain reader does
not apply a nodata mask. Metadata now describes those actual behaviours.
No physical values are changed by this diagnostic; scientific review and
source rebuilds remain separate work.

Turns hashed NASA/ESA/Copernicus snapshots into one table: a row per H3 land
cell (resolution 4, about 1,770 km² each, 91,800 cells), with the raw traits
for terrain, thermal, illumination, surface material and water ice. Anything
we couldn't compute is **null**, and the reason is in `missing_reason`. No
guesses, no fills (AGENTS.md rule 3).

What was downloaded, why, and what we deliberately left out:
**[INVENTORY.md](INVENTORY.md)** (generated from `data/snapshots/MANIFEST.json`).

## Shared data mirror (Google Drive)

Raw payloads are big (~2 GB) and gitignored, so they're mirrored here:
**https://drive.google.com/drive/folders/1W4s6X4HTHmF7Xvd8eb1x3FlO-osP07V_**

- `MANIFEST.json` in git is still the source of truth. Every mirror copy is
  checked against its sha256 before it's used.
- One-time setup (any machine): install rclone, then
  `rclone config create ccdrive drive scope=drive root_folder_id=1W4s6X4HTHmF7Xvd8eb1x3FlO-osP07V_`
  and log in as a Google account the folder is shared with.
- **Mount it** (read-only): `scripts/drive_mount.sh` mounts it at
  `~/mnt/cosmic-drive` (override with `CC_DRIVE_MOUNT`).
- **Use it:** `uv run python -m p0ingest restore` copies every manifest file
  that's missing locally from the mount and checks its hash. `fetch()` does the
  same thing automatically before it downloads anything.
- **Update it** after new fetches: `scripts/drive_sync.sh`. That's
  `rclone copy`, never `sync`, so nothing on Drive is ever deleted. `_derived/`
  is skipped by default; it rebuilds in ~2 min plus the terrain pass.

## Run it

```bash
cd services/ingest
uv sync
uv run python -m p0ingest.fetch_p0      # MODIS LST + land cover 2023 (Earthdata token needed)
uv run python -m p0ingest.terrain       # Copernicus GLO-30 overview pass, ~30 min, streams ~9 GB, stores none
uv run python -m p0ingest.process       # -> _derived/cells-r4.parquet (L1) + cells-r4-monthly.parquet (L1m), ~80 s
uv run --with pandas python -m p0ingest.check_monthly   # W17 checks; exit 0 only if all pass
uv run python -m p0ingest.inventory     # -> services/ingest/INVENTORY.md
```

The Earthdata token is read from `~/.config/cosmic-consultants/earthdata-token`
(never commit it). It's only sent to Earthdata hosts, including across
redirects.

## Output: `cells-r4.parquet`

One row per H3 cell (`h3` is the hex id). Columns are raw measurements, not
losses or scores. Comparing them with Moon/Mars target ranges is the engine's
job (W7), using the envelopes from W5. The file's schema metadata and
`cells-r4.meta.json` list every input file with its sha256, plus timing and
the null rate per column.

## Output: `cells-r4-monthly.parquet` (L1m)

One row per H3 cell and month of 2023 (1,101,600 rows): monthly day and night
ground temperature (median over the hexagon's pixels), the day-night swing,
noon sun height, day length and polar day/night on the 15th. Spec:
`docs/plan/DATA-PIPELINE.md` §5.

- **One temperature rule:** L1 `lst_day_max_k` / `lst_night_min_k` are the
  max / min over the L1m months, so the two files always agree.
  `check_monthly` checks this exactly.
- **Coverage rule:** a monthly median only counts if at least 25% of the
  hexagon's pixels have a value that month (our choice). Otherwise it's null
  with `too-few-lst-pixels`. It drops 0.52% of cell-months (mostly cloudy
  tropics).
- **`missing_reason`** in both files is JSON per row and names only that row's
  null traits.

## Clean and assemble (W29, #69)

Run `uv run python -m p0ingest.assemble` after source builders. It uses
Polars and `data/pipeline/columns.yaml` to join yearly/monthly traits,
historical monthly spread, named hazard events and campaign sites into
`data/snapshots/_derived/assembled/`. The report records input/output hashes,
key checks, unchanged-value checks, missingness and skipped planned sources.

`data-coverage.json` includes every feature in the 55-feature inventory,
using `data/pipeline/feature-preparation.yaml`. A related column is never
reported as an implemented exact feature. Category availability is partial;
field evidence, instrument-specific quantities and missing sources remain
explicit. Historical spread describes 2014–2023; it is not a weather forecast.

The Google Doc IDEA workflow governs the data modules (ADR-0007). Source
builders keep their own tables. The generic Drive sync script excludes
`_derived/`; copy prepared outputs separately and verify their hashes.

The merged dust tables are required inputs. Contributing-month counts, valid
pixel counts, modeled-thickness support fractions, burned mapped-year counts
and the month of the dust maximum have
`role: diagnostic` in the registry (ADR-0010). They stay in native units in
both raw and normalized frames, with exact value/type checks. These diagnostics
do not become physical traits or enter a closeness sum. The coverage report
also retains all eight detailed menus separately from the Doc's 19-category
table; exact test support still needs source review.

`data/pipeline/evidence.yaml` adds one descriptor (`kind`, `support`,
`family`) per registry column so observations, reanalysis, models,
catalogues, and geometry stay separated, `synthetic` values are rejected in
assembled tables, `assemble` rejects `NaN`/infinite floats, and `source-gap`
features carry a dated `absenceScope` stating the scope searched rather than a
claim of absence. Counting `family` values is a discovery hint only;
corroboration requires per-claim review.

Run `python -m unittest discover -s tests -v` for the assembly regressions.

## Temperature history (W24, #64)

`uv run python -m p0ingest.years fetch|build|check` prepares the 2014–2023
monthly temperature panel. It uses the same monthly medians and 25% pixel
coverage rule as the 2023 table. The output is
`_derived/cells-r4-monthly-years.parquet`, keyed by `(h3, year, month)`.

The check verifies the 120 input hashes and output hash, requires exactly
one row for every land cell and calendar month, compares 2023 to L1m exactly,
and checks per-row missing reasons. Run the key-validation regression tests
with `python -m unittest discover -s tests -v`.

These are monthly composites, not observed daily temperature extremes.
They do not complete the separate `tsurf_max`, `tsurf_min` or `tsurf_range`
features in the 55-feature inventory. Additional years are for historical
conditions; this table does not predict future weather or mission losses.

## Planetary source preparation (#74)

```bash
uv run python -m p0ingest.planetary fetch
uv run python -m p0ingest.planetary build
uv run python -m p0ingest.planetary check
uv run python -m unittest discover -s tests -p test_planetary.py
```

The first batch downloads 14 labelled/documented PDS files (760 MB) and
writes three Parquet files under `data/snapshots/_derived/planetary/`:

- `diviner-south-prp.parquet`: 2,880,000 south-pole triangle records.
  Source geometry and planetocentric centre coordinates are retained.
  `temp_avg` is model annual average temperature **2 cm below the surface**;
  `temp_max` is model annual surface maximum. Both are Kelvin.
  `ice_depth` is calculated ice-stability depth in metres, not measured ice
  depth. Source -999 becomes null; zero stays zero; the raw value is retained.
- `tes-thermal-inertia-day.parquet` and `tes-thermal-inertia-night.parquet`:
  25,920,000 pixels each. Thermal inertia is model-derived, in
  J/(m² K √s), using 1999–2004 observations. The usable value excludes
  source-interpolated pixels and values outside the published computed
  range. Raw integers and interpolation flags survive. Zero-based source
  line/sample indices retain the native grid; labels and DSMAP document
  the IAU_1991 frame and 20 pixels/degree map. No Earth H3 assignment is made.

`preparation-report.json` records every input/output hash, units, field
descriptions, time support, null/exclusion counts and caveats. Readers use
bounded batches and disk-backed source arrays. Byte counts, labels, masks,
source exclusions and output hashes are checked; independent raw-file spot
checks are recorded in the work order. Runtime checks establish preparation
integrity; scientific status remains `executed-unreviewed`. Target-specific
extraction, new physical feature calculations and source-model validation
remain open. See ADR-0008.

TES spatial extraction also needs review: the DSMAP equation signs conflict
with the document's stated upper-left/edge convention. Source indices are
preserved; no geographic lookup is performed in this batch.

`uv run python -m p0ingest.campaign_measurements` extracts three reported
ARADS 2019 achieved-result quantities into `_derived/campaign-measurements/`.
It checks the existing raw article hash and retains exact source passages
and character offsets. Unknown historical conditions stay explicit.

The owner's eleven additional NASA/CSA/ESA/JAXA resources are mapped to
existing catalog rows and candidate preparation uses in
`data/sources/agency-portals.yaml`. Run `uv run python -m p0ingest.source_portals`
to record fresh HTTP checks under `data/snapshots/source-portal-probes/`.
These checks preserve failures and never claim dataset or licence acceptance.

Mirror these source directories and `_derived/planetary/` with `rclone copy`,
then run `rclone check --one-way --checksum`. Delivery is pending until that
check completes. Do not overwrite the shared Drive MANIFEST from an isolated
branch; reconcile committed entries when integrating source work.

## Known gaps (also in INVENTORY.md)

- **dustProcess:** MERRA-2 is blocked. GES DISC returns HTTP 403 until the
  Earthdata account approves the "NASA GESDISC DATA ARCHIVE" app.
- **waterIce:** ESA CCI only models 25–85°N and 60–85°S. Its fill is unknown,
  not 0%. It's also driven by MODIS LST, so it doesn't independently confirm
  thermal.
- **subsurface / operations:** not in P0 yet.
- **illumination:** computed from latitude only (no terrain shadowing).

## W26 (#66) source tables: albedo + regolith (my own section)

Two additional source families, built by their own modules. The parent
assembler joins them; these tables do not edit L1/L1m/L2.

- `python -m p0ingest.albedo --fetch` downloads 12 MCD43C3 v061 daily CMG
  granules, dated the 15th of each 2023 month (a dated 16-day BRDF retrieval
  window each, NOT a calendar-month mean). `python -m p0ingest.albedo` builds
  `_derived/albedo-r4-monthly.parquet` (1,101,600 rows: h3 x month 1-12,
  `albedo_ws_sw`, `albedo_bs_sw`, per-field valid-pixel counts, per-row
  `missing_reason`) and `_derived/albedo-r4.parquet` (91,800 rows:
  `albedo_ws_sw_mean`, `albedo_months_used`, same for black-sky). Only
  `Albedo_Quality == 0` pixels count and a hexagon keeps a value only with
  >= 25% valid-pixel support; each `.meta.json` carries the real QA counts,
  per-sample window dates read from the files, units and model limits.
- `python -m p0ingest.regolith --fetch` downloads the six Pelletier et al.
  2016 (ORNL DAAC 1304) 30-arcsec GeoTIFFs + the user guide; downloads are
  checked against the publisher's public sha256 sidecars. `python -m
  p0ingest.regolith` builds `_derived/regolith-r4.parquet` (91,800 rows):
  per-hex exact histogram medians of upland regolith thickness
  (`regolith_thick_m`), upland soil, sedimentary deposit and the product's
  weighted average, with support fractions, per-class pixel counts, the
  native fill kept as null, the published 50 m upper valid bound retained,
  and per-row `missing_reason` (e.g. `outside-product-coverage` south of
  60 S). Model output, not a measurement; lunar regolith is NOT claimed
  equivalent.
- `python -m p0ingest.w26_check` (also with `-O`) runs the transformation
  regression tests, the key-domain checks against the master cell set and
  5-site spot checks (Death Valley, Haughton, Atacama, McMurdo, Mauna Loa)
  against the raw sources; exit 0 only if all pass.

## Map placement check (#74)

`uv run python -m p0ingest.projection_check fetch|run` checks where the native
planetary products sit on their body, using independent references only:
MOLA MEGDR topography (4 and 16 px/deg) and the USGS/IAU Gazetteer of
Planetary Nomenclature. MOLA itself is first checked against named montes and
planitiae. The report goes to `_derived/planetary/projection-check.json`.

- TES thermal inertia: the label text is right (line 1 = 90 N, sample 1 =
  180 W). The DSMAP equations' signs are wrong. The night map matches MOLA's
  fine structure under that mapping only, and the day map agrees with the night
  map under the same mapping only.
- Not resolved: a residual apparent longitude offset (night peak about
  +0.3 deg east). Day and night disagree on it, so it is not one grid error.
  Slope-aspect response and the IAU 1991 (TES) vs MOLA frame difference both
  move it. No correction is applied. Treat TES positions as uncertain at that
  size until a cited frame transform exists.
- Diviner PRP: centre lat/lon recomputed from the three body-fixed vertices
  match the table, and named south-polar crater floors are colder than their
  rims far more often than with east/west mirrored positions.

This is placement evidence only. No value changes and no target association.

## Output: `burned-r4-monthly.parquet` (W25, issue #65, Mistral Vibe helper)

One row per land cell and calendar month (91,800 x 12 = 1,101,600 rows):
`h3`, `month` (1-12), `burned_pct` [%], `years_mapped` (0-10),
`missing_reason` (JSON). Source: MODIS MCD64A1 v061 monthly 500-m tiles
(CMR `C2565786756-LPCLOUD`, licence CC0), 2015-2024, 32,160 granules
(268 tiles x 120 months, live count re-probed at use time).

- `burned_pct` is the mean over 2015-2024 of each year's share of burned
  mapped-land pixels (Burn Date > 0 / >= 0; water -2 never in the
  denominator). Only years with mapped pixel support count, and
  `years_mapped` says how many did.
- No mapped support -> null, never 0, with a reason per row:
  `outside-mcd64a1-tiles` (no granule tile covers the cell at all, e.g.
  all Antarctic land) or `no-mapped-land-in-period` (pixels exist, none
  mapped land in that month any year).
- Streaming rule as `terrain.py`: each granule is downloaded, decoded,
  hashed and dropped. Every source URL/hash/bytes/time is in
  `_derived/burned-r4-ledger.jsonl.gz` (hashed in the meta and MANIFEST).
  A checkpoint commits counts + ledger length atomically; on restart the
  partial ledger is truncated to the checkpoint so uncommitted granules
  are re-fetched, never skipped, and reissued/duplicate granules are a
  hard error (no double counting).
- Run: `uv run python -m p0ingest.burned` (resumable; Earthdata token
  needed). Spot checks: `uv run python -m p0ingest.burned --spots`.
  Tests: `uv run python -m unittest tests.test_burned` (also under `-O`).

## W31 (#89) wind: MERRA-2 10 m wind per hexagon

One more source family, built by its own module; the parent assembler joins
it. No other module was touched.

- The mean wind speed comes from a real SPEED field: I opened real monthly
  granules of both MERRA-2 collections and read their variable lists first.
  M2TMNXSLV monthly has only the vector components U10M/V10M (`10-meter_east_wind`,
  `10-meter_northward_wind`) and NO speed field; the monthly wind SPEED lives
  in M2TMNXFLX (`surface_wind_speed`, m s-1). So `data/catalog/merra2-m2tmnxflx.yaml`
  is a new registry row (CC0, license-verified by the registry probe), and
  `wind.py` never computes speed from |mean U, mean V| (that is biased low by
  Jensen's inequality; `check` proves 0 violations of mean speed >= |mean
  vector|, the speed field being up to 12.4 m/s above that biased bound).
- `python -m p0ingest.wind fetch` downloads 24 granules (12 FLX + 12 SLV,
  2023, v5.12.4, ~1.8 GB - offset 0). `python -m p0ingest.wind build` maps
  each master hexagon center to the NEAREST native 0.5 x 0.625 deg MERRA-2
  grid center (pole rows clipped, longitude wrapped) and writes
  `_derived/wind-r4-monthly.parquet` (1,101,600 rows: h3 x month 1-12;
  columns `wind_speed` (SPEED monthly mean, m s-1), `wind_speed_max`
  (SPEEDMAX monthly mean, the mean of hourly maxima), `u10m_mean`/`v10m_mean`
  (labelled VECTOR COMPONENTS from M2TMNXSLV, direction context only) and
  `missing_reason`) plus `_derived/wind-r4.parquet` (91,800 rows:
  `wind_speed_mean` = mean of the 12 monthly speeds, `months_used`). All
  24 granules verified fully covered their month; no fills anywhere, so no
  row carries a reason (the machinery stays in place for next year).
- Limits are explicit in both `.meta.json` files: 10 m Earth wind is not the
  last km of Mars descent; air density differs (pressureRegime mismatch);
  MERRA-2 is a reanalysis, not a measurement.
- `python -m p0ingest.wind check` (also with `-O`, see above): exact key
  domain (91,800 h3 x 12 months, master cell set), no duplicates, key/column
  schema, aggregation consistency, missing_reason naming, physically
  plausible ranges, the Jensen speed-field sanity check and 5 raw-granule
  spot checks (Death Valley, Haughton, Atacama, McMurdo, Mauna Loa) - all raw
  vs parquet values MATCH; exit 0 only if all pass (`ALL PASS`).

## Aqua LST monthly table (W34, #93, my own section)

`python -m p0ingest.lst_aqua fetch` pulls the 12 monthly MYD11C3 V061
(MODIS/Aqua LST/Emissivity, 0.05 deg CMG) granules of 2023 through
`snapshots.fetch` (URL + fetch time + sha256 + bytes + licence in
`data/snapshots/MANIFEST.json`, ~855 MB raw total, licence cc0, NASA ESDIS
default, row already verified in `data/catalog/modis-myd11c3.yaml`).
`python -m p0ingest.lst_aqua build` writes `_derived/aqua-lst-r4-monthly.parquet`
(1,101,600 rows = 91,800 cells x 12 months) + `.meta.json`, the aqua twin of the
Terra L1m table: monthly medians of day/night LST per hexagon. It imports
`monthly.py` and `grid.py` read-only (never edits them): same 0.05 deg
pixel-to-hexagon rule (pixel centre inside the H3 res-4 cell via
`h3.latlng_to_cell`, land share > 0, support counts kept in
`lst_valid_pixels`), same fill rule (raw counts < 7500 = fill, x0.02 K), same
25%-pixel coverage rule (below it the month is null with reason
`too-few-lst-pixels`), medians, sun geometry on the 15th from the cells table
latitudes. `missing_reason` is per-row JSON whose keys are exactly that row's
null value columns (`lst_day_k` / `lst_night_k` / `lst_diurnal_k`);
`lst_diurnal_k` is null exactly when day or night is null. 2023 result:
10,994 day nulls, 22,822 night nulls (1.0% / 2.1%).

Why it matters: Aqua's composites come from ~13:30 (day) / ~01:30 (night) local
solar time overpasses; Terra's table from ~10:30 / ~22:30. Together the two
tables give four times of day per month for the tsurf_max / tsurf_min /
tsurf_range proxies (monthly composites, NOT daily extremes) and for
thermal-inertia ingredients. Sanity read against the Terra table: Aqua day is
+2.3 to +3.6 K warmer per month (afternoon vs mid-morning overpass), Aqua night
~1.6 K cooler (01:30 vs 22:30) — physically consistent.

`python -m p0ingest.lst_aqua check` (also with `-O`) verifies: exact key set
(91,800 cells-r4 hexagons x 12 months, no duplicates, no extra/missing cells),
physical ranges (lst 150-360 K, diurnal -80-80 K, support counts sane), per-row
`missing_reason` keys equal to that row's null value columns, and 8 raw spot
checks (need >= 5) that recomputed cell/month medians straight from the .hdf
granules with an INDEPENDENT pixel lookup (re-derived per check run via
`h3.latlng_to_cell`, not the cached map) match the table exactly.

MOD21C3 probe (recorded, not built): `modis-mod21c3` (Terra TES algorithm,
monthly 0.05 deg CMG, C2565791050-LPCLOUD, cc0 verified) is USABLE in
principle — same CMG grid, monthly day/night LST (`LST_Day` / `LST_Night`,
uint16, scale 0.02, valid 7500-65535) plus band-29/31/32 emissivity. One
granule (A2023182, 128 MB) fetched and inspected 2026-11-14. NOT built here:
it duplicates day/night LST from the same sensor family (registry note:
algorithmic cross-check only, NOT independent) and the W34 monthly-only scope
does not need it; building it later is a small job (same reader shape, 12 x
128 MB). Filed as a possible follow-up with the parent assembler wiring.

## W49 (#108) target sites: cited Moon/Mars extraction points (my own section)

One YAML file per named site under `data/targets/` (see `data/targets/README.md`
for the full schema and the per-null reasons). Rows carry planetocentric
east-positive centres where the source publishes numerals, quoted verbatim from
sha256-pinned snapshots only; NASA's Artemis releases publish region outlines as
graphics only, so those rows have `centreLat`/`centreLon` null with an explicit
`missingReason` instead of invented centres. Gazetteer-sourced feature rows
re-compose their quote from the USGS centre-point DBF exports. Landing sites
record the great-circle km to their host IAU feature in `usgsCrossCheck`
(Curiosity 51.4 km from the Gale centre, Perseverance 45.6 km from Jezero's,
Spirit 3.6 km from Gusev's, etc.); Zhurong is left coordinate-less with a
`missingReason` because no snapshottable official NASA/USGS source carries its
touchdown numbers.

- `python -m p0ingest.targets` (quiet: `-q`) loads every `data/targets/*.yaml`,
  checks required fields/enums/ranges, filename/id match, quote parsability
  (lat/lon re-parsed from the quote and compared to the declared centre),
  MANIFEST sha256/url match, gazetteer quote recomposition, and
  `usgsCrossCheck` tolerance; exit 0 only when everything passes.
- `tests/test_targets.py` covers the quote parsing, the DBF reader, the
  convention folding and the per-row checks with synthetic fixtures, plus an
  integration test that the real `data/targets/` rows all pass.

## W42 (#101) Moon neutron and gamma-ray maps: moon_nuclear

`uv run python -m p0ingest.moon_nuclear fetch|build|check` prepares:

1. **Lunar Prospector GRS (`lp-grs-pds`):** 2, 5 and 20 degree elemental
   abundance maps (`lpgrs-high1-elem-abundance-{2,5,20}deg.parquet`), keeping
   the upper-triangle error matrix plus label-declared 1-sigma columns.
2. **LRO LEND ALD (`lend`):** all 6 `LEND_RDR_ALD` spatial relative neutron
   count-rate maps (`ALDE` 1 deg global `-80..80`, `ALDN` 0.5 deg north polar
   `80..90`, `ALDS` 0.5 deg south polar `-90..-80`; `20090915` Nominal Mission
   and `20111211` Science Mission) under `data/snapshots/_derived/planetary/lend/`.
   Zero-exposure cells (`exposure <= 0`, PDS `-1.0` sentinel) become explicit
   `null` with JSON `missing_reason: "exposure-zero"`. Relative counting rates
   are NOT converted into H/WEH wt% or epithermal suppression %; `h_wt_neutron`
   remains recorded as a gap in `lend-pds-gap-report.json` alongside `LP-NS`.
## Dust per hexagon: `_derived/dust-r4[-monthly].parquet` (W28, #68)

MERRA-2 `M2TMNXAER` v5.12.4 (GES DISC, CC0), variable `DUEXTTAU`
("Dust Extinction AOT [550 nm]", dimensionless) for all 12 months of 2023.
Access was re-probed independently before fetching: HTTP 206 with token on
2026-11-14T19:46Z (evidence in
`data/snapshots/registry-probes/2026-11-14/dust-68-gesdisc-access.json`);
the earlier 403 EULA block from 18:47Z is gone.

- `uv run python -m p0ingest.dust fetch|build|check` — 12 granules,
  `_derived/dust-r4-monthly.parquet` (h3, month, dust_aod, missing_reason;
  1,101,600 rows) and `_derived/dust-r4.parquet` (h3, dust_aod_mean,
  dust_aod_max, dust_aod_max_month, months_used, missing_reason; 91,800
  rows), each with `.meta.json` (inputs + sha256, native grid, QA counts,
  model limits).
- **Mapping:** each hexagon's center goes to the nearest native 0.5 x 0.625
  deg grid center (per-axis; lat clipped at the exact +/-90 rows; lon wraps
  modulo 576). That's a nearest-center sample, NOT an area-weighted hexagon
  mean and NOT a finer measurement. Up to 4 hexagons share one native cell.
- **Annual rule:** mean/max use only documented valid monthly observations;
  `dust_aod_max_month` is the earliest month hitting the max (ties -> earliest);
  `months_used` stays in the table so partial-year support is visible. In this
  2023 build every land cell has all 12 months (the granules contain zero
  fill cells), so there are no nulls; the fill code paths still run and are
  covered by `tests/test_dust_keys.py`.
- **Limits, stated in the output metadata too:** MERRA-2 is a reanalysis, not
  a direct measurement. DUEXTTAU is a column-integrated atmospheric dust
  optical depth at 550 nm — a dustiness proxy for the air column, not surface
  dust coverage, not a hazard rate, and NOT equivalent to a Mars opacity tau.
- Parent note: the "dustProcess" line under Known gaps above is stale for
  source preparation; integration into `cells-r4*` is the parent's (#69).

## Moon geology context products (#98)

`p0ingest.moon_geology` prepares two source-native Moon context tables plus
two licence-blocked gap reports. Fetch, build and check via
`uv run python -m p0ingest.moon_geology <fetch|build|check>`. No resampling
to H3: these are lunar, not Earth, datasets.

- `unified-geologic-map-moon` (USGS/Astropedia 1:5M unified geologic map,
  CC0-verified). `_derived/planetary/unified-geologic-map-moon/
  geo-units-polygons.parquet` keeps all 12,247 polygon records with WKB
  geometry (little-endian Polygon/MultiPolygon), source-native units table
  `map-units-domu.parquet` (49 DOMU rows) and per-record metadata. Source CRS
  is Moon2000_EquidistantCylindrical_clon0 on the GCS_Moon_2000 sphere
  (r=1,737,400 m); the `.prj` file content is verified against the declared
  projection before building. Output is the exact linear inverse
  (lon_deg = rad2deg(x/R), lat_deg = rad2deg(y/R)), so longitudes land in
  [-180, 180). Ring nesting uses the immediate-smallest-container rule with
  even depth = outer, odd depth = hole (3,159 holes attached; shapefile
  winding is normalised on WKB write, vertices untouched). Point lookups
  should use smallest-containing-polygon. 592 polygons carry source code
  `Iohs`, which has no DOMU row (DOMU lists `Ios`); those rows get a null
  `unit_name` with `missing_reason`, recorded not fixed.
- `lroc-pits-atlas` (Catalog of Lunar Pits v1, March 2021; licence
  established as US public domain via the LROC data-terms page). The 146 MB
  catalog PDF is parsed with pypdf (no pdftotext on the build machine):
  278 pits, one row each, with `lat_deg`, `lon_deg_east` (0-360 east-positive
  exactly as printed), the verbatim coordinate strings, the six measured
  value columns (inner/funnel max/min diameters, depth, long-axis azimuth)
  each paired with its verbatim source string (including `>` / `<` prefixes),
  and a `missing_reason` whose keys are exactly the null value columns.
- `robbins-moon-craters` and `lroc-nac-boulders-watkins`: BLOCKED - neither
  source publishes a licence statement (checked product pages, PDS bundle
  documents and the PDS Imaging node; evidence with URLs and dates in the
  gap reports). Per the missing-stays-missing rule their values are NOT used;
  each writes `_derived/planetary/<datasetId>/gap-report.json`.
- `check` verifies key uniqueness, physical ranges and reason/null matching
  for pits, plus raw spot checks: 5 pit pages re-read from the PDF, and the
  geologic table re-read from the shapefile (polygon roundtrip at records
  0/999/2500/6000/12246) with 5 named site lookups (Apollo 11, Apollo 15,
  Tycho, Aristarchus, Mare Imbrium). Tests: `uv run python -m unittest
  discover -s tests` (plain and `-O`), including
  `tests/test_moon_geology.py`.

## W46 (#105) Mars CRISM MTRDR spectral summary parameters (my own section)

Mars, source-native grid (no H3). `python -m p0ingest.mars_crism --fetch`
snapshots the PDS Geosciences MTRDR bundle `mrocr_4001`: the monthly index
tabs (`mtrdr*_index.tab`, 2006-2012), bundle docs (aareadme, readme, errata,
`mtr_map.cat`, `indxinfo.txt`, the MTRDR SIS) and 10 map-projected
SPECTRAL_SUMMARY_PARAMETERS (SU) scenes around Jezero (FRT000066A4,
HRL000040FF), Gale (FRT0001B696, FRT0000901A), Meridiani (FRT0000334D),
Gusev (FRT00003192), Mawrth Vallis (FRT0000C596, FRT000119DC), and Nili
Fossae (FRT0000805F); full per-region mapping lives in SCENES in the
module. All ~1.2 GB pass through `snapshots.fetch` (URL, UTC fetch
time, sha256, bytes, licence in MANIFEST.json). Us-pd licence, already
verified in `data/catalog/crism-mro.yaml`.

`python -m p0ingest.mars_crism` builds
`_derived/planetary/crism-mtrdr/crism-mtrdr-summary.parquet`
(5,264,901 rows). Key is `(observation_id, source_line, source_sample)`;
`latitude`/`longitude` are pixel centres on each scene's equirectangular
map, from the label corner pins (validated against all four corners).
14 parameters with the source's own names and definitions — BD1900_2,
BD1900R2, D2300, BD2290, BD2210_2, BD2165, SINDEX2, BD2100_2, BD2500_2,
MIN2295_2480, MIN2345_2537, OLINDEX3, LCPINDEX2, HCPINDEX2 (Viviano-Beck
et al. 2014), kept unthresholded. Fill value 65535 becomes null plus a
per-row `missing_reason` whose keys are exactly that row's null parameter
columns ("fill-65535"). `check` verifies MANIFEST hashes, keys, footprint
bounds, missing reasons, and compares 18 spot pixels (168 band values)
against direct raw reads of the .IMG cubes. Gaps in
`preparation-report.json`: no licensed global CRISM summary-parameter
mosaic exists in PDS; Gale Bradbury landing-site pixels are outside the
archived v3 MTRDR scenes. TES-comparable caveats: scene positions carry
~0.3-0.5 deg CRISM map uncertainty; indices are band-depth ratios, not
abundances.

## Mars ice + neutron source tables (#106): GRS + SWIM (my own section)

`python -m p0ingest.mars_ice fetch|build|check|drive` prepares static,
dataset-native Mars maps. No resampling, no H3, no similarity work; the
parent assembler joins what it needs.

- **ody-grs-pds** (PDS Geosciences `ODY-M-GRS-5-ELEMENTS-V1.0`, product
  version 2.0): the published derived element concentration maps from
  2002-06-04 to 2005-04-03. Thirteen labelled snapshot files produce five
  Parquet tables under `data/snapshots/_derived/planetary/ody-grs-pds/`:
  `grs-weh-5deg-smoothed.parquet` (2,592 bins: WEH, the mapped H2O wt%,
  with both published sigma columns), `grs-weh-2deg-unsmoothed.parquet`
  (15,840 bins, published negatives retained), `grs-th-5deg-smoothed.parquet`,
  `grs-k-5deg-smoothed.parquet` (both ppm) and
  `grs-kth-ratio-5deg-smoothed.parquet` (K/Th ratio; its PDS label says
  "parts per million" for a ratio — quirk kept as labelled). Keys are the
  published bin centres (latitude, longitude); only the label
  NOT_APPLICABLE_CONSTANT 9999.999 becomes null, with a per-row JSON
  `missing_reason` whose keys are exactly that row's null value columns.
  WEH is model-derived (inversion against forward-modelled counts with
  water/iron correction factors, per catalog/dataset.cat). Sensing depth is
  order ~1 m of regolith (gamma lines shallower, neutrons deeper) — a
  literature property, not stated in metres in the archive. The suite
  samples to a fixed depth for the whole 2002–2005 window: static map, no
  time step to preserve.
- **swim-mars-ice** (SWIM consistency layers, Morgan et al. 2021): blocked
  during this work order. swim.psi.edu answered HTTP 523 (origin down) on
  every probe since 2026-11-14 22:29 UTC; no PDS, ScienceBase or
  data.nasa.gov mirror exists (searches returned 0). The registry row also
  records the licence as unresolved — usable values need both a live fetch
  and licence evidence. Evidence and retries are on issue #106 and the
  board.

`check` verifies every input hash/size against MANIFEST, output hashes,
uniqueness of (latitude, longitude), exact published bin centres,
documented plausibility ranges, `missing_reason`-vs-null agreement and 5
raw spot checks per product against an independent whitespace-split parse
(25 total). `swim_status` records a live SWIM probe into the wave of
evidence. Unit tests: `python -m unittest discover -s tests`. Drive copy:
`python -m p0ingest.mars_ice drive` (rclone + checksum verify).

## Mars THEMIS IR controlled mosaics, six landing-site ROIs (W45, #104, my own section)

- `python -m p0ingest.mars_themis fetch` downloads, through
  `snapshots.fetch` (MANIFEST: URL, fetch time, sha256, bytes, licence), the
  STAC item list of the USGS collection `mo_themis_controlled_mosaics`
  (CC0-1.0), the ISIS3 mapping labels of all 28 quads x day/night, the
  provenance.txt of the 10 used quads, and 10 quad GeoTIFFs (~4.3 GB raw:
  Jezero -> mc13 Syrtis Major, Gale + Gusev -> mc23 Aeolis, Elysium/InSight ->
  mc15, Utopia -> mc14 Amenthes, Meridiani -> mc19 Margaritifer Sinus). The
  MCS (mcs-mro) EDR label and DATASET.CAT are fetched as probe evidence.
  Three evidence-only URLs are best-effort (logged SKIP, never fatal): the
  THEMIS global-TI FGDC docx 404s on every re-fetch of 2026-11-14, so its
  licence evidence lives only as quoted text in
  `data/catalog/themis-global-thermal-inertia.yaml`.
- `python -m p0ingest.mars_themis build` writes
  `data/snapshots/_derived/planetary/themis-ir-controlled-mosaics/themis-ir-{day,night}-rois.parquet`
  (2,121,771 rows each = 6 sites x ~1 deg ROI on the NATIVE 100 m/pixel
  IAU_2015:49910 simple-cylindrical grid; keys site/quad/source_line/
  source_sample; pixel CENTRE -> lon/lat via the GeoTIFF affine, no H3 step
  for Mars) plus `preparation-report.json` (S3 inputs, hashes, per-site
  windows and clips, DN stats, gaps, cross-check).
- `python -m p0ingest.mars_themis check` verifies MANIFEST licence flags,
  input hashes, output hashes/sizes/row counts, unique keys, 8-bit physical
  range, coordinates in physical range, missing_reason exactly matching null
  DNs, and 24 raw spot checks (12 coordinates x day/night) reading the same
  native pixel straight from the COG. Exit 0 in both plain and `-O` runs.
- Features: `ir_brightness_dn` (8-bit DN). THE MOSAICS ARE QUALITATIVE: values
  are NOT kelvin and NOT TIU, so `tsurf_max`/`tsurf_min`/`tsurf_range` and a
  THEMIS `ti` are recorded as gaps. `ti` remains covered by the TES mosaic
  (~3 km/px); the USGS 100 m quantitative THEMIS TI mosaic is blocked on an
  unresolved licence (accconst=None/useconst=None, no explicit grant per the
  LICENCE-AUDIT-41 precedent). MCS (mcs-mro) publishes only per-orbit
  ~4-hour granules, i.e. finer than the at-most-monthly rule, so it is
  probe-only; no monthly surface-temperature climatology could be used.
- Diagnostic cross-check (nothing adjusted): THEMIS night DN vs TES thermal
  inertia, Spearman rho per site (nominal 0.05 deg TES grid, both longitude
  conventions): Gale ~0.42; Jezero 0.05-0.11; Elysium -0.03..0.08; Utopia
  -0.00..0.03; Gusev 0.03..0.08; Meridiani -0.16. Weak overall, consistent
  with per-quad DN stretching and the ~0.3-0.5 deg TES position uncertainty
  (PR #87).

## W38 (#97) earth_static: MOD44B VCF per-hex table + two blocked-source probes

One delivered Earth context table plus recorded access evidence for the two
sources the work order asked for that cannot be fetched by this repo yet.

- `python -m p0ingest.earth_static --fetch` downloads, via
  `p0ingest.snapshots.fetch` (so MANIFEST.json records url, fetch time,
  sha256, bytes and licence), the v061 user guide and all 291 granules of
  the latest complete yearly series of MOD44B Vegetation Continuous Fields
  (collection C2565805839-LPCLOUD; CC0 in the catalog row). Completeness
  rule: the newest series whose tile set equals the previous series's
  (A2025 == A2024, 291 tiles each, decided in the CMR listing).
- `python -m p0ingest.earth_static build` reads the native 4800x4800
  250 m HDF4-EOS tiles, inverts the MODIS spherical sinusoid exactly
  (phi = y/R, lambda = x/(R cos phi), R = 6371007.181 m — cross-checked
  against GDAL in the tests), bins each tile's pixel centres into the
  0.05 deg CMG lattice (3600x7200, `grid.py`), and maps lattice pixels to
  the 91,800 master H3 res-4 cells through the pinned MOD11C3 land-share
  map (`grid.cmg_cell_map`; pixel centre inside the H3 cell via
  `h3.latlng_to_cell`). Per lattice pixel: mean of the valid (0-100)
  native pixels; per hexagon: median over its lattice-pixel means and the
  exact mean over its native pixels, with support counts at both scales.
  Declared codes only: 200 water and 253 fill never enter statistics;
  the guide declares no masking rule, so Quality/Cloud layers are NOT
  applied. Tile-plane corners beyond the globe ellipse (|lon| > 180 after
  inversion, observed residual code 11 there) are excluded as `offglobe`
  and counted per layer. Output `_derived/vcf-r4.parquet` (91,800 rows,
  `vcf_*_pct_median`, `vcf_*_pct_mean`, support counts, per-row
  `missing_reason`), `_derived/vcf-r4-cmg.npz` (lattice sums/counts) and
  `vcf-r4.meta.json` (rule, QA, known C61 sparse-training limit, inputs
  with sha256). 2026-11-14 run: 291/291 granules, 9.9 GB raw, null rate
  9.91 percent (high-latitude not-retrieved areas stay null, never 0).
- `python -m p0ingest.earth_static check` verifies the key set is exactly
  cells-r4's, no duplicates, physical ranges (0-100 or null), support
  consistency, `missing_reason` keys equal to each row's null value
  columns and 5 raw spot checks (central Amazon, central Sahara, boreal
  Canada, Iowa cropland, Greenland ice sheet) that re-gather the covering
  tiles' native pixels independently and compare against the stored
  lattice npz. 2026-11-14: `"ok": true`, 0 errors, 5/5 green.
- Probes, not delivered (no values used, tables not shipped):
  `nsidc-ggd318-permafrost` data is access-blocked — the legacy NSIDC ECS
  host refuses TCP and daacdata.apps.nsidc.org redirects to an interactive
  URS OAuth login we do not have (the licence itself is resolved:
  reuse with citation, Brown et al. 2002, DOI 10.7265/skbg-kf16 — catalog
  row updated); `earth-impact-database` (passc.net) serves a 114-byte JS
  redirect to a parked page and re-probes the same on 2026-11-14. Evidence
  in `_derived/earth-static-probes.json` (`python -m p0ingest.earth_static
  probe` re-runs it); catalog rows carry the probe results.

## W37 (#96) PALSAR L-band radar backscatter, campaign-site regional table (my own section)

`alos-palsar-rtc-high` (ASF Hi-Res RTC, 12.5 m, gamma0; licence "© NASA [Year],
Includes Material © JAXA, METI [Year]", verified in the registry row). The global
family is ~506k single-date scenes, so this is REGIONAL by the declared subset
rule: for each of the six campaign files in `data/campaigns/`, the site hexagon
plus its H3 ring-1 neighbours (7 cells per site; FMARS and HMP-2015 share a
parent) -> exactly 35 keys. Per key: median HH and HV gamma0 in dB over a
deterministic stride-30 subgrid (every 30th row and column of the 12.5 m raster
= 1/900 of pixels, pooled across the scenes of the union cover), valid-subpixel
counts, scene URs and acquisition dates (ALOS-1 scenes, 2006-2011). Pixel
centres go through `h3.latlng_to_cell(lat, lon, 4)` after a per-window
CRS->WGS84 projection — stated in both the docstring and the `.meta.json`.

**Proxy limits (important):** PALSAR is L-band (1.26 GHz) LINEAR polarization.
The engineering targets `radar_ka_backscatter` (Mars, Ka band) and `cpr_minirf`
(Moon, circular polarization ratio) are a different band and polarization
basis. No conversion was made and none is claimed — weak Earth-side analogue
only.

- `python -m p0ingest.palsar --query` — live CMR probe per cluster, greedy
  fewest-scenes cover (a cell counts covered when its centre + 6 vertices lie
  inside the UNION of chosen footprints; scenes are rotated strips), writes the
  selection file and prints the size plan (real run 2026-11-14: 43 scenes,
  14.74 GB, 0 uncovered cells).
- `--fetch` would download the chosen scenes via `p0ingest.snapshots.fetch` (the ASF
  host is added to the Earthdata-host tuple at call time; MANIFEST provenance).
  **Still blocked 2026-11-15, post-EULA**: the Earthdata account HAS now approved
  ASF's application/EULA (client_id BO_n7nTIlMljdvU6kRRB3g) but a PAT alone still
  cannot drive datapool downloads — datapool/data.asf redirect to URS
  `oauth/authorize` (app_type=401), which rejects EDL tokens in every form
  (401 "HTTP Basic: Access denied" with bearer, basic and query-token variants);
  `cumulus.asf.alaska.edu/s3credentials` DOES issue STS creds but its
  DownloadRoleInRegion role denies `s3:GetObject` on `asf-cumulus-prod-protected`
  for every RTC_HI_RES key layout probed; TEA `/locate` has no route for these
  buckets; CMR publishes no `s3://` URLs for C1206487504-ASF. Full evidence on
  issue #96. A working path needs an interactive Earthdata browser login (or a
  username/password .netrc), not a PAT.
- `--build` writes `_derived/palsar-r4-sites.parquet` + `.meta.json`; with the
  fetch blocked the table carries 35 rows of explicit nulls with
  `missing_reason` `asf-download-auth-unreachable` (missing stays missing on
  purpose). A cell's median needs >= 50 valid subgrid pixels, else
  `not-enough-valid-pixels`.
- `--check` validates columns, keys (exactly the 35 subset cells), no
  duplicates, the dB physical guard, and that `missing_reason` keys match the
  null value columns of each row exactly; with raw scenes present it
  recomputes 5 cells' medians straight from the raw zips and compares. The
  pipeline is exercised offline by `tests/test_palsar.py` (synthetic RTC
  GeoTIFFs; 17 tests; full suite green in normal and `-O` mode).
