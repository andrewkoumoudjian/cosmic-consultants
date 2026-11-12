/-
PORTED 2026-11-12 from owner prior work: Bonferroni / mixing bounds
Source: andrewkoumoudjian/perps-strategy @ 0f34759, lanes/chief/lean/PerpChief/L13Mixing.lean (toolchain v4.15.0).
Port changes ONLY: module path/import remap to Analog.Prior.* (+ Mathlib API renames if listed in docs/research/06). Namespaces, statements, proofs otherwise verbatim. Original file is frozen upstream; do not edit semantics here — supersede via new module + STATEMENTS.md.
-/
/-
PB-L13, Phase B: parent freeze of the mixing-implication module.
Explicit-implication-only mixing statements; no finite-sample FWER or
test-validity claim is derived from mixing. Every theorem takes the
finite-sample test structure it needs as an explicit hypothesis, and
all statements are single-clock: a shift on one tape index only.
-/
import Mathlib.Tactic

namespace PerpChief.L13Mixing

/-! ### A. Finite tape primitives -/

/-- The mean of a realized reading over the first `m` clock ticks. -/

noncomputable def tapeMean (x : ℕ → ℝ) (m : ℕ) : ℝ :=
  (∑ i ∈ Finset.range m, x i) / m

/-- The lag-`k` joint pairing of two readings on an `m`-tick tape:
the mean of the pointwise products over the `m - k` aligned ticks.
The window length is guarded positive by every caller. -/

noncomputable def jointMean (f g : ℕ → ℝ) (m k : ℕ) : ℝ :=
  (∑ i ∈ Finset.range (m - k), f i * g (i + k)) / (m - k)

/-- The product of the two marginal empirical means over the full
`m`-tick tape: the joint-vs-product divergence is measured against
this. -/

noncomputable def marginalProduct (f g : ℕ → ℝ) (m : ℕ) : ℝ :=
  tapeMean f m * tapeMean g m

/-- The stated distance on a realized tape: the gap between the
lag-`k` joint pairing and the product of the two marginal means. -/

noncomputable def pairGap (f g : ℕ → ℝ) (m k : ℕ) : ℝ :=
  |jointMean f g m k - marginalProduct f g m|

/-! ### B. Bounded-readings implications -/

/-- A bounded marginal mean never exceeds its bound. -/
theorem abs_tapeMean_le {x : ℕ → ℝ} {B : ℝ} {m : ℕ} (hm : 0 < m)
    (hb : ∀ i, |x i| ≤ B) : |tapeMean x m| ≤ B := by
  have hr : (0:ℝ) < (m:ℝ) := by exact_mod_cast hm
  rw [tapeMean, abs_div, abs_of_pos hr, div_le_iff₀ hr]
  refine le_trans (Finset.abs_sum_le_sum_abs _ _) ?_
  calc ∑ i ∈ Finset.range m, |x i| ≤ ∑ i ∈ Finset.range m, B :=
        Finset.sum_le_sum (fun i _ => hb i)
    _ ≤ B * (m:ℝ) := by
        rw [Finset.sum_const, Finset.card_range, nsmul_eq_mul, mul_comm]

/-- The lag-`k` joint pairing of bounded readings stays inside the
product of the two bounds: the computational form of the conditional
second-moment bound on the tape. -/
theorem abs_jointMean_le {f g : ℕ → ℝ} {Bf Bg : ℝ} {m k : ℕ} (hm : 0 < m - k)
    (hfb : ∀ i, |f i| ≤ Bf) (hgb : ∀ i, |g i| ≤ Bg) :
    |jointMean f g m k| ≤ Bf * Bg := by
  have hkm : k ≤ m := by omega
  have hr : (0:ℝ) < (m:ℝ) - (k:ℝ) := by
    have h2 : (0:ℝ) < ((m - k : ℕ) : ℝ) := by exact_mod_cast hm
    rwa [Nat.cast_sub hkm] at h2
  rw [jointMean, abs_div, abs_of_pos hr, div_le_iff₀ hr]
  refine le_trans (Finset.abs_sum_le_sum_abs _ _) ?_
  calc ∑ i ∈ Finset.range (m - k), |f i * g (i + k)|
        ≤ ∑ i ∈ Finset.range (m - k), Bf * Bg :=
        Finset.sum_le_sum (fun i _ => by
          rw [abs_mul]
          exact mul_le_mul (hfb i) (hgb (i + k)) (abs_nonneg _)
            (le_trans (abs_nonneg _) (hfb i)))
    _ = Bf * Bg * ((m:ℝ) - (k:ℝ)) := by
        rw [Finset.sum_const, Finset.card_range, nsmul_eq_mul,
          Nat.cast_sub hkm]
        ring

