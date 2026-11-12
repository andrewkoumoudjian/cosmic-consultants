/- NOT IMPORTED by Analog.lean (2026-11-12): mechanical port fails on current Mathlib APIs; registered re-proof candidate in docs/research/06-lean-corpus-inventory.md. Preserved verbatim for the re-prover. -/
/-
PORTED 2026-11-12 from owner prior work: Ville anytime-valid supermartingale bounds
Source: andrewkoumoudjian/perps-strategy @ 0f34759, lanes/chief/lean/PerpChief/Ville.lean (toolchain v4.15.0).
Port changes ONLY: module path/import remap to Analog.Prior.* (+ Mathlib API renames if listed in docs/research/06). Namespaces, statements, proofs otherwise verbatim. Original file is frozen upstream; do not edit semantics here.
-/
/-
WS1 — THE VILLE ENGINE. FROZEN STATEMENTS (chief scientist). Fill in the proof holes; add helper lemmas.
One inequality, three uses: anytime-valid edge test, Lundberg breach bound, no-edge target hurdle.
-/
import Mathlib.Probability.Martingale.OptionalStopping
import Mathlib.Probability.Martingale.BorelCantelli
import Mathlib.MeasureTheory.Function.ConditionalExpectation.Real
import Mathlib.Analysis.SpecialFunctions.Log.Basic
import Mathlib.Analysis.SpecialFunctions.Exp

open MeasureTheory Filter Finset
open scoped ENNReal

namespace PerpChief.Ville

variable {Ω : Type*} {m0 : MeasurableSpace Ω} {μ : Measure Ω} [IsProbabilityMeasure μ]
  {ℱ : Filtration ℕ m0}

/-- V1. Finite-horizon Ville inequality for a nonnegative supermartingale. -/
theorem ville_finite {W : ℕ → Ω → ℝ} (hW : Supermartingale W ℱ μ) (hnn : ∀ n ω, 0 ≤ W n ω)
    {c : ℝ} (hc : 0 < c) (N : ℕ) :
    μ {ω | ∃ n ≤ N, c ≤ W n ω} ≤ ENNReal.ofReal ((∫ ω, W 0 ω ∂μ) / c) := by
  classical
  set τ := leastGE W c N with hτdef
  have hτstop : IsStoppingTime ℱ τ := hW.adapted.isStoppingTime_leastGE c N
  have hτle : ∀ ω, τ ω ≤ N := fun ω => leastGE_le ω
  have hWneg : Submartingale (-W) ℱ μ := hW.neg
  have hstop_int : Integrable (stoppedValue W τ) μ :=
    integrable_stoppedValue ℕ hτstop hW.integrable hτle
  have hexp : ∫ ω, stoppedValue W τ ω ∂μ ≤ ∫ ω, W 0 ω ∂μ := by
    have hmono := hWneg.expected_stoppedValue_mono (isStoppingTime_const ℱ 0) hτstop
      (fun ω => Nat.zero_le (τ ω)) hτle
    have h1 : stoppedValue (-W) (fun _ => 0) = -W 0 := stoppedValue_const (-W) 0
    have h2 : stoppedValue (-W) τ = -stoppedValue W τ := by
      funext ω
      simp [stoppedValue]
    rw [h1, h2] at hmono
    have h3 : (∫ ω, (-W 0) ω ∂μ) = -∫ ω, W 0 ω ∂μ := by
      simp only [Pi.neg_apply]
      exact integral_neg _
    have h4 : (∫ ω, (-stoppedValue W τ) ω ∂μ) = -∫ ω, stoppedValue W τ ω ∂μ := by
      simp only [Pi.neg_apply]
      exact integral_neg _
    rw [h3, h4] at hmono
    exact neg_le_neg_iff.mp hmono
  have hm : ∀ n, MeasurableSet {ω | c ≤ W n ω} := by
    intro n
    exact ℱ.le n _ (measurableSet_le measurable_const (hW.stronglyMeasurable n).measurable)
  have hAmeas : MeasurableSet {ω | ∃ n ≤ N, c ≤ W n ω} := by
    have hset : {ω | ∃ n ≤ N, c ≤ W n ω} = ⋃ n, ⋃ _ : n ≤ N, {ω | c ≤ W n ω} := by
      ext ω
      simp only [Set.mem_setOf_eq, Set.mem_iUnion, exists_prop]
    rw [hset]
    exact MeasurableSet.iUnion fun n => MeasurableSet.iUnion fun _ => hm n
  have hge : ∀ ω ∈ {ω | ∃ n ≤ N, c ≤ W n ω}, c ≤ stoppedValue W τ ω := by
    intro ω hω
    obtain ⟨n, hnN, hcn⟩ := hω
    have hex : ∃ j ∈ Set.Icc 0 N, W j ω ∈ Set.Ici c := ⟨n, ⟨Nat.zero_le _, hnN⟩, hcn⟩
    have hmem := hitting_mem_set (u := W) (s := Set.Ici c) (n := 0) (m := N) hex
    exact hmem
  have hAge : c * (μ {ω | ∃ n ≤ N, c ≤ W n ω}).toReal ≤ ∫ ω, stoppedValue W τ ω ∂μ :=
    le_trans (setIntegral_ge_of_const_le hAmeas (measure_ne_top _ _) hge hstop_int.integrableOn)
      (setIntegral_le_integral hstop_int (Eventually.of_forall fun ω => hnn _ ω))
  have htoReal : (μ {ω | ∃ n ≤ N, c ≤ W n ω}).toReal ≤ (∫ ω, W 0 ω ∂μ) / c := by
    rw [le_div_iff₀ hc]
    rw [mul_comm]
    exact le_trans hAge hexp
  calc μ {ω | ∃ n ≤ N, c ≤ W n ω} = ENNReal.ofReal (μ {ω | ∃ n ≤ N, c ≤ W n ω}).toReal :=
        (ENNReal.ofReal_toReal (measure_ne_top _ _)).symm
    _ ≤ ENNReal.ofReal ((∫ ω, W 0 ω ∂μ) / c) := ENNReal.ofReal_le_ofReal htoReal

/-- Test-by-betting capital process: the paper book's equity at fraction `lam` against null mean `m`. -/
noncomputable def capital (lam X : ℕ → Ω → ℝ) (m : ℝ) : ℕ → Ω → ℝ
  | 0 => fun _ => 1
  | n + 1 => fun ω => capital lam X m n ω * (1 + lam (n + 1) ω * (X (n + 1) ω - m))

/-- Hypotheses of the betting test. `U` exists but enters NO conclusion: the guarantee is
independent of the right tail. `B` is the liquidation/stop cap on the loss. -/
structure BettingHyp (ℱ : Filtration ℕ m0) (μ : Measure Ω) (lam X : ℕ → Ω → ℝ)
    (m B U L : ℝ) : Prop where
  X_adapted : ∀ n, StronglyMeasurable[ℱ n] (X n)
  lam_predictable : ∀ n, StronglyMeasurable[ℱ n] (lam (n + 1))
  X_lower : ∀ n ω, -B ≤ X n ω
  X_upper : ∀ n ω, X n ω ≤ U
  lam_nonneg : ∀ n ω, 0 ≤ lam n ω
  lam_le : ∀ n ω, lam n ω ≤ L
  B_m_nonneg : 0 ≤ B + m
  L_admissible : L * (B + m) ≤ 1
  null_mean : ∀ n, μ[X (n + 1) | ℱ n] ≤ᵐ[μ] fun _ => m

