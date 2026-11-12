/- NOT IMPORTED by Analog.lean (2026-11-12): mechanical port fails on current Mathlib APIs; registered re-proof candidate in docs/research/06-lean-corpus-inventory.md. Preserved verbatim for the re-prover. -/
/-
PORTED 2026-11-12 from owner prior work: betting-test frame bounds
Source: andrewkoumoudjian/perps-strategy @ 0f34759, lanes/chief/lean/PerpChief/FrameB.lean (toolchain v4.15.0).
Port changes ONLY: module path/import remap to Analog.Prior.* (+ Mathlib API renames if listed in docs/research/06). Namespaces, statements, proofs otherwise verbatim. Original file is frozen upstream; do not edit semantics here.
-/
/-
FRAME B IS A BETTING TEST. FROZEN STATEMENTS (chief scientist).
Sizing a book at k x cushion under a trailing floor, the account reaches +τ essentially when the plain
betting capital ∏(1 + k r_t) reaches (1+τ)^(1/δ). So the pass condition and the anytime-valid test are one object.
Consequences, with no return law: a no-edge hurdle in closed form, a t-statistic every passing path must show,
and a minimum time to pass. Models the trailing floor only; a further daily limit can only remove passes
for the same sizing. Says nothing about whether any book has edge.
-/
import Analog.Prior.Ceiling
import Analog.Prior.Ville

open MeasureTheory Filter Finset
open scoped ENNReal

namespace PerpChief.FrameB

noncomputable section

open PerpChief.Leverage PerpChief.Ville

/-- The exponent controlling how much overshoot can flatter a new high. `x = k * U`. -/
def frameExp (δ x : ℝ) : ℝ := Real.log (1 + x) / Real.log (1 + δ * x)

/-- Plain betting capital at fixed fraction `k`, with no floor and no ratchet. -/
def betCapital (k : ℝ) (r : ℕ → ℝ) (T : ℕ) : ℝ := ∏ t ∈ range T, (1 + k * r t)

variable {δ k E0 U τ : ℝ} {r : ℕ → ℝ}

private lemma log_den_pos (hδ0 : 0 < δ) {x : ℝ} (hx : 0 < x) : 0 < Real.log (1 + δ * x) :=
  Real.log_pos (by nlinarith [mul_pos hδ0 hx])

private lemma self_mul_rpow {y : ℝ} (hy : 0 < y) (a : ℝ) : y * y ^ (a - 1) = y ^ a := by
  conv_rhs => rw [show a = 1 + (a - 1) by ring, Real.rpow_add hy, Real.rpow_one]

private lemma run_succ_E (n : ℕ) : (run δ k E0 r (n + 1)).E
    = (run δ k E0 r n).E + k * cushion δ (run δ k E0 r n) * r n := rfl

private lemma run_succ_H (n : ℕ) : (run δ k E0 r (n + 1)).H
    = max (run δ k E0 r n).H ((run δ k E0 r n).E + k * cushion δ (run δ k E0 r n) * r n) := rfl

private lemma factor_pos (hk : 0 < k) {y : ℝ} (hy : -1 / k < y) : 0 < 1 + k * y := by
  have := (div_lt_iff₀ hk).1 hy
  nlinarith

private lemma gap_of_abs (hk : 0 < k) {ε y : ℝ} (hε1 : ε < 1) (h : |k * y| ≤ ε) : -1 / k < y := by
  have h1 := (abs_le.1 h).1
  rw [div_lt_iff₀ hk]
  nlinarith

private lemma betCapital_succ (T : ℕ) : betCapital k r (T + 1) = betCapital k r T * (1 + k * r T) := by
  simp [betCapital, prod_range_succ]

private lemma betCapital_pos (hk : 0 < k) (T : ℕ) (hgap : ∀ t < T, -1 / k < r t) :
    0 < betCapital k r T :=
  prod_pos fun t ht => factor_pos hk (hgap t (mem_range.1 ht))

private lemma log_betCapital (hk : 0 < k) (T : ℕ) (hgap : ∀ t < T, -1 / k < r t) :
    Real.log (betCapital k r T) = ∑ t ∈ range T, Real.log (1 + k * r t) := by
  unfold betCapital
  exact Real.log_prod _ _ fun t ht => (factor_pos hk (hgap t (mem_range.1 ht))).ne'

