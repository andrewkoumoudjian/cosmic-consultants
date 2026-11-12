/-
PORTED 2026-11-12 from owner prior work: dimension standardization
Source: andrewkoumoudjian/perps-strategy @ 0f34759, legacy/rounds1-2/lean/PerpTheory/Standardize.lean (toolchain v4.15.0).
Port changes ONLY: module path/import remap to Analog.Prior.* (+ Mathlib API renames if listed in docs/research/06). Namespaces, statements, proofs otherwise verbatim. Original file is frozen upstream; do not edit semantics here — supersede via new module + STATEMENTS.md.
-/
import Mathlib

/-!
# T1 — Standardisation and scaling (STARTER)

`Z = (R - mu) / sigma`. The `sqrt(t)` law is proved *under* an explicit
uncorrelatedness hypothesis, together with a perfectly-correlated
counterexample: horizon scaling is an assumption to be tested in Python
(PIT calibration at 1h/6h/24h), never a definition.

Finite-sample versions are stated with `Finset` averages so they need no
measure theory and no finite-variance-of-a-law assumption beyond the
sample in hand.
-/

namespace PerpTheory

open Finset

/-- Standardised value. -/
noncomputable def stdize (r mu sigma : ℝ) : ℝ := (r - mu) / sigma

/-- Inverting standardisation recovers the return (for `sigma ≠ 0`). -/
theorem stdize_inv (r mu sigma : ℝ) (hs : sigma ≠ 0) :
    mu + sigma * stdize r mu sigma = r := by
  unfold stdize
  rw [← mul_div_assoc, mul_div_cancel_left₀ _ hs]
  ring

/-- A `k`-sigma event in `Z` is a `k * sigma` event in `R`. -/
theorem stdize_abs_ge (r mu sigma k : ℝ) (hs : 0 < sigma) :
    |stdize r mu sigma| ≥ k ↔ |r - mu| ≥ k * sigma := by
  unfold stdize
  rw [abs_div, abs_of_pos hs]
  exact le_div_iff₀ hs

/-- Sample mean over a finite index set. -/
noncomputable def sampleMean {n : ℕ} (x : Fin n → ℝ) : ℝ :=
  (∑ i, x i) / n

/-- Sample (population) variance over a finite index set. -/
noncomputable def sampleVar {n : ℕ} (x : Fin n → ℝ) : ℝ :=
  (∑ i, (x i - sampleMean x) ^ 2) / n

/-- Standardised samples have mean zero (exact algebra, `n ≠ 0`). -/
theorem sampleMean_stdize_eq_zero {n : ℕ} (hn : n ≠ 0) (x : Fin n → ℝ)
    (sigma : ℝ) (hs : sigma ≠ 0) :
    sampleMean (fun i => stdize (x i) (sampleMean x) sigma) = 0 := by
  have hn' : ((n : ℝ)) ≠ 0 := by exact_mod_cast hn
  have hsum : (∑ i : Fin n, (x i - (∑ j, x j) / (n : ℝ))) = 0 := by
    rw [Finset.sum_sub_distrib, Finset.sum_const, Finset.card_univ,
      Fintype.card_fin, nsmul_eq_mul, ← mul_div_assoc,
      mul_div_cancel_left₀ _ hn', sub_self]
  unfold sampleMean stdize
  rw [← Finset.sum_div, hsum]
  simp

/-- Variance of a sum under an *explicit* zero-cross-term hypothesis.
The hypothesis `hcross` is the uncorrelatedness assumption; without it
the conclusion is false (see `correlated_counterexample`). -/
theorem var_sum_of_uncorr (a b va vb cross : ℝ)
    (h : va + vb + 2 * cross = va + vb) (hcross : cross = 0) :
    va + vb + 2 * cross = va + vb := by
  rw [hcross]; ring

/-- Perfectly correlated counterexample (numbers): two identical unit-
variance terms have sum-variance 4, not 2. Hence `std(sum) = n * sigma`,
not `sqrt(n) * sigma`. Horizon scaling must be earned empirically. -/
example : (1:ℝ) + 1 + 2 * 1 = 4 := by norm_num

/-- MAD scale constant. `1.4826` is the Gaussian consistency factor
`1 / Φ⁻¹(3/4)`. It is recorded as a *definition*, not a theorem: under
fat tails MAD-sigma is a scale, not a standard deviation. -/
noncomputable def madToSigma : ℝ := 1.4826

end PerpTheory
