/-
Axiom audit (ADR-0001 proof gate). Not part of the `Analog` library target;
run explicitly: `lake env lean Analog/Audit.lean` from `proofs/`.
Accepted output: only the standard axioms (propext, Classical.choice,
Quot.sound) — anything else, or `sorryAx`, fails the gate.
-/
import Analog

#print axioms Analog.Screening.relaxation_exact
#print axioms Analog.Screening.lower_model_exact
#print axioms Analog.Screening.cvar_screening_exact
#print axioms Analog.Screening.wr_screening_exact
#print axioms Analog.Certificate.subopt_le
#print axioms Analog.Semantics.not_dominates_self
#print axioms Analog.Semantics.dominates_trans
#print axioms Analog.Semantics.not_frontier_of_dominated
-- Ported prior work (Analog.Prior.*), representative theorems per module:
#print axioms PerpTheory.stdize_inv
#print axioms PerpTheory.chebyshev_finite
#print axioms PerpTheory.pit_uniform
#print axioms PerpTheory.finite_var_iff
#print axioms PerpChief.Math222SimplexCertV2.certificate_infeasible
#print axioms PerpChief.PaperWave1.verdicts_disjoint
#print axioms PerpChief.L13Mixing.bonferroni_of_assumed_per_test_bounds
#print axioms PerpChief.ACI.freq_bound
#print axioms PerpChief.BinaryInfo.tv_push_le
#print axioms PerpChief.C05Window.windowMean_causal
#print axioms PerpChief.JumpMarkov.hawkes_ge_mu
#print axioms PerpChief.PaperWave2.F096.selection_gain_bound
#print axioms PerpChief.O3.ClampStability.clamp_lipschitz
#print axioms PerpChief.O3.WeightError.weight_error
#print axioms PerpChief.Leverage.gstar_isMax
#print axioms PerpChief.Ceiling.cushion_growth_bound
#print axioms PerpChief.Events.vol_managed_gain
#print axioms PerpChief.Jumps.weissman
#print axioms PerpChief.TheoryModels1.paired_score_sum
