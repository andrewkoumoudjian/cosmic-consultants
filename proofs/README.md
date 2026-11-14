# proofs/ — formal mathematics and its application boundary

Selected comparison definitions and proofs exist here. Their presence does not
verify a runtime engine, measurement transformation, dataset or scientific claim.
[STATEMENTS.md](STATEMENTS.md) records exact scope and missing runtime links.
[ADR-0004](../docs/decisions/ADR-0004-evidence-backed-comparison.md) proposes a
narrower product/assurance policy; repository adoption remains pending team review.

Pinned: `leanprover/lean4:v4.36.0-rc2`; Mathlib
`5f44e8099aaff86b8804252d5189966a5b3b8f78` in `lake-manifest.json`.
From this directory, after required dependencies are available:

```sh
lake build
lake env lean Analog/Audit.lean
```

Capture each process exit status directly. `lake exe cache get` is an optional
network/cache setup action, not proof verification. A build may generate artifacts;
do not run it under a read-only task. CI checks build/audit separately. Historical
passes do not establish a fresh local pass on a new host.

| Module | Mathematical scope |
|---|---|
| `Analog/Semantics.lean` | Loss-oriented vectors, valid loss intervals, dominance/frontier and small lemmas. The types do not validate a physical measurement pipeline. |
| `Analog/Atlas.lean` | Frozen S2a/S2b/S2c proposition definitions, not their proofs. |
| `Analog/AtlasProofs.lean` | Nonnegative weighted monotonicity, finite frontier coverage, and no unique non-frontier weighted minimizer. No executable screening algorithm. |
| `Analog/Screening.lean` | Generic CVaR/worst-realisation results from prior optimization work; application hypotheses must be established. |
| `Analog/Certificate.lean` | Conditional optimization-objective gap bound `subopt_le`; not physical uncertainty or feature-score error. |
| `Analog/Prior/*` | Imported prior mathematics or explicitly unimported candidates; relevance requires an actual application statement. |
| `Analog/Audit.lean` | Selected theorem axiom dependencies; explicitly invoked, not part of the library target. |

No `.lean` file, pin or manifest is changed by #43. The conceptual replacement
measurement/requirement/assessment contract has not yet been formalized. New
statements must receive new IDs and pass statement/proof review before any formal
claim; tested runtime outputs must be labeled according to their actual evidence.