/-- V2a. The capital process never goes negative. -/
theorem capital_nonneg {lam X : ℕ → Ω → ℝ} {m B U L : ℝ}
    (h : BettingHyp ℱ μ lam X m B U L) (n : ℕ) (ω : Ω) : 0 ≤ capital lam X m n ω := by
  induction n with
  | zero => simp [capital]
  | succ n ih =>
    have hfac : 0 ≤ 1 + lam (n + 1) ω * (X (n + 1) ω - m) := by
      have h1 : -(B + m) ≤ X (n + 1) ω - m := by
        have hx := h.X_lower (n + 1) ω
        linarith
      have h2 : lam (n + 1) ω * (-(B + m)) ≤ lam (n + 1) ω * (X (n + 1) ω - m) :=
        mul_le_mul_of_nonneg_left h1 (h.lam_nonneg _ _)
      have h3 : lam (n + 1) ω * (B + m) ≤ 1 :=
        le_trans (mul_le_mul_of_nonneg_right (h.lam_le (n + 1) ω) h.B_m_nonneg) h.L_admissible
      have h4 : lam (n + 1) ω * (-(B + m)) = -(lam (n + 1) ω * (B + m)) := by ring
      linarith
    have hstep : capital lam X m (n + 1) ω
        = capital lam X m n ω * (1 + lam (n + 1) ω * (X (n + 1) ω - m)) := by
      simp [capital]
    rw [hstep]
    exact mul_nonneg ih hfac

lemma integrable_of_bound {f : Ω → ℝ} (hf : AEStronglyMeasurable f μ) (C : ℝ)
    (hC : ∀ ω, ‖f ω‖ ≤ C) : Integrable f μ :=
  memℒp_one_iff_integrable.mp (Memℒp.of_bound hf C (Eventually.of_forall hC))

lemma capital_adapted {lam X : ℕ → Ω → ℝ} {m B U L : ℝ} (h : BettingHyp ℱ μ lam X m B U L) :
    ∀ n, StronglyMeasurable[ℱ n] (capital lam X m n) := by
  intro n
  induction n with
  | zero =>
    have h0 : capital lam X m 0 = fun _ : Ω => (1 : ℝ) := by
      funext ω
      simp [capital]
    rw [h0]
    exact stronglyMeasurable_const
  | succ n ih =>
    have hstep : capital lam X m (n + 1)
        = fun ω => capital lam X m n ω * (1 + lam (n + 1) ω * (X (n + 1) ω - m)) := by
      funext ω
      simp [capital]
    rw [hstep]
    have hmeas : Measurable[ℱ (n + 1)]
        (fun ω => capital lam X m n ω * (1 + lam (n + 1) ω * (X (n + 1) ω - m))) := by
      refine Measurable.mul ?_ ?_
      · exact (ih.measurable).mono (ℱ.mono (Nat.le_succ n)) le_rfl
      · refine Measurable.add measurable_const ?_
        refine Measurable.mul ?_ ?_
        · exact ((h.lam_predictable n).measurable).mono (ℱ.mono (Nat.le_succ n)) le_rfl
        · exact (h.X_adapted (n + 1)).measurable.sub measurable_const
    exact hmeas.stronglyMeasurable

lemma betting_X_abs_le {lam X : ℕ → Ω → ℝ} {m B U L : ℝ} (h : BettingHyp ℱ μ lam X m B U L) :
    ∀ n ω, |X n ω| ≤ |B| + |U| := by
  intro n ω
  rw [abs_le]
  constructor
  · have h1 := h.X_lower n ω
    have h2 := neg_abs_le B
    have h3 : (0 : ℝ) ≤ |U| := abs_nonneg U
    have h4 := le_abs_self B
    linarith
  · have h1 := h.X_upper n ω
    have h2 := le_abs_self U
    have h3 : (0 : ℝ) ≤ |B| := abs_nonneg B
    linarith

lemma betting_X_integrable {lam X : ℕ → Ω → ℝ} {m B U L : ℝ} (h : BettingHyp ℱ μ lam X m B U L) :
    ∀ n, Integrable (X n) μ := by
  intro n
  refine integrable_of_bound (((h.X_adapted n).mono (ℱ.le n)).aestronglyMeasurable) (|B| + |U|) ?_
  intro ω
  rw [Real.norm_eq_abs]
  exact betting_X_abs_le h n ω

lemma capital_factor_aestronglyMeasurable {lam X : ℕ → Ω → ℝ} {m B U L : ℝ}
    (h : BettingHyp ℱ μ lam X m B U L) (n : ℕ) :
    AEStronglyMeasurable (fun ω => 1 + lam (n + 1) ω * (X (n + 1) ω - m)) μ := by
  have hmeas : Measurable[ℱ (n + 1)]
      (fun ω => 1 + lam (n + 1) ω * (X (n + 1) ω - m)) := by
    refine Measurable.add measurable_const ?_
    refine Measurable.mul ?_ ?_
    · exact ((h.lam_predictable n).measurable).mono (ℱ.mono (Nat.le_succ n)) le_rfl
    · exact (h.X_adapted (n + 1)).measurable.sub measurable_const
  exact ((hmeas.stronglyMeasurable).mono (ℱ.le (n + 1))).aestronglyMeasurable

lemma capital_factor_bound {lam X : ℕ → Ω → ℝ} {m B U L : ℝ} (h : BettingHyp ℱ μ lam X m B U L) :
    ∀ n ω, ‖1 + lam (n + 1) ω * (X (n + 1) ω - m)‖ ≤ 1 + |L| * (|B| + |U| + |m|) := by
  intro n ω
  have hlam : |lam (n + 1) ω| ≤ |L| := by
    rw [abs_of_nonneg (h.lam_nonneg _ _)]
    exact le_trans (h.lam_le _ _) (le_abs_self L)
  have hXm : |X (n + 1) ω - m| ≤ |B| + |U| + |m| :=
    le_trans (abs_sub _ _) (add_le_add_right (betting_X_abs_le h (n + 1) ω) |m|)
  have hprod : ‖lam (n + 1) ω * (X (n + 1) ω - m)‖ ≤ |L| * (|B| + |U| + |m|) := by
    change |lam (n + 1) ω * (X (n + 1) ω - m)| ≤ |L| * (|B| + |U| + |m|)
    rw [abs_mul]
    exact mul_le_mul hlam hXm (abs_nonneg _) (abs_nonneg _)
  calc ‖1 + lam (n + 1) ω * (X (n + 1) ω - m)‖
      ≤ ‖(1 : ℝ)‖ + ‖lam (n + 1) ω * (X (n + 1) ω - m)‖ := norm_add_le _ _
    _ = 1 + ‖lam (n + 1) ω * (X (n + 1) ω - m)‖ := by rw [norm_one]
    _ ≤ 1 + |L| * (|B| + |U| + |m|) := add_le_add_left hprod 1

