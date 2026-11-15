# ADR-0013 — S9 / S10 statement freeze and co-commit gate exception (#170)

Date: 2026-11-15. Status: **proposed by agent (`@andrewkoumoudjian`) for owner merge of PR #172**.

## Context

[ADR-0001](ADR-0001-scope-collaboration-lean-first.md) specifies three sequential
gates: **Statement** (frozen and committed before any proof attempt or executing
code), **Proof**, and **Experiment**.

In work order #170 (`engine/170-optimal-site-model`, PR #172), commit `c4425a0`
introduced the S9/S10 statement modules (`proofs/Analog/ParetoLayers.lean` and
`proofs/Analog/CampaignOpt.lean`), their proof modules
(`proofs/Analog/ParetoLayersProofs.lean` and `proofs/Analog/CampaignOptProofs.lean`),
and the Python runtime modules (`services/engine/src/planner/pareto_model.py` and
`services/engine/src/planner/optimizer.py`) together in a single initial commit.

Review (`gpt-6.1-terra`, 2026-11-15) correctly flagged that `c4425a0` alone
cannot prove temporal separation between the Statement gate and the Proof/Code
gates.

## Decision

1. **No retroactive claim of prior statement-only commit.** `proofs/STATEMENTS.md`
   records honestly that `c4425a0` co-committed S9/S10 statements, proofs, and
   runtime code rather than splitting statement freeze into an earlier commit.
2. **Scoped ADR-0001 gate-sequence exception for #170.** Owner `@andrewkoumoudjian`
   accepts `ParetoLayers.lean` and `CampaignOpt.lean` at their exact `c4425a0`
   contents (byte-unchanged across every subsequent review commit in PR #172):
   - `proofs/Analog/ParetoLayers.lean`: SHA-256 `877b5362043ce9b1434826b439a0e68e4f65459f93758d23000735a70272168e`
   - `proofs/Analog/CampaignOpt.lean`: SHA-256 `475d0bda4033b1dfb4ae3963ffaed95129648d606ced9563b15ac6d51d1a12eb`
3. **All remaining ADR-0001 requirements stay strictly enforced:**
   - Zero edits to either statement file after `c4425a0`.
   - Pinned `leanprover/lean4:v4.36.0-rc2` `lake build` and `lake env lean Analog/Audit.lean` pass with return code `0`, standard axioms only (`[propext, Classical.choice, Quot.sound]`), and zero `sorry`/`admit`.
   - Future new statement work orders follow the strict separate statement-freeze PR order (`#84` → `#140`).
