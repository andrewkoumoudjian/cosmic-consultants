/-
PORTED 2026-11-12 from owner prior work: power-law excursion tails / trailing floor
Source: andrewkoumoudjian/perps-strategy @ 0f34759, lanes/chief/lean/PerpChief/LeverageLaw.lean (toolchain v4.15.0).
Port changes ONLY: module path/import remap to Analog.Prior.* (+ Mathlib API renames if listed in docs/research/06). Namespaces, statements, proofs otherwise verbatim. Original file is frozen upstream; do not edit semantics here.
-/
/-
WS3 — LEVERAGE LAWS. FROZEN STATEMENTS (chief scientist). Fill in the proof holes; add helper lemmas.
Part I: gross vs knockout under a power-law excursion tail. Part II: the trailing-floor ratchet.
-/
import Mathlib.Analysis.SpecialFunctions.Pow.Real
import Mathlib.Analysis.SpecialFunctions.Log.Basic
import Mathlib.Analysis.Convex.SpecificFunctions.Basic
import Mathlib.MeasureTheory.Measure.MeasureSpace
import Mathlib.Tactic

open Finset MeasureTheory
open scoped ENNReal

namespace PerpChief.Leverage

noncomputable section

/-! ### Part I — tail-exponent law -/

/-- Edge per unit equity at gross G: linear edge minus the knockout tax. -/
def f (a b α G : ℝ) : ℝ := a * G - b * G ^ α

def Gstar (a b α : ℝ) : ℝ := (a / (α * b)) ^ (1 / (α - 1))
def Gmax (a b α : ℝ) : ℝ := (a / b) ^ (1 / (α - 1))

theorem ws3_rpow_inv_mul {x : ℝ} (hx : 0 ≤ x) {α : ℝ} (hα : 1 < α) :
    (x ^ (1 / (α - 1))) ^ (α - 1) = x := by
  have hne : (α - 1) ≠ 0 := sub_ne_zero.mpr (ne_of_gt hα)
  rw [← Real.rpow_mul hx, one_div_mul_cancel hne, Real.rpow_one]

theorem ws3_rpow_mul_inv {x : ℝ} (hx : 0 ≤ x) {α : ℝ} (hα : 1 < α) :
    (x ^ (α - 1)) ^ (1 / (α - 1)) = x := by
  have hne : (α - 1) ≠ 0 := sub_ne_zero.mpr (ne_of_gt hα)
  rw [← Real.rpow_mul hx, mul_one_div_cancel hne, Real.rpow_one]

theorem ws3_pow_alpha {x α : ℝ} (hx : 0 < x) : x ^ α = x ^ (α - 1) * x := by
  conv_lhs => rw [show α = (α - 1) + 1 by ring]
  rw [Real.rpow_add hx, Real.rpow_one]

theorem ws3_gstar_pow {a b α : ℝ} (ha : 0 < a) (hb : 0 < b) (hα : 1 < α) :
    (Gstar a b α) ^ (α - 1) = a / (α * b) := by
  have hbase : 0 ≤ a / (α * b) := by positivity
  unfold Gstar
  exact ws3_rpow_inv_mul hbase hα

theorem ws3_gmax_pow {a b α : ℝ} (ha : 0 < a) (hb : 0 < b) (hα : 1 < α) :
    (Gmax a b α) ^ (α - 1) = a / b := by
  have hbase : 0 ≤ a / b := by positivity
  unfold Gmax
  exact ws3_rpow_inv_mul hbase hα

variable {a b α G : ℝ}

/-- L1. -/
theorem gstar_pos (ha : 0 < a) (hb : 0 < b) (hα : 1 < α) : 0 < Gstar a b α := by
  unfold Gstar
  apply Real.rpow_pos_of_pos
  positivity

