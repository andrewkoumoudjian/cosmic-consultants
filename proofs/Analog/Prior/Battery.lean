/- NOT IMPORTED by Analog.lean (2026-11-12): mechanical port fails on current Mathlib APIs; registered re-proof candidate in docs/research/06-lean-corpus-inventory.md. Preserved verbatim for the re-prover. -/
/-
PORTED 2026-11-12 from owner prior work: battery of tests ledger
Source: andrewkoumoudjian/perps-strategy @ 0f34759, lanes/chief/lean/PerpChief/Battery.lean (toolchain v4.15.0).
Port changes ONLY: module path/import remap to Analog.Prior.* (+ Mathlib API renames if listed in docs/research/06). Namespaces, statements, proofs otherwise verbatim. Original file is frozen upstream; do not edit semantics here.
-/
/-
ROUND 5: THE BATTERY AND THE MAKER LEDGER. FROZEN STATEMENTS (chief scientist).
B. A battery of J tests, each a mixture of K fixed bets, has overall level α at threshold J/α.
   Pathwise, some series must pass and others cannot, whatever the law.
Q. The exact ledger of a quoting book: edge, fees, inventory and funding, on every path.
   Inventory profit equals the fills' mark-outs. A cap bounds each step, and edge at or below the fee leaves only inventory.
Says nothing about whether any mechanism has edge.
-/
import Analog.Prior.Selective

open MeasureTheory Filter Finset
open scoped ENNReal

namespace PerpChief.Battery

noncomputable section

open PerpChief.Ville PerpChief.FrameB PerpChief.Selective

/-! ### B. The battery -/

