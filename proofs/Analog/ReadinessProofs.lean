/-
# W9 (#17): proofs of the frozen S6 (ARL semantics) statements

Proves exactly the 15 Props frozen in `Analog/Readiness.lean` (statement ID
"S6"; owner-approved wording, PR #48, frozen at `28b166a`). The frozen
statement file is imported, never edited. A semantics change must supersede it
under a new statement ID (STATEMENTS.md rule).

Proof idea in plain words: both `arl` and `dimLevel` are `Nat.findGreatest` of a
"gates 1..k all pass" predicate, which is true at 0 and closed downward. So
`k ≤ level ↔ gates 1..k pass`. For `k ≤ 4` and a nonempty required set, "gates
1..k pass" splits into "each required dimension passes its own gates 1..k".
Every S6 statement follows from these two facts.
-/
import Mathlib
import Analog.Readiness

namespace Analog.ReadinessProofs

open Analog.Readiness Analog.Semantics Finset

variable {δ : Type*}

/-! ### Generic facts about cumulative ladders -/

private theorem upTo_mono {P : ℕ → Bool} {k m : ℕ} (hkm : k ≤ m)
    (h : ∀ j ∈ Icc 1 m, P j = true) : ∀ j ∈ Icc 1 k, P j = true := by
  intro j hj
  simp only [mem_Icc] at hj
  exact h j (by simp only [mem_Icc]; omega)

private theorem upTo_succ {P : ℕ → Bool} {k : ℕ}
    (h : ∀ j ∈ Icc 1 k, P j = true) (hk : P (k + 1) = true) :
    ∀ j ∈ Icc 1 (k + 1), P j = true := by
  intro j hj
  simp only [mem_Icc] at hj
  rcases Nat.lt_or_ge j (k + 1) with hlt | hge
  · exact h j (by simp only [mem_Icc]; omega)
  · have : j = k + 1 := by omega
    subst this; exact hk

/-- `Nat.findGreatest` over a downward-closed predicate true at 0:
`k ≤ level ↔ Q k`. -/
private theorem le_findGreatest_iff {Q : ℕ → Prop} [DecidablePred Q] {n k : ℕ}
    (h0 : Q 0) (hdown : ∀ a b, a ≤ b → Q b → Q a) (hk : k ≤ n) :
    k ≤ Nat.findGreatest Q n ↔ Q k := by
  constructor
  · intro hle
    exact hdown _ _ hle (Nat.findGreatest_spec (Nat.zero_le n) h0)
  · intro h
    exact Nat.le_findGreatest hk h

private theorem arl_le_iff (o : Objective δ) (e : Evidence δ) {k : ℕ} (hk : k ≤ 6) :
    k ≤ arl o e ↔ GatesUpTo o e k :=
  le_findGreatest_iff (Q := GatesUpTo o e)
    (by intro j hj; simp only [mem_Icc] at hj; omega)
    (fun _ _ hab h => upTo_mono hab h) hk

private theorem arl_le_six (o : Objective δ) (e : Evidence δ) : arl o e ≤ 6 :=
  Nat.findGreatest_le 6

private theorem dimLevel_le_iff (e : Evidence δ) (d : δ) {k : ℕ} (hk : k ≤ 4) :
    k ≤ dimLevel e d ↔ DimUpTo e d k :=
  le_findGreatest_iff (Q := DimUpTo e d)
    (by intro j hj; simp only [mem_Icc] at hj; omega)
    (fun _ _ hab h => upTo_mono hab h) hk

private theorem dimLevel_le_four (e : Evidence δ) (d : δ) : dimLevel e d ≤ 4 :=
  Nat.findGreatest_le 4

/-- Gates 1..4 are the per-dimension gates: gate `j ≤ 4` passes iff the
required set is nonempty and every required dimension passes its own gate `j`. -/
private theorem gatePass_dim (o : Objective δ) (e : Evidence δ) {j : ℕ}
    (hj1 : 1 ≤ j) (hj4 : j ≤ 4) :
    gatePass o e j = true ↔
      o.required.Nonempty ∧ ∀ d ∈ o.required, dimGatePass e d j = true := by
  interval_cases j <;> simp [gatePass, dimPass, dimGatePass]

/-- For `k ≤ 4`: gates 1..k pass iff required is nonempty and every required
dimension has its own gates 1..k passing. -/
private theorem gatesUpTo_dim (o : Objective δ) (e : Evidence δ) {k : ℕ}
    (hk : k ≤ 4) (hne : o.required.Nonempty) :
    GatesUpTo o e k ↔ ∀ d ∈ o.required, DimUpTo e d k := by
  unfold GatesUpTo DimUpTo
  constructor
  · intro h d hd j hj
    have hj' := hj; simp only [mem_Icc] at hj'
    exact ((gatePass_dim o e hj'.1 (by omega)).1 (h j hj)).2 d hd
  · intro h j hj
    have hj' := hj; simp only [mem_Icc] at hj'
    exact (gatePass_dim o e hj'.1 (by omega)).2 ⟨hne, fun d hd => h d hd j hj⟩

private theorem gate_one_needs_nonempty (o : Objective δ) (e : Evidence δ)
    (h : gatePass o e 1 = true) : o.required.Nonempty := by
  simp [gatePass, dimPass] at h
  exact h.1

/-- ARL ≥ 1 forces a nonempty required set. -/
private theorem arl_pos_nonempty (o : Objective δ) (e : Evidence δ)
    (h : 1 ≤ arl o e) : o.required.Nonempty := by
  have := (arl_le_iff o e (by norm_num)).1 h
  exact gate_one_needs_nonempty o e (this 1 (by simp))

/-- Key bridge: for `k ≤ 4`, `k ≤ arl ↔ every required dimension has level ≥ k`
(with a nonempty required set). -/
private theorem le_arl_iff_dims (o : Objective δ) (e : Evidence δ) {k : ℕ}
    (hk : k ≤ 4) (hne : o.required.Nonempty) :
    k ≤ arl o e ↔ ∀ d ∈ o.required, k ≤ dimLevel e d := by
  rw [arl_le_iff o e (by omega), gatesUpTo_dim o e hk hne]
  exact forall₂_congr fun d _ => (dimLevel_le_iff e d hk).symm

/-! ### S6 theorems -/

theorem s6a_weakest_link : S6a_weakest_link (δ := δ) := by
  intro o e h
  apply le_antisymm
  · rw [Finset.le_inf'_iff]
    intro d hd
    exact (le_arl_iff_dims o e (min_le_right _ _) h).1 (min_le_left _ _) d hd
  · have hinf : o.required.inf' h (dimLevel e) ≤ 4 := by
      obtain ⟨d, hd⟩ := h
      exact (Finset.inf'_le _ hd).trans (dimLevel_le_four e d)
    refine le_min ?_ hinf
    exact (le_arl_iff_dims o e hinf h).2 fun d hd => Finset.inf'_le _ hd

theorem s6b_monotone : S6b_monotone (δ := δ) := by
  intro o e e' h
  have hle := (arl_le_iff o e (arl_le_six o e)).1 le_rfl
  exact (arl_le_iff o e' (arl_le_six o e)).2 fun j hj => h j (hle j hj)

private theorem gatePass_mono_outcomes (o : Objective δ) (e e' : Evidence δ)
    (hd : ∀ d g, e.dim d g = .pass → e'.dim d g = .pass)
    (hs : ∀ g, e.site g = .pass → e'.site g = .pass) (k : ℕ) :
    gatePass o e k = true → gatePass o e' k = true := by
  rcases k with _ | _ | _ | _ | _ | _ | _ | k <;>
    simp only [gatePass, dimPass, sitePass, Bool.and_eq_true, decide_eq_true_eq] <;>
    first
    | (intro h; exact h)
    | (rintro ⟨hne, hall⟩; exact ⟨hne, fun d hdm => hd _ _ (hall d hdm)⟩)
    | (intro h; exact hs _ h)

theorem s6b_monotone_outcomes : S6b_monotone_outcomes (δ := δ) := by
  intro o e e' hd hs
  exact s6b_monotone o e e' (gatePass_mono_outcomes o e e' hd hs)

private theorem dimLevel_congr (e e' : Evidence δ) (d : δ) (h : e'.dim d = e.dim d) :
    dimLevel e' d = dimLevel e d := by
  unfold dimLevel DimUpTo
  congr 1
  funext k
  apply propext
  apply forall₂_congr
  intro j _
  rcases j with _ | _ | _ | _ | _ | j <;> simp [dimGatePass, h]

theorem s6c_no_compensation : S6c_no_compensation (δ := δ) := by
  intro o e e' d₀ hsame d hd hne
  rw [← dimLevel_congr e e' d (hsame d hne)]
  have hne' : o.required.Nonempty := ⟨d, hd⟩
  exact (le_arl_iff_dims o e' (min_le_right _ _) hne').1 (min_le_left _ _) d hd

theorem s6h_site_no_lift : S6h_site_no_lift (δ := δ) := by
  intro o e d hd hlt
  by_contra hgt
  rw [not_le] at hgt
  have hk : dimLevel e d + 1 ≤ 4 := hlt
  have := (le_arl_iff_dims o e hk ⟨d, hd⟩).1 hgt d hd
  omega

theorem s6d_nonpass_blocks : S6d_nonpass_blocks (δ := δ) := by
  intro o e g d hd hnp
  by_contra hge
  rw [not_lt] at hge
  have hlev : g.level ≤ 4 := by cases g <;> simp [DimGate.level]
  have := (le_arl_iff_dims o e hlev ⟨d, hd⟩).1 hge d hd
  have hdim := (dimLevel_le_iff e d hlev).1 this
  have h1 : 1 ≤ g.level := by cases g <;> simp [DimGate.level]
  have := hdim g.level (by simp [mem_Icc, h1])
  cases g <;> simp_all [DimGate.level, dimGatePass]

theorem s6d_unobserved_zero : S6d_unobserved_zero (δ := δ) := by
  rintro o e ⟨d, hd, hnp⟩
  have := s6d_nonpass_blocks o e .observed d hd hnp
  simp [DimGate.level] at this
  exact this

theorem s6d_observed_fail_one : S6d_observed_fail_one (δ := δ) := by
  rintro o e hne hobs ⟨d, hd, hfail⟩
  apply le_antisymm
  · have := s6d_nonpass_blocks o e .withinTolerance d hd (by rw [hfail]; decide)
    simpa [DimGate.level] using this
  · rw [le_arl_iff_dims o e (by norm_num) hne]
    intro d' hd'
    rw [dimLevel_le_iff e d' (by norm_num)]
    intro j hj
    simp only [mem_Icc] at hj
    have : j = 1 := by omega
    subst this
    simp [dimGatePass, hobs d' hd']

theorem s6e_cumulative : S6e_cumulative (δ := δ) := by
  intro o e k hk
  exact (arl_le_iff o e (hk.trans (arl_le_six o e))).1 hk

theorem s6e_maximal : S6e_maximal (δ := δ) := by
  intro o e
  refine ⟨arl_le_six o e, fun hlt => ?_⟩
  by_contra hpass
  rw [Bool.not_eq_false] at hpass
  have hup := (arl_le_iff o e (arl_le_six o e)).1 le_rfl
  have := (arl_le_iff o e (show arl o e + 1 ≤ 6 by omega)).2 (upTo_succ hup hpass)
  omega

theorem s6f_mismatch_irrelevant : S6f_mismatch_irrelevant (δ := δ) := by
  intro o o' e h
  have hg : ∀ j, gatePass o e j = gatePass o' e j := by
    intro j
    rcases j with _ | _ | _ | _ | _ | _ | _ | j <;> simp [gatePass, dimPass, h]
  unfold arl GatesUpTo
  simp only [hg]

theorem s6f_required_only : S6f_required_only (δ := δ) := by
  intro o e e' hdim hsite
  have hg : ∀ j, gatePass o e' j = gatePass o e j := by
    intro j
    have hall : ∀ g, (∀ d ∈ o.required, e'.dim d g = .pass) ↔
        (∀ d ∈ o.required, e.dim d g = .pass) := fun g =>
      forall₂_congr fun d hd => by rw [hdim d hd]
    rcases j with _ | _ | _ | _ | _ | _ | _ | j <;>
      simp [gatePass, dimPass, sitePass, hsite, hall]
  unfold arl GatesUpTo
  simp only [hg]

theorem s6g_not_rateable : S6g_not_rateable (δ := δ) := by
  intro o e h
  simp [rating, h]

theorem s6z_empty_required : S6z_empty_required (δ := δ) := by
  intro o e h
  by_contra hne
  have hpos : 1 ≤ arl o e := Nat.one_le_iff_ne_zero.2 hne
  have := arl_pos_nonempty o e hpos
  rw [h] at this
  exact Finset.not_nonempty_empty this

theorem s6u_all_unknown : S6u_all_unknown (δ := δ) := by
  intro o e h
  rcases o.required.eq_empty_or_nonempty with hemp | ⟨d, hd⟩
  · exact s6z_empty_required o e hemp
  · exact s6d_unobserved_zero o e ⟨d, hd, by rw [h]; decide⟩

end Analog.ReadinessProofs
