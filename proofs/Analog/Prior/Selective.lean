/- NOT IMPORTED by Analog.lean (2026-11-12): mechanical port fails on current Mathlib APIs; registered re-proof candidate in docs/research/06-lean-corpus-inventory.md. Preserved verbatim for the re-prover. -/
/-
PORTED 2026-11-12 from owner prior work: certified abstention improves outcome
Source: andrewkoumoudjian/perps-strategy @ 0f34759, lanes/chief/lean/PerpChief/Selective.lean (toolchain v4.15.0).
Port changes ONLY: module path/import remap to Analog.Prior.* (+ Mathlib API renames if listed in docs/research/06). Namespaces, statements, proofs otherwise verbatim. Original file is frozen upstream; do not edit semantics here.
-/
/-
ROUND 4: SELECTION, THE RETURN LAW AND A CAUSAL JUMP FILTER. FROZEN STATEMENTS (chief scientist).
A. When abstaining from a set of signals raises fixed-fraction capital, on every path.
R. Only k × scale matters, and under a trailing floor δ the high-water mark obeys δ·X ≤ log(H/E0) ≤ max X / a.
J. A jump penalty caps regime switches: batch for an optimal path, pathwise for a causal hysteresis filter.
T. Boundedness of the log-score difference used to compare forecasters, and validity of the mixed test.
Says nothing about whether any signal has edge.
-/
import Analog.Prior.FrameB
import Mathlib.Data.Complex.ExponentialBounds

open MeasureTheory Filter Finset
open scoped ENNReal

namespace PerpChief.Selective

noncomputable section

open PerpChief.Leverage PerpChief.Ville PerpChief.FrameB

/-! ### A. Abstention -/

private lemma log_capital_prod {k : ℝ} {r : ℕ → ℝ} (hk : 0 < k) (T : ℕ) (hgap : ∀ t < T, -1 / k < r t) :
    0 < betCapital k r T ∧ Real.log (betCapital k r T) = ∑ t ∈ range T, Real.log (1 + k * r t) := by
  have hf : ∀ t ∈ range T, 0 < 1 + k * r t := fun t ht => by
    have := (div_lt_iff₀ hk).1 (hgap t (mem_range.1 ht))
    nlinarith
  refine ⟨prod_pos hf, ?_⟩
  unfold betCapital
  exact Real.log_prod _ _ fun t ht => (hf t ht).ne'

/-- A1. A set of steps whose mean-to-variance ratio is at most `c·k` cannot add log capital. -/
theorem abstain_log_nonpos {k ε : ℝ} {x : ℕ → ℝ} {A : Finset ℕ} (hk : 0 < k) (hε0 : 0 < ε) (hε1 : ε < 1)
    (hb : ∀ t ∈ A, |k * x t| ≤ ε)
    (hA : ∑ t ∈ A, x t ≤ (1 / 2 - ε / 3) * k * ∑ t ∈ A, x t ^ 2) :
    ∑ t ∈ A, Real.log (1 + k * x t) ≤ 0 := by
  have hterm : ∀ t ∈ A, Real.log (1 + k * x t) ≤ k * x t - (1 / 2 - ε / 3) * (k * x t) ^ 2 :=
    fun t ht => PerpChief.Ceiling.log_one_add_le_quad hε0 hε1 (hb t ht)
  have hsum := sum_le_sum hterm
  have he : ∑ t ∈ A, (k * x t - (1 / 2 - ε / 3) * (k * x t) ^ 2)
      = k * ∑ t ∈ A, x t - (1 / 2 - ε / 3) * k ^ 2 * ∑ t ∈ A, x t ^ 2 := by
    rw [sum_sub_distrib, mul_sum, mul_sum]
    congr 1
    exact sum_congr rfl fun t _ => by ring
  have hm := mul_le_mul_of_nonneg_left hA hk.le
  have hr : k * ((1 / 2 - ε / 3) * k * ∑ t ∈ A, x t ^ 2) = (1 / 2 - ε / 3) * k ^ 2 * ∑ t ∈ A, x t ^ 2 := by ring
  linarith

