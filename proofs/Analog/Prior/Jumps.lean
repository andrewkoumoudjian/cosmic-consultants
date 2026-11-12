/-
PORTED 2026-11-12 from owner prior work: Weissman EVT extrapolation + hazard budgets
Source: andrewkoumoudjian/perps-strategy @ 0f34759, lanes/chief/lean/PerpChief/Jumps.lean (toolchain v4.15.0).
Port changes ONLY: module path/import remap to Analog.Prior.* (+ Mathlib API renames if listed in docs/research/06). Namespaces, statements, proofs otherwise verbatim. Original file is frozen upstream; do not edit semantics here.
-/
/-
ROUND 3b — JUMP MODELLING AS A RISK BUDGET. FROZEN STATEMENTS (chief scientist).
Prior lanes: the jump rate is stable and clusters, the sign is near 50/50, and jump rates were not forecastable
as a directional edge. So stop asking which way a jump goes and ask how much leverage its hazard allows.
Part A: the jump-limited multiplier. Part B: hazard parity. Part C: what a hazard state can buy.
Part D: aftershock cool-off. Part E: the direction-free payoff (discrete Tanaka).
`PerpChief.Leverage.breach_le_union` already turns a marginal gap hazard into a breach bound with no independence.
Verified does not mean profitable.
-/
import Analog.Prior.LeverageLaw
import Analog.Prior.Events
import Mathlib.Analysis.MeanInequalitiesPow

open Finset

namespace PerpChief.Jumps

noncomputable section

variable {ι : Type*}

/-! ### Part A — the jump-limited multiplier -/

/-- A1. Under a Pareto gap tail `P(step ≤ -x) = C·x^(-α)`, summed gap hazard over `H` steps at multiplier `k`
stays within budget `β` exactly when `k` is at most `(β/(H·C))^(1/α)`. -/
theorem jump_limited_k {H C β k α : ℝ} (hH : 0 < H) (hC : 0 < C) (hβ : 0 < β) (hk : 0 < k) (hα : 0 < α) :
    H * (C * (1 / k) ^ (-α)) ≤ β ↔ k ≤ (β / (H * C)) ^ (1 / α) := by
  have e : (1 / k) ^ (-α) = k ^ α := by
    rw [one_div, Real.inv_rpow hk.le, Real.rpow_neg hk.le, inv_inv]
  have hHC : 0 < H * C := mul_pos hH hC
  rw [e, one_div, Real.le_rpow_inv_iff_of_pos hk.le (div_pos hβ hHC).le hα, le_div_iff₀ hHC]
  constructor <;> intro h <;> nlinarith

/-- A2. Cutting the hazard by a factor `ρ` raises the limit by exactly `ρ^(-1/α)`. -/
theorem hazard_cut_gain {H C β ρ α : ℝ} (hH : 0 < H) (hC : 0 < C) (hβ : 0 < β) (hρ : 0 < ρ) :
    (β / (H * (C * ρ))) ^ (1 / α) = ρ ^ (-(1 / α)) * (β / (H * C)) ^ (1 / α) := by
  have hHC : 0 < H * C := mul_pos hH hC
  have e : β / (H * (C * ρ)) = ρ⁻¹ * (β / (H * C)) := by
    have h1 := hH.ne'
    have h2 := hC.ne'
    have h3 := hρ.ne'
    field_simp
  rw [e, Real.mul_rpow (inv_nonneg.2 hρ.le) (div_pos hβ hHC).le, Real.inv_rpow hρ.le,
    Real.rpow_neg hρ.le]

/-- A3. Weissman extrapolation: under a Pareto tail, the level at hazard `h` is the level at anchor `p`
scaled by `(p/h)^(1/α)`. This is the role of a 5-8% anchor. -/
theorem weissman {C α p h : ℝ} (hC : 0 < C) (hα : 0 < α) (hp : 0 < p) (hh : 0 < h) :
    (C / h) ^ (1 / α) = (C / p) ^ (1 / α) * (p / h) ^ (1 / α) := by
  have _ := hα
  rw [← Real.mul_rpow (div_pos hC hp).le (div_pos hp hh).le]
  congr 1
  field_simp

