# Agent onboarding — kickoff prompts

Paste one of these into a fresh agent session (any harness) to land it
correctly in this repo. The long form is for an agent about to do real work;
the short form is for a read-only / opinion task in the commons.

## Long form (working agent)

```text
You are joining github.com/andrewkoumoudjian/cosmic-consultants — a NASA
Space Apps 2026 monorepo ("Identify Earth Locations that Analog the
Permanent Moon Base Locations and Mars"), Lean-first, multi-agent.

Do these in order. Do not edit anything until step 4 is done.

1. Sync: clone the repo (or `git pull` your checkout). Confirm `git status`
   and note the HEAD commit.
2. Read, in order: AGENTS.md, docs/decisions/ADR-0001*, README.md, and your
   work-order issue. AGENTS.md is binding, especially: Lean statement -> proof
   -> experiment gates, no sorry in accepted proofs, pinned Lean toolchain,
   one issue = one branch = one PR, package lanes, provenance for every
   number, no scalar "similarity score" anywhere.
3. Read the boards: issue #6 (presence) and issue #7 (commons). Note who is
   checked in, what is in flight, and read your topic threads in #7.
4. CHECK IN on issue #6 (this is mandatory before any claim or edit):
   gh issue comment 6 --repo andrewkoumoudjian/cosmic-consultants --body "
   ## Check-in
   - Identity: <your agent identity/product>
   - Model: <your exact model>
   - Harness: <T3 Code / OpenCode / Mistral Vibe / Muse / ...>
   - Controlling human: Andrew Koumoudjian (@andrewkoumoudjian)
   - Session: <your session/thread id or link>
   - Lane + work order: <lane>, issue #<the ONE issue below>
   - State I found: <HEAD commit, clean/dirty, in-flight work you saw>
   - Intended action: <one or two lines>
   - Blockers: <or none>"
   Copy the shape of the existing exemplar comments on #6. Harness, provider
   and model are three separate fields. Never sign another agent's name.
5. Claim EXACTLY ONE work order: comment your claim (identity/model/harness)
   on that issue, set label status:in-progress, branch from up-to-date main
   as <lane>/<issue>-<slug>, prefer an isolated worktree if your harness
   supports it. Stay inside your package lane (see AGENTS.md/CODEOWNERS);
   cross-lane needs go through a contracts/ change first.
6. Work to the issue's acceptance evidence. Quote real command output in your
   PR (the PR template has the checklist). For Lean: `lake build` return code
   from lake itself, `lake env lean Analog/Audit.lean` (from proofs/), zero
   sorry/admit. Failed or partial work is preserved and reported, not hidden.
7. Hand off three times with the same facts: PR description, closing comment
   on the work-order issue, handoff comment on #6. Discussion, questions,
   half-ideas and challenges go to the commons (#7) with its tags — end every
   commons post with an "Ask:" line and your signature.
8. Never push to main, never merge your own PR, never run data statistics
   against unfrozen/unproved statements (ADR-0001). If something here
   contradicts a newer board post by the owner, the owner wins; flag it.

Your work order for this session: <PASTE ISSUE NUMBER + ONE-LINE OBJECTIVE>
Your lane: <proofs|contracts|ingest|engine|api|atlas|data|research|docs>
```

## Short form (read-only / commons participant)

```text
Read github.com/andrewkoumoudjian/cosmic-consultants AGENTS.md and issues #6
(presence board) and #7 (commons). Check in briefly on #6 (identity / model /
harness / controlling human Andrew Koumoudjian) stating you are read-only.
Then in #7 answer or extend: <TOPIC SLUG OR QUESTION>. Follow the commons
format ([Q]/[IDEA]/[FINDING]/[CHALLENGE]/[HELP], topic slug, quote what you
answer, end with "Ask:" + your signature). Evidence links over opinions; mark
speculation. Claim no work and edit no files.
```

## Maintainer notes

- Update this file whenever AGENTS.md rules change in ways a newcomer would
  trip on; keep the two prompts paste-ready (no repo-relative jargon that
  isn't defined inline).
- If an agent cannot use `gh` (no auth, read-only harness), the human pastes
  its check-in/handoff verbatim and marks it "posted on behalf of …". The
  board is still the record.
