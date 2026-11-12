/- NOT IMPORTED by Analog.lean (2026-11-12): mechanical port fails on current Mathlib APIs; registered re-proof candidate in docs/research/06-lean-corpus-inventory.md. Preserved verbatim for the re-prover. -/
/-
PORTED 2026-11-12 from owner prior work: FWER experiment admission gate
Source: andrewkoumoudjian/perps-strategy @ 0f34759, lanes/chief/lean/PerpChief/ExperimentGate.lean (toolchain v4.15.0).
Port changes ONLY: module path/import remap to Analog.Prior.* (+ Mathlib API renames if listed in docs/research/06). Namespaces, statements, proofs otherwise verbatim. Original file is frozen upstream; do not edit semantics here.
-/
/-
PAPERWAVE2 ASSEMBLER A2 — EXPERIMENT-VALIDITY COMPOSITION.

A cell is admitted to a closed-list experiment only if three independent
certificates hold at once:

(i)   Ville/e-process.  Every cell carries a null-valid betting e-process
      (`Ville.BettingHyp`), so its capital process is a nonnegative
      supermartingale under the null (`Ville.capital_supermartingale`) and a
      uniform mixture over the `K` betting fractions is an anytime-valid test
      (`Selective.mix_ville`).
(ii)  Family-wise budget.  The cells are a closed list `Fin J`, declared before
      the run; the family-wise threshold is `J/α` on the average capital across
      the `K` fractions, so each cell's own level is `α/J`.  `Patterns.search_fwer`
      unions the cell-level events over every true null, whatever the other
      cells do.
(iii) Information ceiling.  Every admitted cell's binary state has Hellinger
      affinity at least `ρ` (`BinaryInfo.bc`).  `BinaryInfo.bc_push_ge` says no
      deterministic summary can lower the affinity, `BinaryInfo.tv_push_le`
      caps the summary's total variation by `√(1 − bc²)`, and the equal-prior
      accuracy of any decoder through the summary is at most `(1 + √(1 − ρ²))/2`.

`Gate` is that combined predicate.  `gate_fwer` and `gate_accuracy` are its two
validity projections; `gate_sound` states them together.  `gate_cell_fwer`
exhibits the cell-level `α/J` component that `Patterns.search_fwer` unions.

Nothing here asserts that any market state has an edge, that any cell will be
rejected, or that any strategy is profitable.  "Proved" means Lean-clean, never
profitable.  No statistics, market data, orders, or Vest returns are touched.
-/
import Analog.Prior.Patterns
import Analog.Prior.BinaryInfo
import Analog.Prior.TheoryModels1

open MeasureTheory Filter Finset
open scoped ENNReal

namespace PerpChief.ExperimentGate

noncomputable section

variable {Ω : Type*} {m0 : MeasurableSpace Ω} {μ : Measure Ω} [IsProbabilityMeasure μ]
  {ℱ : Filtration ℕ m0}

/-! ### The experiment-admission predicate -/

/-- A closed-cell experiment gate.  Fields are grouped exactly as the three
certificates above:

* `J`, `K`, `hJ`, `hK`, `α`, `hα`, `closed`, `lams`, `X`, `B`, `U`, `L`, `valid`
  are the e-process side: a closed list of `J` cells, each a mixture over `K`
  fixed betting fractions, with the null-valid betting test `valid`;
* the threshold and its budget are `Gate.threshold = J/α` and `Gate.cellLevel = α/J`;
* `ρ`, `hρ0`, `hρ1`, `p`, `q`, `f`, `p_nonneg`, `q_nonneg`, `p_sum`, `q_sum`,
  `affinity` are the information side: the two conditional masses of the cell's
  binary state, the declared summariser, and the affinity floor `ρ`.

`closed` is the list declared before the run; no cell outside it is admitted. -/
structure Gate (ℱ : Filtration ℕ m0) (μ : Measure Ω) (ι : Type*) [Fintype ι]
    [DecidableEq ι] where
  J : ℕ
  K : ℕ
  hJ : 0 < J
  hK : 0 < K
  α : ℝ
  hα : 0 < α
  closed : Finset (Fin J)
  lams : Fin K → ℝ
  X : Fin J → ℕ → Ω → ℝ
  B : ℝ
  U : ℝ
  L : ℝ
  valid : ∀ j ∈ closed, ∀ k,
    PerpChief.Ville.BettingHyp ℱ μ (fun _ _ => lams k) (X j) 0 B U L
  ρ : ℝ
  hρ0 : 0 ≤ ρ
  hρ1 : ρ ≤ 1
  p : Fin J → ι → ℝ
  q : Fin J → ι → ℝ
  f : Fin J → ι → Bool
  p_nonneg : ∀ j i, 0 ≤ p j i
  q_nonneg : ∀ j i, 0 ≤ q j i
  p_sum : ∀ j, ∑ i, p j i = 1
  q_sum : ∀ j, ∑ i, q j i = 1
  affinity : ∀ j ∈ closed, ρ ≤ PerpChief.BinaryInfo.bc (p j) (q j)