/-- A2. So skipping that set can only raise capital on the same path. -/
theorem abstain_improves {k ε : ℝ} {x : ℕ → ℝ} {A : Finset ℕ} {T : ℕ} (hk : 0 < k) (hε0 : 0 < ε)
    (hε1 : ε < 1) (hAT : A ⊆ range T) (hb : ∀ t ∈ A, |k * x t| ≤ ε)
    (hA : ∑ t ∈ A, x t ≤ (1 / 2 - ε / 3) * k * ∑ t ∈ A, x t ^ 2) :
    ∑ t ∈ range T, Real.log (1 + k * x t) ≤ ∑ t ∈ range T \ A, Real.log (1 + k * x t) := by
  have h1 := abstain_log_nonpos hk hε0 hε1 hb hA
  have h2 := sum_sdiff (f := fun t => Real.log (1 + k * x t)) hAT
  simp only at h2
  linarith

/-- A3. The other side: a set with mean-to-variance ratio at least `k/(1-ε)` cannot lose log capital. -/
theorem keep_log_nonneg {k ε : ℝ} {x : ℕ → ℝ} {A : Finset ℕ} (hk : 0 < k) (hε1 : ε < 1)
    (hb : ∀ t ∈ A, |k * x t| ≤ ε) (hA : k / (1 - ε) * ∑ t ∈ A, x t ^ 2 ≤ ∑ t ∈ A, x t) :
    0 ≤ ∑ t ∈ A, Real.log (1 + k * x t) := by
  have hd : 0 < 1 - ε := by linarith
  have hterm : ∀ t ∈ A, k * x t - (k * x t) ^ 2 / (1 - ε) ≤ Real.log (1 + k * x t) := fun t ht => by
    set y := k * x t with hy
    have hab := abs_le.1 (hb t ht)
    have hpos : 0 < 1 + y := by linarith [hab.1]
    have hlog := Real.one_sub_inv_le_log_of_pos hpos
    have hid : 1 - (1 + y)⁻¹ = y - y ^ 2 / (1 + y) := by
      field_simp
      ring
    have hle : y ^ 2 / (1 + y) ≤ y ^ 2 / (1 - ε) :=
      div_le_div_of_nonneg_left (sq_nonneg y) hd (by linarith [hab.1])
    linarith
  have hsum := sum_le_sum hterm
  have he : ∑ t ∈ A, (k * x t - (k * x t) ^ 2 / (1 - ε))
      = k * ∑ t ∈ A, x t - k * (k / (1 - ε) * ∑ t ∈ A, x t ^ 2) := by
    rw [sum_sub_distrib, mul_sum, mul_sum, mul_sum]
    congr 1
    refine sum_congr rfl fun t _ => ?_
    field_simp
    ring
  have hm := mul_le_mul_of_nonneg_left hA hk.le
  linarith

/-! ### R. The return law -/

variable {δ k E0 U : ℝ} {r : ℕ → ℝ}

/-- R1. Only `k × scale` matters: rescaling a book's returns by `c` and `k` by `1/c` changes nothing. -/
theorem run_scale {c : ℝ} (hc : c ≠ 0) (n : ℕ) :
    run δ (k / c) E0 (fun t => c * r t) n = run δ k E0 r n := by
  induction n with
  | zero => rfl
  | succ n ih =>
      show cstep δ (k / c) (c * r n) (run δ (k / c) E0 (fun t => c * r t) n) = cstep δ k (r n) (run δ k E0 r n)
      rw [ih]
      have h : ∀ C : ℝ, k / c * C * (c * r n) = k * C * r n := fun C => by
        field_simp
        ring
      simp only [cstep, h]

