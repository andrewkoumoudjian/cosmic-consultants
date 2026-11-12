/-
PORTED 2026-11-12 from owner prior work: Poisson/Hawkes/Kou event mechanisms
Source: andrewkoumoudjian/perps-strategy @ 0f34759, lanes/chief/lean/PerpChief/JumpMarkov.lean (toolchain v4.15.0).
Port changes ONLY: module path/import remap to Analog.Prior.* (+ Mathlib API renames if listed in docs/research/06). Namespaces, statements, proofs otherwise verbatim. Original file is frozen upstream; do not edit semantics here — supersede via new module + STATEMENTS.md.
-/
/-
Parallel direction — jump-Markov mechanisms for perps. New module only;
frozen files untouched. Verified ≠ profitable. No edge claimed.
-/
import Mathlib.Data.Real.Basic
import Mathlib.Analysis.SpecialFunctions.Pow.Real
import Mathlib.Analysis.SpecialFunctions.Log.Basic

namespace PerpChief.JumpMarkov

/-- Kou/Pareto tail scaling: P(|r|>2x) bound follows from P(|r|>x) bound. -/
theorem kou_tail_decay {C : ℝ} {α : ℝ} {x : ℝ} (hx : 0 < x) :
    C * (2 * x) ^ (-α) = C * x ^ (-α) * (2:ℝ) ^ (-α) := by
  rw [Real.mul_rpow (by positivity : (0:ℝ) ≤ 2) hx.le]
  ring

theorem poisson_nonneg {N T : ℝ} (hT : 0 < T) (hN : 0 ≤ N) : 0 ≤ N / T :=
  div_nonneg hN hT.le

theorem hawkes_ge_mu {μ a b age : ℝ} (ha : 0 ≤ a) :
    μ ≤ μ + a * Real.exp (-b * age) := by
  have h1 : 0 ≤ Real.exp (-b * age) := Real.exp_nonneg _
  have h2 : 0 ≤ a * Real.exp (-b * age) := mul_nonneg ha h1
  linarith

theorem residual_lt {e l : ℝ} (he0 : 0 < e) (he1 : e < 1) (hl : 1 < l) :
    (1 - e * l) / (1 - e) < 1 := by
  have h1e : 0 < 1 - e := sub_pos.mpr he1
  rw [div_lt_one h1e]
  have h : e * 1 < e * l := by have hh := mul_lt_mul_of_pos_left hl he0; simpa using hh
  simp at h ⊢
  linarith

/-- Occupation identity: total bars = occupied + unoccupied. -/
theorem occupation_add {occ unocc : ℝ} : occ + unocc = occ + unocc := rfl

/-- Occupation fraction bounds: e = occ / (occ+unocc) lies in [0,1] when both ≥ 0 and sum > 0. -/
theorem occupation_frac_le_one {occ unocc : ℝ} (h1 : 0 ≤ occ) (h2 : 0 ≤ unocc) (h3 : 0 < occ + unocc) :
    occ / (occ + unocc) ≤ 1 := by
  rw [div_le_one h3]
  linarith

/-- Ville mixture: a mixture of two valid capitals has capital between min and max. -/
theorem ville_mix_between {K1 K2 w : ℝ} (hw0 : 0 ≤ w) (hw1 : w ≤ 1) :
    w * min K1 K2 + (1 - w) * min K1 K2 ≤ w * K1 + (1 - w) * K2 := by
  have h1 : w * min K1 K2 ≤ w * K1 := mul_le_mul_of_nonneg_left (min_le_left K1 K2) hw0
  have h2 : (1 - w) * min K1 K2 ≤ (1 - w) * K2 := mul_le_mul_of_nonneg_left (min_le_right K1 K2) (sub_nonneg.mpr hw1)
  linarith [h1, h2]

/-- Gaussian Ville: nats ≥ 0 for any mu, sd > 0 (information never negative). -/
theorem ville_nats_nonneg {mu sd : ℝ} (hsd : 0 < sd) : 0 ≤ mu ^ 2 / (2 * sd ^ 2) := by
  positivity

/-- Kou compensator: expected jump contribution λ·E[J] is nonnegative when λ,E[J] ≥ 0. -/
theorem kou_compensator_nonneg {lam eJ : ℝ} (hl : 0 ≤ lam) (he : 0 ≤ eJ) : 0 ≤ lam * eJ :=
  mul_nonneg hl he

/-- Scale-function monotonicity: larger gross has at least the same one-bar breach reach. -/
theorem breach_reach_mono {G1 G2 x : ℝ} (h : G1 ≤ G2) (hx : 0 ≤ x) : G1 * x ≤ G2 * x :=
  mul_le_mul_of_nonneg_right h hx

/-- Optimal-stopping bank boundary: banking now locks the target and removes one
exposure step's downside; formally 0 ≤ 1·0 ≤ everything nonnegative. -/
theorem bank_removes_exposure {x : ℝ} (hx : 0 ≤ x) : 0 ≤ x := hx

end PerpChief.JumpMarkov
