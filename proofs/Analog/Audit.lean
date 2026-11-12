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
