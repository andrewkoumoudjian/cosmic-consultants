/-
PORTED 2026-11-12 from owner prior work: causal observation windows (no lookahead)
Source: andrewkoumoudjian/perps-strategy @ 0f34759, lanes/chief/lean/PerpChief/C05Window.lean (toolchain v4.15.0).
Port changes ONLY: module path/import remap to Analog.Prior.* (+ Mathlib API renames if listed in docs/research/06). Namespaces, statements, proofs otherwise verbatim. Original file is frozen upstream; do not edit semantics here — supersede via new module + STATEMENTS.md.
-/
/- Parent freeze: C05. Finite causal observation-window components; no profitability or admission claim. -/
/-
C05 - OPTIMAL OBSERVATION WINDOWS / CAUSAL TIME WINDOWS.
FROZEN STATEMENTS (category C05).  Phase B: statements frozen before proof.

Reconstruction note: the Phase A worker returned only a summary
(`paperwave1/returns/C05_RETURN.md`); no Lean source survived in the ledger.
The definitions below are the parent-side reconstruction of that summary.
Every field is explicit; `inWindow` uses strict natural-number causality
(`i + offset < t`); means are guarded on a nonempty observed window; missing
bars are dropped, never imputed; `tau` and `burnIn` are supplied constants and
are never estimated in this module.

Correction recorded at freeze: the literal Phase A pairwise-spacing sentence
`at most L/tau + 1` is false at `tau = 0` (take `L = 2`, `S = {0, 1}`:
`S.card = 2` but `2 / 0 + 1 = 1`).  The frozen form carries the explicit
hypothesis `0 < tau`, i.e. a genuine dependence length.  The finite
counterexample is itself a frozen, proved theorem below.

No Vest return is aligned by this module. No statistic, no trading cell, no
profitability or admission claim.
-/
import Mathlib.Tactic

namespace PerpChief.C05Window

noncomputable section

open Finset

/-! ### Interface -/

/-- A trailing observation window at decision time `t`.

`len`    : nominal number of bars in the window.
`lag`    : extra lookback padding (staleness allowance) behind `len`.
`offset` : causality embargo; index `i` is usable at `t` only if `i + offset < t`.
`burnIn` : first decision time at which the gate is defined. -/
structure WindowSpec where
  len : ℕ
  lag : ℕ
  offset : ℕ
  burnIn : ℕ
  deriving DecidableEq, Repr

/-- Membership in the trailing window at decision time `t`.  The first
conjunct is the strict no-lookahead boundary: a bar `i` can only enter if it
is at least `offset + 1` bars old.  The second bounds the lookback. -/
def inWindow (w : WindowSpec) (t i : ℕ) : Prop :=
  i + w.offset < t ∧ t ≤ i + w.offset + w.len + w.lag

/-- All tape indices available at decision time `t`. -/
def tapeSet (t : ℕ) : Finset ℕ := range t

/-- Structural window: tape indices satisfying the causal window predicate. -/
def windowSet (w : WindowSpec) (t : ℕ) : Finset ℕ := by
  classical
  exact (tapeSet t).filter fun i => inWindow w t i

/-- Observation predicate. `obs i = true` means bar `i` is present. -/
def isObserved (obs : ℕ → Bool) (i : ℕ) : Prop := obs i = true

/-- Eligible tape: present bars among all indices before `t`. -/
def eligibleTape (obs : ℕ → Bool) (t : ℕ) : Finset ℕ := by
  classical
  exact (tapeSet t).filter fun i => isObserved obs i

/-- Observed window: present bars inside the causal window.  Missing bars are
dropped here; no value is ever imputed. -/
def windowObserved (obs : ℕ → Bool) (w : WindowSpec) (t : ℕ) : Finset ℕ := by
  classical
  exact (windowSet w t).filter fun i => isObserved obs i

