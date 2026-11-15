# Non-UI continuation receipt — 2026-11-15

This resumes Andrew's stopped data/theorem session. UI components were not edited.
Implementation commits: `5fa94c0` (scenario contract), `ae2b3ce` (runtime and packaging).

## Executed checks

- Engine: `unittest discover -s services/engine/tests -q`, 53 tests, OK with
  `COSMIC_ASSEMBLED_DIR` and `COSMIC_MONTHLY_YEARS_PATH` set to the real local data.
  The same real-data run under `python -O` passes 53 tests, no skips.
- Terrain: 3 tests, OK. Covers isolated land retaining elevation when slope is
  unknown and a requested auxiliary mask failing rather than falling back.
- Contracts: `scripts/validate_contracts.py --self-test`, rc=0, `all contracts valid`.
  Source-payload spot checks skip absent snapshots in this isolated code checkout;
  this run is not a fresh audit of source physics or licences.
- Atlas: 53 tests pass, build rc=0.
- Fresh `planner.release`: 91,800 cells, 459 golden cases, 66 files,
  `campaignErrorCount: 0`.
- `check:planner`: all 459 Python/browser golden cases and all artifact hashes pass;
  Moon 7,599 matches, Mars 10,703 matches on the default requests. Counts describe
  this exact release and are not evidence of scientific validity.
- Packaging: clean lockfile install and Vite build pass. 123 files before receipt
  and server-only alias/sidecars; startup cells.bin 9,547,200 bytes. Largest raw
  asset is the on-demand pareto-targets.json, 23,213,633 bytes (below 25 MiB).
- Browser at the published :10000 URL renders the Moon/Mars screen, 91,800 cells,
  manifest prefix `2cd4e189`; no failed resource responses. It did not fetch any
  supplementary yearly arrays during startup. This is a check from this host,
  not a claim that the owner's Mac connection has been verified.

Release manifest SHA256:
`2cd4e1899bc6111dbe0c3c6251b1392ab4fa1fdf673cc6ea86542c52b1e4b0fe`.

Deployment receipt SHA256 (identical via forced public Funnel route):
`fb5eb9700fd673bd4ad6bd96999fb7dc04d89e5f58f21d93d5412c7ac20c0b7d`.

All four supplementary campaign solves have `certified: false` and
`certificationStatus: uncertified-numerical-tolerance`. Their
`certifiedSuboptLe` is null. Numerical estimates remain in their own field.

## Proof verification

Independently checked PR #140 at `dfada7300d691cc2cc256ea1831ae7140eca5103`
in an isolated Linux worktree using `leanprover/lean4:v4.36.0-rc2`:

- `lake build` process rc=0; `Build completed successfully (18314 jobs).`
- `lake env lean Analog/Audit.lean` process rc=0; all 76 output lines attached
  in `lean-140-audit.txt`. Only `propext`, `Classical.choice`, `Quot.sound` occur.
- No proof source was changed here. #140 is still a separate PR. Its owner
  freeze/replacement decision and ledger cleanup are not silently accepted by
  this compilation run. Mathematical compilation does not certify physics or
  the browser implementation.

## Deployment and remaining work

The same URL `https://drew.tail166795.ts.net:10000/` now points to :4187
(`cosmic-planner-preview-4187`). Old :4185 and :4186 processes remain active.
Default HTTPS and :8443 still point to :4185. Cloudflare was not modified:
the owner clarified that :10000 was the URL intended. Both account connectors
require reauthentication; Wrangler is unauthenticated. The static artifact is
prepared for Cloudflare, subject to authenticated account/project selection.

Remaining non-UI work: #76 full DEM/MODIS QA replay and historical input-filter
accounting; #140 owner acceptance/ledger reconciliation; S8 past-campaign
closeness runtime integration; source-specific incomplete traits in data-coverage.
The new dark mission UI is still another author's app and not part of this build.
