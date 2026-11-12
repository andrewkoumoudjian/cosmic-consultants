/-
PORTED 2026-11-12 from owner prior work: pathwise ceiling bounds
Source: andrewkoumoudjian/perps-strategy @ 0f34759, lanes/chief/lean/PerpChief/Ceiling.lean (toolchain v4.15.0).
Port changes ONLY: module path/import remap to Analog.Prior.* (+ Mathlib API renames if listed in docs/research/06). Namespaces, statements, proofs otherwise verbatim. Original file is frozen upstream; do not edit semantics here.
-/
/-
WS7 — THE PATHWISE CEILING. FROZEN STATEMENTS (chief scientist). Fill in the proof holes; add helper lemmas.
Bridge finding: the ratchet never breaches without a gap, but volatility drag can starve the cushion to zero.
One inequality gives a leverage ceiling with no return law, and caps every fixed-fraction e-value by the
self-normalised t-statistic: to verify an edge at level α you need A²/B ≥ 4c·log(1/α), whatever the law.
-/
import Analog.Prior.LeverageLaw
import Mathlib.Analysis.Calculus.MeanValue
import Mathlib.Analysis.SpecialFunctions.Log.Deriv

open Finset

namespace PerpChief.Ceiling

noncomputable section

open PerpChief.Leverage

/-- Auxiliary derivative for the cubic Taylor bound. -/
lemma ws7_hasDerivAt_g {y : ℝ} (hy : -1 < y) :
    HasDerivAt (fun x : ℝ => x - x ^ 2 / 2 + x ^ 3 / 3 - Real.log (1 + x)) (y ^ 3 / (1 + y)) y := by
  have hne : (1 : ℝ) + y ≠ 0 := by linarith
  have hlog : HasDerivAt (fun x : ℝ => Real.log (1 + x)) ((1 + y)⁻¹) y := by
    have h1 : HasDerivAt (fun x : ℝ => 1 + x) 1 y := by
      simpa using (hasDerivAt_id y).const_add (1 : ℝ)
    have h2 := h1.log hne
    simpa using h2
  have hx2 : HasDerivAt (fun x : ℝ => x ^ 2 / 2) y y := by
    have h := (hasDerivAt_pow 2 y).div_const (2 : ℝ)
    convert h using 1
    norm_num
  have hx3 : HasDerivAt (fun x : ℝ => x ^ 3 / 3) (y ^ 2) y := by
    have h := (hasDerivAt_pow 3 y).div_const (3 : ℝ)
    convert h using 1
    norm_num
  have hpoly : HasDerivAt (fun x : ℝ => x - x ^ 2 / 2 + x ^ 3 / 3) (1 - y + y ^ 2) y :=
    ((hasDerivAt_id y).sub hx2).add hx3
  have h := hpoly.sub hlog
  convert h using 1
  field_simp
  ring

