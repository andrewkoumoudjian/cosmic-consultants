/-
# W22 (#170): proofs of the S9 Pareto layer statements

Proves every `S9...` Prop defined in `Analog/ParetoLayers.lean` cleanly with
standard axioms only and no unproven placeholders or escape hatches.
-/
import Mathlib
import Analog.ParetoLayers
import Analog.AtlasProofs

namespace Analog.ParetoLayersProofs

open Analog.Semantics Analog.Atlas Analog.AtlasProofs Analog.ParetoLayers Finset

private theorem frontier_subset {σ : Type*} {n : ℕ}
    (S : Finset σ) (loss : σ → Fin n → ℝ) : frontier S loss ⊆ S := by
  classical
  exact Finset.filter_subset _ _

private theorem peelRem_succ_subset {σ : Type*} {n : ℕ}
    (S : Finset σ) (loss : σ → Fin n → ℝ) (k : ℕ) :
    peelRem S loss (k + 1) ⊆ peelRem S loss k := by
  classical
  exact Finset.sdiff_subset

private theorem peelRem_subset {σ : Type*} {n : ℕ}
    (S : Finset σ) (loss : σ → Fin n → ℝ) : ∀ k, peelRem S loss k ⊆ S
  | 0 => Subset.rfl
  | k + 1 => (peelRem_succ_subset S loss k).trans (peelRem_subset S loss k)

private theorem peelRem_mono {σ : Type*} {n : ℕ}
    (S : Finset σ) (loss : σ → Fin n → ℝ) {k₁ k₂ : ℕ} (h : k₁ ≤ k₂) :
    peelRem S loss k₂ ⊆ peelRem S loss k₁ := by
  obtain ⟨d, rfl⟩ := Nat.exists_eq_add_of_le h
  induction d with
  | zero => simp
  | succ d ih =>
    calc peelRem S loss (k₁ + (d + 1))
        = peelRem S loss ((k₁ + d) + 1) := by rw [add_assoc]
      _ ⊆ peelRem S loss (k₁ + d) := peelRem_succ_subset S loss (k₁ + d)
      _ ⊆ peelRem S loss k₁ := ih (Nat.le_add_right k₁ d)

private theorem peelLayer_subset_rem {σ : Type*} {n : ℕ}
    (S : Finset σ) (loss : σ → Fin n → ℝ) (k : ℕ) :
    peelLayer S loss k ⊆ peelRem S loss k :=
  frontier_subset _ _

private theorem peelLayer_subset {σ : Type*} {n : ℕ}
    (S : Finset σ) (loss : σ → Fin n → ℝ) (k : ℕ) :
    peelLayer S loss k ⊆ S :=
  (peelLayer_subset_rem S loss k).trans (peelRem_subset S loss k)

private theorem mem_peelLayer_iff {σ : Type*} {n : ℕ}
    (S : Finset σ) (loss : σ → Fin n → ℝ) (k : ℕ) {x : σ} :
    x ∈ peelLayer S loss k ↔
      x ∈ peelRem S loss k ∧ ∀ y ∈ peelRem S loss k, ¬ Dominates (loss y) (loss x) := by
  classical
  simp [peelLayer, ParetoLayers.frontier]

private theorem mem_peelLayer_not_mem_rem_succ {σ : Type*} {n : ℕ}
    (S : Finset σ) (loss : σ → Fin n → ℝ) (k : ℕ) {x : σ}
    (hx : x ∈ peelLayer S loss k) : x ∉ peelRem S loss (k + 1) := by
  classical
  simp only [peelRem, Finset.mem_sdiff]
  intro ⟨_, hnot⟩
  exact hnot hx

