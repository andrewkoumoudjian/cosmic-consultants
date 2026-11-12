/- NOT IMPORTED by Analog.lean (2026-11-12): mechanical port fails on current Mathlib APIs; registered re-proof candidate in docs/research/06-lean-corpus-inventory.md. Preserved verbatim for the re-prover. -/
/-
PORTED 2026-11-12 from owner prior work: anytime-valid hazard test validity
Source: andrewkoumoudjian/perps-strategy @ 0f34759, lanes/chief/lean/PerpChief/HazardTest.lean (toolchain v4.15.0).
Port changes ONLY: module path/import remap to Analog.Prior.* (+ Mathlib API renames if listed in docs/research/06). Namespaces, statements, proofs otherwise verbatim. Original file is frozen upstream; do not edit semantics here.
-/
/-
WS8 — VALIDITY OF THE HAZARD_V1 TEST. FROZEN STATEMENTS (chief scientist). Fill in the proof holes; add helper lemmas.
The test was run first and is registered in `events/HAZARD_V1.md`; this module certifies its Type I guarantee.
Each hour takes the mean of (hit - pi) over in-state coins and bets on it. The claim needs no independence
across coins or across time, only a conditional bound on each coin's hit probability given the past.
It says nothing about direction, edge or profit.
-/
import Analog.Prior.Ville

open MeasureTheory Filter Finset
open scoped ENNReal

namespace PerpChief.HazardTest

noncomputable section

open PerpChief.Ville

variable {Ω : Type*} {m0 : MeasurableSpace Ω} {μ : Measure Ω} [IsProbabilityMeasure μ]
  {ℱ : Filtration ℕ m0} {C : ℕ}

/-- Hourly statistic: mean of `(hit - pi)` over in-state coins. Lean's `x / 0 = 0` gives `0` when no coin is in state. -/
def Xbar (s hit pi : ℕ → Fin C → Ω → ℝ) (n : ℕ) (ω : Ω) : ℝ :=
  (∑ i, s n i ω * (hit n i ω - pi n i ω)) / ∑ i, s n i ω

/-- Assumptions of HAZARD_V1. `null` is H0: given the past, each coin's hit probability is at most `pi`. -/
structure HazardHyp (ℱ : Filtration ℕ m0) (μ : Measure Ω) (s hit pi : ℕ → Fin C → Ω → ℝ) (c : ℝ) : Prop where
  s_adapted : ∀ n i, StronglyMeasurable[ℱ n] (s n i)
  s_predictable : ∀ n i, StronglyMeasurable[ℱ n] (s (n + 1) i)
  pi_adapted : ∀ n i, StronglyMeasurable[ℱ n] (pi n i)
  pi_predictable : ∀ n i, StronglyMeasurable[ℱ n] (pi (n + 1) i)
  hit_adapted : ∀ n i, StronglyMeasurable[ℱ n] (hit n i)
  s_zero_one : ∀ n i ω, s n i ω = 0 ∨ s n i ω = 1
  hit_nonneg : ∀ n i ω, 0 ≤ hit n i ω
  hit_le_one : ∀ n i ω, hit n i ω ≤ 1
  pi_nonneg : ∀ n i ω, 0 ≤ pi n i ω
  pi_le_of_state : ∀ n i ω, s n i ω = 1 → pi n i ω ≤ c
  c_nonneg : 0 ≤ c
  null : ∀ n i, μ[hit (n + 1) i | ℱ n] ≤ᵐ[μ] pi (n + 1) i

variable {s hit pi : ℕ → Fin C → Ω → ℝ} {c : ℝ}

lemma Xbar_stronglyMeasurable (h : HazardHyp ℱ μ s hit pi c) (n : ℕ) :
    StronglyMeasurable[ℱ n] (Xbar s hit pi n) := by
  have hnum : StronglyMeasurable[ℱ n] (fun ω => ∑ i, s n i ω * (hit n i ω - pi n i ω)) := by
    apply Finset.stronglyMeasurable_sum
    intro i _
    exact (h.s_adapted n i).mul ((h.hit_adapted n i).sub (h.pi_adapted n i))
  have hden : StronglyMeasurable[ℱ n] (fun ω => ∑ i, s n i ω) := by
    apply Finset.stronglyMeasurable_sum
    intro i _
    exact h.s_adapted n i
  have hmeas : Measurable[ℱ n] (Xbar s hit pi n) := by
    have hEq : Xbar s hit pi n
        = fun ω => (∑ i, s n i ω * (hit n i ω - pi n i ω)) / (∑ i, s n i ω) := by
      funext ω
      rfl
    rw [hEq]
    exact hnum.measurable.div hden.measurable
  exact hmeas.stronglyMeasurable

