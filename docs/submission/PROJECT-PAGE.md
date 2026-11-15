# Space Apps project page: draft (W14, #25)

Status: **draft**, written 2026-11-14 at about 16:40 EST, before feature freeze.
Every sentence marked ⚠ describes a part that isn't built yet. At feature
freeze (Sun 16:00 local), each ⚠ line is either confirmed against the deployed
build or cut. Nothing here may claim more than the build does (AGENTS.md rule 2,
PITCH.md).

Submission fields follow the Space Apps project page and the team doc's
"FINAL DELIVERABLEs" tab: title, a 50–200 word summary, links (demo, code,
info), data used, tools and the AI disclosure.

## 1. Project name

**Owner decides** (open question 3 in MISSION-PLANNER.md). The placeholder is
*Proving Grounds*. Shortlist to pick from, or replace:

- Proving Grounds
- Analog Mission Planner
- Earth Rehearsal

No NASA logos, insignia or "NASA" in the name (doc 07 §1.1).

## 2. One sentence

Tell us what you want to test for the Moon or Mars, and when, and we take you
step by step to a field plan on Earth: where, which months, what it can and
can't rehearse, how to get there, what could go wrong, and who has done it
before.

## 3. Summary (50–200 words; this draft is 177)

> We built a mission planning tool for Moon and Mars analog field tests. A
> scientist picks one of NASA's Moon-to-Mars objectives, the target body and
> the months of the trip. The tool turns Moon and Mars target conditions into
> test requirements in Earth units and checks every one of 91,800 land
> hexagons on Earth against them, month by month. ⚠ It walks the scientist
> through six steps: objectives, site finder and compare, gaps, logistics,
> risks, and past analog missions, and ends with a one-page field plan.
> Each trait shows match, miss with its gap in real units, or unknown with
> the reason. It never adds traits into one "looks like Mars" score, because a
> great match on one trait would hide a bad one. It always lists what Earth
> can't test: gravity, air pressure and radiation. Every number links back to
> the NASA, ESA or partner file it came from, with its hash. That matters
> because analog sites are still picked mostly by tradition, and a site that
> suits a rover traverse can be wrong for ice coring.

Word count, checked: `wc -w` on the quoted text = 177 (re-check after edits).

## 4. Links

| Link | Value | Status |
|---|---|---|
| Demo (≤30 s video, or ≤7 slides) | ⚠ | #24 (pitch lane). Video locks Sun 19:00 |
| Code | https://github.com/andrewkoumoudjian/cosmic-consultants | Owner decides visibility. Judges must be able to open it |
| Deployed app | ⚠ | Needs W11b and a deploy |
| Info | `docs/plan/MISSION-PLANNER.md`, `docs/plan/DATA-PIPELINE.md`, `proofs/STATEMENTS.md` | on main |

## 5. Detailed description

**What it does.** ⚠ Six steps, one shareable link (the plan request lives in
the URL, `contracts/plan-request.schema.json`):

1. **Objectives.** Body, test category, NASA objective (OP-5LM, SE-3LM, LI-5L
   to start), months, length, team size and hard limits. Requirements are
   must or nice; nothing is weighted. A live counter shows 91,800 places →
   pass your limits → match every must requirement.
2. **Site finder and compare.** Each hexagon is "every requirement matches",
   "at least one miss" or "no miss but something unknown". Up to 3 sites side
   by side, month by month. The "top X" list uses Pareto layers (a place is on
   layer 1 if no other place is at least as good on every trait and better on
   one), so there's no single score.
3. **Gaps.** Per trait, match, miss with the gap in real units, or unknown with
   the reason. Plus what Earth can't test for this objective.
4. **Logistics.** Travel time to a city, nearest paved-runway airport, the
   protected-land share, and the field-season months.
5. **Risks.** Natural events NASA EONET recorded nearby, by type and month,
   with EONET's own caveat that it's a curated list. Also steep ground and
   temperature extremes. Each hazard is its own flag, with no combined risk score.
6. **Past missions.** Cited analog campaigns (HMP Haughton, MDRS, FMARS,
   HI-SEAS, Desert RATS, ARADS Atacama), with quoted outcomes and a
   closeness bar split by trait (Shapley values).

**What Earth can't rehearse (challenge "Remember Earth's limits").** Gravity,
the lunar vacuum and thin Martian air, and the radiation environment are
permanent mismatches. They're listed on every plan and never scored.

**How the data works.**
- Earth's land is cut into 91,800 equal-size H3 hexagons (about 1,770 km² each).
- Each hexagon gets measured traits from satellite data, yearly and per month
  of 2023. Missing values stay missing, with a reason.
- Moon and Mars conditions come from cited sources and become Earth-unit test
  bands. Each band states its basis and caveat (`data/requirements/trait-map.yaml`).

**Why it's trustworthy.**
- Every number traces to a stored source file with URL, date, licence and
  sha256 (`data/snapshots/MANIFEST.json`).
- The rules for verdicts and the Shapley split are written as Lean theorems
  before the code computes them: `proofs/Analog/Funnel.lean` (S7) and
  `proofs/Analog/Closeness.lean` (S8). ⚠ The status of S7/S8 at submission
  time must be copied from `proofs/STATEMENTS.md`: proposed, frozen or proved.
- A proof covers the logic only. It does not show that any value or band is
  scientifically right.

**Honest limits.**
- Values are means over a hexagon, not along a traverse.
- Some traits have no Earth or target data yet: dust bands, the Mars thermal
  band, the lunar cold-trap temperature, caves and subsurface. These show as
  unknown, never as bad.
- EONET counts are not hazard rates.

## 6. NASA data used

See [DATA-USED.md](DATA-USED.md). The Global Awards rule needs at least one
dataset from the challenge's Resources tab. **LRO Diviner** (Moon) is on the
Resources tab, and we downloaded, hashed and decoded it (#74/#75). NASA Earthdata
(MODIS) and NASA PDS (MGS TES) are also on the tab as portals.

## 7. Space agency partner data

ESA: Copernicus DEM GLO-30 and ESA CCI Permafrost (Copernicus Data Space and
the ESA Open Science Catalog are on the tab). CSA and JAXA resources were
inventoried (`data/sources/agency-portals.yaml`, #74) but don't feed a
published number. ⚠ Confirm at freeze.

## 8. Tools, code and other resources

See [TOOLS.md](TOOLS.md). It includes the owner's prior work, listed as prior
work: the Lean corpus under `proofs/Analog/Prior/` and the FastOpt screening
proofs (`proofs/Analog/Screening.lean`).

## 9. AI disclosure

[`AI-USAGE.md`](../../AI-USAGE.md) is the descriptive text; commit trailers and
the #6 check-ins are the metadata. Any AI-generated image or video in the demo
carries a visible "AI-generated" watermark.

## Freeze checklist (from PLAN-hackathon.md, kept in sync by #25)

- [ ] Project name picked by the owner
- [ ] Summary re-checked against the deployed build, 50–200 words
- [ ] 30-s video link (no NASA logos, no minors, AI imagery watermarked)
- [ ] Code link reachable by judges (owner sets repo visibility; LICENSE decided)
- [ ] Every ⚠ line confirmed or cut
- [ ] DATA-USED.md statuses re-probed (rule 2: counts and statuses at use time)
- [ ] AI-USAGE.md table complete (every agent that checked in on #6)
- [ ] Every number on the page traceable to `data/snapshots/`
- [ ] Submitted with a screenshot by Sun 22:00 local (2 h before the 23:59 deadline, which is still unverified)
