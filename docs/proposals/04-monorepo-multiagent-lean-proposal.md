# 04 — Proposal: original implementation, monorepo, multi-agent workflow, Lean verdict

> Historical proposal; retained for rationale, not current execution instructions.
> ADR-0001 resolved its original questions; ADR-0002/0003 were accepted by #26.
> [ADR-0004](../decisions/ADR-0004-evidence-backed-comparison.md), which would have
> replaced global screening and readiness levels, was **deferred by the owner on 2026-11-14 (#46)**.
> The current plan is [PLAN-hackathon.md](../PLAN-hackathon.md).
> Generic optimization proofs do not bound physical measurement/analogy error.

Date: 2026-11-12. Status: **proposal for approval — nothing here is built.**
Scope of this document: research + setup proposal only, per task. Three decisions at
the end need the repo owner's call before any scaffolding.

Inputs: [`01` NASA catalog](../research/01-nasa-data-catalog.md) ·
[`02` challenge brief](../research/02-challenge-brief.md) ·
[`03` literature](../research/03-literature-inventory.md) ·
GitHub history of `andrewkoumoudjian` / `QUARCC-Umbrella` (inventoried 2026-11-12, §2).

## 1. The proposed original implementation (one paragraph)

**A certified Pareto analog atlas.** Fix each target (Artemis-class lunar south-polar
base regions; reference human-Mars landing zones) as a published multi-dimensional
envelope over the brief's dimensions (terrain, thermal, illumination, dust/process,
water-ice proxies, surface material, subsurface). Rasterize Earth's land surface into
cells, attach the same dimensions from open data, then run **certified screening**:
eliminate cells that provably cannot reach the Pareto frontier under *any* weighting
in a declared family — with a machine-checked Lean proof that the elimination is
exact, and a suboptimality certificate bounding the error of every retained cell's
scores. Survivors are published as an interactive map where each site carries a
per-dimension **analogy vector** (match strength + explicit breakdown, including the
brief's four permanent mismatches), full data provenance, and a named exploration use.
No scalar "Mars-likeness" ranking — that is both prior art (Peña-Asensio et al. 2024)
and conceptually wrong per Foucher et al. 2021 (literature doc §7).

Why this is efficient: screening makes a global search tractable (solve on a subset,
prove the rest irrelevant, only re-add violators — the exact algorithm already proven
in the author's `fastopt`). Why this is unique: gaps 1, 3, 4, 5 of the literature doc.
Why it fits the brief: systematic global search, partial analogy formalized, process
data (EONET/GIBS time series) folded in, map-first deliverable, "surprise us" via
method rather than a lucky pin-drop.

## 2. What the author's GitHub history actually gives us (verified 2026-11-12)

`andrewkoumoudjian`: 45 public repos, bio "QUARCC-Umbrella Lead Researcher". Relevant, non-fork assets:

| Repo | Verified contents | Translated to this challenge |
|---|---|---|
| `QUARCC-Umbrella/quant-fund` → `fastopt/` | Python optimizer (`ipm.py`, `scenarios.py`, `portfolio.py`, `surrogate.py`, `allocation.py`…) **plus a Lean 4/Mathlib proof package** `fastopt/proofs/` (`lake-manifest.json`, `lakefile.toml`, `lean-toolchain`): `FastOpt/Screening.lean` proves `relaxation_exact`, `lower_model_exact`, `ru_restricted_le`, `ru_tight`, `cvar_screening_exact`, `wr_screening_exact` for the Rockafellar–Uryasev CVaR objective; `FastOpt/Certificate.lean` proves `subopt_le`, a dual-residual suboptimality bound. `PARITY.md`/`FORKFIAM.md` show a spec↔implementation parity discipline. | **The core.** Earth cells ↔ scenarios; environmental extremes ↔ tail losses; CVaR/worst-realisation ↔ "how bad is this site on its worst dimensions"; screening exactness ↔ certified elimination of Earth cells; certificate ↔ auditable error bound on every published score (propositions P5/P6 in brief doc). |
| `andrewkoumoudjian/qcelect` | "Live map of Quebec 2026 elections": bootstrap commit establishes "production/research boundary, ingestion contracts, static SVG UI architecture, Cloudflare serving path". | The map deliverable's architecture: research pipeline emits versioned static artifacts; Cloudflare serves them; no live NASA calls from the browser (required by catalog rate limits, catalog doc §3). Static-first also survives hackathon judging traffic. |
| `andrewkoumoudjian/bunting` (Rust, ~3.0 MB) | "A market engine deployable on rust workers, contains client and server packages." | Rust-on-Workers/WASM is proven in-house: the cell-scoring/screening engine can be one Rust crate compiled to native (batch) and WASM (in-browser re-weighting within the certified weight family). |
| `andrewkoumoudjian/footy-models` (Rust+Python) | Forecasting with explicit provider discovery, frozen SHAs, documented data gaps ("soccerdata/ClubElo/… gaps, frozen SHAs"). | The provenance discipline P8 demands: every dataset pinned by version/hash, gaps written down, not papered over. |
| `andrewkoumoudjian/searxflare` (Rust) | "a meta search engine built on wasm rust cf workers". | Federated catalog search pattern → one query surface over Earthdata CMR/STAC, PDS, USGS Astro STAC, Trek. |
| `QUARCC-Umbrella/quarcc-vault` (TypeScript) | "Private financial dataset library for QUARCC" with MCP/RLS proof work. | Dataset-library + agent-access patterns for the `data/catalog` package; agents query data through contracts, not ad-hoc downloads. |

Not translatable / don't drag in: trading semantics, sports models, mail/scraping
forks that fill most of the 45 repos. The reuse claim is **algorithms + architecture
+ discipline**, not code volume.

## 3. Lean verdict: verified kernel, not the implementation language

| Option | Verdict | Reason |
|---|---|---|
| Whole implementation in Lean | **No** | No GIS/raster/STAC ecosystem; ingest and map work would stall. Lean proves; it does not fetch tiles. |
| No Lean | **No** | Throws away the author's rarest asset and the cleanest originality claim (gap 3). "Certified" is otherwise marketing. |
| **Thin verified kernel (recommended)** | **Yes** | Port `FastOpt.Screening`/`FastOpt.Certificate` to an `Analog` namespace and prove three statements about *this* problem: (i) screening exactness for cell elimination under the declared weight family, (ii) the suboptimality/error certificate for published per-dimension scores, (iii) Pareto-dominance soundness (a dominated cell is never presented as frontier). Runtime (Rust/Python) must emit certificates the Lean statement covers; CI runs `lake build` and rejects `sorry`/`axiom` leakage. Mirrors the author's existing spec↔code parity pattern. |

Honest boundary to state in the submission itself: Lean certifies the *screening and
scoring logic*, never the geophysics. Dataset error stays an empirical question (P8).

## 4. Proposed monorepo layout (`cosmic-consultants`)

One repo, four toolchains kept in separate lanes (pnpm · Cargo · Lake · Python/uv),
contracts in the middle so agents never share mutable state — only versioned artifacts.

```
cosmic-consultants/
├─ README.md                  # one-paragraph pitch + links to docs/research, docs/proposals
├─ AGENTS.md                  # binding rules for every agent/human (§5)
├─ docs/
│  ├─ research/               # 01–03 (this delivery) — evidence, append-only
│  ├─ proposals/              # 04 (this file)
│  └─ decisions/              # ADR-0001… one decision per file, immutable once accepted
├─ contracts/                 # SINGLE SOURCE OF TRUTH between packages
│  ├─ site.schema.json        # Site, Dimension, AnalogyVector, Breakdown, Provenance
│  ├─ envelope.schema.json    # TargetEnvelope (Moon/Mars), WeightFamily
│  └─ certificate.schema.json # ScreeningCertificate, ScoreCertificate
├─ data/
│  ├─ catalog/                # dataset registry: one YAML per dataset (source, version, hash, license)
│  ├─ fixtures/               # golden validation sites (Haughton, Atacama, Death Valley…) as frozen JSON
│  └─ snapshots/              # fetched payloads, content-addressed, never edited by hand
├─ services/
│  ├─ ingest/     (Python/uv) # Earthdata/PDS/USGS/Trek/EONET fetchers → cells + snapshots
│  ├─ engine/     (Rust)      # screening + Pareto frontier; native batch + WASM build
│  └─ api/        (TS Worker) # serves versioned artifacts; the only holder of the NASA API key
├─ proofs/        (Lean/Lake) # Analog.Screening, Analog.Certificate, Analog.Pareto
├─ apps/
│  └─ atlas/      (TS)        # interactive map: GIBS (Earth) + Trek WMTS (Moon/Mars), site dossiers
├─ research/
│  ├─ corpus/                 # harvested bibliography (BibTeX) + dedup script output
│  └─ notebooks/              # exploratory only; nothing ships from here
└─ .github/
   ├─ ISSUE_TEMPLATE/work-order.md
   ├─ PULL_REQUEST_TEMPLATE.md   # evidence checklist (probe output, tests, proof status)
   ├─ CODEOWNERS                 # one owner-agent-role per top-level package
   └─ workflows/                 # ci: contracts codegen check, cargo test, lake build, ingest smoke
```

Dependency rule (enforced by review, stated in `AGENTS.md`): `apps → api → engine
artifacts`; `ingest → data/snapshots`; `engine → contracts + snapshots`; `proofs`
depend on `contracts` *statements* only. Nothing imports across a lane except through
`contracts/` schemas and versioned files under `data/`.

## 5. Multi-agent collaboration: Delta CLI vs GitHub Issues

Facts about Delta (from https://delta.dev/cli, fetched 2026-11-12): Beta product by
the Zed team; syncs **agent sessions** (conversation + a copy of the checkout including
uncommitted changes) to DeltaDB; a teammate `/delta join`s and their agent continues
with ~100k tokens of newest history; supports `delta thread search/query/fork`,
`delta worktree mount`; harness support is "**Starting with Claude Code. More coming
soon.**" It is a session-sharing/sync layer, not a task system: no assignment, states,
labels, CI gates, or public audit trail, and session content leaves the repo into DeltaDB.

| Criterion | GitHub Issues (+ PRs, Projects) | Delta CLI |
|---|---|---|
| System of record | Yes: durable, in-repo, judge-visible | No: external session store |
| Task state machine | Labels/assignees/milestones, enforceable | None |
| Works across harnesses (Claude/Codex/Muse/…) | Yes, via `gh` + files | Claude Code first; others "soon" |
| Session handoff (context + dirty tree) | Manual: handoff comment + branch | Native, excellent — its whole point |
| Reproducibility for SME judges | Full public trail | Invisible to judges |
| Maturity / lock-in risk | None | Beta, proprietary store |

**Recommendation: GitHub Issues as the message board and system of record; Delta as an
optional personal session-sync convenience, never load-bearing.** Operating protocol:

1. **One issue = one work order = one branch = one PR.** Issue template fields:
   objective, package (from `CODEOWNERS`), input artifacts (paths + hashes), output
   artifact, acceptance test/probe, propositions touched (P1–P8).
2. **Claim by assignment + `status:in-progress` label** before writing code; file
   ownership by package prevents two agents editing the same lane; cross-lane needs
   go through a `contracts/` change issue first.
3. **Handoff = PR description + closing issue comment** quoting real command output
   (tests, `lake build`, live probe). Unfinished work is handed off as a pushed
   branch + "state / next action / blocker" comment — readable by any harness,
   no Delta required. (If the team adopts Delta, `/delta share` links may be *added*
   to that comment; the comment remains sufficient alone.)
4. **Agents never push to `main`**; merge requires green CI (contracts, cargo, lake)
   and one review by a different agent role or the owner. `sorry` in `proofs/` fails CI.
5. **Decisions are files, not chat:** anything that changes scope, weights, datasets
   or architecture lands as `docs/decisions/ADR-*.md` in the PR that implements it.

## 6. Suggested sequence (after approval)

| Phase | Work orders (examples) | Exit evidence |
|---|---|---|
| 0. Refresh | A0: re-fetch brief + Resources + judging guides (2026-11-13); diff docs 01–02; harvest full corpus to `research/corpus/` | Dated diff note appended to docs 01–03 |
| 1. Contracts & fixtures | Schemas in `contracts/`; golden sites fixtures; dataset registry rows with live probes | CI codegen check; every registry row has a probe log |
| 2. Target envelopes | Moon south-pole + Mars reference envelopes from PDS/Trek data, cited per dimension | Envelope JSON validating against schema, sources attached |
| 3. Engine + proofs | Rust screening/Pareto over a coarse Earth grid; Lean `Analog.*` port proving exactness on the fixtures | Screening on fixtures retains Haughton/Atacama-class cells; `lake build` green, no `sorry` |
| 4. Atlas | Map app (GIBS + Trek side-by-side), per-site dossiers with analogy vectors and breakdowns | Deployed static build; every figure traceable to `data/snapshots/` |
| 5. Hardening | Sensitivity to WeightFamily, P4 novelty audit vs corpus, written report export | Audit table P1–P8 all green or explicitly waived |

## 7. Decisions — RESOLVED 2026-11-12 (see [ADR-0001](../decisions/ADR-0001-scope-collaboration-lean-first.md))

Owner's answers: (1) **both targets, same methodology**; (2) **whichever is better
for cross-agent collaboration** → GitHub Issues as system of record (§5);
(3) **methodology and its mathematics are defined and solved in Lean** — stronger
than the thin-kernel recommendation in §3: Lean is the specification/proof
authority and statements freeze before engine code or statistics (ADR-0001 gates).
Original questions kept below for the record.

1. **Scope:** Moon-only, Mars-only, or both targets? (Recommendation: **Moon south pole
   first, Mars envelope second** — "permanent Moon base" leads the title, and one
   target done with certificates beats two done thin.) And deliverable: atlas + dossiers
   as proposed, or a different first form?
2. **Collaboration:** GitHub Issues as system of record with Delta optional (recommended),
   Delta-first, or plain branches/PRs with no issue protocol?
3. **Lean:** thin verified kernel as in §3 (recommended), no Lean, or a larger formal
   scope (e.g. also formalize dimension/tolerance semantics before any engine code)?

On approval, Phase 0 starts 2026-11-13 when NASA publishes the Resources tab — building
dataset contracts before that risks rework against the official resource/judging guides.