lemma capital_integrable {lam X : ℕ → Ω → ℝ} {m B U L : ℝ} (h : BettingHyp ℱ μ lam X m B U L) :
    ∀ n, Integrable (capital lam X m n) μ := by
  intro n
  induction n with
  | zero =>
    have h0 : capital lam X m 0 = fun _ : Ω => (1 : ℝ) := by
      funext ω
      simp [capital]
    rw [h0]
    exact integrable_const 1
  | succ n ih =>
    have hstep : capital lam X m (n + 1)
        = fun ω => (1 + lam (n + 1) ω * (X (n + 1) ω - m)) * capital lam X m n ω := by
      funext ω
      simp [capital]
      ring
    rw [hstep]
    exact Integrable.bdd_mul ih (capital_factor_aestronglyMeasurable h n)
      ⟨1 + |L| * (|B| + |U| + |m|), capital_factor_bound h n⟩

/-- V2b. Under the null it is a supermartingale. -/
theorem capital_supermartingale {lam X : ℕ → Ω → ℝ} {m B U L : ℝ}
    (h : BettingHyp ℱ μ lam X m B U L) : Supermartingale (capital lam X m) ℱ μ := by
  refine supermartingale_nat (capital_adapted h) (capital_integrable h) fun n => ?_
  have hAint : Integrable (capital lam X m n) μ := capital_integrable h n
  have hAint1 : Integrable (capital lam X m (n + 1)) μ := capital_integrable h (n + 1)
  have hXint : Integrable (X (n + 1)) μ := betting_X_integrable h (n + 1)
  have hstep : ∀ ω, capital lam X m (n + 1) ω
      = capital lam X m n ω + (capital lam X m n ω * lam (n + 1) ω) * (X (n + 1) ω - m) := by
    intro ω
    have hs : capital lam X m (n + 1) ω
        = capital lam X m n ω * (1 + lam (n + 1) ω * (X (n + 1) ω - m)) := by
      simp [capital]
    rw [hs]
    ring
  have hξZint : Integrable
      (fun ω => (capital lam X m n ω * lam (n + 1) ω) * (X (n + 1) ω - m)) μ := by
    have hdiff : (fun ω => (capital lam X m n ω * lam (n + 1) ω) * (X (n + 1) ω - m))
        = (fun ω => capital lam X m (n + 1) ω - capital lam X m n ω) := by
      funext ω
      rw [hstep ω]
      ring
    rw [hdiff]
    exact hAint1.sub hAint
  have hZint : Integrable (fun ω => X (n + 1) ω - m) μ := hXint.sub (integrable_const m)
  have hξmeas : StronglyMeasurable[ℱ n] (fun ω => capital lam X m n ω * lam (n + 1) ω) :=
    ((capital_adapted h n).measurable.mul (h.lam_predictable n).measurable).stronglyMeasurable
  have hpull : μ[(fun ω => (capital lam X m n ω * lam (n + 1) ω) * (X (n + 1) ω - m)) | ℱ n]
      =ᵐ[μ] (fun ω => capital lam X m n ω * lam (n + 1) ω)
        * μ[(fun ω => X (n + 1) ω - m) | ℱ n] :=
    condexp_stronglyMeasurable_mul hξmeas hξZint hZint
  have hsub : μ[(fun ω => X (n + 1) ω - m) | ℱ n]
      =ᵐ[μ] fun ω => (μ[X (n + 1) | ℱ n]) ω - m := by
    have h1 : μ[(fun ω => X (n + 1) ω - m) | ℱ n]
        =ᵐ[μ] μ[X (n + 1) | ℱ n] - μ[(fun _ : Ω => m) | ℱ n] :=
      condexp_sub hXint (integrable_const m)
    refine h1.trans ?_
    filter_upwards with ω
    rw [condexp_const (ℱ.le n) (c := m)]
    rfl
  have hAeq : μ[capital lam X m n | ℱ n] = capital lam X m n :=
    condexp_of_stronglyMeasurable (ℱ.le n) (capital_adapted h n) hAint
  have hmain : μ[capital lam X m (n + 1) | ℱ n] =ᵐ[μ]
      fun ω => capital lam X m n ω
        + (capital lam X m n ω * lam (n + 1) ω) * ((μ[X (n + 1) | ℱ n]) ω - m) := by
    have e1 : μ[capital lam X m (n + 1) | ℱ n] =ᵐ[μ]
        μ[(fun ω => capital lam X m n ω
          + (capital lam X m n ω * lam (n + 1) ω) * (X (n + 1) ω - m)) | ℱ n] :=
      condexp_congr_ae (Eventually.of_forall hstep)
    have e2 : μ[(fun ω => capital lam X m n ω
          + (capital lam X m n ω * lam (n + 1) ω) * (X (n + 1) ω - m)) | ℱ n]
        =ᵐ[μ] μ[capital lam X m n | ℱ n]
          + μ[(fun ω => (capital lam X m n ω * lam (n + 1) ω) * (X (n + 1) ω - m)) | ℱ n] :=
      condexp_add hAint hξZint
    have e3 : μ[capital lam X m n | ℱ n]
          + μ[(fun ω => (capital lam X m n ω * lam (n + 1) ω) * (X (n + 1) ω - m)) | ℱ n]
        =ᵐ[μ] fun ω => capital lam X m n ω
          + (capital lam X m n ω * lam (n + 1) ω) * ((μ[X (n + 1) | ℱ n]) ω - m) := by
      have eA : μ[capital lam X m n | ℱ n] =ᵐ[μ] capital lam X m n := by
        rw [hAeq]
      have eB : μ[(fun ω => (capital lam X m n ω * lam (n + 1) ω) * (X (n + 1) ω - m)) | ℱ n]
          =ᵐ[μ] fun ω => (capital lam X m n ω * lam (n + 1) ω)
            * ((μ[X (n + 1) | ℱ n]) ω - m) :=
        hpull.trans (EventuallyEq.mul EventuallyEq.rfl hsub)
      exact eA.add eB
    exact e1.trans (e2.trans e3)
  filter_upwards [hmain, h.null_mean n] with ω hm hn
  rw [hm]
  have hnn : (0 : ℝ) ≤ capital lam X m n ω * lam (n + 1) ω :=
    mul_nonneg (capital_nonneg h n ω) (h.lam_nonneg _ _)
  have hle : (capital lam X m n ω * lam (n + 1) ω) * ((μ[X (n + 1) | ℱ n]) ω - m) ≤ 0 :=
    mul_nonpos_of_nonneg_of_nonpos hnn (sub_nonpos.mpr hn)
  linarith

