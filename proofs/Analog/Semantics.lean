/-
S1 / S5 (ADR-0001): analogy semantics shared by both target bodies.

Orientation convention (frozen with this file): every dimension is a *loss* —
`0` is a perfect match to the target envelope and larger is worse. Executing
code must map raw measurements into this orientation; it may not invent its own.

What is proved here today is deliberately small and fully checked: dominance is
irreflexive and transitive, and a dominated cell is not on the Pareto frontier.
The problem-specific forms of S2 (screening ⇒ off-frontier for the declared
weight family) build on `Analog.Screening` and are tracked in STATEMENTS.md —
they are NOT claimed by this file.
-/
import Mathlib

open Finset

namespace Analog.Semantics

/-- Target bodies. One methodology: both are instances of the same types below. -/
inductive Body
  | moon
  | mars
  deriving DecidableEq, Repr

/-- Dimensions on which no Earth location can be analogous, per the challenge
brief: reduced gravity, the pressure regime (lunar vacuum / thin Martian
atmosphere), and the radiation environment. These are breakdowns by
construction, never scored dimensions. -/
inductive PermanentMismatch
  | gravity
  | pressureRegime
  | radiation
  deriving DecidableEq, Repr

/-- A target envelope over `n` scored dimensions: acceptable loss interval per
dimension. `valid` is part of the data, so an ill-formed envelope cannot be
constructed by executing code that conforms to this spec. -/
structure Envelope (n : ℕ) where
  lo : Fin n → ℝ
  hi : Fin n → ℝ
  valid : ∀ i, lo i ≤ hi i

/-- Body-tagged envelope (S5): Moon and Mars targets have the same type, so
cross-body statements can only be made through shared dimensions. -/
structure TargetEnvelope (n : ℕ) where
  body : Body
  envelope : Envelope n

/-- Loss vector `x` lies in envelope `e` on every scored dimension. -/
def InEnvelope {n : ℕ} (e : Envelope n) (x : Fin n → ℝ) : Prop :=
  ∀ i, e.lo i ≤ x i ∧ x i ≤ e.hi i

/-- Per-dimension analogy record published for a site: a loss score plus an
explicit breakdown flag per dimension (brief requirement R4). A single scalar
similarity score is not representable here on purpose. -/
structure AnalogyVector (n : ℕ) where
  loss : Fin n → ℝ
  breakdown : Fin n → Bool

/-- Pareto dominance on loss vectors: at least as good everywhere, strictly
better somewhere. -/
def Dominates {n : ℕ} (a b : Fin n → ℝ) : Prop :=
  (∀ i, a i ≤ b i) ∧ ∃ i, a i < b i

/-- `x` is on the Pareto frontier of candidate set `U`: nothing in `U`
dominates it. -/
def IsFrontier {n : ℕ} (U : Finset (Fin n → ℝ)) (x : Fin n → ℝ) : Prop :=
  x ∈ U ∧ ∀ y ∈ U, ¬ Dominates y x

theorem not_dominates_self {n : ℕ} (a : Fin n → ℝ) : ¬ Dominates a a := by
  rintro ⟨-, i, hi⟩
  exact (lt_irrefl _ hi).elim

theorem dominates_trans {n : ℕ} {a b c : Fin n → ℝ}
    (hab : Dominates a b) (hbc : Dominates b c) : Dominates a c := by
  obtain ⟨hab_le, i, hi⟩ := hab
  obtain ⟨hbc_le, -⟩ := hbc
  exact ⟨fun j => (hab_le j).trans (hbc_le j), i, hi.trans_le (hbc_le i)⟩

theorem not_frontier_of_dominated {n : ℕ} {U : Finset (Fin n → ℝ)}
    {x y : Fin n → ℝ} (hy : y ∈ U) (h : Dominates y x) :
    ¬ IsFrontier U x := by
  rintro ⟨-, hfront⟩
  exact hfront y hy h

/-- Degenerate case, kept as a regression test for the definitions: with zero
scored dimensions every loss vector is in every envelope, vacuously. -/
theorem inEnvelope_zero_dim (e : Envelope 0) (x : Fin 0 → ℝ) :
    InEnvelope e x :=
  fun i => i.elim0

end Analog.Semantics
