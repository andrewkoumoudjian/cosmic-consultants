/-
PORTED 2026-11-12 from owner prior work: rare-event frequency vs magnitude separation
Source: andrewkoumoudjian/perps-strategy @ 0f34759, lanes/chief/lean/PerpChief/Events.lean (toolchain v4.15.0).
Port changes ONLY: module path/import remap to Analog.Prior.* (+ Mathlib API renames if listed in docs/research/06). Namespaces, statements, proofs otherwise verbatim. Original file is frozen upstream; do not edit semantics here.
-/
/-
ROUND 3a — THE 5-8% EVENT FAMILY. FROZEN STATEMENTS (chief scientist).
A rare event can be stable as a frequency and say nothing about direction. These theorems separate what the
frequency proves from what must still be tested, and price the evidence a clustered, concentrated book can give.
Part A: frequency and energy. Part B: concentration caps evidence. Part C: clustered bets.
Part D: where to place capital across events. Part E: hedging. Part F: the threshold-cost law.
Verified does not mean profitable.
-/
import Analog.Prior.Ceiling
import Mathlib.Algebra.Order.Chebyshev
import Mathlib.Analysis.Convex.SpecificFunctions.Basic

open Finset

namespace PerpChief.Events

noncomputable section

variable {ι κ : Type*}

/-! ### Part A — what a frequency proves -/

/-- A1. Pathwise Markov: bars past threshold `k` carry at least `count · k²` of the energy. -/
theorem exceed_count_energy (s : Finset ι) (z : ι → ℝ) {k : ℝ} (hk : 0 ≤ k) :
    ((s.filter (fun i => k ≤ |z i|)).card : ℝ) * k ^ 2 ≤ ∑ i ∈ s, z i ^ 2 := by
  calc ((s.filter (fun i => k ≤ |z i|)).card : ℝ) * k ^ 2
      = ∑ _i ∈ s.filter (fun i => k ≤ |z i|), k ^ 2 := by simp [sum_const, nsmul_eq_mul]
    _ ≤ ∑ i ∈ s.filter (fun i => k ≤ |z i|), z i ^ 2 := by
        refine sum_le_sum fun i hi => ?_
        have h := pow_le_pow_left₀ hk (mem_filter.1 hi).2 2
        rwa [sq_abs] at h
    _ ≤ ∑ i ∈ s, z i ^ 2 :=
        sum_le_sum_of_subset_of_nonneg (filter_subset _ _) (fun _ _ _ => sq_nonneg _)

/-- A2. Lower bound on the tail's share of energy from its frequency and the body's mean square. -/
theorem tail_share_ge {nT nB K b T : ℝ} (hnT : 0 < nT) (hK : 0 < K) (hnB : 0 ≤ nB) (hb : 0 ≤ b)
    (hT : nT * K ≤ T) :
    nT * K / (nT * K + nB * b) ≤ T / (T + nB * b) := by
  have hx : 0 < nT * K := mul_pos hnT hK
  have hc : 0 ≤ nB * b := mul_nonneg hnB hb
  have hTpos : 0 < T := lt_of_lt_of_le hx hT
  rw [div_le_div_iff₀ (by linarith) (by linarith)]
  nlinarith [mul_nonneg (sub_nonneg.2 hT) hc]

/-- The three-point law: `+k` with probability `q`, `-k` with `p - q`, otherwise `0`. -/
def atoms (k : ℝ) : Fin 3 → ℝ := ![k, -k, 0]
def law (p q : ℝ) : Fin 3 → ℝ := ![q, p - q, 1 - p]

/-- A3. The law is a probability vector for every admissible split. -/
theorem law_prob {p q : ℝ} (hq0 : 0 ≤ q) (hqp : q ≤ p) (hp1 : p ≤ 1) :
    (∀ i, 0 ≤ law p q i) ∧ ∑ i, law p q i = 1 := by
  refine ⟨fun i => ?_, ?_⟩
  · fin_cases i <;> simp [law] <;> linarith
  · simp [law, Fin.sum_univ_three]

/-- A4. Its exceedance frequency at `k` is exactly `p`, whatever the split `q`. -/
theorem law_frequency {p q k : ℝ} (hk : 0 < k) :
    ∑ i, (if k ≤ |atoms k i| then law p q i else 0) = p := by
  simp [Fin.sum_univ_three, atoms, law, abs_neg, abs_of_pos hk, not_le.2 hk]

