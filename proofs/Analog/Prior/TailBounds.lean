/-
PORTED 2026-11-12 from owner prior work: finite Chebyshev / tail laws
Source: andrewkoumoudjian/perps-strategy @ 0f34759, legacy/rounds1-2/lean/PerpTheory/TailBounds.lean (toolchain v4.15.0).
Port changes ONLY: module path/import remap to Analog.Prior.* (+ Mathlib API renames if listed in docs/research/06). Namespaces, statements, proofs otherwise verbatim. Original file is frozen upstream; do not edit semantics here — supersede via new module + STATEMENTS.md.
-/
import Mathlib

/-!
# T3/T4 — Sigma-probability bounds and assumed tail laws (STARTER)

The only honest sigma-probability statements while the tail index is
undecided (programme estimates span 1.17–5.8) are distribution-free
bounds *conditional on finite variance*. At `k = 3`: Chebyshev 11.1%,
Cantelli 10% — versus Gaussian 0.27%. That gap is the size of model
risk, stated as a theorem.

Finite-sample Chebyshev is proved by counting: the sum of squared
deviations bounds the number of `k`-sigma exceedances. Parametric laws
(Student-t, GPD) enter only as an assumed `TailLaw` structure; no
theorem asserts perps follow them. Python must earn a law by PIT
calibration.
-/

namespace PerpTheory

open Finset

/-- Finite-sample Chebyshev (counting form). If the average squared
deviation from `mu` is at most `sigma^2`, then the fraction of points
with `|x - mu| ≥ k * sigma` is at most `1 / k^2`. -/
theorem chebyshev_finite {n : ℕ} (_hn : 0 < n) (x : Fin n → ℝ)
    (mu sigma k : ℝ) (hs : 0 < sigma) (hk : 0 < k)
    (hvar : (∑ i, (x i - mu) ^ 2) ≤ n * sigma ^ 2) :
    ((Finset.univ.filter (fun i => |x i - mu| ≥ k * sigma)).card : ℝ)
      ≤ n / k ^ 2 := by
  classical
  set S := Finset.univ.filter (fun i => |x i - mu| ≥ k * sigma) with hS
  have hbound : (∑ i ∈ S, (x i - mu) ^ 2) ≤ ∑ i, (x i - mu) ^ 2 :=
    Finset.sum_le_sum_of_subset_of_nonneg (Finset.filter_subset _ _)
      (fun i _ _ => sq_nonneg _)
  have hlow : (S.card : ℝ) * (k * sigma) ^ 2 ≤ ∑ i ∈ S, (x i - mu) ^ 2 := by
    have hconst : (S.card : ℝ) * (k * sigma) ^ 2
        = ∑ _i ∈ S, (k * sigma) ^ 2 := by
      rw [Finset.sum_const, nsmul_eq_mul]
    rw [hconst]
    apply Finset.sum_le_sum
    intro i hi
    have hi' : |x i - mu| ≥ k * sigma := (Finset.mem_filter.mp hi).2
    have hnn : 0 ≤ k * sigma := by positivity
    have hsq : (x i - mu) ^ 2 = |x i - mu| ^ 2 := (sq_abs _).symm
    rw [hsq]
    nlinarith [hi', hnn, abs_nonneg (x i - mu)]
  have hchain : (S.card : ℝ) * (k * sigma) ^ 2 ≤ (n : ℝ) * sigma ^ 2 :=
    le_trans (le_trans hlow hbound) hvar
  have hs2 : (0:ℝ) < sigma ^ 2 := by positivity
  have hmul : ((S.card : ℝ) * k ^ 2) * sigma ^ 2 ≤ (n : ℝ) * sigma ^ 2 := by
    have e : (k * sigma) ^ 2 = k ^ 2 * sigma ^ 2 := by ring
    rw [e] at hchain
    calc ((S.card : ℝ) * k ^ 2) * sigma ^ 2
        = (S.card : ℝ) * (k ^ 2 * sigma ^ 2) := by ring
      _ ≤ (n : ℝ) * sigma ^ 2 := hchain
  have h2 : (S.card : ℝ) * k ^ 2 ≤ (n : ℝ) :=
    le_of_mul_le_mul_right hmul hs2
  rw [le_div_iff₀ (by positivity : (0:ℝ) < k ^ 2)]
  exact h2

/-- Cantelli (one-sided) bound *values*: `1 / (1 + k^2)`. The full
measure-theoretic Cantelli proof is deferred; the starter records the
bound function and its `k = 3` value so Python and Lean agree on the
number. Chebyshev above is the proved two-sided bound. -/
noncomputable def cantelliBound (k : ℝ) : ℝ := 1 / (1 + k ^ 2)

example : cantelliBound 3 = 1 / 10 := by
  unfold cantelliBound; norm_num

/-- Chebyshev bound value at `k = 3` is `1/9 ≈ 11.1%`. -/
example : (1:ℝ) / 3 ^ 2 = 1 / 9 := by norm_num

/-- An *assumed* tail law: a CDF together with whatever tail hypotheses
the caller supplies. Nothing here claims perps follow `F`. -/
structure TailLaw where
  cdf : ℝ → ℝ
  mono : Monotone cdf
  ge_zero : ∀ z, 0 ≤ cdf z
  le_one : ∀ z, cdf z ≤ 1

/-- Two-sided exceedance probability under an assumed law, by
definition: `P(|Z| > k) = 1 - F(k) + F(-k)` (with the usual abuse at
atoms; Python uses the fitted continuous CDF). -/
noncomputable def exceedProb (L : TailLaw) (k : ℝ) : ℝ :=
  1 - L.cdf k + L.cdf (-k)

/-- GPD exceedance form (assumed, `xi ≠ 0`):
`P(R > u + x | R > u) = (1 + xi * x / beta) ^ (-1 / xi)`.
Recorded as a definition; fitting and threshold choice are Python's
burden (pre-registered POT sweep). -/
noncomputable def gpdExceed (xi beta x : ℝ) : ℝ :=
  (1 + xi * x / beta) ^ (-1 / xi : ℝ)

/-- Bhatia–Davis (algebraic core): for a value in `[-H, H]`,
`(x - mu)^2 ≤ (H - mu)(mu + H) + (something)` — starter records the
pointwise bound `(x - mu)^2 ≤ (|mu| + H)^2` actually used to keep a
*truncated* (liquidation-bounded) variance finite. -/
theorem sq_dev_bounded (x mu H : ℝ) (hx : |x| ≤ H) :
    (x - mu) ^ 2 ≤ (|mu| + H) ^ 2 := by
  have h1 : |x - mu| ≤ |mu| + H := by
    calc |x - mu| = |x + (-mu)| := by ring_nf
      _ ≤ |x| + |-mu| := abs_add_le x (-mu)
      _ = |x| + |mu| := by rw [abs_neg]
      _ ≤ |mu| + H := by linarith [hx]
  have hsq : (x - mu) ^ 2 = |x - mu| ^ 2 := (sq_abs _).symm
  have hnn : 0 ≤ |mu| + H :=
    add_nonneg (abs_nonneg mu) (le_trans (abs_nonneg x) hx)
  rw [hsq]
  nlinarith [h1, hnn, abs_nonneg (x - mu)]

end PerpTheory