/-- Cubic Taylor bound for `log (1 + x)` on `(-1, ∞)`. -/
lemma ws7_log_le_cubic {x : ℝ} (hx : -1 < x) :
    Real.log (1 + x) ≤ x - x ^ 2 / 2 + x ^ 3 / 3 := by
  have hg0 : (fun t : ℝ => t - t ^ 2 / 2 + t ^ 3 / 3 - Real.log (1 + t)) 0 = 0 := by simp
  suffices h : 0 ≤ (fun t : ℝ => t - t ^ 2 / 2 + t ^ 3 / 3 - Real.log (1 + t)) x by
    simp only [] at h
    linarith [h]
  rcases lt_trichotomy x 0 with hneg | heq | hpos
  · have hanti : AntitoneOn (fun t : ℝ => t - t ^ 2 / 2 + t ^ 3 / 3 - Real.log (1 + t))
        (Set.Icc x 0) := by
      apply antitoneOn_of_deriv_nonpos (convex_Icc x 0)
      · intro y hy
        have hy1 : -1 < y := lt_of_lt_of_le hx (Set.mem_Icc.mp hy).1
        exact (ws7_hasDerivAt_g hy1).continuousAt.continuousWithinAt
      · intro y hy
        have hyIcc : y ∈ Set.Icc x 0 := interior_subset hy
        have hy1 : -1 < y := lt_of_lt_of_le hx (Set.mem_Icc.mp hyIcc).1
        exact (ws7_hasDerivAt_g hy1).differentiableAt.differentiableWithinAt
      · intro y hy
        have hyIcc : y ∈ Set.Icc x 0 := interior_subset hy
        obtain ⟨hxy, hy0⟩ := Set.mem_Icc.mp hyIcc
        have hy1 : -1 < y := lt_of_lt_of_le hx hxy
        rw [(ws7_hasDerivAt_g hy1).deriv]
        have hnum : y ^ 3 ≤ 0 := by
          have e : y ^ 3 = y * (y * y) := by ring
          rw [e]
          exact mul_nonpos_of_nonpos_of_nonneg hy0 (mul_self_nonneg y)
        exact div_nonpos_of_nonpos_of_nonneg hnum (by linarith : (0:ℝ) ≤ 1 + y)
    have hle := hanti (Set.left_mem_Icc.mpr hneg.le) (Set.right_mem_Icc.mpr hneg.le) hneg.le
    rw [hg0] at hle
    exact hle
  · subst heq
    rw [hg0]
  · have hmono : MonotoneOn (fun t : ℝ => t - t ^ 2 / 2 + t ^ 3 / 3 - Real.log (1 + t))
        (Set.Icc 0 x) := by
      apply monotoneOn_of_deriv_nonneg (convex_Icc 0 x)
      · intro y hy
        have hy0 : (0:ℝ) ≤ y := (Set.mem_Icc.mp hy).1
        have hy1 : -1 < y := by linarith
        exact (ws7_hasDerivAt_g hy1).continuousAt.continuousWithinAt
      · intro y hy
        have hyIcc : y ∈ Set.Icc 0 x := interior_subset hy
        have hy0 : (0:ℝ) ≤ y := (Set.mem_Icc.mp hyIcc).1
        have hy1 : -1 < y := by linarith
        exact (ws7_hasDerivAt_g hy1).differentiableAt.differentiableWithinAt
      · intro y hy
        have hyIcc : y ∈ Set.Icc 0 x := interior_subset hy
        have hy0 : (0:ℝ) ≤ y := (Set.mem_Icc.mp hyIcc).1
        have hy1 : -1 < y := by linarith
        rw [(ws7_hasDerivAt_g hy1).deriv]
        exact div_nonneg (by positivity) (by linarith : (0:ℝ) ≤ 1 + y)
    have hle := hmono (Set.left_mem_Icc.mpr hpos.le) (Set.right_mem_Icc.mpr hpos.le) hpos.le
    rw [hg0] at hle
    exact hle

/-- C1. The quadratic drag inequality, with an explicit constant. -/
theorem log_one_add_le_quad {x ε : ℝ} (hε0 : 0 < ε) (hε1 : ε < 1) (hx : |x| ≤ ε) :
    Real.log (1 + x) ≤ x - (1 / 2 - ε / 3) * x ^ 2 := by
  have _hε0 : (0:ℝ) < ε := hε0
  have hlt : |x| < 1 := lt_of_le_of_lt hx hε1
  have hx1 : -1 < x := by
    have h := abs_lt.mp hlt
    linarith [h.1]
  have hcubic := ws7_log_le_cubic hx1
  have hxle : x ≤ ε := le_trans (le_abs_self x) hx
  have hsq : (0:ℝ) ≤ x ^ 2 := by positivity
  have h23 : x ^ 3 / 3 ≤ (ε / 3) * x ^ 2 := by
    have hmul : x ^ 3 ≤ ε * x ^ 2 := by
      have e : x ^ 3 = x * x ^ 2 := by ring
      rw [e]
      exact mul_le_mul_of_nonneg_right hxle hsq
    linarith [hmul]
  linarith [hcubic, h23]

/-- Gap form of a small-step bound: `|k * y| ≤ ε < 1` forces `-1 / k < y`. -/
lemma ws7_gap {k ε y : ℝ} (hk : 0 < k) (hε1 : ε < 1) (h : |k * y| ≤ ε) : -1 / k < y := by
  have h1 : |k * y| < 1 := lt_of_le_of_lt h hε1
  have h2 : -1 < k * y := (abs_lt.mp h1).1
  rw [div_lt_iff₀ hk, mul_comm]
  exact h2