/-- A5. Its second moment is `p·k²`, whatever the split `q`. -/
theorem law_second_moment {p q k : ℝ} : ∑ i, law p q i * atoms k i ^ 2 = p * k ^ 2 := by
  simp [Fin.sum_univ_three, atoms, law]
  ring

/-- A6. Its mean is `(2q - p)·k`: every value in `[-p·k, p·k]` occurs at the same frequency and energy.
A frequency and a second moment therefore cannot identify the sign of the drift. -/
theorem law_mean {p q k : ℝ} : ∑ i, law p q i * atoms k i = (2 * q - p) * k := by
  simp [Fin.sum_univ_three, atoms, law]
  ring

/-! ### Part B — concentration caps evidence -/

/-- B1. If a subset `T` holds share `σ` of total PnL, the squared t-statistic is at most `|T|/σ²`. Law-free. -/
theorem concentration_tstat {s T : Finset ι} {x : ι → ℝ} {σ : ℝ} (hT : T ⊆ s) (hσ : σ ≠ 0)
    (hshare : ∑ i ∈ T, x i = σ * ∑ i ∈ s, x i) (hB : 0 < ∑ i ∈ s, x i ^ 2) :
    (∑ i ∈ s, x i) ^ 2 / ∑ i ∈ s, x i ^ 2 ≤ (T.card : ℝ) / σ ^ 2 := by
  have h1 : (∑ i ∈ T, x i) ^ 2 ≤ (T.card : ℝ) * ∑ i ∈ T, x i ^ 2 := sq_sum_le_card_mul_sum_sq
  have h2 : ∑ i ∈ T, x i ^ 2 ≤ ∑ i ∈ s, x i ^ 2 :=
    sum_le_sum_of_subset_of_nonneg hT (fun _ _ _ => sq_nonneg _)
  have hσ2 : 0 < σ ^ 2 := by positivity
  rw [div_le_div_iff₀ hB hσ2]
  have h3 : (T.card : ℝ) * ∑ i ∈ T, x i ^ 2 ≤ (T.card : ℝ) * ∑ i ∈ s, x i ^ 2 :=
    mul_le_mul_of_nonneg_left h2 (Nat.cast_nonneg _)
  rw [hshare] at h1
  nlinarith

/-- B2. Hence every fixed-fraction e-process on that book has log-value at most `|T|/(4cσ²)`. -/
theorem evalue_concentration {x : ℕ → ℝ} {lam ε σ : ℝ} {N : ℕ} {T : Finset ℕ} (hε0 : 0 < ε) (hε1 : ε < 1)
    (h : ∀ t < N, |lam * x t| ≤ ε) (hT : T ⊆ range N) (hσ : σ ≠ 0)
    (hshare : ∑ i ∈ T, x i = σ * ∑ i ∈ range N, x i) (hB : 0 < ∑ i ∈ range N, x i ^ 2) :
    ∑ t ∈ range N, Real.log (1 + lam * x t) ≤ (T.card : ℝ) / (4 * (1 / 2 - ε / 3) * σ ^ 2) := by
  have h0 := PerpChief.Ceiling.log_capital_le_tstat hε0 hε1 N h hB
  have hc : (0 : ℝ) < 1 / 2 - ε / 3 := by linarith
  have h1 := concentration_tstat hT hσ hshare hB
  have hσ2 : σ ≠ 0 := hσ
  have e1 : (∑ t ∈ range N, x t) ^ 2 / (4 * (1 / 2 - ε / 3) * ∑ t ∈ range N, x t ^ 2)
      = ((∑ t ∈ range N, x t) ^ 2 / ∑ t ∈ range N, x t ^ 2) / (4 * (1 / 2 - ε / 3)) := by
    rw [div_div, mul_comm (∑ t ∈ range N, x t ^ 2)]
  have e2 : (T.card : ℝ) / (4 * (1 / 2 - ε / 3) * σ ^ 2)
      = ((T.card : ℝ) / σ ^ 2) / (4 * (1 / 2 - ε / 3)) := by
    rw [div_div, mul_comm (σ ^ 2)]
  rw [e2]
  rw [e1] at h0
  exact h0.trans (div_le_div_of_nonneg_right h1 (by positivity))

/-! ### Part C — clustered bets -/

