# Source QA Audit & Replay Receipt — Work Order #76

- **Work order:** [#76](https://github.com/andrewkoumoudjian/cosmic-consultants/issues/76)
- **QA policy:** [data/pipeline/qa-policy.yaml](../../../data/pipeline/qa-policy.yaml) (`status: proposed`) + [ADR-0015](../../decisions/ADR-0015-source-qa-policy.md)
- **Runtime status:** `executed`
- **Scientific status:** `proposed` / `executed-unreviewed` (historical derived artifacts preserved untouched pending owner policy freeze)

## 1. Historical artifacts preserved (untouched, SHA256-verified)

No historical `_derived/` scientific tables or ledgers were modified or overwritten:

| Artifact | Size (bytes) | SHA256 |
|---|---|---|
| `data/snapshots/copernicus-dem-glo30/tileList.txt` | `1,110,900` | `10604e3052c98a09e9216f1a8f0a555a04148419757575f783d4937fd44316dc` |
| `data/snapshots/_derived/terrain-r4.npz` | `3,626,306` | `fc79637f1f3600653ab9723a23cbd6a10cf0dd21f1409c4d452da01823865a1f` |
| `data/snapshots/_derived/terrain-r4.meta.json` | `272` | `6bcb912e8bc24a78a844ccfdd1a53e45eae426902b0b2cb132a2188a95c5af05` |
| `data/snapshots/_derived/terrain-r4-ledger.jsonl.gz` | `1,386,519` | `53470ed0bc8385a78731c76fbe6560ca9252262e3ddb643a2c64b47019e9335b` |
| `data/snapshots/_derived/cells-r4.parquet` | `9,678,906` | `f129020bd11c79c43d8d2f913bd03b34cd34462860bceb018c537e2dd75386f7` |
| `data/snapshots/_derived/cells-r4-monthly.parquet` | `22,865,087` | `63ceebabe76730775ac950a64aa1e4dc95e6a8da35ad8b6db37310e1e9deb784` |
| `data/snapshots/_derived/cells-r4-monthly-years.parquet` | `37,353,107` | `dcb5fe60f4326c517f5a2f456808c25ef56ba7797225ab7c0dc8ea8d156cbe83` |
| `data/snapshots/_derived/context-r4.parquet` | `1,490,243` | `77c4294fc772fa9da79c04c20b65aa58af3f56fd1ca6534f6031fe42e07e0624` |

## 2. Verified licenses (`data/catalog/`)

- `copernicus-dem-glo30`: `copernicus-dem-licence` (`verified: true`)
- `modis-mod11c3`, `modis-myd11c3`, `modis-mcd12c1`: `cc0` (`verified: true`)
- `esa-cci-permafrost-extent-nh`, `esa-cci-permafrost-extent-antarctica`: `esa-cci-permafrost-terms` (`verified: true`)
- `travel-time-to-cities-2015`: `cc-by-3.0` (`verified: true`)
- `ourairports`: `public-domain` (`verified: true`)
- `eonet-v3-events`: `nasa-esds-open-data-eonet-disclaimer` (`verified: true`)

## 3. Committed receipts in this folder

- [`mod11c3-qa-replay.json`](mod11c3-qa-replay.json) — deterministic replay of all `120` SHA256-verified `MOD11C3` HDF4 granules (`2014–2023`, `3,110,400,000` Day px + `3,110,400,000` Night px), proving:
  - `0` anomalies between `raw >= 7500` and `mandatory QA in {00, 01}` across all 120 granules;
  - `mand_qa == 00`-only collapses 2023 cell-month coverage to `10.61%` Day / `11.43%` Night (rejected);
  - `P2` (`raw >= 7500` AND `LST error <= 2 K`) retains `98.88%` Day / `97.98%` Night cell-months in 2023 (`98.88%` / `97.93%` across 2014–2023) while excluding `> 2 K` retrievals (`P1` `<= 3 K` recorded as fallback).
- [`dem-wbm-probe.json`](dem-wbm-probe.json) — historical `terrain-r4-ledger.jsonl.gz` audit (`26,450/26,450` tiles, `0` errors, `appliedNodataFilterCount: 0`, `invalidInputValues: null`, `7,619` `water_pct > 50%` cells & `763` `0.0 m / 0.0 deg` sea-surface cells) plus live S3 `/vsicurl/` probe of 7 representative tiles (`DEM` + `WBM` + `EDM`), showing why `WBM != 0` (including inland lakes `WBM=2` like Lake Superior `100%` and Lake Baikal `70.7%`) and `EDM == 0` are required.
- [`cleaning-report-76.json`](cleaning-report-76.json) — full `p0ingest.clean_audit` report (`45` active rules, `30` live raw threshold replays including `esa-cci-fill-255` = `262,261,805` masked and `raster-nodata` = `530,356,617` masked, explicit `null` wherever raw snapshots/streaming counts are absent locally, `completeInputFilterAccounting: false`).

## 4. Reproduction commands

```bash
# Unit tests (no raw snapshots required)
PYTHONPATH=services/ingest/src services/ingest/.venv/bin/python -m unittest services/ingest/tests/test_clean_audit.py -v

# Full 120-granule MOD11C3 replay + live DEM WBM/EDM S3 probe
PYTHONPATH=services/ingest/src services/ingest/.venv/bin/python -m p0ingest.source_qa audit-all \
  --repo . --snapshots /path/to/data/snapshots --out docs/qa/source-qa-76

# Audit report (verifies the 120-granule receipt SHA256s + replays 2023 MOD11C3, MCD12C1, Permafrost, Travel-Time, DEM ledger)
PYTHONPATH=services/ingest/src services/ingest/.venv/bin/python -m p0ingest.clean_audit \
  --snapshots /path/to/data/snapshots --out docs/qa/source-qa-76/cleaning-report-76.json
```
