/-
S2-atlas STATEMENT module (work order #2, ADR-0001 statement gate).

This file contains DEFINITIONS OF PROPOSITIONS ONLY. Nothing here is proved,
and a `def … : Prop` elaborating is not evidence for it. Work order #3 (W2)
must produce theorems of exactly `S2a_weight_mono`, `S2b_frontier_covers` and
`S2c_no_unique_minimiser` below, or this file must be superseded by a new
statement ID — never edited silently after owner freeze.

Reading guide for the owner review:
- `agg w x` is the weighted total loss of cell loss-vector `x` under weights
  `w`. It is a device inside statements/proofs; per S1 it is NEVER published
  as a site score.
- The weight family is a parameter `W`, constrained only by `NonnegWeights`.
  Instantiating `W := BoxFamily lo hi` (per-dimension weight ranges) is the
  proposed atlas choice; the frozen Props do not depend on that choice.
- Degenerate cases, by construction: empty candidate set `U` makes every
  claim vacuous; `n = 0` scored dimensions makes `Dominates` unattainable
  (no strict coordinate exists), so everything is frontier — consistent.
  Zero weights are allowed: S2a then gives `≤` only; strictness needs a
  weight positive on a strict coordinate (stated in S2a, second conjunct).
- What is NOT claimed: that `loss` measures reality (empirical, brief P8);
  that any executing code computes `FrontierCells` correctly (that is the
  engine conformance obligation, S3-atlas); anything about weights with
  negative components (excluded by hypothesis, on purpose).
-/
import Analog.Semantics

open Finset

namespace Analog.Atlas

open Analog.Semantics

/-- Weighted total loss (proof device only; never a published score). -/
def agg {n : ℕ} (w x : Fin n → ℝ) : ℝ :=
  ∑ i, w i * x i

/-- Every weight in the family is componentwise nonnegative. -/
def NonnegWeights {n : ℕ} (W : Set (Fin n → ℝ)) : Prop :=
  ∀ w ∈ W, ∀ i, 0 ≤ w i

/-- Per-dimension weight ranges: the proposed atlas weight family. -/
def BoxFamily {n : ℕ} (lo hi : Fin n → ℝ) : Set (Fin n → ℝ) :=
  {w | ∀ i, lo i ≤ w i ∧ w i ≤ hi i}

/-- Weak dominance: at least as good on every scored dimension. -/
def DominatesOrEq {n : ℕ} (a b : Fin n → ℝ) : Prop :=
  ∀ i, a i ≤ b i

/-- A cell is frontier in `U` when no cell of `U` strictly dominates its
loss vector. Stated directly on cells (a `Prop`, no decidability burden);
its agreement with the frozen S1 `IsFrontier` on the loss image of `U` is
itself a W2 obligation, noted here so the reviewer can object early. -/
def IsFrontierCell {ι : Type*} {n : ℕ} (U : Finset ι) (loss : ι → Fin n → ℝ)
    (x : ι) : Prop :=
  x ∈ U ∧ ∀ y ∈ U, ¬ Dominates (loss y) (loss x)

/-- S2a (weight monotonicity): strict vector dominance is respected by every
nonnegative weighting (weakly), and strictly by any weighting positive on a
strict coordinate. -/
def S2a_weight_mono {n : ℕ} : Prop :=
  ∀ (a b : Fin n → ℝ), Dominates a b →
    (∀ w : Fin n → ℝ, (∀ i, 0 ≤ w i) → agg w a ≤ agg w b) ∧
    (∀ (w : Fin n → ℝ) (i : Fin n), a i < b i → 0 < w i →
      (∀ j, 0 ≤ w j) → agg w a < agg w b)

/-- S2b (frontier covers): every candidate cell is weakly dominated by some
frontier cell. This is the finite-descent heart of screening exactness:
discarding non-frontier cells cannot remove the last weakly-best witness
for any cell. -/
def S2b_frontier_covers : Prop :=
  ∀ {ι : Type*} {n : ℕ} (U : Finset ι) (loss : ι → Fin n → ℝ) (x : ι),
    x ∈ U → ∃ y, IsFrontierCell U loss y ∧ DominatesOrEq (loss y) (loss x)

/-- S2c (no unique minimiser off the frontier): under any nonnegative weight
family, a screened-out (non-frontier) cell is never the unique weighted
minimiser over `U`. This is the certificate the atlas publishes next to its
elimination counts (`contracts/certificate.schema.json`). -/
def S2c_no_unique_minimiser : Prop :=
  ∀ {ι : Type*} {n : ℕ} (U : Finset ι) (loss : ι → Fin n → ℝ)
    (W : Set (Fin n → ℝ)), NonnegWeights W →
    ∀ x ∈ U, ¬ IsFrontierCell U loss x → ∀ w ∈ W,
      ∃ y, IsFrontierCell U loss y ∧ agg w (loss y) ≤ agg w (loss x)

end Analog.Atlas
