# ADR-0003 — 48-hour delivery scope: what ships, what is stretch

Date: 2026-11-12. Status: **accepted by merge #26 (`5da36ce`)**, under its original
merge-acceptance clause. Status annotation corrected in #43; substantive decision
below preserved. [ADR-0004](ADR-0004-evidence-backed-comparison.md), which would have replaced
this scope, was **deferred by the owner on 2026-11-14 (#46)**; this scope stands.
This historical decision partially **narrows** ADR-0001 for the hackathon window
only (2026-11-14 09:00 → 2026-11-15 23:59 local); ADR-0001 itself is unchanged.

## Context

ADR-0001 + proposal 04 describe five lanes (Lean, Python ingest, Rust
engine native+WASM, TS Worker API, TS map) with three gates per statement.
That is a sound research design, but the build window is ~39 working hours,
judges see a **30-second demo video first** (doc 07 §1.1), and organizers say
judges evaluate "progress toward a solution". As of `eaabc9b` no ingest,
engine, API or map code exists (correctly — build starts 2026-11-14).

## Decision

1. **Lean in the window: only S6 (ARL) is new.** S6 statement freezes in the
   first block (W8), proofs follow (W9). S1/S2-atlas/S4/S5 are already
   Lean-clean. **S3-atlas (engine certificate conformance) moves to stretch**:
   run certificates are emitted with `scoreBound: null` (already allowed by
   `certificate.schema.json`) and say so. No further `Prior/*` porting (Ville
   chain stays deferred). The experiment gate opens when S6 is Lean-clean, or
   when its statement is frozen if W9 slips — in that case published levels are
   labelled `executed-unreviewed` against a frozen-but-unproved statement.
2. **Static-first architecture.** Ingest (Python) and engine v0 produce
   versioned static artifacts (per-objective readiness grids + site dossiers as
   JSON/GeoJSON, hashed); the map is a static TS app on Cloudflare Pages. The
   Worker API is built only if a runtime NASA API-key call is actually needed
   (GIBS and Trek WMTS need no key). **Engine v0 may be Python**; the Rust
   crate + WASM in-browser reweighting are stretch.
3. **Grid.** H3 hexagons; global coarse resolution chosen in W6 by a measured
   run-time budget (target: a full global pass for 3 objectives in < 20 min on
   one laptop), finer resolution for opportunity regions only.
4. **Priority order (cut from the bottom when late).**
   - **P0 (the demo):** 3 objectives — `OP-5LM` surface mobility/EVA (Mars),
     `SE-3LM` frozen-volatile coring (Moon), `LI-5L` precision landing under
     low sun (Moon) — global ARL 0–3 heatmaps, opportunity layer, dossiers for
     the 5 golden sites + 2–3 opportunity sites with gates 4–6 hand-evidenced
     from literature (each claim cited), "Earth cannot rehearse" lists.
   - **P1:** remaining doc-07 §2.1 objectives; Moon/Mars target side panel
     (Trek WMTS) next to the Earth map; ARL-change explorer ("what one field
     campaign would unlock").
   - **P2 (stretch):** Rust/WASM engine, S3-atlas certificates, weight-family
     sensitivity report, Ville chain.
5. **Freeze times (local):** contracts + S6 statement Sat 13:00; feature freeze
   Sun 16:00; video locked Sun 19:00; submission complete Sun 22:00 (2-hour
   buffer before the 23:59 deadline, which is itself unverified until A0).

## Consequences

- Lanes `services/engine` (Rust) and `services/api` may legitimately stay empty
  at submission; the README says so and why.
- Every published level still traces to a snapshot (rule 3) — static-first
  makes that easier, not harder.
- If the owner rejects this ADR, ADR-0001 sequencing (W5→W7 with S3-atlas
  before publication) governs, and P0 will likely not finish in the window.
