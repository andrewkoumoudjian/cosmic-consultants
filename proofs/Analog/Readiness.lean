/-
S6 (ARL semantics) STATEMENT module (work order W8, issue #16; ADR-0002 D2 + D5).

This file contains DEFINITIONS and PROPOSITIONS ONLY. Nothing here is proved,
and a `def … : Prop` elaborating is not evidence for it. Work order W9 (#17)
must produce theorems of exactly the `S6…` Props below, in a separate module,
or this file must be superseded by a new statement ID. Never edit it silently
after owner freeze.

Plain-English reading guide (for the owner review):
- A gate outcome is `pass`, `fail` or `unknown`. Only `pass` counts.
- Gates 1–4 are checked per required dimension (trait): 1 observed, 2 within
  tolerance, 3 corroborated, 4 field-characterized. Gates 5–6 are checked once
  per site: 5 operable, 6 campaign-proven.
- A per-dimension gate passes only if the objective has at least one required
  dimension AND every required dimension passes it. So an objective with zero
  required dimensions gets ARL 0. It can't silently reach a high level.
- `arl o e` is the largest `k ≤ 6` such that gates 1..k all pass ("cumulative",
  like TRL). If gate 1 fails, ARL is 0.
- `dimLevel e d` is one dimension's own level (largest `k ≤ 4` with its gates
  1..k passing). S6a says the per-dimension part of ARL is the minimum of these:
  the weakest dimension sets the level.
- The not-testable-on-Earth list (`PermanentMismatch`: gravity, pressure regime,
  radiation) is published next to the level but never changes it (S6f).
- Objectives marked not rateable get no level at all (S6g).

Degenerate cases written down on purpose (issue #16): zero required dimensions
(S6z), every outcome unknown (S6u), and a site gate passing while a
per-dimension gate fails (S6h). S6a needs a nonempty required set to state a
minimum. For the empty set, the cumulative definition gives 0 (S6z). These
agree, so the kill criterion of #16 is not triggered.

What is NOT claimed: that any gate outcome is correct about the real world
(that's the data and literature, ADR-0002 "honest limits"), that the engine
computes `arl` this way (a conformance check, separate), anything about
`limitingDimension` / `limitingGate` contract fields (not stated here), or any
ranking within a level (that is the S2-atlas frontier, not ARL).
-/
import Analog.Semantics

open Finset

namespace Analog.Readiness

open Analog.Semantics

/-- Outcome of one gate check. Missing data is `unknown`, never `fail`, and
only `pass` ever counts toward a level. -/
inductive Outcome
  | unknown
  | fail
  | pass
  deriving DecidableEq, Repr

/-- Gates checked per required dimension (ADR-0002 D2, gates 1–4). -/
inductive DimGate
  | observed
  | withinTolerance
  | corroborated
  | fieldCharacterized
  deriving DecidableEq, Repr

/-- Gates checked once per site (ADR-0002 D2, gates 5–6). -/
inductive SiteGate
  | operable
  | campaignProven
  deriving DecidableEq, Repr

/-- Ladder position of a per-dimension gate. -/
def DimGate.level : DimGate → ℕ
  | .observed => 1
  | .withinTolerance => 2
  | .corroborated => 3
  | .fieldCharacterized => 4

/-- A mission objective (ADR-0002 D1), reduced to what the ladder reads:
the required scored dimensions, the not-testable-on-Earth list and whether it
is rateable at all. `δ` is the scored-dimension type (the contract enum). -/
structure Objective (δ : Type*) where
  required : Finset δ
  notTestable : Finset PermanentMismatch
  rateable : Bool

/-- Gate outcomes for one (cell or site, objective) pair. -/
structure Evidence (δ : Type*) where
  dim : δ → DimGate → Outcome
  site : SiteGate → Outcome

variable {δ : Type*}

/-- A per-dimension gate passes: at least one required dimension, and every
required dimension has outcome `pass`. -/
def dimPass (o : Objective δ) (e : Evidence δ) (g : DimGate) : Bool :=
  decide o.required.Nonempty && decide (∀ d ∈ o.required, e.dim d g = .pass)

/-- A site gate passes: its outcome is `pass`. -/
def sitePass (e : Evidence δ) (g : SiteGate) : Bool :=
  decide (e.site g = .pass)

/-- Gate `k` of the ladder, for `k = 1 … 6`. Any other index never passes. -/
def gatePass (o : Objective δ) (e : Evidence δ) : ℕ → Bool
  | 1 => dimPass o e .observed
  | 2 => dimPass o e .withinTolerance
  | 3 => dimPass o e .corroborated
  | 4 => dimPass o e .fieldCharacterized
  | 5 => sitePass e .operable
  | 6 => sitePass e .campaignProven
  | _ => false

/-- Gates `1 … k` all pass (vacuous for `k = 0`). -/
def GatesUpTo (o : Objective δ) (e : Evidence δ) (k : ℕ) : Prop :=
  ∀ j ∈ Finset.Icc 1 k, gatePass o e j = true

instance (o : Objective δ) (e : Evidence δ) : DecidablePred (GatesUpTo o e) :=
  fun k => by unfold GatesUpTo; infer_instance

/-- **ARL** (ADR-0002 D2): the largest `k ≤ 6` with gates `1 … k` all passing. -/
def arl (o : Objective δ) (e : Evidence δ) : ℕ :=
  Nat.findGreatest (GatesUpTo o e) 6

/-- Level `k` of one dimension's own ladder, for `k = 1 … 4`. -/
def dimGatePass (e : Evidence δ) (d : δ) : ℕ → Bool
  | 1 => decide (e.dim d .observed = .pass)
  | 2 => decide (e.dim d .withinTolerance = .pass)
  | 3 => decide (e.dim d .corroborated = .pass)
  | 4 => decide (e.dim d .fieldCharacterized = .pass)
  | _ => false

/-- One dimension's own gates `1 … k` all pass. -/
def DimUpTo (e : Evidence δ) (d : δ) (k : ℕ) : Prop :=
  ∀ j ∈ Finset.Icc 1 k, dimGatePass e d j = true

instance (e : Evidence δ) (d : δ) : DecidablePred (DimUpTo e d) :=
  fun k => by unfold DimUpTo; infer_instance

/-- One dimension's level: the largest `k ≤ 4` with its gates `1 … k` passing. -/
def dimLevel (e : Evidence δ) (d : δ) : ℕ :=
  Nat.findGreatest (DimUpTo e d) 4

/-- Published rating: a level only for rateable objectives (ADR-0002 D1). -/
def rating (o : Objective δ) (e : Evidence δ) : Option ℕ :=
  if o.rateable then some (arl o e) else none

/-! ## S6 propositions (frozen on owner approval) -/

/-- **S6a weakest link.** With at least one required dimension, the
per-dimension part of ARL (capped at 4) is the minimum of the dimensions' own
levels. -/
def S6a_weakest_link : Prop :=
  ∀ (o : Objective δ) (e : Evidence δ) (h : o.required.Nonempty),
    min (arl o e) 4 = o.required.inf' h (dimLevel e)

/-- **S6b monotone in evidence (gate form, ADR wording).** If `e'` passes
every gate `e` passes, `e'`'s level is at least `e`'s. -/
def S6b_monotone : Prop :=
  ∀ (o : Objective δ) (e e' : Evidence δ),
    (∀ k, gatePass o e k = true → gatePass o e' k = true) →
      arl o e ≤ arl o e'

/-- **S6b′ monotone in evidence (outcome form).** Turning outcomes into
`pass`, and never a `pass` into anything else, never lowers the level. -/
def S6b_monotone_outcomes : Prop :=
  ∀ (o : Objective δ) (e e' : Evidence δ),
    (∀ d g, e.dim d g = .pass → e'.dim d g = .pass) →
    (∀ g, e.site g = .pass → e'.site g = .pass) →
      arl o e ≤ arl o e'

/-- **S6c no compensation.** Changing only dimension `d₀`'s outcomes (site
outcomes may change too) cannot lift the per-dimension part of ARL above the
level of any other required dimension. -/
def S6c_no_compensation : Prop :=
  ∀ (o : Objective δ) (e e' : Evidence δ) (d₀ : δ),
    (∀ d, d ≠ d₀ → e'.dim d = e.dim d) →
      ∀ d ∈ o.required, d ≠ d₀ → min (arl o e') 4 ≤ dimLevel e d

/-- **S6h site gates can't lift a weak dimension.** If a required dimension
has not reached level 4 on its own, ARL is at most that dimension's level,
whatever the site gates say. -/
def S6h_site_no_lift : Prop :=
  ∀ (o : Objective δ) (e : Evidence δ),
    ∀ d ∈ o.required, dimLevel e d < 4 → arl o e ≤ dimLevel e d

/-- **S6d unknown ≠ failure (part 1).** A required dimension that is not
observed (outcome `unknown` or `fail` at gate 1) gives ARL 0. -/
def S6d_unobserved_zero : Prop :=
  ∀ (o : Objective δ) (e : Evidence δ),
    (∃ d ∈ o.required, e.dim d .observed ≠ .pass) → arl o e = 0

/-- **S6d unknown ≠ failure (part 2).** Every required dimension observed, but
one observed out of tolerance (`fail` at gate 2), gives ARL exactly 1. -/
def S6d_observed_fail_one : Prop :=
  ∀ (o : Objective δ) (e : Evidence δ),
    o.required.Nonempty →
    (∀ d ∈ o.required, e.dim d .observed = .pass) →
    (∃ d ∈ o.required, e.dim d .withinTolerance = .fail) →
      arl o e = 1

/-- **S6d′ only `pass` counts.** A required dimension without `pass` at a
per-dimension gate keeps ARL strictly below that gate. -/
def S6d_nonpass_blocks : Prop :=
  ∀ (o : Objective δ) (e : Evidence δ) (g : DimGate),
    ∀ d ∈ o.required, e.dim d g ≠ .pass → arl o e < g.level

/-- **S6e cumulative.** Every gate up to the level passes. -/
def S6e_cumulative : Prop :=
  ∀ (o : Objective δ) (e : Evidence δ) (k : ℕ),
    k ≤ arl o e → ∀ j ∈ Finset.Icc 1 k, gatePass o e j = true

/-- **S6e′ maximal.** The level is at most 6, and below 6 the next gate does
not pass. With S6e this pins `arl` down exactly. -/
def S6e_maximal : Prop :=
  ∀ (o : Objective δ) (e : Evidence δ),
    arl o e ≤ 6 ∧ (arl o e < 6 → gatePass o e (arl o e + 1) = false)

/-- **S6f mismatch never rated (part 1).** The not-testable list and the
rateable flag never change the level: only the required set matters. -/
def S6f_mismatch_irrelevant : Prop :=
  ∀ (o o' : Objective δ) (e : Evidence δ),
    o.required = o'.required → arl o e = arl o' e

/-- **S6f scored dimensions only (part 2).** Outcomes on dimensions the
objective doesn't require never change the level. -/
def S6f_required_only : Prop :=
  ∀ (o : Objective δ) (e e' : Evidence δ),
    (∀ d ∈ o.required, e'.dim d = e.dim d) → e'.site = e.site →
      arl o e' = arl o e

/-- **S6g not rateable, no level.** -/
def S6g_not_rateable : Prop :=
  ∀ (o : Objective δ) (e : Evidence δ), o.rateable = false → rating o e = none

/-- **S6z degenerate: no required dimensions.** ARL is 0. -/
def S6z_empty_required : Prop :=
  ∀ (o : Objective δ) (e : Evidence δ), o.required = ∅ → arl o e = 0

/-- **S6u degenerate: everything unknown.** If every per-dimension outcome is
`unknown`, ARL is 0, whatever the site gates say. -/
def S6u_all_unknown : Prop :=
  ∀ (o : Objective δ) (e : Evidence δ),
    (∀ d g, e.dim d g = .unknown) → arl o e = 0

end Analog.Readiness