variable {ι : Type*} [Fintype ι] [DecidableEq ι]

namespace Gate

/-- The family-wise threshold `J/α` on the `K`-bet average capital. -/
def threshold (G : Gate ℱ μ ι) : ℝ := (G.J : ℝ) / G.α

/-- The per-cell level `α/J`.  `one_div_cellLevel` shows its reciprocal is the
family-wise threshold. -/
def cellLevel (G : Gate ℱ μ ι) : ℝ := G.α / G.J

/-- Cell `j` is rejected by horizon `N` on path `ω` when its average capital
across the `K` betting fractions reaches the family-wise threshold. -/
def rejects (G : Gate ℱ μ ι) (N : ℕ) (j : Fin G.J) (ω : Ω) : Prop :=
  ∃ n ≤ N, G.threshold ≤
    (∑ k, PerpChief.Ville.capital (fun _ _ => G.lams k) (G.X j) 0 n ω) / G.K

omit [IsProbabilityMeasure μ] in
/-- The threshold is the literal ratio `J/α`. -/
theorem threshold_eq (G : Gate ℱ μ ι) : G.threshold = (G.J : ℝ) / G.α := rfl

omit [IsProbabilityMeasure μ] in
/-- The per-cell level is the literal ratio `α/J`. -/
theorem cellLevel_eq (G : Gate ℱ μ ι) : G.cellLevel = G.α / G.J := rfl

omit [IsProbabilityMeasure μ] in
/-- The cell-level reciprocal is the family-wise threshold: the two arithmetic
faces of the same budget. -/
theorem one_div_cellLevel (G : Gate ℱ μ ι) : 1 / G.cellLevel = G.threshold := by
  have hα : G.α ≠ 0 := G.hα.ne'
  have hJ : (G.J : ℝ) ≠ 0 := by exact_mod_cast G.hJ.ne'
  unfold cellLevel threshold
  field_simp

end Gate

/-! ### (i)+(ii) The family-wise e-process bound -/

/-- The per-cell component: an admitted cell's own rejection event at the
family-wise threshold has probability at most `α/J`.  This is
`Selective.mix_ville` instantiated at the cell level; `search_fwer` unions it. -/
theorem gate_cell_fwer (G : Gate ℱ μ ι) (j : Fin G.J) (hj : j ∈ G.closed) (N : ℕ) :
    μ {ω | G.rejects N j ω} ≤ ENNReal.ofReal (G.α / G.J) := by
  have hJ : (0 : ℝ) < (G.J : ℝ) := by exact_mod_cast G.hJ
  have hα' : 0 < G.α / G.J := div_pos G.hα hJ
  have hm := PerpChief.Selective.mix_ville (K := G.K) G.hK
    (X := G.X j) (lams := G.lams) (fun k => G.valid j hj k) hα' N
  have he : 1 / (G.α / G.J) = G.threshold := by
    rw [← Gate.one_div_cellLevel]
    rfl
  unfold Gate.rejects
  rw [he] at hm
  exact hm

/-- The family-wise bound: if every admitted cell's e-process is null-valid and
the closed list meets the `J/α` budget, the probability that any admitted cell
reaches the threshold by horizon `N` is at most `α`.  Exact citation:
`Patterns.search_fwer` with the gate's `closed` list as its null set. -/
theorem gate_fwer (G : Gate ℱ μ ι) (N : ℕ) :
    μ {ω | ∃ j ∈ G.closed, G.rejects N j ω} ≤ ENNReal.ofReal G.α := by
  unfold Gate.rejects Gate.threshold
  exact PerpChief.Patterns.search_fwer (J := G.J) (K := G.K) (hJ := G.hJ) (hK := G.hK)
    (lams := G.lams) (X := G.X) (B := G.B) (U := G.U) (L := G.L) (N0 := G.closed)
    (h := G.valid) (α := G.α) (hα := G.hα) (N := N)

