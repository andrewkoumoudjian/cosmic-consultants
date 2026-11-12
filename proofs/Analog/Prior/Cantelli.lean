/- NOT IMPORTED by Analog.lean (2026-11-12): mechanical port fails on current Mathlib APIs; registered re-proof candidate in docs/research/06-lean-corpus-inventory.md. Preserved verbatim for the re-prover. -/
/-
PORTED 2026-11-12 from owner prior work: one-sided tail bound
Source: andrewkoumoudjian/perps-strategy @ 0f34759, legacy/rounds1-2/lean/PerpTheory/Cantelli.lean (toolchain v4.15.0).
Port changes ONLY: module path/import remap to Analog.Prior.* (+ Mathlib API renames if listed in docs/research/06). Namespaces, statements, proofs otherwise verbatim. Original file is frozen upstream; do not edit semantics here — supersede via new module + STATEMENTS.md.
-/
import Mathlib
import Analog.Prior.TailBounds

/-!
# T9 — Cantelli's inequality, measure-theoretic (one-sided Chebyshev)

`TailBounds.lean` proves two-sided Chebyshev by counting (finite
samples) and records the one-sided Cantelli bound *value*
`cantelliBound k = 1 / (1 + k^2)` without proof. This file proves the
measure-theoretic statement behind that number: for a real random
variable `X` with finite variance `v` on a probability space and any
`k > 0`,

  `P(X - E[X] ≥ k) ≤ v / (v + k^2)`,

and, standardized with `v = σ^2`, exactly `cantelliBound k`. At
`k = 3`: 10% (vs Chebyshev 11.1%, Gaussian 0.27%).

Proof (classical): for any `t ≥ 0` the event `{X - m ≥ k}` (with
`m = E[X]`) is contained in `{(X - m + t)^2 ≥ (k + t)^2}`; Markov
bounds that by `E[(X - m + t)^2] / (k + t)^2 = (v + t^2)/(k + t)^2`;
`t := v / k` minimizes the bound to `v / (v + k^2)`.

Verified ≠ profitable: this is distribution-free arithmetic under a
finite second moment. It says nothing about perp return laws, costs,
funding, or any edge. See `SIGMA_SPEC.md` §2/§7.
-/

namespace PerpTheory

open MeasureTheory ProbabilityTheory

open scoped ENNReal NNReal

variable {Ω : Type*} [MeasurableSpace Ω] {μ : Measure Ω}

/-- Expectation of the shifted squared deviation:
`E[(X - E[X] + t)^2] = Var[X] + t^2`. -/
theorem integral_shifted_sq [IsProbabilityMeasure μ] {X : Ω → ℝ} (hX : Memℒp X 2 μ)
    (t : ℝ) : ∫ ω, (X ω - μ[X] + t) ^ 2 ∂μ = variance X μ + t ^ 2 := by
  have hC : Memℒp (X - fun _ : Ω => μ[X]) 2 μ := hX.sub (memℒp_const _)
  have iC : Integrable (fun ω => (X ω - μ[X]) ^ 2) μ := hC.integrable_sq
  have iL : Integrable (fun ω => (2 * t) * (X ω - μ[X])) μ :=
    (hC.integrable one_le_two).const_mul _
  have iK : Integrable (fun _ : Ω => t ^ 2) μ := integrable_const _
  have hint0 : ∫ ω, X ω - μ[X] ∂μ = 0 := by
    have h1 : ∫ ω, (X - fun _ : Ω => μ[X]) ω ∂μ
        = ∫ ω, X ω ∂μ - ∫ ω, (μ[X] : ℝ) ∂μ :=
      integral_sub' (hX.integrable one_le_two) (integrable_const _)
    have h2 : ∫ ω, (μ[X] : ℝ) ∂μ = μ[X] := by rw [integral_const]; simp
    have h3 : ∫ ω, X ω ∂μ = μ[X] := rfl
    calc ∫ ω, X ω - μ[X] ∂μ
        = ∫ ω, (X - fun _ : Ω => μ[X]) ω ∂μ := rfl
      _ = ∫ ω, X ω ∂μ - ∫ ω, (μ[X] : ℝ) ∂μ := h1
      _ = μ[X] - ∫ ω, (μ[X] : ℝ) ∂μ := by rw [h3]
      _ = μ[X] - μ[X] := by rw [h2]
      _ = 0 := by ring
  have hI1 : ∫ ω, (X ω - μ[X]) ^ 2 ∂μ = variance X μ := hX.variance_eq.symm
  have hI2 : ∫ ω, (2 * t) * (X ω - μ[X]) ∂μ = 0 := by
    have h2 : ∫ ω, (2 * t) * (X ω - μ[X]) ∂μ
        = (2 * t) * ∫ ω, X ω - μ[X] ∂μ :=
      integral_mul_left (2 * t : ℝ) (fun ω : Ω => X ω - μ[X])
    rw [h2, hint0, mul_zero]
  have hI3 : ∫ ω, t ^ 2 ∂μ = t ^ 2 := by rw [integral_const]; simp
  have hexp : ∀ ω, (X ω - μ[X] + t) ^ 2
      = (X ω - μ[X]) ^ 2 + ((2 * t) * (X ω - μ[X]) + t ^ 2) := fun ω => by ring
  have hstep1 : ∫ ω, (X ω - μ[X] + t) ^ 2 ∂μ
      = ∫ ω, (X ω - μ[X]) ^ 2 ∂μ
          + ∫ ω, (2 * t) * (X ω - μ[X]) + t ^ 2 ∂μ := by
    have h2 : ∫ ω, (X ω - μ[X]) ^ 2 + ((2 * t) * (X ω - μ[X]) + t ^ 2) ∂μ
        = ∫ ω, (X ω - μ[X]) ^ 2 ∂μ
          + ∫ ω, (2 * t) * (X ω - μ[X]) + t ^ 2 ∂μ :=
      integral_add' iC (iL.add iK)
    rw [integral_congr_ae (ae_of_all μ hexp)]
    exact h2
  have hstep2 : ∫ ω, (2 * t) * (X ω - μ[X]) + t ^ 2 ∂μ
      = ∫ ω, (2 * t) * (X ω - μ[X]) ∂μ + ∫ ω, t ^ 2 ∂μ :=
    integral_add' iL iK
  rw [hstep1, hstep2, hI1, hI2, hI3]
  ring