/-- C1. Bundling bets into clusters of size at most `m` raises the summed square by at most `m`. -/
theorem cluster_penalty [DecidableEq κ] (s : Finset ι) (c : ι → κ) (x : ι → ℝ) {m : ℕ}
    (hm : ∀ g ∈ s.image c, (s.filter (fun i => c i = g)).card ≤ m) :
    ∑ g ∈ s.image c, (∑ i ∈ s.filter (fun i => c i = g), x i) ^ 2 ≤ (m : ℝ) * ∑ i ∈ s, x i ^ 2 := by
  calc ∑ g ∈ s.image c, (∑ i ∈ s.filter (fun i => c i = g), x i) ^ 2
      ≤ ∑ g ∈ s.image c, (m : ℝ) * ∑ i ∈ s.filter (fun i => c i = g), x i ^ 2 := by
        refine sum_le_sum fun g hg => ?_
        refine sq_sum_le_card_mul_sum_sq.trans ?_
        refine mul_le_mul_of_nonneg_right ?_ (sum_nonneg fun _ _ => sq_nonneg _)
        exact_mod_cast hm g hg
    _ = (m : ℝ) * ∑ i ∈ s, x i ^ 2 := by
        rw [← mul_sum, sum_fiberwise_of_maps_to (fun i hi => mem_image_of_mem c hi)]

lemma sum_sq_le_sq_sum (t : Finset ι) (y : ι → ℝ) (h : ∀ i ∈ t, 0 ≤ y i) :
    ∑ i ∈ t, y i ^ 2 ≤ (∑ i ∈ t, y i) ^ 2 := by
  classical
  induction t using Finset.induction_on with
  | empty => simp
  | @insert a t ha ih =>
    have h1 := h a (mem_insert_self a t)
    have h2 : 0 ≤ ∑ i ∈ t, y i := sum_nonneg fun i hi => h i (mem_insert_of_mem hi)
    have h3 := ih fun i hi => h i (mem_insert_of_mem hi)
    rw [sum_insert ha, sum_insert ha]
    nlinarith [mul_nonneg h1 h2]

/-- C2. If every cluster's bets share a sign, bundling cannot lower the summed square: the raw t-statistic overstates. -/
theorem cluster_same_sign [DecidableEq κ] (s : Finset ι) (c : ι → κ) (x : ι → ℝ)
    (hsign : ∀ g ∈ s.image c, (∀ i ∈ s.filter (fun i => c i = g), 0 ≤ x i) ∨
      (∀ i ∈ s.filter (fun i => c i = g), x i ≤ 0)) :
    ∑ i ∈ s, x i ^ 2 ≤ ∑ g ∈ s.image c, (∑ i ∈ s.filter (fun i => c i = g), x i) ^ 2 := by
  rw [← sum_fiberwise_of_maps_to (s := s) (t := s.image c) (g := c)
    (fun i hi => mem_image_of_mem c hi) (fun i => x i ^ 2)]
  refine sum_le_sum fun g hg => ?_
  rcases hsign g hg with h | h
  · exact sum_sq_le_sq_sum _ _ h
  · have := sum_sq_le_sq_sum (s.filter (fun i => c i = g)) (fun i => -x i)
      (fun i hi => by have := h i hi; simp; linarith)
    simpa [sum_neg_distrib] using this

/-! ### Part D — placing capital across events -/

/-- D1. Sharpe budget: `(Σ wμ)² / Σ w²σ² ≤ Σ μ²/σ²` for every weighting. -/
theorem sharpe_budget (s : Finset ι) (w μ v : ι → ℝ) (hv : ∀ i ∈ s, 0 < v i) :
    (∑ i ∈ s, w i * μ i) ^ 2 ≤ (∑ i ∈ s, w i ^ 2 * v i) * ∑ i ∈ s, μ i ^ 2 / v i := by
  have key := sum_mul_sq_le_sq_mul_sq s (fun i => w i * √(v i)) (fun i => μ i / √(v i))
  have e1 : ∑ i ∈ s, w i * √(v i) * (μ i / √(v i)) = ∑ i ∈ s, w i * μ i := by
    refine sum_congr rfl fun i hi => ?_
    have : √(v i) ≠ 0 := (Real.sqrt_pos.2 (hv i hi)).ne'
    field_simp
  have e2 : ∑ i ∈ s, (w i * √(v i)) ^ 2 = ∑ i ∈ s, w i ^ 2 * v i := by
    refine sum_congr rfl fun i hi => ?_
    rw [mul_pow, Real.sq_sqrt (hv i hi).le]
  have e3 : ∑ i ∈ s, (μ i / √(v i)) ^ 2 = ∑ i ∈ s, μ i ^ 2 / v i := by
    refine sum_congr rfl fun i hi => ?_
    rw [div_pow, Real.sq_sqrt (hv i hi).le]
  simpa only [e1, e2, e3] using key