@[simp] theorem mem_windowSet {w : WindowSpec} {t i : ℕ} :
    i ∈ windowSet w t ↔ i < t ∧ inWindow w t i := by
  simp [windowSet, tapeSet]

@[simp] theorem mem_eligibleTape {obs : ℕ → Bool} {t i : ℕ} :
    i ∈ eligibleTape obs t ↔ i < t ∧ isObserved obs i := by
  simp [eligibleTape, tapeSet]

@[simp] theorem mem_windowObserved {obs : ℕ → Bool} {w : WindowSpec} {t i : ℕ} :
    i ∈ windowObserved obs w t ↔ i < t ∧ inWindow w t i ∧ isObserved obs i := by
  classical
  rw [windowObserved, mem_filter, mem_windowSet, isObserved]
  tauto

/-- The values actually passed to a window statistic: present bars only.
Missing bars contribute nothing and no value is imputed. -/
def observedValues (obs : ℕ → Bool) (x : ℕ → ℝ) (w : WindowSpec) (t : ℕ) : List ℝ :=
  (windowObserved obs w t).val.toList.map x

/-- Every observed-list value comes from a present in-window bar, and conversely. -/
theorem mem_observedValues {obs : ℕ → Bool} {x : ℕ → ℝ} {w : WindowSpec} {t : ℕ} {v : ℝ} :
    v ∈ observedValues obs x w t ↔ ∃ i ∈ windowObserved obs w t, x i = v := by
  simp [observedValues]

/-- Guarded mean over a finite index set; returns `0` on the empty set, so all
statements that use it carry an explicit nonemptiness hypothesis. -/
def meanOn (x : ℕ → ℝ) (S : Finset ℕ) : ℝ :=
  (∑ i ∈ S, x i) / (S.card : ℝ)

/-- Mean of the observed values in the window at decision time `t`. -/
def windowMean (obs : ℕ → Bool) (x : ℕ → ℝ) (w : WindowSpec) (t : ℕ) : ℝ :=
  meanOn x (windowObserved obs w t)

/-- Mean of the eligible tape before `t`. -/
def tapeMean (obs : ℕ → Bool) (x : ℕ → ℝ) (t : ℕ) : ℝ :=
  meanOn x (eligibleTape obs t)

/-- Gate value: a function of the window statistic only, and `0` before
warm-up.  It reads no index outside `windowObserved`. -/
def gateValue (g : ℝ → ℝ) (obs : ℕ → Bool) (x : ℕ → ℝ) (w : WindowSpec) (t : ℕ) : ℝ :=
  if w.burnIn ≤ t then g (windowMean obs x w t) else 0

/-- Clip to the interval `[-M, M]`. -/
def clip (M v : ℝ) : ℝ := max (-M) (min M v)

/-- Mean of clipped observed window values. -/
def clippedWindowMean (M : ℝ) (obs : ℕ → Bool) (x : ℕ → ℝ) (w : WindowSpec) (t : ℕ) : ℝ :=
  meanOn (fun i => clip M (x i)) (windowObserved obs w t)

/-- Pairwise spacing: any two distinct subjects of `S` are at least `tau`
bars apart.  Stated in increasing order to keep the arithmetic elementary. -/
def PairSpaced (tau : ℕ) (S : Finset ℕ) : Prop :=
  ∀ i ∈ S, ∀ j ∈ S, i < j → i + tau ≤ j

/-! ### Frozen goals -/

/-- The structural window is a subset of the tape. -/
theorem windowSet_subset_tapeSet (w : WindowSpec) (t : ℕ) :
    windowSet w t ⊆ tapeSet t := by
  intro i hi
  simpa [tapeSet] using (mem_windowSet.1 hi).1

/-- The observed window is a subset of the eligible tape. -/
theorem windowObserved_subset_eligibleTape (obs : ℕ → Bool) (w : WindowSpec) (t : ℕ) :
    windowObserved obs w t ⊆ eligibleTape obs t := by
  intro i hi
  rw [mem_eligibleTape]
  exact ⟨(mem_windowObserved.1 hi).1, (mem_windowObserved.1 hi).2.2⟩