private theorem mem_peelLayer_disjoint {σ : Type*} {n : ℕ}
    (S : Finset σ) (loss : σ → Fin n → ℝ) {k₁ k₂ : ℕ} {x : σ}
    (hne : k₁ ≠ k₂) (hx₁ : x ∈ peelLayer S loss k₁) :
    x ∉ peelLayer S loss k₂ := by
  rcases lt_or_gt_of_ne hne with hlt | hlt
  · intro hx₂
    have hrem : x ∈ peelRem S loss (k₁ + 1) :=
      peelRem_mono S loss (Nat.succ_le_of_lt hlt) (peelLayer_subset_rem S loss k₂ hx₂)
    exact mem_peelLayer_not_mem_rem_succ S loss k₁ hx₁ hrem
  · intro hx₂
    have hrem : x ∈ peelRem S loss (k₂ + 1) :=
      peelRem_mono S loss (Nat.succ_le_of_lt hlt) (peelLayer_subset_rem S loss k₁ hx₁)
    exact mem_peelLayer_not_mem_rem_succ S loss k₂ hx₂ hrem

/-- **S9a**: every Pareto layer is pairwise incomparable. -/
theorem s9a_layer_incomparable {σ : Type*} {n : ℕ} :
    S9a_layer_incomparable (σ := σ) (n := n) := by
  intro S loss k x y hx hy
  have hy' := (mem_peelLayer_iff S loss k).mp hy
  exact hy'.2 x (peelLayer_subset_rem S loss k hx)

/-- **S9b**: strict dominance strictly lowers the dominator's layer index. -/
theorem s9b_dominates_strictly_later {σ : Type*} {n : ℕ} :
    S9b_dominates_strictly_later (σ := σ) (n := n) := by
  intro S loss kx ky x y hx hy hdom
  by_contra hle
  push Not at hle
  rcases eq_or_lt_of_le hle with rfl | hlt
  · exact s9a_layer_incomparable S loss kx hy hx hdom
  · have hy_rem : y ∈ peelRem S loss kx :=
      peelRem_mono S loss hlt.le (peelLayer_subset_rem S loss ky hy)
    have hx' := (mem_peelLayer_iff S loss kx).mp hx
    exact hx'.2 y hy_rem hdom