/-- V3. Anytime-valid test: P(capital EVER reaches 1/α within N) ≤ α, for every N, with peeking. -/
theorem capital_ville {lam X : ℕ → Ω → ℝ} {m B U L : ℝ}
    (h : BettingHyp ℱ μ lam X m B U L) {α : ℝ} (hα : 0 < α) (N : ℕ) :
    μ {ω | ∃ n ≤ N, 1 / α ≤ capital lam X m n ω} ≤ ENNReal.ofReal α := by
  have hbound := ville_finite (capital_supermartingale h) (fun n ω => capital_nonneg h n ω)
    (c := 1 / α) (div_pos one_pos hα) N
  have hInt : (∫ ω, capital lam X m 0 ω ∂μ) = 1 := by
    have h0 : capital lam X m 0 = fun _ : Ω => (1 : ℝ) := by
      funext ω
      simp [capital]
    rw [h0]
    simp
  rw [hInt, one_div_one_div] at hbound
  exact hbound

/-- V4. No parameter to tune: an average of supermartingales is a supermartingale. -/
theorem mix_supermartingale {K : ℕ} (hK : 0 < K) {W : Fin K → ℕ → Ω → ℝ}
    (hW : ∀ i, Supermartingale (W i) ℱ μ) :
    Supermartingale (fun n ω => (∑ i, W i n ω) / K) ℱ μ := by
  have hsum : ∀ s : Finset (Fin K), Supermartingale (fun n ω => ∑ i ∈ s, W i n ω) ℱ μ := by
    intro s
    induction s using Finset.induction with
    | empty =>
      have hEq : (fun n ω => ∑ i ∈ (∅ : Finset (Fin K)), W i n ω) = (0 : ℕ → Ω → ℝ) := by
        funext n ω
        simp
      rw [hEq]
      exact (martingale_zero ℝ ℱ μ).supermartingale
    | @insert a s has ih =>
      have hEq : (fun n ω => ∑ i ∈ insert a s, W i n ω)
          = (W a + fun n ω => ∑ i ∈ s, W i n ω) := by
        funext n ω
        simp [Finset.sum_insert has]
      rw [hEq]
      exact (hW a).add ih
  have hM : (fun n ω => (∑ i, W i n ω) / K)
      = (K : ℝ)⁻¹ • (fun n ω => ∑ i, W i n ω) := by
    funext n ω
    simp [Pi.smul_apply, div_eq_inv_mul]
  rw [hM]
  exact Supermartingale.smul_nonneg (inv_nonneg.mpr (Nat.cast_nonneg K)) (hsum Finset.univ)

/-- V5. Pathwise regret of the mixture against the best fraction in hindsight: log K. -/
theorem mix_log_regret {K : ℕ} (hK : 0 < K) {w : Fin K → ℝ} (hw : ∀ i, 0 < w i) (j : Fin K) :
    Real.log (w j) - Real.log K ≤ Real.log ((∑ i, w i) / K) := by
  have hKpos : (0 : ℝ) < K := by exact_mod_cast hK
  have hle : w j ≤ ∑ i, w i :=
    Finset.single_le_sum (fun i _ => (hw i).le) (Finset.mem_univ j)
  have hdiv : w j / K ≤ (∑ i, w i) / K := by
    exact div_le_div_of_nonneg_right hle hKpos.le
  calc Real.log (w j) - Real.log K = Real.log (w j / K) := by
        rw [Real.log_div (hw j).ne' hKpos.ne']
    _ ≤ Real.log ((∑ i, w i) / K) :=
        Real.log_le_log (div_pos (hw j) hKpos) hdiv

/-- Running PnL. -/
noncomputable def S (X : ℕ → Ω → ℝ) (n : ℕ) (ω : Ω) : ℝ := ∑ k ∈ range n, X (k + 1) ω

lemma X_abs_le_of_bounds {X : ℕ → Ω → ℝ} {B U : ℝ} (hlo : ∀ n ω, -B ≤ X n ω)
    (hhi : ∀ n ω, X n ω ≤ U) : ∀ n ω, |X n ω| ≤ |B| + |U| := by
  intro n ω
  rw [abs_le]
  constructor
  · have h1 := hlo n ω
    have h2 := neg_abs_le B
    have h3 : (0 : ℝ) ≤ |U| := abs_nonneg U
    have h4 := le_abs_self B
    linarith
  · have h1 := hhi n ω
    have h2 := le_abs_self U
    have h3 : (0 : ℝ) ≤ |B| := abs_nonneg B
    linarith

lemma X_integrable_of_bounds {X : ℕ → Ω → ℝ} {B U : ℝ}
    (hX : ∀ n, StronglyMeasurable[ℱ n] (X n)) (hlo : ∀ n ω, -B ≤ X n ω)
    (hhi : ∀ n ω, X n ω ≤ U) : ∀ n, Integrable (X n) μ := by
  intro n
  refine integrable_of_bound (((hX n).mono (ℱ.le n)).aestronglyMeasurable) (|B| + |U|) ?_
  intro ω
  rw [Real.norm_eq_abs]
  exact X_abs_le_of_bounds hlo hhi n ω

lemma S_succ {X : ℕ → Ω → ℝ} (n : ℕ) (ω : Ω) : S X (n + 1) ω = S X n ω + X (n + 1) ω := by
  simp [S, Finset.sum_range_succ]

lemma S_measurable {X : ℕ → Ω → ℝ} (hX : ∀ n, StronglyMeasurable[ℱ n] (X n)) :
    ∀ n, StronglyMeasurable[ℱ n] (S X n) := by
  intro n
  induction n with
  | zero =>
    have h0 : S X 0 = fun _ : Ω => (0 : ℝ) := by
      funext ω
      simp [S]
    rw [h0]
    exact stronglyMeasurable_const
  | succ n ih =>
    have hstep : S X (n + 1) = fun ω => S X n ω + X (n + 1) ω := by
      funext ω
      exact S_succ n ω
    rw [hstep]
    have hmeas : Measurable[ℱ (n + 1)] (fun ω => S X n ω + X (n + 1) ω) :=
      Measurable.add ((ih.measurable).mono (ℱ.mono (Nat.le_succ n)) le_rfl)
        (hX (n + 1)).measurable
    exact hmeas.stronglyMeasurable

lemma S_abs_le {X : ℕ → Ω → ℝ} {B U : ℝ} (hlo : ∀ n ω, -B ≤ X n ω) (hhi : ∀ n ω, X n ω ≤ U) :
    ∀ n ω, |S X n ω| ≤ n * (|B| + |U|) := by
  intro n ω
  have hC : (0 : ℝ) ≤ |B| + |U| := add_nonneg (abs_nonneg _) (abs_nonneg _)
  calc |S X n ω| = |∑ k ∈ Finset.range n, X (k + 1) ω| := rfl
    _ ≤ ∑ k ∈ Finset.range n, |X (k + 1) ω| := Finset.abs_sum_le_sum_abs _ _
    _ ≤ ∑ _k ∈ Finset.range n, (|B| + |U|) :=
        Finset.sum_le_sum fun k _ => X_abs_le_of_bounds hlo hhi (k + 1) ω
    _ = n * (|B| + |U|) := by rw [Finset.sum_const, Finset.card_range, nsmul_eq_mul]