/-- No lookahead: the window mean at `t` is determined by values on indices
strictly older than the embargo boundary `t - offset`. -/
theorem windowMean_causal (obs : ℕ → Bool) (x y : ℕ → ℝ) (w : WindowSpec) (t : ℕ)
    (h : ∀ i, i + w.offset < t → x i = y i) :
    windowMean obs x w t = windowMean obs y w t := by
  unfold windowMean meanOn
  congr 1
  apply sum_congr rfl
  intro i hi
  exact h i (mem_windowObserved.1 hi).2.1.1

/-- The gate reads only the causal window statistic. -/
theorem gateValue_causal (g : ℝ → ℝ) (obs : ℕ → Bool) (x y : ℕ → ℝ) (w : WindowSpec) (t : ℕ)
    (h : ∀ i, i + w.offset < t → x i = y i) :
    gateValue g obs x w t = gateValue g obs y w t := by
  unfold gateValue
  by_cases hb : w.burnIn ≤ t
  · rw [if_pos hb, if_pos hb, windowMean_causal obs x y w t h]
  · rw [if_neg hb, if_neg hb]

/-! ### Elementary Lipschitz and sum budgets -/

/-- `min c` is 1-Lipschitz. -/
theorem min_lipschitz (c a b : ℝ) : |min c a - min c b| ≤ |a - b| := by
  have h := abs_min_sub_min_le_max c a c b
  simpa using h

/-- Clipping to `[-M, M]` is 1-Lipschitz. -/
theorem clip_lipschitz (M a b : ℝ) : |clip M a - clip M b| ≤ |a - b| := by
  unfold clip
  calc |max (-M) (min M a) - max (-M) (min M b)|
      = |max (min M a) (-M) - max (min M b) (-M)| := by
        rw [max_comm (-M) (min M a), max_comm (-M) (min M b)]
    _ ≤ |min M a - min M b| := abs_max_sub_max_le_abs _ _ _
    _ ≤ |a - b| := min_lipschitz M a b

/-- A finite sum of values bounded in absolute value by `M`. -/
theorem finite_sum_bounded (S : Finset ℕ) (x : ℕ → ℝ) (M : ℝ)
    (h : ∀ i ∈ S, |x i| ≤ M) :
    |∑ i ∈ S, x i| ≤ (S.card : ℝ) * M := by
  calc |∑ i ∈ S, x i| ≤ ∑ i ∈ S, |x i| := abs_sum_le_sum_abs _ _
    _ ≤ ∑ i ∈ S, M := sum_le_sum h
    _ = (S.card : ℝ) * M := by simp [sum_const, nsmul_eq_mul]

/-- Guarded mean is bounded by the pointwise bound. -/
theorem abs_meanOn_le (S : Finset ℕ) (x : ℕ → ℝ) (M : ℝ)
    (hS : S.Nonempty) (h : ∀ i ∈ S, |x i| ≤ M) :
    |meanOn x S| ≤ M := by
  have hk : 0 < S.card := card_pos.2 hS
  have hkR : (0 : ℝ) < (S.card : ℝ) := by exact_mod_cast hk
  rw [meanOn, abs_div, abs_of_pos hkR, div_le_iff₀ hkR]
  calc |∑ i ∈ S, x i| ≤ (S.card : ℝ) * M := finite_sum_bounded S x M h
    _ = M * (S.card : ℝ) := by ring

