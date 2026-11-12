/-
PORTED 2026-11-12 from owner prior work: tail-index estimation gates
Source: andrewkoumoudjian/perps-strategy @ 0f34759, legacy/rounds1-2/lean/PerpTheory/Estimation.lean (toolchain v4.15.0).
Port changes ONLY: module path/import remap to Analog.Prior.* (+ Mathlib API renames if listed in docs/research/06). Namespaces, statements, proofs otherwise verbatim. Original file is frozen upstream; do not edit semantics here — supersede via new module + STATEMENTS.md.
-/
import Mathlib

/-!
# T6 — Estimation gates (STARTER) + openai/math 140 demotion

Paper 140 (memory/precision in *noiseless* Gaussian regression) is a
lower bound `T ≥ c_A d log(1/eps)` on bit-memory. It yields no
estimator, sample size or coverage rule for noisy dependent perp
returns, so it is NOT formalised as a trading theorem. Its residue is
accounting discipline: every estimate logs its `EstimatorState`.

The load-bearing gate: if a fitted Student-t has `nu ≤ 2`, variance
(and hence sigma) is undefined — the signal must be quantile-based.
Lean enforces the *type* of the signal; Python estimates `nu`.
-/

namespace PerpTheory

/-- Which language the signal may speak. -/
inductive SignalMode where
  | sigma     -- finite-variance reading licensed (nu > 2)
  | quantile  -- only quantiles / MAD-scale licensed (nu ≤ 2 or unknown)
  deriving DecidableEq, Repr

/-- Gate from fitted degrees of freedom. `nu = 0` encodes "not fitted". -/
noncomputable def modeOfNu (nu : ℝ) : SignalMode :=
  if nu > 2 then SignalMode.sigma else SignalMode.quantile

theorem modeOfNu_quantile_of_le_two (nu : ℝ) (h : nu ≤ 2) :
    modeOfNu nu = SignalMode.quantile := by
  unfold modeOfNu
  rw [if_neg (by linarith : ¬ nu > 2)]

theorem modeOfNu_sigma_of_gt_two (nu : ℝ) (h : nu > 2) :
    modeOfNu nu = SignalMode.sigma := by
  unfold modeOfNu
  rw [if_pos h]

/-- Estimator provenance that Python must log for every fitted value
(the formal residue of paper 140: name the retained state). -/
structure EstimatorState where
  scaleKind : String      -- e.g. "mad90d-deseason" or "ewma0.94"
  windowBars : ℕ
  nu : ℝ                  -- fitted Student-t df (0 = not fitted)
  xi : ℝ                  -- fitted GPD shape (0 = not fitted)
  seed : ℕ

/-- Tail-index convention (fixed once, programme-wide):
`alpha = 1 / xi` for `xi > 0`. The `1 + xi` convention in one legacy
file is a different number and must never be mixed in. -/
noncomputable def alphaOfXi (xi : ℝ) : ℝ := 1 / xi

example : alphaOfXi 0.5 = 2 := by unfold alphaOfXi; norm_num
example : alphaOfXi 0.25 = 4 := by unfold alphaOfXi; norm_num

/-- Finite-variance threshold in `xi` language: `alpha > 2 ↔ xi < 1/2`
(for `xi > 0`). -/
theorem finite_var_iff (xi : ℝ) (hx : 0 < xi) :
    alphaOfXi xi > 2 ↔ xi < 1 / 2 := by
  unfold alphaOfXi
  constructor
  · intro h
    rw [gt_iff_lt, lt_div_iff₀ hx] at h
    -- h : 2 * xi < 1
    linarith
  · intro h
    rw [gt_iff_lt, lt_div_iff₀ hx]
    linarith

end PerpTheory