/-- Scaling the new-high comparison by the old high-water mark. -/
private lemma scale_high {a H y : ℝ} (hH : 0 < H) (hy : 0 < y) :
    δ * y * y ^ (a - 1) = δ * (y / H) ^ a * (H * H ^ (a - 1)) ∧
      (y - (1 - δ) * H) * H ^ (a - 1) = (y / H - (1 - δ)) * (H * H ^ (a - 1)) := by
  constructor
  · rw [self_mul_rpow hH, mul_assoc, self_mul_rpow hy, mul_assoc, ← Real.mul_rpow (by positivity) hH.le,
      div_mul_cancel₀ _ hH.ne']
  · field_simp
    ring

/-- B1. The exponent lies between 1 and the frictionless value `1/δ`. -/
theorem frameExp_bounds (hδ0 : 0 < δ) (hδ1 : δ < 1) {x : ℝ} (hx : 0 < x) :
    1 ≤ frameExp δ x ∧ frameExp δ x ≤ 1 / δ := by
  have hM := log_den_pos hδ0 hx
  unfold frameExp
  constructor
  · rw [one_le_div hM]
    exact Real.log_le_log (by nlinarith [mul_pos hδ0 hx]) (by nlinarith)
  · rw [div_le_div_iff₀ hM hδ0, mul_comm, one_mul]
    have hb := rpow_one_add_le_one_add_mul_self (s := x) (by linarith) hδ0.le hδ1.le
    have hl := Real.log_le_log (Real.rpow_pos_of_pos (by linarith : (0:ℝ) < 1 + x) δ) hb
    rwa [Real.log_rpow (by linarith)] at hl

/-- B2. Small steps recover `1/δ`: the exponent is at least `1/(δ(1+x))`. -/
theorem frameExp_ge (hδ0 : 0 < δ) (hδ1 : δ < 1) {x : ℝ} (hx : 0 < x) :
    1 / (δ * (1 + x)) ≤ frameExp δ x := by
  have hM := log_den_pos hδ0 hx
  have hdx : 0 < δ * x := mul_pos hδ0 hx
  unfold frameExp
  rw [div_le_div_iff₀ (by positivity) hM, one_mul]
  have h1 : Real.log (1 + δ * x) ≤ δ * x := by
    have := Real.log_le_sub_one_of_pos (by linarith : (0:ℝ) < 1 + δ * x)
    linarith
  have h2 : 1 - (1 + x)⁻¹ ≤ Real.log (1 + x) := Real.one_sub_inv_le_log_of_pos (by linarith)
  have h3 : (δ * (1 + x)) * (1 - (1 + x)⁻¹) = δ * x := by
    field_simp
    ring
  have h4 : (δ * (1 + x)) * (1 - (1 + x)⁻¹) ≤ (δ * (1 + x)) * Real.log (1 + x) :=
    mul_le_mul_of_nonneg_left h2 (by positivity)
  nlinarith

/-- B3. The chord inequality behind the upper potential. -/
theorem chord_upper (hδ0 : 0 < δ) (hδ1 : δ < 1) {x u : ℝ} (hx : 0 < x) (hu1 : 1 ≤ u)
    (hu2 : u ≤ 1 + δ * x) : δ * u ^ frameExp δ x ≤ u - (1 - δ) := by
  have hM := log_den_pos hδ0 hx
  have hdx : 0 < δ * x := mul_pos hδ0 hx
  have ha := (frameExp_bounds hδ0 hδ1 hx).1
  set a := frameExp δ x with hadef
  have hA : (1 + δ * x) ^ a = 1 + x := by
    rw [Real.rpow_def_of_pos (by linarith), mul_comm, hadef]
    unfold frameExp
    rw [div_mul_cancel₀ _ hM.ne', Real.exp_log (by linarith)]
  set w := (u - 1) / (δ * x) with hw
  have hw0 : 0 ≤ w := div_nonneg (by linarith) hdx.le
  have hw1 : w ≤ 1 := (div_le_one hdx).2 (by linarith)
  have hconv := (convexOn_rpow ha).2 (x := 1) (y := 1 + δ * x)
    (by simp) (by simp only [Set.mem_Ici]; linarith) (sub_nonneg.2 hw1) hw0 (by ring)
  simp only [smul_eq_mul, Real.one_rpow, mul_one] at hconv
  have hu : 1 - w + w * (1 + δ * x) = u := by
    rw [hw]; field_simp; ring
  rw [hu, hA] at hconv
  have hw2 : δ * (w * x) = u - 1 := by
    rw [hw]; field_simp; ring
  nlinarith [mul_le_mul_of_nonneg_left hconv hδ0.le]

/-- B4. The Bernoulli inequality behind the lower potential. -/
theorem bernoulli_lower (hδ0 : 0 < δ) (hδ1 : δ < 1) {u : ℝ} (hu : 1 ≤ u) :
    u - (1 - δ) ≤ δ * u ^ (1 / δ) := by
  have hp : 1 ≤ 1 / δ := (one_le_div hδ0).2 hδ1.le
  have hb := one_add_mul_self_le_rpow_one_add (s := u - 1) (by linarith) hp
  rw [show 1 + (u - 1) = u by ring] at hb
  have hm := mul_le_mul_of_nonneg_left hb hδ0.le
  have he : δ * (1 + 1 / δ * (u - 1)) = u - (1 - δ) := by
    field_simp; ring
  linarith

/-- B5. The high-water mark is attained at some earlier equity. -/
theorem high_attained (n : ℕ) :
    ∃ m ≤ n, (run δ k E0 r n).H = (run δ k E0 r m).E ∧ (run δ k E0 r m).H = (run δ k E0 r m).E := by
  induction n with
  | zero => exact ⟨0, le_rfl, rfl, rfl⟩
  | succ n ih =>
      obtain ⟨m, hm, h1, h2⟩ := ih
      rcases le_total (run δ k E0 r n).H
          ((run δ k E0 r n).E + k * cushion δ (run δ k E0 r n) * r n) with h | h
      · refine ⟨n + 1, le_rfl, ?_, ?_⟩ <;> rw [run_succ_H, max_eq_right h, run_succ_E]
      · exact ⟨m, by omega, by rw [run_succ_H, max_eq_left h, h1], h2⟩

/-- B6. Upper potential: on every gap-free path it is at most the betting capital. -/
theorem potential_le (hE : 0 < E0) (hδ0 : 0 < δ) (hδ1 : δ < 1) (hk : 0 < k) (hU : 0 < U) (T : ℕ)
    (hgap : ∀ t < T, -1 / k < r t) (hr : ∀ t < T, r t ≤ U) :
    cushion δ (run δ k E0 r T) * (run δ k E0 r T).H ^ (frameExp δ (k * U) - 1)
      ≤ δ * E0 ^ frameExp δ (k * U) * betCapital k r T := by
  have hx : 0 < k * U := mul_pos hk hU
  set a := frameExp δ (k * U) with hadef
  induction T with
  | zero =>
      have hc : cushion δ (run δ k E0 r 0) = δ * E0 := by
        show E0 - (1 - δ) * E0 = δ * E0
        ring
      rw [hc]
      show δ * E0 * E0 ^ (a - 1) ≤ δ * E0 ^ a * betCapital k r 0
      simp only [betCapital, range_zero, prod_empty, mul_one]
      rw [mul_assoc, self_mul_rpow hE]
  | succ T ih =>
      have hg : ∀ t < T, -1 / k < r t := fun t ht => hgap t (by omega)
      have ih' := ih hg fun t ht => hr t (by omega)
      obtain ⟨hE1, hEH, hH, hC, hCE⟩ := ws3_cstate_inv hE hδ0 hδ1 hk T hg
      have hf := factor_pos hk (hgap T (by omega))
      have hrT := hr T (by omega)
      set s := run δ k E0 r T with hs
      set E' := s.E + k * cushion δ s * r T with hE'
      have hCf : E' - (1 - δ) * s.H = cushion δ s * (1 + k * r T) := by
        simp only [hE', cushion]; ring
      have hstep : cushion δ (run δ k E0 r (T + 1)) * (run δ k E0 r (T + 1)).H ^ (a - 1)
          ≤ cushion δ s * s.H ^ (a - 1) * (1 + k * r T) := by
        rcases le_total E' s.H with h | h
        · have hHs : (run δ k E0 r (T + 1)).H = s.H := by
            rw [run_succ_H, ← hs, ← hE', max_eq_left h]
          have hEs : (run δ k E0 r (T + 1)).E = E' := by rw [run_succ_E, ← hs]
          have hc' : cushion δ (run δ k E0 r (T + 1)) = cushion δ s * (1 + k * r T) := by
            rw [← hCf]; simp only [cushion, hHs, hEs]
          rw [hc', hHs]
          exact le_of_eq (by ring)
        · have hHs : (run δ k E0 r (T + 1)).H = E' := by
            rw [run_succ_H, ← hs, ← hE', max_eq_right h]
          have hEs : (run δ k E0 r (T + 1)).E = E' := by rw [run_succ_E, ← hs]
          have hy : 0 < E' := lt_of_lt_of_le hH h
          have hc' : cushion δ (run δ k E0 r (T + 1)) = δ * E' := by
            simp only [cushion, hHs, hEs]; ring
          rw [hc', hHs]
          obtain ⟨h1, h2⟩ := scale_high (δ := δ) (a := a) hH hy
          have hup : E' ≤ s.H * (1 + δ * (k * U)) := by
            have hC2 : cushion δ s ≤ δ * s.H := hCE.trans (mul_le_mul_of_nonneg_left hEH hδ0.le)
            have hf2 : 1 + k * r T ≤ 1 + k * U := by nlinarith
            have hm : cushion δ s * (1 + k * r T) ≤ δ * s.H * (1 + k * U) :=
              mul_le_mul hC2 hf2 hf.le (by positivity)
            nlinarith
          have hu1 : 1 ≤ E' / s.H := (one_le_div hH).2 h
          have hu2 : E' / s.H ≤ 1 + δ * (k * U) := (div_le_iff₀ hH).2 (by linarith)
          have hch := chord_upper hδ0 hδ1 hx hu1 hu2
          rw [← hadef] at hch
          have hq : 0 ≤ s.H * s.H ^ (a - 1) := by positivity
          have hfin := mul_le_mul_of_nonneg_right hch hq
          calc δ * E' * E' ^ (a - 1) = δ * (E' / s.H) ^ a * (s.H * s.H ^ (a - 1)) := h1
            _ ≤ (E' / s.H - (1 - δ)) * (s.H * s.H ^ (a - 1)) := hfin
            _ = (E' - (1 - δ) * s.H) * s.H ^ (a - 1) := h2.symm
            _ = cushion δ s * s.H ^ (a - 1) * (1 + k * r T) := by rw [hCf]; ring
      calc _ ≤ cushion δ s * s.H ^ (a - 1) * (1 + k * r T) := hstep
        _ ≤ δ * E0 ^ a * betCapital k r T * (1 + k * r T) := mul_le_mul_of_nonneg_right ih' hf.le
        _ = δ * E0 ^ a * betCapital k r (T + 1) := by rw [betCapital_succ]; ring

/-- B7. Lower potential: on every gap-free path it is at least the betting capital. -/
theorem potential_ge (hE : 0 < E0) (hδ0 : 0 < δ) (hδ1 : δ < 1) (hk : 0 < k) (T : ℕ)
    (hgap : ∀ t < T, -1 / k < r t) :
    δ * E0 ^ (1 / δ) * betCapital k r T
      ≤ cushion δ (run δ k E0 r T) * (run δ k E0 r T).H ^ (1 / δ - 1) := by
  induction T with
  | zero =>
      have hc : cushion δ (run δ k E0 r 0) = δ * E0 := by
        show E0 - (1 - δ) * E0 = δ * E0
        ring
      rw [hc]
      show δ * E0 ^ (1 / δ) * betCapital k r 0 ≤ δ * E0 * E0 ^ (1 / δ - 1)
      simp only [betCapital, range_zero, prod_empty, mul_one]
      rw [mul_assoc, self_mul_rpow hE]
  | succ T ih =>
      have hg : ∀ t < T, -1 / k < r t := fun t ht => hgap t (by omega)
      have ih' := ih hg
      obtain ⟨hE1, hEH, hH, hC, hCE⟩ := ws3_cstate_inv hE hδ0 hδ1 hk T hg
      have hf := factor_pos hk (hgap T (by omega))
      set a := 1 / δ with hadef
      set s := run δ k E0 r T with hs
      set E' := s.E + k * cushion δ s * r T with hE'
      have hCf : E' - (1 - δ) * s.H = cushion δ s * (1 + k * r T) := by
        simp only [hE', cushion]; ring
      have hstep : cushion δ s * s.H ^ (a - 1) * (1 + k * r T)
          ≤ cushion δ (run δ k E0 r (T + 1)) * (run δ k E0 r (T + 1)).H ^ (a - 1) := by
        rcases le_total E' s.H with h | h
        · have hHs : (run δ k E0 r (T + 1)).H = s.H := by
            rw [run_succ_H, ← hs, ← hE', max_eq_left h]
          have hEs : (run δ k E0 r (T + 1)).E = E' := by rw [run_succ_E, ← hs]
          have hc' : cushion δ (run δ k E0 r (T + 1)) = cushion δ s * (1 + k * r T) := by
            rw [← hCf]; simp only [cushion, hHs, hEs]
          rw [hc', hHs]
          exact le_of_eq (by ring)
        · have hHs : (run δ k E0 r (T + 1)).H = E' := by
            rw [run_succ_H, ← hs, ← hE', max_eq_right h]
          have hEs : (run δ k E0 r (T + 1)).E = E' := by rw [run_succ_E, ← hs]
          have hy : 0 < E' := lt_of_lt_of_le hH h
          have hc' : cushion δ (run δ k E0 r (T + 1)) = δ * E' := by
            simp only [cushion, hHs, hEs]; ring
          rw [hc', hHs]
          obtain ⟨h1, h2⟩ := scale_high (δ := δ) (a := a) hH hy
          have hu1 : 1 ≤ E' / s.H := (one_le_div hH).2 h
          have hbe := bernoulli_lower hδ0 hδ1 hu1
          rw [← hadef] at hbe
          have hq : 0 ≤ s.H * s.H ^ (a - 1) := by positivity
          have hfin := mul_le_mul_of_nonneg_right hbe hq
          calc cushion δ s * s.H ^ (a - 1) * (1 + k * r T)
              = (E' - (1 - δ) * s.H) * s.H ^ (a - 1) := by rw [hCf]; ring
            _ = (E' / s.H - (1 - δ)) * (s.H * s.H ^ (a - 1)) := h2
            _ ≤ δ * (E' / s.H) ^ a * (s.H * s.H ^ (a - 1)) := hfin
            _ = δ * E' * E' ^ (a - 1) := h1.symm
      calc δ * E0 ^ a * betCapital k r (T + 1)
          = δ * E0 ^ a * betCapital k r T * (1 + k * r T) := by rw [betCapital_succ]; ring
        _ ≤ cushion δ s * s.H ^ (a - 1) * (1 + k * r T) := mul_le_mul_of_nonneg_right ih' hf.le
        _ ≤ _ := hstep

/-- B8. Necessary: a pass forces the betting capital to have reached `(1+τ)^a` by then. -/
theorem pass_forces_capital (hE : 0 < E0) (hδ0 : 0 < δ) (hδ1 : δ < 1) (hk : 0 < k) (hU : 0 < U)
    (hτ : 0 < τ) (n : ℕ) (hgap : ∀ t < n, -1 / k < r t) (hr : ∀ t < n, r t ≤ U)
    (hpass : (1 + τ) * E0 ≤ (run δ k E0 r n).H) :
    ∃ m ≤ n, (1 + τ) ^ frameExp δ (k * U) ≤ betCapital k r m := by
  have hx : 0 < k * U := mul_pos hk hU
  have ha := (frameExp_bounds hδ0 hδ1 hx).1
  obtain ⟨m, hm, h1, h2⟩ := high_attained (δ := δ) (k := k) (E0 := E0) (r := r) n
  refine ⟨m, hm, ?_⟩
  have hgm : ∀ t < m, -1 / k < r t := fun t ht => hgap t (by omega)
  have hp := potential_le hE hδ0 hδ1 hk hU m hgm fun t ht => hr t (by omega)
  set a := frameExp δ (k * U) with hadef
  have hEm : (1 + τ) * E0 ≤ (run δ k E0 r m).E := by rw [← h1]; exact hpass
  have hyp : 0 < (run δ k E0 r m).E := lt_of_lt_of_le (by positivity) hEm
  have hc : cushion δ (run δ k E0 r m) = δ * (run δ k E0 r m).E := by
    simp only [cushion, h2]; ring
  rw [hc, h2, mul_assoc, self_mul_rpow hyp] at hp
  have hpow : ((1 + τ) * E0) ^ a ≤ (run δ k E0 r m).E ^ a :=
    Real.rpow_le_rpow (by positivity) hEm (by linarith)
  rw [Real.mul_rpow (by linarith) hE.le] at hpow
  have hd : 0 < δ * E0 ^ a := by positivity
  have hchain : δ * E0 ^ a * (1 + τ) ^ a ≤ δ * E0 ^ a * betCapital k r m := by
    calc δ * E0 ^ a * (1 + τ) ^ a = δ * ((1 + τ) ^ a * E0 ^ a) := by ring
      _ ≤ δ * (run δ k E0 r m).E ^ a := mul_le_mul_of_nonneg_left hpow hδ0.le
      _ ≤ _ := hp
  exact le_of_mul_le_mul_left hchain hd

/-- B9. Sufficient: if the betting capital reaches `(1+τ)^(1/δ)`, the account has passed. -/
theorem capital_forces_pass (hE : 0 < E0) (hδ0 : 0 < δ) (hδ1 : δ < 1) (hk : 0 < k) (hτ : 0 < τ)
    (T : ℕ) (hgap : ∀ t < T, -1 / k < r t) (hcap : (1 + τ) ^ (1 / δ) ≤ betCapital k r T) :
    (1 + τ) * E0 ≤ (run δ k E0 r T).H := by
  obtain ⟨_, hEH, hH, _, hCE⟩ := ws3_cstate_inv hE hδ0 hδ1 hk T hgap
  have hp := potential_ge hE hδ0 hδ1 hk T hgap
  have hb : 0 < 1 / δ := by positivity
  set b := 1 / δ with hbdef
  set s := run δ k E0 r T with hs
  have hC2 : cushion δ s ≤ δ * s.H := hCE.trans (mul_le_mul_of_nonneg_left hEH hδ0.le)
  have hup : cushion δ s * s.H ^ (b - 1) ≤ δ * s.H ^ b := by
    calc cushion δ s * s.H ^ (b - 1) ≤ δ * s.H * s.H ^ (b - 1) :=
          mul_le_mul_of_nonneg_right hC2 (by positivity)
      _ = δ * s.H ^ b := by rw [mul_assoc, self_mul_rpow hH]
  have hchain : δ * (((1 + τ) * E0) ^ b) ≤ δ * s.H ^ b := by
    rw [Real.mul_rpow (by linarith) hE.le]
    calc δ * ((1 + τ) ^ b * E0 ^ b) = δ * E0 ^ b * (1 + τ) ^ b := by ring
      _ ≤ δ * E0 ^ b * betCapital k r T := mul_le_mul_of_nonneg_left hcap (by positivity)
      _ ≤ _ := hp.trans hup
  have hle := le_of_mul_le_mul_left hchain hδ0
  exact (Real.rpow_le_rpow_iff (by positivity) hH.le hb).1 hle

/-- B10. The no-edge hurdle. Under a null of non-positive conditional mean with capped loss, for any
dependence and any right tail up to `U`, the chance of ever passing is at most `(1+τ)^(-a)`. -/
theorem null_hurdle {Ω : Type*} {m0 : MeasurableSpace Ω} {μ : Measure Ω} [IsProbabilityMeasure μ]
    {ℱ : Filtration ℕ m0} {X : ℕ → Ω → ℝ} {B : ℝ}
    (h : BettingHyp ℱ μ (fun _ _ => k) X 0 B U k) (hk : 0 < k) (hkB : k * B < 1) (hU : 0 < U)
    (hE : 0 < E0) (hδ0 : 0 < δ) (hδ1 : δ < 1) (hτ : 0 < τ) (N : ℕ) :
    μ {ω | ∃ n ≤ N, (1 + τ) * E0 ≤ (run δ k E0 (fun t => X (t + 1) ω) n).H}
      ≤ ENNReal.ofReal ((1 + τ) ^ (-frameExp δ (k * U))) := by
  have hx : 0 < k * U := mul_pos hk hU
  set a := frameExp δ (k * U) with hadef
  have hbase : (0:ℝ) < 1 + τ := by linarith
  have hα : 0 < (1 + τ) ^ (-a) := Real.rpow_pos_of_pos hbase _
  have hsub : {ω | ∃ n ≤ N, (1 + τ) * E0 ≤ (run δ k E0 (fun t => X (t + 1) ω) n).H}
      ⊆ {ω | ∃ n ≤ N, 1 / (1 + τ) ^ (-a) ≤ capital (fun _ _ => k) X 0 n ω} := by
    rintro ω ⟨n, hn, hpass⟩
    have hgap : ∀ t < n, -1 / k < X (t + 1) ω := fun t _ => by
      rw [div_lt_iff₀ hk]
      nlinarith [h.X_lower (t + 1) ω]
    obtain ⟨m, hm, hcap⟩ := pass_forces_capital (r := fun t => X (t + 1) ω) hE hδ0 hδ1 hk hU hτ n hgap
      (fun t _ => h.X_upper (t + 1) ω) hpass
    refine ⟨m, hm.trans hn, ?_⟩
    have hcapeq : ∀ j, capital (fun _ _ => k) X 0 j ω = betCapital k (fun t => X (t + 1) ω) j := by
      intro j
      induction j with
      | zero => simp [capital, betCapital]
      | succ j ih =>
          rw [betCapital_succ, ← ih]
          simp only [capital, sub_zero]
    rw [hcapeq, Real.rpow_neg hbase.le, one_div, inv_inv]
    exact hcap
  exact (measure_mono hsub).trans (capital_ville h hα N)

/-- B11. Every passing path shows a large t-statistic on some prefix, for any `k`. -/
theorem pass_requires_tstat (hE : 0 < E0) (hδ0 : 0 < δ) (hδ1 : δ < 1) (hk : 0 < k) (hU : 0 < U)
    (hτ : 0 < τ) {ε : ℝ} (hε0 : 0 < ε) (hε1 : ε < 1) (n : ℕ) (hb : ∀ t < n, |k * r t| ≤ ε)
    (hr : ∀ t < n, r t ≤ U) (hpass : (1 + τ) * E0 ≤ (run δ k E0 r n).H) :
    ∃ m ≤ n, 0 < ∑ t ∈ range m, r t ^ 2 ∧
      4 * (1 / 2 - ε / 3) * (frameExp δ (k * U) * Real.log (1 + τ))
        ≤ (∑ t ∈ range m, r t) ^ 2 / ∑ t ∈ range m, r t ^ 2 := by
  have hgap : ∀ t < n, -1 / k < r t := fun t ht => gap_of_abs hk hε1 (hb t ht)
  obtain ⟨m, hm, hcap⟩ := pass_forces_capital hE hδ0 hδ1 hk hU hτ n hgap hr hpass
  have hx : 0 < k * U := mul_pos hk hU
  have ha := (frameExp_bounds hδ0 hδ1 hx).1
  set a := frameExp δ (k * U) with hadef
  have hbase : (0:ℝ) < 1 + τ := by linarith
  have hgm : ∀ t < m, -1 / k < r t := fun t ht => hgap t (by omega)
  have hlog : a * Real.log (1 + τ) ≤ ∑ t ∈ range m, Real.log (1 + k * r t) := by
    rw [← log_betCapital hk m hgm, ← Real.log_rpow hbase]
    exact Real.log_le_log (Real.rpow_pos_of_pos hbase _) hcap
  have hbm : ∀ t < m, |k * r t| ≤ ε := fun t ht => hb t (by omega)

  have hlpos : 0 < a * Real.log (1 + τ) := mul_pos (by linarith) (Real.log_pos (by linarith))
  have hBpos : 0 < ∑ t ∈ range m, r t ^ 2 := by
    rcases (sum_nonneg fun t _ => sq_nonneg (r t) : 0 ≤ ∑ t ∈ range m, r t ^ 2).lt_or_eq with h | h
    · exact h
    · exfalso
      have hz := (sum_eq_zero_iff_of_nonneg fun t _ => sq_nonneg (r t)).1 h.symm
      have hzero : ∑ t ∈ range m, Real.log (1 + k * r t) = 0 :=
        sum_eq_zero fun t ht => by
          have : r t = 0 := by simpa using hz t ht
          simp [this]
      linarith
  refine ⟨m, hm, hBpos, ?_⟩
  have hts := PerpChief.Ceiling.log_capital_le_tstat hε0 hε1 m hbm hBpos
  have hc : (0:ℝ) < 1 / 2 - ε / 3 := by linarith
  have hmul := mul_le_mul_of_nonneg_left (hlog.trans hts) (by linarith : (0:ℝ) ≤ 4 * (1 / 2 - ε / 3))
  rwa [PerpChief.Ceiling.ws7_four_mul_div hc.ne' hBpos.ne'] at hmul

/-- B12. Minimum time to pass, given bounds on the path's realised mean and second moment. -/
theorem pass_time_bound (hE : 0 < E0) (hδ0 : 0 < δ) (hδ1 : δ < 1) (hk : 0 < k) (hU : 0 < U)
    (hτ : 0 < τ) {ε m1 m2 : ℝ} (hε0 : 0 < ε) (hε1 : ε < 1) (n : ℕ) (hb : ∀ t < n, |k * r t| ≤ ε)
    (hr : ∀ t < n, r t ≤ U) (hm1 : ∀ m ≤ n, ∑ t ∈ range m, r t ≤ m1 * m)
    (hm2 : ∀ m ≤ n, m2 * m ≤ ∑ t ∈ range m, r t ^ 2)
    (hg : 0 ≤ k * m1 - (1 / 2 - ε / 3) * k ^ 2 * m2)
    (hpass : (1 + τ) * E0 ≤ (run δ k E0 r n).H) :
    frameExp δ (k * U) * Real.log (1 + τ) ≤ (k * m1 - (1 / 2 - ε / 3) * k ^ 2 * m2) * n := by
  have hgap : ∀ t < n, -1 / k < r t := fun t ht => gap_of_abs hk hε1 (hb t ht)
  obtain ⟨m, hm, hcap⟩ := pass_forces_capital hE hδ0 hδ1 hk hU hτ n hgap hr hpass
  have hx : 0 < k * U := mul_pos hk hU
  have ha := (frameExp_bounds hδ0 hδ1 hx).1
  set a := frameExp δ (k * U) with hadef
  have hbase : (0:ℝ) < 1 + τ := by linarith
  have hgm : ∀ t < m, -1 / k < r t := fun t ht => hgap t (by omega)
  have hlog : a * Real.log (1 + τ) ≤ ∑ t ∈ range m, Real.log (1 + k * r t) := by
    rw [← log_betCapital hk m hgm, ← Real.log_rpow hbase]
    exact Real.log_le_log (Real.rpow_pos_of_pos hbase _) hcap
  have hbm : ∀ t < m, |k * r t| ≤ ε := fun t ht => hb t (by omega)

  have hc : (0:ℝ) < 1 / 2 - ε / 3 := by linarith
  have h5 := PerpChief.Ceiling.log_capital_le hε0 hε1 m hbm
  have h1 := mul_le_mul_of_nonneg_left (hm1 m hm) hk.le
  have h2 := mul_le_mul_of_nonneg_left (hm2 m hm) (by positivity : (0:ℝ) ≤ (1 / 2 - ε / 3) * k ^ 2)
  have h3 := mul_le_mul_of_nonneg_left (Nat.cast_le (α := ℝ).2 hm) hg
  have h4 : (k * m1 - (1 / 2 - ε / 3) * k ^ 2 * m2) * (m : ℝ)
      = k * (m1 * m) - (1 / 2 - ε / 3) * k ^ 2 * (m2 * m) := by ring
  linarith

/-- B13. At Frame B's numbers the frictionless test level exceeds 4.89. -/
theorem frame_b_level : (489 / 100 : ℝ) ≤ (11 / 10 : ℝ) ^ (1 / (6 / 100 : ℝ)) := by
  by_contra hlt
  push_neg at hlt
  have hy : (0:ℝ) ≤ (11 / 10 : ℝ) ^ (1 / (6 / 100 : ℝ)) := by positivity
  have h3 := pow_lt_pow_left₀ hlt hy (n := 3) (by norm_num)
  have he : ((11 / 10 : ℝ) ^ (1 / (6 / 100 : ℝ))) ^ 3 = (11 / 10 : ℝ) ^ 50 := by
    rw [← Real.rpow_natCast, ← Real.rpow_mul (by norm_num)]
    rw [show (1 / (6 / 100 : ℝ)) * ((3 : ℕ) : ℝ) = ((50 : ℕ) : ℝ) by norm_num, Real.rpow_natCast]
  rw [he] at h3
  norm_num at h3

/-- B14. So the frictionless no-edge hurdle is below 20.5%. -/
theorem frame_b_hurdle : (11 / 10 : ℝ) ^ (-(1 / (6 / 100 : ℝ))) ≤ 205 / 1000 := by
  rw [Real.rpow_neg (by norm_num)]
  have h := inv_anti₀ (by norm_num : (0:ℝ) < 489 / 100) frame_b_level
  refine h.trans ?_
  norm_num

end

end PerpChief.FrameB