/-- **S9c**: identical loss vectors always belong to the exact same layer. -/
theorem s9c_equal_vectors_same_layer {σ : Type*} {n : ℕ} :
    S9c_equal_vectors_same_layer (σ := σ) (n := n) := by
  intro S loss kx ky x y hx hy heq
  classical
  have aux : ∀ {k₁ k₂ : ℕ} {a b : σ},
      a ∈ peelLayer S loss k₁ → b ∈ peelLayer S loss k₂ →
      loss a = loss b → k₁ < k₂ → False := by
    intro k₁ k₂ a b ha hb heq' hlt
    have hb_rem : b ∈ peelRem S loss (k₁ + 1) :=
      peelRem_mono S loss (Nat.succ_le_of_lt hlt) (peelLayer_subset_rem S loss k₂ hb)
    simp only [peelRem, Finset.mem_sdiff] at hb_rem
    have hb_not_front : b ∉ ParetoLayers.frontier (peelRem S loss k₁) loss := hb_rem.2
    simp only [ParetoLayers.frontier, Finset.mem_filter, not_and, not_forall, not_not] at hb_not_front
    obtain ⟨w, hw_rem, hw_dom⟩ := hb_not_front hb_rem.1
    rw [← heq'] at hw_dom
    exact ((mem_peelLayer_iff S loss k₁).mp ha).2 w hw_rem hw_dom
  rcases lt_trichotomy kx ky with hlt | rfl | hlt
  · exact False.elim (aux hx hy heq hlt)
  · rfl
  · exact False.elim (aux hy hx heq.symm hlt)

private theorem frontier_nonempty {σ : Type*} {n : ℕ}
    (T : Finset σ) (loss : σ → Fin n → ℝ) (hT : T.Nonempty) :
    (frontier T loss).Nonempty := by
  classical
  obtain ⟨a, ha⟩ := hT
  obtain ⟨y, hyfr, _⟩ := s2b_frontier_covers T loss a ha
  refine ⟨y, Finset.mem_filter.mpr ⟨hyfr.1, hyfr.2⟩⟩

private theorem peelRem_card_bound {σ : Type*} {n : ℕ}
    (S : Finset σ) (loss : σ → Fin n → ℝ) :
    ∀ k, (peelRem S loss k).Nonempty → (peelRem S loss k).card + k ≤ S.card := by
  intro k
  induction k with
  | zero => intro _; simp [peelRem]
  | succ k ih =>
    intro hne
    have hrem_k : (peelRem S loss k).Nonempty := by
      obtain ⟨z, hz⟩ := hne
      exact ⟨z, peelRem_succ_subset S loss k hz⟩
    obtain ⟨y, hy_front⟩ := frontier_nonempty (peelRem S loss k) loss hrem_k
    have hy_rem : y ∈ peelRem S loss k := frontier_subset _ _ hy_front
    have hy_not_succ : y ∉ peelRem S loss (k + 1) :=
      mem_peelLayer_not_mem_rem_succ S loss k hy_front
    have hlt_card : (peelRem S loss (k + 1)).card < (peelRem S loss k).card := by
      refine Finset.card_lt_card ⟨peelRem_succ_subset S loss k, ?_⟩
      intro hsub
      exact hy_not_succ (hsub hy_rem)
    have ihk := ih hrem_k
    omega

/-- **S9d**: every site in `S` belongs to a unique peeled layer `k < S.card`. -/
theorem s9d_layer_partition {σ : Type*} {n : ℕ} :
    S9d_layer_partition (σ := σ) (n := n) := by
  intro S loss x hx
  classical
  have hnot_card : x ∉ peelRem S loss S.card := by
    intro hmem
    have hbound := peelRem_card_bound S loss S.card ⟨x, hmem⟩
    have hpos : 0 < (peelRem S loss S.card).card := Finset.card_pos.mpr ⟨x, hmem⟩
    omega
  have hex : ∃ m, x ∉ peelRem S loss (m + 1) := ⟨S.card, by
    intro h
    exact hnot_card (peelRem_succ_subset S loss S.card h)⟩
  let k := Nat.find hex
  have hk_not : x ∉ peelRem S loss (k + 1) := Nat.find_spec hex
  have hk_in : x ∈ peelRem S loss k := by
    change x ∈ peelRem S loss (Nat.find hex)
    rcases Nat.eq_zero_or_pos (Nat.find hex) with hk0 | hkpos
    · rw [hk0]; exact hx
    · have hklt : Nat.find hex - 1 < Nat.find hex := Nat.sub_lt hkpos Nat.one_pos
      have hk_prev := Nat.find_min hex hklt
      push Not at hk_prev
      rwa [Nat.sub_add_cancel hkpos] at hk_prev
  have hk_layer : x ∈ peelLayer S loss k := by
    simp only [peelRem, Finset.mem_sdiff] at hk_not
    by_contra hnl
    exact hk_not ⟨hk_in, hnl⟩
  have hk_lt : k < S.card := by
    have hbound := peelRem_card_bound S loss k ⟨x, hk_in⟩
    have hpos : 0 < (peelRem S loss k).card := Finset.card_pos.mpr ⟨x, hk_in⟩
    omega
  refine ⟨k, ⟨hk_layer, hk_lt⟩, ?_⟩
  intro k' ⟨hk'layer, _⟩
  by_contra hne
  exact mem_peelLayer_disjoint S loss hne hk'layer hk_layer

/-- **S9e**: any site missing a scored dimension is excluded from every Pareto layer. -/
theorem s9e_unknown_excluded {σ : Type*} {n : ℕ} :
    S9e_unknown_excluded (σ := σ) (n := n) := by
  intro U obs loss x i hnone k hx
  classical
  have hx_comp : x ∈ comparableSites U obs := peelLayer_subset (comparableSites U obs) loss k hx
  simp only [comparableSites, Finset.mem_filter] at hx_comp
  have his : (obs x i).isSome = true := hx_comp.2 i
  simp [hnone] at his

/-- **S9f**: mutually incomparable trade-off vectors share layer 0 regardless of
any scalar scoring function. -/
theorem s9f_tradeoff_never_separated {n : ℕ} :
    S9f_tradeoff_never_separated (n := n) := by
  intro a b _score hna hnb
  classical
  refine ⟨(mem_peelLayer_iff ({a, b} : Finset (Fin n → ℝ)) id 0).mpr ?_,
          (mem_peelLayer_iff ({a, b} : Finset (Fin n → ℝ)) id 0).mpr ?_⟩
  · refine ⟨Finset.mem_insert_self a {b}, ?_⟩
    intro y hy
    rcases Finset.mem_insert.mp hy with rfl | hyb
    · exact not_dominates_self _
    · rw [Finset.mem_singleton.mp hyb]
      exact hnb
  · refine ⟨Finset.mem_insert_of_mem (Finset.mem_singleton_self b), ?_⟩
    intro y hy
    rcases Finset.mem_insert.mp hy with rfl | hyb
    · exact hna
    · rw [Finset.mem_singleton.mp hyb]
      exact not_dominates_self _

/-- **S9g**: 1-indexed peeled layer equals `1 + max` of dominating layers in `S`. -/
theorem s9g_dp_recurrence {σ : Type*} {n : ℕ} :
    S9g_dp_recurrence (σ := σ) (n := n) := by
  intro S loss x k hx
  classical
  let F := S.filter (fun w => Dominates (loss w) (loss x))
  let g : σ → ℕ := fun w =>
    if h : ∃ m, w ∈ peelLayer S loss m then Classical.choose h + 1 else 0
  have hsup_eq : F.sup g = k := by
    apply le_antisymm
    · refine Finset.sup_le ?_
      intro w hw
      have hwdom : Dominates (loss w) (loss x) := (Finset.mem_filter.mp hw).2
      simp only [g]
      split_ifs with hex'
      · have hch : w ∈ peelLayer S loss (Classical.choose hex') := Classical.choose_spec hex'
        have hlt : Classical.choose hex' < k :=
          s9b_dominates_strictly_later S loss hx hch hwdom
        omega
      · exact Nat.zero_le _
    · cases k with
      | zero => exact Nat.zero_le _
      | succ k' =>
        have hx_rem_succ : x ∈ peelRem S loss (k' + 1) := peelLayer_subset_rem S loss (k' + 1) hx
        simp only [peelRem, Finset.mem_sdiff] at hx_rem_succ
        have hx_rem : x ∈ peelRem S loss k' := hx_rem_succ.1
        have hx_not_front : x ∉ ParetoLayers.frontier (peelRem S loss k') loss := hx_rem_succ.2
        simp only [ParetoLayers.frontier, Finset.mem_filter, not_and, not_forall, not_not] at hx_not_front
        obtain ⟨w, hw_rem, hw_dom⟩ := hx_not_front hx_rem
        have hw_not_succ : w ∉ peelRem S loss (k' + 1) := by
          intro hw_succ
          exact ((mem_peelLayer_iff S loss (k' + 1)).mp hx).2 w hw_succ hw_dom
        have hw_layer : w ∈ peelLayer S loss k' := by
          simp only [peelRem, Finset.mem_sdiff] at hw_not_succ
          by_contra hnl
          exact hw_not_succ ⟨hw_rem, hnl⟩
        have hwS : w ∈ S := peelLayer_subset S loss k' hw_layer
        have hwF : w ∈ F := Finset.mem_filter.mpr ⟨hwS, hw_dom⟩
        have hle := Finset.le_sup (f := g) hwF
        simp only [g] at hle
        split_ifs at hle with hex'
        · have hchoose_eq : Classical.choose hex' = k' := by
            by_contra hne
            exact mem_peelLayer_disjoint S loss hne (Classical.choose_spec hex') hw_layer
          rw [hchoose_eq] at hle
          exact hle
        · exact absurd ⟨k', hw_layer⟩ hex'
  rw [hsup_eq]
  omega

end Analog.ParetoLayersProofs
