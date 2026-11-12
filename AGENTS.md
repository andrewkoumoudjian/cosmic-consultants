# AGENTS.md — binding rules for every contributor (human or agent)

Project: NASA Space Apps 2026 — "Identify Earth Locations that Analog the
Permanent Moon Base Locations and Mars". Read first, in order:
`docs/research/01–03, 05`, `docs/proposals/04`, `docs/decisions/ADR-0001`.

## Non-negotiables

1. **Lean-first (ADR-0001).** Concepts are defined in `proofs/Analog/` and their
   correctness theorems frozen before executing code computes with them. No
   `sorry`/`admit`/custom axioms in accepted proofs. Pinned toolchain only
   (`proofs/lean-toolchain`); the parent/owner re-runs `lake build` and
   `lake env lean Analog/Audit.lean` before accepting any proof claim. Capture
   the Lean process return code itself — never through a pipe that masks it.
2. **Evidence over narration.** Every claim in an issue/PR quotes real output:
   compiler/test results, live API probes with dates, dataset hashes. A claim
   copied from a doc is intent, not a result. Counts from catalogs are re-probed
   at use time, never cited stale.
3. **Provenance (brief P8).** Every number in the atlas traces to a snapshot in
   `data/snapshots/` (URL, fetch date, hash, license). No hand-edited snapshots,
   no fabricated fills for missing records — missing stays explicit.
4. **Partial analogy always (brief R4/P3).** `gravity`, `pressureRegime`,
   `radiation` are permanent breakdowns. No single scalar similarity score
   anywhere in code or copy; analogy is the per-dimension vector.
5. **One issue = one branch = one PR.** Claim by assignment + `status:in-progress`
   before coding. Stay inside your package lane (`CODEOWNERS`); cross-lane needs
   go through a `contracts/` change first. Never push to `main` directly after
   the bootstrap commits; never let two agents edit the same file concurrently —
   writers work in isolated checkouts/worktrees.
6. **Track route honestly.** Dispatch records name harness, provider, model as
   three separate fields. Record separate runtime status and scientific status
   (`proposed/frozen/Lean-clean/executed-unreviewed/accepted/rejected/partial/
   blocked`). Failed and partial work is preserved and reported, not deleted.
7. **Decisions are files.** Scope/weight/dataset/architecture changes land as
   `docs/decisions/ADR-*.md` in the PR that implements them. Chat is not a record.

## Package lanes

`proofs/` Lean spec+proofs · `contracts/` JSON Schemas (single source between
lanes) · `services/ingest/` Python fetchers · `services/engine/` Rust screening
(native+WASM) · `services/api/` TS Worker (only holder of the NASA API key) ·
`apps/atlas/` TS map (GIBS + Trek WMTS) · `data/` catalog/fixtures/snapshots ·
`research/` corpus + notebooks (nothing ships from notebooks).

Dependency rule: `apps → api artifacts`; `ingest → data/snapshots`;
`engine → contracts + snapshots`; `proofs` depend on contract *statements* only.