/-- The product of the two marginal means of bounded readings stays
inside the product of the two bounds. -/
theorem abs_marginalProduct_le {f g : ℕ → ℝ} {Bf Bg : ℝ} {m : ℕ} (hm : 0 < m)
    (hfb : ∀ i, |f i| ≤ Bf) (hgb : ∀ i, |g i| ≤ Bg) :
    |marginalProduct f g m| ≤ Bf * Bg := by
  have hBf0 : 0 ≤ Bf := le_trans (abs_nonneg _) (hfb 0)
  have h1 : |tapeMean f m| ≤ Bf := abs_tapeMean_le hm hfb
  have h2 : |tapeMean g m| ≤ Bg := abs_tapeMean_le hm hgb
  rw [marginalProduct, abs_mul]
  exact mul_le_mul h1 h2 (abs_nonneg _) hBf0

/-- The L13 contraction implication: if the recorded decay law holds
for the joint pairing at every lag, then the stated distance between
the lag-`k` joint pairing and the product of the marginal means is at
most the recorded mixing coefficient at lag `k` plus the explicit
marginal-product allowance. The decay law is a hypothesis here, not a
derivation from sample autocorrelations. -/
theorem abs_pairGap_le_of_decayLaw
    {f g : ℕ → ℝ} {Bf Bg : ℝ} {m k : ℕ} (hm : 0 < m)
    (hfb : ∀ i, |f i| ≤ Bf) (hgb : ∀ i, |g i| ≤ Bg) {c ρ : ℝ}
    (hDecay : ∀ j, |jointMean f g m j| ≤ c * ρ ^ j) :
    pairGap f g m k ≤ c * ρ ^ k + Bf * Bg := by
  have hJ : |jointMean f g m k| ≤ c * ρ ^ k := hDecay k
  have hMP : |marginalProduct f g m| ≤ Bf * Bg :=
    abs_marginalProduct_le hm hfb hgb
  have htri : |jointMean f g m k - marginalProduct f g m|
      ≤ |jointMean f g m k| + |marginalProduct f g m| := abs_sub _ _
  unfold pairGap
  linarith

/-! ### C. Family-wide error is assumed, not derived -/

/-- Bonferroni on an explicitly assumed finite-sample test structure:
with per-test error at most `α / m` for each of `m` tests, the family
average error is at most `α`. The per-test bounds are hypotheses; the
family-wide claim follows only from them, never from mixing alone. -/
theorem bonferroni_of_assumed_per_test_bounds
    {m : ℕ} (hm : 0 < m) {err : Fin m → ℝ} {α : ℝ} (hα : 0 ≤ α)
    (hper : ∀ j, err j ≤ α / m) : (∑ j, err j) / m ≤ α := by
  have hr : (0:ℝ) < (m:ℝ) := by exact_mod_cast hm
  have hdm : α / (m:ℝ) ≤ α :=
    div_le_self hα (by exact_mod_cast (show (1:ℕ) ≤ m from by omega))
  rw [div_le_iff₀ hr, mul_comm α (m:ℝ)]
  calc ∑ j, err j ≤ ∑ _j : Fin m, α :=
        Finset.sum_le_sum (fun j _ => le_trans (hper j) hdm)
    _ = (m:ℝ) * α := by
        rw [Finset.sum_const, Finset.card_univ, Fintype.card_fin,
          nsmul_eq_mul]

end PerpChief.L13Mixing
