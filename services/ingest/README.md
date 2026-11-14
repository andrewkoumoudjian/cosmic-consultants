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

