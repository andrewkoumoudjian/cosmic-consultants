/-
PORTED 2026-11-12 from owner prior work: Gaussian propeller selection-gain cap
Source: andrewkoumoudjian/perps-strategy @ 0f34759, lanes/chief/frozen/PaperWave2/F096.lean (toolchain v4.15.0).
Port changes ONLY: module path/import remap to Analog.Prior.* (+ Mathlib API renames if listed in docs/research/06). Namespaces, statements, proofs otherwise verbatim. Original file is frozen upstream; do not edit semantics here — supersede via new module + STATEMENTS.md.
-/
/-
PaperWave2 family 096 — Gaussian propeller bound, applied selection-gain cap.

Upstream result (OpenAI, *The Gaussian propeller bound in every dimension*,
24 September 2026): for every finite measurable partition `A` of `ℝ^d` and every
`k`, `∑ᵢ ‖∫_{Aᵢ} x dγ_d(x)‖² ≤ 9/(8π)`, independent of `d` and `k`; the bound is
attained by three planar `2π/3` sectors times an orthogonal factor.

This module does **not** reprove the propeller bound. It freezes the applied
composition that turns it into a cap on the expected payoff of selecting the best
of `k` Gaussian linear signals:

  expected selected score ≤ 3/(2√(2π)) · √(total centred signal variance).

The two inputs are explicit:
* the propeller bound for the score-vector law (`PropellerBound`, an external
  theorem, not proved here);
* the argmax cell identity (`selectedScore_eq_inner`), which is proved.

The bound is dimension-free and number-of-cells-free: adding regimes or risk
factors cannot raise the cap. It is a *ceiling on selection gain*, not a
profitability statement.

Toolchain: Lean 4.15.0 / Mathlib v4.15.0.
-/
import Mathlib

open Finset BigOperators
open scoped Real RealInnerProductSpace InnerProductSpace

namespace PerpChief.PaperWave2.F096

noncomputable section

variable {Ω : Type*} [Fintype Ω] {d k : ℕ}

/-- `d`-dimensional Euclidean score space. -/
abbrev Space (d : ℕ) := EuclideanSpace ℝ (Fin d)

/-- A finite weighted scenario space carrying a `d`-dimensional score vector. -/
structure Scenario (Ω : Type*) [Fintype Ω] (d : ℕ) where
  weight : Ω → ℝ
  weight_nonneg : ∀ ω, 0 ≤ weight ω
  weight_sum : ∑ ω, weight ω = 1
  vec : Ω → Space d

/-- A labelled finite partition of the scenario space. -/
structure CellPartition (Ω : Type*) [Fintype Ω] (k : ℕ) where
  cell : Fin k → Finset Ω
  disjoint : ∀ i j : Fin k, i ≠ j → Disjoint (cell i) (cell j)
  cover : ∀ ω : Ω, ∃ i : Fin k, ω ∈ cell i

variable (S : Scenario Ω d) (C : CellPartition Ω k)

/-- Gaussian first moment (centroid) of cell `i`: the paper's `z(Aᵢ)`, unnormalised
by the cell probability. -/
def centroid (i : Fin k) : Space d :=
  ∑ ω ∈ C.cell i, S.weight ω • S.vec ω

/-- Sum of squared centroid lengths: the paper's propeller functional `𝓕(A)`. -/
def propellerValue : ℝ :=
  ∑ i : Fin k, ‖centroid S C i‖ ^ 2

/-- The Gaussian propeller bound specialised to this score-vector law. This is the
external theorem of family 096, stated as an explicit hypothesis. -/
def PropellerBound : Prop :=
  propellerValue S C ≤ 9 / (8 * Real.pi)

/-- Expected score of the selected (argmax) cell. When the cells are the argmax
cells of the scores `u`, this is the expected maximum score. -/
def selectedScore (u : Fin k → Space d) : ℝ :=
  ∑ i : Fin k, ∑ ω ∈ C.cell i, S.weight ω * ⟪u i, S.vec ω⟫_ℝ

/-- Cell `i` is a maximising cell for the scores `u`. -/
def IsMaxCell (u : Fin k → Space d) : Prop :=
  ∀ (i : Fin k) (ω : Ω), ω ∈ C.cell i →
    ∀ j : Fin k, ⟪u i, S.vec ω⟫_ℝ ≤ ⟪u j, S.vec ω⟫_ℝ