/-- D2. The budget is attained at `w = μ/σ²`. -/
theorem sharpe_budget_attained (s : Finset ι) (μ v : ι → ℝ) (hv : ∀ i ∈ s, 0 < v i) :
    (∑ i ∈ s, (μ i / v i) * μ i) ^ 2
      = (∑ i ∈ s, (μ i / v i) ^ 2 * v i) * ∑ i ∈ s, μ i ^ 2 / v i := by
  have e1 : ∑ i ∈ s, (μ i / v i) * μ i = ∑ i ∈ s, μ i ^ 2 / v i := by
    refine sum_congr rfl fun i _ => ?_
    ring
  have e2 : ∑ i ∈ s, (μ i / v i) ^ 2 * v i = ∑ i ∈ s, μ i ^ 2 / v i := by
    refine sum_congr rfl fun i hi => ?_
    have := (hv i hi).ne'
    field_simp
  rw [e1, e2]
  ring

/-- D3. Volatility-management gain: the factor `E[σ²]·E[1/σ²]` is at least one. -/
theorem vol_managed_gain (s : Finset ι) (v : ι → ℝ) (hv : ∀ i ∈ s, 0 < v i) :
    ((s.card : ℝ)) ^ 2 ≤ (∑ i ∈ s, v i) * ∑ i ∈ s, 1 / v i := by
  have key := sharpe_budget s (fun _ => (1 : ℝ)) (fun _ => (1 : ℝ)) v hv
  have e1 : ∑ i ∈ s, (fun _ => (1 : ℝ)) i * (fun _ => (1 : ℝ)) i = (s.card : ℝ) := by simp
  have e2 : ∑ i ∈ s, (fun _ => (1 : ℝ)) i ^ 2 * v i = ∑ i ∈ s, v i := by simp
  have e3 : ∑ i ∈ s, (fun _ => (1 : ℝ)) i ^ 2 / v i = ∑ i ∈ s, 1 / v i := by simp
  rw [e1, e2, e3] at key
  exact key

/-- D4. The counterweight. If the mean scales with the variance (risk compensation), flat weights
already attain the budget, so volatility management has nothing to gain. The covariance is the scalar. -/
theorem risk_compensated_flat_optimal (s : Finset ι) (v : ι → ℝ) (a : ℝ) (hv : ∀ i ∈ s, 0 < v i) :
    (∑ i ∈ s, a * v i) ^ 2 = (∑ i ∈ s, v i) * ∑ i ∈ s, (a * v i) ^ 2 / v i := by
  have e : ∑ i ∈ s, (a * v i) ^ 2 / v i = a ^ 2 * ∑ i ∈ s, v i := by
    rw [mul_sum]
    refine sum_congr rfl fun i hi => ?_
    have := (hv i hi).ne'
    field_simp
  rw [e, ← mul_sum]
  ring

/-! ### Part E — hedging an event -/

lemma hedge_expand (s : Finset ι) (x m : ι → ℝ) (β : ℝ) :
    ∑ i ∈ s, (x i - β * m i) ^ 2
      = ∑ i ∈ s, x i ^ 2 - 2 * β * (∑ i ∈ s, x i * m i) + β ^ 2 * ∑ i ∈ s, m i ^ 2 := by
  have : ∀ i ∈ s, (x i - β * m i) ^ 2 = x i ^ 2 - 2 * β * (x i * m i) + β ^ 2 * m i ^ 2 := by
    intro i _; ring
  rw [sum_congr rfl this, sum_add_distrib, sum_sub_distrib, ← mul_sum, ← mul_sum]

/-- E1. The least-squares identity behind any market hedge. -/
theorem hedge_identity (s : Finset ι) (x m : ι → ℝ) (hM : 0 < ∑ i ∈ s, m i ^ 2) :
    ∑ i ∈ s, (x i - (∑ j ∈ s, x j * m j) / (∑ j ∈ s, m j ^ 2) * m i) ^ 2
      = ∑ i ∈ s, x i ^ 2 - (∑ j ∈ s, x j * m j) ^ 2 / ∑ j ∈ s, m j ^ 2 := by
  rw [hedge_expand]
  have hne := hM.ne'
  field_simp
  ring

