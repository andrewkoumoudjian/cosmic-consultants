# ADR-0012: Rebuild the planner UI on React, Base UI, Motion and a 3D globe

- Status: proposed (owner asked for it on 2026-11-15; accepted when the PR merges)
- Issue: #181
- Supersedes: nothing. `apps/atlas/` stays as it is.

## Context

The planner works (#132, PR #149), but the owner finds it ugly. Derek drew the
mission flow in the team's CosmicConsultants Figma file (seven screens, "not
final"). The owner picked the stack: React with Base UI, Motion for movement,
a three.js globe (globe.gl), and JSheets-style tables for data.

Three open PRs edit `apps/atlas/src/planner/engine.ts` and its tests (#157,
#167, #171). A rewrite inside `apps/atlas/` would collide with all three.

## Decision

1. **New app at `apps/planner/`**, built with Vite. `apps/atlas/` is left
   untouched, and the old planner keeps working until the owner retires it.
2. **One engine, not two.** The new app imports
   `apps/atlas/src/planner/engine.ts`, `data.ts` and `apps/atlas/src/plan-url.ts`
   as they are. Verdicts, the funnel, Pareto layers and the hashed data loader
   stay the code that the 459 golden cases (`npm run check:planner`) test against
   Python. The UI adds no verdict logic.
3. **Same data release.** It reads `./data/planner-v1/` from the one release
   (`python -m planner.release … apps/atlas/public/data/planner-v1`). Vite's
   `publicDir` points there, so a single release serves both apps.
4. **Stack, with exact pins** (each released at least two weeks before
   2026-11-15): React 19.3.1, `@base-ui/react` 1.9.0 (unstyled, accessible
   controls), `motion` 14.9.0, `globe.gl` 2.46.2 on `three` 0.187.0, Vite 7.3.7
   (released 2026-10-06; `apps/atlas` pins 7.3.8, released 2026-11-09, which is
   too new for the two-week rule) and TypeScript 5.9.3 (the same as `apps/atlas`), `h3-js` 4.1.0, `@types/three`
   0.187.0 and `@types/node` 24.7.0 (the same as `apps/atlas`). Fonts are self-hosted through
   `@fontsource` (Geist Sans 5.3.0, Geist Mono 5.3.0, Source Serif 4 5.3.1), so the
   demo works offline.
5. **The design is followed where it's honest, and changed where it isn't.**
   - The Figma site finder ranks sites by one percentage ("92%", an "AVG"
     column). That breaks AGENTS.md rule 4. The new app shows each site's
     per-trait results (match / miss with gap / unknown) and the engine's order
     (Pareto layer, then the sort trait's gap). There is no percentage and no
     average.
   - Costs, permit timelines, likelihood × severity risk scores and 0–100
     seasonal scores in the Figma frames are illustrative. We hold no data for
     them, so those sections say "not checked" instead of inventing numbers
     (rule 3).
   - The dot-matrix world map becomes a globe drawn from the 91,800 published
     land cells, each colored by its funnel class.
6. **Look: "Observatory".** The owner shared a moodboard on 2026-11-15 (links
   in `apps/planner/DESIGN.md`). They rejected the first take (cobalt on bone
   paper) as ugly, asked for no filler copy, and said the Figma file is a
   loose guide, not the source of truth. So: a white page with one ink and one
   ultramarine accent, big light serif titles, one top bar for navigation, and
   no captions, stat cards or framed panels. The globe is the one dark object on
   the page, styled after the three.js TSL Earth example: a navy sphere, an
   ultramarine atmosphere, and the matching cells glowing like city lights.
   Verdicts are ● match, ◆ miss with gap, ○ unknown: always a shape plus a
   colour, never colour alone. Derek's Moon and Mars engravings and radio icons
   are used as they are. The hero is parked until the owner asks for it.
7. **JSheets is a desktop app, so we export to it.** Checked on 2026-11-15:
   JSheets (matsonj/jsheets-releases) is a native Rust desktop app (egui, with
   DuckDB inside). Its `.jsheets` files are DuckDB databases, and it opens CSV.
   The release "source code" archive only holds the README, and every release
   is newer than two weeks, so there's nothing we could pin or embed in a web
   page. Instead:
   - each report step has an "Open in JSheets (.csv)" button that saves a tidy
     table: one row per compared site and trait (verdict, value, band, gap,
     reason), plus limit and logistics rows. Every row carries the release
     manifest hash. Missing values stay empty, with a reason;
   - the in-app tables borrow the spreadsheet look (thin grid, header row,
     frozen first column, right-aligned mono numbers).
   A test checks that the CSV carries the engine's verdict for all 459 golden
   cases.

## Consequences

- Two front ends exist for a while. The README points to the new one; the old
  one stays as a fallback.
- `npm run check:planner` in `apps/atlas` still guards the engine. The new app
  has its own build and a test confirming that its view layer reads the same
  engine results for the golden cases.
- Bundle size grows (three.js). The globe loads lazily after the data, so step 1
  renders fast.
