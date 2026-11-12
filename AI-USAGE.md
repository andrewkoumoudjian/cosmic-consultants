# AI usage disclosure

Space Apps requires teams to say where and how AI tools were used: "Code and
data: Must acknowledge AI generation in descriptive text and metadata"
(Nick-GO-Team, [discussion #1849](https://github.com/nasa/spaceapps/discussions/1849);
see [doc 07](docs/research/07-spaceapps-rules-and-m2m-objectives.md)). This file
is that descriptive text; the metadata is the commit trailers and the agent
check-ins on issue #6.

## How AI is used in this repo

Most research docs, Lean proofs, contracts and planning documents are written
by AI coding agents under the direction and review of the team. Humans set
scope and make decisions (ADRs are accepted by the owner), and review and merge
every PR. Each agent session records its identity, model and harness on the
[agents message board (#6)](https://github.com/andrewkoumoudjian/cosmic-consultants/issues/6).

| Agent (product) | Model | Harness | Used for (per board check-ins) |
|---|---|---|---|
| Muse Code | muse-wonder-full-1.0 | T3 Code via Muse Code | research docs 01–06, proposal 04, Lean scaffold, prior-corpus port, boards |
| Mistral Vibe | zai-glm-5-3-flash (Z.ai / GLM) | T3 Code (acpRegistry) | Lean W1/W2 (S2-atlas), Cantelli re-proof |
| Claude Code | claude-opus-5-5 (Anthropic) | T3 Code | hackathon plan, ADR-0002/0003, doc 07, pitch plan, backlog #14–#25 |

Commit metadata: AI-assisted commits carry a `Co-Authored-By:` trailer naming
the agent. Five early commits (`628a6c3`, `333c4cd`, `14b2655`, `b42e4b7`,
`f47fe7c`) lack the
trailer although agents wrote them; the table above and the #6 check-ins cover
them.

## Rules we hold ourselves to

- AI-generated images or video in the submission carry a visible "AI-generated"
  watermark; AI audio is acknowledged in text and metadata.
- No AI-generated content uses or modifies NASA branding or design elements.
- AI output is never evidence by itself: every number traces to a dataset
  snapshot, and every proof claim to a compiler + axiom-audit run (AGENTS.md).

Update this table when a new agent or model joins (board check-in first).
