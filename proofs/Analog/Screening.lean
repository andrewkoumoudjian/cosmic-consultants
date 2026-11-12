/-
Provenance: owner's prior work, `QUARCC-Umbrella/quant-fund`
(`fastopt/proofs/FastOpt/Screening.lean`), namespace adapted FastOpt → Analog
2026-11-12; theorem statements and proofs unchanged. In the atlas instantiation
the scenario set `U` is the Earth cell set and losses are per-dimension analog
losses (see `Analog.Semantics`); that instantiation is work-order S2 and is not
claimed by the generic theorems below.

Exact tail-scenario screening (fastopt.models.Portfolio._solve_screened).

The solver optimises a CVaR / worst-realisation model on a subset `S` of the
scenarios `U`.  Dropping scenarios only removes nonnegative terms, so the
restricted objective is a lower model of the full one; at the restricted
minimiser the dropped terms are zero exactly when no dropped scenario's loss
exceeds the threshold `t` (the VaR level).  The code checks that condition
(with a 1e-10 relative slack) before returning, and otherwise adds the
violated scenarios and re-solves.

The solver works on the equivalent LP with auxiliaries
`u_i >= loss_i - t, u_i >= 0`; at any optimum `u_i = max 0 (loss_i - t)`, so
the statements below, phrased with `max`, are the ones that matter.
-/
import Mathlib

open Finset

namespace Analog.Screening

/-- Constraint form: a minimiser of a relaxation that is feasible for the
full problem minimises the full problem. -/
theorem relaxation_exact {X : Type*} (f : X → ℝ) {Cfull Crel : Set X}
    (hsub : Cfull ⊆ Crel) {x : X} (hmin : ∀ y ∈ Crel, f x ≤ f y) :
    ∀ y ∈ Cfull, f x ≤ f y :=
  fun y hy => hmin y (hsub hy)

/-- Objective form: a lower model that is tight at its own minimiser. -/
theorem lower_model_exact {X : Type*} (K : Set X) (F G : X → ℝ)
    (hle : ∀ y ∈ K, G y ≤ F y) {x : X}
    (hmin : ∀ y ∈ K, G x ≤ G y) (htight : F x = G x) :
    ∀ y ∈ K, F x ≤ F y := by
  intro y hy
  rw [htight]
  exact (hmin y hy).trans (hle y hy)

/-- Rockafellar–Uryasev objective on the scenario set `s`, `c = 1/(alpha T)`. -/
noncomputable def ruObj {ι : Type*} (s : Finset ι) (c t : ℝ) (loss : ι → ℝ) : ℝ :=
  t + c * ∑ i ∈ s, max 0 (loss i - t)

theorem ru_restricted_le {ι : Type*} {S U : Finset ι} (hSU : S ⊆ U) {c : ℝ}
    (hc : 0 ≤ c) (t : ℝ) (loss : ι → ℝ) :
    ruObj S c t loss ≤ ruObj U c t loss := by
  unfold ruObj
  have hsum : ∑ i ∈ S, max 0 (loss i - t) ≤ ∑ i ∈ U, max 0 (loss i - t) :=
    Finset.sum_le_sum_of_subset_of_nonneg hSU (fun i _ _ => le_max_left _ _)
  linarith [mul_le_mul_of_nonneg_left hsum hc]

theorem ru_tight {ι : Type*} {S U : Finset ι} (hSU : S ⊆ U) (c t : ℝ)
    (loss : ι → ℝ) (hout : ∀ i ∈ U, i ∉ S → loss i ≤ t) :
    ruObj U c t loss = ruObj S c t loss := by
  unfold ruObj
  have h : ∑ i ∈ S, max 0 (loss i - t) = ∑ i ∈ U, max 0 (loss i - t) :=
    Finset.sum_subset hSU (fun i hiU hiS => max_eq_left (by linarith [hout i hiU hiS]))
  rw [h]

/-- CVaR screening is exact: if `(x, t)` minimises the restricted
Rockafellar–Uryasev objective over the feasible set `K` and no dropped
scenario's loss exceeds `t`, then `(x, t)` minimises the full objective. -/
theorem cvar_screening_exact {X ι : Type*} {S U : Finset ι} (hSU : S ⊆ U)
    {c : ℝ} (hc : 0 ≤ c) (K : Set (X × ℝ)) (loss : X → ι → ℝ) {x : X} {t : ℝ}
    (hmin : ∀ q ∈ K, ruObj S c t (loss x) ≤ ruObj S c q.2 (loss q.1))
    (hout : ∀ i ∈ U, i ∉ S → loss x i ≤ t) :
    ∀ q ∈ K, ruObj U c t (loss x) ≤ ruObj U c q.2 (loss q.1) := by
  intro q hq
  rw [ru_tight hSU c t (loss x) hout]
  exact (hmin q hq).trans (ru_restricted_le hSU hc q.2 (loss q.1))

/-- Worst realisation: `min M  s.t.  loss_i(x) <= M  (i ∈ U)`.  The
restricted problem is a relaxation (`relaxation_exact`); the code accepts
its solution when every dropped loss is `<= M`, i.e. it is feasible for the
full problem. -/
theorem wr_screening_exact {X ι : Type*} {S U : Finset ι} (hSU : S ⊆ U)
    (K : Set (X × ℝ)) (loss : X → ι → ℝ) {x : X} {M : ℝ}
    (hmin : ∀ q ∈ K, (∀ i ∈ S, loss q.1 i ≤ q.2) → M ≤ q.2)
    (hout : ∀ i ∈ U, i ∉ S → loss x i ≤ M) (hin : ∀ i ∈ S, loss x i ≤ M) :
    (∀ i ∈ U, loss x i ≤ M) ∧
      ∀ q ∈ K, (∀ i ∈ U, loss q.1 i ≤ q.2) → M ≤ q.2 := by
  refine ⟨fun i hi => ?_, fun q hq hfull => hmin q hq (fun i hi => hfull i (hSU hi))⟩
  by_cases hiS : i ∈ S
  · exact hin i hiS
  · exact hout i hi hiS

end Analog.Screening