lemma s_nonneg (h : HazardHyp ℱ μ s hit pi c) (n : ℕ) (i : Fin C) (ω : Ω) :
    0 ≤ s n i ω := by
  rcases h.s_zero_one n i ω with hs | hs <;> rw [hs] <;> norm_num

/-- H1. The statistic is bounded below by `-c`. -/
theorem Xbar_lower (h : HazardHyp ℱ μ s hit pi c) (n : ℕ) (ω : Ω) : -c ≤ Xbar s hit pi n ω := by
  by_cases hd : (∑ i, s n i ω) = 0
  · unfold Xbar
    rw [hd, div_zero]
    linarith [h.c_nonneg]
  · have hd_nonneg : 0 ≤ ∑ i, s n i ω := by
      apply Finset.sum_nonneg
      intro i _
      rcases h.s_zero_one n i ω with hs | hs <;> rw [hs] <;> norm_num
    have hd_pos : 0 < ∑ i, s n i ω := lt_of_le_of_ne hd_nonneg (Ne.symm hd)
    have hterm : ∀ i ∈ Finset.univ, -c * s n i ω ≤ s n i ω * (hit n i ω - pi n i ω) := by
      intro i _
      rcases h.s_zero_one n i ω with hs | hs
      · rw [hs]; norm_num
      · rw [hs]
        have hpi := h.pi_le_of_state n i ω hs
        have hhit := h.hit_nonneg n i ω
        simp only [mul_one, one_mul]
        linarith
    have hsum : -c * (∑ i, s n i ω) ≤ ∑ i, s n i ω * (hit n i ω - pi n i ω) := by
      have h1 : (∑ i, -c * s n i ω) ≤ ∑ i, s n i ω * (hit n i ω - pi n i ω) :=
        Finset.sum_le_sum hterm
      have h2 : (∑ i, -c * s n i ω) = -c * (∑ i, s n i ω) := by
        rw [Finset.mul_sum]
      rw [h2] at h1
      exact h1
    unfold Xbar
    rw [le_div_iff₀ hd_pos]
    exact hsum

/-- H2. The statistic is at most one. -/
theorem Xbar_upper (h : HazardHyp ℱ μ s hit pi c) (n : ℕ) (ω : Ω) : Xbar s hit pi n ω ≤ 1 := by
  by_cases hd : (∑ i, s n i ω) = 0
  · unfold Xbar
    rw [hd, div_zero]
    norm_num
  · have hd_nonneg : 0 ≤ ∑ i, s n i ω := by
      apply Finset.sum_nonneg
      intro i _
      rcases h.s_zero_one n i ω with hs | hs <;> rw [hs] <;> norm_num
    have hd_pos : 0 < ∑ i, s n i ω := lt_of_le_of_ne hd_nonneg (Ne.symm hd)
    have hterm : ∀ i ∈ Finset.univ, s n i ω * (hit n i ω - pi n i ω) ≤ s n i ω * 1 := by
      intro i _
      rcases h.s_zero_one n i ω with hs | hs
      · rw [hs]; norm_num
      · rw [hs]
        have hpi := h.pi_nonneg n i ω
        have hhit := h.hit_le_one n i ω
        simp only [mul_one, one_mul]
        linarith
    have hsum : (∑ i, s n i ω * (hit n i ω - pi n i ω)) ≤ ∑ i, s n i ω := by
      have h1 : (∑ i, s n i ω * (hit n i ω - pi n i ω)) ≤ ∑ i, s n i ω * 1 :=
        Finset.sum_le_sum hterm
      have h2 : (∑ i, s n i ω * 1) = ∑ i, s n i ω := by simp
      rw [h2] at h1
      exact h1
    unfold Xbar
    rw [div_le_iff₀ hd_pos]
    calc (∑ i, s n i ω * (hit n i ω - pi n i ω)) ≤ ∑ i, s n i ω := hsum
      _ = 1 * (∑ i, s n i ω) := by rw [one_mul]

lemma Xbar_integrable (h : HazardHyp ℱ μ s hit pi c) (n : ℕ) :
    Integrable (Xbar s hit pi n) μ := by
  refine integrable_of_bound
    (((Xbar_stronglyMeasurable h n).mono (ℱ.le n)).aestronglyMeasurable) (c + 1) ?_
  intro ω
  rw [Real.norm_eq_abs, abs_le]
  constructor
  · have hlo := Xbar_lower h n ω
    linarith [h.c_nonneg]
  · have hhi := Xbar_upper h n ω
    linarith [h.c_nonneg]

