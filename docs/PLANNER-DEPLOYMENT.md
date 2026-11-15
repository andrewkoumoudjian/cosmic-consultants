# Build and publish the planner

The browser runs the TypeScript engine compiled by Vite. There is no Rust/WASM
build target. Python runs the data release and campaign optimization offline.
No Python service, API key, or server-side solver is required by the static app.

## Build the data

Use the project Python environment, with its pinned dependencies and the optimizer
requirements in `services/engine/README.md`. Point at a verified assembly, not the
raw source folders. Source QA remains partial under #76.

```sh
PYTHONPATH=services/engine/src python -m planner.release ASSEMBLED RELEASE --repo "$PWD"
```

The release summary reports campaign errors. Each example repeats its parameter
origin and basis from `data/pipeline/release-scenarios.yaml`. These are illustrative
team assumptions, not accepted planetary bands. An uncertified estimate is never
stored in `certifiedSuboptLe`.

`cells.bin` holds the existing app fields plus land share. Extra yearly fields
live in `yearly/<column>.bin`; the data adapter's `ensureYearly` loads and verifies
them on demand. Monthly arrays also load on demand. All files are hashed in the
build manifest. Updating the release does not make a UI render supplementary
target models automatically; UI consumers still need to request those outputs.

## Package an existing UI without editing its checkout

For the white planner, use the checked-out PR #182 as APP_SOURCE. The separate
dark `apps/mission-ui` app is not supported by this packager yet; its author must
push it and connect its placeholder screens to the engine adapter first.

```sh
python scripts/package_planner.py --repo "$PWD" --app-source APP_SOURCE --release RELEASE --out NEW_DIST
```

The command verifies every release input hash, copies UI source into a temporary
build directory, overlays this branch's shared engine/data adapters, installs the
UI lockfile with `npm ci`, builds, and rejects any single asset over 25 MiB.
It requires a fresh output directory and never overwrites a deployed directory.
`deployment-receipt.json` records source commits, file hashes, and bundle sizes.

Cloudflare Pages supports at most 25 MiB per asset
([limits](https://developers.cloudflare.com/pages/platform/limits/)). Its `_headers`
file applies long caching to hashed Vite assets and revalidation to data and entry
pages ([headers](https://developers.cloudflare.com/pages/configuration/headers/)).
A real `404.html` keeps missing JSON/bin requests from receiving SPA HTML.

After account access is authenticated and the project is selected, the prepared
folder can be uploaded with `wrangler pages deploy NEW_DIST --project-name PROJECT`.
Never include source snapshots, tokens, `.env`, or credentials in NEW_DIST.

For a tunnel, serve NEW_DIST on a new loopback port with `scripts/serve_planner.py`
(copy `index.html` to `planner.html`, the server's site-root check). Verify data
and manifest hashes before switching only the intended public route. Keep the
old service running for rollback. `*.ts.net` links are Tailscale, not Cloudflare.