/-- Summed form of C1 at a fixed fraction. -/
lemma ws7_sum_log_le {lam : ℝ} {x : ℕ → ℝ} {ε : ℝ} (hε0 : 0 < ε) (hε1 : ε < 1) (T : ℕ)
    (h : ∀ t < T, |lam * x t| ≤ ε) :
    ∑ t ∈ range T, Real.log (1 + lam * x t)
      ≤ lam * ∑ t ∈ range T, x t - (1 / 2 - ε / 3) * lam ^ 2 * ∑ t ∈ range T, x t ^ 2 := by
  have hterm : ∀ t ∈ range T, Real.log (1 + lam * x t)
      ≤ lam * x t - (1 / 2 - ε / 3) * (lam * x t) ^ 2 := by
    intro t ht
    exact log_one_add_le_quad hε0 hε1 (h t (Finset.mem_range.mp ht))
  have hle := Finset.sum_le_sum hterm
  have heq : ∑ t ∈ range T, (lam * x t - (1 / 2 - ε / 3) * (lam * x t) ^ 2)
      = lam * ∑ t ∈ range T, x t - (1 / 2 - ε / 3) * lam ^ 2 * ∑ t ∈ range T, x t ^ 2 := by
    rw [Finset.sum_sub_distrib]
    congr 1
    · rw [← Finset.mul_sum]
    · have hcong : ∀ t ∈ range T, (1 / 2 - ε / 3) * (lam * x t) ^ 2
          = ((1 / 2 - ε / 3) * lam ^ 2) * x t ^ 2 := fun t _ => by ring
      rw [Finset.sum_congr rfl hcong, ← Finset.mul_sum]
  rwa [heq] at hle

variable {δ k E0 ε : ℝ} {r : ℕ → ℝ}

/-- C2. Between new highs the cushion's log growth is linear edge minus quadratic drag, on every path. -/
theorem cushion_growth_bound (hE : 0 < E0) (hδ0 : 0 < δ) (hδ1 : δ < 1) (hk : 0 < k)
    (hε0 : 0 < ε) (hε1 : ε < 1) (T : ℕ) (hrk : ∀ t < T, |k * r t| ≤ ε)
    (hnh : ∀ t < T, (run δ k E0 r (t + 1)).E ≤ (run δ k E0 r t).H) :
    Real.log (cushion δ (run δ k E0 r T))
      ≤ Real.log (δ * E0) + k * ∑ t ∈ range T, r t
        - (1 / 2 - ε / 3) * k ^ 2 * ∑ t ∈ range T, r t ^ 2 := by
  have hr : ∀ t < T, -1 / k < r t := fun t ht => ws7_gap hk hε1 (hrk t ht)
  have hid := log_cushion_no_new_high hE hδ0 hδ1 hk T hr hnh
  rw [hid]
  have hsum := ws7_sum_log_le (lam := k) (x := r) hε0 hε1 T hrk
  linarith [hsum]

/-- C3. The ceiling: above k = A/(cB) the cushion is smaller than it started, whatever the law.
A = Σr is the realised edge, B = Σr² the realised variance. No probability appears. -/
theorem cushion_shrinks_above_ceiling (hE : 0 < E0) (hδ0 : 0 < δ) (hδ1 : δ < 1) (hk : 0 < k)
    (hε0 : 0 < ε) (hε1 : ε < 1) (T : ℕ) (hrk : ∀ t < T, |k * r t| ≤ ε)
    (hnh : ∀ t < T, (run δ k E0 r (t + 1)).E ≤ (run δ k E0 r t).H)
    (hB : 0 < ∑ t ∈ range T, r t ^ 2)
    (hceil : (∑ t ∈ range T, r t) / ((1 / 2 - ε / 3) * ∑ t ∈ range T, r t ^ 2) < k) :
    cushion δ (run δ k E0 r T) < δ * E0 := by
  have hc : (0:ℝ) < 1 / 2 - ε / 3 := by linarith [hε1]
  have hr : ∀ t < T, -1 / k < r t := fun t ht => ws7_gap hk hε1 (hrk t ht)
  have hpos : 0 < cushion δ (run δ k E0 r T) := cushion_pos_upto hE hδ0 hδ1 hk T hr
  have hδE : (0:ℝ) < δ * E0 := mul_pos hδ0 hE
  have hgrowth := cushion_growth_bound hE hδ0 hδ1 hk hε0 hε1 T hrk hnh
  have hAlt : ∑ t ∈ range T, r t < k * ((1 / 2 - ε / 3) * ∑ t ∈ range T, r t ^ 2) := by
    have hpos2 : (0:ℝ) < (1 / 2 - ε / 3) * ∑ t ∈ range T, r t ^ 2 := mul_pos hc hB
    rwa [div_lt_iff₀ hpos2] at hceil
  have hneg : k * ∑ t ∈ range T, r t
      - (1 / 2 - ε / 3) * k ^ 2 * ∑ t ∈ range T, r t ^ 2 < 0 := by
    have key : k * ∑ t ∈ range T, r t
        - (1 / 2 - ε / 3) * k ^ 2 * ∑ t ∈ range T, r t ^ 2
        = k * (∑ t ∈ range T, r t
          - k * ((1 / 2 - ε / 3) * ∑ t ∈ range T, r t ^ 2)) := by ring
    rw [key]
    apply mul_neg_of_pos_of_neg hk
    linarith [hAlt]
  have hloglt : Real.log (cushion δ (run δ k E0 r T)) < Real.log (δ * E0) := by
    linarith [hgrowth, hneg]
  exact (Real.log_lt_log_iff hpos hδE).mp hloglt

