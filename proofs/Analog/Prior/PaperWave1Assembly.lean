/-
PORTED 2026-11-12 from owner prior work: primal witness xor Farkas refutation
Source: andrewkoumoudjian/perps-strategy @ 0f34759, lanes/chief/lean/PerpChief/PaperWave1Assembly.lean (toolchain v4.15.0).
Port changes ONLY: module path/import remap to Analog.Prior.* (+ Mathlib API renames if listed in docs/research/06). Namespaces, statements, proofs otherwise verbatim. Original file is frozen upstream; do not edit semantics here — supersede via new module + STATEMENTS.md.
-/
import Analog.Prior.Math222SimplexCertV2

/-!
# PaperWave1 Assembly 4: finite scenario-probability, primal-or-dual risk API

Composition layer over the frozen, parent-audited `PerpChief.Math222SimplexCertV2` only.
The scenario space is the closed probability simplex itself: an allocation is a point `w`
of that simplex, the threshold `b` is exact data, and a verdict is one of
* `witness w hw hrow` - a concrete feasible point,
* `farkas y hy`       - a dual certificate of infeasibility,
* `abstain`           - neither proof term available (unresolved).

The two proof-carrying cases are mutually exclusive by LP duality:
`certificate_infeasible` of the frozen module refutes `Feasible` from any
`Certifies A y b`, while a witness term constructs `Feasible` outright.
-/

namespace PerpChief.PaperWave1

open PerpChief.Math222SimplexCertV2

/-- The primal-or-dual verdict on one fixed system `(A, b)`. -/
inductive Verdict (A : Fin m → Fin d → ℝ) (b : ℝ) where
  | witness : (w : Fin d → ℝ) → IsSimplex w → (∀ i, (∑ j, A i j * w j) ≤ b) → Verdict A b
  | farkas : (y : Fin m → ℝ) → Certifies A y b → Verdict A b
  | abstain : Verdict A b

/-- A witness verdict yields `Feasible` definitionally. -/
theorem witness_gives_feasible {A : Fin m → Fin d → ℝ} {b : ℝ}
    (w : Fin d → ℝ) (hw : IsSimplex w)
    (hrow : ∀ i, (∑ j, A i j * w j) ≤ b) : Feasible A b := by
  exact ⟨w, hw, hrow⟩

/-- A Farkas certificate refutes feasibility. -/
theorem farkas_refutes_feasible {A : Fin m → Fin d → ℝ} {b : ℝ}
    {y : Fin m → ℝ} (hy : Certifies A y b) : ¬ Feasible A b := by
  exact certificate_infeasible A b y hy

/-- The two proof-carrying verdicts are mutually exclusive on one system. -/
theorem verdicts_disjoint {A : Fin m → Fin d → ℝ} {b : ℝ}
    (w : Fin d → ℝ) (hw : IsSimplex w)
    (hrow : ∀ i, (∑ j, A i j * w j) ≤ b)
    {y : Fin m → ℝ} (hy : Certifies A y b) : False := by
  exact farkas_refutes_feasible hy ⟨w, hw, hrow⟩

end PerpChief.PaperWave1