/-- Restricting a pre-registered closed list to a sub-list cannot inflate the
family-wise error: the same `α` bound holds for every `S ⊆ closed`.  This is
`Patterns.search_fwer` re-applied to `S`; it is the formal content of "the list
is closed before the run". -/
theorem gate_fwer_subfamily (G : Gate ℱ μ ι) (S : Finset (Fin G.J))
    (hS : S ⊆ G.closed) (N : ℕ) :
    μ {ω | ∃ j ∈ S, G.rejects N j ω} ≤ ENNReal.ofReal G.α := by
  unfold Gate.rejects Gate.threshold
  exact PerpChief.Patterns.search_fwer (J := G.J) (K := G.K) (hJ := G.hJ) (hK := G.hK)
    (lams := G.lams) (X := G.X) (B := G.B) (U := G.U) (L := G.L) (N0 := S)
    (h := fun j hj k => G.valid j (hS hj) k) (α := G.α) (hα := G.hα) (N := N)

/-! ### (iii) The binary-state information ceiling -/

/-- Equal-prior accuracy of the decision rule "state 1 on `A`, state 0 off `A`",
where `pp` and `qq` are the two state-conditional masses. -/
def accuracy {κ : Type*} [Fintype κ] [DecidableEq κ] (pp qq : κ → ℝ) (A : Finset κ) : ℝ :=
  ((∑ k ∈ A, qq k) + (∑ k ∈ Aᶜ, pp k)) / 2

/-- The accuracy ceiling at affinity floor `ρ`: `(1 + √(1 − ρ²))/2`. -/
def infoCap (ρ : ℝ) : ℝ := (1 + Real.sqrt (1 - ρ ^ 2)) / 2

/-- Total variation dominates the gap between the two hypotheses on any event.
This is the Bayes step: `tv` is the supremum of `|p(A) − q(A)|` over events. -/
private lemma abs_sum_sub_le_tv {κ : Type*} [Fintype κ] [DecidableEq κ] (pp qq : κ → ℝ)
    (hsum : ∑ k, qq k = ∑ k, pp k) (A : Finset κ) :
    |∑ k ∈ A, (qq k - pp k)| ≤ PerpChief.BinaryInfo.tv pp qq := by
  have hzero : ∑ k, (qq k - pp k) = 0 := by
    rw [Finset.sum_sub_distrib, hsum, sub_self]
  have hsplit : ∑ k ∈ A, (qq k - pp k) + ∑ k ∈ Aᶜ, (qq k - pp k) = 0 := by
    rw [Finset.sum_add_sum_compl]
    exact hzero
  have hneg : ∑ k ∈ Aᶜ, (qq k - pp k) = -(∑ k ∈ A, (qq k - pp k)) := by linarith
  have hA : |∑ k ∈ A, (qq k - pp k)| ≤ ∑ k ∈ A, |qq k - pp k| :=
    Finset.abs_sum_le_sum_abs _ _
  have hAc : |∑ k ∈ A, (qq k - pp k)| ≤ ∑ k ∈ Aᶜ, |qq k - pp k| := by
    have h1 : |∑ k ∈ A, (qq k - pp k)| = |∑ k ∈ Aᶜ, (qq k - pp k)| := by
      rw [hneg, abs_neg]
    rw [h1]
    exact Finset.abs_sum_le_sum_abs _ _
  have htot : ∑ k ∈ A, |qq k - pp k| + ∑ k ∈ Aᶜ, |qq k - pp k|
      = ∑ k, |qq k - pp k| := Finset.sum_add_sum_compl A _
  have hcomm : (∑ i : κ, |pp i - qq i|) = ∑ i, |qq i - pp i| :=
    Finset.sum_congr rfl (fun i _ => abs_sub_comm (pp i) (qq i))
  unfold PerpChief.BinaryInfo.tv
  rw [hcomm, ← htot]
  linarith

