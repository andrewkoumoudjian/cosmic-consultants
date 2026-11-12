/-
# W2 (#3): proofs of the frozen S2-atlas statements

Proves exactly the three Props frozen in `Analog/Atlas.lean` (statement ID
"S2-atlas"; owner-approved wording, PR #11, frozen at `42cfe45`):
  - `S2a_weight_mono` — nonnegative weightings respect dominance (weakly,
    strictly with a positive weight on a strict coordinate),
  - `S2b_frontier_covers` — every candidate cell is weakly dominated by a
    frontier cell of the same finite set,
  - `S2c_no_unique_minimiser` — a screened-out cell is never the unique
    weighted minimiser under a nonnegative weight family.

The frozen statement file is imported, never edited; a semantics change must
supersede under a new statement ID (STATEMENTS.md rule).
-/
import Mathlib
import Analog.Atlas

namespace Analog.AtlasProofs

open Analog.Atlas Analog.Semantics Finset

/-- Pointwise-monotonicity of the weighted total loss under nonnegative
weights (the weak half of S2a, in reusable form; also drives S2c). -/
private theorem agg_mono {n : ℕ} {a b : Fin n → ℝ} (h : ∀ i, a i ≤ b i)
    {w : Fin n → ℝ} (hw : ∀ i, 0 ≤ w i) : agg w a ≤ agg w b :=
  Finset.sum_le_sum fun i _ => mul_le_mul_of_nonneg_left (h i) (hw i)

/-- **S2a** (frozen statement): strict vector dominance is respected weakly by
every nonnegative weighting, and strictly by any weighting positive on a
strict coordinate. -/
theorem s2a_weight_mono {n : ℕ} : Analog.Atlas.S2a_weight_mono (n := n) := by
  rintro a b ⟨hle, -, -⟩
  refine ⟨fun w hw => agg_mono hle hw, ?_⟩
  intro w i hi hw₀ hwnn
  simp only [agg]
  have hdist : ∑ j, (w j * b j - w j * a j) = ∑ j, w j * b j - ∑ j, w j * a j :=
    Finset.sum_sub_distrib (fun j => w j * b j) (fun j => w j * a j)
  have hpos : 0 < ∑ j, (w j * b j - w j * a j) :=
    Finset.sum_pos'
      (fun j _ => sub_nonneg.mpr (mul_le_mul_of_nonneg_left (hle j) (hwnn j)))
      ⟨i, Finset.mem_univ i, by
        have hp : 0 < w i * (b i - a i) := mul_pos hw₀ (sub_pos.mpr hi)
        rwa [mul_sub] at hp⟩
  have e : ∑ j, w j * b j = ∑ j, w j * a j + ∑ j, (w j * b j - w j * a j) := by
    rw [hdist]
    ring
  rw [e]
  exact lt_add_of_le_of_pos le_rfl hpos

/-- Workhorse for S2b: descent on `U.card`. If `x ∈ U`, some `y ∈ U` that no
member of `U` strictly dominates weakly dominates `x`'s loss vector. -/
private theorem covers_aux {ι : Type*} {n : ℕ} (loss : ι → Fin n → ℝ) :
    ∀ (k : ℕ) (U : Finset ι), U.card ≤ k → ∀ x ∈ U,
      ∃ y, IsFrontierCell U loss y ∧ DominatesOrEq (loss y) (loss x) := by
  classical
  intro k
  induction k with
  | zero =>
    intro U _hU x hx
    exact absurd (Finset.card_pos.mpr ⟨x, hx⟩) (by omega)
  | succ k ih =>
    intro U hU x hx
    by_cases hfront : IsFrontierCell U loss x
    · exact ⟨x, hfront, fun i => le_rfl⟩
    · -- Not frontier: some `z ∈ U` strictly dominates `loss x` (and `z ≠ x`).
      have hz : ∃ z ∈ U, Dominates (loss z) (loss x) := by
        by_contra hno
        push Not at hno
        exact hfront ⟨hx, hno⟩
      obtain ⟨z, hzU, hzdom⟩ := hz
      have hzx : z ≠ x := by
        intro he
        rw [he] at hzdom
        exact not_dominates_self (loss x) hzdom
      -- Recurse inside `U.erase x` (strictly smaller, still contains `z`).
      have hcardL : (U.erase x).card < U.card := Finset.card_erase_lt_of_mem hx
      obtain ⟨y, hyfr, hle⟩ := ih (U.erase x) (by omega) z (Finset.mem_erase.mpr ⟨hzx, hzU⟩)
      obtain ⟨hyU', hyfront⟩ := hyfr
      refine ⟨y, ⟨(Finset.mem_erase.mp hyU').2, ?_⟩, ?_⟩
      · -- Frontier in `U.erase x` plus the `w = x` case handled term-wise:
        -- a strict dominator `w = x` of `loss y` would force
        -- `loss x j < loss y j ≤ loss z j ≤ loss x j`, absurd.
        intro w hwU hwdom
        by_cases hwx : w = x
        · rw [hwx] at hwdom
          obtain ⟨hwle, j, hj⟩ := hwdom
          have heq : loss x j = loss y j :=
            le_antisymm (hwle j) ((hle j).trans (hzdom.1 j))
          rw [heq] at hj
          exact absurd hj (lt_irrefl _)
        · exact hyfront w (Finset.mem_erase.mpr ⟨hwx, hwU⟩) hwdom
      · intro i
        exact (hle i).trans (hzdom.1 i)

/-- **S2b** (frozen statement): every candidate cell of `U` is weakly
dominated by some frontier cell of `U`. -/
theorem s2b_frontier_covers : Analog.Atlas.S2b_frontier_covers :=
  fun {_} {_} U loss x hx => covers_aux loss U.card U le_rfl x hx

/-- **S2c** (frozen statement): under any nonnegative weight family, a
screened-out cell is never the unique weighted minimiser over `U`. -/
theorem s2c_no_unique_minimiser : Analog.Atlas.S2c_no_unique_minimiser := by
  intro ι n U loss W hW x hx _hnf w hw
  have hwnn : ∀ i, 0 ≤ w i := hW w hw
  obtain ⟨y, hyfr, hle⟩ := s2b_frontier_covers U loss x hx
  refine ⟨y, hyfr, ?_⟩
  simp only [agg]
  exact Finset.sum_le_sum fun i _ => mul_le_mul_of_nonneg_left (hle i) (hwnn i)

end Analog.AtlasProofs
