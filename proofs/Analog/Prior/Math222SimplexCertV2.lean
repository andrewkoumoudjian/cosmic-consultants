/-
PORTED 2026-11-12 from owner prior work: LP duality + Farkas certificates
Source: andrewkoumoudjian/perps-strategy @ 0f34759, lanes/chief/lean/PerpChief/Math222SimplexCertV2.lean (toolchain v4.15.0).
Port changes ONLY: module path/import remap to Analog.Prior.* (+ Mathlib API renames if listed in docs/research/06). Namespaces, statements, proofs otherwise verbatim. Original file is frozen upstream; do not edit semantics here — supersede via new module + STATEMENTS.md.
-/
/- FROZEN statement (parent mathematics review, Phase A): finite dual-certificate theory for the
   simplex LP of experiment M07 (family 222 finiteness shell). One fixed finite
   matrix, exact real arithmetic. Proves the certificate logic used by the
   HiGHS classification: a nonnegative, mass-one row weighting y whose every
   convex-weighted column strictly exceeds a scalar threshold b makes
   "Aw <= b with w a probability vector" impossible, and vice versa weak
   duality bounds the LP objective. NO perceptron exponent, no annealed
   entropy, no density limit, no catalogue theorem, no market statement and
   no numerical-accuracy claim about floating-point solvers is proved here. -/
import Mathlib.Tactic

namespace PerpChief.Math222SimplexCertV2

variable {m d : ℕ}

/-- `w` is a point of the closed probability simplex: componentwise
    nonnegative with total mass 1. Cost side: `d` weights. -/
def IsSimplex (w : Fin d → ℝ) : Prop := (∀ j, 0 ≤ w j) ∧ (∑ j, w j = 1)

/-- Simplex feasibility of the M07 constraint system with scalar threshold
    `b`: some simplex `w` has every component of `Aw` at most `b`. -/
def Feasible (A : Fin m → Fin d → ℝ) (b : ℝ) : Prop :=
  ∃ w, IsSimplex w ∧ ∀ i, (∑ j, A i j * w j) ≤ b

/-- The dual certificate actually checked by the M07 run (y = the negated
    simplex marginals): `y` is a mass-one nonnegative row weighting and every
    convex-weighted column sum `(Aᵀy) j` strictly exceeds `b`. -/
def Certifies (A : Fin m → Fin d → ℝ) (y : Fin m → ℝ) (b : ℝ) : Prop :=
  IsSimplex y ∧ ∀ j, b < (∑ i, y i * A i j)

/-- Simplex feasibility against a vector of per-row thresholds `b i`. -/
def FeasibleV (A : Fin m → Fin d → ℝ) (b : Fin m → ℝ) : Prop :=
  ∃ w, IsSimplex w ∧ ∀ i, (∑ j, A i j * w j) ≤ b i

/-- L1. Mass-weighted sums of strictly positive quantities are strictly
    positive. This is the only inequality engine of the module; it is what
    fails when weights are allowed to be negative. -/
theorem pos_weighted_sum (w : Fin d → ℝ) (hw : IsSimplex w) (f : Fin d → ℝ)
    (hf : ∀ j, 0 < f j) : 0 < ∑ j, w j * f j := by
  by_contra hc
  have hzero : ∑ j, w j * f j = 0 := by
    have hnn : 0 ≤ ∑ j, w j * f j :=
      Finset.sum_nonneg (fun j _ => mul_nonneg (hw.1 j) (le_of_lt (hf j)))
    linarith
  have hall : ∀ j, w j * f j = 0 := fun j =>
    (Finset.sum_eq_zero_iff_of_nonneg
      (fun k (_ : k ∈ (Finset.univ : Finset (Fin d))) =>
        mul_nonneg (hw.1 k) (le_of_lt (hf k)))).mp hzero j (Finset.mem_univ j)
  have hwzero : ∀ j, w j = 0 := fun j => by
    rcases mul_eq_zero.mp (hall j) with hW | hF
    · exact hW
    · exact absurd hF (ne_of_gt (hf j))
  have h1 : (∑ j, w j) = 1 := hw.2
  rw [show (∑ j, w j) = 0 from Finset.sum_eq_zero (fun j _ => hwzero j)] at h1
  linarith

/-- T1. Transfer identity between primal row-weighting and dual
    column-weighting of the same matrix: `y ⬝ (Aw) = w ⬝ (Aᵀ y)`. Exact,
    needs only that sums of products reassociate and commute. -/
theorem transfer_identity (A : Fin m → Fin d → ℝ) (w : Fin d → ℝ) (y : Fin m → ℝ) :
    (∑ i, y i * (∑ j, A i j * w j)) = (∑ j, w j * (∑ i, y i * A i j)) := by
  simp only [Finset.mul_sum]
  rw [Finset.sum_comm]
  refine Finset.sum_congr rfl fun j _ => ?_
  refine Finset.sum_congr rfl fun i _ => ?_
  ring

/-- T2. Weak duality for the M07 LP with both simplex premises: if simplex
    `w` meets every constraint at target level `t + b`, then the dual
    objective `min_j (Aᵀy) j − b` cannot exceed `t`; constructively, some
    column `j` satisfies `(Aᵀy) j − b ≤ t`. Strict separation at `b`
    (T3/T4) is the case `t = 0`, so the certificate is a special case of
    this statement rather than an assumed conclusion. -/