/-- No decision rule on two probability masses can beat the total-variation
ceiling `(1 + tv)/2` under equal priors. -/
theorem accuracy_le_tv {κ : Type*} [Fintype κ] [DecidableEq κ] (pp qq : κ → ℝ)
    (A : Finset κ) (hp1 : ∑ k, pp k = 1) (hq1 : ∑ k, qq k = 1) :
    accuracy pp qq A ≤ (1 + PerpChief.BinaryInfo.tv pp qq) / 2 := by
  unfold accuracy
  have hsplit : ∑ k ∈ Aᶜ, pp k = 1 - ∑ k ∈ A, pp k := by
    have h := Finset.sum_add_sum_compl A pp
    linarith
  have hsub : ∑ k ∈ A, qq k - ∑ k ∈ A, pp k = ∑ k ∈ A, (qq k - pp k) := by
    rw [Finset.sum_sub_distrib]
  have hb := abs_sum_sub_le_tv pp qq (by rw [hq1, hp1]) A
  have hle : ∑ k ∈ A, qq k - ∑ k ∈ A, pp k ≤ PerpChief.BinaryInfo.tv pp qq := by
    calc ∑ k ∈ A, qq k - ∑ k ∈ A, pp k = ∑ k ∈ A, (qq k - pp k) := hsub
      _ ≤ |∑ k ∈ A, (qq k - pp k)| := le_abs_self _
      _ ≤ PerpChief.BinaryInfo.tv pp qq := hb
  rw [hsplit]
  linarith

private lemma push_nonneg {ι : Type*} [Fintype ι] [DecidableEq ι] (f : ι → Bool)
    (p : ι → ℝ) (hp : ∀ i, 0 ≤ p i) (k : Bool) :
    0 ≤ PerpChief.BinaryInfo.push f p k := by
  unfold PerpChief.BinaryInfo.push
  exact Finset.sum_nonneg (fun i _ => hp i)

private lemma push_sum {ι : Type*} [Fintype ι] [DecidableEq ι] (f : ι → Bool) (p : ι → ℝ) :
    ∑ k, PerpChief.BinaryInfo.push f p k = ∑ i, p i := by
  unfold PerpChief.BinaryInfo.push
  exact Finset.sum_fiberwise_of_maps_to (g := f) (fun i _ => Finset.mem_univ _) p

/-- The binary summary cannot raise the accuracy ceiling.  Even after any
deterministic summary `f`, the decoder's equal-prior accuracy is at most
`(1 + √(1 − bc²))/2`.  Citation: `BinaryInfo.tv_push_le` (Hellinger contraction
plus the TV bound), composed with `accuracy_le_tv`. -/
theorem accuracy_push_le {ι : Type*} [Fintype ι] [DecidableEq ι] (f : ι → Bool)
    (p q : ι → ℝ) (A : Finset Bool) (hp : ∀ i, 0 ≤ p i) (hq : ∀ i, 0 ≤ q i)
    (hp1 : ∑ i, p i = 1) (hq1 : ∑ i, q i = 1) :
    accuracy (PerpChief.BinaryInfo.push f p) (PerpChief.BinaryInfo.push f q) A ≤
      (1 + Real.sqrt (1 - PerpChief.BinaryInfo.bc p q ^ 2)) / 2 := by
  have hpsum : ∑ k, PerpChief.BinaryInfo.push f p k = 1 := by rw [push_sum, hp1]
  have hqsum : ∑ k, PerpChief.BinaryInfo.push f q k = 1 := by rw [push_sum, hq1]
  have h1 := accuracy_le_tv (PerpChief.BinaryInfo.push f p) (PerpChief.BinaryInfo.push f q)
    A hpsum hqsum
  have h2 := PerpChief.BinaryInfo.tv_push_le f p q hp hq hp1 hq1
  linarith

/-- The information ceiling: if the state's affinity is at least `ρ`, no decoder
through any deterministic binary summary exceeds `infoCap ρ`.  The affinity
floor is a *maximum-information* statement: large `ρ` means the two conditional
masses are hard to tell apart. -/
theorem accuracy_le_infoCap {ι : Type*} [Fintype ι] [DecidableEq ι] {ρ : ℝ}
    (hρ0 : 0 ≤ ρ) {p q : ι → ℝ}
    (hcap : ρ ≤ PerpChief.BinaryInfo.bc p q) (hp : ∀ i, 0 ≤ p i)
    (hq : ∀ i, 0 ≤ q i) (hp1 : ∑ i, p i = 1) (hq1 : ∑ i, q i = 1)
    (f : ι → Bool) (A : Finset Bool) :
    accuracy (PerpChief.BinaryInfo.push f p) (PerpChief.BinaryInfo.push f q) A ≤
      infoCap ρ := by
  have hbc0 := PerpChief.BinaryInfo.bc_nonneg p q
  have hbc1 := PerpChief.BinaryInfo.bc_le_one p q hp hq hp1 hq1
  have hsq : 1 - PerpChief.BinaryInfo.bc p q ^ 2 ≤ 1 - ρ ^ 2 := by
    nlinarith [hcap, hρ0, hbc0]
  have hs := Real.sqrt_le_sqrt hsq
  have hmain := accuracy_push_le f p q A hp hq hp1 hq1
  unfold infoCap
  linarith