/-- L2. Global optimum over all positive gross. -/
theorem gstar_isMax (ha : 0 < a) (hb : 0 < b) (hα : 1 < α) (hG : 0 < G) :
    f a b α G ≤ f a b α (Gstar a b α) := by
  set g := Gstar a b α with hgdef
  have hgpos : 0 < g := gstar_pos ha hb hα
  have hαpos : (0:ℝ) < α := by linarith
  have hαne : α ≠ 0 := ne_of_gt hαpos
  have hpow : g ^ (α - 1) = a / (α * b) := ws3_gstar_pow ha hb hα
  have hgα : g ^ α = g ^ (α - 1) * g := ws3_pow_alpha hgpos
  have hbP : b * g ^ α = a * g / α := by
    rw [hgα, hpow]
    field_simp
  have hag : a * g = α * (b * g ^ α) := by
    rw [hbP]
    field_simp
  have hbern0 := one_add_mul_self_le_rpow_one_add (s := G / g - 1) (p := α)
    (by linarith [div_pos hG hgpos]) (by linarith)
  have hbase : (1:ℝ) + (G / g - 1) = G / g := by ring
  rw [hbase, Real.div_rpow hG.le hgpos.le α] at hbern0
  have hPpos : 0 < g ^ α := Real.rpow_pos_of_pos hgpos α
  have key : a * G - (α - 1) * (b * g ^ α) ≤ b * G ^ α := by
    have hmul := mul_le_mul_of_nonneg_left hbern0
      (show (0:ℝ) ≤ b * g ^ α by positivity)
    have eR : b * g ^ α * (G ^ α / g ^ α) = b * G ^ α := by
      field_simp
    have eL : b * g ^ α * (1 + α * (G / g - 1)) = a * G - (α - 1) * (b * g ^ α) := by
      rw [hgα, hpow]
      field_simp
      ring
    rw [eR, eL] at hmul
    exact hmul
  unfold f
  linarith [key, hag]

/-- L3. Value at the optimum: the tail exponent alone fixes the tax share (1/α of the linear edge). -/
theorem gstar_value (ha : 0 < a) (hb : 0 < b) (hα : 1 < α) :
    f a b α (Gstar a b α) = a * Gstar a b α * (1 - 1 / α) := by
  have hgpos : 0 < Gstar a b α := gstar_pos ha hb hα
  have hαpos : 0 < α := by linarith
  have hpow := ws3_gstar_pow ha hb hα
  have hαeq : (Gstar a b α) ^ α = (Gstar a b α) ^ (α - 1) * Gstar a b α :=
    ws3_pow_alpha hgpos
  have hkey : b * (Gstar a b α) ^ α = a * Gstar a b α / α := by
    rw [hαeq, hpow]
    field_simp
  have hrw : a * Gstar a b α * (1 - 1 / α) = a * Gstar a b α - b * (Gstar a b α) ^ α := by
    rw [hkey]
    field_simp
  unfold f
  exact hrw.symm

/-- L4. The ceiling: edge is positive exactly below Gmax. -/
theorem f_pos_iff (ha : 0 < a) (hb : 0 < b) (hα : 1 < α) (hG : 0 < G) :
    0 < f a b α G ↔ G < Gmax a b α := by
  have hα1 : (0:ℝ) < α - 1 := by linarith
  have hfact : f a b α G = G * (a - b * G ^ (α - 1)) := by
    unfold f
    rw [ws3_pow_alpha hG]
    ring
  constructor
  · intro hf
    rw [hfact] at hf
    have hpos : 0 < a - b * G ^ (α - 1) := by
      by_contra h
      push_neg at h
      have : G * (a - b * G ^ (α - 1)) ≤ 0 :=
        mul_nonpos_of_nonneg_of_nonpos hG.le h
      linarith
    have hlt : G ^ (α - 1) < a / b := by
      rw [lt_div_iff₀ hb]
      linarith [hpos]
    have hlt2 : (G ^ (α - 1)) ^ (1 / (α - 1)) < (a / b) ^ (1 / (α - 1)) :=
      (Real.rpow_lt_rpow_iff (Real.rpow_nonneg hG.le _) (div_nonneg ha.le hb.le)
        (one_div_pos.mpr hα1)).mpr hlt
    rw [ws3_rpow_mul_inv hG.le hα] at hlt2
    exact hlt2
  · intro hGlt
    rw [hfact]
    apply mul_pos hG
    have hlt : G ^ (α - 1) < a / b := by
      have h1 : G ^ (α - 1) < (Gmax a b α) ^ (α - 1) :=
        Real.rpow_lt_rpow hG.le hGlt hα1
      rw [ws3_gmax_pow ha hb hα] at h1
      exact h1
    rw [lt_div_iff₀ hb] at hlt
    linarith [hlt]

