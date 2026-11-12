/-
PORTED 2026-11-12 from owner prior work: adaptive quantile thermostat (distribution-free)
Source: andrewkoumoudjian/perps-strategy @ 0f34759, lanes/chief/lean/PerpChief/ACI.lean (toolchain v4.15.0).
Port changes ONLY: module path/import remap to Analog.Prior.* (+ Mathlib API renames if listed in docs/research/06). Namespaces, statements, proofs otherwise verbatim. Original file is frozen upstream; do not edit semantics here — supersede via new module + STATEMENTS.md.
-/
/-
WS2 — THE SIGMA THERMOSTAT. FROZEN STATEMENTS (chief scientist). Fill in the proof holes; add helper lemmas.
Deterministic statements on ARBITRARY sequences: no law, no stationarity, no regime assumption.
Companion C3 proved no fitted point can pass the fold band under regime spread; this replaces the
fitted point by a controlled one whose fold error is an exact identity.
-/
import Mathlib
import Mathlib.Data.Real.Basic
import Mathlib.Tactic

open Finset

namespace PerpChief.ACI

noncomputable section

/-- Exceedance indicator. -/
def err (q z : ℝ) : ℝ := if q < z then 1 else 0

/-- Online sigma threshold (Gibbs–Candès 2021 form, on the sigma scale). -/
def qSeq (γ a q0 : ℝ) (z : ℕ → ℝ) : ℕ → ℝ
  | 0 => q0
  | n + 1 => qSeq γ a q0 z n + γ * (err (qSeq γ a q0 z n) (z n) - a)

variable {γ a q0 : ℝ} {z : ℕ → ℝ}

lemma qSeq_zero : qSeq γ a q0 z 0 = q0 := rfl

lemma qSeq_succ (n : ℕ) :
    qSeq γ a q0 z (n + 1) = qSeq γ a q0 z n + γ * (err (qSeq γ a q0 z n) (z n) - a) := rfl

/-- A1. Exact telescoping over ANY window. -/
theorem window_identity (hγ : γ ≠ 0) (s T : ℕ) :
    ∑ t ∈ range T, (err (qSeq γ a q0 z (s + t)) (z (s + t)) - a)
      = (qSeq γ a q0 z (s + T) - qSeq γ a q0 z s) / γ := by
  induction T with
  | zero => simp
  | succ T ih =>
    rw [sum_range_succ, ih]
    have hstep : qSeq γ a q0 z (s + (T + 1))
        = qSeq γ a q0 z (s + T) + γ * (err (qSeq γ a q0 z (s + T)) (z (s + T)) - a) := by
      have hidx : s + (T + 1) = (s + T) + 1 := by ring
      rw [hidx, qSeq_succ]
    rw [hstep]
    field_simp
    ring

/-- A2. Fold exceedance frequency is the target plus an observed certificate. -/
theorem window_freq (hγ : γ ≠ 0) (s : ℕ) {T : ℕ} (hT : 0 < T) :
    (∑ t ∈ range T, err (qSeq γ a q0 z (s + t)) (z (s + t))) / T - a
      = (qSeq γ a q0 z (s + T) - qSeq γ a q0 z s) / (γ * T) := by
  have h : (∑ t ∈ range T, (err (qSeq γ a q0 z (s + t)) (z (s + t)) - a))
      = (qSeq γ a q0 z (s + T) - qSeq γ a q0 z s) / γ := window_identity hγ s T
  rw [Finset.sum_sub_distrib] at h
  simp only [Finset.sum_const, Finset.card_range, nsmul_eq_mul] at h
  have hTr : (T : ℝ) ≠ 0 := by exact_mod_cast hT.ne'
  have hΔ : qSeq γ a q0 z (s + T) - qSeq γ a q0 z s
      = γ * ((∑ t ∈ range T, err (qSeq γ a q0 z (s + t)) (z (s + t))) - (T : ℝ) * a) := by
    rw [h]
    field_simp
  rw [hΔ]
  field_simp