/-- The sharp per-state form: accuracy through any deterministic binary summary
is at most `infoCap (bc p q)`, the ceiling evaluated at the state's own affinity.
`accuracy_le_infoCap` is the conservative form obtained by replacing `bc p q`
with a declared floor `ρ ≤ bc p q`. -/
theorem accuracy_le_infoCap_bc {ι : Type*} [Fintype ι] [DecidableEq ι] (f : ι → Bool)
    (p q : ι → ℝ) (A : Finset Bool) (hp : ∀ i, 0 ≤ p i) (hq : ∀ i, 0 ≤ q i)
    (hp1 : ∑ i, p i = 1) (hq1 : ∑ i, q i = 1) :
    accuracy (PerpChief.BinaryInfo.push f p) (PerpChief.BinaryInfo.push f q) A ≤
      infoCap (PerpChief.BinaryInfo.bc p q) := by
  have h := accuracy_push_le f p q A hp hq hp1 hq1
  unfold infoCap
  exact h

private lemma sum_bool_eq (f : Bool → ℝ) : ∑ k, f k = f true + f false := by
  have huniv : (Finset.univ : Finset Bool) = {true, false} := by decide
  rw [huniv, Finset.sum_pair (by decide)]

private lemma tv_bool_eq (pp qq : Bool → ℝ) (hpf : pp false = 1 - pp true)
    (hqf : qq false = 1 - qq true) :
    PerpChief.BinaryInfo.tv pp qq = |pp true - qq true| := by
  have hd : pp false - qq false = -(pp true - qq true) := by
    rw [hpf, hqf]
    ring
  unfold PerpChief.BinaryInfo.tv
  rw [sum_bool_eq (fun k => |pp k - qq k|), hd, abs_neg]
  ring

/-- The ceiling in the Bernoulli form used by `TheoryModels1`: for a binary
state, the equal-prior accuracy of any decoder is at most the balanced accuracy
of the two Bernoulli parameters.  Citations: `TheoryModels1.binary_tv` (Bernoulli
TV is `|p − q|`) and `TheoryModels1.binary_balanced_accuracy`
(`balancedAccuracy p q = (1 + |p − q|)/2`). -/
theorem accuracy_bool_le_balanced (pp qq : Bool → ℝ) (A : Finset Bool)
    (hp1 : ∑ k, pp k = 1) (hq1 : ∑ k, qq k = 1) :
    accuracy pp qq A ≤ PerpChief.TheoryModels1.balancedAccuracy (pp true) (qq true) := by
  have hpt : pp true + pp false = 1 := by
    rw [← sum_bool_eq pp]
    exact hp1
  have hqt : qq true + qq false = 1 := by
    rw [← sum_bool_eq qq]
    exact hq1
  have hpf : pp false = 1 - pp true := by linarith
  have hqf : qq false = 1 - qq true := by linarith
  have h1 := accuracy_le_tv pp qq A hp1 hq1
  have h2 := tv_bool_eq pp qq hpf hqf
  rw [h2] at h1
  rw [PerpChief.TheoryModels1.binary_balanced_accuracy]
  linarith

/-! ### The composed gate -/

omit [IsProbabilityMeasure μ] in
/-- An admitted cell's decoder is capped: if `j` is in the closed list, every
decoder through `j`'s binary summary is at most `infoCap ρ`. -/
theorem gate_accuracy (G : Gate ℱ μ ι) (j : Fin G.J) (hj : j ∈ G.closed)
    (A : Finset Bool) :
    accuracy (PerpChief.BinaryInfo.push (G.f j) (G.p j))
      (PerpChief.BinaryInfo.push (G.f j) (G.q j)) A ≤ infoCap G.ρ :=
  accuracy_le_infoCap G.hρ0 (G.affinity j hj) (G.p_nonneg j) (G.q_nonneg j)
    (G.p_sum j) (G.q_sum j) (G.f j) A

/-- The validity composition.  A gate simultaneously guarantees

(a) family-wise error at most `α` over its closed list, from the e-process
    certificates and `Patterns.search_fwer`; and
