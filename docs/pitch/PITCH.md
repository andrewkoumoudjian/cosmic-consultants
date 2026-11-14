# Pitch plan

> **Product changed on 2026-11-14:** ARL is replaced by the mission planning
> workflow ([ADR-0005](../decisions/ADR-0005-mission-planning-workflow.md),
> [plan](../plan/MISSION-PLANNER.md)). The pitch lane (W13, #24) rewrites this file.

Working title: **Proving Grounds — Analog Readiness Levels for NASA's Moon-to-Mars objectives**
(name is a placeholder; owner picks). No NASA logos or mission insignia
anywhere (doc 07 §1.1). Planning document; the deck and video are built in
W13 (#24) during the window, from the build that actually exists.
Direction: ARL (ADR-0002), kept by the owner on 2026-11-14 (#46). Every
claim in the final pitch must match what the build actually does.

## The one-liner

> Everyone can show you where Earth *looks* like Mars. We show NASA where on
> Earth to **rehearse each Moon-to-Mars objective**, how ready that place is,
> and what it can never rehearse there.

## Story arc (2–3 min live, or the walkthrough video)

1. **Problem.** Analog field sites get picked by tradition — the same few
   deserts and Antarctic valleys. The challenge itself says these sites "are
   not entirely well characterized", and NASA's objective OP-1L asks for
   demonstrations on Earth to "shorten the timeframe for system testing and
   readiness".
2. **Insight.** Technology has a readiness scale (TRL). **Test sites don't.**
   Whether a site is "a good Mars analog" depends on *what you want to test
   there* — rover traverses, ice coring, or precision landing all need
   different conditions.
3. **Product.** Pick a NASA objective → global heatmap of Analog Readiness
   Levels 0–6 → click a site → its readiness ladder: which evidence it has,
   the dimension holding it back, and the "Earth cannot rehearse this" list.
4. **The twist (Surprise us).** The opportunity layer: sites the data rates as
   ready (ARL 3) that nobody has characterized in the field yet. "Here's where
   the next field campaign should go, and what it would prove."
5. **Why believe it.** Open NASA data with hashed snapshots behind every
   number; the ladder rules are machine-checked in Lean (it can't quietly
   average a bad dimension away); calibrated against known analogs (Haughton,
   Mistastin, Dry Valleys, Atacama, Death Valley) — including where we
   disagree with them.
6. **Who uses it.** Analog-campaign planners, rover/instrument teams choosing
   test sites, crew science-training planners (SE-1).

## 30-second demo video (storyboard — W13 replaces shots with real captures)

| Time | Shot | On-screen text / VO |
|---|---|---|
| 0–4 s | Earth globe, faint heatmap | "Where on Earth can we rehearse Mars?" |
| 4–11 s | Select **OP-5: surface mobility & EVA (Mars)** → heatmap blooms | "Pick a NASA objective. See every place it can be rehearsed." |
| 11–19 s | Click an opportunity site → dossier ladder ARL 3, limiting gate highlighted | "Readiness level, the evidence behind it, what's holding it back." |
| 19–24 s | "Earth cannot rehearse" panel: gravity, thin air | "And what Earth can never test." |
| 24–30 s | Switch to **SE-3: ice coring (Moon)** → map shifts to the poles; title card | "Proving Grounds: readiness levels for analog sites." |

## Mapping to judging criteria (provisional — 2025 criteria; replace after A0 reads the 2026 guide)

| Criterion | Our answer |
|---|---|
| Impact | Mission planners get a decision tool keyed to NASA's own objectives (OP-1L) |
| Creativity | First readiness ladder for analog sites (no prior scale found, doc 07 §3); opportunity layer |
| Validity | Hashed open data, Lean-checked ladder logic, calibration with misses reported |
| Relevance | Answers every brief requirement: identify (R1), characterize (R2), NASA data (R3), breakdowns (R4), exploration use (R5), map (R6) |
| Presentation | 30-s video shows the full loop; live demo on the deployed map |

## Judge Q&A (prepare answers with real numbers from the build)

- **"Isn't ARL just a score?"** It's an evidence level for one named objective,
  set by its weakest dimension, never averaged, always shown with the
  per-dimension breakdown. No site gets an overall score.
- **"Who chose the thresholds?"** We did, and published them per objective;
  they come from the Moon/Mars target envelopes with cited sources. Change one
  and the map changes.
- **"Why Lean?"** It proves the ladder can't be gamed: more evidence never
  lowers a level, and a strong dimension can't make up for a weak one. It
  doesn't certify the geology; the data provenance does that.
- **"Atacama is already known."** Exactly — it calibrates the ladder. The
  opportunity layer is about the places that aren't.
- **"What about gravity?"** Every objective lists what Earth can't rehearse.
  Objectives that are mostly gravity or radiation are shown but never rated.
- **"Next step?"** Feed field-campaign results back in as gate-4 evidence;
  extend to all 63 objectives; let PIs submit evidence.
