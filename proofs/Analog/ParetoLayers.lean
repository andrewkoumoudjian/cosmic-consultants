/-
S9 (Pareto layer peeling and non-scalar multi-objective partial order)
STATEMENT module (work order W22, issue #170; ADR-0001, ADR-0005 D3, AGENTS.md rule 4).

This file contains DEFINITIONS and PROPOSITIONS ONLY. No proofs live here;
`ParetoLayersProofs.lean` proves every `S9...` Prop below.
-/
import Mathlib
import Analog.Semantics
import Analog.Atlas

open Finset

namespace Analog.ParetoLayers

open Analog.Semantics Analog.Atlas

section

open Classical

/-- Eligible comparable subset of `U`: sites where every scored dimension is
observed (`some _`). A site with any `none` observation is excluded rather
than assigned a fabricated zero gap. -/
noncomputable def comparableSites {σ : Type*} {n : ℕ}
    (U : Finset σ) (obs : σ → Fin n → Option ℝ) : Finset σ :=
  U.filter (fun s => ∀ i : Fin n, (obs s i).isSome)

/-- Pareto frontier of finite set `S` under loss map `loss`: members of `S`
not strictly dominated by any member of `S`. -/
noncomputable def frontier {σ : Type*} {n : ℕ}
    (S : Finset σ) (loss : σ → Fin n → ℝ) : Finset σ :=
  S.filter (fun x => ∀ y ∈ S, ¬ Dominates (loss y) (loss x))

/-- Remaining unpeeled candidates after peeling `k` Pareto layers. -/
noncomputable def peelRem {σ : Type*} {n : ℕ}
    (S : Finset σ) (loss : σ → Fin n → ℝ) : ℕ → Finset σ
  | 0 => S
  | k + 1 => peelRem S loss k \ frontier (peelRem S loss k) loss

/-- 0-indexed Pareto layer `k` (`k = 0` corresponds to layer 1 in the contract/engine). -/
noncomputable def peelLayer {σ : Type*} {n : ℕ}
    (S : Finset σ) (loss : σ → Fin n → ℝ) (k : ℕ) : Finset σ :=
  frontier (peelRem S loss k) loss

end

/-! ## S9 propositions -/

/-- **S9a (antichain property):** every Pareto layer is pairwise incomparable. -/
def S9a_layer_incomparable {σ : Type*} {n : ℕ} : Prop :=
  ∀ (S : Finset σ) (loss : σ → Fin n → ℝ) (k : ℕ) {x y : σ},
    x ∈ peelLayer S loss k → y ∈ peelLayer S loss k → ¬ Dominates (loss x) (loss y)

/-- **S9b (dominance separation):** if `y` strictly dominates `x`, then `y` sits
in a strictly earlier (lower-index) layer than `x`. -/
def S9b_dominates_strictly_later {σ : Type*} {n : ℕ} : Prop :=
  ∀ (S : Finset σ) (loss : σ → Fin n → ℝ) {kx ky : ℕ} {x y : σ},
    x ∈ peelLayer S loss kx → y ∈ peelLayer S loss ky →
      Dominates (loss y) (loss x) → ky < kx

/-- **S9c (tie preservation):** two sites with identical loss vectors always
receive the exact same Pareto layer index. -/
def S9c_equal_vectors_same_layer {σ : Type*} {n : ℕ} : Prop :=
  ∀ (S : Finset σ) (loss : σ → Fin n → ℝ) {kx ky : ℕ} {x y : σ},
    x ∈ peelLayer S loss kx → y ∈ peelLayer S loss ky →
      loss x = loss y → kx = ky

/-- **S9d (exhaustive partition):** every comparable site in `S` belongs to a
unique Pareto layer `k < S.card`. -/
def S9d_layer_partition {σ : Type*} {n : ℕ} : Prop :=
  ∀ (S : Finset σ) (loss : σ → Fin n → ℝ) {x : σ},
    x ∈ S → ∃! k, x ∈ peelLayer S loss k ∧ k < S.card

/-- **S9e (unknown exclusion):** a site missing any scored dimension is excluded
from `comparableSites` and enters no Pareto layer. -/
def S9e_unknown_excluded {σ : Type*} {n : ℕ} : Prop :=
  ∀ (U : Finset σ) (obs : σ → Fin n → Option ℝ) (loss : σ → Fin n → ℝ)
    {x : σ} (i : Fin n),
    obs x i = none → ∀ k, x ∉ peelLayer (comparableSites U obs) loss k

/-- **S9f (non-scalarity):** mutually incomparable trade-off vectors always share
layer 0 regardless of any arbitrary scalar scoring function `score`. -/
def S9f_tradeoff_never_separated {n : ℕ} : Prop :=
  ∀ (a b : Fin n → ℝ) (_score : (Fin n → ℝ) → ℝ),
    ¬ Dominates a b → ¬ Dominates b a →
      a ∈ peelLayer ({a, b} : Finset (Fin n → ℝ)) id 0 ∧
      b ∈ peelLayer ({a, b} : Finset (Fin n → ℝ)) id 0

/-- **S9g (DP equivalence):** 1-indexed peeled layer `k + 1` equals
`1 + max { layer(w) | w ∈ S, Dominates (loss w) (loss x) }`, matching the
bottom-up recurrence computed by `pareto_layers`. -/
def S9g_dp_recurrence {σ : Type*} {n : ℕ} : Prop :=
  ∀ (S : Finset σ) (loss : σ → Fin n → ℝ) {x : σ} {k : ℕ},
    x ∈ peelLayer S loss k →
      k + 1 = 1 +
        letI := Classical.propDecidable
        (S.filter (fun w => Dominates (loss w) (loss x))).sup
          (fun w => if h : ∃ m, w ∈ peelLayer S loss m then Classical.choose h + 1 else 0)

end Analog.ParetoLayers