/-- A3. The V2 gate statistic ρ₃ on a fold, as an identity. -/
theorem fold_ratio (hγ : γ ≠ 0) (ha : a ≠ 0) (s : ℕ) {T : ℕ} (hT : 0 < T) :
    ((∑ t ∈ range T, err (qSeq γ a q0 z (s + t)) (z (s + t))) / T) / a
      = 1 + (qSeq γ a q0 z (s + T) - qSeq γ a q0 z s) / (γ * a * T) := by
  have hfreq : (∑ t ∈ range T, err (qSeq γ a q0 z (s + t)) (z (s + t))) / T - a
      = (qSeq γ a q0 z (s + T) - qSeq γ a q0 z s) / (γ * T) := window_freq hγ s hT
  have hTr : (T : ℝ) ≠ 0 := by exact_mod_cast hT.ne'
  have h2 : (∑ t ∈ range T, err (qSeq γ a q0 z (s + t)) (z (s + t))) / T
      = a + (qSeq γ a q0 z (s + T) - qSeq γ a q0 z s) / (γ * T) := by linarith [hfreq]
  rw [h2]
  field_simp

/-- A4. The threshold cannot escape if the data are bounded. -/
theorem q_bounds {M : ℝ} (hγ : 0 < γ) (ha0 : 0 ≤ a) (ha1 : a ≤ 1) (hz : ∀ t, |z t| ≤ M)
    (hq : |q0| ≤ M) (t : ℕ) :
    -M - γ * a ≤ qSeq γ a q0 z t ∧ qSeq γ a q0 z t ≤ M + γ * (1 - a) := by
  have hγa : 0 ≤ γ * a := mul_nonneg hγ.le ha0
  have hγ1a : 0 ≤ γ * (1 - a) := mul_nonneg hγ.le (by linarith)
  induction t with
  | zero =>
    rw [qSeq_zero]
    obtain ⟨hlo, hhi⟩ := abs_le.mp hq
    constructor <;> linarith
  | succ n ih =>
    have hzn := abs_le.mp (hz n)
    rw [qSeq_succ n]
    by_cases h : qSeq γ a q0 z n < z n
    · have herr : err (qSeq γ a q0 z n) (z n) = 1 := by simp [err, h]
      rw [herr]
      constructor <;> linarith [ih.1, ih.2, h, hzn.1, hzn.2]
    · have herr : err (qSeq γ a q0 z n) (z n) = 0 := by simp [err, h]
      have hle : z n ≤ qSeq γ a q0 z n := le_of_not_gt h
      rw [herr]
      constructor <;> linarith [ih.1, ih.2, hle, hzn.1, hzn.2]

/-- A5. Distribution-free frequency guarantee over every window, on every path. -/
theorem freq_bound {M : ℝ} (hγ : 0 < γ) (ha0 : 0 ≤ a) (ha1 : a ≤ 1) (hz : ∀ t, |z t| ≤ M)
    (hq : |q0| ≤ M) (s : ℕ) {T : ℕ} (hT : 0 < T) :
    |(∑ t ∈ range T, err (qSeq γ a q0 z (s + t)) (z (s + t))) / T - a|
      ≤ (2 * M + γ) / (γ * T) := by
  have hγne : γ ≠ 0 := ne_of_gt hγ
  have hfreq : (∑ t ∈ range T, err (qSeq γ a q0 z (s + t)) (z (s + t))) / T - a
      = (qSeq γ a q0 z (s + T) - qSeq γ a q0 z s) / (γ * T) := window_freq hγne s hT
  have hb1 := q_bounds hγ ha0 ha1 hz hq s
  have hb2 := q_bounds hγ ha0 ha1 hz hq (s + T)
  have hTpos : (0 : ℝ) < T := by exact_mod_cast hT
  have hγT : (0 : ℝ) < γ * T := mul_pos hγ hTpos
  have hsum : γ * (1 - a) + γ * a = γ := by ring
  have habs : |qSeq γ a q0 z (s + T) - qSeq γ a q0 z s| ≤ 2 * M + γ := by
    rw [abs_le]
    constructor <;> linarith [hb1.1, hb1.2, hb2.1, hb2.2]
  rw [hfreq, abs_div, abs_of_pos hγT]
  exact (div_le_div_iff_of_pos_right hγT).mpr habs

