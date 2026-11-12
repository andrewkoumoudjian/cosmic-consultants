/-
PORTED 2026-11-12 from owner prior work: Hellinger/TV contraction under summaries
Source: andrewkoumoudjian/perps-strategy @ 0f34759, lanes/chief/lean/PerpChief/BinaryInfo.lean (toolchain v4.15.0).
Port changes ONLY: module path/import remap to Analog.Prior.* (+ Mathlib API renames if listed in docs/research/06). Namespaces, statements, proofs otherwise verbatim. Original file is frozen upstream; do not edit semantics here — supersede via new module + STATEMENTS.md.
-/
/-
VEST-RESIDUAL LANE: BINARY-SUMMARY INFORMATION CEILING (COURTADE–KUMAR / HELLINGER CONTRACTION).
FROZEN STATEMENTS (vest-residual lane), written before any October confusion count is used
in a ceiling computation by this lane. Source avenue: openai/math family 119 (The Courtade–Kumar
and Hellinger conjectures), recorded in lanes/vestresidual/THEORIES.md §3 item 119.

No binary summary of noisy data can increase separation between the hypotheses it separates:
pushing any test forward through a deterministic summarizer cannot decrease the Hellinger
affinity, so the binary channel's separation — and with it the best accuracy of any decoder
using only the summary — is capped by the affinity of the underlying masses. What is left for
data, one number per binary state (SqueezeUp, SEL-VOLEXP gate, SHORTGAP gate): the TV/Bayes
ceiling of its October 2×2 confusion channel, namely accuracy ≤ (1 + tv)/2 ≤ (1 + √(1 − bc²))/2,
where bc is the Hellinger affinity of the outcome-conditional masses and tv the total variation.
-/
import Mathlib.Data.Real.Sqrt
import Mathlib
import Mathlib
import Mathlib.Tactic

namespace PerpChief.BinaryInfo

open Finset

/-- Hellinger (Bhattacharyya) affinity of two finitely supported mass functions. -/
noncomputable def bc {ι : Type*} [Fintype ι] (p q : ι → ℝ) : ℝ :=
  ∑ i, Real.sqrt (p i * q i)

/-- Total variation of two finitely supported mass functions. -/
noncomputable def tv {ι : Type*} [Fintype ι] (p q : ι → ℝ) : ℝ :=
  (∑ i, |p i - q i|) / 2

/-- Pushforward of a mass function through a deterministic summarizer. -/
noncomputable def push {ι κ : Type*} [Fintype ι] [DecidableEq κ] [Fintype κ]
    (f : ι → κ) (p : ι → ℝ) : κ → ℝ :=
  fun k => ∑ i ∈ univ.filter (fun i => f i = k), p i

private lemma push_nonneg {ι κ : Type*} [Fintype ι] [DecidableEq κ] [Fintype κ]
    (f : ι → κ) (p : ι → ℝ) (hp : ∀ i, 0 ≤ p i) (k : κ) :
    0 ≤ push f p k := by
  unfold push
  exact Finset.sum_nonneg (fun i _ => hp i)

private lemma sum_push {ι κ : Type*} [Fintype ι] [DecidableEq κ] [Fintype κ]
    (f : ι → κ) (p : ι → ℝ) :
    ∑ k, push f p k = ∑ i, p i := by
  unfold push
  exact Finset.sum_fiberwise_of_maps_to (g := f) (fun i _ => mem_univ _) p

/-- B1. The affinity is non-negative. -/
theorem bc_nonneg {ι : Type*} [Fintype ι] (p q : ι → ℝ) :
    0 ≤ bc p q := by
  unfold bc
  exact Finset.sum_nonneg (fun i _ => Real.sqrt_nonneg _)

