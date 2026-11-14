/-
S7 (funnel and verdict semantics) STATEMENT module (work order W21, issue #80;
ADR-0005, MISSION-PLANNER.md "Lean first", contracts from W20 #78 / PR #79).

This file contains DEFINITIONS and PROPOSITIONS ONLY. Nothing here is proved,
and a `def … : Prop` elaborating is not evidence for it. A follow-up module
`FunnelProofs.lean` must produce theorems of exactly the `S7…` Props below, or
this file must be superseded by a new statement ID. Never edit it silently
after owner freeze.

Plain-English reading guide (for the owner review):
- A requirement is a band on one Earth column: `lo ≤ value ≤ hi`, or
  `value < hi` when the source says "< hi" (`hiStrict`). No band = unknown.
- One value against one band gives a verdict: `matched` (known and inside),
  `missed` (known and outside) or `unknown` (value or band missing). These are
  the contract's `match` / `miss` / `unknown` (`match` is a Lean keyword).
- Every trait is read per month. A yearly (L1) trait simply has the same value
  every month. Over the requested months, a trait is `missed` if any month
  misses; otherwise `unknown` if any month is unknown or no month was asked
  for; otherwise `matched` (contract site-plan `verdicts[].verdict`).
- A site **survives** when every MUST trait is `matched`. Nice traits are
  shown and never filter. The funnel class is `allMatch` exactly when the site
  survives; otherwise `someMiss` if a must trait misses, else
  `noMissSomeUnknown`.
- Hard limits (travel time, protected land, …) remove a site only when its
  value is known and over the limit. An unknown value never removes a site;
  the site plan flags it instead.

What is NOT claimed: that any band is scientifically right, that any Earth
value is right, that the engine computes these functions (a conformance check
against `golden-verdicts.json`, separate), anything about the Pareto shortlist
(that reuses S2/S4), or anything about floating-point rounding (Lean reals are
exact; the engine's comparisons need a numeric policy, STATEMENTS.md).
-/
import Mathlib

open Finset

namespace Analog.Funnel

/-- Contract verdicts `match` / `miss` / `unknown`. -/
inductive Verdict
  | matched
  | missed
  | unknown
  deriving DecidableEq, Repr

/-- Contract `funnelClass`. A class, not a score. -/
inductive FunnelClass
  | allMatch
  | someMiss
  | noMissSomeUnknown
  deriving DecidableEq, Repr

/-- An Earth-unit band (trait-map `band` + `hiStrict`). -/
structure Band where
  lo : ℝ
  hi : ℝ
  hiStrict : Bool

/-- `x` is inside the band: `lo ≤ x` and `x ≤ hi` (or `x < hi` if strict). -/
def Band.Contains (b : Band) (x : ℝ) : Prop :=
  b.lo ≤ x ∧ (if b.hiStrict then x < b.hi else x ≤ b.hi)

/-- Band `b` lies inside band `b'`: everything `b` accepts, `b'` accepts. -/
def Band.Within (b b' : Band) : Prop :=
  ∀ x, b.Contains x → b'.Contains x

/-- `b'` is at least as strict as `b`: dropping a band (to unknown) is
stricter than anything; a band never replaces "no band"; otherwise `b'` lies
inside `b`. -/
def Tighter : Option Band → Option Band → Prop
  | none, _ => True
  | some _, none => False
  | some x, some y => x.Within y

open Classical in
/-- One value against one band. Missing value or missing band is `unknown`. -/
noncomputable def verdict : Option Band → Option ℝ → Verdict
  | some b, some x => if b.Contains x then .matched else .missed
  | _, _ => .unknown

open Classical in
/-- Verdict over a window of months: any miss → `missed`; else an empty
window or any unknown → `unknown`; else `matched`. -/
noncomputable def windowVerdict {μ : Type*} (months : Finset μ) (vm : μ → Verdict) : Verdict :=
  if ∃ m ∈ months, vm m = .missed then .missed
  else if months = ∅ ∨ ∃ m ∈ months, vm m = .unknown then .unknown
  else .matched

/-- What the request fixes for the verdicts: must traits, one band per trait
(trait map, or the user's edit), and the requested months. -/
structure Plan (δ μ : Type*) where
  must : Finset δ
  band : δ → Option Band
  months : Finset μ

variable {δ μ σ : Type*}

/-- A trait's verdict at a site: per-month verdicts, then the window rule.
`val s d m` is site `s`'s value of trait `d` in month `m` (`none` = missing). -/
noncomputable def traitVerdict (p : Plan δ μ) (val : σ → δ → μ → Option ℝ) (s : σ) (d : δ) : Verdict :=
  windowVerdict p.months (fun m => verdict (p.band d) (val s d m))

/-- A site survives: every must trait is `matched`. -/
def Survives (p : Plan δ μ) (val : σ → δ → μ → Option ℝ) (s : σ) : Prop :=
  ∀ d ∈ p.must, traitVerdict p val s d = .matched

open Classical in
/-- The surviving sites among `cells` (the funnel's last stage). -/
noncomputable def survivors (p : Plan δ μ) (val : σ → δ → μ → Option ℝ) (cells : Finset σ) : Finset σ :=
  cells.filter (Survives p val)

open Classical in
/-- Contract `funnelClass`, over the must traits only. -/
noncomputable def funnelClass (p : Plan δ μ) (val : σ → δ → μ → Option ℝ) (s : σ) : FunnelClass :=
  if ∃ d ∈ p.must, traitVerdict p val s d = .missed then .someMiss
  else if ∃ d ∈ p.must, traitVerdict p val s d = .unknown then .noMissSomeUnknown
  else .allMatch

/-- Hard limits: `lim` gives the limits in force, `cap l` its maximum,
`lval s l` the site's value (`none` = unknown). A site is removed only by a
known value over the cap. -/
def PassesLimits {ι : Type*} (lim : Finset ι) (cap : ι → ℝ) (lval : σ → ι → Option ℝ) (s : σ) : Prop :=
  ∀ l ∈ lim, ∀ x, lval s l = some x → x ≤ cap l

/-! ## S7 propositions (frozen on owner approval) -/

/-- **S7a match means known and inside.** A verdict is `matched` exactly when
both the band and the value are known and the value is inside the band. -/
def S7a_match_iff : Prop :=
  ∀ (b : Option Band) (v : Option ℝ),
    verdict b v = .matched ↔ ∃ b' x, b = some b' ∧ v = some x ∧ b'.Contains x

/-- **S7b unknown never counts as match.** If a site survives, every must
trait has a band and a known value in every requested month. -/
def S7b_unknown_not_match : Prop :=
  ∀ (p : Plan δ μ) (val : σ → δ → μ → Option ℝ) (s : σ),
    Survives p val s → ∀ d ∈ p.must, p.band d ≠ none ∧ ∀ m ∈ p.months, val s d m ≠ none

/-- **S7c tightening a band never adds a site.** Same must traits and months,
every band at least as strict: the survivors can only shrink. -/
def S7c_tighten_band : Prop :=
  ∀ (p p' : Plan δ μ) (val : σ → δ → μ → Option ℝ) (cells : Finset σ),
    p'.must = p.must → p'.months = p.months → (∀ d, Tighter (p'.band d) (p.band d)) →
      survivors p' val cells ⊆ survivors p val cells

/-- **S7d adding a must requirement never adds a site.** -/
def S7d_add_must : Prop :=
  ∀ (p p' : Plan δ μ) (val : σ → δ → μ → Option ℝ) (cells : Finset σ),
    p.must ⊆ p'.must → p'.band = p.band → p'.months = p.months →
      survivors p' val cells ⊆ survivors p val cells

/-- **S7e window matched.** The window verdict is `matched` exactly when at
least one month was asked for and every requested month is `matched`. -/
def S7e_window_matched : Prop :=
  ∀ (months : Finset μ) (vm : μ → Verdict),
    windowVerdict months vm = .matched ↔ months.Nonempty ∧ ∀ m ∈ months, vm m = .matched

/-- **S7e′ window missed.** The window verdict is `missed` exactly when some
requested month misses. -/
def S7e_window_missed : Prop :=
  ∀ (months : Finset μ) (vm : μ → Verdict),
    windowVerdict months vm = .missed ↔ ∃ m ∈ months, vm m = .missed

/-- **S7f funnel class agrees with survival.** -/
def S7f_class_allMatch_iff : Prop :=
  ∀ (p : Plan δ μ) (val : σ → δ → μ → Option ℝ) (s : σ),
    funnelClass p val s = .allMatch ↔ Survives p val s

/-- **S7g nice traits never filter.** Changing the band of a trait that is
not a must requirement never changes whether a site survives. -/
def S7g_nice_never_filters : Prop :=
  ∀ (p p' : Plan δ μ) (val : σ → δ → μ → Option ℝ) (s : σ),
    p'.must = p.must → p'.months = p.months → (∀ d ∈ p.must, p'.band d = p.band d) →
      (Survives p' val s ↔ Survives p val s)

/-- **S7h a longer trip never finds more sites.** Adding months to a non-empty
window can only shrink the survivors. -/
def S7h_more_months : Prop :=
  ∀ (p p' : Plan δ μ) (val : σ → δ → μ → Option ℝ) (cells : Finset σ),
    p.months.Nonempty → p.months ⊆ p'.months → p'.must = p.must → p'.band = p.band →
      survivors p' val cells ⊆ survivors p val cells

/-- **S7i unknown limit values never remove a site.** Turning some of a
site's limit values into unknown never makes it fail the limits. -/
def S7i_unknown_limit_kept {ι : Type*} : Prop :=
  ∀ (lim : Finset ι) (cap : ι → ℝ) (lval lval' : σ → ι → Option ℝ) (s : σ),
    (∀ l ∈ lim, lval' s l = lval s l ∨ lval' s l = none) →
      PassesLimits lim cap lval s → PassesLimits lim cap lval' s

/-- **S7z degenerate: no months asked for.** Every trait is `unknown`, so no
site with a must requirement survives. -/
def S7z_empty_window : Prop :=
  ∀ (p : Plan δ μ) (val : σ → δ → μ → Option ℝ) (s : σ),
    p.months = ∅ → p.must.Nonempty → ¬ Survives p val s

end Analog.Funnel