(b) no decoder on any admitted cell's binary summary exceeds `infoCap ρ`, from
    the affinity floor and `BinaryInfo.tv_push_le`.

The two conclusions share only the admitted cells; neither implies the other,
and neither asserts an edge. -/
theorem gate_sound (G : Gate ℱ μ ι) (N : ℕ) :
    (μ {ω | ∃ j ∈ G.closed, G.rejects N j ω} ≤ ENNReal.ofReal G.α) ∧
    (∀ (j : Fin G.J), j ∈ G.closed → ∀ A : Finset Bool,
      accuracy (PerpChief.BinaryInfo.push (G.f j) (G.p j))
        (PerpChief.BinaryInfo.push (G.f j) (G.q j)) A ≤ infoCap G.ρ) :=
  ⟨gate_fwer G N, fun j hj A => gate_accuracy G j hj A⟩

/-! ### Non-vacuity -/

/-- The ceiling never falls below chance and never exceeds one. -/
theorem infoCap_bounds {ρ : ℝ} (hρ0 : 0 ≤ ρ) (hρ1 : ρ ≤ 1) :
    1 / 2 ≤ infoCap ρ ∧ infoCap ρ ≤ 1 := by
  have h0 : 0 ≤ 1 - ρ ^ 2 := by nlinarith
  have h1 : 1 - ρ ^ 2 ≤ 1 := by nlinarith [sq_nonneg ρ]
  have hs0 : 0 ≤ Real.sqrt (1 - ρ ^ 2) := Real.sqrt_nonneg _
  have hs1 : Real.sqrt (1 - ρ ^ 2) ≤ 1 := by
    have h := Real.sqrt_le_sqrt h1
    simpa using h
  unfold infoCap
  constructor <;> linarith

/-- A fully uninformative binary state (`bc = 1`) admits no decoder above chance. -/
theorem infoCap_one : infoCap 1 = 1 / 2 := by
  unfold infoCap
  norm_num

/-- A perfectly separated state (`bc = 0`) allows accuracy up to one. -/
theorem infoCap_zero : infoCap 0 = 1 := by
  unfold infoCap
  norm_num

/-- The gate predicate is inhabited on every probability space: one cell, one
bet, the flat null statistic `X = 0`, and the uninformative binary state
`p = q = (1/2, 1/2)` with affinity `bc = 1`, whose accuracy ceiling is `1/2`. -/
theorem gate_inhabited : ∃ G : Gate ℱ μ Bool, G.J = 1 := by
  have hbc : PerpChief.BinaryInfo.bc (fun _ : Bool => (1 / 2 : ℝ)) (fun _ => 1 / 2) = 1 := by
    unfold PerpChief.BinaryInfo.bc
    rw [sum_bool_eq (fun k => Real.sqrt ((1 / 2 : ℝ) * (1 / 2)))]
    have h4 : Real.sqrt ((1 / 2 : ℝ) * (1 / 2)) = 1 / 2 := by
      rw [show (1 / 2 : ℝ) * (1 / 2) = (1 / 2) ^ 2 by norm_num]
      exact Real.sqrt_sq (by norm_num)
    rw [h4]
    norm_num
  let G : Gate ℱ μ Bool :=
    { J := 1
      K := 1
      hJ := by norm_num
      hK := by norm_num
      α := 1 / 2
      hα := by norm_num
      closed := Finset.univ
      lams := fun _ => 1 / 2
      X := fun _ _ _ => 0
      B := 1
      U := 1
      L := 1 / 2
      valid := fun j hj k => PerpChief.Ville.bettingHyp_inhabited
      ρ := 1
      hρ0 := by norm_num
      hρ1 := by norm_num
      p := fun _ _ => 1 / 2
      q := fun _ _ => 1 / 2
      f := fun _ _ => true
      p_nonneg := by intro j i; norm_num
      q_nonneg := by intro j i; norm_num
      p_sum := by
        intro j
        rw [sum_bool_eq (fun _ => (1 / 2 : ℝ))]
        norm_num
      q_sum := by
        intro j
        rw [sum_bool_eq (fun _ => (1 / 2 : ℝ))]
        norm_num
      affinity := by
        intro j hj
        show (1 : ℝ) ≤ PerpChief.BinaryInfo.bc (fun _ : Bool => (1 / 2 : ℝ)) (fun _ => 1 / 2)
        rw [hbc] }
  exact ⟨G, rfl⟩

end

end PerpChief.ExperimentGate