/-- H3. Under H0 the statistic has non-positive conditional mean, with no independence assumption. -/
theorem Xbar_null (h : HazardHyp ℱ μ s hit pi c) (n : ℕ) :
    μ[Xbar s hit pi (n + 1) | ℱ n] ≤ᵐ[μ] fun _ => 0 := by
  have hs_pred : ∀ i, StronglyMeasurable[ℱ n] (s (n + 1) i) := fun i => h.s_predictable n i
  have hpi_pred : ∀ i, StronglyMeasurable[ℱ n] (pi (n + 1) i) := fun i => h.pi_predictable n i
  have hD_meas : StronglyMeasurable[ℱ n] (fun ω => ∑ i, s (n + 1) i ω) := by
    apply Finset.stronglyMeasurable_sum
    intro i _
    exact hs_pred i
  have hD_nonneg : ∀ ω, 0 ≤ ∑ i, s (n + 1) i ω := fun ω =>
    Finset.sum_nonneg fun i _ => s_nonneg h (n + 1) i ω
  have hinv_meas : StronglyMeasurable[ℱ n] (fun ω => (∑ i, s (n + 1) i ω)⁻¹) := by
    have hm : Measurable[ℱ n] (fun ω => (∑ i, s (n + 1) i ω)⁻¹) :=
      hD_meas.measurable.inv
    exact hm.stronglyMeasurable
  have hhit_int : ∀ i, Integrable (hit (n + 1) i) μ := by
    intro i
    refine integrable_of_bound
      (((h.hit_adapted (n + 1) i).mono (ℱ.le (n + 1))).aestronglyMeasurable) 1 ?_
    intro ω
    rw [Real.norm_eq_abs, abs_le]
    constructor <;> linarith [h.hit_nonneg (n + 1) i ω, h.hit_le_one (n + 1) i ω]
  have hshit_int : ∀ i, Integrable (fun ω => s (n + 1) i ω * hit (n + 1) i ω) μ := by
    intro i
    have hs_up : StronglyMeasurable[ℱ (n + 1)] (s (n + 1) i) :=
      (hs_pred i).mono (ℱ.mono (Nat.le_succ n))
    have hsm : StronglyMeasurable[ℱ (n + 1)]
        (fun ω => s (n + 1) i ω * hit (n + 1) i ω) :=
      hs_up.mul (h.hit_adapted (n + 1) i)
    refine integrable_of_bound ((hsm.mono (ℱ.le (n + 1))).aestronglyMeasurable) 1 ?_
    intro ω
    rcases h.s_zero_one (n + 1) i ω with hs | hs
    · rw [hs]
      simp
    · rw [hs]
      simp only [one_mul, Real.norm_eq_abs]
      rw [abs_of_nonneg (h.hit_nonneg (n + 1) i ω)]
      exact h.hit_le_one (n + 1) i ω
  have hspi_int : ∀ i, Integrable (fun ω => s (n + 1) i ω * pi (n + 1) i ω) μ := by
    intro i
    have hs_up : StronglyMeasurable[ℱ (n + 1)] (s (n + 1) i) :=
      (hs_pred i).mono (ℱ.mono (Nat.le_succ n))
    have hsm : StronglyMeasurable[ℱ (n + 1)]
        (fun ω => s (n + 1) i ω * pi (n + 1) i ω) :=
      hs_up.mul (h.pi_adapted (n + 1) i)
    refine integrable_of_bound ((hsm.mono (ℱ.le (n + 1))).aestronglyMeasurable) c ?_
    intro ω
    rcases h.s_zero_one (n + 1) i ω with hs | hs
    · rw [hs]
      simp [h.c_nonneg]
    · rw [hs]
      simp only [one_mul, Real.norm_eq_abs]
      rw [abs_of_nonneg (h.pi_nonneg (n + 1) i ω)]
      exact h.pi_le_of_state (n + 1) i ω hs
  have ht_int : ∀ i, Integrable
      (fun ω => s (n + 1) i ω * (hit (n + 1) i ω - pi (n + 1) i ω)) μ := by
    intro i
    have hs_up : StronglyMeasurable[ℱ (n + 1)] (s (n + 1) i) :=
      (hs_pred i).mono (ℱ.mono (Nat.le_succ n))
    have hsm : StronglyMeasurable[ℱ (n + 1)]
        (fun ω => s (n + 1) i ω * (hit (n + 1) i ω - pi (n + 1) i ω)) :=
      hs_up.mul ((h.hit_adapted (n + 1) i).sub (h.pi_adapted (n + 1) i))
    refine integrable_of_bound ((hsm.mono (ℱ.le (n + 1))).aestronglyMeasurable) (c + 1) ?_
    intro ω
    rcases h.s_zero_one (n + 1) i ω with hs | hs
    · rw [hs]
      simp only [zero_mul, norm_zero]
      linarith [h.c_nonneg]
    · rw [hs]
      simp only [one_mul, Real.norm_eq_abs, abs_le]
      constructor <;>
        linarith [h.hit_nonneg (n + 1) i ω, h.hit_le_one (n + 1) i ω,
          h.pi_nonneg (n + 1) i ω, h.pi_le_of_state (n + 1) i ω hs, h.c_nonneg]
  have hterm_condexp : ∀ i,
      μ[fun ω => s (n + 1) i ω * (hit (n + 1) i ω - pi (n + 1) i ω) | ℱ n]
        =ᵐ[μ] fun ω => s (n + 1) i ω * ((μ[hit (n + 1) i | ℱ n]) ω - pi (n + 1) i ω) := by
    intro i
    have hpull_i : μ[fun ω => s (n + 1) i ω * hit (n + 1) i ω | ℱ n]
        =ᵐ[μ] fun ω => s (n + 1) i ω * (μ[hit (n + 1) i | ℱ n]) ω :=
      condexp_stronglyMeasurable_mul (hs_pred i) (hshit_int i) (hhit_int i)
    have hspi_stm : StronglyMeasurable[ℱ n] (fun ω => s (n + 1) i ω * pi (n + 1) i ω) :=
      (hs_pred i).mul (hpi_pred i)
    have hspi_eq : μ[fun ω => s (n + 1) i ω * pi (n + 1) i ω | ℱ n]
        = fun ω => s (n + 1) i ω * pi (n + 1) i ω :=
      condexp_of_stronglyMeasurable (ℱ.le n) hspi_stm (hspi_int i)
    have hspi_ae : μ[fun ω => s (n + 1) i ω * pi (n + 1) i ω | ℱ n]
        =ᵐ[μ] fun ω => s (n + 1) i ω * pi (n + 1) i ω :=
      Filter.EventuallyEq.of_eq hspi_eq
    have step1 : μ[fun ω => s (n + 1) i ω * (hit (n + 1) i ω - pi (n + 1) i ω) | ℱ n]
        =ᵐ[μ] μ[fun ω => s (n + 1) i ω * hit (n + 1) i ω
          - s (n + 1) i ω * pi (n + 1) i ω | ℱ n] :=
      condexp_congr_ae (Filter.Eventually.of_forall fun ω => by ring)
    have step2 : μ[fun ω => s (n + 1) i ω * hit (n + 1) i ω
          - s (n + 1) i ω * pi (n + 1) i ω | ℱ n]
        =ᵐ[μ] μ[fun ω => s (n + 1) i ω * hit (n + 1) i ω | ℱ n]
          - μ[fun ω => s (n + 1) i ω * pi (n + 1) i ω | ℱ n] :=
      condexp_sub (hshit_int i) (hspi_int i)
    have step3 : μ[fun ω => s (n + 1) i ω * hit (n + 1) i ω | ℱ n]
          - μ[fun ω => s (n + 1) i ω * pi (n + 1) i ω | ℱ n]
        =ᵐ[μ] (fun ω => s (n + 1) i ω * (μ[hit (n + 1) i | ℱ n]) ω)
          - (fun ω => s (n + 1) i ω * pi (n + 1) i ω) :=
      hpull_i.sub hspi_ae
    have step4 : (fun ω => s (n + 1) i ω * (μ[hit (n + 1) i | ℱ n]) ω)
          - (fun ω => s (n + 1) i ω * pi (n + 1) i ω)
        =ᵐ[μ] fun ω => s (n + 1) i ω * ((μ[hit (n + 1) i | ℱ n]) ω - pi (n + 1) i ω) := by
      filter_upwards with ω
      simp only [Pi.sub_apply]
      ring
    exact step1.trans (step2.trans (step3.trans step4))
  have hN_int : Integrable
      (fun ω => ∑ i, s (n + 1) i ω * (hit (n + 1) i ω - pi (n + 1) i ω)) μ :=
    integrable_finset_sum Finset.univ fun i _ => ht_int i
  have hN_condexp_sum : μ[fun ω => ∑ i, s (n + 1) i ω * (hit (n + 1) i ω - pi (n + 1) i ω) | ℱ n]
      =ᵐ[μ] fun ω => ∑ i, (μ[fun ω => s (n + 1) i ω * (hit (n + 1) i ω - pi (n + 1) i ω) | ℱ n]) ω := by
    have hh := condexp_finset_sum (m := ℱ n) (s := Finset.univ)
      (f := fun i ω => s (n + 1) i ω * (hit (n + 1) i ω - pi (n + 1) i ω))
      (fun i _ => ht_int i)
    have hEqF : (fun ω => ∑ i, s (n + 1) i ω * (hit (n + 1) i ω - pi (n + 1) i ω))
        = ∑ i, fun ω => s (n + 1) i ω * (hit (n + 1) i ω - pi (n + 1) i ω) := by
      funext ω
      rw [Finset.sum_apply]
    rw [hEqF]
    filter_upwards [hh] with ω hω
    rw [hω, Finset.sum_apply]
  have hN_condexp : μ[fun ω => ∑ i, s (n + 1) i ω * (hit (n + 1) i ω - pi (n + 1) i ω) | ℱ n]
      =ᵐ[μ] fun ω => ∑ i, s (n + 1) i ω * ((μ[hit (n + 1) i | ℱ n]) ω - pi (n + 1) i ω) := by
    have hall : ∀ᵐ ω ∂μ, ∀ i,
        (μ[fun ω => s (n + 1) i ω * (hit (n + 1) i ω - pi (n + 1) i ω) | ℱ n]) ω
          = s (n + 1) i ω * ((μ[hit (n + 1) i | ℱ n]) ω - pi (n + 1) i ω) :=
      (ae_all_iff).mpr fun i => hterm_condexp i
    filter_upwards [hN_condexp_sum, hall] with ω hSum hAll
    rw [hSum]
    exact Finset.sum_congr rfl fun i _ => hAll i
  have hprod_eq : (fun ω => (∑ i, s (n + 1) i ω)⁻¹)
        * (fun ω => ∑ i, s (n + 1) i ω * (hit (n + 1) i ω - pi (n + 1) i ω))
      = Xbar s hit pi (n + 1) := by
    funext ω
    simp only [Pi.mul_apply, Xbar, div_eq_mul_inv, mul_comm]
  have hfg_int : Integrable ((fun ω => (∑ i, s (n + 1) i ω)⁻¹)
      * (fun ω => ∑ i, s (n + 1) i ω * (hit (n + 1) i ω - pi (n + 1) i ω))) μ := by
    rw [hprod_eq]
    exact Xbar_integrable h (n + 1)
  have hpullD : μ[Xbar s hit pi (n + 1) | ℱ n]
      =ᵐ[μ] (fun ω => (∑ i, s (n + 1) i ω)⁻¹)
        * μ[fun ω => ∑ i, s (n + 1) i ω * (hit (n + 1) i ω - pi (n + 1) i ω) | ℱ n] := by
    have stepX : μ[Xbar s hit pi (n + 1) | ℱ n]
        =ᵐ[μ] μ[(fun ω => (∑ i, s (n + 1) i ω)⁻¹)
          * (fun ω => ∑ i, s (n + 1) i ω * (hit (n + 1) i ω - pi (n + 1) i ω)) | ℱ n] :=
      condexp_congr_ae (Filter.Eventually.of_forall fun ω => by
        show Xbar s hit pi (n + 1) ω
            = ((fun ω => (∑ i, s (n + 1) i ω)⁻¹)
              * (fun ω => ∑ i, s (n + 1) i ω * (hit (n + 1) i ω - pi (n + 1) i ω))) ω
        simp only [Pi.mul_apply, Xbar, div_eq_mul_inv, mul_comm])
    have stepPull := condexp_stronglyMeasurable_mul hinv_meas hfg_int hN_int
    exact stepX.trans stepPull
  have hnull_all : ∀ᵐ ω ∂μ, ∀ i, (μ[hit (n + 1) i | ℱ n]) ω ≤ pi (n + 1) i ω :=
    (ae_all_iff).mpr fun i => h.null n i
  filter_upwards [hpullD, hN_condexp, hnull_all] with ω hPull hN hNull
  have hsum_nonpos : (∑ i, s (n + 1) i ω * ((μ[hit (n + 1) i | ℱ n]) ω - pi (n + 1) i ω)) ≤ 0 :=
    Finset.sum_nonpos fun i _ =>
      mul_nonpos_of_nonneg_of_nonpos (s_nonneg h (n + 1) i ω) (sub_nonpos.mpr (hNull i))
  have hinv_nonneg : 0 ≤ (∑ i, s (n + 1) i ω)⁻¹ := inv_nonneg.mpr (hD_nonneg ω)
  show (μ[Xbar s hit pi (n + 1) | ℱ n]) ω ≤ 0
  rw [hPull]
  simp only [Pi.mul_apply]
  rw [hN]
  exact mul_nonpos_of_nonneg_of_nonpos hinv_nonneg hsum_nonpos

