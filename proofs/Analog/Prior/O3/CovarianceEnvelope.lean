/-
PORTED 2026-11-12 from owner prior work: quadratic error envelope
Source: andrewkoumoudjian/perps-strategy @ 0f34759, lanes/chief/lean/PerpChief/O3/CovarianceEnvelope.lean (toolchain v4.15.0).
Port changes ONLY: module path/import remap to Analog.Prior.* (+ Mathlib API renames if listed in docs/research/06). Namespaces, statements, proofs otherwise verbatim. Original file is frozen upstream; do not edit semantics here — supersede via new module + STATEMENTS.md.
-/
import Mathlib

namespace PerpChief.O3.CovarianceEnvelope

open scoped BigOperators

def quadratic {n : ℕ} (w : Fin n → ℝ) (a : Fin n → Fin n → ℝ) : ℝ :=
  ∑ i, ∑ j, w i * a i j * w j

def gross {n : ℕ} (w : Fin n → ℝ) : ℝ := ∑ i, |w i|

theorem quadratic_error {n : ℕ} (w : Fin n → ℝ)
    (a b : Fin n → Fin n → ℝ) (e : ℝ) (he : 0 ≤ e)
    (hab : ∀ i j, |a i j - b i j| ≤ e) :
    |quadratic w a - quadratic w b| ≤ e * gross w ^ 2 := by
  have hd : quadratic w a - quadratic w b =
      ∑ i, ∑ j, w i * (a i j - b i j) * w j := by
    simp [quadratic, mul_sub, sub_mul, Finset.sum_sub_distrib]
  rw [hd]
  calc
    |∑ i, ∑ j, w i * (a i j - b i j) * w j|
        ≤ ∑ i, |∑ j, w i * (a i j - b i j) * w j| :=
      Finset.abs_sum_le_sum_abs _ _
    _ ≤ ∑ i, ∑ j, |w i * (a i j - b i j) * w j| := by
      exact Finset.sum_le_sum fun i _ => Finset.abs_sum_le_sum_abs _ _
    _ ≤ ∑ i, ∑ j, |w i| * e * |w j| := by
      apply Finset.sum_le_sum
      intro i _
      apply Finset.sum_le_sum
      intro j _
      simp only [abs_mul]
      exact mul_le_mul_of_nonneg_right
        (mul_le_mul_of_nonneg_left (hab i j) (abs_nonneg _)) (abs_nonneg _)
    _ = (∑ i, |w i| * e) * (∑ j, |w j|) := by
      exact (Finset.sum_mul_sum Finset.univ Finset.univ
        (fun i => |w i| * e) (fun j => |w j|)).symm
    _ = e * gross w ^ 2 := by
      rw [← Finset.sum_mul]
      unfold gross
      ring

theorem conservative_cap {n : ℕ} (w : Fin n → ℝ)
    (a b : Fin n → Fin n → ℝ) (e cap : ℝ) (he : 0 ≤ e)
    (hab : ∀ i j, |a i j - b i j| ≤ e)
    (hcap : quadratic w b + e * gross w ^ 2 ≤ cap) :
    quadratic w a ≤ cap := by
  have h := (le_abs_self (quadratic w a - quadratic w b)).trans
    (quadratic_error w a b e he hab)
  linarith

theorem one_coordinate_tight (e x : ℝ) (he : 0 ≤ e) :
    |x * e * x| = e * |x| ^ 2 := by
  rw [abs_mul, abs_mul, abs_of_nonneg he]
  ring

end PerpChief.O3.CovarianceEnvelope