/-- C4. At a high-water mark, effective gross is exactly k·δ, so the ceiling on k is a ceiling on gross. -/
theorem gross_at_high {E : ℝ} (hE : 0 < E) : k * cushion δ ⟨E, E⟩ / E = k * δ := by
  have hEne : E ≠ 0 := ne_of_gt hE
  have hc : cushion δ ⟨E, E⟩ = δ * E := by
    show E - (1 - δ) * E = δ * E
    ring
  rw [hc]
  field_simp

variable {x : ℕ → ℝ} {lam : ℝ}

/-- C5. Log capital at a fixed fraction: linear minus quadratic, on every path. -/
theorem log_capital_le (hε0 : 0 < ε) (hε1 : ε < 1) (T : ℕ) (h : ∀ t < T, |lam * x t| ≤ ε) :
    ∑ t ∈ range T, Real.log (1 + lam * x t)
      ≤ lam * ∑ t ∈ range T, x t - (1 / 2 - ε / 3) * lam ^ 2 * ∑ t ∈ range T, x t ^ 2 := by
  exact ws7_sum_log_le hε0 hε1 T h

/-- Completing the square: `lam * A - c * lam ^ 2 * B ≤ A ^ 2 / (4 * c * B)`. -/
lemma ws7_quad_le {A B lam c : ℝ} (hc : 0 < c) (hB : 0 < B) :
    lam * A - c * lam ^ 2 * B ≤ A ^ 2 / (4 * c * B) := by
  have hden : (0:ℝ) < 4 * c * B := mul_pos (mul_pos (by norm_num) hc) hB
  have hD : (0:ℝ) ≤ (A - 2 * c * lam * B) ^ 2 / (4 * c * B) :=
    div_nonneg (by positivity) hden.le
  have hid : A ^ 2 / (4 * c * B)
      = lam * A - c * lam ^ 2 * B + (A - 2 * c * lam * B) ^ 2 / (4 * c * B) := by
    field_simp
    ring
  rw [hid]
  linarith [hD]

/-- Cancellation of the factor `4 * c` against the t-statistic denominator. -/
lemma ws7_four_mul_div {A B c : ℝ} (hc : c ≠ 0) (hB : B ≠ 0) :
    4 * c * (A / (4 * c * B)) = A / B := by
  field_simp

/-- C6. Pathwise: no fixed fraction earns more log capital than A²/(4cB), the squared self-normalised
t-statistic over 4c. With ε → 0 this is t²/2. -/
theorem log_capital_le_tstat (hε0 : 0 < ε) (hε1 : ε < 1) (T : ℕ) (h : ∀ t < T, |lam * x t| ≤ ε)
    (hB : 0 < ∑ t ∈ range T, x t ^ 2) :
    ∑ t ∈ range T, Real.log (1 + lam * x t)
      ≤ (∑ t ∈ range T, x t) ^ 2 / (4 * (1 / 2 - ε / 3) * ∑ t ∈ range T, x t ^ 2) := by
  have hc : (0:ℝ) < 1 / 2 - ε / 3 := by linarith [hε1]
  have h5 := log_capital_le hε0 hε1 T h
  have hquad := ws7_quad_le (A := ∑ t ∈ range T, x t) (B := ∑ t ∈ range T, x t ^ 2)
    (lam := lam) (c := 1 / 2 - ε / 3) hc hB
  exact le_trans h5 hquad

