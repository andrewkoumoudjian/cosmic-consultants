/-
Suboptimality certificate (analog score certificate (ported from fastopt.ipm)).

For a convex objective `f` with gradient `g` at an iterate `z` (feasible or
not), multipliers `lam >= 0` for `G z <= h` and `y` for `E z = e`, and the
dual residual `r_d = g + G' lam + E' y`, every *feasible* `z*` satisfies

  f z - f z*  <=  lam'(h - G z) + y'(e - E z) + M * ||z - z*||_1,

where `M >= ||r_d||_inf`.  The code evaluates the right-hand side with the
returned `(z, lam, y)` (`info["dual_term"]`) and an L1 diameter of the
feasible set in place of `||z - z*||_1`.

`hconv` is the first-order convexity inequality
`f z* >= f z + g'(z* - z)`; for the convex quadratics fastopt solves
(`1/2 z'Pz + c'z`, `P` PSD) it holds with `g = P z + c`.
-/
import Mathlib

open Finset

namespace Analog.Certificate

theorem subopt_le {n r p : ℕ} (f : (Fin n → ℝ) → ℝ) (z zs g : Fin n → ℝ)
    (G : Fin r → Fin n → ℝ) (h lam : Fin r → ℝ)
    (E : Fin p → Fin n → ℝ) (e y : Fin p → ℝ) (M : ℝ)
    (hconv : f z - f zs ≤ ∑ i, g i * (z i - zs i))
    (hfeas : ∀ j, ∑ i, G j i * zs i ≤ h j)
    (heq : ∀ k, ∑ i, E k i * zs i = e k)
    (hlam : ∀ j, 0 ≤ lam j)
    (hM : ∀ i, |g i + ∑ j, G j i * lam j + ∑ k, E k i * y k| ≤ M) :
    f z - f zs ≤ ∑ j, lam j * (h j - ∑ i, G j i * z i)
               + ∑ k, y k * (e k - ∑ i, E k i * z i)
               + M * ∑ i, |z i - zs i| := by
  -- shorthand
  set d : Fin n → ℝ := fun i => z i - zs i with hd
  set rd : Fin n → ℝ := fun i => g i + ∑ j, G j i * lam j + ∑ k, E k i * y k with hrd
  -- swap the order of the double sums
  have hG : ∑ i, (∑ j, G j i * lam j) * d i = ∑ j, lam j * ∑ i, G j i * d i := by
    simp_rw [Finset.sum_mul, Finset.mul_sum]
    rw [Finset.sum_comm]
    exact Finset.sum_congr rfl fun j _ => Finset.sum_congr rfl fun i _ => by ring
  have hE : ∑ i, (∑ k, E k i * y k) * d i = ∑ k, y k * ∑ i, E k i * d i := by
    simp_rw [Finset.sum_mul, Finset.mul_sum]
    rw [Finset.sum_comm]
    exact Finset.sum_congr rfl fun k _ => Finset.sum_congr rfl fun i _ => by ring
  -- g = rd - G' lam - E' y
  have hsplit : ∑ i, g i * d i
      = ∑ i, rd i * d i - ∑ i, (∑ j, G j i * lam j) * d i
          - ∑ i, (∑ k, E k i * y k) * d i := by
    rw [← Finset.sum_sub_distrib, ← Finset.sum_sub_distrib]
    exact Finset.sum_congr rfl fun i _ => by simp only [hrd]; ring
  -- Hölder: rd'd <= M ||d||_1
  have hHolder : ∑ i, rd i * d i ≤ M * ∑ i, |d i| := by
    rw [Finset.mul_sum]
    refine Finset.sum_le_sum fun i _ => ?_
    calc rd i * d i ≤ |rd i * d i| := le_abs_self _
      _ = |rd i| * |d i| := abs_mul _ _
      _ ≤ M * |d i| := mul_le_mul_of_nonneg_right (hM i) (abs_nonneg _)
  -- inequality rows: -lam'G d <= lam'(h - G z)
  have hIneq : -(∑ j, lam j * ∑ i, G j i * d i) ≤ ∑ j, lam j * (h j - ∑ i, G j i * z i) := by
    rw [← Finset.sum_neg_distrib]
    refine Finset.sum_le_sum fun j _ => ?_
    have hdj : ∑ i, G j i * d i = ∑ i, G j i * z i - ∑ i, G j i * zs i := by
      rw [← Finset.sum_sub_distrib]
      exact Finset.sum_congr rfl fun i _ => by simp only [hd]; ring
    rw [hdj]
    nlinarith [mul_le_mul_of_nonneg_left (hfeas j) (hlam j)]
  -- equality rows: -y'E d = y'(e - E z)
  have hEq : -(∑ k, y k * ∑ i, E k i * d i) = ∑ k, y k * (e k - ∑ i, E k i * z i) := by
    rw [← Finset.sum_neg_distrib]
    refine Finset.sum_congr rfl fun k _ => ?_
    have hdk : ∑ i, E k i * d i = ∑ i, E k i * z i - e k := by
      rw [← heq k, ← Finset.sum_sub_distrib]
      exact Finset.sum_congr rfl fun i _ => by simp only [hd]; ring
    rw [hdk]
    ring
  have hconv' : f z - f zs ≤ ∑ i, g i * d i := hconv
  have hd1 : ∑ i, |z i - zs i| = ∑ i, |d i| := rfl
  rw [hd1]
  linarith [hconv', hsplit, hG, hE, hHolder, hIneq, hEq]

end Analog.Certificate