/-- R2. Floor on the high-water mark: `δ` times the free log capital. -/
theorem return_floor (hE : 0 < E0) (hδ0 : 0 < δ) (hδ1 : δ < 1) (hk : 0 < k) (T : ℕ)
    (hgap : ∀ t < T, -1 / k < r t) :
    δ * ∑ t ∈ range T, Real.log (1 + k * r t) ≤ Real.log ((run δ k E0 r T).H / E0) := by
  have hH : ∀ n, E0 ≤ (run δ k E0 r n).H := by
    intro n
    induction n with
    | zero => exact le_rfl
    | succ n ih => exact le_max_of_le_left ih
  have hlog0 : 0 ≤ Real.log ((run δ k E0 r T).H / E0) :=
    Real.log_nonneg ((one_le_div hE).2 (hH T))
  obtain ⟨hcpos, hclog⟩ := log_capital_prod hk T hgap
  set X := ∑ t ∈ range T, Real.log (1 + k * r t) with hX
  by_cases hneg : X ≤ 0
  · nlinarith
  · push_neg at hneg
    have hdX : 0 < δ * X := mul_pos hδ0 hneg
    have hexp : 1 < Real.exp (δ * X) := Real.one_lt_exp_iff.2 hdX
    have hτ : 0 < Real.exp (δ * X) - 1 := by linarith
    have hcap : (1 + (Real.exp (δ * X) - 1)) ^ (1 / δ) ≤ betCapital k r T := by
      rw [show 1 + (Real.exp (δ * X) - 1) = Real.exp (δ * X) by ring, ← Real.exp_mul,
        show δ * X * (1 / δ) = X by field_simp, ← hclog, Real.exp_log hcpos]
    have hp := capital_forces_pass hE hδ0 hδ1 hk hτ T hgap hcap
    rw [show 1 + (Real.exp (δ * X) - 1) = Real.exp (δ * X) by ring] at hp
    rw [Real.le_log_iff_exp_le (div_pos (lt_of_lt_of_le hE (hH T)) hE), le_div_iff₀ hE]
    exact hp

