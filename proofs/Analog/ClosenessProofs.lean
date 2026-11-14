/-
# W21 (#80): proofs of the S8 (closeness and Shapley split) statements

Proves exactly the 7 Props in `Analog/Closeness.lean` (statement ID "S8",
PR #84). The statement file is imported, never edited. Accepted only after the
owner freezes #84.

Proof idea in plain words: the closeness of a set of traits is a plain sum, so
adding trait `d` to any coalition adds exactly `d`'s own term. Shapley's value
is a weighted average of those additions, and the weights add up to 1
(`shapley_weights`: group coalitions by size `k`; each size contributes
`C(n-1,k) · k! (n-1-k)! / n! = (n-1)!/n!`, and there are `n` sizes). So each
share is its own term (S8c), and everything else follows.
-/
import Mathlib
import Analog.Closeness

namespace Analog.ClosenessProofs

open Analog.Closeness Finset

variable {δ : Type*} [DecidableEq δ]

/-! ### The Shapley weights add up to 1 -/

private theorem weight_sum (k : ℕ) :
    ∑ m ∈ range (k + 1), (k.choose m) •
      (((Nat.factorial m * Nat.factorial (k + 1 - m - 1) : ℕ) : ℝ) / (Nat.factorial (k + 1) : ℝ)) = 1 := by
  have hterm : ∀ m ∈ range (k + 1), (k.choose m) •
      (((Nat.factorial m * Nat.factorial (k + 1 - m - 1) : ℕ) : ℝ) / (Nat.factorial (k + 1) : ℝ))
        = (Nat.factorial k : ℝ) / (Nat.factorial (k + 1) : ℝ) := by
    intro m hm
    have hm' : m ≤ k := Nat.lt_succ_iff.mp (Finset.mem_range.mp hm)
    have hsub : k + 1 - m - 1 = k - m := by omega
    rw [hsub, nsmul_eq_mul, ← mul_div_assoc]
    congr 1
    rw [← Nat.choose_mul_factorial_mul_factorial hm']
    push_cast; ring
  rw [Finset.sum_congr rfl hterm, Finset.sum_const, Finset.card_range, nsmul_eq_mul, Nat.factorial_succ]
  push_cast
  have h1 : (k : ℝ) + 1 ≠ 0 := by positivity
  have h2 : (Nat.factorial k : ℝ) ≠ 0 := by exact_mod_cast Nat.factorial_ne_zero k
  field_simp

private theorem shapley_weights (T : Finset δ) {d : δ} (hd : d ∈ T) :
    ∑ S ∈ (T.erase d).powerset,
      ((Nat.factorial S.card * Nat.factorial (T.card - S.card - 1) : ℕ) : ℝ) / (Nat.factorial T.card : ℝ) = 1 := by
  obtain ⟨k, hk⟩ : ∃ k, T.card = k + 1 :=
    ⟨T.card - 1, by have := Finset.card_pos.mpr ⟨d, hd⟩; omega⟩
  have hcard : (T.erase d).card = k := by simp [Finset.card_erase_of_mem hd, hk]
  rw [hk]
  have h := Finset.sum_powerset_apply_card (x := T.erase d)
    (f := fun m => ((Nat.factorial m * Nat.factorial (k + 1 - m - 1) : ℕ) : ℝ) / (Nat.factorial (k + 1) : ℝ))
  rw [hcard] at h
  exact h.trans (weight_sum k)

/-! ### S8 -/

omit [DecidableEq δ] in
theorem s8a_nonneg : S8a_nonneg (δ := δ) := by
  intro T scale x y
  unfold closeness term
  exact Finset.sum_nonneg (fun d _ => sq_nonneg _)

omit [DecidableEq δ] in
theorem s8b_zero_iff : S8b_zero_iff (δ := δ) := by
  intro T scale x y hs
  unfold closeness term
  rw [Finset.sum_eq_zero_iff_of_nonneg (fun d _ => sq_nonneg _)]
  refine forall₂_congr fun d hd => ?_
  simp [hs d hd, sub_eq_zero]

theorem s8c_shapley_is_term : S8c_shapley_is_term (δ := δ) := by
  intro T scale x y d hd
  unfold shapley
  have hins : ∀ S ∈ (T.erase d).powerset,
      game scale x y (insert d S) - game scale x y S = term scale x y d := by
    intro S hS
    have hdS : d ∉ S := fun h => by
      have := Finset.mem_powerset.mp hS h
      simp at this
    unfold game; rw [Finset.sum_insert hdS]; ring
  calc ∑ S ∈ (T.erase d).powerset,
        ((Nat.factorial S.card * Nat.factorial (T.card - S.card - 1) : ℕ) : ℝ) / (Nat.factorial T.card : ℝ)
          * (game scale x y (insert d S) - game scale x y S)
      = ∑ S ∈ (T.erase d).powerset,
        ((Nat.factorial S.card * Nat.factorial (T.card - S.card - 1) : ℕ) : ℝ) / (Nat.factorial T.card : ℝ)
          * term scale x y d := Finset.sum_congr rfl (fun S hS => by rw [hins S hS])
    _ = (∑ S ∈ (T.erase d).powerset,
        ((Nat.factorial S.card * Nat.factorial (T.card - S.card - 1) : ℕ) : ℝ) / (Nat.factorial T.card : ℝ))
          * term scale x y d := (Finset.sum_mul _ _ _).symm
    _ = term scale x y d := by rw [shapley_weights T hd, one_mul]

theorem s8d_shares_sum : S8d_shares_sum (δ := δ) := by
  intro T scale x y
  rw [Finset.sum_congr rfl (fun d hd => s8c_shapley_is_term T scale x y d hd)]
  rfl

theorem s8e_share_nonneg : S8e_share_nonneg (δ := δ) := by
  intro T scale x y d hd
  rw [s8c_shapley_is_term T scale x y d hd]
  unfold term
  exact sq_nonneg _

omit [DecidableEq δ] in
theorem s8f_missing_unranked : S8f_missing_unranked (δ := δ) := by
  intro T scale x y
  unfold closenessOpt
  split_ifs with h
  · constructor
    · intro h'; simp at h'
    · rintro ⟨d, hd, hx | hy⟩
      · have := (h d hd).1; rw [hx] at this; exact absurd this (by simp)
      · have := (h d hd).2; rw [hy] at this; exact absurd this (by simp)
  · refine ⟨fun _ => ?_, fun _ => rfl⟩
    push Not at h
    obtain ⟨d, hd, hd'⟩ := h
    refine ⟨d, hd, ?_⟩
    by_cases hx : (x d).isSome
    · right; simpa using hd' hx
    · left; simpa using hx

theorem s8g_share_local : S8g_share_local (δ := δ) := by
  intro T scale x y x' y' d hd hx hy
  rw [s8c_shapley_is_term T scale x' y' d hd, s8c_shapley_is_term T scale x y d hd]
  unfold term; rw [hx, hy]

end Analog.ClosenessProofs
