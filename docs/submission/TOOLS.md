# Tools, code and resources (W14, #25)

Space Apps asks teams to list "all of the data, resources, and tools that you
used… including any code, text, and images (even if they are open source or
freely available)" (doc 07, discussion #1821). Pinned versions come from the
repo's lock files at `03a040e`. Re-check them at freeze.

## Our own prior work (listed as prior work, not made during the hackathon)

- **Owner's Lean corpus**, ported to `proofs/Analog/Prior/*` (sources:
  `perps-strategy`, `QUARCC-Umbrella/quant-fund`). Dispositions are in
  `docs/research/06-lean-corpus-inventory.md`.
- **FastOpt screening proofs**, ported to `proofs/Analog/Screening.lean` from
  `QUARCC-Umbrella/quant-fund` (`fastopt/proofs`). The theorem statements are
  unchanged; only the namespace was adapted.

## Languages and toolchains

- Lean 4 `v4.36.0-rc2` (pinned in `proofs/lean-toolchain`) with Mathlib (`proofs/lake-manifest.json`)
- Python 3.12 (CI), managed with `uv` (`services/ingest/uv.lock`)
- TypeScript 5.9.3, Node ≥ 22.12, Vite 7.3.8 (`apps/atlas/package.json`)

## Libraries

| Library | Version | Where |
|---|---|---|
| h3 (Uber H3 hexagon grid) | 4.1.2 | ingest, contract checks |
| numpy | 2.1.3 | ingest |
| pyarrow | 18.1.0 | ingest |
| polars | 2.1.0 | ingest |
| pyhdf | 0.11.6 | ingest (MODIS HDF4) |
| netCDF4 | 1.7.2 | ingest (MERRA-2, ESA CCI) |
| rasterio | 1.4.3 | ingest (DEM, rasters) |
| PyYAML | 6.0.2 | ingest, contract checks |
| requests | 2.32.3 | ingest |
| jsonschema | 4.23.0 | contract checks (CI) |
| maplibre-gl | 6.18.0 | app map |
| ajv / ajv-formats | 8.20.0 / 3.0.1 | app mock-data check |
| js-yaml | 4.3.2 | app objective sync |

## Services and infrastructure

- GitHub (repo, issues as the agents' board #6 and commons #7, Actions CI)
- Google Drive (data mirror, folder `1W4s6X4HTHmF7Xvd8eb1x3FlO-osP07V_`) via rclone
- An Oracle Cloud instance used for data transfer (DATA-PIPELINE §7)
- NASA Earthdata login (LP DAAC, GES DISC) for downloads
- Figma (UI design, Derek's session) and Google Docs (team doc "nasa space apps 2026")
- QUARCC fastopt (planned optimizer, P2, not built)

## AI tools

All AI agents and models are listed in [`AI-USAGE.md`](../../AI-USAGE.md).
