# ADR-0015 — Source QA Policy for Copernicus GLO-30 DEM, MODIS MOD11C3/MYD11C3, and Input-Filter Accounting (#76)

Date: 2026-11-15  
Status: **proposed** (owner freeze required before re-running any scientific table rebuild)  
Work order: [#76](https://github.com/andrewkoumoudjian/cosmic-consultants/issues/76)  
Related: [ADR-0007](ADR-0007-data-preparation-scope.md), [ADR-0014](ADR-0014-explicit-release-examples.md) (PR #184)

## Context

Work order #69 (`clean_audit.py`) surfaced three open source-quality gaps tracked in #76:

1. **Copernicus GLO-30 DEM (`terrain.py`):** the historical `terrain-r4.npz` build (`26,450` tiles, `2,923,236,898` pixels at overview level 2 / ~240 m) read unmasked DEM arrays (`ds.nodata = None`). Ocean pixels are encoded as `0.0 m`, and inland lakes/rivers carry flat water elevations, so coastal and lakefront H3 cells with `land_pct_mean > 0` received `0.0°` water slopes.
2. **MODIS MOD11C3 v061 (`monthly.py`, `years.py`):** only the raw count guard `raw >= 7500` (`_FillValue = 0`, scale `0.02 K`, 25% H3 pixel-coverage rule) was applied. Neither `QC_Day` / `QC_Night` bit filtering nor the full 10-year (`2014–2023`, 120-granule) input-filter accounting was audited.
3. **Missing historical input-filter counts (`clean_audit.py`):** several datasets whose pinned raw inputs exist locally (`esa-cci-permafrost`, `travel-time-to-cities-2015`) or whose builders recorded native counts in `_derived/*.meta.json` still showed `output-counts-only` / `null` in `cleaning-report.json`.

Per project rules, **historical derived artifacts are preserved untouched**, licenses are verified first, and **QA policy is proposed and frozen here before changing any scientific calculation**.

## Verified licenses

All audited datasets have `license.verified: true` in `data/catalog/`:

| Dataset | Catalog ID | Verified License |
|---|---|---|
| Copernicus GLO-30 DEM + AUXFILES WBM/EDM | `copernicus-dem-glo30` | `copernicus-dem-licence` |
| MODIS/Terra LST Monthly CMG | `modis-mod11c3` | `cc0` |
| MODIS/Aqua LST Monthly CMG | `modis-myd11c3` | `cc0` |
| MODIS Land Cover CMG | `modis-mcd12c1` | `cc0` |
| ESA CCI Permafrost v5.0 (NH + Antarctica) | `esa-cci-permafrost-extent-*` | `esa-cci-permafrost-terms` |
| Global Travel Time to Cities (2015) | `travel-time-to-cities-2015` | `cc-by-3.0` |

## Empirical QA replay findings (no historical calculations altered)

### 1. Copernicus GLO-30 DEM & WBM/EDM live probe
- **Historical ledger (`terrain-r4-ledger.jsonl.gz`):** verified all `26,450` tiles in `copernicus-dem-glo30/tileList.txt` (`0` missing, `0` extra, `0` errors, `26,450` `arraySha256` digests, `0` mask fields). Because `terrain._read_tile` applied no nodata/water mask, `appliedNodataFilterCount = 0` and historical `invalidInputValues` stays `null` (never fabricated).
- **Coastal / water overlap in `cells-r4.parquet` (`91,800` cells):** `91,285` cells have DEM pixels (`515` null). Of those `91,285` cells, `7,619` have `water_pct > 50%` (MCD12C1), `6,400` have `land_pct_mean < 50%` (MOD11C3), and `763` have exact `slope_mean_deg == 0.0` with `elev_min_m == elev_max_m == 0.0`.
- **Live S3 probe across 7 representative tiles (`docs/qa/source-qa-76/dem-wbm-probe.json`):**
  - Ocean coast (`N68_00_E055_00` Pechora Sea): `45,363 / 101,250` (`44.8%`) exact `0.0 m`; `WBM = {0: 54860, 1: 45770, 2: 587, 3: 33}`; `407` `WBM=1` boundary pixels have interpolated non-zero overview elevation.
  - Inland lake (`N47_00_W087_00` Lake Superior): `202,500 / 202,500` (`100%`) `WBM=2` (`EDM=9`) at ~`183 m`, `0` exact-zero pixels (`z==0: 0`).
  - Lake Baikal (`N53_00_E108_00`): `95,387 / 135,000` (`70.7%`) `WBM=2`.
  - Desert/mountain (`N38_00_W111_00` Utah): `EDM = {1: 195882, 2: 6238 (infilled), 4: 1, 9: 4, 10: 375}`.

### 2. Full 120-granule MODIS MOD11C3 v061 replay (2014–2023)
Replayed all `120` SHA256-verified HDF4 granules (`3,110,400,000` Day pixels and `3,110,400,000` Night pixels; `docs/qa/source-qa-76/mod11c3-qa-replay.json`):
- **`raw >= 7500` equivalence:** `0` pixels across all 120 granules have `raw >= 7500` with `mand_qa in {2, 3}`, and `0` pixels have `raw < 7500` with `mand_qa in {0, 1}`. The existing `raw >= 7500` filter already removes 100% of `10` (cloud) and `11` (not produced) pixels.
- **Mandatory QA `00`-only is unusable for global 2023 coverage:** in 2023 Collection 6.1, ~72% of valid pixels carry `mand_qa = 01` (*"other quality"*), mostly with `LST error <= 2 K`. Requiring `mand_qa == 00` collapses 2023 H3 cell-month retention (at `>= 25%` pixel share) from `98.94%` / `98.11%` to **`10.61%` Day / `11.43%` Night**.
- **LST Error bits (`6–7`) among `raw >= 7500` pixels (120 granules, 2014–2023):**
  - Day (`1,061,238,815` valid px): `<= 1 K`: `800,857,331` (`75.46%`), `<= 2 K`: `255,818,265` (`24.11%`), `<= 3 K`: `4,355,702` (`0.41%`), `> 3 K`: `207,517` (`0.020%`).
  - Night (`1,053,817,781` valid px): `<= 1 K`: `812,072,707` (`77.06%`), `<= 2 K`: `236,206,315` (`22.41%`), `<= 3 K`: `5,166,161` (`0.49%`), `> 3 K`: `372,598` (`0.035%`).
- **H3 cell-month retention (`>= 25%` CMG pixels):**

| Candidate Policy | 2023 Day Kept (`/ 1,101,600`) | 2023 Night Kept (`/ 1,101,600`) | 2014–2023 Day Kept (`/ 11,016,000`) | 2014–2023 Night Kept (`/ 11,016,000`) |
|---|---|---|---|---|
| `P0`: `raw >= 7500` (baseline) | `1,089,887` (`98.9367%`) | `1,080,764` (`98.1086%`) | `10,899,346` (`98.9410%`) | `10,802,596` (`98.0628%`) |
| `P1`: `raw >= 7500` & `LST error <= 3 K` | `1,089,878` (`98.9359%`) | `1,080,699` (`98.1027%`) | `10,899,265` (`98.9403%`) | `10,801,846` (`98.0560%`) |
| **`P2`: `raw >= 7500` & `LST error <= 2 K`** | **`1,089,224` (`98.8765%`)** | **`1,079,386` (`97.9835%`)** | **`10,892,533` (`98.8792%`)** | **`10,788,223` (`97.9323%`)** |
| `P3`: `mand_qa == 00` only | `116,912` (`10.6129%`) | `125,940` (`11.4325%`) | `5,746,542` (`52.1654%`) | `5,083,952` (`46.1506%`) |
| `P4`: `raw >= 7500` & `LST error <= 1 K` | `905,351` (`82.1851%`) | `933,568` (`84.7466%`) | `9,002,126` (`81.7186%`) | `9,348,987` (`84.8673%`) |

### 3. Additional pinned raw replays completed
- **ESA CCI Permafrost v5.0 (`esa-cci-fill-255`):** NH (`6000 × 36000 = 216,000,000` px) masks `172,869,206` (`255` fill) and retains `43,130,794`; Antarctica (`2500 × 36000 = 90,000,000` px) masks `89,392,599` (`255` fill) and retains `607,401`.
- **Travel Time to Cities 2015 (`raster-nodata`):** `17400 × 43200 = 751,680,000` px masks `530,356,617` (`nodata = -9999.0`, `0` non-finite) and retains `221,323,383`.

## Decisions (proposed for owner freeze)

1. **Preserve historical artifacts until freeze:** keep `terrain-r4.npz`, `cells-r4*.parquet`, and `dem-unmasked-source` in `data/pipeline/columns.yaml` unchanged until the owner freezes this policy and authorizes a separate rebuild PR.
2. **Proposed DEM policy (`wbm-land-edm-nonvoid-v1`):** mask all `WBM != 0` (`1=ocean`, `2=lake`, `3=river` — preventing `0.0°` slopes on both ocean coasts and inland lakes such as Lake Superior/Baikal) AND `EDM == 0` (void) AND non-finite/`nodata`; fail a tile rather than falling back if requested auxiliary masks are unavailable; compute gradients only on retained land neighbors while keeping elevation on isolated valid land pixels. Rename `columns.yaml` from `dem-unmasked-source` to `dem-wbm-edm-mask` only when the masked rebuild lands.
3. **Proposed MOD11C3 (and symmetric MYD11C3) QC policy:** reject `P3` (`mand_qa == 00` only). Recommend **`P2`: `raw >= 7500` AND `LST error <= 2 K` (`(qc >> 6) & 3 <= 1`)**, which removes `0.43%` day / `0.53%` night of coarse `> 2 K` retrievals while preserving `98.88%` day / `97.98%` night 2023 cell-months (`P1: <= 3 K` recorded as fallback if owner prefers minimal change). Apply symmetrically to `MYD11C3` (`lst_aqua.py`) once its 12 granules are restored locally.
4. **Honest non-fabrication rule:** `clean_audit.py` replays every pinned raw file present on disk, surfaces recorded builder `cleanRules`/`qa` from SHA256-verified `_derived/*.meta.json`, and keeps `maskedInputValues = null` wherever raw inputs or historical streaming counts are absent (`dem-unmasked-source`, `modis-myd11c3` when HDFs are not local). `completeInputFilterAccounting` remains `false` until the post-freeze DEM + MOD11C3 rebuilds and missing raw-snapshot replays complete.

## Acceptance (for freeze + subsequent rebuild PR)

- **Audit PR (this PR):** `clean_audit` + `source_qa` reproduce the exact SHA256-verified counts above, `services/ingest/tests` pass, and no historical `_derived/` calculations are altered.
- **Post-freeze rebuild PR (separate step after owner approval):**
  - Freeze `data/pipeline/qa-policy.yaml` status to `accepted`.
  - Run full `26,450`-tile masked Copernicus GLO-30 S3 rebuild (via #184's `terrain.run(mask_water=True)`) and rebuild `cells-r4*` / `cells-r4-monthly*` / `cells-r4-monthly-years*` under the frozen MOD11C3 QC rule, updating `columns.yaml` and `cleaning-report.json` (`completeInputFilterAccounting` evaluated honestly).
