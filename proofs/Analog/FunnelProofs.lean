/-
# W21 (#80): proofs of the S7 (funnel and verdict) statements

Proves exactly the 11 Props in `Analog/Funnel.lean` (statement ID "S7",
PR #84). The statement file is imported, never edited. These proofs are
accepted only after the owner freezes #84; until then they show that every
statement as written is provable (no statement had to change).

Proof idea in plain words: a verdict is `matched` only for a known value inside
a known band (S7a). Over a window, `matched` means at least one month and every
month `matched` (S7e). Survival is "every must trait matched", so anything that
can only turn `matched` into something else (a tighter band, more must traits,
more months) can only remove sites, and anything that doesn't touch the must
traits changes nothing.
-/
import Mathlib
import Analog.Funnel

namespace Analog.FunnelProofs

open Analog.Funnel Finset

variable {δ μ σ ι : Type*}

/-! ### Basic facts -/

private theorem verdict_matched_iff (b : Option Band) (v : Option ℝ) :
    verdict b v = .matched ↔ ∃ b' x, b = some b' ∧ v = some x ∧ b'.Contains x := by
  cases b with
  | none => cases v <;> simp [verdict]
  | some b =>
    cases v with
    | none => simp [verdict]
    | some x => by_cases h : b.Contains x <;> simp [verdict, h]

private theorem window_matched_iff (months : Finset μ) (vm : μ → Verdict) :
    windowVerdict months vm = .matched ↔ months.Nonempty ∧ ∀ m ∈ months, vm m = .matched := by
  unfold windowVerdict
  split_ifs with h1 h2
  · constructor
    · intro h; exact absurd h (by decide)
    · rintro ⟨_, hall⟩
      obtain ⟨m, hm, hv⟩ := h1
      rw [hall m hm] at hv; exact absurd hv (by decide)
  · constructor
    · intro h; exact absurd h (by decide)
    · rintro ⟨hne, hall⟩
      rcases h2 with h2 | ⟨m, hm, hv⟩
      · rw [h2] at hne; exact absurd hne Finset.not_nonempty_empty
      · rw [hall m hm] at hv; exact absurd hv (by decide)
  · refine ⟨fun _ => ?_, fun _ => rfl⟩
    have hne : months ≠ ∅ := fun h => h2 (Or.inl h)
    refine ⟨Finset.nonempty_iff_ne_empty.mpr hne, fun m hm => ?_⟩
    cases hv : vm m
    · rfl
    · exact absurd ⟨m, hm, hv⟩ h1
    · exact absurd (Or.inr ⟨m, hm, hv⟩) h2

private theorem window_missed_iff (months : Finset μ) (vm : μ → Verdict) :
    windowVerdict months vm = .missed ↔ ∃ m ∈ months, vm m = .missed := by
  unfold windowVerdict
  split_ifs with h1 h2
  · exact ⟨fun _ => h1, fun _ => rfl⟩
  · exact ⟨fun h => absurd h (by decide), fun h => absurd h h1⟩
  · exact ⟨fun h => absurd h (by decide), fun h => absurd h h1⟩

/-- A trait is matched at a site iff the window is non-empty and every
requested month's verdict is matched. -/
private theorem trait_matched_iff (p : Plan δ μ) (val : σ → δ → μ → Option ℝ) (s : σ) (d : δ) :
    traitVerdict p val s d = .matched ↔
      p.months.Nonempty ∧ ∀ m ∈ p.months, verdict (p.band d) (val s d m) = .matched :=
  window_matched_iff _ _

private theorem traitVerdict_congr (p p' : Plan δ μ) (val : σ → δ → μ → Option ℝ) (s : σ) (d : δ)
    (hm : p'.months = p.months) (hb : p'.band d = p.band d) :
    traitVerdict p' val s d = traitVerdict p val s d := by
  unfold traitVerdict; rw [hm, hb]

private theorem verdict_tighter {b b' : Option Band} {v : Option ℝ} (ht : Tighter b' b)
    (h : verdict b' v = .matched) : verdict b v = .matched := by
  obtain ⟨x, y, rfl, rfl, hc⟩ := (verdict_matched_iff _ _).mp h
  cases b with
  | none => exact absurd ht (by simp [Tighter])
  | some z => exact (verdict_matched_iff _ _).mpr ⟨z, y, rfl, rfl, ht y hc⟩

private theorem mem_survivors (p : Plan δ μ) (val : σ → δ → μ → Option ℝ) (cells : Finset σ) (s : σ) :
    s ∈ survivors p val cells ↔ s ∈ cells ∧ Survives p val s := by
  classical
  unfold survivors; exact Finset.mem_filter

/-! ### S7 -/

theorem s7a_match_iff : S7a_match_iff := verdict_matched_iff

theorem s7b_unknown_not_match : S7b_unknown_not_match (δ := δ) (μ := μ) (σ := σ) := by
  intro p val s hs d hd
  obtain ⟨⟨m₀, hm₀⟩, hall⟩ := (trait_matched_iff p val s d).mp (hs d hd)
  obtain ⟨b', x, hb, -, -⟩ := (verdict_matched_iff _ _).mp (hall m₀ hm₀)
  refine ⟨by rw [hb]; exact Option.some_ne_none b', fun m hm => ?_⟩
  obtain ⟨-, y, -, hy, -⟩ := (verdict_matched_iff _ _).mp (hall m hm)
  rw [hy]; exact Option.some_ne_none y

theorem s7c_tighten_band : S7c_tighten_band (δ := δ) (μ := μ) (σ := σ) := by
  intro p p' val cells hmust hmonths hband s hs
  rw [mem_survivors] at hs ⊢
  refine ⟨hs.1, fun d hd => ?_⟩
  obtain ⟨hne, hall⟩ := (trait_matched_iff p' val s d).mp (hs.2 d (hmust ▸ hd))
  rw [hmonths] at hne hall
  exact (trait_matched_iff p val s d).mpr ⟨hne, fun m hm => verdict_tighter (hband d) (hall m hm)⟩

theorem s7d_add_must : S7d_add_must (δ := δ) (μ := μ) (σ := σ) := by
  intro p p' val cells hsub hband hmonths s hs
  rw [mem_survivors] at hs ⊢
  refine ⟨hs.1, fun d hd => ?_⟩
  rw [← traitVerdict_congr p p' val s d hmonths (by rw [hband])]
  exact hs.2 d (hsub hd)

theorem s7e_window_matched : S7e_window_matched (μ := μ) := window_matched_iff

theorem s7e_window_missed : S7e_window_missed (μ := μ) := window_missed_iff

theorem s7f_class_allMatch_iff : S7f_class_allMatch_iff (δ := δ) (μ := μ) (σ := σ) := by
  intro p val s
  unfold funnelClass Survives
  split_ifs with h1 h2
  · refine ⟨fun h => absurd h (by decide), fun h => ?_⟩
    obtain ⟨d, hd, hv⟩ := h1
    have := h d hd; rw [hv] at this; exact absurd this (by decide)
  · refine ⟨fun h => absurd h (by decide), fun h => ?_⟩
    obtain ⟨d, hd, hv⟩ := h2
    have := h d hd; rw [hv] at this; exact absurd this (by decide)
  · refine ⟨fun _ d hd => ?_, fun _ => rfl⟩
    cases hv : traitVerdict p val s d
    · rfl
    · exact absurd ⟨d, hd, hv⟩ h1
    · exact absurd ⟨d, hd, hv⟩ h2

theorem s7g_nice_never_filters : S7g_nice_never_filters (δ := δ) (μ := μ) (σ := σ) := by
  intro p p' val s hmust hmonths hband
  unfold Survives
  rw [hmust]
  constructor
  · intro h d hd; rw [← traitVerdict_congr p p' val s d hmonths (hband d hd)]; exact h d hd
  · intro h d hd; rw [traitVerdict_congr p p' val s d hmonths (hband d hd)]; exact h d hd

theorem s7h_more_months : S7h_more_months (δ := δ) (μ := μ) (σ := σ) := by
  intro p p' val cells hne hsub hmust hband s hs
  rw [mem_survivors] at hs ⊢
  refine ⟨hs.1, fun d hd => ?_⟩
  obtain ⟨-, hall⟩ := (trait_matched_iff p' val s d).mp (hs.2 d (hmust ▸ hd))
  refine (trait_matched_iff p val s d).mpr ⟨hne, fun m hm => ?_⟩
  have := hall m (hsub hm)
  rwa [hband] at this

theorem s7i_unknown_limit_kept : S7i_unknown_limit_kept (σ := σ) (ι := ι) := by
  intro lim cap lval lval' s hsame hpass l hl x hx
  rcases hsame l hl with h | h
  · rw [h] at hx; exact hpass l hl x hx
  · rw [h] at hx; exact absurd hx (by simp)

theorem s7z_empty_window : S7z_empty_window (δ := δ) (μ := μ) (σ := σ) := by
  intro p val s hempty ⟨d, hd⟩ hs
  obtain ⟨hne, -⟩ := (trait_matched_iff p val s d).mp (hs d hd)
  rw [hempty] at hne
  exact Finset.not_nonempty_empty hne

end Analog.FunnelProofs