/-- **Cantelli's inequality** (one-sided Chebyshev), measure-theoretic:
for a real random variable with finite variance `v` and `k > 0`,
`P(X - E[X] ≥ k) ≤ v / (v + k^2)`. Distribution-free. -/
theorem cantelli [IsProbabilityMeasure μ] {X : Ω → ℝ} (hX : Memℒp X 2 μ)
    {k : ℝ} (hk : 0 < k) :
    μ {ω | k ≤ X ω - μ[X]} ≤ ENNReal.ofReal (variance X μ / (variance X μ + k ^ 2)) := by
  have hv : 0 ≤ variance X μ := variance_nonneg X μ
  set t : ℝ := variance X μ / k with ht
  have ht_nn : 0 ≤ t := div_nonneg hv hk.le
  have hkt : 0 < k + t := by linarith
  -- Step 1: the shifted square, as a nonnegative real function.
  set g : Ω → ℝ := fun ω => (X ω - μ[X] + t) ^ 2 with hg
  have hgnn : ∀ ω, 0 ≤ g ω := fun ω => pow_two_nonneg _
  have hgint : Integrable g μ :=
    ((hX.sub (memℒp_const _)).add (memℒp_const _)).integrable_sq
  have hgmeas : AEStronglyMeasurable g μ := hgint.aestronglyMeasurable
  -- Step 2: the event is contained in the shifted-square event.
  have hincl : {ω | k ≤ X ω - μ[X]} ⊆ {ω | (k + t) ^ 2 ≤ g ω} := by
    intro ω hω
    simp only [Set.mem_setOf_eq] at hω
    have h1 : k + t ≤ X ω - μ[X] + t := by linarith
    exact sq_le_sq' (by linarith) h1
  -- Step 3: Markov (L¹) on `g`, cast to the `‖·‖₊` form.
  have hcoe : ∀ ω, (‖g ω‖₊ : ℝ≥0∞) = ENNReal.ofReal (g ω) := by
    intro ω
    have h1 : (‖g ω‖₊ : ℝ≥0∞) = ENNReal.ofReal ‖g ω‖ :=
      (ofReal_norm_eq_coe_nnnorm (g ω)).symm
    rw [h1, Real.norm_eq_abs, abs_of_nonneg (hgnn ω)]
  have hset : {ω | (k + t) ^ 2 ≤ g ω}
      = {ω | ENNReal.ofReal ((k + t) ^ 2) ≤ ‖g ω‖₊} := by
    ext ω
    simp only [Set.mem_setOf_eq, hcoe ω, ENNReal.ofReal_le_ofReal_iff (hgnn ω)]
  have hε : ENNReal.ofReal ((k + t) ^ 2) ≠ 0 :=
    ((ENNReal.ofReal_pos).mpr (by positivity)).ne'
  have hmarkov := meas_ge_le_mul_pow_eLpNorm μ one_ne_zero ENNReal.one_ne_top hgmeas hε
  simp only [ENNReal.one_toReal, ENNReal.rpow_one] at hmarkov
  refine le_trans (measure_mono hincl) ?_
  rw [hset]
  refine le_trans hmarkov ?_
  -- Step 4: evaluate the Markov bound at the optimal shift t = v / k.
  have heLp : eLpNorm g 1 μ = ENNReal.ofReal (∫ ω, g ω ∂μ) := by
    rw [eLpNorm_eq_lintegral_rpow_nnnorm one_ne_zero ENNReal.one_ne_top]
    simp only [ENNReal.one_toReal, div_one, ENNReal.rpow_one]
    rw [ofReal_integral_eq_lintegral_ofReal hgint (ae_of_all μ hgnn)]
    exact lintegral_congr hcoe
  rw [heLp, integral_shifted_sq hX t]
  have hconv : (ENNReal.ofReal ((k + t) ^ 2))⁻¹ * ENNReal.ofReal (variance X μ + t ^ 2)
      = ENNReal.ofReal ((variance X μ + t ^ 2) / (k + t) ^ 2) := by
    rw [ENNReal.ofReal_div_of_pos (show (0:ℝ) < (k + t) ^ 2 by positivity),
      ENNReal.div_eq_inv_mul]
  rw [hconv]
  -- Real arithmetic: (v + t^2)/(k + t)^2 = v/(v + k^2) at t = v/k.
  have hkarith : (variance X μ + t ^ 2) / (k + t) ^ 2
      = variance X μ / (variance X μ + k ^ 2) := by
    have hdiv : (0:ℝ) ≤ variance X μ / k := div_nonneg hv hk.le
    have hden1 : (0:ℝ) < k + variance X μ / k := by linarith
    have hden1s : (0:ℝ) < (k + variance X μ / k) ^ 2 := sq_pos_of_ne_zero hden1.ne'
    have hden2 : (0:ℝ) < variance X μ + k ^ 2 := by nlinarith
    rw [ht]
    field_simp
    ring
  rw [hkarith]

