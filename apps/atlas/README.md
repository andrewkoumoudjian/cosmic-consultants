# Atlas — the readiness map (W11, issue #21)

A static site: pick a NASA Moon-to-Mars objective, see where on Earth it can be
rehearsed, and see how ready each place is.

**Everything in `mock/` is synthetic.** The sites, their coordinates and every
gate outcome were invented so the map has something to draw while the data and
engine lanes (#19, #20) are still working. They are not assessments of the
real places whose regions they sit in. The map says so in the banner and in
every dossier.

## Run it

```bash
cd apps/atlas
npm ci          # pinned versions, see package.json
npm run dev     # http://localhost:5173
npm run build   # type-check + static build into dist/
npm run preview # serve the build
npm run check:mock  # validate the mock data against the contract
```

`npm run check:mock` is the important one for CI. It checks that

- every file in `mock/sites/` validates against `contracts/site.schema.json`,
- the ARL of every readiness entry is the level its gates give (the rule frozen
  in `proofs/Analog/Readiness.lean`: the level is the largest k ≤ 6 whose gates
  1..k all pass, and gates 1–4 must pass for *every* required dimension),
- the limiting gate and limiting dimension are right,
- nothing in the data carries a single similarity score or a cross-objective
  total (AGENTS.md rule 4),
- every mock site says SYNTHETIC,
- the objective rows copied into `src/data/objectives.json` still match
  `data/objectives/*.yaml` (run `npm run sync:objectives` to refresh them).

## What is where

| Path | What it is |
|---|---|
| `src/main.ts` | App wiring: objective picker, layers, dossier panel |
| `src/map.ts` | MapLibre map, NASA GIBS basemap, site marker layers |
| `src/arl.ts` | The ARL ladder, the ordinal colour ramp, the ARL recompute rule |
| `src/dossier.ts` | The site dossier: gate ladder, limiting dimension, vector, "Earth cannot rehearse" |
| `src/objectives.ts` | The objective rows (copied from the contracts lane) and the greyed-out non-rateable list |
| `src/data/objectives.json` | Generated from `data/objectives/*.yaml` by `npm run sync:objectives` |
| `mock/sites/*.json` | The synthetic sites (one file per site) |
| `mock/generate_mock.py` | Regenerates the mock sites; it recomputes the ARL with the frozen rule |
| `scripts/check-mock.mjs` | The check script described above |
| `scripts/sync-objectives.mjs` | Copies the objective rows into the app |
| `screenshots/` | One screenshot per P0 objective, taken from the built app |

## The basemap

NASA GIBS WMTS, "Blue Marble Shaded Relief and Bathymetry (MODIS)",
EPSG:3857, tile matrix set `GoogleMapsCompatible_Level8`, JPEG tiles:

```
https://gibs.earthdata.nasa.gov/wmts/epsg3857/best/BlueMarble_ShadedRelief_Bathymetry/default/GoogleMapsCompatible_Level8/{z}/{y}/{x}.jpeg
```

No API key and no NASA branding, which is what the challenge rules ask for.
The layer identifier and tile URL came from the live WMTS capabilities document
(`https://gibs.earthdata.nasa.gov/wmts/epsg3857/best/1.0.0/WMTSCapabilities.xml`)
and a tile was fetched on 2026-11-14 to confirm it returns a real image.

## Rules the app follows

- **No single similarity score, anywhere.** The colour of a marker is the
  ordinal readiness level for the objective you picked. The per-dimension
  numbers are shown next to it, never summed. Levels of different objectives
  are never combined.
- **The level never appears on its own.** Every level comes with the gate
  ladder, the limiting dimension and gate, the per-dimension vector and the
  objective's "Earth cannot rehearse this" list (gravity, air pressure,
  radiation).
- **Unknown stays unknown.** A site with no readiness entry for the selected
  objective is drawn as a grey hatched marker, and the panel says "not rated
  here", not "bad".

## What lands next

The map code **does change**. The ARL ladder above is superseded
([ADR-0005](../../docs/decisions/ADR-0005-mission-planning-workflow.md)), and
W11b turns this page into the six-step mission planner
([docs/plan/MISSION-PLANNER.md](../../docs/plan/MISSION-PLANNER.md), § UI):
an H3 hexagon layer instead of site points, six step cards instead of the
dossier, and no ARL legend. It builds against a mock L4 until the engine (#20)
publishes the real one; switching is one config line, and the mock banner
stays up until then.

W11b slice 1 (#121) is in: `src/plan-url.ts` turns a plan request into the
URL query and back, following `contracts/plan-request.schema.json` (#79), so
a plan is a shareable link. `npm test` checks that it round-trips exactly and
rejects bad links with a clear message. The UI doesn't use it yet.