/-- E2. No hedge ratio does better. -/
theorem hedge_optimal (s : Finset ι) (x m : ι → ℝ) (β : ℝ) (hM : 0 < ∑ i ∈ s, m i ^ 2) :
    ∑ i ∈ s, x i ^ 2 - (∑ j ∈ s, x j * m j) ^ 2 / ∑ j ∈ s, m j ^ 2 ≤ ∑ i ∈ s, (x i - β * m i) ^ 2 := by
  rw [hedge_expand]
  have hne := hM.ne'
  have key : β ^ 2 * (∑ j ∈ s, m j ^ 2) - 2 * β * (∑ j ∈ s, x j * m j)
      + (∑ j ∈ s, x j * m j) ^ 2 / ∑ j ∈ s, m j ^ 2
      = (β * (∑ j ∈ s, m j ^ 2) - ∑ j ∈ s, x j * m j) ^ 2 / ∑ j ∈ s, m j ^ 2 := by
    field_simp
    ring
  have h0 : 0 ≤ (β * (∑ j ∈ s, m j ^ 2) - ∑ j ∈ s, x j * m j) ^ 2 / ∑ j ∈ s, m j ^ 2 :=
    div_nonneg (sq_nonneg _) hM.le
  rw [← key] at h0
  linarith

/-! ### Part F — the threshold-cost law -/

/-- Information rate of a threshold book at level `k`: event rate `∝ k^(-β)` times squared net mean
`(a·k - c)²`, with `a` the reversal per unit threshold and `c` the cost. Take `β = α` when bet variance is
flat in `k`, and `β = α + 2` when bet standard deviation scales with `k`. -/
def infoRate (β a c k : ℝ) : ℝ := k ^ (-β) * (a * k - c) ^ 2

/-- The information-optimal threshold. -/
def kStar (β a c : ℝ) : ℝ := β * c / (a * (β - 2))

/-- F1. For `β > 2` the rate is globally maximised at `kStar` over all thresholds with non-negative net mean. -/
theorem threshold_optimal {β a c k : ℝ} (hβ : 2 < β) (ha : 0 < a) (hc : 0 < c) (hk : c / a ≤ k) :
    infoRate β a c k ≤ infoRate β a c (kStar β a c) := by
  have hβ0 : 0 < β := by linarith
  have hb2 : 0 < β - 2 := by linarith
  have hκ : 0 < kStar β a c := by unfold kStar; positivity
  have hk0 : 0 < k := lt_of_lt_of_le (div_pos hc ha) hk
  set κ := kStar β a c with hκdef
  set t := k / κ with ht
  have ht0 : 0 < t := div_pos hk0 hκ
  have hkt : k = κ * t := by rw [ht]; field_simp
  have haκ : a * κ = β * c / (β - 2) := by
    rw [hκdef]; unfold kStar; field_simp
  set U := a * κ - c with hU
  have hUv : U = 2 * c / (β - 2) := by
    rw [hU, haκ]; field_simp; ring
  have hUpos : 0 < U := by rw [hUv]; positivity
  set w := 1 + β / 2 * (t - 1) with hw
  have hu : a * k - c = U * w := by
    rw [hkt, hUv, hw]
    have : a * (κ * t) = (β * c / (β - 2)) * t := by rw [← haκ]; ring
    rw [this]; field_simp; ring
  have hu0 : 0 ≤ a * k - c := by
    have := (div_le_iff₀ ha).1 hk
    nlinarith
  have hw0 : 0 ≤ w := by
    by_contra hneg
    push_neg at hneg
    have : U * w < 0 := mul_neg_of_pos_of_neg hUpos hneg
    linarith [hu ▸ hu0]
  have hbern : w ≤ t ^ (β / 2) := by
    have h := one_add_mul_self_le_rpow_one_add (s := t - 1) (by linarith) (p := β / 2) (by linarith)
    simpa [hw] using h
  have hsq : w ^ 2 ≤ t ^ β := by
    have h2 : w ^ 2 ≤ (t ^ (β / 2)) ^ 2 := pow_le_pow_left₀ hw0 hbern 2
    have e : (t ^ (β / 2)) ^ 2 = t ^ β := by
      rw [← Real.rpow_natCast, ← Real.rpow_mul ht0.le]
      congr 1
      push_cast
      ring
    rwa [e] at h2
  have htβ : 0 < t ^ β := Real.rpow_pos_of_pos ht0 β
  have hκβ : 0 < κ ^ (-β) := Real.rpow_pos_of_pos hκ _
  have hsplit : k ^ (-β) = κ ^ (-β) * (t ^ β)⁻¹ := by
    rw [hkt, Real.mul_rpow hκ.le ht0.le, Real.rpow_neg ht0.le]
  unfold infoRate
  rw [hu, hsplit]
  have hfrac : (t ^ β)⁻¹ * w ^ 2 ≤ 1 := by
    rw [inv_mul_le_iff₀ htβ]
    linarith
  calc κ ^ (-β) * (t ^ β)⁻¹ * (U * w) ^ 2
      = κ ^ (-β) * U ^ 2 * ((t ^ β)⁻¹ * w ^ 2) := by ring
    _ ≤ κ ^ (-β) * U ^ 2 * 1 := mul_le_mul_of_nonneg_left hfrac (by positivity)
    _ = κ ^ (-β) * (a * κ - c) ^ 2 := by rw [hU]; ring

