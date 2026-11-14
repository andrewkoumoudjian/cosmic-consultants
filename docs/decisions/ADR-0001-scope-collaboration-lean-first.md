# ADR-0001 — Scope, collaboration system, Lean-first methodology

> Historical accepted decision; substantive body preserved. Proposed
> [ADR-0004](ADR-0004-evidence-backed-comparison.md) names the gates and
> certificate promises it would supersede. It has not yet been adopted.

Date: 2026-11-12. Status: **accepted by repo owner** (answers to proposal
[`04`](/home/drew/cosmic-consultants/docs/proposals/04-monorepo-multiagent-lean-proposal.md) §7).
Immutable once accepted; supersede by a new ADR, never edit in place.

## Decisions

1. **Both targets, one methodology.** Lunar permanent-base sites and Mars
   landing/exploration sites are both in scope, handled by the *same* formal
   methodology instantiated with body-specific target envelopes. A dimension that
   cannot be instantiated for a body is recorded as an explicit non-analogy for that
   body, not silently dropped. (Supersedes the Moon-first recommendation.)
2. **Collaboration: whichever is better for cross-agent work → GitHub Issues as the
   system of record**, per proposal §5: one issue = one work order = one branch =
   one PR; package file-ownership; handoff = pushed branch + evidence comment
   readable by any harness (T3 Code, OpenCode, Mistral Vibe, Muse…). Delta CLI
   may be used as an optional session-sync convenience; it is never load-bearing,
   because it is Beta, Claude-Code-first, and its store sits outside the repo.
   Harness, provider and model are tracked as three separate fields in every
   dispatch record; a similarly-named model on another route is not a substitute.
3. **Methodology and its mathematics are defined and solved in Lean.** Lean is the
   specification and proof authority: every concept the atlas computes with —
   dimension, target envelope, analogy vector, weight family, Pareto frontier,
   screening rule, certificate — is first *defined* as Lean, its correctness
   *stated* as Lean theorems, and only then implemented in executing languages
   (Rust/Python/TS), which must conform to the frozen statements. Direct reuse
   starting point: `FastOpt.Screening` / `FastOpt.Certificate` from
   `QUARCC-Umbrella/quant-fund:fastopt/proofs` (proposal §2).

## Lean-first operating gates (binding on all agents)

Three separate gates, in order. No gate's output may be claimed as the next gate's:

| Gate | Content | Acceptance rule |
|---|---|---|
| **Statement** | Definitions, domain, quantifiers, assumptions, intended conclusion. Checked for counterexamples, degenerate cases (empty dimension set, zero-width envelope, missing observations, total mismatch), and assumptions that merely restate the conclusion. | Statement is **frozen and committed** (file + content hash recorded in the work order) before any proof attempt or any data statistics are run against it. |
| **Proof** | Proof of the exact frozen statement in a new module; frozen/proved files are never edited to fit later code. | Pinned toolchain (`lean-toolchain` at repo pin, matching the Mathlib pin); parent re-runs the compiler and axiom audit personally; **no `sorry`/`admit`/custom axioms/unsafe escapes** in accepted proofs; compiler return code is captured from Lean itself, never through a pipe that can mask failure. A `def X : Prop` elaborating is *not* a proof of `X` — definition and theorem obligation are separate artifacts. |
| **Experiment** | Dataset ingest, screening runs, atlas numbers. | Executes only against frozen statements with passing proofs; input snapshot hashes verified before statistics; missing records kept explicit; every published number traces to a snapshot (brief proposition P8). |

Statuses are tracked separately per statement and never conflated:
`proposed → frozen → Lean-clean → executed-unreviewed → accepted` (or
`rejected / partial / blocked`). Dispatch success is not proof success; Lean-clean
is not scientific validity; a partial dataset pool is not full coverage.

## Initial statement ledger (to be frozen as work orders, in this order)

| ID | Statement (informal, to be formalized) | Ports from |
|---|---|---|
| S1 | Analogy-vector semantics: per-dimension match is a value in a declared scale with an explicit breakdown flag; the brief's four permanent mismatches (gravity, vacuum/atmosphere, radiation — per body) are non-analogous by construction. | new |
| S2 | Screening exactness: a cell eliminated by the screening rule cannot enter the Pareto frontier under any weight in the declared family. | `cvar_screening_exact`, `wr_screening_exact` |
| S3 | Certificate bound: published per-dimension scores carry a computable suboptimality/error bound evaluated from the run's own duals/residuals. | `subopt_le` |
| S4 | Pareto soundness: no dominated cell is presented as frontier; dominance is checked against the frozen dimension order. | `relaxation_exact`, `lower_model_exact` |
| S5 | Body-instantiation coherence: Moon and Mars envelopes are instances of one envelope type; cross-body claims are only made through the shared dimensions. | new |

## Consequences for sequencing

- Phase order from proposal §6 stands, with S1–S5 freezing inserted as Phase 1.5 —
  before engine code and before any global statistics.
- Dataset work proceeds in parallel as *registry/provenance* only (docs 01 §4,
  05 §5); it asserts no analog conclusions until the experiment gate opens.
- First action remains **A0 (2026-11-13)**: re-fetch the challenge Resources tab and
  judging/submission guides, diff docs 01/02/05, then open the S1 work order.
