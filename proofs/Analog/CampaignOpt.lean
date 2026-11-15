/-
S10 (Multi-year CVaR campaign allocation LP, dual certificate, and tail screening)
STATEMENT module (work order W22, issue #170; ADR-0001, ADR-0005 D5,
MISSION-PLANNER.md "Campaign optimizer").

This file contains DEFINITIONS and PROPOSITIONS ONLY. No proofs live here;
`CampaignOptProofs.lean` proves every `S10...` Prop below, building directly on
`Analog.Screening` and `Analog.Certificate`.
-/
import Mathlib
import Analog.Screening
import Analog.Certificate

open Finset

namespace Analog.CampaignOpt

open Analog.Screening Analog.Certificate

/-- Problem parameters for multi-year Rockafellar–Uryasev CVaR campaign day
allocation across `m` candidate `(site, month)` pairs, `T` historical years
(scenarios), and `k` required traits:
- `hi`: per-pair allocation upper bound (`0 ≤ w j ≤ hi j`),
- `cov`: trait coverage indicator/coefficient (`req r ≤ ∑ j, cov r j * w j`),
- `cost`, `budget`: linear travel-cost proxy (`∑ j, cost j * w j ≤ budget`),
- `L`: annual loss matrix (`L i j` = loss of pair `j` in year `i`). -/
structure CampaignProblem (m T k : ℕ) where
  hi : Fin m → ℝ
  cov : Fin k → Fin m → ℝ
  req : Fin k → ℝ
  cost : Fin m → ℝ
  budget : ℝ
  L : Fin T → Fin m → ℝ
  c : ℝ
  hc : 0 ≤ c

/-- Annual campaign loss in year `i` under field-day weights `w`. -/
def scenarioLoss {m T k : ℕ} (P : CampaignProblem m T k) (w : Fin m → ℝ) (i : Fin T) : ℝ :=
  ∑ j : Fin m, P.L i j * w j

/-- Feasible allocation weights `w` for campaign problem `P`. -/
def CampaignFeasible {m T k : ℕ} (P : CampaignProblem m T k) (w : Fin m → ℝ) : Prop :=
  (∀ j, 0 ≤ w j ∧ w j ≤ P.hi j) ∧
  (∑ j : Fin m, w j = 1) ∧
  (∀ r, P.req r ≤ ∑ j : Fin m, P.cov r j * w j) ∧
  (∑ j : Fin m, P.cost j * w j ≤ P.budget)

/-- Linearized Rockafellar–Uryasev LP epigraph feasibility on scenario subset `S`:
`u i ≥ 0` and `u i ≥ loss_i(w) - t` for every `i ∈ S`. -/
def EpigraphFeasible {m T k : ℕ} (P : CampaignProblem m T k)
    (S : Finset (Fin T)) (w : Fin m → ℝ) (t : ℝ) (u : Fin T → ℝ) : Prop :=
  CampaignFeasible P w ∧ ∀ i ∈ S, 0 ≤ u i ∧ scenarioLoss P w i - t ≤ u i

/-- Linearized Rockafellar–Uryasev LP objective on scenario subset `S`. -/
def lpObj {T : ℕ} (S : Finset (Fin T)) (c t : ℝ) (u : Fin T → ℝ) : ℝ :=
  t + c * ∑ i ∈ S, u i

/-- Full feasible set in `(w, t)` space for `Analog.Screening.cvar_screening_exact`. -/
def FeasibleWT {m T k : ℕ} (P : CampaignProblem m T k) : Set ((Fin m → ℝ) × ℝ) :=
  { q | CampaignFeasible P q.1 }

/-! ## S10 propositions -/

