/-
PORTED 2026-11-12 from owner prior work: score sensitivity to weight error
Source: andrewkoumoudjian/perps-strategy @ 0f34759, lanes/chief/lean/PerpChief/O3/WeightError.lean (toolchain v4.15.0).
Port changes ONLY: module path/import remap to Analog.Prior.* (+ Mathlib API renames if listed in docs/research/06). Namespaces, statements, proofs otherwise verbatim. Original file is frozen upstream; do not edit semantics here — supersede via new module + STATEMENTS.md.
-/
import Analog.Prior.O3.CovarianceEnvelope

namespace PerpChief.O3.WeightError

open scoped BigOperators
open PerpChief.O3.CovarianceEnvelope

def exposureError {n : ℕ} (v w : Fin n → ℝ) : ℝ := ∑ i, |v i - w i|

theorem weight_error {n : ℕ} (v w : Fin n → ℝ)
    (a : Fin n → Fin n → ℝ) (m : ℝ) (hm : 0 ≤ m)
    (ha : ∀ i j, |a i j| ≤ m) :
    |quadratic v a - quadratic w a| ≤
      m * (gross v + gross w) * exposureError v w := by
  have hd : quadratic v a - quadratic w a =
      ∑ i, ∑ j, a i j * (v i * v j - w i * w j) := by
    unfold quadratic
    rw [← Finset.sum_sub_distrib]
    apply Finset.sum_congr rfl
    intro i _
    rw [← Finset.sum_sub_distrib]
    apply Finset.sum_congr rfl
    intro j _
    ring
  rw [hd]
  have hterm : ∀ i j, |a i j * (v i * v j - w i * w j)| ≤
      m * (|v i - w i| * |v j| + |w i| * |v j - w j|) := by
    intro i j
    rw [abs_mul]
    have hdiff : v i * v j - w i * w j =
        (v i - w i) * v j + w i * (v j - w j) := by ring
    have hb : |v i * v j - w i * w j| ≤
        |v i - w i| * |v j| + |w i| * |v j - w j| := by
      rw [hdiff]
      calc
        |(v i - w i) * v j + w i * (v j - w j)|
            ≤ |(v i - w i) * v j| + |w i * (v j - w j)| := abs_add_le _ _
        _ = |v i - w i| * |v j| + |w i| * |v j - w j| := by
            rw [abs_mul, abs_mul]
    exact mul_le_mul (ha i j) hb (abs_nonneg _) hm
  have hA : ∑ i, ∑ j, |v i - w i| * |v j| =
      (∑ i, |v i - w i|) * (∑ j, |v j|) := by
    rw [Finset.sum_mul_sum]
  have hB : ∑ i, ∑ j, |w i| * |v j - w j| =
      (∑ i, |w i|) * (∑ j, |v j - w j|) := by
    rw [Finset.sum_mul_sum]
  have hC : ∑ i, ∑ j, m * (|v i - w i| * |v j| + |w i| * |v j - w j|) =
      m * ((∑ i, ∑ j, |v i - w i| * |v j|) +
           (∑ i, ∑ j, |w i| * |v j - w j|)) := by
    rw [mul_add, Finset.mul_sum, Finset.mul_sum]
    rw [← Finset.sum_add_distrib]
    apply Finset.sum_congr rfl
    intro i _
    rw [Finset.mul_sum, Finset.mul_sum]
    rw [← Finset.sum_add_distrib]
    apply Finset.sum_congr rfl
    intro j _
    ring
  calc
    |∑ i, ∑ j, a i j * (v i * v j - w i * w j)|
        ≤ ∑ i, |∑ j, a i j * (v i * v j - w i * w j)| :=
      Finset.abs_sum_le_sum_abs _ _
    _ ≤ ∑ i, ∑ j, |a i j * (v i * v j - w i * w j)| :=
      Finset.sum_le_sum fun i _ => Finset.abs_sum_le_sum_abs _ _
    _ ≤ ∑ i, ∑ j, m * (|v i - w i| * |v j| + |w i| * |v j - w j|) :=
      Finset.sum_le_sum fun i _ => Finset.sum_le_sum fun j _ => hterm i j
    _ = m * ((∑ i, |v i - w i|) * (∑ j, |v j|) +
             (∑ i, |w i|) * (∑ j, |v j - w j|)) := by
      rw [hC, hA, hB]
    _ = m * (gross v + gross w) * exposureError v w := by
      unfold gross exposureError
      ring

theorem bounded_weight_error {n : ℕ} (v w : Fin n → ℝ)
    (a : Fin n → Fin n → ℝ) (m g d : ℝ)
    (hm : 0 ≤ m) (hg : 0 ≤ g) (hd : 0 ≤ d)
    (ha : ∀ i j, |a i j| ≤ m) (hw : gross w ≤ g)
    (hv : exposureError v w ≤ d) :
    |quadratic v a - quadratic w a| ≤ m * d * (2 * g + d) := by
  have hδ : 0 ≤ exposureError v w := by
    unfold exposureError
    exact Finset.sum_nonneg fun i _ => abs_nonneg _
  have hGv : 0 ≤ gross v := by
    unfold gross
    exact Finset.sum_nonneg fun i _ => abs_nonneg _
  have hGvd : gross v ≤ g + d := by
    calc
      gross v = ∑ i, |v i| := rfl
      _ = ∑ i, |w i + (v i - w i)| := by
          apply Finset.sum_congr rfl
          intro i _
          congr 1
          ring
      _ ≤ ∑ i, (|w i| + |v i - w i|) := by
          apply Finset.sum_le_sum
          intro i _
          exact abs_add_le _ _
      _ = gross w + exposureError v w := by
          unfold gross exposureError
          rw [Finset.sum_add_distrib]
      _ ≤ g + d := add_le_add hw hv
  have hprod : (gross v + gross w) * exposureError v w ≤ (2 * g + d) * d := by
    have hsum : gross v + gross w ≤ (g + d) + g := add_le_add hGvd hw
    have h := mul_le_mul hsum hv hδ (by linarith : (0:ℝ) ≤ (g + d) + g)
    calc
      (gross v + gross w) * exposureError v w ≤ ((g + d) + g) * d := h
      _ = (2 * g + d) * d := by ring
  calc
    |quadratic v a - quadratic w a|
        ≤ m * (gross v + gross w) * exposureError v w :=
      weight_error v w a m hm ha
    _ = m * ((gross v + gross w) * exposureError v w) := by ring
    _ ≤ m * ((2 * g + d) * d) := mul_le_mul_of_nonneg_left hprod hm
    _ = m * d * (2 * g + d) := by ring

end PerpChief.O3.WeightError
