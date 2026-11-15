import Analog.Funnel
namespace Analog.FunnelProofs
open Analog.Funnel Finset
variable {δ μ σ : Type*}
theorem verdict_exhaust (v : Verdict) : v = .matched ↔ v ≠ .missed ∧ v ≠ .unknown := by
  cases v <;> simp
theorem s7a_match_iff : S7a_match_iff := by
  intro b v
  cases b <;> cases v <;> simp [verdict]
theorem window_matched_iff (months : Finset μ) (vm : μ → Verdict) :
    windowVerdict months vm = .matched ↔ months.Nonempty ∧ ∀ m ∈ months, vm m = .matched := by
  classical
  simp only [windowVerdict]
  split_ifs <;> simp_all [Finset.nonempty_iff_ne_empty, verdict_exhaust] <;> aesop
theorem s7e_window_matched : S7e_window_matched (μ := μ) := window_matched_iff
theorem s7e_window_missed : S7e_window_missed (μ := μ) := by
  intro months vm
  classical
  simp only [windowVerdict]
  split_ifs <;> simp_all
theorem trait_matched_iff (p : Plan δ μ) (val : σ → δ → μ → Option ℝ) (s : σ) (d : δ) :
    traitVerdict p val s d = .matched ↔ p.months.Nonempty ∧
      ∀ m ∈ p.months, ∃ b x, p.band d = some b ∧ val s d m = some x ∧ b.Contains x := by
  simp only [traitVerdict, window_matched_iff]
  constructor
  · rintro ⟨hn, h⟩
    exact ⟨hn, fun m hm => (s7a_match_iff _ _).mp (h m hm)⟩
  · rintro ⟨hn, h⟩
    exact ⟨hn, fun m hm => (s7a_match_iff _ _).mpr (h m hm)⟩
theorem s7b_unknown_not_match : S7b_unknown_not_match (δ := δ) (μ := μ) (σ := σ) := by
  intro p val s hs d hd
  obtain ⟨hne, hm⟩ := (trait_matched_iff p val s d).mp (hs d hd)
  obtain ⟨m, hmem⟩ := hne
  obtain ⟨b, x, hb, _, _⟩ := hm m hmem
  refine ⟨by simp [hb], ?_⟩
  intro m hmem
  obtain ⟨_, x, _, hx, _⟩ := hm m hmem
  simp [hx]
theorem s7c_tighten_band : S7c_tighten_band (δ := δ) (μ := μ) (σ := σ) := by
  intro p q val cells hmust hmonths ht s hs
  classical
  simp only [survivors, mem_filter] at hs ⊢
  refine ⟨hs.1, ?_⟩
  intro d hd
  obtain ⟨hne, hm⟩ := (trait_matched_iff q val s d).mp (hs.2 d (hmust ▸ hd))
  apply (trait_matched_iff p val s d).mpr
  refine ⟨hmonths ▸ hne, ?_⟩
  intro m hmem
  obtain ⟨b, x, hb, hx, hinside⟩ := hm m (hmonths ▸ hmem)
  have h := ht d
  cases hp : p.band d with
  | none => simp [hb, hp, Tighter] at h
  | some c =>
    refine ⟨c, x, rfl, hx, ?_⟩
    have hh : b.Within c := by simpa [hb, hp, Tighter] using h
    exact hh x hinside
theorem s7d_add_must : S7d_add_must (δ := δ) (μ := μ) (σ := σ) := by
  intro p q val cells hmust hband hmonths s hs
  classical
  simp only [survivors, mem_filter] at hs ⊢
  refine ⟨hs.1, ?_⟩
  intro d hd
  have h := hs.2 d (hmust hd)
  simpa [traitVerdict, hband, hmonths] using h
theorem s7f_class_allMatch_iff : S7f_class_allMatch_iff (δ := δ) (μ := μ) (σ := σ) := by
  intro p val s
  classical
  simp only [funnelClass, Survives]
  split_ifs <;> simp_all [verdict_exhaust] <;> aesop
theorem s7g_nice_never_filters : S7g_nice_never_filters (δ := δ) (μ := μ) (σ := σ) := by
  intro p q val s hmust hmonths hbands
  have heq : ∀ d ∈ p.must, traitVerdict q val s d = traitVerdict p val s d := by
    intro d hd
    simp [traitVerdict, hmonths, hbands d hd]
  simp only [Survives, hmust]
  constructor <;> intro h d hd
  · rw [← heq d hd]; exact h d hd
  · rw [heq d hd]; exact h d hd
theorem s7h_more_months : S7h_more_months (δ := δ) (μ := μ) (σ := σ) := by
  intro p q val cells hne hsub hmust hband s hs
  classical
  simp only [survivors, mem_filter] at hs ⊢
  refine ⟨hs.1, ?_⟩
  intro d hd
  obtain ⟨_, hm⟩ := (trait_matched_iff q val s d).mp (hs.2 d (hmust ▸ hd))
  apply (trait_matched_iff p val s d).mpr
  refine ⟨hne, ?_⟩
  intro m hmem
  simpa [hband] using hm m (hsub hmem)
theorem s7i_unknown_limit_kept {ι : Type*} : S7i_unknown_limit_kept (σ := σ) (ι := ι) := by
  intro lim cap v w s hw hp l hl x hx
  rcases hw l hl with heq | heq
  · exact hp l hl x (heq ▸ hx)
  · simp [heq] at hx
theorem s7z_empty_window : S7z_empty_window (δ := δ) (μ := μ) (σ := σ) := by
  intro p val s hempty hmust hs
  obtain ⟨d, hd⟩ := hmust
  have h := (trait_matched_iff p val s d).mp (hs d hd)
  simpa [hempty] using h.1
end Analog.FunnelProofs
