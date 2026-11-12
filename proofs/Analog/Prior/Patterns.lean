/- NOT IMPORTED by Analog.lean (2026-11-12): mechanical port fails on current Mathlib APIs; registered re-proof candidate in docs/research/06-lean-corpus-inventory.md. Preserved verbatim for the re-prover. -/
/-
PORTED 2026-11-12 from owner prior work: search/selection pattern bounds
Source: andrewkoumoudjian/perps-strategy @ 0f34759, lanes/chief/lean/PerpChief/Patterns.lean (toolchain v4.15.0).
Port changes ONLY: module path/import remap to Analog.Prior.* (+ Mathlib API renames if listed in docs/research/06). Namespaces, statements, proofs otherwise verbatim. Original file is frozen upstream; do not edit semantics here.
-/
/-
ROUND 6: LONG AND SHORT, CERTAINTY, AND THE SEARCH. FROZEN STATEMENTS (chief scientist), written before any further test.
D. Long and short on the same path: log returns bias each side in opposite directions, a long's loss is capped and a short's isn't,
   and net of cost the two capitals can't both grow.
C. Win rate alone isn't certainty: the break-even loss, and the exact variance of a two-point bet.
L. Leverage under the floor: the winning bets any path needs to reach a target, whatever the leverage inside k.
S. The search: a predictable state keeps the null, and J cells at threshold J/α control false discovery across all true nulls,
   whatever the others do. These state tests. They don't assert that any market state has an edge.
-/
import Analog.Prior.Battery

open MeasureTheory Filter Finset
open scoped ENNReal

namespace PerpChief.Patterns

noncomputable section

open PerpChief.Leverage PerpChief.Ville PerpChief.Selective

/-! ### D. Direction -/

/-- D1. On a price ratio `x`, a short's simple return never exceeds its log return. Log returns flatter shorts. -/
theorem short_log_flatters {x : ℝ} (hx : 0 < x) : 1 - x ≤ -Real.log x := by
  have := Real.log_le_sub_one_of_pos hx
  linarith

/-- D2. A long's log return never exceeds its simple return. Log returns penalise longs. -/
theorem long_log_understates {x : ℝ} (hx : 0 < x) : Real.log x ≤ x - 1 := by
  exact Real.log_le_sub_one_of_pos hx

/-- D3. A long's loss is at most its notional, for any non-negative price ratio. -/
theorem long_loss_capped {x : ℝ} (hx : 0 ≤ x) : -1 ≤ x - 1 := by
  linarith

/-- D4. A short's loss has no bound. -/
theorem short_loss_unbounded (B : ℝ) : ∃ x : ℝ, 0 < x ∧ 1 - x < -B := by
  refine ⟨|B| + 2, by positivity, ?_⟩
  have := le_abs_self B
  linarith

/-- Capital of a fixed bet `lam`, long the return `x`, paying `c` per bet. -/
def longCap (lam c : ℝ) (x : ℕ → ℝ) (T : ℕ) : ℝ := ∏ t ∈ range T, (1 + lam * (x t - c))

/-- Capital of a fixed bet `lam`, short the return `x`, paying `c` per bet. -/
def shortCap (lam c : ℝ) (x : ℕ → ℝ) (T : ℕ) : ℝ := ∏ t ∈ range T, (1 + lam * (-x t - c))