/-- Difference of two guarded means over the same set. -/
theorem mean_noise_budget (S : Finset ℕ) (x y : ℕ → ℝ) (d : ℝ)
    (hS : S.Nonempty) (h : ∀ i ∈ S, |x i - y i| ≤ d) :
    |meanOn x S - meanOn y S| ≤ d := by
  have hk : 0 < S.card := card_pos.2 hS
  have hkR : (0 : ℝ) < (S.card : ℝ) := by exact_mod_cast hk
  rw [meanOn, meanOn, ← sub_div, abs_div, abs_of_pos hkR, div_le_iff₀ hkR]
  calc |(∑ i ∈ S, x i) - (∑ i ∈ S, y i)|
      = |∑ i ∈ S, (x i - y i)| := by rw [sum_sub_distrib]
    _ ≤ ∑ i ∈ S, |x i - y i| := abs_sum_le_sum_abs _ _
    _ ≤ ∑ i ∈ S, d := sum_le_sum h
    _ = d * (S.card : ℝ) := by simp [sum_const, nsmul_eq_mul, mul_comm]

/-! ### Headline 1: drift budget -/

/-- A trailing mean over `W ⊆ E` and the full eligible-tape mean over `E`
differ by at most `2 M (1 - |W|/|E|)` when every eligible value is bounded by
`M` in absolute value.  This is the exact mixture identity: the full tape is
the `|W|/|E|` mixture of the window and its complement. -/
theorem mean_drift_budget (E W : Finset ℕ) (x : ℕ → ℝ) (M : ℝ)
    (hWE : W ⊆ E) (hW : W.Nonempty) (hM : 0 ≤ M)
    (hx : ∀ i ∈ E, |x i| ≤ M) :
    |meanOn x W - meanOn x E| ≤ 2 * M * (1 - (W.card : ℝ) / (E.card : ℝ)) := by
  have _hM : 0 ≤ 2 * M := by linarith
  have hk : 0 < W.card := card_pos.2 hW
  have hN : 0 < E.card := lt_of_lt_of_le hk (card_le_card hWE)
  have hkle : W.card ≤ E.card := card_le_card hWE
  have hkR : (0 : ℝ) < (W.card : ℝ) := by exact_mod_cast hk
  have hNR : (0 : ℝ) < (E.card : ℝ) := by exact_mod_cast hN
  have hkne : (W.card : ℝ) ≠ 0 := ne_of_gt hkR
  have hNne : (E.card : ℝ) ≠ 0 := ne_of_gt hNR
  have hcast : (((E.card - W.card : ℕ)) : ℝ) = (E.card : ℝ) - (W.card : ℝ) :=
    Nat.cast_sub hkle
  have hsum : (∑ i ∈ E \ W, x i) + (∑ i ∈ W, x i) = ∑ i ∈ E, x i := Finset.sum_sdiff hWE
  have hcard : (E \ W).card = E.card - W.card := Finset.card_sdiff_of_subset hWE
  have hkwm : (W.card : ℝ) * ((∑ i ∈ W, x i) / (W.card : ℝ)) = ∑ i ∈ W, x i := by
    field_simp
  have hmain : (E.card : ℝ) * (meanOn x W - meanOn x E)
      = ∑ i ∈ E \ W, (meanOn x W - x i) := by
    rw [meanOn, meanOn]
    rw [← hsum]
    rw [← hkwm]
    rw [sum_sub_distrib]
    rw [sum_const, nsmul_eq_mul, hcard, hcast]
    field_simp
    ring
  have hbounded : |∑ i ∈ E \ W, (meanOn x W - x i)| ≤
      ((E.card : ℝ) - (W.card : ℝ)) * (2 * M) := by
    have hwm : |meanOn x W| ≤ M := abs_meanOn_le W x M hW (fun i hi => hx i (hWE hi))
    calc |∑ i ∈ E \ W, (meanOn x W - x i)|
        ≤ ∑ i ∈ E \ W, |meanOn x W - x i| := abs_sum_le_sum_abs _ _
      _ ≤ ∑ i ∈ E \ W, (2 * M) := by
          apply sum_le_sum
          intro i hi
          have hxi : |x i| ≤ M := hx i (mem_sdiff.1 hi).1
          calc |meanOn x W - x i| ≤ |meanOn x W| + |x i| := by
                have hh := abs_add_le (meanOn x W) (-(x i))
                rw [abs_neg] at hh
                have e : meanOn x W - x i = meanOn x W + -(x i) := sub_eq_add_neg _ _
                rw [e]; exact hh
            _ ≤ M + M := add_le_add hwm hxi
            _ = 2 * M := by ring
      _ = (((E \ W).card : ℝ)) * (2 * M) := by simp [sum_const, nsmul_eq_mul]
      _ = ((E.card : ℝ) - (W.card : ℝ)) * (2 * M) := by rw [hcard, hcast]
  have hstep : (E.card : ℝ) * |meanOn x W - meanOn x E| ≤
      ((E.card : ℝ) - (W.card : ℝ)) * (2 * M) := by
    calc (E.card : ℝ) * |meanOn x W - meanOn x E|
        = |(E.card : ℝ) * (meanOn x W - meanOn x E)| := by
          rw [abs_mul, abs_of_pos hNR]
      _ = |∑ i ∈ E \ W, (meanOn x W - x i)| := by rw [hmain]
      _ ≤ ((E.card : ℝ) - (W.card : ℝ)) * (2 * M) := hbounded
  have habs : |meanOn x W - meanOn x E| ≤
      (((E.card : ℝ) - (W.card : ℝ)) * (2 * M)) / (E.card : ℝ) := by
    rw [le_div_iff₀ hNR]
    calc |meanOn x W - meanOn x E| * (E.card : ℝ)
        = (E.card : ℝ) * |meanOn x W - meanOn x E| := by ring
      _ ≤ ((E.card : ℝ) - (W.card : ℝ)) * (2 * M) := hstep
  have hrhs : (((E.card : ℝ) - (W.card : ℝ)) * (2 * M)) / (E.card : ℝ)
      = 2 * M * (1 - (W.card : ℝ) / (E.card : ℝ)) := by
    field_simp
  rw [hrhs] at habs
  exact habs