/-- C7. The verification requirement. Reaching e-value 1/α at a fixed fraction forces the t-statistic. -/
theorem evalue_requires_tstat {α : ℝ} (hα : 0 < α) (hε0 : 0 < ε) (hε1 : ε < 1) (T : ℕ)
    (h : ∀ t < T, |lam * x t| ≤ ε) (hB : 0 < ∑ t ∈ range T, x t ^ 2)
    (hreach : Real.log (1 / α) ≤ ∑ t ∈ range T, Real.log (1 + lam * x t)) :
    4 * (1 / 2 - ε / 3) * Real.log (1 / α)
      ≤ (∑ t ∈ range T, x t) ^ 2 / ∑ t ∈ range T, x t ^ 2 := by
  have _hα : (0:ℝ) < α := hα
  have hc : (0:ℝ) < 1 / 2 - ε / 3 := by linarith [hε1]
  have hcne : (1 / 2 - ε / 3 : ℝ) ≠ 0 := ne_of_gt hc
  have hBne : (∑ t ∈ range T, x t ^ 2) ≠ 0 := ne_of_gt hB
  have h6 := log_capital_le_tstat hε0 hε1 T h hB
  have hle : Real.log (1 / α)
      ≤ (∑ t ∈ range T, x t) ^ 2 / (4 * (1 / 2 - ε / 3) * ∑ t ∈ range T, x t ^ 2) :=
    le_trans hreach h6
  have hmul : 4 * (1 / 2 - ε / 3) * Real.log (1 / α)
      ≤ 4 * (1 / 2 - ε / 3)
        * ((∑ t ∈ range T, x t) ^ 2 / (4 * (1 / 2 - ε / 3) * ∑ t ∈ range T, x t ^ 2)) :=
    mul_le_mul_of_nonneg_left hle (by linarith [hc] : (0:ℝ) ≤ 4 * (1 / 2 - ε / 3))
  have heq : 4 * (1 / 2 - ε / 3)
      * ((∑ t ∈ range T, x t) ^ 2 / (4 * (1 / 2 - ε / 3) * ∑ t ∈ range T, x t ^ 2))
      = (∑ t ∈ range T, x t) ^ 2 / ∑ t ∈ range T, x t ^ 2 :=
    ws7_four_mul_div hcne hBne
  calc 4 * (1 / 2 - ε / 3) * Real.log (1 / α)
      ≤ 4 * (1 / 2 - ε / 3)
        * ((∑ t ∈ range T, x t) ^ 2 / (4 * (1 / 2 - ε / 3) * ∑ t ∈ range T, x t ^ 2)) := hmul
    _ = (∑ t ∈ range T, x t) ^ 2 / ∑ t ∈ range T, x t ^ 2 := heq

