# Statement ledger (ADR-0001 gates)

Statuses: `proposed → frozen → Lean-clean → executed-unreviewed → accepted`
(or `rejected / partial / blocked`). Update a row only with evidence (commit hash,
compiler output, audit output) quoted in the linked issue/PR.

| ID | Content | File | Status (2026-11-12) |
|---|---|---|---|
| S1 | Analogy semantics: loss orientation, `AnalogyVector` with per-dimension breakdown, `PermanentMismatch` non-scored by construction | `Analog/Semantics.lean` | **frozen + Lean-clean** (definitions + dominance/frontier lemmas; build and axiom audit in scaffold commit) |
| S5 | Body coherence: `TargetEnvelope` same type for Moon/Mars | `Analog/Semantics.lean` | **frozen + Lean-clean** (by construction; no theorem needed beyond the type) |
| S2 (generic) | Screening exactness for CVaR / worst-realisation objectives | `Analog/Screening.lean` (`cvar_screening_exact`, `wr_screening_exact`) | **Lean-clean**, ported from owner's `FastOpt` (statements/proofs unchanged, namespace only) |
| S2 (atlas) | Screening ⇒ eliminated Earth cell cannot reach the frontier under the declared weight family, over `Analog.Semantics` losses | — | **proposed** (open work order; instantiation not yet formalized) |
| S3 (generic) | Suboptimality certificate bound from dual residual | `Analog/Certificate.lean` (`subopt_le`) | **Lean-clean** (ported as S2-generic) |
| S3 (atlas) | Score certificates emitted by the Rust engine satisfy the `subopt_le` hypotheses | — | **proposed** (needs engine + certificate schema conformance) |
| S4 | Pareto soundness: dominated ⇒ not frontier | `Analog/Semantics.lean` (`not_frontier_of_dominated`) | **Lean-clean** |

Axiom audit snapshot (2026-11-12, `lake env lean Analog/Audit.lean`, RC=0): all
eight audited theorems depend only on `[propext, Classical.choice, Quot.sound]`.
Toolchain pin: `leanprover/lean4:v4.36.0-rc2`, Mathlib rev
`5f44e8099aaff86b8804252d5189966a5b3b8f78` (from the `fastopt` manifest; see
`lake-manifest.json`). Do not silently build on any other toolchain.

**Prior-corpus row (2026-11-13):** 21 owner's modules ported into
`Analog/Prior/*` (namespaces verbatim) build clean; 20 representative theorems
join the audit (28 total audited, all standard axioms, RC=0). These are
**Lean-clean as mathematics**; none is yet *instantiated* for analog semantics
— instantiations are new statements under S1–S5 (e.g. S2-atlas may cite
`Math222SimplexCertV2`/`F096`/`L13Mixing`; process dimensions may cite
`ACI`/`C05Window`/`Jumps`). Cantelli re-proved 2026-11-13 (issue #9):
`Analog.Prior.Cantelli` imported, `PerpTheory.cantelli` in the audit — the
applied Mathlib renames are listed in doc 06 §3. The Ville→ExperimentGate
chain remains **candidates** (preserved unimported, re-proof pending). Full
dispositions:
[`docs/research/06-lean-corpus-inventory.md`](/home/drew/cosmic-consultants/docs/research/06-lean-corpus-inventory.md).

File hashes at freeze time are recorded in git history (scaffold commit); a
frozen file that changes gets a new statement ID and the old row is marked
superseded, never edited to look unchanged.