/-- L5. Universal over-leverage multiple: depends on α ONLY (≈1.71 at α=3.1). -/
theorem gmax_ratio (ha : 0 < a) (hb : 0 < b) (hα : 1 < α) :
    Gmax a b α / Gstar a b α = α ^ (1 / (α - 1)) := by
  have h1 : (0:ℝ) ≤ a / b := by positivity
  have h2 : (0:ℝ) ≤ a / (α * b) := by positivity
  have hquot : (a / b) / (a / (α * b)) = α := by
    field_simp
  unfold Gmax Gstar
  rw [← Real.div_rpow h1 h2, hquot]

/-- L6. Regime damping: a b-spread of s moves G* only by s^(1/(α−1)). Observed s=3.7, α=3.1 ⇒ ≈1.86. -/
theorem gstar_sensitivity {b₁ b₂ : ℝ} (ha : 0 < a) (hb₁ : 0 < b₁) (hb₂ : 0 < b₂) (hα : 1 < α) :
    Gstar a b₁ α / Gstar a b₂ α = (b₂ / b₁) ^ (1 / (α - 1)) := by
  have h1 : (0:ℝ) ≤ a / (α * b₁) := by positivity
  have h2 : (0:ℝ) ≤ a / (α * b₂) := by positivity
  have hquot : (a / (α * b₁)) / (a / (α * b₂)) = b₂ / b₁ := by
    field_simp
  unfold Gstar
  rw [← Real.div_rpow h1 h2, hquot]

/-- L7. Maximin: sizing for the worst regime b₂ beats any gross's worst case, in every milder regime. -/
theorem maximin {b₂ : ℝ} (ha : 0 < a) (hb : b ≤ b₂) (hb₂ : 0 < b₂) (hα : 1 < α) (hG : 0 < G) :
    f a b₂ α G ≤ f a b α (Gstar a b₂ α) := by
  have h1 : f a b₂ α G ≤ f a b₂ α (Gstar a b₂ α) := gstar_isMax ha hb₂ hα hG
  have hgpos : 0 < Gstar a b₂ α := gstar_pos ha hb₂ hα
  have hPpos : 0 < (Gstar a b₂ α) ^ α := Real.rpow_pos_of_pos hgpos α
  have hmul : b * (Gstar a b₂ α) ^ α ≤ b₂ * (Gstar a b₂ α) ^ α :=
    mul_le_mul_of_nonneg_right hb hPpos.le
  have h2 : f a b₂ α (Gstar a b₂ α) ≤ f a b α (Gstar a b₂ α) := by
    unfold f
    linarith [hmul]
  linarith [h1, h2]

