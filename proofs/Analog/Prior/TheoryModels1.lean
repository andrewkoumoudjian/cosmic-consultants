/-
PORTED 2026-11-12 from owner prior work: metric identity batch
Source: andrewkoumoudjian/perps-strategy @ 0f34759, lanes/chief/lean/PerpChief/TheoryModels1.lean (toolchain v4.15.0).
Port changes ONLY: module path/import remap to Analog.Prior.* (+ Mathlib API renames if listed in docs/research/06). Namespaces, statements, proofs otherwise verbatim. Original file is frozen upstream; do not edit semantics here.
-/
/- Frozen deterministic identities for the first executed theory-model batch.
They certify metric arithmetic, not a return law, an edge, a sharp
Courtade-Kumar result, or an MP/GOE limit for market observations. -/
import Analog.Prior.ACI
import Analog.Prior.BinaryInfo
import Mathlib.Tactic

namespace PerpChief.TheoryModels1
open Finset

noncomputable def balancedAccuracy (p q : ℝ) : ℝ :=
  (max p q + max (1 - p) (1 - q)) / 2

/-- Optimal binary decoding under equal class priors, not raw accuracy. -/
theorem binary_balanced_accuracy (p q : ℝ) :
    balancedAccuracy p q = (1 + |p - q|) / 2 := by
  unfold balancedAccuracy
  rcases le_total p q with h | h
  · rw [max_eq_right h, max_eq_left (show 1 - q ≤ 1 - p by linarith), abs_of_nonpos (by linarith : p - q ≤ 0)]
    ring
  · rw [max_eq_left h, max_eq_right (show 1 - p ≤ 1 - q by linarith), abs_of_nonneg (by linarith : 0 ≤ p - q)]
    ring

/-- TV of the two Bernoulli class-conditional state laws. -/
theorem binary_tv (p q : ℝ) :
    (|p - q| + |(1 - p) - (1 - q)|) / 2 = |p - q| := by
  have h : (1 - p) - (1 - q) = -(p - q) := by ring
  rw [h, abs_neg]
  ring

/-- Finite spectral displacement under the stated trace normalization. -/
theorem spectral_displacement {n : ℕ} (l : Fin n → ℝ)
    (ht : ∑ i, l i = (n : ℝ)) :
    ∑ i, (l i - 1) ^ 2 = (∑ i, l i ^ 2) - n := by
  have hex : ∀ i : Fin n, (l i - 1) ^ 2 = l i ^ 2 - 2 * l i + 1 := by
    intro i
    ring
  simp_rw [hex]
  rw [Finset.sum_add_distrib, Finset.sum_sub_distrib, ← Finset.mul_sum, ht]
  simp
  ring

/-- Squared variance forecast loss is nonnegative, with no model assumption. -/
theorem variance_loss_nonneg (v r : ℝ) : 0 ≤ (v - r ^ 2) ^ 2 := by
  exact sq_nonneg _

/-- Paired proper-score comparisons retain their observation pairing. -/
theorem paired_score_sum {n : ℕ} (a b : Fin n → ℝ) :
    ∑ i, (a i - b i) = (∑ i, a i) - ∑ i, b i := by
  rw [Finset.sum_sub_distrib]

/-- Bucket-local ACI has the same exact pathwise certificate. -/
theorem bucket_aci_identity (γ a q0 : ℝ) (z : ℕ → ℝ)
    (idx : ℕ → ℕ) (hγ : γ ≠ 0) (s T : ℕ) :
    ∑ t ∈ range T,
      (PerpChief.ACI.err (PerpChief.ACI.qSeq γ a q0 (z ∘ idx) (s + t))
        ((z ∘ idx) (s + t)) - a)
      = (PerpChief.ACI.qSeq γ a q0 (z ∘ idx) (s + T)
        - PerpChief.ACI.qSeq γ a q0 (z ∘ idx) s) / γ := by
  exact PerpChief.ACI.window_identity hγ s T

end PerpChief.TheoryModels1
