/-
S8 (past-mission closeness and its Shapley split) STATEMENT module (work order
W21, issue #80; ADR-0005 D5, MISSION-PLANNER.md step 6).

This file contains DEFINITIONS and PROPOSITIONS ONLY. Nothing here is proved,
and a `def … : Prop` elaborating is not evidence for it. A follow-up module
`ClosenessProofs.lean` must produce theorems of exactly the `S8…` Props below,
or this file must be superseded by a new statement ID. Never edit it silently
after owner freeze.

Plain-English reading guide (for the owner review):
- ADR-0005 D5 allows ONE "how alike" number, and only between a chosen site and
  a past analog campaign's site: the closeness. It is the sum, over a fixed set
  `T` of traits, of the squared difference divided by that trait's scale (its
  interquartile range over L1). Smaller means more alike.
- It is always shown split per trait by Shapley values. (Shapley values split a
  total fairly between its causes; here the causes are traits.) S8c says that
  for this sum each trait's Shapley share is just its own term, so S8d says the
  shares add up to the closeness exactly (the UI "done when" for step 6) and
  S8e says no share is negative.
- A campaign missing a trait in `T` gets no closeness at all (S8f): it is
  listed apart, never ranked with a made-up value.
- Traits with zero spread or yes/no traits are shown as same/different and are
  left out of `T` by the engine. Lean's `x / 0 = 0` means a zero scale would
  contribute 0; S8b therefore assumes nonzero scales.

What is NOT claimed: that closeness measures scientific similarity, that the
scales are right, or that the engine computes these functions (conformance
check, separate). Closeness never rates a site on its own (AGENTS.md rule 4).
-/
import Mathlib

open Finset

namespace Analog.Closeness

variable {δ : Type*} [DecidableEq δ]

/-- One trait's term: squared difference over the trait's scale. -/
noncomputable def term (scale x y : δ → ℝ) (d : δ) : ℝ :=
  ((x d - y d) / scale d) ^ 2

/-- Closeness over the trait set `T` (contract `precedents[].closeness`). -/
noncomputable def closeness (T : Finset δ) (scale x y : δ → ℝ) : ℝ :=
  ∑ d ∈ T, term scale x y d

/-- The closeness of a coalition `S` of traits: the game Shapley splits. -/
noncomputable def game (scale x y : δ → ℝ) (S : Finset δ) : ℝ :=
  ∑ d ∈ S, term scale x y d

/-- Shapley value of player `d` in game `v` with player set `T`:
`∑_{S ⊆ T \ {d}} |S|! (|T| − |S| − 1)! / |T|! · (v (S ∪ {d}) − v S)`. -/
noncomputable def shapley (T : Finset δ) (v : Finset δ → ℝ) (d : δ) : ℝ :=
  ∑ S ∈ (T.erase d).powerset,
    ((Nat.factorial S.card * Nat.factorial (T.card - S.card - 1) : ℕ) : ℝ) /
      (Nat.factorial T.card : ℝ) * (v (insert d S) - v S)

open Classical in
/-- Closeness when traits may be missing (`none`): defined only when both
sites have every trait in `T`. -/
noncomputable def closenessOpt (T : Finset δ) (scale : δ → ℝ) (x y : δ → Option ℝ) : Option ℝ :=
  if ∀ d ∈ T, (x d).isSome ∧ (y d).isSome then
    some (closeness T scale (fun d => (x d).getD 0) (fun d => (y d).getD 0))
  else none

/-! ## S8 propositions (frozen on owner approval) -/

/-- **S8a closeness is never negative.** -/
def S8a_nonneg : Prop :=
  ∀ (T : Finset δ) (scale x y : δ → ℝ), 0 ≤ closeness T scale x y

/-- **S8b zero means identical on the trait set** (scales nonzero). -/
def S8b_zero_iff : Prop :=
  ∀ (T : Finset δ) (scale x y : δ → ℝ), (∀ d ∈ T, scale d ≠ 0) →
    (closeness T scale x y = 0 ↔ ∀ d ∈ T, x d = y d)

/-- **S8c each trait's Shapley share is its own term.** -/
def S8c_shapley_is_term : Prop :=
  ∀ (T : Finset δ) (scale x y : δ → ℝ), ∀ d ∈ T,
    shapley T (game scale x y) d = term scale x y d

/-- **S8d the shares add up to the closeness exactly.** -/
def S8d_shares_sum : Prop :=
  ∀ (T : Finset δ) (scale x y : δ → ℝ),
    ∑ d ∈ T, shapley T (game scale x y) d = closeness T scale x y

/-- **S8e no negative share.** -/
def S8e_share_nonneg : Prop :=
  ∀ (T : Finset δ) (scale x y : δ → ℝ), ∀ d ∈ T,
    0 ≤ shapley T (game scale x y) d

/-- **S8f a missing trait means no closeness.** The closeness is undefined
exactly when one of the two sites lacks a trait in `T`. -/
def S8f_missing_unranked : Prop :=
  ∀ (T : Finset δ) (scale : δ → ℝ) (x y : δ → Option ℝ),
    closenessOpt T scale x y = none ↔ ∃ d ∈ T, x d = none ∨ y d = none

/-- **S8g a share depends only on its own trait.** Changing either site's
value on other traits never changes trait `d`'s share. -/
def S8g_share_local : Prop :=
  ∀ (T : Finset δ) (scale x y x' y' : δ → ℝ), ∀ d ∈ T,
    x' d = x d → y' d = y d →
      shapley T (game scale x' y') d = shapley T (game scale x y) d

end Analog.Closeness