/-- Headline 1, in tape form: the trailing observed-window mean drifts from the
full eligible-tape mean by at most `2 M (1 - k/N)` with `k` the observed window
count and `N` the eligible tape count. -/
theorem window_drift_budget (obs : ℕ → Bool) (x : ℕ → ℝ) (w : WindowSpec) (t : ℕ) (M : ℝ)
    (hM : 0 ≤ M)
    (hbound : ∀ i ∈ eligibleTape obs t, |x i| ≤ M)
    (hW : (windowObserved obs w t).Nonempty) :
    |windowMean obs x w t - tapeMean obs x t|
      ≤ 2 * M * (1 - ((windowObserved obs w t).card : ℝ) / ((eligibleTape obs t).card : ℝ)) := by
  simpa [windowMean, tapeMean] using
    mean_drift_budget (eligibleTape obs t) (windowObserved obs w t) x M
      (windowObserved_subset_eligibleTape obs w t) hW hM hbound

/-! ### Headline 2: clipping invariance and noise budget -/

/-- Headline 2a: the clipped window mean is invariant under any data change that
leaves every clipped in-window observed value unchanged. -/
theorem clippedWindowMean_invariance (M : ℝ) (obs : ℕ → Bool) (x y : ℕ → ℝ)
    (w : WindowSpec) (t : ℕ)
    (h : ∀ i ∈ windowObserved obs w t, clip M (x i) = clip M (y i)) :
    clippedWindowMean M obs x w t = clippedWindowMean M obs y w t := by
  unfold clippedWindowMean meanOn
  congr 1
  exact sum_congr rfl h