/-- A6. Group validity: run one thermostat per bucket and A5 holds inside each bucket. -/
theorem group_freq_bound {M : ℝ} (idx : ℕ → ℕ) (hγ : 0 < γ) (ha0 : 0 ≤ a) (ha1 : a ≤ 1)
    (hz : ∀ t, |z t| ≤ M) (hq : |q0| ≤ M) (s : ℕ) {T : ℕ} (hT : 0 < T) :
    |(∑ t ∈ range T, err (qSeq γ a q0 (z ∘ idx) (s + t)) ((z ∘ idx) (s + t))) / T - a|
      ≤ (2 * M + γ) / (γ * T) := by
  exact freq_bound (z := z ∘ idx) hγ ha0 ha1 (fun t => hz (idx t)) hq s hT

/-- A7. Sigma-unit ticket: at size R/q a move z costs more than R iff it exceeds q. -/
theorem ticket_breach_iff {R q z : ℝ} (hR : 0 < R) (hq : 0 < q) : R / q * z > R ↔ q < z := by
  constructor
  · intro h
    have h1 : R / q * z > R / q * q := by
      have : R / q * q = R := by field_simp
      linarith [h]
    have hpos : (0 : ℝ) < R / q := div_pos hR hq
    exact lt_of_mul_lt_mul_left h1 (le_of_lt hpos)
  · intro h
    have hpos : (0 : ℝ) < R / q := div_pos hR hq
    have h1 : R / q * z > R / q * q := mul_lt_mul_of_pos_left h hpos
    have h2 : R / q * q = R := by field_simp
    linarith [h1]

/-- A8. Therefore budget breaches are counted exactly by A5's exceedances. -/
theorem ticket_count {R : ℝ} (hR : 0 < R) (s T : ℕ)
    (hpos : ∀ t, 0 < qSeq γ a q0 z (s + t)) :
    ∑ t ∈ range T, (if R / qSeq γ a q0 z (s + t) * z (s + t) > R then (1 : ℝ) else 0)
      = ∑ t ∈ range T, err (qSeq γ a q0 z (s + t)) (z (s + t)) := by
  apply Finset.sum_congr rfl
  intro t _
  have hq : 0 < qSeq γ a q0 z (s + t) := hpos t
  have hiff := ticket_breach_iff (R := R) (q := qSeq γ a q0 z (s + t)) (z := z (s + t)) hR hq
  unfold err
  by_cases h : qSeq γ a q0 z (s + t) < z (s + t)
  · rw [if_pos (hiff.mpr h), if_pos h]
  · rw [if_neg (fun hb => h (hiff.mp hb)), if_neg h]

/-- Pinball loss at tail level a. -/
def pinball (a q z : ℝ) : ℝ := a * max (q - z) 0 + (1 - a) * max (z - q) 0