/-- V6. Lundberg breach bound. A capped left tail makes θ exist even when the right tail has
no fourth moment (Hill α≈3). -/
theorem lundberg {X : ℕ → Ω → ℝ} {B U θ : ℝ} (hθ : 0 < θ)
    (hX : ∀ n, StronglyMeasurable[ℱ n] (X n)) (hlo : ∀ n ω, -B ≤ X n ω) (hhi : ∀ n ω, X n ω ≤ U)
    (hnull : ∀ n, μ[fun ω => Real.exp (-θ * X (n + 1) ω) | ℱ n] ≤ᵐ[μ] fun _ => 1)
    (D : ℝ) (N : ℕ) :
    μ {ω | ∃ n ≤ N, S X n ω ≤ -D} ≤ ENNReal.ofReal (Real.exp (-θ * D)) := by
  classical
  set W : ℕ → Ω → ℝ := fun n ω => Real.exp (-θ * S X n ω) with hWdef
  have hC : (0 : ℝ) ≤ |B| + |U| := add_nonneg (abs_nonneg _) (abs_nonneg _)
  have hWadapted : ∀ n, StronglyMeasurable[ℱ n] (W n) := by
    intro n
    have hmeas : Measurable[ℱ n] (fun ω => Real.exp (-θ * S X n ω)) :=
      Real.measurable_exp.comp (Measurable.const_mul (S_measurable hX n).measurable (-θ))
    exact hmeas.stronglyMeasurable
  have hWbound : ∀ n ω, ‖W n ω‖ ≤ Real.exp (θ * n * (|B| + |U|)) := by
    intro n ω
    have h1 : -θ * S X n ω ≤ θ * n * (|B| + |U|) := by
      have h2 : -θ * S X n ω ≤ θ * |S X n ω| := by
        have e : -θ * S X n ω = θ * (-S X n ω) := by ring
        rw [e]
        exact mul_le_mul_of_nonneg_left (neg_le_abs _) hθ.le
      have h3 : θ * |S X n ω| ≤ θ * (n * (|B| + |U|)) :=
        mul_le_mul_of_nonneg_left (S_abs_le hlo hhi n ω) hθ.le
      have e2 : θ * (n * (|B| + |U|)) = θ * n * (|B| + |U|) := by ring
      linarith
    have h4 : W n ω = Real.exp (-θ * S X n ω) := rfl
    rw [h4]
    change |Real.exp (-θ * S X n ω)| ≤ Real.exp (θ * n * (|B| + |U|))
    rw [abs_of_pos (Real.exp_pos _)]
    exact Real.exp_le_exp.mpr h1
  have hWint : ∀ n, Integrable (W n) μ := by
    intro n
    refine integrable_of_bound (((hWadapted n).mono (ℱ.le n)).aestronglyMeasurable)
      (Real.exp (θ * n * (|B| + |U|))) ?_
    intro ω
    exact hWbound n ω
  have hgint : ∀ n, Integrable (fun ω => Real.exp (-θ * X (n + 1) ω)) μ := by
    intro n
    have hmeas : Measurable (fun ω => Real.exp (-θ * X (n + 1) ω)) :=
      Real.measurable_exp.comp
        (Measurable.const_mul (((hX (n + 1)).mono (ℱ.le (n + 1))).measurable) (-θ))
    refine integrable_of_bound hmeas.aestronglyMeasurable (Real.exp (θ * (|B| + |U|))) ?_
    intro ω
    change |Real.exp (-θ * X (n + 1) ω)| ≤ Real.exp (θ * (|B| + |U|))
    rw [abs_of_pos (Real.exp_pos _)]
    refine Real.exp_le_exp.mpr ?_
    have h2 : -θ * X (n + 1) ω ≤ θ * |X (n + 1) ω| := by
      have e : -θ * X (n + 1) ω = θ * (-X (n + 1) ω) := by ring
      rw [e]
      exact mul_le_mul_of_nonneg_left (neg_le_abs _) hθ.le
    have h3 : θ * |X (n + 1) ω| ≤ θ * (|B| + |U|) :=
      mul_le_mul_of_nonneg_left (X_abs_le_of_bounds hlo hhi (n + 1) ω) hθ.le
    linarith
  have hWsup : Supermartingale W ℱ μ := by
    refine supermartingale_nat hWadapted hWint fun n => ?_
    have hfac : ∀ ω, W (n + 1) ω = W n ω * Real.exp (-θ * X (n + 1) ω) := by
      intro ω
      have hS : S X (n + 1) ω = S X n ω + X (n + 1) ω := S_succ n ω
      have e1 : W (n + 1) ω = Real.exp (-θ * S X (n + 1) ω) := rfl
      have e2 : W n ω = Real.exp (-θ * S X n ω) := rfl
      rw [e1, e2, hS]
      have e3 : -θ * (S X n ω + X (n + 1) ω) = -θ * S X n ω + -θ * X (n + 1) ω := by ring
      rw [e3, Real.exp_add]
    have hprodint : Integrable (fun ω => W n ω * Real.exp (-θ * X (n + 1) ω)) μ := by
      have heq : (fun ω => W n ω * Real.exp (-θ * X (n + 1) ω)) = W (n + 1) := by
        funext ω
        exact (hfac ω).symm
      rw [heq]
      exact hWint (n + 1)
    have hpull : μ[(fun ω => W n ω * Real.exp (-θ * X (n + 1) ω)) | ℱ n]
        =ᵐ[μ] W n * μ[(fun ω => Real.exp (-θ * X (n + 1) ω)) | ℱ n] :=
      condexp_stronglyMeasurable_mul (hWadapted n) hprodint (hgint n)
    have hmain : μ[W (n + 1) | ℱ n] =ᵐ[μ] W n * μ[(fun ω => Real.exp (-θ * X (n + 1) ω)) | ℱ n] :=
      (condexp_congr_ae (Eventually.of_forall hfac)).trans hpull
    filter_upwards [hmain, hnull n] with ω hm hn
    rw [hm]
    have hnn : (0 : ℝ) ≤ W n ω := by
      have e : W n ω = Real.exp (-θ * S X n ω) := rfl
      rw [e]
      exact (Real.exp_pos _).le
    calc W n ω * (μ[fun ω => Real.exp (-θ * X (n + 1) ω) | ℱ n]) ω
        ≤ W n ω * 1 := mul_le_mul_of_nonneg_left hn hnn
      _ = W n ω := mul_one _
  have hWnn : ∀ n ω, 0 ≤ W n ω := by
    intro n ω
    have e : W n ω = Real.exp (-θ * S X n ω) := rfl
    rw [e]
    exact (Real.exp_pos _).le
  have hW0int : (∫ ω, W 0 ω ∂μ) = 1 := by
    have h0 : W 0 = fun _ : Ω => (1 : ℝ) := by
      funext ω
      have e : W 0 ω = Real.exp (-θ * S X 0 ω) := rfl
      rw [e]
      simp [S]
    rw [h0]
    simp
  have hbound := ville_finite hWsup hWnn (c := Real.exp (θ * D)) (Real.exp_pos _) N
  rw [hW0int] at hbound
  have hexp : (1 : ℝ) / Real.exp (θ * D) = Real.exp (-θ * D) := by
    rw [one_div, ← Real.exp_neg]
    congr 1
    ring
  rw [hexp] at hbound
  refine le_trans (measure_mono ?_) hbound
  intro ω hω
  obtain ⟨n, hnN, hnS⟩ := hω
  refine ⟨n, hnN, ?_⟩
  have h2 : θ * S X n ω ≤ θ * (-D) := mul_le_mul_of_nonneg_left hnS hθ.le
  have h3 : θ * D ≤ -θ * S X n ω := by
    have e1 : -θ * S X n ω = -(θ * S X n ω) := by ring
    have e2 : θ * (-D) = -(θ * D) := by ring
    rw [e1]
    linarith
  have e : W n ω = Real.exp (-θ * S X n ω) := rfl
  rw [e]
  exact Real.exp_le_exp.mpr h3

