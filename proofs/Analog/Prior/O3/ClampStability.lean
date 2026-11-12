/-
PORTED 2026-11-12 from owner prior work: clamp Lipschitz/feasibility
Source: andrewkoumoudjian/perps-strategy @ 0f34759, lanes/chief/lean/PerpChief/O3/ClampStability.lean (toolchain v4.15.0).
Port changes ONLY: module path/import remap to Analog.Prior.* (+ Mathlib API renames if listed in docs/research/06). Namespaces, statements, proofs otherwise verbatim. Original file is frozen upstream; do not edit semantics here — supersede via new module + STATEMENTS.md.
-/
import Mathlib

namespace PerpChief.O3.ClampStability

open scoped BigOperators

def clamp (lo hi x : ℝ) : ℝ := min hi (max lo x)

theorem clamp_lipschitz (lo hi x y : ℝ) :
    |clamp lo hi x - clamp lo hi y| ≤ |x - y| := by
  unfold clamp
  calc
    |min hi (max lo x) - min hi (max lo y)|
        ≤ |max lo x - max lo y| := by
          simpa [min_comm] using
            (abs_min_sub_min_le_max (max lo x) hi (max lo y) hi)
    _ ≤ |x - y| := by
          simpa [max_comm] using (abs_max_sub_max_le_abs x y lo)

theorem clamp_feasible (lo hi x : ℝ) (h : lo ≤ hi) :
    lo ≤ clamp lo hi x ∧ clamp lo hi x ≤ hi := by
  constructor
  · exact le_min_iff.mpr ⟨h, le_max_left lo x⟩
  · exact min_le_left hi (max lo x)

end PerpChief.O3.ClampStability