/-- Standardized Cantelli: with `Var[X] = σ^2`, the bound is exactly
`cantelliBound k = 1 / (1 + k^2)` — the number Python compares
empirical exceedances against (`sigma/fit.py`). -/
theorem cantelli_std [IsProbabilityMeasure μ] {X : Ω → ℝ} (hX : Memℒp X 2 μ)
    {σ : ℝ} (hσ : 0 < σ) (hvar : variance X μ = σ ^ 2) {k : ℝ} (hk : 0 < k) :
    μ {ω | k * σ ≤ X ω - μ[X]} ≤ ENNReal.ofReal (cantelliBound k) := by
  have hkσ : 0 < k * σ := by positivity
  have h := cantelli hX hkσ
  rw [hvar] at h
  have hcalc : σ ^ 2 / (σ ^ 2 + (k * σ) ^ 2) = 1 / (1 + k ^ 2) := by
    have hσ2 : (0:ℝ) < σ ^ 2 := by nlinarith
    have hden : (0:ℝ) < σ ^ 2 + (k * σ) ^ 2 := by nlinarith
    have hden2 : (0:ℝ) < 1 + k ^ 2 := by nlinarith
    field_simp
    ring
  rw [hcalc] at h
  exact h

/-- Real-valued form of `cantelli` (probabilities as `ℝ`). -/
theorem cantelli_toReal [IsProbabilityMeasure μ] {X : Ω → ℝ} (hX : Memℒp X 2 μ)
    {k : ℝ} (hk : 0 < k) :
    (μ {ω | k ≤ X ω - μ[X]}).toReal ≤ variance X μ / (variance X μ + k ^ 2) := by
  have hv : 0 ≤ variance X μ := variance_nonneg X μ
  have h := cantelli hX hk
  have hne : ENNReal.ofReal (variance X μ / (variance X μ + k ^ 2)) ≠ ∞ :=
    ENNReal.ofReal_ne_top
  have h2 := (ENNReal.toReal_le_toReal (ne_top_of_le_ne_top hne h) hne).mpr h
  rwa [ENNReal.toReal_ofReal (div_nonneg hv (by nlinarith : (0:ℝ) ≤ variance X μ + k ^ 2))] at h2

end PerpTheory
