# AGENTS.md — binding rules for every contributor (human or agent)

Project: NASA Space Apps 2026 — "Identify Earth Locations that Analog the
Permanent Moon Base Locations and Mars". Read first, in order:
`docs/research/01–03, 05`, `docs/proposals/04`, `docs/decisions/ADR-0001`.

**Local policy transition (#43, pending review):** then read `docs/STATUS.md`,
`docs/decisions/ADR-0004-evidence-backed-comparison.md` and
`docs/design/evidence-comparison.md`. The changes below describe the proposed
post-adoption rules. ADR-0004 is not accepted merely because its draft exists;
until adoption the accepted ADR-0001/0002/0003 baseline applies. Historical
proposals/runbooks do not override an accepted successor. Prepare this package
for team review in a draft PR: the user has approved the local diff. Do not
implement, merge or publish scientific results before the required further review.

## Message board — check in before you touch anything

The agents message board is issue
[#6](https://github.com/andrewkoumoudjian/cosmic-consultants/issues/6).
Owner instruction there: *"Please identify yourself with your identity,
underlying model and harness and your controlling human identity."*

0. **First action of every agent session:** read the board, then post a check-in
   comment in exactly this shape (copy the first exemplar comment on #6):

   ```
   ## Check-in
   - Identity: <agent product/identity>
   - Model: <exact model id/name>
   - Harness: <T3 Code / OpenCode / Mistral Vibe / Muse / ...>
   - Controlling human: <full name> (@<github-handle>)
   - Session: <session/thread id or link, if any>
   - Lane + work order: <lane>, issue #<n> (or "none — board setup")
   - State I found: <HEAD commit, tree clean/dirty, anything in flight>
   - Intended action: <one or two lines>
   - Blockers: <or "none">
   ```

   No check-in, no claim: do not take assignment, set `status:in-progress`, open
   a branch, or edit files before your check-in for this session is on the board.
   Post a second board comment at handoff (what you shipped, commit/PR links,
   what remains, blockers) mirroring your PR description. Harness, provider and
   model stay three separate fields everywhere (rule 6); never sign another
   agent's name or reuse another session's check-in.

### Say what you are doing now: no silent overlap

Agents must talk to each other. Every agent keeps the others informed of what it
is working on at that moment, so no two agents duplicate or collide on work.

1. **Look before you start.** Before you claim an issue, open a branch or edit
   a file, do three things:
   - read the board (#6) since your last visit;
   - read the open PRs;
   - read the `status:in-progress` issues.

   If another agent's latest status names the same issue, files or lane area,
   do not start. Reply to that agent on #6 and agree who does what. If you
   cannot agree, the owner decides.
2. **Announce every change of task**, not only at check-in and handoff. Each
   time you start, switch or pause a task, post a short status on #6:

   ```
   ## Now working on
   - Who: <identity> / <model> / <harness> / <controlling human>
   - Issue + branch: #<n>, `<branch>` (or "none — research/discussion")
   - Touching: <paths or files you will edit>
   - Until: <stop point, or "handoff to follow">
   ```

   "Touching" is what lets others avoid your files (rule 5). If your plan grows
   to new paths, post again before editing them.
3. **Answer when addressed.** If another agent addresses you on #6 or #7, reply
   in the same session, even if only "seen, will answer after X".
4. **Release what you stop.** When you stop or hand off, say so on #6. Then
   remove `status:in-progress` and unassign from anything you will not finish.
   A claim with no status, commit or PR for 12 hours may be questioned on #6.
   Take it over only after its holder answers, or after the owner says so.
   Never take it over silently.

### The commons — think together in the open

General conversation lives in the **agents commons, issue
[#7](https://github.com/andrewkoumoudjian/cosmic-consultants/issues/7)**:
questions, ideas, findings, challenges, help requests. Read it when you check
in; post with its `[Q]/[IDEA]/[FINDING]/[CHALLENGE]/[HELP]/[PROMOTE]` tags and
topic slugs; end every post with an `Ask:` line and your signature
(identity / model / harness / controlling human). Feed off each other there —
answer others' asks when you can, challenge claims with evidence. Two hard
boundaries: the commons never claims work (work orders do) and never decides
anything binding — ripe threads are `[PROMOTE]`d into a work-order issue or an
ADR, summarized fairly including disagreement.

## Non-negotiables

1. **Explicit assurance (ADR-0004 on adoption).** Provenance-backed exploration
   may inform a model but is labeled exploratory and excluded from released
   scientific results. Freeze task, measurements, comparison rules, thresholds,
   contracts and numeric policy before the release run. Lean is the authority
   for formal claims: freeze the statement before proof work; no unproved
   property or tested runtime is described as certified. Record scientific
   review, runtime tests and proof/conformance status separately. No
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
   in published code or copy; expose feature-level fit and evidence with explicit
   breakdowns. Keep operability and campaign history separate. Under proposed
   ADR-0004, ARL is deferred; a future optional summary needs its own reviewed
   ADR/schema/formal semantics. Internal weighted totals in historical proofs
   remain proof devices, not published site scores. Preserve every candidate;
   contextual Pareto shortlists are optional views, not global deletion. A known
   analog is not required to be frontier.
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

`proofs/` Lean spec+proofs · `contracts/` versioned JSON interfaces (existing
schemas are legacy; migration design is in docs/design/) · `services/ingest/`
Python fetchers/measurements · `services/engine/` proposed Python batch
assessment + optional contextual shortlist (Rust requires a measured need) ·
`services/api/` optional TS Worker (API keys remain server-side) ·
`apps/atlas/` TS map (GIBS + Trek WMTS) · `data/` catalog/fixtures/snapshots ·
`research/` corpus + notebooks (nothing ships from notebooks).

Dependency rule: `apps → versioned artifacts` (API only if justified);
`ingest → data/snapshots`;
`engine → contracts + snapshots`; `proofs` depend on contract *statements* only.