/-- D5. Net of cost, long and short capital multiply to at most one on every path. -/
theorem long_short_product {lam c : ℝ} {x : ℕ → ℝ} {T : ℕ} (hl : 0 ≤ lam) (hc : 0 ≤ c) (hlc : lam * c ≤ 2)
    (hL : ∀ t < T, 0 < 1 + lam * (x t - c)) (hS : ∀ t < T, 0 < 1 + lam * (-x t - c)) :
    longCap lam c x T * shortCap lam c x T ≤ 1 := by
  have hsplit : longCap lam c x T * shortCap lam c x T
      = ∏ t ∈ range T, ((1 + lam * (x t - c)) * (1 + lam * (-x t - c))) := by
    unfold longCap shortCap
    rw [Finset.prod_mul_distrib]
  rw [hsplit]
  refine Finset.prod_le_one (fun t ht => ?_) (fun t _ => ?_)
  · have ht' := Finset.mem_range.1 ht
    exact (mul_pos (hL t ht') (hS t ht')).le
  · have h0 : 0 ≤ lam * c := mul_nonneg hl hc
    have h1 : (1 + lam * (x t - c)) * (1 + lam * (-x t - c)) = (1 - lam * c) ^ 2 - (lam * x t) ^ 2 := by ring
    rw [h1]
    nlinarith [sq_nonneg (lam * x t), mul_nonneg h0 (by linarith : 0 ≤ 2 - lam * c)]

/-- D6. So if one direction's capital reaches `C`, the other's is at most `1/C`. -/
theorem one_direction_only {lam c C : ℝ} {x : ℕ → ℝ} {T : ℕ} (hl : 0 ≤ lam) (hc : 0 ≤ c) (hlc : lam * c ≤ 2)
    (hL : ∀ t < T, 0 < 1 + lam * (x t - c)) (hS : ∀ t < T, 0 < 1 + lam * (-x t - c))
    (hC : 0 < C) (hreach : C ≤ longCap lam c x T) : shortCap lam c x T ≤ 1 / C := by
  have hprod := long_short_product hl hc hlc hL hS
  have hSpos : 0 < shortCap lam c x T :=
    Finset.prod_pos fun t ht => hS t (Finset.mem_range.1 ht)
  rw [le_div_iff₀ hC]
  nlinarith [mul_le_mul_of_nonneg_right hreach hSpos.le]

/-! ### C. Certainty -/

/-- C1. For any win rate below one, a large enough loss makes the mean non-positive. -/
theorem win_rate_not_certainty {p u v : ℝ} (hp0 : 0 < p) (hp1 : p < 1) (hv : p * u / (1 - p) ≤ v) :
    p * u - (1 - p) * v ≤ 0 := by
  have hd : 0 < 1 - p := by linarith
  rw [div_le_iff₀ hd] at hv
  linarith

/-- C2. The exact variance of a bet winning `u` with probability `p` and losing `v` otherwise. -/
theorem bet_variance (p u v : ℝ) :
    p * u ^ 2 + (1 - p) * v ^ 2 - (p * u - (1 - p) * v) ^ 2 = p * (1 - p) * (u + v) ^ 2 := by
  ring

/-! ### L. Leverage under the floor -/

/-- Number of winning steps. -/
def wins (r : ℕ → ℝ) (T : ℕ) : ℕ := ((range T).filter fun t => 0 < r t).card

private lemma wins_succ_pos {r : ℕ → ℝ} {T : ℕ} (h : 0 < r T) : wins r (T + 1) = wins r T + 1 := by
  unfold wins
  rw [Finset.range_succ, Finset.filter_insert, if_pos h, Finset.card_insert_of_not_mem]
  simp

private lemma wins_succ_nonpos {r : ℕ → ℝ} {T : ℕ} (h : ¬ 0 < r T) : wins r (T + 1) = wins r T := by
  unfold wins
  rw [Finset.range_succ, Finset.filter_insert, if_neg h]