/-- F2. `kStar` is proportional to the cost and inverse to the reversal. -/
theorem kStar_scales {β a c l : ℝ} (hl : l ≠ 0) (ha : a ≠ 0) (hβ : β ≠ 2) :
    kStar β (l * a) (l * c) = kStar β a c := by
  unfold kStar
  have hb : β - 2 ≠ 0 := sub_ne_zero.2 hβ
  field_simp

/-- F3. For `0 < β ≤ 2` there is no interior optimum: the rate never falls as the threshold rises. -/
theorem threshold_no_interior {β a c k₁ k₂ : ℝ} (hβ0 : 0 < β) (hβ : β ≤ 2) (ha : 0 < a) (hc : 0 ≤ c)
    (hk₁0 : 0 < k₁) (hk₁ : c / a ≤ k₁) (h12 : k₁ ≤ k₂) :
    infoRate β a c k₁ ≤ infoRate β a c k₂ := by
  have _ := hβ0
  have hk₂ : 0 < k₂ := lt_of_lt_of_le hk₁0 h12
  set t := k₂ / k₁ with ht
  have ht1 : 1 ≤ t := (one_le_div hk₁0).2 h12
  have ht0 : 0 < t := by linarith
  have hk2t : k₂ = k₁ * t := by rw [ht]; field_simp
  have hu₁ : 0 ≤ a * k₁ - c := by
    have := (div_le_iff₀ ha).1 hk₁
    nlinarith
  have hu₂ : t * (a * k₁ - c) ≤ a * k₂ - c := by
    rw [hk2t]; nlinarith
  have hsq : (t * (a * k₁ - c)) ^ 2 ≤ (a * k₂ - c) ^ 2 :=
    pow_le_pow_left₀ (mul_nonneg ht0.le hu₁) hu₂ 2
  have hk₁β : 0 < k₁ ^ (-β) := Real.rpow_pos_of_pos hk₁0 _
  have hsplit : k₂ ^ (-β) = k₁ ^ (-β) * t ^ (-β) := by
    rw [hk2t, Real.mul_rpow hk₁0.le ht0.le]
  have hgain : 1 ≤ t ^ (-β) * t ^ 2 := by
    have e : t ^ (-β) * t ^ 2 = t ^ (2 - β) := by
      rw [show (2 : ℝ) - β = -β + 2 by ring, Real.rpow_add ht0, Real.rpow_two]
    rw [e]
    exact Real.one_le_rpow ht1 (by linarith)
  unfold infoRate
  rw [hsplit]
  have hbase : 0 ≤ k₁ ^ (-β) * (a * k₁ - c) ^ 2 := by positivity
  calc k₁ ^ (-β) * (a * k₁ - c) ^ 2
      = k₁ ^ (-β) * (a * k₁ - c) ^ 2 * 1 := by ring
    _ ≤ k₁ ^ (-β) * (a * k₁ - c) ^ 2 * (t ^ (-β) * t ^ 2) :=
        mul_le_mul_of_nonneg_left hgain hbase
    _ = k₁ ^ (-β) * t ^ (-β) * (t * (a * k₁ - c)) ^ 2 := by ring
    _ ≤ k₁ ^ (-β) * t ^ (-β) * (a * k₂ - c) ^ 2 :=
        mul_le_mul_of_nonneg_left hsq (by positivity)

end

end PerpChief.Events
