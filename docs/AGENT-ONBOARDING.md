# Agent onboarding — current review boundary

Read AGENTS.md and docs/STATUS.md before interpreting an old proposal or issue.
ADR-0001/0002/0003 are accepted history; ADR-0004 is a proposed successor whose
local diff has controlling-human approval for draft-PR feedback. Repository
adoption and implementation remain pending review. This file describes the target.

## Working-agent kickoff

```text
You are joining cosmic-consultants, a NASA Space Apps 2026 repository.

1. Read the live coordination board #6 first, and commons #7; inspect open PRs
   and status:in-progress work. Record local HEAD and tree status. Do not pull,
   overwrite work, sign another agent's name or take an overlapping task.
2. Post your own check-in on #6 in the AGENTS.md template. Identify the actual
   controlling human, harness, provider and model separately; if an exact model
   ID is unavailable, say so rather than inventing it. Read AGENTS.md, STATUS,
   applicable accepted ADRs, the proposed successor and the work-order issue.
3. Claim one authorized issue and announce paths/stop point before edits. Use
   an isolated branch/worktree. Cross-lane interfaces go through a contract
   design/change first. Record plan changes and answer mentions on the boards.
4. Respect the task's review boundary. For #43: approved design/docs, fixture
   metadata and CI maintenance may be published in a draft PR for team feedback.
   No merge, new runtime/Lean/schema or science output. Existing #40/#42 are
   separate unmerged work. Do not adopt their results
   by copying them or change their ownership.
5. After ADR-0004 adoption, exploratory research may inform a model with provenance
   and explicit exploratory labeling. Freeze release requirements/rules/inputs and
   numeric policy before the release run. Until adoption, the existing accepted
   gates govern dependent implementation. Event/build-window rules still apply.
6. Distinguish scientific review, runtime tests, formal proof and conformance.
   An imported theorem does not verify an application. Never mutate a frozen
   Lean statement to fit runtime code. Use the pinned toolchain and capture the
   Lean process return code directly before claiming any proof pass.
7. Preserve missingness, per-feature results and permanent breakdowns. No ARL v0,
   overall similarity score or global Pareto deletion under the proposed redesign.
   Known analogs may be dominated. Corroboration is claim/pair-specific review.
8. Report executed checks with real output and limits. Hand off on #6 and the
   issue; release assignment/in-progress status when stopping. Open a PR only
   when explicitly authorized by the task; for local review give file/diff links.
```

## Read-only kickoff

```text
Read AGENTS.md, STATUS.md and the boards. Check in as yourself with the actual
controlling human. State that you are read-only. Claim no implementation work.
For commons posts use its topic/tag/signature/Ask format. Distinguish historical
intent from code and execution evidence; qualify access and verification limits.
```

If GitHub is unavailable, do not pretend a check-in was posted. Obtain the
required on-behalf check-in before claims/edits, or stay read-only. Direct human
instructions and documented adoption boundaries must be reported explicitly.