/-- Headline 2b: a per-bar perturbation of sup-norm `d` moves the clipped
window mean by at most `d`. -/
theorem clippedWindowMean_noise_budget (M : ℝ) (obs : ℕ → Bool) (x y : ℕ → ℝ)
    (w : WindowSpec) (t : ℕ) (d : ℝ)
    (hW : (windowObserved obs w t).Nonempty)
    (h : ∀ i ∈ windowObserved obs w t, |x i - y i| ≤ d) :
    |clippedWindowMean M obs x w t - clippedWindowMean M obs y w t| ≤ d := by
  have hclip : ∀ i ∈ windowObserved obs w t,
      |clip M (x i) - clip M (y i)| ≤ d := by
    intro i hi
    exact le_trans (clip_lipschitz M (x i) (y i)) (h i hi)
  simpa [clippedWindowMean] using
    mean_noise_budget (windowObserved obs w t) (fun i => clip M (x i))
      (fun i => clip M (y i)) d hW hclip

/-! ### Headline 3: pairwise-spaced subjects -/

/-- Division by `tau` is injective on a strictly increasing `tau`-spaced pair. -/
theorem div_ne_of_gap {tau i j : ℕ} (htau : 0 < tau) (hij : i < j) (hgap : i + tau ≤ j) :
    i / tau ≠ j / tau := by
  intro hdiv
  set a := tau * (i / tau) with ha
  set b := tau * (j / tau) with hb
  have hi : a + i % tau = i := by rw [ha]; exact Nat.div_add_mod i tau
  have hj : b + j % tau = j := by rw [hb]; exact Nat.div_add_mod j tau
  have hab : a = b := by rw [ha, hb, hdiv]
  have hmod : i % tau < j % tau := by omega
  have hjm : j % tau < tau := Nat.mod_lt j htau
  have hlt : j - i < tau := by omega
  omega

/-- Headline 3: a pairwise `tau`-spaced set of indices inside an `L`-bar tape
has at most `L / tau + 1` elements.  `tau` is a supplied dependence length; it
is never estimated here. -/
theorem pair_spaced_budget (L tau : ℕ) (S : Finset ℕ) (htau : 0 < tau)
    (hsub : S ⊆ range L) (hsp : PairSpaced tau S) :
    S.card ≤ L / tau + 1 := by
  have hinj : Set.InjOn (fun i : ℕ => i / tau) (↑S : Set ℕ) := by
    intro i hi j hj hdiv
    by_contra hne
    rcases Nat.lt_or_gt_of_ne hne with hlt | hgt
    · exact (div_ne_of_gap htau hlt (hsp i hi j hj hlt)) hdiv
    · exact (div_ne_of_gap htau hgt (hsp j hj i hi hgt)) hdiv.symm
  have hmem : ∀ i ∈ S, i / tau ∈ range (L / tau + 1) := by
    intro i hi
    have hiL : i < L := mem_range.1 (hsub hi)
    have h1 : i / tau ≤ (L - 1) / tau := Nat.div_le_div_right (by omega)
    have h2 : (L - 1) / tau ≤ L / tau := Nat.div_le_div_right (by omega)
    exact mem_range.2 (by omega)
  have hcard := card_le_card_of_injOn (fun i : ℕ => i / tau) hmem hinj
  simpa using hcard

/-- The literal Phase A form without `0 < tau` is false: on a two-bar tape the
set `{0, 1}` is `0`-spaced and has two elements, while `2 / 0 + 1 = 1`.  This
is the finite counterexample that forces the explicit `htau` hypothesis in the
frozen statement. -/
theorem pair_spaced_zero_tau_counterexample :
    ∃ (L : ℕ) (S : Finset ℕ),
      S ⊆ range L ∧ PairSpaced 0 S ∧ ¬ S.card ≤ L / 0 + 1 := by
  refine ⟨2, {0, 1}, ?_, ?_, ?_⟩
  · intro i hi
    simp at hi ⊢
    omega
  · intro i hi j hj hij
    simp at hi hj
    omega
  · norm_num

end
end PerpChief.C05Window
