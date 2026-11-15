# Agent onboarding — kickoff prompts

Paste one of these into a fresh agent session (any harness). Replace every
angle-bracket placeholder with the actual agent, human and work order.
AGENTS.md and newer owner instructions govern; these prompts add no rules.

## Long form (working agent)

```text
You are joining github.com/andrewkoumoudjian/cosmic-consultants — a NASA
Space Apps 2026 monorepo ("Identify Earth Locations that Analog the
Permanent Moon Base Locations and Mars"), Lean-first, multi-agent.

Do these in order. Do not claim work, open a branch or edit files before
your own check-in is on the board.

1. First read issue #6 (agents board), then #7 (commons). Note active work,
   questions addressed to you and newer owner instructions. Inspect the
   checkout's HEAD and clean/dirty state without changing it. Read AGENTS.md
   for the binding rules and check-in format.
2. CHECK IN on #6 before any claim, branch or edit. Post this shape:

   ## Check-in
   - Identity: <your agent product/identity>
   - Model: <exact serving model ID, or state if it is unavailable>
   - Harness: <actual harness>
   - Controlling human: <full name> (@<github-handle>)
   - Session: <your session/thread ID or link, if any>
   - Lane + work order: <lane>, issue #<number>, or "none — orientation"
   - State I found: <HEAD commit, clean/dirty, anything in flight>
   - Intended action: <one or two lines>
   - Blockers: <or "none">

   Record provider separately from model and harness in the same post. Use
   your actual controlling human, not the person named in an example.
   Never sign another agent's name or reuse another session's check-in.
   If you cannot post, have the human post your exact check-in on your
   behalf before you claim or edit anything.
3. Read, in order: docs/research/01, 02, 03, 05 (the numbered files),
   docs/proposals/04, then docs/decisions/ADR-0001*. Also read README.md,
   docs/plan/MISSION-PLANNER.md, applicable ADRs and your work-order issue.
   ADR-0005 replaces the earlier ARL product. Show per-trait match/miss/unknown
   and a Pareto shortlist; no single site similarity score. Keep gravity,
   pressureRegime and radiation as permanent breakdowns. AGENTS.md lists
   the two bounded exceptions and their display limits.
4. Before claiming, branching or editing, reread #6 since your last visit,
   open PRs and issues marked status:in-progress. If another agent names the
   same issue, files or lane, agree on a split on #6 first. A stale claim
   does not permit takeover. Answer when addressed on #6 or #7.
5. Claim exactly one work order: comment your identity and route on it,
   assign yourself and set status:in-progress. Fetch current main and create
   one issue branch in an isolated checkout/worktree. Follow your harness's
   branch naming rules. Preserve existing work; do not reset a shared or
   dirty checkout. One issue = one branch = one PR. Stay in your package
   lane (CODEOWNERS); cross-lane needs go through a contracts/ change first.
6. Before editing, post on #6:

   ## Now working on
   - Who: <identity> / <model> / <harness> / <controlling human>
   - Issue + branch: #<number>, <branch>
   - Touching: <exact paths you will edit>
   - Until: <stop point, or "handoff to follow">

   Include provider separately. Post again before adding paths or switching,
   pausing or finishing tasks. Announce blockers, reusable resources and
   helper starts/stops; helpers check in themselves. Follow your harness's
   rules on whether helpers may be started. After about two hours without
   a post, send a short progress update.
7. Work to the issue's acceptance checks. Freeze and commit definitions and
   theorem statements before proofs or data statistics. Data experiments
   require passing proofs too (ADR-0001). Never change frozen statements
   to fit code. No sorry/admit/custom axioms in accepted proofs. Use
   proofs/lean-toolchain and its Mathlib pin. The parent/owner must rerun
   lake build and lake env lean Analog/Audit.lean from proofs/ before
   accepting proof claims; capture each process's own return code, not a pipe's. Quote real
   test/probe output and keep runtime and scientific status separate.
   Hosted CI may not start at all (#139): jobs can fail in about two
   seconds with no logs and a payments or spending-limit annotation. That
   is neither a pass nor proof your change broke something. Run the checks
   yourself before calling anything green: `python scripts/local_checks.py`
   for the groups it covers, and the exact commands in
   `.github/workflows/<workflow>.yml` for anything it does not. Put the
   commands, output tails and return codes in the PR, and say that hosted
   CI did not run.
   Preserve failed and partial results. Verify snapshot hashes before
   statistics; every published number needs URL, fetch date, hash and
   license provenance. Never hand-edit snapshots or invent missing records.
   Catalog counts must be probed again when used.
8. Hand off with the same facts in three places: PR description, work-order
   comment and #6 handoff. Include commit/PR links, real evidence, limits,
   remaining work and blockers. Every PR description links both its #6
   "Now working on" post and its #6 handoff post (see the PR template).
   If hosted CI did not start, say so in the handoff and link your local
   evidence. A reviewer with working Actions can push the same commit from
   their account; never write that checks passed when no job ran.
   Release status:in-progress and assignment from work you stop or hand
   off. Never push directly to main or merge your own PR.
9. Keep posts short and in plain English. Discussion goes to #7 with a
   [Q]/[IDEA]/[FINDING]/[CHALLENGE]/[HELP]/[PROMOTE] tag and topic slug.
   End with an Ask: line and your identity/model/harness/human signature;
   keep provider separate. The commons does not claim work or make binding
   decisions. Promote ready discussions into work orders or ADRs. Scope,
   weight, dataset and architecture decisions land as ADR files in the
   implementing PR; chat alone is not the record.

Your work order: <issue number + one-line objective>
Your lane: <proofs|contracts|ingest|engine|api|atlas|data|research|docs>
Your controlling human: <full name> (@<github-handle>)
```

## Short form (read-only / commons participant)

```text
First read github.com/andrewkoumoudjian/cosmic-consultants issue #6 (agents
board) and #7 (commons). Inspect the checkout's HEAD and clean/dirty state
without changing it, and read AGENTS.md. Post your own check-in on #6 using
the full AGENTS.md shape: Identity, Model, Harness, Controlling human,
Session, Lane + work order, State I found, Intended action, Blockers.
Identify your actual controlling human, <full name> (@<github-handle>).
Record provider separately from harness and model. State that you are
read-only; do not reuse another session's check-in. If you cannot post,
have the human post your exact check-in on your behalf first.

Read the required research/proposal/ADR files listed in AGENTS.md, README
and the files relevant to <topic slug or question>. Announce your read-only
topic on #6 with "Now working on" (Touching: no tracked files). Answer asks
addressed to you, and contribute on #7 with its topic slug and a
[Q]/[IDEA]/[FINDING]/[CHALLENGE]/[HELP]/[PROMOTE] tag. Use plain English,
link evidence and label speculation. End with an Ask: line and your
identity/model/harness/human signature, with provider separate. The commons
does not claim work or make binding decisions. Claim no work, open no
branch and edit no files. Post a short #6 handoff when done, including what
you found, the evidence, what remains and any blockers.
```

## Maintainer notes

- Keep both prompts aligned with AGENTS.md and the PR template. A prompt
  must not silently grant permission to bypass a gate or take another claim.
- Use the actual controlling human in both prompts, even when a board
  example names someone else. An unavailable exact model ID stays explicit.
- If a human posts for an agent that cannot use GitHub, paste the agent's
  check-in/handoff verbatim and mark it "posted on behalf of …". The board
  remains the record.
- Keep the #139 warning current. Drop it once Actions jobs start for
  everyone again.
