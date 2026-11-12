/-
PORTED 2026-11-12 from owner prior work: probability integral transform
Source: andrewkoumoudjian/perps-strategy @ 0f34759, legacy/rounds1-2/lean/PerpTheory/PIT.lean (toolchain v4.15.0).
Port changes ONLY: module path/import remap to Analog.Prior.* (+ Mathlib API renames if listed in docs/research/06). Namespaces, statements, proofs otherwise verbatim. Original file is frozen upstream; do not edit semantics here — supersede via new module + STATEMENTS.md.
-/
import Mathlib
import Analog.Prior.TailBounds

/-!
# T10 — Probability integral transform (PIT): definition + uniformity

The Python side gates every fitted law through PIT calibration
(`SIGMA_SPEC.md` §5–§6: pooled KS killed the first sleeve; v2 moves to
per-coin thinned PIT). Lean's job here is minimal and honest: record
the *definition* and prove the one theorem that makes PIT a
calibration tool at all — that under a continuous strictly increasing
CDF, the transform is exactly uniform.

* `pit F X ω = F (X ω)` — the sample pushed through the candidate CDF.
* `pit_uniform` — if `F` is strictly increasing onto `(0, 1)` and `X`
  has CDF `F`, then `P(F(X) ≤ u) = u` for every `u ∈ (0, 1)`.

Atoms: with atoms the plain PIT is not uniform (mass piles at jumps);
the general fix is the *randomized* PIT, deliberately out of scope
here. Python remains the arbiter of fit. Verified ≠ profitable.
-/

namespace PerpTheory

open MeasureTheory ProbabilityTheory

open scoped ENNReal

variable {Ω : Type*} [MeasurableSpace Ω] {μ : Measure Ω}

/-- Probability integral transform: the sample pushed through the
candidate CDF `F`. `pit F X ω = F (X ω)`. -/
noncomputable def pit (F : ℝ → ℝ) (X : Ω → ℝ) : Ω → ℝ := fun ω => F (X ω)

/-- `pit` is measurable when `F` is monotone (Borel) and `X` is
measurable. -/
theorem measurable_pit {F : ℝ → ℝ} (hF : Monotone F) {X : Ω → ℝ} (hX : Measurable X) :
    Measurable (pit F X) := hF.measurable.comp hX

omit [MeasurableSpace Ω] in
/-- PIT of a `TailLaw` CDF lands in `[0, 1]`. -/
theorem pit_mem_Icc {L : TailLaw} {X : Ω → ℝ} (ω : Ω) :
    pit L.cdf X ω ∈ Set.Icc (0:ℝ) 1 :=
  ⟨L.ge_zero _, L.le_one _⟩

/-- **PIT uniformity** (continuous strictly increasing case): if `F`
is strictly increasing and onto `(0, 1)`, and `X` has CDF `F` in the
sense `P(X ≤ x) = F x` for all `x`, then the transform `F ∘ X` is
uniform on `(0, 1)`: `P(F(X) ≤ u) = u` for every `u ∈ (0, 1)`. -/
theorem pit_uniform [IsProbabilityMeasure μ] {F : ℝ → ℝ} (hmono : StrictMono F)
    (hsurj : ∀ u ∈ Set.Ioo (0:ℝ) 1, ∃ x, F x = u)
    {X : Ω → ℝ} (hcdf : ∀ x, μ {ω | X ω ≤ x} = ENNReal.ofReal (F x))
    {u : ℝ} (hu : u ∈ Set.Ioo (0:ℝ) 1) :
    μ {ω | pit F X ω ≤ u} = ENNReal.ofReal u := by
  obtain ⟨x₀, hx₀⟩ := hsurj u hu
  have hset : {ω | pit F X ω ≤ u} = {ω | X ω ≤ x₀} := by
    ext ω
    simp only [Set.mem_setOf_eq, pit]
    constructor
    · intro h
      exact hmono.le_iff_le.mp (by rw [hx₀]; exact h)
    · intro h
      have h2 := hmono.le_iff_le.mpr h
      rwa [hx₀] at h2
  rw [hset, hcdf x₀, hx₀]

end PerpTheory