lemma pinball_sub_le (ha0 : 0 ≤ a) (ha1 : a ≤ 1) (q qs zz : ℝ) :
    pinball a q zz - pinball a qs zz ≤ (a - err q zz) * (q - qs) := by
  have h1a : 0 ≤ 1 - a := by linarith
  have hA : a * (qs - zz) ≤ pinball a qs zz := by
    unfold pinball
    have m1 : qs - zz ≤ max (qs - zz) 0 := le_max_left _ _
    have m2 : (0 : ℝ) ≤ max (zz - qs) 0 := le_max_right _ _
    have p1 : a * (qs - zz) ≤ a * max (qs - zz) 0 := mul_le_mul_of_nonneg_left m1 ha0
    have p2 : (0 : ℝ) ≤ (1 - a) * max (zz - qs) 0 := mul_nonneg h1a m2
    linarith
  have hB : (1 - a) * (zz - qs) ≤ pinball a qs zz := by
    unfold pinball
    have m1 : zz - qs ≤ max (zz - qs) 0 := le_max_left _ _
    have m2 : (0 : ℝ) ≤ max (qs - zz) 0 := le_max_right _ _
    have p1 : (1 - a) * (zz - qs) ≤ (1 - a) * max (zz - qs) 0 :=
      mul_le_mul_of_nonneg_left m1 h1a
    have p2 : (0 : ℝ) ≤ a * max (qs - zz) 0 := mul_nonneg ha0 m2
    linarith
  by_cases h : q < zz
  · have herr : err q zz = 1 := by simp [err, h]
    have hq : pinball a q zz = (1 - a) * (zz - q) := by
      unfold pinball
      have e1 : max (q - zz) 0 = 0 := max_eq_right (by linarith)
      have e2 : max (zz - q) 0 = zz - q := max_eq_left (by linarith)
      rw [e1, e2]
      ring
    rw [herr, hq]
    nlinarith [hB]
  · have herr : err q zz = 0 := by simp [err, h]
    have hq : pinball a q zz = a * (q - zz) := by
      unfold pinball
      have hle : zz ≤ q := le_of_not_gt h
      have e1 : max (q - zz) 0 = q - zz := max_eq_left (by linarith)
      have e2 : max (zz - q) 0 = 0 := max_eq_right (by linarith)
      rw [e1, e2]
      ring
    rw [herr, hq]
    nlinarith [hA]

lemma aci_regret_step (hγ : 0 < γ) (ha0 : 0 ≤ a) (ha1 : a ≤ 1) (qs : ℝ) (t : ℕ) :
    pinball a (qSeq γ a q0 z t) (z t) - pinball a qs (z t)
      ≤ ((qSeq γ a q0 z t - qs) ^ 2 - (qSeq γ a q0 z (t + 1) - qs) ^ 2) / (2 * γ)
        + γ / 2 := by
  have hpin := pinball_sub_le ha0 ha1 (qSeq γ a q0 z t) qs (z t)
  have hsq : (qSeq γ a q0 z (t + 1) - qs) ^ 2
      = (qSeq γ a q0 z t - qs) ^ 2
        - 2 * γ * (a - err (qSeq γ a q0 z t) (z t)) * (qSeq γ a q0 z t - qs)
        + γ ^ 2 * (a - err (qSeq γ a q0 z t) (z t)) ^ 2 := by
    rw [qSeq_succ]
    ring
  have hg2 : (a - err (qSeq γ a q0 z t) (z t)) ^ 2 ≤ 1 := by
    by_cases h : qSeq γ a q0 z t < z t
    · have herr : err (qSeq γ a q0 z t) (z t) = 1 := by simp [err, h]
      rw [herr]
      nlinarith [mul_nonneg ha0 (show (0 : ℝ) ≤ 2 - a by linarith)]
    · have herr : err (qSeq γ a q0 z t) (z t) = 0 := by simp [err, h]
      rw [herr]
      nlinarith [mul_nonneg (show (0 : ℝ) ≤ 1 - a by linarith)
        (show (0 : ℝ) ≤ 1 + a by linarith)]
  have hγhalf : (γ / 2) * (a - err (qSeq γ a q0 z t) (z t)) ^ 2 ≤ γ / 2 := by
    have h := mul_le_mul_of_nonneg_left hg2 (show (0 : ℝ) ≤ γ / 2 by linarith)
    simpa using h
  have key : (a - err (qSeq γ a q0 z t) (z t)) * (qSeq γ a q0 z t - qs)
      = ((qSeq γ a q0 z t - qs) ^ 2 - (qSeq γ a q0 z (t + 1) - qs) ^ 2) / (2 * γ)
        + (γ / 2) * (a - err (qSeq γ a q0 z t) (z t)) ^ 2 := by
    have h2γ : (2 : ℝ) * γ ≠ 0 := by
      have : (0 : ℝ) < 2 * γ := by linarith
      exact ne_of_gt this
    rw [hsq]
    field_simp
    ring
  linarith [hpin, key, hγhalf]

