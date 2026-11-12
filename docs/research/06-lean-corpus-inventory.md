# 06 — Owner's Lean corpus: inventory and port dispositions

Date: 2026-11-12. Owner request: add every Lean proof of theirs that might be
useful for the analog problem. Sources searched: GitHub code search over
`andrewkoumoudjian` (283 `.lean` hits), `QUARCC-Umbrella` (3 — the `fastopt`
files), `noviavervillestreet` (0), plus local checkouts under `/home/drew`
(only duplicates/worktrees of the same two repos). The corpus of record:
`andrewkoumoudjian/perps-strategy` @ `0f34759` — **304 `.lean` files on disk**,
toolchain `leanprover/lean4:v4.15.0`; ~153 files mention `sorry`/`admit`
(includes header-comment false positives of the form "Fill in `sorry`…" in
otherwise clean FROZEN modules).

Port target: `proofs/Analog/Prior/` on the repo pin `v4.36.0-rc2`, Mathlib
`5f44e80…`. Original namespaces are kept verbatim; only module paths/imports
are remapped `PerpTheory.*`/`PerpChief.*` → `Analog.Prior.*`. Upstream files are
frozen; ported copies carry a provenance header. Any further edit beyond the
mechanical renames listed in §3 would be a new module, not a port edit.

## 1. ADDED — imported, builds clean, audited (21 modules + 1 aggregator chain)