/-- C8. A finite mixture over fractions cannot beat C6 either. -/
theorem mix_le_tstat {K : ℕ} (hK : 0 < K) {lams : Fin K → ℝ} (hε0 : 0 < ε) (hε1 : ε < 1) (T : ℕ)
    (h : ∀ j, ∀ t < T, |lams j * x t| ≤ ε) (hB : 0 < ∑ t ∈ range T, x t ^ 2) :
    Real.log ((∑ j, ∏ t ∈ range T, (1 + lams j * x t)) / K)
      ≤ (∑ t ∈ range T, x t) ^ 2 / (4 * (1 / 2 - ε / 3) * ∑ t ∈ range T, x t ^ 2) := by
  set M : ℝ := (∑ t ∈ range T, x t) ^ 2
    / (4 * (1 / 2 - ε / 3) * ∑ t ∈ range T, x t ^ 2) with hMdef
  have hfac : ∀ j : Fin K, ∀ t ∈ range T, (0:ℝ) < 1 + lams j * x t := by
    intro j t ht
    have h1 : |lams j * x t| < 1 :=
      lt_of_le_of_lt (h j t (Finset.mem_range.mp ht)) hε1
    have h2 := abs_lt.mp h1
    linarith [h2.1]
  have hPpos : ∀ j : Fin K, (0:ℝ) < ∏ t ∈ range T, (1 + lams j * x t) :=
    fun j => Finset.prod_pos (fun t ht => hfac j t ht)
  have hlogP : ∀ j : Fin K,
      Real.log (∏ t ∈ range T, (1 + lams j * x t)) ≤ M := by
    intro j
    rw [Real.log_prod (fun t ht => (hfac j t ht).ne')]
    exact log_capital_le_tstat (lam := lams j) hε0 hε1 T (h j) hB
  have hPle : ∀ j : Fin K, ∏ t ∈ range T, (1 + lams j * x t) ≤ Real.exp M := by
    intro j
    calc ∏ t ∈ range T, (1 + lams j * x t)
        = Real.exp (Real.log (∏ t ∈ range T, (1 + lams j * x t))) :=
          (Real.exp_log (hPpos j)).symm
      _ ≤ Real.exp M := Real.exp_le_exp.mpr (hlogP j)
  have hKpos : (0:ℝ) < (K : ℝ) := by exact_mod_cast hK
  have hsumle : ∑ j, ∏ t ∈ range T, (1 + lams j * x t)
      ≤ ∑ _j : Fin K, Real.exp M :=
    Finset.sum_le_sum (fun j _ => hPle j)
  have hsumexp : ∑ _j : Fin K, Real.exp M = (K : ℝ) * Real.exp M := by
    rw [Finset.sum_const, Finset.card_univ, Fintype.card_fin, nsmul_eq_mul]
  have havgpos : (0:ℝ) < (∑ j, ∏ t ∈ range T, (1 + lams j * x t)) / (K : ℝ) := by
    apply div_pos _ hKpos
    exact Finset.sum_pos (fun j _ => hPpos j) ⟨⟨0, hK⟩, Finset.mem_univ _⟩
  have havg : (∑ j, ∏ t ∈ range T, (1 + lams j * x t)) / (K : ℝ) ≤ Real.exp M := by
    rw [div_le_iff₀ hKpos]
    have hle : ∑ j, ∏ t ∈ range T, (1 + lams j * x t) ≤ (K : ℝ) * Real.exp M :=
      le_trans hsumle (le_of_eq hsumexp)
    calc ∑ j, ∏ t ∈ range T, (1 + lams j * x t)
        ≤ (K : ℝ) * Real.exp M := hle
      _ = Real.exp M * (K : ℝ) := mul_comm _ _
  calc Real.log ((∑ j, ∏ t ∈ range T, (1 + lams j * x t)) / (K : ℝ))
      ≤ Real.log (Real.exp M) :=
        (Real.log_le_log_iff havgpos (Real.exp_pos M)).mpr havg
    _ = M := Real.log_exp M

/-- C9. The critical exponent: the regime spread is damped in G* iff α > 2, and amplified below it. -/
theorem damping_iff {α s : ℝ} (hα : 1 < α) (hs : 1 < s) : s ^ (1 / (α - 1)) < s ↔ 2 < α := by
  have hα1 : (0:ℝ) < α - 1 := by linarith [hα]
  have hiff : s ^ (1 / (α - 1)) < s ↔ (1:ℝ) / (α - 1) < 1 := by
    have h : s ^ (1 / (α - 1)) < s ^ (1:ℝ) ↔ (1:ℝ) / (α - 1) < 1 :=
      Real.rpow_lt_rpow_left_iff hs
    rwa [Real.rpow_one] at h
  rw [hiff]
  constructor
  · intro h
    have h1 : (1:ℝ) < α - 1 := (div_lt_one hα1).mp h
    linarith [h1]
  · intro h
    apply (div_lt_one hα1).mpr
    linarith [h]

/-- C10. The overshoot correction: the frictionless hurdle D/(T+D) understates the no-edge bound. -/
theorem hurdle_overshoot_gap {T D B : ℝ} (hT : 0 < T) (hD : 0 < D) (hB : 0 < B) :
    D / (T + D) < (D + B) / (T + D + B) := by
  have h1 : (0:ℝ) < T + D := by linarith [hT, hD]
  have h2 : (0:ℝ) < T + D + B := by linarith [hT, hD, hB]
  rw [div_lt_div_iff₀ h1 h2]
  have hTB : (0:ℝ) < T * B := mul_pos hT hB
  nlinarith [hTB]

end

end PerpChief.Ceiling