/-- B2. The affinity of two probability mass functions is at most one. -/
theorem bc_le_one {ι : Type*} [Fintype ι] (p q : ι → ℝ)
    (hp : ∀ i, 0 ≤ p i) (hq : ∀ i, 0 ≤ q i)
    (hp1 : ∑ i, p i = 1) (hq1 : ∑ i, q i = 1) :
    bc p q ≤ 1 := by
  have hsq : ∀ i, (Real.sqrt (p i)) ^ 2 = p i := fun i => Real.sq_sqrt (hp i)
  have hsq' : ∀ i, (Real.sqrt (q i)) ^ 2 = q i := fun i => Real.sq_sqrt (hq i)
  have hterm : ∀ i, Real.sqrt (p i) * Real.sqrt (q i) = Real.sqrt (p i * q i) :=
    fun i => (Real.sqrt_mul (hp i) (q i)).symm
  have hcs2 : (∑ i, Real.sqrt (p i) * Real.sqrt (q i)) ^ 2 ≤ (∑ i, p i) * ∑ i, q i := by
    have h1 := Finset.sum_mul_sq_le_sq_mul_sq univ (fun i => Real.sqrt (p i)) (fun i => Real.sqrt (q i))
    rwa [Finset.sum_congr rfl (fun i _ => hsq i), Finset.sum_congr rfl (fun i _ => hsq' i)] at h1
  have hthis : bc p q = ∑ i, Real.sqrt (p i) * Real.sqrt (q i) := by
    unfold bc
    exact (Finset.sum_congr rfl (fun i _ => hterm i)).symm
  have hbc : bc p q ^ 2 ≤ 1 := by
    calc bc p q ^ 2 = (∑ i, Real.sqrt (p i) * Real.sqrt (q i)) ^ 2 := by rw [hthis]
      _ ≤ (∑ i, p i) * ∑ i, q i := hcs2
      _ = 1 := by rw [hp1, hq1]; ring
  have hnn := bc_nonneg p q
  nlinarith [sq_nonneg (bc p q - 1)]

/-- B3. Hellinger contraction: no deterministic summary decreases the affinity.
This is the exact contraction inequality the ceiling computation uses. -/
theorem bc_push_ge {ι κ : Type*} [Fintype ι] [DecidableEq κ] [Fintype κ]
    (f : ι → κ) (p q : ι → ℝ)
    (hp : ∀ i, 0 ≤ p i) (hq : ∀ i, 0 ≤ q i) :
    bc p q ≤ bc (push f p) (push f q) := by
  unfold bc push
  have key : ∀ k : κ,
      ∑ i ∈ univ.filter (fun i => f i = k), Real.sqrt (p i * q i)
        ≤ Real.sqrt ((∑ i ∈ univ.filter (fun i => f i = k), p i)
          * ∑ i ∈ univ.filter (fun i => f i = k), q i) := by
    intro k
    set S := univ.filter (fun i => f i = k) with hS
    have hpS : ∀ i ∈ S, 0 ≤ p i := fun i _ => hp i
    have hqS : ∀ i ∈ S, 0 ≤ q i := fun i _ => hq i
    have hCS := Finset.sum_sq_le_sum_mul_sum_of_sq_eq_mul S hpS hqS
      (fun i _ => by rw [Real.sq_sqrt (mul_nonneg (hp i) (hq i))])
    exact Real.le_sqrt_of_sq_le hCS
  have hsum : (∑ k, ∑ i ∈ univ.filter (fun i => f i = k), Real.sqrt (p i * q i))
      = ∑ i, Real.sqrt (p i * q i) :=
    Finset.sum_fiberwise_of_maps_to (g := f) (fun i _ => mem_univ _) (fun i => Real.sqrt (p i * q i))
  calc ∑ i, Real.sqrt (p i * q i)
      = ∑ k, ∑ i ∈ univ.filter (fun i => f i = k), Real.sqrt (p i * q i) := hsum.symm
    _ ≤ ∑ k, Real.sqrt ((∑ i ∈ univ.filter (fun i => f i = k), p i)
          * ∑ i ∈ univ.filter (fun i => f i = k), q i) :=
        Finset.sum_le_sum (fun k _ => key k)

/-- B4. Total variation is bounded by the square root of one minus the squared affinity. -/
theorem tv_le_sqrt {ι : Type*} [Fintype ι] (p q : ι → ℝ)
    (hp : ∀ i, 0 ≤ p i) (hq : ∀ i, 0 ≤ q i)
    (hp1 : ∑ i, p i = 1) (hq1 : ∑ i, q i = 1) :
    tv p q ≤ Real.sqrt (1 - bc p q ^ 2) := by
  have hb0 := bc_nonneg p q
  have hb1 := bc_le_one p q hp hq hp1 hq1
  have hA : ∑ i, (Real.sqrt (p i) - Real.sqrt (q i)) ^ 2 = 2 - 2 * bc p q := by
    have hpt : ∀ i, (Real.sqrt (p i) - Real.sqrt (q i)) ^ 2
        = p i + q i - 2 * Real.sqrt (p i * q i) := by
      intro i
      rw [sub_sq, Real.sq_sqrt (hp i), Real.sq_sqrt (hq i),
        Real.sqrt_mul (hp i) (q i)]
      ring
    rw [Finset.sum_congr rfl (fun i _ => hpt i),
      Finset.sum_sub_distrib, Finset.sum_add_distrib, hp1, hq1,
      ← Finset.mul_sum]
    unfold bc
    ring
  have hB : ∑ i, (Real.sqrt (p i) + Real.sqrt (q i)) ^ 2 = 2 + 2 * bc p q := by
    have hpt : ∀ i, (Real.sqrt (p i) + Real.sqrt (q i)) ^ 2
        = p i + q i + 2 * Real.sqrt (p i * q i) := by
      intro i
      rw [add_sq, Real.sq_sqrt (hp i), Real.sq_sqrt (hq i),
        Real.sqrt_mul (hp i) (q i)]
      ring
    rw [Finset.sum_congr rfl (fun i _ => hpt i),
      Finset.sum_add_distrib, Finset.sum_add_distrib, hp1, hq1,
      ← Finset.mul_sum]
    unfold bc
    ring
  have habs : ∀ i, |p i - q i|
      = |Real.sqrt (p i) - Real.sqrt (q i)| * (Real.sqrt (p i) + Real.sqrt (q i)) := by
    intro i
    have hfact : p i - q i
        = (Real.sqrt (p i) - Real.sqrt (q i)) * (Real.sqrt (p i) + Real.sqrt (q i)) := by
      have h1 : (Real.sqrt (p i) - Real.sqrt (q i)) * (Real.sqrt (p i) + Real.sqrt (q i))
          = (Real.sqrt (p i)) ^ 2 - (Real.sqrt (q i)) ^ 2 := by ring
      rw [h1, Real.sq_sqrt (hp i), Real.sq_sqrt (hq i)]
    rw [hfact, abs_mul, abs_of_nonneg (add_nonneg (Real.sqrt_nonneg _) (Real.sqrt_nonneg _))]
  have hcs := Finset.sum_mul_sq_le_sq_mul_sq univ
    (fun i => |Real.sqrt (p i) - Real.sqrt (q i)|) (fun i => Real.sqrt (p i) + Real.sqrt (q i))
  have hsq_abs : ∀ i, (|Real.sqrt (p i) - Real.sqrt (q i)|) ^ 2
      = (Real.sqrt (p i) - Real.sqrt (q i)) ^ 2 := fun i => sq_abs _
  rw [Finset.sum_congr rfl (fun i _ => hsq_abs i), hA, hB] at hcs
  have hcs' : (∑ i, |p i - q i|) ^ 2 ≤ 4 - 4 * bc p q ^ 2 := by
    have hsum : ∑ i, |Real.sqrt (p i) - Real.sqrt (q i)| * (Real.sqrt (p i) + Real.sqrt (q i))
        = ∑ i, |p i - q i| := Finset.sum_congr rfl (fun i _ => (habs i).symm)
    rw [← hsum]
    calc (∑ i, |Real.sqrt (p i) - Real.sqrt (q i)| * (Real.sqrt (p i) + Real.sqrt (q i))) ^ 2
        ≤ (2 - 2 * bc p q) * (2 + 2 * bc p q) := hcs
      _ = 4 - 4 * bc p q ^ 2 := by ring
  have htv : tv p q ^ 2 ≤ 1 - bc p q ^ 2 := by
    unfold tv
    rw [div_pow, show (2 : ℝ) ^ 2 = 4 by ring]
    have h4 : (∑ i, |p i - q i|) ^ 2 ≤ 4 - 4 * bc p q ^ 2 := hcs'
    linarith
  exact Real.le_sqrt_of_sq_le htv

/-- B5. The binary channel induced by a summary has its separation capped by the
affinity of the underlying masses; any decoder using only the summary cannot beat
accuracy (1 + tv)/2 ≤ (1 + √(1 − bc p q ^ 2))/2. -/
theorem tv_push_le {ι κ : Type*} [Fintype ι] [DecidableEq κ] [Fintype κ]
    (f : ι → κ) (p q : ι → ℝ)
    (hp : ∀ i, 0 ≤ p i) (hq : ∀ i, 0 ≤ q i)
    (hp1 : ∑ i, p i = 1) (hq1 : ∑ i, q i = 1) :
    tv (push f p) (push f q) ≤ Real.sqrt (1 - bc p q ^ 2) := by
  have hpp : ∀ k, 0 ≤ push f p k := fun k => push_nonneg f p hp k
  have hqp : ∀ k, 0 ≤ push f q k := fun k => push_nonneg f q hq k
  have hpsum : ∑ k, push f p k = 1 := by rw [sum_push, hp1]
  have hqsum : ∑ k, push f q k = 1 := by rw [sum_push, hq1]
  have hb0 := bc_nonneg (push f p) (push f q)
  have hb1 := bc_le_one (push f p) (push f q) hpp hqp hpsum hqsum
  have hle := tv_le_sqrt (push f p) (push f q) hpp hqp hpsum hqsum
  have hbcge := bc_push_ge f p q hp hq
  have hb0' := bc_nonneg p q
  have hb1' := bc_le_one p q hp hq hp1 hq1
  have hle2 : Real.sqrt (1 - bc (push f p) (push f q) ^ 2) ≤ Real.sqrt (1 - bc p q ^ 2) := by
    apply Real.sqrt_le_sqrt
    have hsq : bc p q ^ 2 ≤ bc (push f p) (push f q) ^ 2 := by
      have h1 : bc p q ≤ bc (push f p) (push f q) := hbcge
      nlinarith [sq_nonneg (bc p q), mul_nonneg hb0' hb0, sq_nonneg (bc (push f p) (push f q))]
    linarith
  exact le_trans hle hle2

end PerpChief.BinaryInfo