/-- V7. The exact price of gross: scaling the book by G divides the Lundberg exponent by G. -/
theorem lundberg_gross {X : ℕ → Ω → ℝ} {B U θ G : ℝ} (hθ : 0 < θ) (hG : 0 < G)
    (hX : ∀ n, StronglyMeasurable[ℱ n] (X n)) (hlo : ∀ n ω, -B ≤ X n ω) (hhi : ∀ n ω, X n ω ≤ U)
    (hnull : ∀ n, μ[fun ω => Real.exp (-θ * X (n + 1) ω) | ℱ n] ≤ᵐ[μ] fun _ => 1)
    (D : ℝ) (N : ℕ) :
    μ {ω | ∃ n ≤ N, G * S X n ω ≤ -D} ≤ ENNReal.ofReal (Real.exp (-θ * D / G)) := by
  have h := lundberg hθ hX hlo hhi hnull (D / G) N
  have hset : {ω | ∃ n ≤ N, G * S X n ω ≤ -D} = {ω | ∃ n ≤ N, S X n ω ≤ -(D / G)} := by
    ext ω
    constructor
    · rintro ⟨n, hnN, hn⟩
      refine ⟨n, hnN, ?_⟩
      have e : -(D / G) = -D / G := by ring
      rw [e, le_div_iff₀ hG]
      rw [mul_comm]
      exact hn
    · rintro ⟨n, hnN, hn⟩
      refine ⟨n, hnN, ?_⟩
      have e : -(D / G) = -D / G := by ring
      rw [e, le_div_iff₀ hG] at hn
      rw [mul_comm]
      exact hn
  have hexp : Real.exp (-θ * (D / G)) = Real.exp (-θ * D / G) := by
    congr 1
    ring
  rw [hset]
  rw [hexp] at h
  exact h

/-- The account has not breached through step n. -/
def alive (X : ℕ → Ω → ℝ) (D : ℝ) (n : ℕ) (ω : Ω) : Prop := ∀ k ≤ n, -D < S X k ω

/-- Gated running PnL: accumulates `X (k + 1)` only while the account was alive at `k`. -/
noncomputable def gated (X : ℕ → Ω → ℝ) (D : ℝ) : ℕ → Ω → ℝ
  | 0 => fun _ => 0
  | n + 1 => fun ω => gated X D n ω + {ω | alive X D n ω}.indicator (X (n + 1)) ω

lemma gated_zero (X : ℕ → Ω → ℝ) (D : ℝ) : gated X D 0 = fun _ : Ω => (0 : ℝ) := rfl

lemma gated_succ (X : ℕ → Ω → ℝ) (D : ℝ) (n : ℕ) (ω : Ω) :
    gated X D (n + 1) ω = gated X D n ω + {ω | alive X D n ω}.indicator (X (n + 1)) ω := rfl

lemma alive_measurableSet {X : ℕ → Ω → ℝ} {D : ℝ} (hX : ∀ n, StronglyMeasurable[ℱ n] (X n))
    (hD : 0 < D) : ∀ n, MeasurableSet[ℱ n] {ω | alive X D n ω} := by
  intro n
  induction n with
  | zero =>
    have hset : {ω | alive X D 0 ω} = Set.univ := by
      ext ω
      simp only [Set.mem_setOf_eq, Set.mem_univ, iff_true]
      intro k hk
      have hk0 : k = 0 := Nat.le_zero.mp hk
      rw [hk0]
      have hS0 : S X 0 ω = 0 := by simp [S]
      rw [hS0]
      linarith
    rw [hset]
    exact MeasurableSet.univ
  | succ n ih =>
    have hset : {ω | alive X D (n + 1) ω}
        = {ω | alive X D n ω} ∩ {ω | -D < S X (n + 1) ω} := by
      ext ω
      constructor
      · intro h
        exact ⟨fun k hk => h k (le_trans hk (Nat.le_succ n)), h (n + 1) le_rfl⟩
      · rintro ⟨h1, h2⟩ k hk
        by_cases hkn : k = n + 1
        · rw [hkn]
          exact h2
        · have hk' : k ≤ n := by omega
          exact h1 k hk'
    rw [hset]
    exact (ℱ.mono (Nat.le_succ n) _ ih).inter
      (measurableSet_lt measurable_const (S_measurable hX (n + 1)).measurable)

lemma gated_measurable {X : ℕ → Ω → ℝ} {D : ℝ} (hX : ∀ n, StronglyMeasurable[ℱ n] (X n))
    (hD : 0 < D) : ∀ n, StronglyMeasurable[ℱ n] (gated X D n) := by
  intro n
  induction n with
  | zero =>
    rw [gated_zero]
    exact stronglyMeasurable_const
  | succ n ih =>
    have hstep : gated X D (n + 1)
        = fun ω => gated X D n ω + {ω | alive X D n ω}.indicator (X (n + 1)) ω := by
      funext ω
      exact gated_succ X D n ω
    rw [hstep]
    have hmeas : Measurable[ℱ (n + 1)]
        (fun ω => gated X D n ω + {ω | alive X D n ω}.indicator (X (n + 1)) ω) := by
      refine Measurable.add ((ih.measurable).mono (ℱ.mono (Nat.le_succ n)) le_rfl) ?_
      refine Measurable.indicator (hX (n + 1)).measurable ?_
      exact ℱ.mono (Nat.le_succ n) _
        ((alive_measurableSet hX hD n))
    exact hmeas.stronglyMeasurable