/-- L1. Under the floor and cushion sizing, each winning step raises the high-water mark by at most `1 + δkU`. -/
theorem wins_ceiling {δ k E0 U : ℝ} {r : ℕ → ℝ} (hE : 0 < E0) (hδ0 : 0 < δ) (hδ1 : δ < 1) (hk : 0 < k) (hU : 0 ≤ U)
    (T : ℕ) (hgap : ∀ t < T, -1 / k < r t) (hr : ∀ t < T, r t ≤ U) :
    (run δ k E0 r T).H ≤ E0 * (1 + δ * k * U) ^ wins r T := by
  have hA : 1 ≤ 1 + δ * k * U := by
    have : 0 ≤ δ * k * U := by positivity
    linarith
  induction T with
  | zero =>
      show E0 ≤ E0 * (1 + δ * k * U) ^ wins r 0
      simp [wins]
  | succ T ih =>
      have ih' := ih (fun t ht => hgap t (by omega)) (fun t ht => hr t (by omega))
      obtain ⟨hEp, hEH, hHp, hc0, hcle⟩ :=
        ws3_cstate_inv (r := r) hE hδ0 hδ1 hk T fun t ht => hgap t (by omega)
      set s := run δ k E0 r T with hs
      have hH' : (run δ k E0 r (T + 1)).H = max s.H (s.E + k * cushion δ s * r T) := rfl
      have hAp : 0 < (1 + δ * k * U) ^ wins r T := by positivity
      by_cases hw : 0 < r T
      · have hcnt : wins r (T + 1) = wins r T + 1 := wins_succ_pos hw
        rw [hH', hcnt, pow_succ, ← mul_assoc]
        have hup : s.E + k * cushion δ s * r T ≤ s.H * (1 + δ * k * U) := by
          have h1 : cushion δ s * r T ≤ δ * s.E * U :=
            mul_le_mul hcle (hr T (by omega)) hw.le (by positivity)
          have h2 : k * (cushion δ s * r T) ≤ k * (δ * s.E * U) := mul_le_mul_of_nonneg_left h1 hk.le
          have h3 : s.E * (δ * k * U) ≤ s.H * (δ * k * U) := mul_le_mul_of_nonneg_right hEH (by positivity)
          nlinarith
        have hle : max s.H (s.E + k * cushion δ s * r T) ≤ s.H * (1 + δ * k * U) :=
          max_le (by nlinarith) hup
        exact hle.trans (mul_le_mul_of_nonneg_right ih' (by linarith))
      · have hcnt : wins r (T + 1) = wins r T := wins_succ_nonpos hw
        rw [hH', hcnt]
        push_neg at hw
        have hdown : s.E + k * cushion δ s * r T ≤ s.H := by
          have : k * cushion δ s * r T ≤ 0 := mul_nonpos_of_nonneg_of_nonpos (by positivity) hw
          linarith
        rw [max_eq_left hdown]
        exact ih'

/-- L2. Reaching a multiple `M` of the start needs at least `log M / log(1 + δkU)` winning steps. -/
theorem wins_needed {δ k E0 U M : ℝ} {r : ℕ → ℝ} (hE : 0 < E0) (hδ0 : 0 < δ) (hδ1 : δ < 1) (hk : 0 < k) (hU : 0 ≤ U)
    (hM : 0 < M) (T : ℕ) (hgap : ∀ t < T, -1 / k < r t) (hr : ∀ t < T, r t ≤ U)
    (hreach : M * E0 ≤ (run δ k E0 r T).H) :
    Real.log M ≤ wins r T * Real.log (1 + δ * k * U) := by
  have hc := wins_ceiling hE hδ0 hδ1 hk hU T hgap hr
  have hA : 0 < 1 + δ * k * U := by
    have : 0 ≤ δ * k * U := by positivity
    linarith
  have hle : M ≤ (1 + δ * k * U) ^ wins r T := by
    have : M * E0 ≤ (1 + δ * k * U) ^ wins r T * E0 := by nlinarith
    exact le_of_mul_le_mul_right this hE
  have := Real.log_le_log hM hle
  rwa [Real.log_pow] at this

/-! ### S. The search -/

/-- S1. Gating a bet on a predictable state keeps the null. -/
theorem gated_null {Ω : Type*} {m0 : MeasurableSpace Ω} {μ : Measure Ω} [IsProbabilityMeasure μ]
    {ℱ : Filtration ℕ m0} {A : ℕ → Set Ω} {Y : ℕ → Ω → ℝ} (hA : ∀ n, MeasurableSet[ℱ n] (A n))
    (hY : ∀ n, Integrable (Y (n + 1)) μ)
    (hnull : ∀ n, ∀ᵐ ω ∂μ, ω ∈ A n → (μ[Y (n + 1) | ℱ n]) ω ≤ 0) (n : ℕ) :
    μ[(A n).indicator (Y (n + 1)) | ℱ n] ≤ᵐ[μ] fun _ => 0 := by
  have hi := condexp_indicator (hY n) (hA n)
  filter_upwards [hi, hnull n] with ω h1 h2
  rw [h1]
  by_cases hm : ω ∈ A n
  · rw [Set.indicator_of_mem hm]
    exact h2 hm
  · rw [Set.indicator_of_not_mem hm]

/-- S2. Across `J` cells at threshold `J/α`, the chance that any truly null cell reaches it is at most `α`,
whatever the other cells do. -/
theorem search_fwer {Ω : Type*} {m0 : MeasurableSpace Ω} {μ : Measure Ω} [IsProbabilityMeasure μ]
    {ℱ : Filtration ℕ m0} {J K : ℕ} (hJ : 0 < J) (hK : 0 < K) {lams : Fin K → ℝ}
    {X : Fin J → ℕ → Ω → ℝ} {B U L : ℝ} (N0 : Finset (Fin J))
    (h : ∀ j ∈ N0, ∀ k, BettingHyp ℱ μ (fun _ _ => lams k) (X j) 0 B U L) {α : ℝ} (hα : 0 < α) (N : ℕ) :
    μ {ω | ∃ j ∈ N0, ∃ n ≤ N, (J : ℝ) / α ≤ (∑ k, capital (fun _ _ => lams k) (X j) 0 n ω) / K}
      ≤ ENNReal.ofReal α := by
  have hJr : (0 : ℝ) < J := by exact_mod_cast hJ
  have hα' : 0 < α / J := div_pos hα hJr
  set S : Fin J → Set Ω := fun j => {ω | ∃ n ≤ N, (J : ℝ) / α ≤ (∑ k, capital (fun _ _ => lams k) (X j) 0 n ω) / K} with hS
  have hone : ∀ j ∈ N0, μ (S j) ≤ ENNReal.ofReal (α / J) := fun j hj => by
    have hm := mix_ville hK (fun k => h j hj k) hα' N
    have he : 1 / (α / J) = (J : ℝ) / α := by field_simp
    rwa [he] at hm
  have hsub : {ω | ∃ j ∈ N0, ∃ n ≤ N, (J : ℝ) / α ≤ (∑ k, capital (fun _ _ => lams k) (X j) 0 n ω) / K}
      ⊆ ⋃ j ∈ N0, S j := by
    intro ω hω
    obtain ⟨j, hj, hn⟩ := hω
    exact Set.mem_biUnion hj hn
  have hcard : ((N0.card : ℕ) : ℝ) ≤ J := by
    have := Finset.card_le_univ N0
    simp only [Fintype.card_fin] at this
    exact_mod_cast this
  calc _ ≤ μ (⋃ j ∈ N0, S j) := measure_mono hsub
    _ ≤ ∑ j ∈ N0, μ (S j) := measure_biUnion_finset_le _ _
    _ ≤ ∑ _j ∈ N0, ENNReal.ofReal (α / J) := Finset.sum_le_sum hone
    _ = ENNReal.ofReal (∑ _j ∈ N0, α / J) := (ENNReal.ofReal_sum_of_nonneg fun _ _ => hα'.le).symm
    _ ≤ ENNReal.ofReal α := by
        apply ENNReal.ofReal_le_ofReal
        simp only [Finset.sum_const, nsmul_eq_mul]
        calc (N0.card : ℝ) * (α / J) ≤ J * (α / J) := mul_le_mul_of_nonneg_right hcard hα'.le
          _ = α := by field_simp

end

end PerpChief.Patterns
