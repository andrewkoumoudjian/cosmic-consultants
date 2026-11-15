/-
# W22 (#170): proofs of the S10 CVaR campaign optimizer statements

Proves every `S10...` Prop defined in `Analog/CampaignOpt.lean` cleanly,
instantiating `Analog.Screening.cvar_screening_exact` and
`Analog.Certificate.subopt_le` with standard axioms only and no unproven
placeholders or escape hatches.
-/
import Mathlib
import Analog.CampaignOpt

namespace Analog.CampaignOptProofs

open Analog.Screening Analog.Certificate Analog.CampaignOpt Finset

/-- **S10a**: epigraph LP objective upper-bounds `ruObj` and is exact when
`u i = max 0 (loss_i(w) - t)`. -/
theorem s10a_epigraph_tight {m T k : ℕ} :
    S10a_epigraph_tight (m := m) (T := T) (k := k) := by
  intro P S w t u ⟨_hfeas, hepi⟩
  refine ⟨?_, ?_⟩
  · unfold ruObj lpObj
    have hsum : ∑ i ∈ S, max 0 (scenarioLoss P w i - t) ≤ ∑ i ∈ S, u i := by
      refine Finset.sum_le_sum fun i hi => ?_
      exact max_le (hepi i hi).1 (hepi i hi).2
    linarith [mul_le_mul_of_nonneg_left hsum P.hc]
  · intro htight
    unfold ruObj lpObj
    have hsum : ∑ i ∈ S, max 0 (scenarioLoss P w i - t) = ∑ i ∈ S, u i :=
      Finset.sum_congr rfl fun i hi => (htight i hi).symm
    rw [hsum]

/-- **S10b**: Rockafellar–Uryasev tail-scenario screening is exact for the
multi-year campaign allocation problem. -/
theorem s10b_cvar_screening_exact {m T k : ℕ} :
    S10b_cvar_screening_exact (m := m) (T := T) (k := k) := by
  intro P S w t _hfeas hmin hout q hq
  exact cvar_screening_exact (Finset.subset_univ S) P.hc (FeasibleWT P) (scenarioLoss P) hmin
    (fun i _ hiS => hout i hiS) q hq

/-- **S10c**: convex combination preserves every campaign constraint. -/
theorem s10c_convex_feasible {m T k : ℕ} :
    S10c_convex_feasible (m := m) (T := T) (k := k) := by
  intro P w₁ w₂ θ hθ0 hθ1 hw₁ hw₂
  have h1θ : 0 ≤ 1 - θ := sub_nonneg.mpr hθ1
  refine ⟨?_, ?_, ?_, ?_⟩
  · intro j
    obtain ⟨hw₁0, hw₁h⟩ := hw₁.1 j
    obtain ⟨hw₂0, hw₂h⟩ := hw₂.1 j
    refine ⟨add_nonneg (mul_nonneg h1θ hw₁0) (mul_nonneg hθ0 hw₂0), ?_⟩
    calc (1 - θ) * w₁ j + θ * w₂ j
        ≤ (1 - θ) * P.hi j + θ * P.hi j :=
          add_le_add (mul_le_mul_of_nonneg_left hw₁h h1θ) (mul_le_mul_of_nonneg_left hw₂h hθ0)
      _ = P.hi j := by ring
  · calc ∑ j : Fin m, ((1 - θ) * w₁ j + θ * w₂ j)
        = (1 - θ) * (∑ j : Fin m, w₁ j) + θ * (∑ j : Fin m, w₂ j) := by
          rw [Finset.sum_add_distrib, ← Finset.mul_sum, ← Finset.mul_sum]
      _ = (1 - θ) * 1 + θ * 1 := by rw [hw₁.2.1, hw₂.2.1]
      _ = 1 := by ring
  · intro r
    have hsplit : ∑ j : Fin m, P.cov r j * ((1 - θ) * w₁ j + θ * w₂ j) =
        (1 - θ) * (∑ j : Fin m, P.cov r j * w₁ j) + θ * (∑ j : Fin m, P.cov r j * w₂ j) := by
      have hterm : ∀ j, P.cov r j * ((1 - θ) * w₁ j + θ * w₂ j) =
          (1 - θ) * (P.cov r j * w₁ j) + θ * (P.cov r j * w₂ j) := fun j => by ring
      simp_rw [hterm, Finset.sum_add_distrib, ← Finset.mul_sum]
    rw [hsplit]
    have h1 := mul_le_mul_of_nonneg_left (hw₁.2.2.1 r) h1θ
    have h2 := mul_le_mul_of_nonneg_left (hw₂.2.2.1 r) hθ0
    linarith
  · have hsplit : ∑ j : Fin m, P.cost j * ((1 - θ) * w₁ j + θ * w₂ j) =
        (1 - θ) * (∑ j : Fin m, P.cost j * w₁ j) + θ * (∑ j : Fin m, P.cost j * w₂ j) := by
      have hterm : ∀ j, P.cost j * ((1 - θ) * w₁ j + θ * w₂ j) =
          (1 - θ) * (P.cost j * w₁ j) + θ * (P.cost j * w₂ j) := fun j => by ring
      simp_rw [hterm, Finset.sum_add_distrib, ← Finset.mul_sum]
    rw [hsplit]
    have h1 := mul_le_mul_of_nonneg_left hw₁.2.2.2 h1θ
    have h2 := mul_le_mul_of_nonneg_left hw₂.2.2.2 hθ0
    linarith

/-- **S10d**: instantiates `Analog.Certificate.subopt_le` for the linear
Rockafellar–Uryasev campaign LP. -/
theorem s10d_dual_subopt_certificate {n r p : ℕ} :
    S10d_dual_subopt_certificate (n := n) (r := r) (p := p) := by
  intro z zs g G h lam E e y M hfeas heq hlam hM
  have hconv : (∑ i, g i * z i) - (∑ i, g i * zs i) ≤ ∑ i, g i * (z i - zs i) := by
    rw [← Finset.sum_sub_distrib]
    exact le_of_eq (Finset.sum_congr rfl fun i _ => by ring)
  exact subopt_le (fun v => ∑ i, g i * v i) z zs g G h lam E e y M hconv hfeas heq hlam hM

/-- **S10e**: feasible campaign weights satisfy simplex sum and per-pair caps. -/
theorem s10e_allocation_bounds {m T k : ℕ} :
    S10e_allocation_bounds (m := m) (T := T) (k := k) :=
  fun _ _ hw => ⟨hw.1, hw.2.1⟩

end Analog.CampaignOptProofs