/-- **Argmax identity.** The expected selected score is the inner product of the
signal vectors with the cell centroids. No Gaussianity is used; only linearity of
the integral and the partition. -/
theorem selectedScore_eq_inner (u : Fin k → Space d) :
    selectedScore S C u = ∑ i : Fin k, ⟪u i, centroid S C i⟫_ℝ := by
  unfold selectedScore centroid
  refine Finset.sum_congr rfl (fun i _ => ?_)
  rw [inner_sum]
  refine Finset.sum_congr rfl (fun ω _ => ?_)
  rw [inner_smul_right]

/-- A finite partition sums like the whole space. -/
theorem sum_cells_eq_sum_univ (f : Ω → ℝ) :
    (∑ i : Fin k, ∑ ω ∈ C.cell i, f ω) = ∑ ω, f ω := by
  classical
  have hUnion : (Finset.univ : Finset (Fin k)).biUnion C.cell = Finset.univ := by
    ext ω
    simp only [Finset.mem_biUnion, Finset.mem_univ]
    exact ⟨fun _ => trivial, fun _ => by simpa using C.cover ω⟩
  rw [← hUnion, Finset.sum_biUnion]
  exact fun i _ j _ hij => C.disjoint i j hij

/-- **Cauchy–Schwarz core.** The selected score is bounded by the product of the
signal norm and the propeller functional, with no Gaussian input. -/
theorem selection_cauchy_schwarz (u : Fin k → Space d) :
    (∑ i : Fin k, ⟪u i, centroid S C i⟫_ℝ) ≤
      Real.sqrt (∑ i : Fin k, ‖u i‖ ^ 2) *
        Real.sqrt (∑ i : Fin k, ‖centroid S C i‖ ^ 2) := by
  have hinner : (∑ i : Fin k, ⟪u i, centroid S C i⟫_ℝ) ≤
      ∑ i : Fin k, ‖u i‖ * ‖centroid S C i‖ := by
    refine Finset.sum_le_sum (fun i _ => ?_)
    exact real_inner_le_norm (u i) (centroid S C i)
  have hsq : (∑ i : Fin k, ‖u i‖ * ‖centroid S C i‖) ^ 2 ≤
      (∑ i : Fin k, ‖u i‖ ^ 2) * (∑ i : Fin k, ‖centroid S C i‖ ^ 2) :=
    Finset.sum_mul_sq_le_sq_mul_sq Finset.univ
      (fun i => ‖u i‖) (fun i => ‖centroid S C i‖)
  have hprod : ∑ i : Fin k, ‖u i‖ * ‖centroid S C i‖ ≤
      Real.sqrt ((∑ i : Fin k, ‖u i‖ ^ 2) *
        (∑ i : Fin k, ‖centroid S C i‖ ^ 2)) :=
    Real.le_sqrt_of_sq_le hsq
  have hnn : 0 ≤ ∑ i : Fin k, ‖u i‖ ^ 2 :=
    Finset.sum_nonneg (fun i _ => sq_nonneg _)
  rw [Real.sqrt_mul hnn] at hprod
  exact hinner.trans hprod

/-- The propeller constant, in the paper's normalisation. -/
theorem propeller_constant_eq :
    Real.sqrt (9 / (8 * Real.pi)) = 3 / (2 * Real.sqrt (2 * Real.pi)) := by
  have hπ : (0 : ℝ) < Real.pi := Real.pi_pos
  have hsq : (3 / (2 * Real.sqrt (2 * Real.pi))) ^ 2 = 9 / (8 * Real.pi) := by
    have h2 : (Real.sqrt (2 * Real.pi)) ^ 2 = 2 * Real.pi :=
      Real.sq_sqrt (by positivity)
    rw [div_pow, mul_pow, h2]
    ring_nf
  rw [← hsq]
  exact Real.sqrt_sq (by positivity)

theorem propeller_constant_pos : 0 < 9 / (8 * Real.pi) := by positivity