lemma gated_eq_S_of_alive {X : ℕ → Ω → ℝ} {D : ℝ} :
    ∀ n ω, alive X D n ω → gated X D n ω = S X n ω := by
  intro n
  induction n with
  | zero =>
    intro ω _
    have e1 : gated X D 0 ω = 0 := rfl
    have e2 : S X 0 ω = 0 := by simp [S]
    rw [e1, e2]
  | succ n ih =>
    intro ω halive
    have halive_n : alive X D n ω := fun k hk => halive k (le_trans hk (Nat.le_succ n))
    rw [gated_succ, ih ω halive_n, Set.indicator_of_mem halive_n]
    exact (S_succ n ω).symm

lemma gated_abs_le {X : ℕ → Ω → ℝ} {D B U : ℝ} (hlo : ∀ n ω, -B ≤ X n ω)
    (hhi : ∀ n ω, X n ω ≤ U) : ∀ n ω, |gated X D n ω| ≤ n * (|B| + |U|) := by
  intro n
  induction n with
  | zero =>
    intro ω
    have e : gated X D 0 ω = 0 := rfl
    rw [e]
    simp
  | succ n ih =>
    intro ω
    have hC : (0 : ℝ) ≤ |B| + |U| := add_nonneg (abs_nonneg _) (abs_nonneg _)
    rw [gated_succ]
    have hind : |{ω | alive X D n ω}.indicator (X (n + 1)) ω| ≤ |B| + |U| := by
      by_cases hmem : ω ∈ {ω | alive X D n ω}
      · rw [Set.indicator_of_mem hmem]
        exact X_abs_le_of_bounds hlo hhi (n + 1) ω
      · rw [Set.indicator_of_not_mem hmem]
        simp [hC]
    have hcast : ((n + 1 : ℕ) : ℝ) * (|B| + |U|) = n * (|B| + |U|) + (|B| + |U|) := by
      push_cast
      ring
    rw [hcast]
    exact le_trans (abs_add _ _) (add_le_add (ih ω) hind)

lemma gated_integrable {X : ℕ → Ω → ℝ} {D B U : ℝ} (hX : ∀ n, StronglyMeasurable[ℱ n] (X n))
    (hD : 0 < D) (hlo : ∀ n ω, -B ≤ X n ω) (hhi : ∀ n ω, X n ω ≤ U) :
    ∀ n, Integrable (gated X D n) μ := by
  intro n
  refine integrable_of_bound (((gated_measurable hX hD n).mono (ℱ.le n)).aestronglyMeasurable)
    (n * (|B| + |U|)) ?_
  intro ω
  rw [Real.norm_eq_abs]
  exact gated_abs_le hlo hhi n ω