/-- B1. Overall level of a battery of `J` mixture tests. -/
theorem battery_level {Ω : Type*} {m0 : MeasurableSpace Ω} {μ : Measure Ω} [IsProbabilityMeasure μ]
    {ℱ : Filtration ℕ m0} {J K : ℕ} (hJ : 0 < J) (hK : 0 < K) {lams : Fin K → ℝ}
    {X : Fin J → ℕ → Ω → ℝ} {B U L : ℝ}
    (h : ∀ j k, BettingHyp ℱ μ (fun _ _ => lams k) (X j) 0 B U L) {α : ℝ} (hα : 0 < α) (N : ℕ) :
    μ {ω | ∃ j, ∃ n ≤ N, (J : ℝ) / α ≤ (∑ k, capital (fun _ _ => lams k) (X j) 0 n ω) / K}
      ≤ ENNReal.ofReal α := by
  have hJr : (0 : ℝ) < J := by exact_mod_cast hJ
  have hα' : 0 < α / J := div_pos hα hJr
  have hone : ∀ j : Fin J, μ {ω | ∃ n ≤ N, (J : ℝ) / α ≤ (∑ k, capital (fun _ _ => lams k) (X j) 0 n ω) / K}
      ≤ ENNReal.ofReal (α / J) := fun j => by
    have hm := mix_ville hK (h j) hα' N
    have he : 1 / (α / J) = (J : ℝ) / α := by field_simp
    rwa [he] at hm
  have hsub : {ω | ∃ j, ∃ n ≤ N, (J : ℝ) / α ≤ (∑ k, capital (fun _ _ => lams k) (X j) 0 n ω) / K}
      ⊆ ⋃ j : Fin J, {ω | ∃ n ≤ N, (J : ℝ) / α ≤ (∑ k, capital (fun _ _ => lams k) (X j) 0 n ω) / K} := by
    intro ω hω
    obtain ⟨j, hj⟩ := hω
    exact Set.mem_iUnion.2 ⟨j, hj⟩
  calc _ ≤ μ (⋃ j : Fin J, {ω | ∃ n ≤ N, (J : ℝ) / α ≤ (∑ k, capital (fun _ _ => lams k) (X j) 0 n ω) / K}) :=
        measure_mono hsub
    _ ≤ ∑ j : Fin J, μ {ω | ∃ n ≤ N, (J : ℝ) / α ≤ (∑ k, capital (fun _ _ => lams k) (X j) 0 n ω) / K} :=
        measure_iUnion_fintype_le μ _
    _ ≤ ∑ _j : Fin J, ENNReal.ofReal (α / J) := Finset.sum_le_sum fun j _ => hone j
    _ = ENNReal.ofReal α := by
        rw [← ENNReal.ofReal_sum_of_nonneg (fun _ _ => hα'.le)]
        congr 1
        simp only [Finset.sum_const, Finset.card_univ, Fintype.card_fin, nsmul_eq_mul]
        field_simp

private lemma log_bet {k : ℝ} {x : ℕ → ℝ} {T : ℕ} (hf : ∀ t < T, 0 < 1 + k * x t) :
    0 < betCapital k x T ∧ Real.log (betCapital k x T) = ∑ t ∈ range T, Real.log (1 + k * x t) := by
  have hf' : ∀ t ∈ range T, 0 < 1 + k * x t := fun t ht => hf t (Finset.mem_range.1 ht)
  refine ⟨Finset.prod_pos hf', ?_⟩
  unfold betCapital
  exact Real.log_prod _ _ fun t ht => (hf' t ht).ne'

/-- B2. A realised series that must pass: enough drift for its variance at one grid bet. -/
theorem battery_sufficient {K : ℕ} (hK : 0 < K) {lams : Fin K → ℝ} {x : ℕ → ℝ} {T : ℕ} {ε c : ℝ}
    (hε : ε < 1) (hc : 0 < c) (hpos : ∀ k, ∀ t < T, 0 < 1 + lams k * x t) (j : Fin K)
    (hb : ∀ t < T, |lams j * x t| ≤ ε)
    (hlev : Real.log (K * c) ≤ lams j * ∑ t ∈ range T, x t
        - (lams j) ^ 2 / (1 - ε) * ∑ t ∈ range T, x t ^ 2) :
    c ≤ (∑ k, betCapital (lams k) x T) / K := by
  have hKr : (0 : ℝ) < K := by exact_mod_cast hK
  have hd : 0 < 1 - ε := by linarith
  obtain ⟨hWpos, hWlog⟩ := log_bet (hpos j)
  have hterm : ∀ t ∈ range T, lams j * x t - (lams j * x t) ^ 2 / (1 - ε) ≤ Real.log (1 + lams j * x t) :=
    fun t ht => by
      set y := lams j * x t with hy
      have hab := abs_le.1 (hb t (Finset.mem_range.1 ht))
      have hposy : 0 < 1 + y := by linarith [hab.1]
      have hlog := Real.one_sub_inv_le_log_of_pos hposy
      have hid : 1 - (1 + y)⁻¹ = y - y ^ 2 / (1 + y) := by
        field_simp
        ring
      have hle : y ^ 2 / (1 + y) ≤ y ^ 2 / (1 - ε) :=
        div_le_div_of_nonneg_left (sq_nonneg y) hd (by linarith [hab.1])
      linarith
  have hsum := Finset.sum_le_sum hterm
  have he : ∑ t ∈ range T, (lams j * x t - (lams j * x t) ^ 2 / (1 - ε))
      = lams j * ∑ t ∈ range T, x t - (lams j) ^ 2 / (1 - ε) * ∑ t ∈ range T, x t ^ 2 := by
    rw [Finset.sum_sub_distrib, Finset.mul_sum, Finset.mul_sum]
    congr 1
    refine Finset.sum_congr rfl fun t _ => ?_
    ring
  have hKc : 0 < (K : ℝ) * c := mul_pos hKr hc
  have hlogle : Real.log (K * c) ≤ Real.log (betCapital (lams j) x T) := by
    rw [hWlog]
    linarith
  have hWge : (K : ℝ) * c ≤ betCapital (lams j) x T := (Real.log_le_log_iff hKc hWpos).1 hlogle
  have hone : betCapital (lams j) x T ≤ ∑ k, betCapital (lams k) x T :=
    Finset.single_le_sum (f := fun k => betCapital (lams k) x T)
      (fun k _ => (log_bet (hpos k)).1.le) (Finset.mem_univ j)
  rw [le_div_iff₀ hKr]
  linarith

/-- B3. A realised series that cannot pass: the squared t-statistic must clear the level. -/
theorem battery_necessary {K : ℕ} (hK : 0 < K) {lams : Fin K → ℝ} {x : ℕ → ℝ} {T : ℕ} {ε c : ℝ}
    (hε0 : 0 < ε) (hε1 : ε < 1) (hc : 1 ≤ c) (hb : ∀ k, ∀ t < T, |lams k * x t| ≤ ε)
    (hv : 0 < ∑ t ∈ range T, x t ^ 2) (hpass : c ≤ (∑ k, betCapital (lams k) x T) / K) :
    4 * (1 / 2 - ε / 3) * Real.log c * ∑ t ∈ range T, x t ^ 2 ≤ (∑ t ∈ range T, x t) ^ 2 := by
  have hKr : (0 : ℝ) < K := by exact_mod_cast hK
  have hcpos : 0 < c := by linarith
  have hpos : ∀ k, ∀ t < T, 0 < 1 + lams k * x t := fun k t ht => by
    have := abs_le.1 (hb k t ht)
    linarith [this.1]
  haveI : Nonempty (Fin K) := Fin.pos_iff_nonempty.1 hK
  obtain ⟨k, hk⟩ : ∃ k, c ≤ betCapital (lams k) x T := by
    by_contra hno
    push_neg at hno
    have hlt : ∑ k, betCapital (lams k) x T < ∑ _k : Fin K, c :=
      Finset.sum_lt_sum_of_nonempty Finset.univ_nonempty fun k _ => hno k
    simp only [Finset.sum_const, Finset.card_univ, Fintype.card_fin, nsmul_eq_mul] at hlt
    rw [le_div_iff₀ hKr] at hpass
    linarith
  obtain ⟨hWpos, hWlog⟩ := log_bet (hpos k)
  have hterm : ∀ t ∈ range T, Real.log (1 + lams k * x t)
      ≤ lams k * x t - (1 / 2 - ε / 3) * (lams k * x t) ^ 2 :=
    fun t ht => PerpChief.Ceiling.log_one_add_le_quad hε0 hε1 (hb k t (Finset.mem_range.1 ht))
  have hsum := Finset.sum_le_sum hterm
  have he : ∑ t ∈ range T, (lams k * x t - (1 / 2 - ε / 3) * (lams k * x t) ^ 2)
      = lams k * ∑ t ∈ range T, x t - (1 / 2 - ε / 3) * (lams k) ^ 2 * ∑ t ∈ range T, x t ^ 2 := by
    rw [Finset.sum_sub_distrib, Finset.mul_sum, Finset.mul_sum]
    congr 1
    exact Finset.sum_congr rfl fun t _ => by ring
  have hlogc : Real.log c ≤ Real.log (betCapital (lams k) x T) := Real.log_le_log hcpos hk
  set s := ∑ t ∈ range T, x t with hs
  set v := ∑ t ∈ range T, x t ^ 2 with hvdef
  set l := lams k with hl
  set a := (1 / 2 - ε / 3) with ha
  have hapos : 0 < a := by rw [ha]; linarith
  have hkey : Real.log c ≤ l * s - a * l ^ 2 * v := by
    rw [hWlog] at hlogc
    linarith
  have hmul := mul_le_mul_of_nonneg_left hkey (by positivity : 0 ≤ 4 * a * v)
  nlinarith [sq_nonneg (s - 2 * a * l * v)]

/-! ### Q. The maker ledger -/

/-- Inventory after the fills before step `t`. -/
def inv (q : ℕ → ℝ) : ℕ → ℝ
  | 0 => 0
  | t + 1 => inv q t + q t

/-- Cash: fill `q t` at price `p t`, pay fee `φ t`, pay funding `f t` per unit held after the fill. -/
def cash (q p φ f : ℕ → ℝ) : ℕ → ℝ
  | 0 => 0
  | t + 1 => cash q p φ f t - q t * p t - φ t - inv q (t + 1) * f t

/-- Account value marked at mid `m`. -/
def value (q p φ f m : ℕ → ℝ) (T : ℕ) : ℝ := cash q p φ f T + inv q T * m T

private lemma value_succ (q p φ f m : ℕ → ℝ) (t : ℕ) :
    value q p φ f m (t + 1) = value q p φ f m t + q t * (m t - p t) - φ t
      + inv q (t + 1) * (m (t + 1) - m t) - inv q (t + 1) * f t := by
  have hI : inv q (t + 1) = inv q t + q t := rfl
  have hC : cash q p φ f (t + 1) = cash q p φ f t - q t * p t - φ t - inv q (t + 1) * f t := rfl
  unfold value
  rw [hC, hI]
  ring

/-- Q1. Value is edge at the fill, less fees, plus inventory revaluation, less funding. -/
theorem quote_ledger (q p φ f m : ℕ → ℝ) (T : ℕ) :
    value q p φ f m T = ∑ t ∈ range T, q t * (m t - p t) - ∑ t ∈ range T, φ t
      + ∑ t ∈ range T, inv q (t + 1) * (m (t + 1) - m t) - ∑ t ∈ range T, inv q (t + 1) * f t := by
  induction T with
  | zero => simp [value, cash, inv]
  | succ T ih =>
    rw [value_succ, ih]
    simp only [Finset.sum_range_succ]
    ring

/-- Q2. Inventory revaluation is the sum of each fill's mark-out to the end. -/
theorem inventory_markout (q m : ℕ → ℝ) (T : ℕ) :
    ∑ t ∈ range T, inv q (t + 1) * (m (t + 1) - m t) = ∑ t ∈ range T, q t * (m T - m t) := by
  have hinv : ∀ n, inv q n = ∑ t ∈ range n, q t := fun n => by
    induction n with
    | zero => simp [inv]
    | succ n ih => rw [Finset.sum_range_succ, ← ih]; rfl
  induction T with
  | zero => simp
  | succ T ih =>
    rw [Finset.sum_range_succ, ih, Finset.sum_range_succ (fun t => q t * (m (T + 1) - m t)) T, hinv (T + 1),
      Finset.sum_range_succ]
    have hsplit : ∑ t ∈ range T, q t * (m (T + 1) - m t)
        = ∑ t ∈ range T, q t * (m T - m t) + (∑ t ∈ range T, q t) * (m (T + 1) - m T) := by
      rw [Finset.sum_mul, ← Finset.sum_add_distrib]
      exact Finset.sum_congr rfl fun t _ => by ring
    rw [hsplit]
    ring

/-- Q3. One step can't lose more than the fee plus the cap times the move and funding. -/
theorem quote_step {q p φ f m : ℕ → ℝ} {Q r : ℝ} {t : ℕ} (hcap : |inv q (t + 1)| ≤ Q)
    (hedge : 0 ≤ q t * (m t - p t)) (hfee : φ t ≤ r * |q t|) :
    -(r * |q t| + Q * (|m (t + 1) - m t| + |f t|)) ≤ value q p φ f m (t + 1) - value q p φ f m t := by
  rw [value_succ]
  set I := inv q (t + 1)
  have h1 : -(Q * |m (t + 1) - m t|) ≤ I * (m (t + 1) - m t) := by
    have h := neg_abs_le (I * (m (t + 1) - m t))
    rw [abs_mul] at h
    have := mul_le_mul_of_nonneg_right hcap (abs_nonneg (m (t + 1) - m t))
    linarith
  have h2 : I * f t ≤ Q * |f t| := by
    have h := le_abs_self (I * f t)
    rw [abs_mul] at h
    have := mul_le_mul_of_nonneg_right hcap (abs_nonneg (f t))
    linarith
  nlinarith [h1, h2]

/-- Q4. If edge at the fill never exceeds the fee, the book makes money only from inventory. -/
theorem quote_ceiling {q p φ f m : ℕ → ℝ} {T : ℕ} (hk : ∀ t < T, q t * (m t - p t) ≤ φ t) :
    value q p φ f m T ≤ ∑ t ∈ range T, inv q (t + 1) * (m (t + 1) - m t)
      - ∑ t ∈ range T, inv q (t + 1) * f t := by
  rw [quote_ledger]
  have := Finset.sum_le_sum fun t ht => hk t (Finset.mem_range.1 ht)
  linarith

end

end PerpChief.Battery