/-- `9/(8π) < 1`: the propeller ceiling is strictly sharper than the trivial
Bessel ceiling `1` on one unit-variance coordinate. -/
theorem propeller_constant_lt_one : 9 / (8 * Real.pi) < 1 := by
  rw [div_lt_one (by positivity)]
  nlinarith [Real.pi_gt_three]

/-- **Applied selection-gain cap.** Given the propeller bound for the score law,
the expected score of the best of `k` Gaussian linear signals is at most
`3/(2√(2π))` times the square root of the total centred signal variance.
The constant is `≈ 0.598`, independent of dimension `d` and of the number of
cells `k`. -/
theorem selection_gain_bound (u : Fin k → Space d) (hprop : PropellerBound S C) :
    selectedScore S C u ≤
      (3 / (2 * Real.sqrt (2 * Real.pi))) *
        Real.sqrt (∑ i : Fin k, ‖u i‖ ^ 2) := by
  rw [selectedScore_eq_inner]
  have hcs := selection_cauchy_schwarz S C u
  have hz : ∑ i : Fin k, ‖centroid S C i‖ ^ 2 ≤ 9 / (8 * Real.pi) := hprop
  have hsqrt := Real.sqrt_le_sqrt hz
  have hnn : 0 ≤ Real.sqrt (∑ i : Fin k, ‖u i‖ ^ 2) := Real.sqrt_nonneg _
  have hmul : Real.sqrt (∑ i : Fin k, ‖u i‖ ^ 2) *
        Real.sqrt (∑ i : Fin k, ‖centroid S C i‖ ^ 2) ≤
      Real.sqrt (∑ i : Fin k, ‖u i‖ ^ 2) * Real.sqrt (9 / (8 * Real.pi)) :=
    mul_le_mul_of_nonneg_left hsqrt hnn
  calc
    (∑ i : Fin k, ⟪u i, centroid S C i⟫_ℝ)
        ≤ Real.sqrt (∑ i : Fin k, ‖u i‖ ^ 2) *
            Real.sqrt (∑ i : Fin k, ‖centroid S C i‖ ^ 2) := hcs
    _ ≤ Real.sqrt (∑ i : Fin k, ‖u i‖ ^ 2) *
          Real.sqrt (9 / (8 * Real.pi)) := hmul
    _ = (3 / (2 * Real.sqrt (2 * Real.pi))) *
          Real.sqrt (∑ i : Fin k, ‖u i‖ ^ 2) := by
        rw [propeller_constant_eq]
        ring

/-- Total centred signal variance of the `k` candidate bets. -/
def signalVariance (u : Fin k → Space d) : ℝ :=
  ∑ i : Fin k, ‖u i‖ ^ 2

/-- The same cap with the propeller constant kept as `√(9/(8π))`. -/
theorem selection_gain_bound_sqrt (u : Fin k → Space d) (hprop : PropellerBound S C) :
    selectedScore S C u ≤
      Real.sqrt (9 / (8 * Real.pi)) * Real.sqrt (signalVariance u) := by
  have h := selection_gain_bound S C u hprop
  rw [← propeller_constant_eq] at h
  simpa [signalVariance, mul_comm] using h

/-- **No-free-regime corollary.** For a fixed total variance budget `V`, the
expected selected score never exceeds `√(9/(8π)) · √V`, however many regimes or
risk factors are added. The selected cell's own mass is not part of the bound. -/
theorem best_of_k_cap (u : Fin k → Space d) (hprop : PropellerBound S C)
    {V : ℝ} (hV : signalVariance u = V) :
    selectedScore S C u ≤ Real.sqrt (9 / (8 * Real.pi)) * Real.sqrt V := by
  simpa [hV] using selection_gain_bound_sqrt S C u hprop

/-- Applied form with the argmax condition carried explicitly: when the cells are
the argmax cells of the scores, the cell sum is the expected maximum score. -/
theorem best_of_k_cap_of_max (u : Fin k → Space d) (_hmax : IsMaxCell S C u)
    (hprop : PropellerBound S C) {V : ℝ} (hV : signalVariance u = V) :
    selectedScore S C u ≤ Real.sqrt (9 / (8 * Real.pi)) * Real.sqrt V :=
  best_of_k_cap S C u hprop hV

end

end PerpChief.PaperWave2.F096