/-- L8. Exact accounting behind the law: capped hits cost c of equity; forgone exits cost G·P·(x̄+φ). -/
theorem equity_edge_identity {μ' P xbar φ c : ℝ} (hG : 0 < G) (hc : 0 < c) :
    G * (μ' - P * (xbar + c / G + φ)) = G * μ' - P * c - G * P * (xbar + φ) := by
  have hGne : G ≠ 0 := ne_of_gt hG
  field_simp
  ring

/-- L9. The extra forgone-winner term only lowers the ceiling. -/
theorem ceiling_two_power {b2 : ℝ} (ha : 0 < a) (hb : 0 < b) (hα : 1 < α) (hb2 : 0 ≤ b2)
    (hG : Gmax a b α ≤ G) :
    a * G - b * G ^ α - b2 * G ^ (α + 1) ≤ 0 := by
  have hgmaxpos : 0 < Gmax a b α := by
    unfold Gmax
    apply Real.rpow_pos_of_pos
    positivity
  have hGpos : 0 < G := lt_of_lt_of_le hgmaxpos hG
  have hf : f a b α G ≤ 0 := by
    apply le_of_not_gt
    intro hfpos
    have hlt : G < Gmax a b α := (f_pos_iff ha hb hα hGpos).mp hfpos
    linarith
  have hterm : (0:ℝ) ≤ b2 * G ^ (α + 1) :=
    mul_nonneg hb2 (Real.rpow_nonneg hGpos.le _)
  unfold f at hf
  linarith [hf, hterm]

/-- L10. α=1 kills the law: no interior optimum, sign of (a−b) decides everything. -/
theorem alpha_one_linear (hG : 0 < G) : f a b 1 G = (a - b) * G := by
  unfold f
  rw [Real.rpow_one]
  ring

/-! ### Part II — trailing-floor ratchet -/

structure CState where
  E : ℝ
  H : ℝ

def cushion (δ : ℝ) (s : CState) : ℝ := s.E - (1 - δ) * s.H

/-- Book notional is k × cushion; r is the book's return per unit notional this step. -/
def cstep (δ k r : ℝ) (s : CState) : CState :=
  let E' := s.E + k * cushion δ s * r
  ⟨E', max s.H E'⟩

def run (δ k E0 : ℝ) (r : ℕ → ℝ) : ℕ → CState
  | 0 => ⟨E0, E0⟩
  | n + 1 => cstep δ k (r n) (run δ k E0 r n)

variable {δ k E0 : ℝ} {r : ℕ → ℝ}

theorem ws3_cstate_inv (hE : 0 < E0) (hδ0 : 0 < δ) (hδ1 : δ < 1) (hk : 0 < k) :
    ∀ n : ℕ, (∀ t < n, -1 / k < r t) →
      0 < (run δ k E0 r n).E ∧ (run δ k E0 r n).E ≤ (run δ k E0 r n).H ∧
      0 < (run δ k E0 r n).H ∧ 0 < cushion δ (run δ k E0 r n) ∧
      cushion δ (run δ k E0 r n) ≤ δ * (run δ k E0 r n).E := by
  intro n
  induction n with
  | zero =>
      intro _
      have hc0 : cushion δ (run δ k E0 r 0) = δ * E0 := by
        show E0 - (1 - δ) * E0 = δ * E0
        ring
      refine ⟨hE, le_rfl, hE, ?_, ?_⟩
      · rw [hc0]; positivity
      · rw [hc0]
        exact le_rfl
  | succ n ih =>
      intro hr
      have hr_n : ∀ t < n, -1 / k < r t := fun t ht => hr t (Nat.lt_succ_of_lt ht)
      obtain ⟨hEpos, hEH, hHpos, hcpos, hcle⟩ := ih hr_n
      have hrstep : -1 / k < r n := hr n (Nat.lt_succ_self n)
      have hkr : -1 < k * r n := by
        have h := mul_lt_mul_of_pos_right hrstep hk
        have e : (-1 / k) * k = (-1 : ℝ) := by field_simp
        rw [e] at h
        linarith [h]
      have h1k : (0:ℝ) < 1 + k * r n := by linarith
      set s := run δ k E0 r n with hs
      set E' := s.E + k * cushion δ s * r n with hE'def
      have hsucc : run δ k E0 r (n + 1) = ⟨E', max s.H E'⟩ := rfl
      have hkc : - cushion δ s < k * cushion δ s * r n := by
        have h := mul_lt_mul_of_pos_left hkr hcpos
        have e1 : cushion δ s * (-1) = - cushion δ s := by ring
        have e2 : cushion δ s * (k * r n) = k * cushion δ s * r n := by ring
        rwa [e1, e2] at h
      have hcdef : cushion δ s = s.E - (1 - δ) * s.H := rfl
      have hE'gt : (1 - δ) * s.H < E' := by
        rw [hE'def]
        linarith [hkc, hcdef]
      have hE'pos : 0 < E' :=
        lt_trans (mul_pos (by linarith : (0:ℝ) < 1 - δ) hHpos) hE'gt
      have hE'H' : E' ≤ max s.H E' := le_max_right s.H E'
      have hH'pos : 0 < max s.H E' := lt_of_lt_of_le hHpos (le_max_left s.H E')
      have hcle' : E' - (1 - δ) * max s.H E' ≤ δ * E' := by
        have hmul : (1 - δ) * E' ≤ (1 - δ) * max s.H E' :=
          mul_le_mul_of_nonneg_left hE'H' (by linarith : (0:ℝ) ≤ 1 - δ)
        linarith [hmul]
      rw [hsucc]
      refine ⟨hE'pos, hE'H', hH'pos, ?_, ?_⟩
      · show 0 < E' - (1 - δ) * max s.H E'
        rcases le_total E' s.H with hcase | hcase
        · have hmax : max s.H E' = s.H := max_eq_left hcase
          rw [hmax]
          have heq : E' - (1 - δ) * s.H = cushion δ s * (1 + k * r n) := by
            rw [hE'def, hcdef]; ring
          rw [heq]
          positivity
        · have hmax : max s.H E' = E' := max_eq_right hcase
          rw [hmax]
          have heq : E' - (1 - δ) * E' = δ * E' := by ring
          rw [heq]
          positivity
      · show E' - (1 - δ) * max s.H E' ≤ δ * E'
        exact hcle'

theorem ws3_no_new_high (hE : 0 < E0) (hδ0 : 0 < δ) (hδ1 : δ < 1) (hk : 0 < k) :
    ∀ T : ℕ, (∀ t < T, -1 / k < r t) →
      (∀ t < T, (run δ k E0 r (t + 1)).E ≤ (run δ k E0 r t).H) →
      (run δ k E0 r T).H = E0 ∧
      cushion δ (run δ k E0 r T) = δ * E0 * ∏ t ∈ range T, (1 + k * r t) := by
  intro T
  induction T with
  | zero =>
      intro _ _
      constructor
      · rfl
      · show E0 - (1 - δ) * E0 = δ * E0 * ∏ t ∈ range 0, (1 + k * r t)
        simp
        ring
  | succ n ih =>
      intro hr hnh
      have hr_n : ∀ t < n, -1 / k < r t := fun t ht => hr t (Nat.lt_succ_of_lt ht)
      have hnh_n : ∀ t < n, (run δ k E0 r (t + 1)).E ≤ (run δ k E0 r t).H :=
        fun t ht => hnh t (Nat.lt_succ_of_lt ht)
      obtain ⟨hHn, hcn⟩ := ih hr_n hnh_n
      have hstepH : (run δ k E0 r (n + 1)).H
          = max (run δ k E0 r n).H (run δ k E0 r (n + 1)).E := rfl
      have hHsucc : (run δ k E0 r (n + 1)).H = E0 := by
        rw [hstepH, max_eq_left (hnh n (Nat.lt_succ_self n)), hHn]
      constructor
      · exact hHsucc
      · have hstepC : cushion δ (run δ k E0 r (n + 1))
            = cushion δ (run δ k E0 r n) * (1 + k * r n) := by
          have hH : (run δ k E0 r (n + 1)).H = (run δ k E0 r n).H := by
            rw [hHsucc, hHn]
          show (run δ k E0 r (n + 1)).E - (1 - δ) * (run δ k E0 r (n + 1)).H
            = cushion δ (run δ k E0 r n) * (1 + k * r n)
          rw [hH]
          show (run δ k E0 r n).E + k * cushion δ (run δ k E0 r n) * r n
              - (1 - δ) * (run δ k E0 r n).H
            = cushion δ (run δ k E0 r n) * (1 + k * r n)
          have hcdef : cushion δ (run δ k E0 r n)
              = (run δ k E0 r n).E - (1 - δ) * (run δ k E0 r n).H := rfl
          rw [hcdef]
          ring
        rw [hstepC, hcn, Finset.prod_range_succ]
        ring

/-- L11. No breach through n unless a step gap ≤ −1/k occurred. Every strategy, every path. -/
theorem cushion_pos_upto (hE : 0 < E0) (hδ0 : 0 < δ) (hδ1 : δ < 1) (hk : 0 < k) (n : ℕ)
    (hr : ∀ t < n, -1 / k < r t) : 0 < cushion δ (run δ k E0 r n) := by
  exact (ws3_cstate_inv hE hδ0 hδ1 hk n hr).2.2.2.1

/-- L12. Effective gross never exceeds k·δ. -/
theorem gross_bound (hE : 0 < E0) (hδ0 : 0 < δ) (hδ1 : δ < 1) (hk : 0 < k) (n : ℕ)
    (hr : ∀ t < n, -1 / k < r t) :
    k * cushion δ (run δ k E0 r n) / (run δ k E0 r n).E ≤ k * δ := by
  obtain ⟨hEpos, -, -, -, hcle⟩ := ws3_cstate_inv hE hδ0 hδ1 hk n hr
  rw [div_le_iff₀ hEpos]
  have hmul : k * cushion δ (run δ k E0 r n) ≤ k * (δ * (run δ k E0 r n).E) :=
    mul_le_mul_of_nonneg_left hcle hk.le
  linarith [hmul]

/-- L13. Tightness: a −1/k gap from the high-water mark exhausts the cushion exactly. -/
theorem gap_tight (hE : 0 < E0) (hδ0 : 0 < δ) (hδ1 : δ < 1) (hk : 0 < k) (hr : r 0 = -1 / k) :
    cushion δ (run δ k E0 r 1) = 0 := by
  have hkne : k ≠ 0 := ne_of_gt hk
  have hE' : (run δ k E0 r 1).E = (1 - δ) * E0 := by
    show E0 + k * (E0 - (1 - δ) * E0) * r 0 = (1 - δ) * E0
    rw [hr]
    field_simp
    ring
  have hH : (run δ k E0 r 1).H = E0 := by
    show max E0 (run δ k E0 r 1).E = E0
    rw [hE']
    apply max_eq_left
    have : (1 - δ) * E0 ≤ E0 := by
      have h1 : (1 - δ) * E0 ≤ 1 * E0 :=
        mul_le_mul_of_nonneg_right (by linarith : (1 - δ) ≤ 1) hE.le
      linarith [h1]
    exact this
  show (run δ k E0 r 1).E - (1 - δ) * (run δ k E0 r 1).H = 0
  rw [hE', hH]
  ring

/-- L14. Pathwise log-cushion identity between new highs. -/
theorem log_cushion_no_new_high (hE : 0 < E0) (hδ0 : 0 < δ) (hδ1 : δ < 1) (hk : 0 < k) (T : ℕ)
    (hr : ∀ t < T, -1 / k < r t)
    (hnh : ∀ t < T, (run δ k E0 r (t + 1)).E ≤ (run δ k E0 r t).H) :
    Real.log (cushion δ (run δ k E0 r T))
      = Real.log (δ * E0) + ∑ t ∈ range T, Real.log (1 + k * r t) := by
  obtain ⟨-, hcush⟩ := ws3_no_new_high hE hδ0 hδ1 hk T hr hnh
  have hδE : (0:ℝ) < δ * E0 := by positivity
  have hprodpos : (0:ℝ) < ∏ t ∈ range T, (1 + k * r t) := by
    apply Finset.prod_pos
    intro t ht
    have htT : t < T := Finset.mem_range.mp ht
    have h := hr t htT
    have hkr : -1 < k * r t := by
      have hh := mul_lt_mul_of_pos_right h hk
      have e : (-1 / k) * k = (-1 : ℝ) := by field_simp
      rw [e] at hh
      linarith [hh]
    linarith
  rw [hcush, Real.log_mul hδE.ne' hprodpos.ne', Real.log_prod]
  intro t ht
  have htT : t < T := Finset.mem_range.mp ht
  have h := hr t htT
  have hkr : -1 < k * r t := by
    have hh := mul_lt_mul_of_pos_right h hk
    have e : (-1 / k) * k = (-1 : ℝ) := by field_simp
    rw [e] at hh
    linarith [hh]
  have : (0:ℝ) < 1 + k * r t := by linarith
  exact ne_of_gt this

/-- L15. Union bound on the only way to breach. The per-step gap probability is where the measured
tail exponent enters; everything else above is pathwise. -/
theorem breach_le_union {Ω : Type*} [MeasurableSpace Ω] {μ : Measure Ω} {R : ℕ → Ω → ℝ}
    {p : ℝ≥0∞} (hE : 0 < E0) (hδ0 : 0 < δ) (hδ1 : δ < 1) (hk : 0 < k) (T : ℕ)
    (hp : ∀ t < T, μ {ω | R t ω ≤ -1 / k} ≤ p) :
    μ {ω | ¬ 0 < cushion δ (run δ k E0 (fun t => R t ω) T)} ≤ T * p := by
  have hsub : {ω | ¬ 0 < cushion δ (run δ k E0 (fun t => R t ω) T)}
      ⊆ ⋃ t ∈ range T, {ω | R t ω ≤ -1 / k} := by
    intro ω hω
    by_cases hall : ∀ t < T, -1 / k < R t ω
    · exfalso
      apply hω
      exact cushion_pos_upto hE hδ0 hδ1 hk T hall
    · push_neg at hall
      obtain ⟨t, ht, hle⟩ := hall
      exact Set.mem_biUnion (Finset.mem_range.mpr ht) hle
  calc μ {ω | ¬ 0 < cushion δ (run δ k E0 (fun t => R t ω) T)}
      ≤ μ (⋃ t ∈ range T, {ω | R t ω ≤ -1 / k}) := measure_mono hsub
    _ ≤ ∑ t ∈ range T, μ {ω | R t ω ≤ -1 / k} := measure_biUnion_finset_le _ _
    _ ≤ ∑ _t ∈ range T, p :=
        Finset.sum_le_sum fun t ht => hp t (Finset.mem_range.mp ht)
    _ = T * p := by simp [Finset.sum_const, Finset.card_range, nsmul_eq_mul]

/-! ### Dual floor: trailing AND daily limit -/

structure DState where
  E : ℝ
  H : ℝ
  Fd : ℝ

def dmargin (δ : ℝ) (s : DState) : ℝ := min (s.E - (1 - δ) * s.H) (s.E - s.Fd)

def dstep (δ k D r : ℝ) (reset : Bool) (s : DState) : DState :=
  let E' := s.E + k * dmargin δ s * r
  ⟨E', max s.H E', if reset then E' - D else s.Fd⟩

def drun (δ k D E0 : ℝ) (r : ℕ → ℝ) (reset : ℕ → Bool) : ℕ → DState
  | 0 => ⟨E0, E0, E0 - D⟩
  | n + 1 => dstep δ k D (r n) (reset n) (drun δ k D E0 r reset n)

theorem ws3_dstate_inv {D : ℝ} {reset : ℕ → Bool} (hE : 0 < E0) (hδ0 : 0 < δ) (hδ1 : δ < 1)
    (hk : 0 < k) (hD : 0 < D) :
    ∀ n : ℕ, (∀ t < n, -1 / k < r t) →
      let s := drun δ k D E0 r reset n
      0 < s.E ∧ s.E ≤ s.H ∧ 0 < s.H ∧ 0 < s.E - (1 - δ) * s.H ∧ 0 < s.E - s.Fd := by
  intro n
  induction n with
  | zero =>
      intro _
      refine ⟨hE, le_rfl, hE, ?_, ?_⟩
      · show (0:ℝ) < E0 - (1 - δ) * E0
        have : E0 - (1 - δ) * E0 = δ * E0 := by ring
        rw [this]; positivity
      · show (0:ℝ) < E0 - (E0 - D)
        linarith
  | succ n ih =>
      intro hr
      have hr_n : ∀ t < n, -1 / k < r t := fun t ht => hr t (Nat.lt_succ_of_lt ht)
      obtain ⟨hEpos, hEH, hHpos, hm1, hm2⟩ := ih hr_n
      have hrstep : -1 / k < r n := hr n (Nat.lt_succ_self n)
      have hkr : -1 < k * r n := by
        have h := mul_lt_mul_of_pos_right hrstep hk
        have e : (-1 / k) * k = (-1 : ℝ) := by field_simp
        rw [e] at h
        linarith [h]
      set s := drun δ k D E0 r reset n with hs
      set m := dmargin δ s with hmdef
      have hmpos : 0 < m := by
        rw [hmdef]
        show 0 < min (s.E - (1 - δ) * s.H) (s.E - s.Fd)
        exact lt_min hm1 hm2
      have hm_le1 : m ≤ s.E - (1 - δ) * s.H := by
        rw [hmdef]; exact min_le_left _ _
      have hm_le2 : m ≤ s.E - s.Fd := by
        rw [hmdef]; exact min_le_right _ _
      set E' := s.E + k * m * r n with hE'def
      have hsucc : drun δ k D E0 r reset (n + 1)
          = ⟨E', max s.H E', if reset n then E' - D else s.Fd⟩ := rfl
      have hkm : -m < k * m * r n := by
        have h := mul_lt_mul_of_pos_left hkr hmpos
        have e1 : m * (-1) = -m := by ring
        have e2 : m * (k * r n) = k * m * r n := by ring
        rwa [e1, e2] at h
      have hE'gt : (1 - δ) * s.H < E' := by
        rw [hE'def]
        have hge : (1 - δ) * s.H ≤ s.E - m := by linarith [hm_le1]
        linarith [hkm, hge]
      have hE'pos : 0 < E' :=
        lt_trans (mul_pos (by linarith : (0:ℝ) < 1 - δ) hHpos) hE'gt
      have hE'H' : E' ≤ max s.H E' := le_max_right s.H E'
      have hH'pos : 0 < max s.H E' := lt_of_lt_of_le hHpos (le_max_left s.H E')
      rw [hsucc]
      refine ⟨hE'pos, hE'H', hH'pos, ?_, ?_⟩
      · show 0 < E' - (1 - δ) * max s.H E'
        rcases le_total E' s.H with hcase | hcase
        · have hmax : max s.H E' = s.H := max_eq_left hcase
          rw [hmax, hE'def]
          have hge : s.E - (1 - δ) * s.H - m < s.E + k * m * r n - (1 - δ) * s.H := by
            linarith [hkm]
          linarith [hm_le1, hge]
        · have hmax : max s.H E' = E' := max_eq_right hcase
          rw [hmax]
          have heq : E' - (1 - δ) * E' = δ * E' := by ring
          rw [heq]; positivity
      · show 0 < E' - (if reset n then E' - D else s.Fd)
        cases hres : reset n with
        | false =>
            rw [if_neg (by simp [hres]), hE'def]
            have hge : s.E - s.Fd - m < s.E + k * m * r n - s.Fd := by linarith [hkm]
            linarith [hm_le2, hge]
        | true =>
            rw [if_pos (by simp [hres])]
            linarith

/-- L16. Sizing on min(trailing cushion, daily cushion) protects both Frame B floors, with arbitrary
day boundaries. -/
theorem dual_floor_pos {D : ℝ} {reset : ℕ → Bool} (hE : 0 < E0) (hδ0 : 0 < δ) (hδ1 : δ < 1)
    (hk : 0 < k) (hD : 0 < D) (n : ℕ) (hr : ∀ t < n, -1 / k < r t) :
    let s := drun δ k D E0 r reset n
    0 < s.E - (1 - δ) * s.H ∧ 0 < s.E - s.Fd := by
  have h := ws3_dstate_inv (D := D) (reset := reset) hE hδ0 hδ1 hk hD n hr
  exact ⟨h.2.2.2.1, h.2.2.2.2⟩

/-- Frame B instance: gross cap 1.5× ⇔ k = 25 ⇒ the book-level gap limit is −4%. -/
theorem frameB_instance : (25 : ℝ) * (6 / 100) = 3 / 2 ∧ (-1 : ℝ) / 25 = -(4 / 100) := by
  constructor <;> norm_num

end

end PerpChief.Leverage
