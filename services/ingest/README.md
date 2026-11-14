# services/ingest — W6 (#19): Earth P0 traits per H3 cell

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

## Known gaps (also in INVENTORY.md)

- **dustProcess:** MERRA-2 is blocked. GES DISC returns HTTP 403 until the
  Earthdata account approves the "NASA GESDISC DATA ARCHIVE" app.
- **waterIce:** ESA CCI only models 25–85°N and 60–85°S. Its fill is unknown,
  not 0%. It's also driven by MODIS LST, so it doesn't independently confirm
  thermal.
- **subsurface / operations:** not in P0 yet.
- **illumination:** computed from latitude only (no terrain shadowing).

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