/-- **S10a (epigraph relaxation bound):** every epigraph-feasible `(w, t, u)`
upper-bounds `ruObj S P.c t (scenarioLoss P w)`, with exact equality at
`u i = max 0 (scenarioLoss P w i - t)`. -/
def S10a_epigraph_tight {m T k : ℕ} : Prop :=
  ∀ (P : CampaignProblem m T k) (S : Finset (Fin T))
    (w : Fin m → ℝ) (t : ℝ) (u : Fin T → ℝ),
    EpigraphFeasible P S w t u →
      ruObj S P.c t (scenarioLoss P w) ≤ lpObj S P.c t u ∧
      ((∀ i ∈ S, u i = max 0 (scenarioLoss P w i - t)) →
        ruObj S P.c t (scenarioLoss P w) = lpObj S P.c t u)

/-- **S10b (exact multi-year tail screening):** if `(w*, t*)` minimizes the
screened Rockafellar–Uryasev objective over active years `S ⊆ Finset.univ` and
every dropped year `i ∉ S` has loss `≤ t*`, then `(w*, t*)` minimizes the full
multi-year CVaR objective over all `T` years. -/
def S10b_cvar_screening_exact {m T k : ℕ} : Prop :=
  ∀ (P : CampaignProblem m T k) (S : Finset (Fin T))
    {w : Fin m → ℝ} {t : ℝ},
    CampaignFeasible P w →
    (∀ q ∈ FeasibleWT P,
      ruObj S P.c t (scenarioLoss P w) ≤ ruObj S P.c q.2 (scenarioLoss P q.1)) →
    (∀ i : Fin T, i ∉ S → scenarioLoss P w i ≤ t) →
    ∀ q ∈ FeasibleWT P,
      ruObj Finset.univ P.c t (scenarioLoss P w) ≤
        ruObj Finset.univ P.c q.2 (scenarioLoss P q.1)

/-- **S10c (convexity of campaign feasible region):** any convex combination of
two feasible campaign allocations stays feasible (budget, caps, coverage, cost). -/
def S10c_convex_feasible {m T k : ℕ} : Prop :=
  ∀ (P : CampaignProblem m T k) {w₁ w₂ : Fin m → ℝ} {θ : ℝ},
    0 ≤ θ → θ ≤ 1 →
    CampaignFeasible P w₁ → CampaignFeasible P w₂ →
    CampaignFeasible P (fun j => (1 - θ) * w₁ j + θ * w₂ j)

/-- **S10d (computable dual suboptimality certificate):** for the linear CVaR
objective `f z = ∑ i, g i * z i` under constraints `G z ≤ h, E z = e`, any
primal iterate `z` and dual multipliers `lam ≥ 0, y` with residual bound
`|g i + ∑ j, G j i * lam j + ∑ r, E r i * y r| ≤ M` satisfies the explicit
suboptimality bound against every feasible `z*`. -/
def S10d_dual_subopt_certificate {n r p : ℕ} : Prop :=
  ∀ (z zs g : Fin n → ℝ)
    (G : Fin r → Fin n → ℝ) (h lam : Fin r → ℝ)
    (E : Fin p → Fin n → ℝ) (e y : Fin p → ℝ) (M : ℝ),
    (∀ j, ∑ i, G j i * zs i ≤ h j) →
    (∀ l, ∑ i, E l i * zs i = e l) →
    (∀ j, 0 ≤ lam j) →
    (∀ i, |g i + ∑ j, G j i * lam j + ∑ l, E l i * y l| ≤ M) →
    (∑ i, g i * z i) - (∑ i, g i * zs i) ≤
      ∑ j, lam j * (h j - ∑ i, G j i * z i)
      + ∑ l, y l * (e l - ∑ i, E l i * z i)
      + M * ∑ i, |z i - zs i|

/-- **S10e (bound preservation):** any campaign-feasible allocation respects
non-negativity, unit simplex sum, and per-pair caps (`ADR-0005 D5`: plan allocation,
never a scalar site analogy score). -/
def S10e_allocation_bounds {m T k : ℕ} : Prop :=
  ∀ (P : CampaignProblem m T k) (w : Fin m → ℝ),
    CampaignFeasible P w →
      (∀ j, 0 ≤ w j ∧ w j ≤ P.hi j) ∧ ∑ j : Fin m, w j = 1

end Analog.CampaignOpt