/-- R3. Ceiling on the high-water mark: the log capital reached on some prefix, divided by `a`. -/
theorem return_ceiling (hE : 0 < E0) (hδ0 : 0 < δ) (hδ1 : δ < 1) (hk : 0 < k) (hU : 0 < U) (n : ℕ)
    (hgap : ∀ t < n, -1 / k < r t) (hr : ∀ t < n, r t ≤ U) (hup : E0 < (run δ k E0 r n).H) :
    ∃ m ≤ n, frameExp δ (k * U) * Real.log ((run δ k E0 r n).H / E0)
      ≤ ∑ t ∈ range m, Real.log (1 + k * r t) := by
  set H := (run δ k E0 r n).H with hHdef
  have hq : 1 < H / E0 := (one_lt_div hE).2 hup
  have hτ : 0 < H / E0 - 1 := by linarith
  have hpass : (1 + (H / E0 - 1)) * E0 ≤ (run δ k E0 r n).H := by
    rw [show 1 + (H / E0 - 1) = H / E0 by ring, div_mul_cancel₀ _ hE.ne']
  obtain ⟨m, hm, hcap⟩ := pass_forces_capital hE hδ0 hδ1 hk hU hτ n hgap hr hpass
  rw [show 1 + (H / E0 - 1) = H / E0 by ring] at hcap
  refine ⟨m, hm, ?_⟩
  obtain ⟨hcpos, hclog⟩ := log_capital_prod (r := r) hk m fun t ht => hgap t (by omega)
  rw [← hclog, ← Real.log_rpow (by linarith)]
  exact Real.log_le_log (Real.rpow_pos_of_pos (by linarith) _) hcap

/-! ### J. Jump penalties -/

/-- Number of regime switches over `T` steps. -/
def switches {σ : Type*} [DecidableEq σ] (s : ℕ → σ) (T : ℕ) : ℕ :=
  ((range T).filter fun t => s (t + 1) ≠ s t).card

/-- J1. If a path is no worse than a constant path under loss plus jump penalty, its switches are capped. -/
theorem batch_switch_bound {σ : Type*} [DecidableEq σ] {ℓ : ℕ → σ → ℝ} {L pen : ℝ} {T : ℕ} (s : ℕ → σ) (a : σ)
    (hpen : 0 < pen) (hℓ0 : ∀ t b, 0 ≤ ℓ t b) (hℓ1 : ∀ t b, ℓ t b ≤ L)
    (hmin : ∑ t ∈ range (T + 1), ℓ t (s t) + pen * switches s T ≤ ∑ t ∈ range (T + 1), ℓ t a) :
    (switches s T : ℝ) ≤ (T + 1) * L / pen := by
  have hs0 : 0 ≤ ∑ t ∈ range (T + 1), ℓ t (s t) := sum_nonneg fun t _ => hℓ0 t _
  have ha : ∑ t ∈ range (T + 1), ℓ t a ≤ (T + 1) * L := by
    calc ∑ t ∈ range (T + 1), ℓ t a ≤ ∑ _t ∈ range (T + 1), L := sum_le_sum fun t _ => hℓ1 t a
      _ = (T + 1) * L := by simp
  rw [le_div_iff₀ hpen]
  linarith

/-- One step of the causal filter: evidence accumulates in `[0, pen]`, and the regime flips only at an edge. -/
def jstep (pen e : ℝ) (st : ℝ × Bool) : ℝ × Bool :=
  let y := max 0 (min pen (st.1 + e))
  (y, if pen ≤ y then true else if y ≤ 0 then false else st.2)

/-- The causal filter run on an evidence stream. -/
def jrun (pen : ℝ) (e : ℕ → ℝ) (st0 : ℝ × Bool) : ℕ → ℝ × Bool
  | 0 => st0
  | n + 1 => jstep pen (e n) (jrun pen e st0 n)

private def phi (pen : ℝ) (st : ℝ × Bool) : ℝ := if st.2 then pen - st.1 else st.1

private lemma jstep_inv {pen e y : ℝ} {s : Bool} (hpen : 0 < pen) (hy0 : 0 ≤ y) (hy1 : y ≤ pen) :
    0 ≤ (jstep pen e (y, s)).1 ∧ (jstep pen e (y, s)).1 ≤ pen ∧
      (if (jstep pen e (y, s)).2 ≠ s then pen else 0) + phi pen (jstep pen e (y, s)) ≤ phi pen (y, s) + |e| := by
  set y' := max 0 (min pen (y + e)) with hy'
  have h0 : 0 ≤ y' := le_max_left _ _
  have h1 : y' ≤ pen := max_le hpen.le (min_le_left _ _)
  have hu : y' ≤ y + |e| := max_le (by positivity) ((min_le_right _ _).trans (by linarith [le_abs_self e]))
  have hl : y - |e| ≤ y' :=
    (le_min (by linarith [abs_nonneg e]) (by linarith [neg_abs_le e])).trans (le_max_right _ _)
  have hfst : (jstep pen e (y, s)).1 = y' := rfl
  have hsnd : (jstep pen e (y, s)).2 = if pen ≤ y' then true else if y' ≤ 0 then false else s := rfl
  refine ⟨hfst ▸ h0, hfst ▸ h1, ?_⟩
  have hphi : phi pen (jstep pen e (y, s)) = if (jstep pen e (y, s)).2 then pen - y' else y' := rfl
  rw [hphi, hsnd]
  by_cases c1 : pen ≤ y'
  · cases s <;> simp [c1, phi] <;> linarith
  · by_cases c2 : y' ≤ 0
    · cases s <;> simp [c1, c2, phi] <;> linarith
    · cases s <;> simp [c1, c2, phi] <;> linarith

private lemma switches_succ {σ : Type*} [DecidableEq σ] (s : ℕ → σ) (T : ℕ) :
    (switches s (T + 1) : ℝ) = switches s T + if s (T + 1) ≠ s T then 1 else 0 := by
  unfold switches
  rw [range_succ, filter_insert]
  by_cases h : s (T + 1) ≠ s T
  · have : T ∉ (range T).filter fun t => s (t + 1) ≠ s t := by simp
    simp [h, card_insert_of_not_mem this]
  · simp [h]

/-- J2. Pathwise: each switch of the causal filter must be paid for with `pen` of absolute evidence. -/
theorem filter_switch_bound {pen : ℝ} {e : ℕ → ℝ} {st0 : ℝ × Bool} (hpen : 0 < pen) (h0 : 0 ≤ st0.1)
    (h1 : st0.1 ≤ pen) (T : ℕ) :
    (switches (fun n => (jrun pen e st0 n).2) T : ℝ) * pen ≤ pen + ∑ t ∈ range T, |e t| := by
  have hinv : ∀ n, 0 ≤ (jrun pen e st0 n).1 ∧ (jrun pen e st0 n).1 ≤ pen ∧
      (switches (fun n => (jrun pen e st0 n).2) n : ℝ) * pen + phi pen (jrun pen e st0 n)
        ≤ phi pen st0 + ∑ t ∈ range n, |e t| := by
    intro n
    induction n with
    | zero =>
        refine ⟨h0, h1, ?_⟩
        simp [switches, jrun]
    | succ n ih =>
        obtain ⟨ih0, ih1, ih2⟩ := ih
        rcases hst : jrun pen e st0 n with ⟨y, s⟩
        rw [hst] at ih0 ih1 ih2
        have hstep := jstep_inv (e := e n) (s := s) hpen ih0 ih1
        have hn : jrun pen e st0 (n + 1) = jstep pen (e n) (y, s) := by
          show jstep pen (e n) (jrun pen e st0 n) = _
          rw [hst]
        obtain ⟨a, b, c⟩ := hstep
        refine ⟨by rw [hn]; exact a, by rw [hn]; exact b, ?_⟩
        rw [switches_succ, sum_range_succ, hn]
        simp only [hn, hst] at *
        by_cases hc : (jstep pen (e n) (y, s)).2 ≠ s
        · simp only [hc, ne_eq, not_false_eq_true, if_true] at c ⊢
          nlinarith
        · simp only [hc, if_false] at c ⊢
          nlinarith
  obtain ⟨a, b, c⟩ := hinv T
  have hphi0 : 0 ≤ phi pen (jrun pen e st0 T) := by
    unfold phi
    split_ifs <;> linarith
  have hphi1 : phi pen st0 ≤ pen := by
    unfold phi
    split_ifs <;> linarith
  linarith

/-- J3. So total switching cost is capped in advance by evidence over penalty, with no return law. -/
theorem filter_cost_bound {pen c : ℝ} {e : ℕ → ℝ} {st0 : ℝ × Bool} (hpen : 0 < pen) (hc : 0 ≤ c) (h0 : 0 ≤ st0.1)
    (h1 : st0.1 ≤ pen) (T : ℕ) :
    c * (switches (fun n => (jrun pen e st0 n).2) T : ℝ) ≤ c * (1 + ∑ t ∈ range T, |e t| / pen) := by
  have hb := filter_switch_bound (e := e) hpen h0 h1 T
  refine mul_le_mul_of_nonneg_left ?_ hc
  rw [← sum_div]
  have : (pen + ∑ t ∈ range T, |e t|) / pen = 1 + (∑ t ∈ range T, |e t|) / pen := by
    field_simp
  rw [← this, le_div_iff₀ hpen]
  exact hb

/-! ### T. Comparing forecasters -/

/-- Log-score gain of forecast `m * p` over forecast `p`, for hit or miss. -/
def scoreDiff (m p : ℝ) (hit : Bool) : ℝ :=
  if hit then Real.log m else Real.log ((1 - m * p) / (1 - p))

/-- T1. With multipliers in `[1/2, 2]` and `p ≤ 1/4`, the score gain is bounded by `log 2`. -/
theorem scoreDiff_abs_le {m p : ℝ} (hm0 : 1 / 2 ≤ m) (hm1 : m ≤ 2) (hp0 : 0 ≤ p) (hp1 : p ≤ 1 / 4)
    (hit : Bool) : |scoreDiff m p hit| ≤ Real.log 2 := by
  have hl2 : 0 < Real.log 2 := Real.log_pos (by norm_num)
  have hhalf : Real.log (1 / 2) = -Real.log 2 := by
    rw [one_div, Real.log_inv]
  have key : ∀ q : ℝ, 1 / 2 ≤ q → q ≤ 2 → |Real.log q| ≤ Real.log 2 := fun q h1 h2 => by
    rw [abs_le]
    constructor
    · rw [← hhalf]
      exact Real.log_le_log (by norm_num) h1
    · exact Real.log_le_log (by linarith) h2
  cases hit with
  | true => simpa [scoreDiff] using key m hm0 hm1
  | false =>
      have hd : 0 < 1 - p := by linarith
      have hmp1 : m * p ≤ 2 * p := mul_le_mul_of_nonneg_right hm1 hp0
      have hmp0 : 1 / 2 * p ≤ m * p := mul_le_mul_of_nonneg_right hm0 hp0
      have := key ((1 - m * p) / (1 - p)) ((le_div_iff₀ hd).2 (by linarith)) ((div_le_iff₀ hd).2 (by linarith))
      simpa [scoreDiff] using this

/-- T2. Any uniform mixture of valid fixed bets on one statistic is a valid anytime test. -/
theorem mix_ville {Ω : Type*} {m0 : MeasurableSpace Ω} {μ : Measure Ω} [IsProbabilityMeasure μ]
    {ℱ : Filtration ℕ m0} {X : ℕ → Ω → ℝ} {B U' L : ℝ} {K : ℕ} (hK : 0 < K) {lams : Fin K → ℝ}
    (h : ∀ j, BettingHyp ℱ μ (fun _ _ => lams j) X 0 B U' L) {α : ℝ} (hα : 0 < α) (N : ℕ) :
    μ {ω | ∃ n ≤ N, 1 / α ≤ (∑ j, capital (fun _ _ => lams j) X 0 n ω) / K} ≤ ENNReal.ofReal α := by
  have hSuper : ∀ j, Supermartingale (capital (fun _ _ => lams j) X 0) ℱ μ :=
    fun j => capital_supermartingale (h j)
  have hMix : Supermartingale (fun n ω => (∑ j, capital (fun _ _ => lams j) X 0 n ω) / K) ℱ μ :=
    mix_supermartingale hK hSuper
  have hNonneg : ∀ n ω, 0 ≤ (∑ j, capital (fun _ _ => lams j) X 0 n ω) / K := fun n ω =>
    div_nonneg (sum_nonneg fun j _ => capital_nonneg (h j) n ω) (Nat.cast_nonneg K)
  have hBound := ville_finite hMix hNonneg (c := 1 / α) (div_pos one_pos hα) N
  have hInt : (∫ ω, (fun n ω => (∑ j, capital (fun _ _ => lams j) X 0 n ω) / K) 0 ω ∂μ) = 1 := by
    have h0 : (fun n ω => (∑ j, capital (fun _ _ => lams j) X 0 n ω) / K) 0 = fun _ : Ω => (1 : ℝ) := by
      funext ω
      have hKreal : (K : ℝ) ≠ 0 := by exact_mod_cast hK.ne'
      simp only [capital]
      rw [sum_const, card_univ, Fintype.card_fin, nsmul_eq_mul, mul_one, div_self hKreal]
    rw [h0]
    simp
  rw [hInt, one_div_one_div] at hBound
  exact hBound

/-- T3. The registered largest bet 7/5 is admissible against a loss bound of `log 2`. -/
theorem score_test_admissible : (7 / 5 : ℝ) * Real.log 2 ≤ 1 := by
  have := Real.log_two_lt_d9
  linarith

end

end PerpChief.Selective
