# Hackathon plan — Analog Readiness Levels (2026-11-14 → 11-15)

> **Not the current plan any more.** On 2026-11-14 the owner replaced ARL with the
> mission planning workflow: [ADR-0005](decisions/ADR-0005-mission-planning-workflow.md),
> [plan](plan/MISSION-PLANNER.md), [data pipeline](plan/DATA-PIPELINE.md). The
> schedule and submission checklist below still apply.

Written 2026-11-12 (issue #14). Decisions: [ADR-0002](decisions/ADR-0002-analog-readiness-levels.md)
(ARL), [ADR-0003](decisions/ADR-0003-hackathon-delivery-scope.md) (48-h scope) —
both **accepted** (merge #26). **This is the current plan.** On 2026-11-14 the
owner chose to keep ARL and deferred [ADR-0004](decisions/ADR-0004-evidence-backed-comparison.md) (#46).
The Resources tab is now live: see [challenge page](challenge/challenge-page.md#resources-tab). Rules and sources:
[doc 07](research/07-spaceapps-rules-and-m2m-objectives.md). Pitch:
[`pitch/PITCH.md`](pitch/PITCH.md).

## The product in one paragraph

Pick a NASA Moon-to-Mars objective — say *OP-5: operate EVA suits, tools and
vehicles on Mars*. The map shows where on Earth that objective can be rehearsed
and how ready each place is, on a 0–6 **Analog Readiness Level** ladder (like
TRL, but for test sites): from "the data says it matches" up to "a campaign has
already tested this here". Every level shows why: which dimension limits it,
which evidence gate it hasn't passed yet, and what Earth **cannot** rehearse
for that objective (gravity, vacuum or thin air, radiation). An **opportunity
layer** highlights places the data rates as ready but nobody has characterized
in the field yet — where NASA's next field campaign should go.

## Rules of the window

- Build starts **Sat 2026-11-14 09:00 local**; nothing under `services/`,
  `apps/`, new `contracts/` or new Lean before then (doc 07 §1.1). Before then:
  research, registry/provenance, team formation, reading the Resources tab.
- Submit through the Space Apps project page; ≥1 NASA dataset **from this
  challenge's Resources tab** (Global Awards eligibility); 30-s demo video limit;
  AI use disclosed for code and data (`AI-USAGE.md`).
- AGENTS.md still binds: check in on #6, one issue = one branch = one PR,
  evidence over narration, no fabricated fills.

## Backlog → issues

| W | Issue | Lane | Depends on | Must be done by (local) |
|---|---|---|---|---|
| A0 | #1 | docs | guides live Fri 11-13 | **Fri 11-13** (allowed: reading resources) |
| W3 | #4 | data | A0 | Fri 11-13 for registry rows (provenance only) |
| W4 | #5 | research | — | Fri 11-13 (research) |
| W10 | #15 | contracts | ADR-0002 merged | Sat 13:00 |
| W8 | #16 | proofs (statement) | ADR-0002 | Sat 13:00 frozen |
| W5 | #18 | data | W3, W10 | Sat 17:00 |
| W6 | #19 | ingest | W3 | Sat 22:00 (first global pass) |
| W9 | #17 | proofs (proof) | W8 | Sun 09:00 |
| W7 | #20 | engine | W5, W6, W8, W10 | Sun 02:00 first end-to-end; Sun 12:00 final |
| W12 | #22 | research | W4, W7 opportunity list | Sun 14:00 |
| W15 | #23 | data | expectations frozen Sat; run after W7 | Sun 14:00 |
| W11 | #21 | atlas | W10 (mock data from Sat 13:00), W7 | Sun 16:00 feature freeze |
| W13 | #24 | pitch | W11, W15 | Sun 19:00 video locked |
| W14 | #25 | docs | everything | Sun 22:00 submitted |

The atlas starts at Sat 13:00 against **mock artifacts that validate against
W10 contracts** (organizers explicitly allow mock data, #1787), so map and data
pipelines run in parallel and meet Sunday morning.

## Schedule (local time)

| When | Milestone | Exit evidence |
|---|---|---|
| Fri 11-13 | A0: Resources tab + Submission/Judging guides read; registry rows for Resources-listed NASA datasets | A0 diff comment on #1 |
| Sat 09:00 | Kickoff: owner merges/updates ADR-0002/0003; agents check in on #6 and claim W10, W8, W6, W11 | Check-ins on #6 |
| Sat 13:00 | **Contracts + S6 statement frozen**; atlas on mock data | W10, W8 merged |
| Sat 22:00 | First global ingest pass, hashed | W6 manifest |
| Sun 02:00 | First end-to-end ARL artifacts for 1 objective | W7 draft PR |
| Sun 09:00 | S6 Lean-clean (or fallback label per ADR-0003) | Audit output |
| Sun 12:00 | All 3 P0 objectives computed; calibration run | W7, W15 |
| Sun 16:00 | **Feature freeze**; deployed build | URL |
| Sun 19:00 | **Video locked** (≤30 s) + walkthrough | ffprobe |
| Sun 22:00 | **Submitted** (2-h buffer before 23:59) | Screenshot |

## Data plan for P0 (candidates — confirm against the Resources tab in A0)

| Dimension | Earth source (cell value) | Moon / Mars envelope source |
|---|---|---|
| terrain | NASADEM or Copernicus DEM → slope, roughness | LRO LOLA slope · MOLA slope / HiRISE DTM stats |
| thermal | MODIS LST → min, max, diurnal range | LRO Diviner · TES / MCS temperatures |
| illumination | computed solar geometry (min sun elevation, polar day/night) | LOLA-derived illumination maps (south pole) |
| surfaceMaterial | MODIS land cover / NDVI (bare ground) + GLiM lithology (basaltic/anorthositic) | LROC/Clementine-class mineralogy · CRISM/TES mineralogy |
| dustProcess | MERRA-2 dust optical depth | Mars dust climatology (TES/MCS) |
| waterIce | permafrost extent (NSIDC / ESA CCI) | LEND/LAMP PSR ice · SHARAD ice |
| operations (gate 5) | accessibility-to-cities raster + WDPA protected areas | — |

## Submission checklist (W14, refreshed after A0)

- [ ] Project title + one-line summary
- [ ] 30-s demo video link (no NASA logos, no minors, AI imagery watermarked)
- [ ] Project link (repo and/or deployed atlas; owner decides repo visibility)
- [ ] Detailed description incl. what Earth cannot rehearse (R4)
- [ ] NASA data used (≥1 from challenge Resources) + other agencies' data
- [ ] All resources/tools/code listed, incl. owner's prior Lean corpus (`proofs/Analog/Prior/*`, FastOpt port) as prior work
- [ ] AI-use disclosure (code + data) — points to `AI-USAGE.md`
- [ ] Every number on the page traceable to `data/snapshots/`

## Risks

| Risk | Mitigation |
|---|---|
| Resources tab prescribes datasets we didn't plan for | A0 Friday; registry first; dimensions without data show "unknown" |
| Global ingest too slow | H3 resolution picked by measured budget (ADR-0003 D3); fall back to continent-scale for the demo region |
| ARL thresholds look arbitrary to SME judges | Thresholds published per objective; calibration against golden sites (W15); say it's our choice, changeable |
| Lean proof slips | ADR-0003 D1 fallback label; statement still frozen before code |
| Over-claiming novelty of opportunity sites | Gate 4 failing is evidence of under-characterization only after a W12 literature check; otherwise "unknown" |
