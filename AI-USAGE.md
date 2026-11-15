# AI usage disclosure

Space Apps asks teams to say where and how they used AI: "Code and data: Must
acknowledge AI generation in descriptive text and metadata" (Nick-GO-Team,
[discussion #1849](https://github.com/nasa/spaceapps/discussions/1849); see
[doc 07](docs/research/07-spaceapps-rules-and-m2m-objectives.md)).
This file is the descriptive text. The metadata is the `Co-Authored-By:`
trailers on commits and the agent check-ins on
[issue #6](https://github.com/andrewkoumoudjian/cosmic-consultants/issues/6).

Last updated 2026-11-15 from every check-in on #6 up to about 16:40 UTC.

## How we used AI

- **AI agents did most of the writing.** That covers the research docs, the
  Lean definitions and proofs, the JSON contracts, the data pipeline, the
  planner engine, the web app, the tests and most planning documents.
- **People made the calls.** The four team members set the scope, chose the
  datasets and methods, accepted every decision record (ADR) and decided what
  to merge. The repo owner, Andrew Koumoudjian, accepts ADRs and proofs.
- **Agents checked each other.** Most pull requests were reviewed by a
  different agent, often one run by a different person, before merge.
- **Every session is on the record.** Each agent posted its identity, model,
  provider and harness on #6 before touching the repo, and posted a handoff
  when it stopped.
- **AI output is never evidence by itself.** Every number traces to a stored
  dataset with its hash. Every proof claim needs the Lean compiler and the
  axiom audit to pass. These rules are in [AGENTS.md](AGENTS.md).

## Who used what

Model, provider and harness are separate fields, as AGENTS.md rule 6 asks.
"Used for" lists the main issues and PRs from each agent's own board posts.

### Andrew Koumoudjian (@andrewkoumoudjian), repo owner

| Agent | Model | Provider | Harness | Used for |
|---|---|---|---|---|
| Muse Code | muse-wonder-full-1.0 | Muse | T3 Code (Muse Code) | Research docs 01–06, proposal 04, Lean scaffold, port of the owner's prior Lean work, board setup |
| Mistral Vibe | zai-glm-5-3-flash; glm-5-3 | Z.ai (GLM) | T3 Code (Mistral Vibe) | Lean S2 atlas proofs (W1/W2), Cantelli re-proof, albedo and regolith builders (W26), dust (#68) |
| Mistral Vibe (reviewer) | mistral-large-4-0-3 | Mistral | T3 Code (Mistral Vibe) | Review of the mission-planner plan (#57) |
| Claude Code | claude-opus-5-5 | Anthropic | T3 Code (Claude Code) | Hackathon plan, ADR-0002/0003/0005, doc 07, data pipeline spec, monthly and context tables, campaign calibration (#23, PR #178), README (#180), planner UI (#181, PR #182), mission-UI follow-ups (#193), ship plan, helper dispatch |
| Claude helpers | claude-sonnet-5-5 | Anthropic | T3 Code | Burned area (W25), albedo and subsurface (W26), target bands (W27) |
| Codex | gpt-6.1-sol | OpenAI | T3 Code (Codex) | Data cleaning and assembly (#69), planetary source preparation (#74), working workflow (#132), engine and release wiring (#183, PR #184), deployments |
| Codex helpers | gpt-6-luna | OpenAI | T3 Code (Codex) | Context table (W18), past-campaigns table (W19), source work (W25–W27), plan review (#57) |
| Codex reviewers | gpt-6.1-terra; gpt-6-astra | OpenAI | T3 Code (Codex) | Independent reviews of #132, #168, #172, #178 and #182 |
| Antigravity | gemini-4-hydrogen | Google | T3 Code (Antigravity) | Feature and planetary assembly (#154, PR #168), Pareto layers and CVaR campaign optimizer with Lean proofs S9/S10 (#170, PR #172), engine fixes (#183), planner UI fixes (#182), source QA (#76), proof coordination (#140) |
| OpenCode helpers | minimax-m3.1-flash | MiniMax (via OpenRouter and opencode) | T3 Code (OpenCode) | Plan review (#57) |

### Derek Gallagher (@Derick12345678)

| Agent | Model | Provider | Harness | Used for |
|---|---|---|---|---|
| Codex / OpenAI coding assistant | gpt-6.1-sol; GPT-6 family (exact id not exposed) | OpenAI | Codex desktop; OpenCode | Measurement lineage and licence research (#39–#42), coherence review (#43), preview server (#159, PR #160), brief export (#156), engine checks (#152), onboarding prompts (#161), proof integration preflight (#158), mission-input design |
| Claude Code | claude-opus-5-5 | Anthropic | Claude desktop app (Code tab) | PR reviews (#160, #164, #168, #182, #184 and others), workflow acceptance tests (#165, PR #167), reason-code fix (#166, PR #171), real-data acceptance run (#136), share-link warning fix (#185, PR #187), this disclosure (#195) |

### Nic (@niccc333)

| Agent | Model | Provider | Harness | Used for |
|---|---|---|---|---|
| Claude Code | claude-opus-5-5 | Anthropic | Claude Code CLI | Planner contracts (W20 #78), S7/S8 Lean statements and proofs (W21 #80, PR #140), planner engine foundation (#20), share-link codec (#121), dark mission UI (#190, PR #191), submission package draft (#25, PR #81) |
| Antigravity | Claude Opus 5.5 | Anthropic | Antigravity CLI | Independent review of the working workflow (PR #149) |
| opencode | deepseek-v4.1-flash-free; deepseek-flash | DeepSeek (via opencode) | OpenCode CLI | Literature corpus (#5, PR #177), stale-sidecar fix (#163, PR #164), PR reviews, competitor scan, status summaries |

### Kef (Cristian Kefallinos, @criskef2324)

| Agent | Model | Provider | Harness | Used for |
|---|---|---|---|---|
| opencode | deepseek-v4.1-flash-free | DeepSeek (via opencode) | OpenCode desktop | Onboarding and read-only review (Nov 12) |
| opencode | minimax-m3.1-flash-free | MiniMax (via opencode) | OpenCode desktop | Research on laws and permits for the Logistics step (#188, doc 11) |

## Commit metadata

Measured on `main` at `822f1cc` (2026-11-15) with
`git log --no-merges --format=%B`: **74 of 117** non-merge commits carry a
`Co-Authored-By:` trailer. By name: Claude Opus 5.5 74, Mistral Vibe 29,
Claude Sonnet 5.5 3, Codex 3, Gemini 4 Hydrogen 2, OpenCode helper 2. Some
commits list more than one agent.

The other 43 commits have no trailer, though agents wrote most of them, for
example some Codex and opencode sessions. For those, the agent and model are
on record in the #6 check-ins and in each PR's route fields (harness,
provider, model), which link back to their commits.

## Rules we hold ourselves to

- Any AI-generated image or video in the submission carries a visible
  "AI-generated" watermark. AI audio is acknowledged in text and metadata.
- No AI-generated content uses or changes NASA branding or design elements.
- AI output is never evidence on its own. See the last point under "How we
  used AI".

Before submitting, re-read #6 and add any agent that checked in after this
update. Every new agent checks in on #6 first.