Verified 2026-11-12: `lake build` RC=0 (18,288 jobs); `Analog/Audit.lean` RC=0,
27 audited theorems on `[propext, Classical.choice, Quot.sound]` only.
Cantelli joined 2026-11-13 (issue #9): see §1.1.

| Module (`Analog.Prior.*`) | Thms | Use for the analog problem |
|---|---:|---|
| Standardize | 4 | Standardization/σ-scaling identities — mapping raw measurements to S1 loss scale |
| TailBounds | 3 | Finite Chebyshev + tail-law framework (base for Cantelli/PIT) |
| PIT | 3 | Probability-integral transform uniformity — calibrating per-dimension scores across datasets |
| Estimation | 3 | Tail-index gates (`finite_var_iff`) — when variance-based dimension stats are even legal |
| Math222SimplexCertV2 | 7 | LP weak duality + Farkas infeasibility certificates over the weight simplex — envelope/weight feasibility, machine-checkable refutations |
| PaperWave1Assembly | 3 | Primal witness ⊻ Farkas refutation API (`verdicts_disjoint`) — the accept/refute shape site claims need |
| L13Mixing | 5 | Bonferroni from assumed per-test bounds — first line of multiple-testing control for a whole-Earth search |
| ACI | 14 | Adaptive quantile thermostat, distribution-free on arbitrary sequences — streaming thresholds for GIBS/EONET time series (process dimensions) |
| BinaryInfo | 5 | Hellinger/TV contraction under summaries (`tv_push_le`) — proves collapsing a site to binary match/mismatch can only lose information; backs the analogy-vector design |
| C05Window | 17 | Causal observation windows (no lookahead) — temporal-ingest causality for process dimensions |
| JumpMarkov | 11 | Poisson/Hawkes/Kou event machinery — dust-storm/volcanic event-process models |
| F096 | 10 | Gaussian propeller selection-gain cap — winner's-curse bound when selecting best-of-Earth cells |
| O3/ClampStability | 2 | Clamp Lipschitz + feasibility — losses clamped into envelopes stay stable |
| O3/CovarianceEnvelope | 3 | Quadratic error envelope under weight perturbation |
| O3/WeightError | 2 | Score sensitivity to wrong weights (brief P6 sensitivity reporting) |
| LeverageLaw | 25 | Power-law excursion tails, `Gstar` optimizer under tail budget, trailing-floor ratchet — tail-budget calculus reused by Ceiling/Jumps |
| Ceiling | 16 | Pathwise growth ceilings under bounded steps — envelope excursion bounds |
| Events | 21 | Rare-event frequency/magnitude separation; `vol_managed_gain` (AM–HM) used by Jumps parity |
| Jumps | 13 | Weissman EVT extrapolation + error, hazard parity/budgets, residual hazard — thermal/dust extreme extrapolation beyond observed record |
| TheoryModels1 | 6 | Metric identity batch (incl. bucket-local ACI identity) |

### 1.1 Cantelli (joined 2026-11-13, issue #9)

| Module (`Analog.Prior.*`) | Thms | Use for the analog problem |
|---|---:|---|
| Cantelli | 4 | One-sided Chebyshev (`P(X−E[X] ≥ k) ≤ v/(v+k²)`, standardized exactly `cantelliBound k = 1/(1+k²)`) — distribution-free extreme-tail bound for thermal/dust dimensions |

Statements verbatim from the frozen upstream file; proof structure verbatim
except the mapping renames in §3 below. No upstream Mathlib Cantelli exists at
the pinned rev (checked 2026-11-13: only Borel–Cantelli files), so no
re-export shortcut was possible.

Plus, already in from the scaffold commit (`333c4cd`), from
`QUARCC-Umbrella/quant-fund:fastopt/proofs`: `Analog.Screening` (CVaR / worst-
realisation screening exactness) and `Analog.Certificate` (`subopt_le`).

## 2. CANDIDATES — copied, preserved, NOT imported (re-proof needed)

Mechanical port fails on current Mathlib; these are re-proof projects, not
renames. Files sit in `proofs/Analog/Prior/` with a `NOT IMPORTED` header;
`Analog.lean` records why. No theorem in these files may be cited until a
re-proof passes the ADR-0001 proof gate.

| Module | Blocker observed 2026-11-12 | What it would buy |
|---|---|---|
| Ville (834L) | Conditional-expectation API replaced (`condexp_*` unknown), `Supermartingale` structure changed, `Set.indicator_of_not_mem` gone | Anytime-valid evidence accumulation for site claims (peek-proof testing) |
| HazardTest (356L) | Depends on Ville | Anytime-valid hazard-rate test validity |
| FrameB | Depends on Ville (+ Ceiling, which is in) | Betting-test frame bounds |
| Selective | Depends on FrameB; also `Mathlib.Data.Complex.ExponentialBounds` import gone | Certified abstention (`abstain_improves`) — formal backing for breakdown/abstain semantics |
| Battery → Patterns → ExperimentGate | Chain through Selective | Battery-of-tests ledger; `gate_fwer` family-wise admission control for candidate sites |

## 3. Mechanical port renames applied (the only proof edits made)

Toolchain drift v4.15.0 → v4.36.0-rc2, applied and then re-verified by build:

- binder syntax `∑/∏ x in s` → `∑/∏ x ∈ s`
- `abs_add` → `abs_add_le`; `Finset.card_sdiff` → `Finset.card_sdiff_of_subset`; `le_or_lt` → `le_total` (+ `hcase.le` → `hcase`)
- removed granular `Mathlib.Algebra.BigOperators.*.Finset` imports → `import Mathlib`
- `Real.log_prod` argument implicitness; `mul_lt_mul_left` rw-forms → `mul_lt_mul_of_pos_left` / `lt_of_mul_lt_mul_left`; one `Finset.sum_sub_distrib` exact-term → `simp only`/`rw` forms (typeclass metavariable)
- deleted tactic lines that current `field_simp`/`rw` make redundant ("No goals") — each deletion re-verified by rebuild; one over-deletion caught and undone (`Events` line 265: only the trailing `; ring` was redundant)
- `Jumps.hazard_parity_exposure`: final step rewritten `rw [le_div_iff₀]; nlinarith` → `rw [mul_comm]; exact hgain` (current `field_simp` normalizes to exactly `Events.vol_managed_gain` up to commutation)
- header comments: `Fill in \`sorry\`` → `Fill in the proof holes` (5 files) so the CI no-sorry grep stays a true gate

Cantelli renames (2026-11-13, issue #9) — statements verbatim, proof structure
verbatim outside these:

- `Memℒp` → `MemLp`; `memℒp_const` → `memLp_const` (enorm-refactor spelling)
- `integral_mul_left` → `integral_const_mul`
- `hX.variance_eq` → `variance_eq_integral hX.aemeasurable` (same ∫(X−𝔼[X])² content)
- `meas_ge_le_mul_pow_eLpNorm μ … hfmeas hε` → `meas_ge_le_mul_pow_eLpNorm_enorm μ … (f := g) hε htop` (Markov lemma lost the AEStronglyMeasurable arg, gained an `ε = ∞ → μ{‖g‖ₑ = ∞} = 0` side condition; `f` must now be pinned by name or `ε'` typeclasses go stuck)
- `eLpNorm_eq_lintegral_rpow_nnnorm` → `eLpNorm_eq_lintegral_rpow_enorm_toReal`
- `ofReal_norm_eq_coe_nnnorm` → `Real.enorm_eq_ofReal` (for nonneg reals)
- `Set.mem_setOf_eq` → `Set.mem_ofPred_eq`; `ENNReal.one_toReal` → `ENNReal.toReal_one`
- file-level `set_option maxHeartbeats 1000000` (two `rw [hstep1, hstep2, …]` unifications)

## 4. REVIEWED, NOT ADDED (with reasons — silence would be a claim too)

| Area | Disposition |
|---|---|
| PerpTheory Kelly, Accounting; JumpBet/Patterns trading laws; FundingMech, Gamma/Barrier ladders, OFI specs, book mechanics | Finance-semantics-bound; no analog-problem statement survives translation |
| PerpTheory PathConstraints (breach monotonicity), Axioms101, FeasibilityCounterexample | Mostly demotion/counterexample notes (valuable upstream, nothing to import as a theorem here); breach-monotonicity idea noted for envelope work orders |
| PaperWave2 F127/F135/F162/F228/F229/F235 ensembles | Genuine math (sensitivity, covering, channels) but no statement our dimensions can instantiate without new theory; revisit only if a work order names one |
| Single-lemma Math1xx bridges (Math110Metric, Math115Margins, Math124Schedule, Math125Median, Math127Sensitivity, Math222Slack, Math374Transport…) | True and clean but at/below Mathlib triviality for our purposes; adding them would inflate the audit surface without buying a certificate |
| Energy (Fernholz master formula), SW06_RegimeAbstain (1,438L), signal-lib causal cores, swarm/synthesis lanes | Energy: tangential. SW06: closest "certified abstention" relative — **candidate if Selective chain stays blocked**, but 1.4k lines + `SignalLib` dependency needs its own work order. Causal cores duplicate C05Window |
| probe*.lean tools, drafts, `_WORKING_UNCOMMITTED`, anything with live `sorry` in proof position | Not proofs yet by ADR-0001 definition; never imported |
| Remaining ~120 sorry-free-looking files not named above | Surveyed at theorem-name/header level (method: `/tmp` survey script run 2026-11-12), all fall in the rows above; a file-level re-survey is cheap to redo from §0 sources if the owner disputes a row |

Next candidates in value order: Ville chain (unlocks ExperimentGate FWER) →
SW06 abstention (if Ville stays out). ~~Cantelli~~ done 2026-11-13 (issue #9,
§1.1). Each is a `gate:proof` work order with the frozen upstream file as its
statement source; open on request, not by default.