/-- A4. Mis-estimating the exponent multiplies the deep level by `(p/h)^(1/α̂ - 1/α)`. -/
theorem weissman_error {p h a a' : ℝ} (hp : 0 < p) (hh : 0 < h) :
    (p / h) ^ (1 / a') = (p / h) ^ (1 / a' - 1 / a) * (p / h) ^ (1 / a) := by
  rw [← Real.rpow_add (div_pos hp hh)]
  congr 1
  ring

/-! ### Part B — hazard parity -/

/-- B1. Scale `σ_t`, tail index `α ≥ 1`. A flat multiplier `m / M_α(σ)` and the parity multiplier `m / σ_t` spend the
same summed hazard `Σ (k_t σ_t)^α`. Parity's mean exposure is at least the flat one. -/
theorem hazard_parity_exposure (s : Finset ι) (hs : s.Nonempty) (σ : ι → ℝ) (hσ : ∀ i ∈ s, 0 < σ i)
    {α : ℝ} (hα : 1 ≤ α) :
    1 / ((∑ i ∈ s, σ i ^ α) / s.card) ^ (1 / α) ≤ (∑ i ∈ s, 1 / σ i) / s.card := by
  have hn : (0 : ℝ) < s.card := by exact_mod_cast hs.card_pos
  have hα0 : 0 < α := by linarith
  set w : ι → ℝ := fun _ => 1 / (s.card : ℝ) with hw
  have hw0 : ∀ i ∈ s, 0 ≤ w i := fun _ _ => by simp only [hw]; positivity
  have hw1 : ∑ i ∈ s, w i = 1 := by
    simp only [hw, sum_const, nsmul_eq_mul]; field_simp
  have hpow := Real.rpow_arith_mean_le_arith_mean_rpow s w σ hw0 hw1 (fun i hi => (hσ i hi).le) hα
  have e1 : ∑ i ∈ s, w i * σ i = (∑ i ∈ s, σ i) / s.card := by
    simp only [hw]; rw [← mul_sum]; ring
  have e2 : ∑ i ∈ s, w i * σ i ^ α = (∑ i ∈ s, σ i ^ α) / s.card := by
    simp only [hw]; rw [← mul_sum]; ring
  rw [e1, e2] at hpow
  have hsum : 0 < ∑ i ∈ s, σ i := sum_pos hσ hs
  have hmean : 0 < (∑ i ∈ s, σ i) / s.card := div_pos hsum hn
  have hM : 0 < (∑ i ∈ s, σ i ^ α) / s.card :=
    div_pos (sum_pos (fun i hi => Real.rpow_pos_of_pos (hσ i hi) α) hs) hn
  have hroot : (∑ i ∈ s, σ i) / s.card ≤ ((∑ i ∈ s, σ i ^ α) / s.card) ^ (1 / α) := by
    rw [one_div, Real.le_rpow_inv_iff_of_pos hmean.le hM.le hα0]
    exact hpow
  have hgain := PerpChief.Events.vol_managed_gain s σ hσ
  have hinv : 1 / ((∑ i ∈ s, σ i) / s.card) ≤ (∑ i ∈ s, 1 / σ i) / s.card := by
    rw [div_le_div_iff₀ hmean hn]
    have : (s.card : ℝ) ≠ 0 := hn.ne'
    field_simp
    rw [mul_comm]; exact hgain
  exact (one_div_le_one_div_of_le hmean hroot).trans hinv

/-- B2. Parity spends exactly the per-step hazard budget. -/
theorem hazard_parity_budget {m σ α : ℝ} (hm : 0 ≤ m) (hσ : 0 < σ) : (m / σ * σ) ^ α = m ^ α := by
  have _ := hm
  rw [div_mul_cancel₀ _ hσ.ne']

/-! ### Part C — what a hazard state can buy -/

/-- C1. Exposure share `e`, lift `ℓ` inside the state: the hazard outside it is `(1 - e·ℓ)/(1 - e)` of base. -/
theorem residual_hazard {N nS J JS : ℝ} (hN : 0 < N) (hJ : 0 < J) (hnS : 0 < nS) (hS : nS < N) :
    (J - JS) / (N - nS) / (J / N)
      = (1 - (nS / N) * ((JS / nS) / (J / N))) / (1 - nS / N) := by
  have h1 : N - nS ≠ 0 := by linarith
  have e : 1 - nS / N = (N - nS) / N := by field_simp
  rw [e]
  have := hN.ne'
  have := hJ.ne'
  have := hnS.ne'
  field_simp

/-- C2. Stepping out of a state with lift above one lowers the hazard per unit of exposure. -/
theorem residual_hazard_lt {e l : ℝ} (he0 : 0 < e) (he1 : e < 1) (hl : 1 < l) :
    (1 - e * l) / (1 - e) < 1 := by
  rw [div_lt_one (by linarith)]
  nlinarith

/-! ### Part D — aftershock cool-off -/

/-- D1. Omori form `lift(a) = A·a^(-q)`: the lift falls to one or below exactly from age `A^(1/q)`. -/
theorem omori_cooloff {A q a : ℝ} (hA : 0 < A) (hq : 0 < q) (ha : 0 < a) :
    A * a ^ (-q) ≤ 1 ↔ A ^ (1 / q) ≤ a := by
  have hp : 0 < a ^ q := Real.rpow_pos_of_pos ha q
  rw [Real.rpow_neg ha.le, ← div_eq_mul_inv, div_le_one hp, one_div,
    Real.rpow_inv_le_iff_of_pos hA.le ha.le hq]

/-! ### Part E — the direction-free payoff -/

/-- Side held at bar `t`: long at or above the level, short below. -/
def side (K p : ℝ) : ℝ := if K ≤ p then 1 else -1

/-- Bar `t`'s crossing cost in a stop-and-reverse book. -/
def crossCost (K p p' : ℝ) : ℝ := |p' - K| - |p - K| - side K p * (p' - p)

/-- E1. Discrete Tanaka: a stop-and-reverse book's PnL is the convex payoff minus summed crossing costs. On every path. -/
theorem tanaka (K : ℝ) (S : ℕ → ℝ) (T : ℕ) :
    ∑ t ∈ range T, side K (S t) * (S (t + 1) - S t)
      = |S T - K| - |S 0 - K| - ∑ t ∈ range T, crossCost K (S t) (S (t + 1)) := by
  induction T with
  | zero => simp
  | succ n ih =>
    rw [sum_range_succ, sum_range_succ, ih]
    unfold crossCost
    ring

/-- E2. Crossing costs are never negative. -/
theorem crossCost_nonneg (K p p' : ℝ) : 0 ≤ crossCost K p p' := by
  unfold crossCost side
  rcases abs_cases (p' - K) with ⟨h1, _⟩ | ⟨h1, _⟩ <;> rcases abs_cases (p - K) with ⟨h2, _⟩ | ⟨h2, _⟩ <;>
    split_ifs <;> rw [h1, h2] <;> linarith

/-- E3. No crossing, no cost. -/
theorem crossCost_eq_zero {K p p' : ℝ} (h : (K ≤ p ∧ K ≤ p') ∨ (p < K ∧ p' ≤ K)) : crossCost K p p' = 0 := by
  unfold crossCost side
  rcases h with ⟨h1, h2⟩ | ⟨h1, h2⟩
  · rw [abs_of_nonneg (sub_nonneg.2 h2), abs_of_nonneg (sub_nonneg.2 h1), if_pos h1]; ring
  · rw [abs_of_nonpos (sub_nonpos.2 h2), abs_of_neg (sub_neg.2 h1), if_neg (not_le.2 h1)]; ring

/-- E4. At a crossing the cost is twice the overshoot past the level: a gap through the level costs the whole gap. -/
theorem crossCost_at_cross {K p p' : ℝ} (h : (K ≤ p ∧ p' < K) ∨ (p < K ∧ K < p')) :
    crossCost K p p' = 2 * |p' - K| := by
  unfold crossCost side
  rcases h with ⟨h1, h2⟩ | ⟨h1, h2⟩
  · rw [abs_of_neg (sub_neg.2 h2), abs_of_nonneg (sub_nonneg.2 h1), if_pos h1]; ring
  · rw [abs_of_pos (sub_pos.2 h2), abs_of_neg (sub_neg.2 h1), if_neg (not_le.2 h1)]; ring

end

end PerpChief.Jumps
