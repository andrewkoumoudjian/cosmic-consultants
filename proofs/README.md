# proofs/ — Lean specification and proof authority (ADR-0001)

Build: `lake exe cache get && lake build` · Audit: `lake env lean Analog/Audit.lean`
(standard axioms only). Pinned: `leanprover/lean4:v4.36.0-rc2`, Mathlib
`5f44e8099aaff86b8804252d5189966a5b3b8f78` via `lake-manifest.json`.

| Module | Content |
|---|---|
| `Analog/Semantics.lean` | S1/S5: bodies, envelopes, analogy vector, permanent mismatches, dominance/frontier + lemmas |
| `Analog/Screening.lean` | Generic exact screening (ported from owner's `FastOpt`, provenance header in file) |
| `Analog/Certificate.lean` | Generic suboptimality certificate `subopt_le` (ported likewise) |
| `Analog/Audit.lean` | `#print axioms` list; not part of the library target |
| `STATEMENTS.md` | Ledger: frozen / Lean-clean / proposed, with what is *not* yet claimed |