/-- V8. No-edge hurdle: with no drift, P(+T before −D) ≤ (D+B)/(T+D+B), overshoot B included.
Frame B ($1000 before $300, B→0) recovers the programme's 23.08%. So a success rate above this
hurdle is itself evidence of drift: the eval objective becomes a test. -/
theorem hurdle {X : ℕ → Ω → ℝ} {T D B U : ℝ} (hT : 0 < T) (hD : 0 < D) (hB : 0 ≤ B)
    (hX : ∀ n, StronglyMeasurable[ℱ n] (X n)) (hlo : ∀ n ω, -B ≤ X n ω) (hhi : ∀ n ω, X n ω ≤ U)
    (hnull : ∀ n, μ[X (n + 1) | ℱ n] ≤ᵐ[μ] fun _ => 0) (N : ℕ) :
    μ {ω | ∃ n ≤ N, T ≤ S X n ω ∧ alive X D n ω} ≤ ENNReal.ofReal ((D + B) / (T + D + B)) := by
  classical
  set Y : ℕ → Ω → ℝ := fun n ω => D + B + gated X D n ω with hYdef
  have hYadapted : ∀ n, StronglyMeasurable[ℱ n] (Y n) := by
    intro n
    have hmeas : Measurable[ℱ n] (fun ω => D + B + gated X D n ω) :=
      Measurable.add measurable_const (gated_measurable hX hD n).measurable
    exact hmeas.stronglyMeasurable
  have hYint : ∀ n, Integrable (Y n) μ := by
    intro n
    have heq : Y n = fun ω => (D + B) + gated X D n ω := rfl
    rw [heq]
    exact (integrable_const (D + B)).add (gated_integrable hX hD hlo hhi n)
  have hYnn : ∀ n ω, 0 ≤ Y n ω := by
    intro n
    induction n with
    | zero =>
      intro ω
      have e : Y 0 ω = D + B + 0 := rfl
      rw [e]
      linarith
    | succ n ih =>
      intro ω
      have hstep : Y (n + 1) ω
          = Y n ω + {ω | alive X D n ω}.indicator (X (n + 1)) ω := by
        have e1 : Y (n + 1) ω = D + B + gated X D (n + 1) ω := rfl
        have e2 : Y n ω = D + B + gated X D n ω := rfl
        rw [e1, e2, gated_succ]
        ring
      rw [hstep]
      by_cases halive : alive X D n ω
      · have hmem : ω ∈ {ω | alive X D n ω} := halive
        rw [Set.indicator_of_mem hmem]
        have hSn : -D < S X n ω := halive n le_rfl
        have hXn : -B ≤ X (n + 1) ω := hlo (n + 1) ω
        have eY : Y n ω = D + B + gated X D n ω := rfl
        rw [eY, gated_eq_S_of_alive n ω halive]
        linarith
      · have hmem : ω ∉ {ω | alive X D n ω} := halive
        rw [Set.indicator_of_not_mem hmem, add_zero]
        exact ih ω
  have hYsup : Supermartingale Y ℱ μ := by
    refine supermartingale_nat hYadapted hYint fun n => ?_
    have hYintn : Integrable (Y n) μ := hYint n
    have hXint : Integrable (X (n + 1)) μ := X_integrable_of_bounds hX hlo hhi (n + 1)
    have hindint : Integrable (fun ω => {ω | alive X D n ω}.indicator (X (n + 1)) ω) μ := by
      have hmeas : Measurable (fun ω => {ω | alive X D n ω}.indicator (X (n + 1)) ω) := by
        refine Measurable.indicator (((hX (n + 1)).mono (ℱ.le (n + 1))).measurable) ?_
        exact ℱ.le n _ (alive_measurableSet hX hD n)
      refine integrable_of_bound hmeas.aestronglyMeasurable (|B| + |U|) ?_
      intro ω
      rw [Real.norm_eq_abs]
      by_cases hmem : ω ∈ {ω | alive X D n ω}
      · rw [Set.indicator_of_mem hmem]
        exact X_abs_le_of_bounds hlo hhi (n + 1) ω
      · rw [Set.indicator_of_not_mem hmem]
        simp [add_nonneg (abs_nonneg B) (abs_nonneg U)]
    have hstep : ∀ ω, Y (n + 1) ω
        = Y n ω + {ω | alive X D n ω}.indicator (X (n + 1)) ω := by
      intro ω
      have e1 : Y (n + 1) ω = D + B + gated X D (n + 1) ω := rfl
      have e2 : Y n ω = D + B + gated X D n ω := rfl
      rw [e1, e2, gated_succ]
      ring
    have hind1 : ∀ ω, {ω | alive X D n ω}.indicator (X (n + 1)) ω
        = ({ω | alive X D n ω}.indicator (fun _ : Ω => (1 : ℝ)) ω) * X (n + 1) ω := by
      intro ω
      by_cases hmem : ω ∈ {ω | alive X D n ω}
      · rw [Set.indicator_of_mem hmem, Set.indicator_of_mem hmem]
        simp
      · rw [Set.indicator_of_not_mem hmem, Set.indicator_of_not_mem hmem]
        simp
    have hprodint : Integrable
        (fun ω => ({ω | alive X D n ω}.indicator (fun _ : Ω => (1 : ℝ)) ω) * X (n + 1) ω) μ := by
      have heq : (fun ω => ({ω | alive X D n ω}.indicator (fun _ : Ω => (1 : ℝ)) ω) * X (n + 1) ω)
          = (fun ω => {ω | alive X D n ω}.indicator (X (n + 1)) ω) := by
        funext ω
        exact (hind1 ω).symm
      rw [heq]
      exact hindint
    have h1meas : StronglyMeasurable[ℱ n]
        ({ω | alive X D n ω}.indicator (fun _ : Ω => (1 : ℝ))) := by
      have hmeas : Measurable[ℱ n] ({ω | alive X D n ω}.indicator (fun _ : Ω => (1 : ℝ))) :=
        Measurable.indicator measurable_const (alive_measurableSet hX hD n)
      exact hmeas.stronglyMeasurable
    have hpull : μ[(fun ω => ({ω | alive X D n ω}.indicator (fun _ : Ω => (1 : ℝ)) ω)
          * X (n + 1) ω) | ℱ n]
        =ᵐ[μ] ({ω | alive X D n ω}.indicator (fun _ : Ω => (1 : ℝ)))
          * μ[X (n + 1) | ℱ n] :=
      condexp_stronglyMeasurable_mul h1meas hprodint hXint
    have hmain : μ[Y (n + 1) | ℱ n] =ᵐ[μ]
        fun ω => Y n ω
          + ({ω | alive X D n ω}.indicator (fun _ : Ω => (1 : ℝ)) ω)
            * (μ[X (n + 1) | ℱ n]) ω := by
      have e1 : μ[Y (n + 1) | ℱ n] =ᵐ[μ]
          μ[(fun ω => Y n ω + {ω | alive X D n ω}.indicator (X (n + 1)) ω) | ℱ n] :=
        condexp_congr_ae (Eventually.of_forall hstep)
      have e2 : μ[(fun ω => Y n ω + {ω | alive X D n ω}.indicator (X (n + 1)) ω) | ℱ n]
          =ᵐ[μ] μ[Y n | ℱ n] + μ[(fun ω => {ω | alive X D n ω}.indicator (X (n + 1)) ω) | ℱ n] :=
        condexp_add hYintn hindint
      have e3 : μ[Y n | ℱ n] + μ[(fun ω => {ω | alive X D n ω}.indicator (X (n + 1)) ω) | ℱ n]
          =ᵐ[μ] fun ω => Y n ω
            + ({ω | alive X D n ω}.indicator (fun _ : Ω => (1 : ℝ)) ω)
              * (μ[X (n + 1) | ℱ n]) ω := by
        have eA : μ[Y n | ℱ n] =ᵐ[μ] Y n := by
          rw [condexp_of_stronglyMeasurable (ℱ.le n) (hYadapted n) hYintn]
        have eB : μ[(fun ω => {ω | alive X D n ω}.indicator (X (n + 1)) ω) | ℱ n]
            =ᵐ[μ] fun ω => ({ω | alive X D n ω}.indicator (fun _ : Ω => (1 : ℝ)) ω)
              * (μ[X (n + 1) | ℱ n]) ω := by
          have eB1 : μ[(fun ω => {ω | alive X D n ω}.indicator (X (n + 1)) ω) | ℱ n]
              =ᵐ[μ] μ[(fun ω => ({ω | alive X D n ω}.indicator (fun _ : Ω => (1 : ℝ)) ω)
                * X (n + 1) ω) | ℱ n] :=
            condexp_congr_ae (Eventually.of_forall hind1)
          exact eB1.trans hpull
        exact eA.add eB
      exact e1.trans (e2.trans e3)
    filter_upwards [hmain, hnull n] with ω hm hn
    rw [hm]
    have hindnn : (0 : ℝ) ≤ {ω | alive X D n ω}.indicator (fun _ : Ω => (1 : ℝ)) ω := by
      by_cases hmem : ω ∈ {ω | alive X D n ω}
      · rw [Set.indicator_of_mem hmem]
        norm_num
      · rw [Set.indicator_of_not_mem hmem]
    have hle : ({ω | alive X D n ω}.indicator (fun _ : Ω => (1 : ℝ)) ω)
        * (μ[X (n + 1) | ℱ n]) ω ≤ 0 :=
      mul_nonpos_of_nonneg_of_nonpos hindnn hn
    linarith
  have hcpos : (0 : ℝ) < T + D + B := by linarith
  have hbound := ville_finite hYsup hYnn (c := T + D + B) hcpos N
  have hY0int : (∫ ω, Y 0 ω ∂μ) = D + B := by
    have h0 : Y 0 = fun _ : Ω => (D + B : ℝ) := by
      funext ω
      have e : Y 0 ω = D + B + gated X D 0 ω := rfl
      rw [e]
      have e2 : gated X D 0 ω = 0 := rfl
      rw [e2, add_zero]
    rw [h0]
    simp
  rw [hY0int] at hbound
  refine le_trans (measure_mono ?_) hbound
  intro ω hω
  obtain ⟨n, hnN, hnT, hnalive⟩ := hω
  refine ⟨n, hnN, ?_⟩
  have eY : Y n ω = D + B + gated X D n ω := rfl
  rw [eY, gated_eq_S_of_alive n ω hnalive]
  linarith

/-- Non-vacuity of the hurdle arithmetic on Frame B. -/
theorem hurdle_frameB : ((300 : ℝ) + 0) / (1000 + 300 + 0) = 3 / 13 := by
  norm_num

/-- Non-vacuity: `BettingHyp` is inhabited by a real instance (flat book, null mean 0). -/
theorem bettingHyp_inhabited :
    BettingHyp ℱ μ (fun _ _ => (1 / 2 : ℝ)) (fun _ _ => (0 : ℝ)) 0 1 1 (1 / 2) := by
  refine ⟨fun _ => stronglyMeasurable_const, fun _ => stronglyMeasurable_const, fun _ _ => by norm_num,
    fun _ _ => by norm_num, fun _ _ => by norm_num, fun _ _ => by norm_num, by norm_num, by norm_num,
    fun n => ?_⟩
  have h0 : μ[(fun _ : Ω => (0 : ℝ)) | ℱ n] =ᵐ[μ] fun _ => (0 : ℝ) := by
    rw [condexp_const (ℱ.le n)]
  exact h0.le

end PerpChief.Ville