/-- A9. Low regret against EVERY fixed sigma threshold, chosen in hindsight, on every path. -/
theorem aci_regret (hγ : 0 < γ) (ha0 : 0 ≤ a) (ha1 : a ≤ 1) (qstar : ℝ) (T : ℕ) :
    ∑ t ∈ range T, (pinball a (qSeq γ a q0 z t) (z t) - pinball a qstar (z t))
      ≤ (q0 - qstar) ^ 2 / (2 * γ) + γ * T / 2 := by
  have hstep : ∀ t ∈ range T,
      pinball a (qSeq γ a q0 z t) (z t) - pinball a qstar (z t)
        ≤ ((qSeq γ a q0 z t - qstar) ^ 2 - (qSeq γ a q0 z (t + 1) - qstar) ^ 2)
          / (2 * γ) + γ / 2 :=
    fun t _ => aci_regret_step hγ ha0 ha1 qstar t
  have hsum := Finset.sum_le_sum hstep
  have htele : (∑ t ∈ range T,
        (((qSeq γ a q0 z t - qstar) ^ 2 - (qSeq γ a q0 z (t + 1) - qstar) ^ 2)
          / (2 * γ) + γ / 2))
      = ((q0 - qstar) ^ 2 - (qSeq γ a q0 z T - qstar) ^ 2) / (2 * γ)
        + γ * T / 2 := by
    rw [Finset.sum_add_distrib]
    have hdiv : (∑ t ∈ range T,
          ((qSeq γ a q0 z t - qstar) ^ 2 - (qSeq γ a q0 z (t + 1) - qstar) ^ 2)
            / (2 * γ))
        = ((qSeq γ a q0 z 0 - qstar) ^ 2 - (qSeq γ a q0 z T - qstar) ^ 2)
          / (2 * γ) := by
      have hcong : (∑ t ∈ range T,
            ((qSeq γ a q0 z t - qstar) ^ 2 - (qSeq γ a q0 z (t + 1) - qstar) ^ 2)
              / (2 * γ))
          = ∑ t ∈ range T,
            ((qSeq γ a q0 z t - qstar) ^ 2 / (2 * γ)
              - (qSeq γ a q0 z (t + 1) - qstar) ^ 2 / (2 * γ)) :=
        Finset.sum_congr rfl (fun t _ => sub_div _ _ _)
      rw [hcong, Finset.sum_range_sub', qSeq_zero, sub_div]
    have hconst : (∑ _t ∈ range T, (γ / 2 : ℝ)) = γ * T / 2 := by
      rw [Finset.sum_const, Finset.card_range, nsmul_eq_mul]
      ring
    rw [hdiv, hconst, qSeq_zero]
  rw [htele] at hsum
  have hnn : (0 : ℝ) ≤ (qSeq γ a q0 z T - qstar) ^ 2 / (2 * γ) :=
    div_nonneg (sq_nonneg _) (by linarith)
  rw [sub_div] at hsum
  linarith [hsum, hnn]

/-- Non-vacuity: a concrete run. Above-threshold print raises q by γ(1−a). -/
theorem qSeq_example : qSeq (1 / 10) (1 / 20) 3 (fun _ => 5) 1 = 3 + (1 / 10) * (1 - 1 / 20) := by
  have hstep : qSeq (1 / 10) (1 / 20) 3 (fun _ => 5) 1
      = (3 : ℝ) + (1 / 10) * (err 3 5 - 1 / 20) := rfl
  have herr : err (3 : ℝ) 5 = 1 := by
    unfold err
    norm_num
  rw [hstep, herr]

end

end PerpChief.ACI