/-- H4. A constant bet on the statistic meets the Ville engine's hypotheses. -/
theorem hazard_bettingHyp (h : HazardHyp ℱ μ s hit pi c) {lam L : ℝ} (hlam0 : 0 ≤ lam) (hlam : lam ≤ L)
    (hL : L * c ≤ 1) :
    BettingHyp ℱ μ (fun _ _ => lam) (Xbar s hit pi) 0 c 1 L := by
  refine ⟨fun n => Xbar_stronglyMeasurable h n, fun _ => stronglyMeasurable_const,
    fun n ω => Xbar_lower h n ω, fun n ω => Xbar_upper h n ω,
    fun _ _ => hlam0, fun _ _ => hlam, ?_, ?_, fun n => Xbar_null h n⟩
  · simpa using h.c_nonneg
  · simpa using hL

/-- H5. The registered test: the running maximum of a uniform mixture of bets exceeds `1/α` with probability at most `α`. -/
theorem hazard_test_valid (h : HazardHyp ℱ μ s hit pi c) {K : ℕ} (hK : 0 < K) {lams : Fin K → ℝ} {L : ℝ}
    (hlam0 : ∀ j, 0 ≤ lams j) (hlam : ∀ j, lams j ≤ L) (hL : L * c ≤ 1) {α : ℝ} (hα : 0 < α) (N : ℕ) :
    μ {ω | ∃ n ≤ N, 1 / α ≤ (∑ j, capital (fun _ _ => lams j) (Xbar s hit pi) 0 n ω) / K}
      ≤ ENNReal.ofReal α := by
  have hBet : ∀ j, BettingHyp ℱ μ (fun _ _ => lams j) (Xbar s hit pi) 0 c 1 L :=
    fun j => hazard_bettingHyp h (hlam0 j) (hlam j) hL
  have hSuper : ∀ j, Supermartingale (capital (fun _ _ => lams j) (Xbar s hit pi) 0) ℱ μ :=
    fun j => capital_supermartingale (hBet j)
  have hMix : Supermartingale
      (fun n ω => (∑ j, capital (fun _ _ => lams j) (Xbar s hit pi) 0 n ω) / K) ℱ μ :=
    mix_supermartingale hK hSuper
  have hNonneg : ∀ n ω, 0 ≤ (∑ j, capital (fun _ _ => lams j) (Xbar s hit pi) 0 n ω) / K := by
    intro n ω
    apply div_nonneg
    · exact Finset.sum_nonneg fun j _ => capital_nonneg (hBet j) n ω
    · exact Nat.cast_nonneg K
  have hBound := ville_finite hMix hNonneg (c := 1 / α) (div_pos one_pos hα) N
  have hInt : (∫ ω, (fun n ω => (∑ j, capital (fun _ _ => lams j) (Xbar s hit pi) 0 n ω) / K) 0 ω ∂μ)
      = 1 := by
    have h0 : (fun n ω => (∑ j, capital (fun _ _ => lams j) (Xbar s hit pi) 0 n ω) / K) 0
        = fun _ : Ω => (1 : ℝ) := by
      funext ω
      have hKreal : (K : ℝ) ≠ 0 := by exact_mod_cast hK.ne'
      simp only [capital]
      rw [Finset.sum_const, Finset.card_univ, Fintype.card_fin, nsmul_eq_mul, mul_one,
        div_self hKreal]
    rw [h0]
    simp
  rw [hInt, one_div_one_div] at hBound
  exact hBound

/-- H6. HAZARD_V1's settings are admissible: largest bet 3, cap 1/4. -/
theorem hazard_v1_admissible : (3 : ℝ) * (1 / 4) ≤ 1 := by
  norm_num

end

end PerpChief.HazardTest
