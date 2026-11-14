# ADR-0002 — Analog Readiness Levels (ARL): per-objective, evidence-staged readiness

Date: 2026-11-12. Status: **accepted by merge #26 (`5da36ce`)**, as its original
merge-acceptance clause specified (issue #14). Status annotation corrected in
work order #43; substantive decision below preserved. [ADR-0004](ADR-0004-evidence-backed-comparison.md), which would have replaced
ARL, was **deferred by the owner on 2026-11-14 (#46)**: **ARL is the current plan.** Builds on
[ADR-0001](ADR-0001-scope-collaboration-lean-first.md); does not edit it.
Sources: [doc 07](../research/07-spaceapps-rules-and-m2m-objectives.md)
(M2M objectives, prior art, organizer rulings), [doc 02](../research/02-challenge-brief.md).

## Context

The owner's pitch direction (2026-11-12): most teams will ship an Earth↔Moon/Mars
look-alike map. Ours should be useful for **actually planning analog missions**:
for a named mission objective, how ready is each Earth site to host a test of
it, how sure are we, and what can't be tested there at all — shown as a heatmap
and demoed so the practical use is obvious.

The brief rewards exactly this: R5/P7 ("how studying or using your Earth analog
could help prepare"), R4/P3 (where the analogy breaks down), F4 ("terrestrial
analog sites are not entirely well characterized"), and the anti-goal ("not
simply to rediscover well-known analog sites"). NASA's own objective **OP-1L**
calls for technology demonstrations "on the surface of Earth" to "reduce risk,
and shorten the timeframe for system testing and readiness". A readiness ladder
for analog sites, keyed to NASA's numbered Moon-to-Mars objectives, plugs
straight into how NASA already plans (TRLs, objective decomposition).

No published "analog readiness level" scale was found (doc 07 §3). Nearest:
Stern et al. 2025 (question → parameters → site match), Lee et al. 2010
(fidelity "for the usage sought"), NTRS 20000105009 (use lower-fidelity sites
early in development, higher-fidelity later).

## Decision

### D1. The unit of rating is (Earth cell or site, mission objective, target body)

A **mission objective** is a row derived from NASA's Moon to Mars Objectives
(Sept 2022): `objectiveId` (e.g. `OP-5LM`), target body, the Earth-testable
component in one sentence, its **required dimensions** (subset of the frozen
dimension enum in `contracts/`), the tolerance per required dimension (taken
from the body's target envelope), and the **not-testable-on-Earth list** — which
of `gravity / pressureRegime / radiation` the objective's full version depends
on. Objectives whose primary content is not Earth-testable (e.g. partial-gravity
physiology) are listed and shown as *not rateable*, never given a level.

### D2. The ladder (cumulative gates, like TRL)

`ARL(c, o)` is the highest level `k` such that **every gate 1…k passes**. Per-
dimension gates must pass for **every** required dimension of `o` — the level is
set by the weakest required dimension (no compensation between dimensions).

| ARL | Name | Gate (must hold for all required dimensions unless marked *site*) | Evidence source |
|---|---|---|---|
| 0 | Unknown | — (some required dimension has **no data** at this cell; missing stays explicit and is rendered as "unknown", never as "bad") | — |
| 1 | Characterizable | every required dimension observed from open data | global rasters |
| 2 | Envelope match | every required dimension's loss within the objective's tolerance | global rasters |
| 3 | Corroborated | ≥2 independent datasets per required dimension, ≥1 non-imagery (brief P2), agreeing within tolerance | global rasters |
| 4 | Field-characterized | published in-situ characterization of the site covering each required dimension | literature corpus (W4/#5) |
| 5 | Operable | *site:* access, protected-area/legal status, safety and season permit a field campaign | WDPA, accessibility rasters, literature |
| 6 | Campaign-proven | *site:* a documented analog campaign exercised this objective class here | campaign index (literature) |

Global heatmaps cover ARL 0–3 (computable everywhere from rasters). ARL 4–6
need site evidence, so they appear as points/dossiers, not as a global surface.
Every gate's pass/fail is published individually, so a dossier can say e.g.
"ARL 3 — passes Operable, fails Field-characterized".

### D3. The product view this enables

- **Readiness heatmap** per selected objective (+ body), ARL 0–3 colored as an
  ordinal scale, unknown hatched.
- **Opportunity layer**: cells at ARL 3 that fail gate 4 and lie outside the
  brief's saturated regions (F3: Antarctica, Atacama, Iceland, Hawaii) — "the
  data says this site is ready; one field campaign promotes it". This is our
  answer to the brief's "not simply to rediscover" anti-goal and to F4.
- **Shortlist within a level**: inside each ARL tier, cells are compared by
  their per-dimension loss vector only; the certified Pareto frontier (S2-atlas,
  already Lean-clean) is the shortlist. No number ranks two ARL-3 sites.
- **Dossier**: the ladder with each gate's evidence and dataset snapshots, the
  limiting dimension and limiting gate, the per-dimension analogy vector, and
  the objective's "Earth cannot rehearse this part" list.

### D4. Relation to AGENTS.md rule 4 ("no single scalar similarity score")

ARL is **not a similarity score**: it is an ordinal evidence level for one
named objective, computed by gates with no weights and no averaging, and it is
never shown without its per-dimension vector, limiting dimension, limiting gate,
and not-testable list. Rule 4 is amended in the same PR to say exactly this.
Any aggregate across objectives ("overall readiness of a site") stays
forbidden.

### D5. Lean (ADR-0001 statement gate applies)

A new statement **S6 (ARL semantics)** is frozen before any code computes
levels (backlog W8 → W9). Informal content to formalize:

- **S6a weakest link:** for per-dimension gates, `ARL = min` over required
  dimensions of the per-dimension level; equivalently, the cumulative-gate
  definition in D2.
- **S6b monotone in evidence:** if evidence `e'` passes every gate `e` passes,
  `ARL e ≤ ARL e'` — adding evidence never lowers a level.
- **S6c no compensation:** changing the evidence of one dimension cannot raise
  ARL above the level of any other required dimension.
- **S6d unknown ≠ failure:** missing data on a required dimension gives ARL 0,
  distinct from observed-but-out-of-tolerance (ARL 1).
- **S6e cumulative:** `ARL ≥ k` implies gate `j` passes for every `j ≤ k`.
- **S6f mismatch never rated:** the level is a function of gate outcomes on
  scored dimensions only; `PermanentMismatch` enters only the published
  not-testable list (extends S1).

## Consequences

- New contract (W10, contracts lane first): `objective.schema.json` and a
  `readiness` block per (site, objective) in `site.schema.json`.
- Golden sites become calibration tests with expected levels (W15): e.g.
  Haughton must reach ≥ ARL 4 for the field-geology objective; a failure is
  reported, not tuned away.
- Pitch is reframed around "readiness for NASA's objectives" (`docs/pitch/PITCH.md`).
- **Honest limits we will state:** gate thresholds (tolerances, "two independent
  datasets") are our choices, published and changeable, not NASA's; the
  objective → dimension mapping is our interpretation of NASA's text; Lean
  certifies the ladder logic, never the geophysics.

## Rejected alternatives

- **Single "Mars-likeness" score per site** — prior art (Peña-Asensio et al.
  2024), contradicts F6/R4, and AGENTS.md rule 4.
- **Continuous confidence percentage per objective** — implies a probability
  model we cannot calibrate in 48 hours; ordinal gates are auditable.
- **Making Pareto-frontier membership a gate** — would hide good-but-dominated
  sites; the frontier is a shortlist inside a level instead.
