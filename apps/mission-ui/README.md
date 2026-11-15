# Mission UI: Analog Atlas

**Live: https://cosmic-mission-ui.pages.dev/** (deploy with `npm run build`, then
`wrangler pages deploy <copy of dist> --project-name cosmic-mission-ui --branch main`).
Eight steps over the shared planner engine and the real `planner-v1` release; no sample values.
The notes below describe the first Figma build and are kept for history.

This builds the **CosmicConsultants** Figma file
(`iXj7QQ2xY8MlOfth7eQKrC`) in React, with Motion for animation and three.js
for the Moon and Mars on step 1. It covers all seven screens:

| Route | Figma frame | Screen |
|---|---|---|
| `#/location` | `01 / Location — Moon`, `— Mars` | Pick Moon or Mars (live three.js planets) |
| `#/category` | `02 / Category — … / 1–8` | Pick one mission category |
| `#/metrics` | `03 / Metrics — …`, `Picker / …`, `Condition / menu`, `Priority / menu` | Requirements table, metric picker, menus |
| `#/sites` | `04 / Site finder` | Candidate list, spider chart, site map |
| `#/limitations` | `05 / Limitation report` | Verification matrix, limitations, trade-offs, evidence |
| `#/logistics` | `06 / Logistics` | Glance table, seasonal heatmap, per-site plan |
| `#/risks` | `07 / Risks` | Risk matrix, exposure by site, register |

`Draft saved / prototype confirmation` is the Save draft dialog.

It's a **separate app** from `apps/planner` (#181/#182), whose owner-chosen
look is different. Both can be compared side by side.

## Run it

```bash
cd apps/mission-ui
npm ci
npm run dev        # http://localhost:5181
npm run build      # type-check + static build into dist/
npm run pending    # list every placeholder and what it waits on
```

Visual and interaction checks (need `npx vite preview` running and a Playwright
Chromium on the machine):

```bash
npm run shots -- out/   # one screenshot per screen at 1440 px, the Figma frame width
node scripts/smoke.mjs out/   # clicks through the flow, checks phone width and console errors
```

## Placeholders: what is real and what isn't

Anything the data pipeline doesn't publish yet is a **named placeholder**,
made with `PENDING(id, awaits, sample)` in `src/data/`. The id names the
value. `awaits` says which table, column or work order will supply it. The
sample is the value drawn in Figma, kept only so the layout can be checked.
On screen:

- each section that uses one shows a dashed amber chip with its id (hover it
  to see what it waits on);
- the sidebar counts them, and **Highlight placeholders** outlines every
  section that isn't real data.

`BLOCKED(id, reason)` covers two things the Figma shows but AGENTS.md rule 4
forbids: a single "match %" per site and an "AVG" fit per site. They render as
an empty `—` slot until the owner decides.

What is real today:

- the category list maps to `categoryId`s in `data/pipeline/test-categories.yaml`;
- each metric names its active column in `data/pipeline/columns.yaml`, or says
  it has none yet (`pipeline.metric.<id>`);
- everything the user enters (world, category, metrics, conditions, targets,
  priorities, removed sites, chart choice) drives the report screens. The
  target column, the bold "required" rows, and the matrix and exposure
  numbers on the risks screen are computed from it.

Everything from step 4 on (sites, verdicts, logistics, risks) is placeholder
data until the engine (#20) and the step 4–6 tables exist. Run
`npm run pending` for the full list (41 today).

## Where things are

| Path | What |
|---|---|
| `src/styles/tokens.css` | Figma variables, same names (`--mission-*`, `--chart-series-*`, `--status-*`) |
| `src/data/pending.ts` | `PENDING` / `BLOCKED` and the registry |
| `src/data/catalog.ts` | Worlds, categories, metric menus, pipeline column links |
| `src/data/placeholders/*.ts` | Step 4–7 design samples, one file per screen |
| `src/state.tsx` | Mission state, hash routing, draft save |
| `src/three/Planet.tsx` | The three.js Moon (halftone) and Mars (engraved strata). Procedural and illustrative, not maps. Falls back to the Figma stills without WebGL |
| `src/screens/*` | One file per screen group |

Motion respects `prefers-reduced-motion`. The planets stop turning then.