theorem lp_weak_duality (A : Fin m → Fin d → ℝ) (b t : ℝ) (w : Fin d → ℝ)
    (y : Fin m → ℝ) (hw : IsSimplex w) (hy : IsSimplex y)
    (hA : ∀ i, (∑ j, A i j * w j) ≤ t + b) :
    ∃ j, (∑ i, y i * A i j) - b ≤ t := by
  by_contra hc
  push_neg at hc
  have hL1 : 0 < ∑ j, w j * ((∑ i, y i * A i j) - (t + b)) :=
    pos_weighted_sum w hw _ fun j => by have := hc j; linarith
  have hsplit : (∑ j, w j * ((∑ i, y i * A i j) - (t + b)))
      = (∑ j, w j * (∑ i, y i * A i j)) - (t + b) := by
    have hA1 : (∑ j, w j * ((∑ i, y i * A i j) - (t + b)))
        = (∑ j, w j * (∑ i, y i * A i j)) - (∑ j, w j * (t + b)) := by
      simp only [mul_sub, Finset.sum_sub_distrib]
    have hA2 : (∑ j, w j * (t + b)) = t + b := by
      rw [← Finset.sum_mul, hw.2, one_mul]
    rw [hA1, hA2]
  have hprimal : (∑ i, y i * (∑ j, A i j * w j)) ≤ t + b := by
    calc (∑ i, y i * (∑ j, A i j * w j))
        ≤ (∑ i, y i * (t + b)) :=
          Finset.sum_le_sum (fun i _ => mul_le_mul_of_nonneg_left (hA i) (hy.1 i))
      _ = t + b := by rw [← Finset.sum_mul, hy.2, one_mul]
  rw [transfer_identity A w y] at hprimal
  linarith

/-- T3. Main certificate theorem: a strict dual certificate at `b` refutes
    scalar threshold feasibility. -/
theorem certificate_infeasible (A : Fin m → Fin d → ℝ) (b : ℝ) (y : Fin m → ℝ)
    (h : Certifies A y b) : ¬ Feasible A b := by
  intro hfeas
  rcases hfeas with ⟨w, hw, hAw⟩
  obtain ⟨j, hj⟩ := lp_weak_duality A b 0 w y hw h.1
    (fun i => by linarith [hAw i])
  exact absurd hj (by have := h.2 j; linarith)

/-- T4. Strengthened witness form: for a certified system, not only does no
    simplex `w` work — every simplex `w` exhibits a concrete violating row. -/
theorem certificate_row (A : Fin m → Fin d → ℝ) (b : ℝ) (y : Fin m → ℝ)
    (hy : IsSimplex y) (hcol : ∀ j, b < (∑ i, y i * A i j)) (w : Fin d → ℝ)
    (hw : IsSimplex w) : ∃ i, b < (∑ j, A i j * w j) := by
  by_contra hc
  push_neg at hc
  exact certificate_infeasible A b y ⟨hy, hcol⟩ ⟨w, hw, hc⟩

/-- T5. Vector-threshold generalisation: the certificate separates against
    any per-row threshold vector once the dual budget `η = ∑ i, y i * b i`
    is substituted for the scalar `b`. The M07 run (constant `b`) is the
    special case `b i ≡ b`, where `η = b`. -/
theorem certificate_general (A : Fin m → Fin d → ℝ) (b : Fin m → ℝ)
    (y : Fin m → ℝ) (hy : IsSimplex y)
    (hcol : ∀ j, (∑ i, y i * b i) < (∑ i, y i * A i j)) :
    ¬ FeasibleV A b := by
  intro hfeas
  rcases hfeas with ⟨w, hw, hAw⟩
  have hprimal : (∑ i, y i * (∑ j, A i j * w j)) ≤ (∑ i, y i * b i) :=
    Finset.sum_le_sum (fun i _ => mul_le_mul_of_nonneg_left (hAw i) (hy.1 i))
  rw [transfer_identity A w y] at hprimal
  have hL1 : 0 < ∑ j, w j * ((∑ i, y i * A i j) - (∑ i, y i * b i)) :=
    pos_weighted_sum w hw _ fun j => by rw [sub_pos]; exact hcol j
  have hsplit : (∑ j, w j * ((∑ i, y i * A i j) - (∑ i, y i * b i)))
      = (∑ j, w j * (∑ i, y i * A i j)) - (∑ i, y i * b i) := by
    have hA1 : (∑ j, w j * ((∑ i, y i * A i j) - (∑ i, y i * b i)))
        = (∑ j, w j * (∑ i, y i * A i j))
          - (∑ j, w j * (∑ i, y i * b i)) := by
      simp only [mul_sub, Finset.sum_sub_distrib]
    have hA2 : (∑ j, w j * (∑ i, y i * b i)) = (∑ i, y i * b i) := by
      rw [← Finset.sum_mul, hw.2, one_mul]
    rw [hA1, hA2]
  linarith

/-- T6. Threshold shrinkage: the same `y` certifies every smaller threshold.
    With `min_j (Aᵀy) j` as capacity this is exactly the ordering shape of
    the frozen `PerpChief.Math222Slack.slack_antitone` (for `a ≤ b`,
    capacity − b ≤ capacity − a): declaring a lower feasibility threshold
    leaves the dual margin no smaller. Restated independently; no import, no
    modification of the frozen module. -/
theorem certificate_shrinks (A : Fin m → Fin d → ℝ) (b b' : ℝ) (y : Fin m → ℝ)
    (h : Certifies A y b) (hb : b' ≤ b) : Certifies A y b' := by
  exact ⟨h.1, fun j => lt_of_le_of_lt hb (h.2 j)⟩

end PerpChief.Math222SimplexCertV2

