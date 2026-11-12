# 07 — Space Apps forum rulings + NASA Moon-to-Mars Objectives (sources for the plan)

Fetched 2026-11-12 (~19:20 UTC). Research only. Two sources the hackathon plan
([`PLAN-hackathon.md`](../PLAN-hackathon.md)) and
[ADR-0002](../decisions/ADR-0002-analog-readiness-levels.md) depend on.

## 1. Space Apps Connect forum (`github.com/nasa/spaceapps` → Discussions)

The repo itself is only a README (terms + code of conduct). All content is in
Discussions: categories *Announcements, Challenges, Find A Team, General,
Global Offers, Project Submission Help, Universal Event* (199 threads at fetch
time). The *Challenges* category is where challenge-specific questions go
(title must start with the challenge name). Probe:
`gh api graphql … repository(owner:"nasa",name:"spaceapps"){discussionCategories …}`.

### 1.1 Rulings by organizers (`*-GO-Team` accounts), quoted verbatim

| Thread | Author, date (UTC) | Ruling |
|---|---|---|
| [#1821](https://github.com/nasa/spaceapps/discussions/1821) | FrancesAdiele, 2026-11-05 (same wording as GO-team posts below) | "If you use a library it must be open-source, but if it is something you created you can use it as a reference. When you submit your project, you must list all of the data, resources, and tools that you used… Resources should include any code, text, and images (even if they are open source or freely available)." |
| #1821, [#1861](https://github.com/nasa/spaceapps/discussions/1861), [#1827](https://github.com/nasa/spaceapps/discussions/1827), [#1777](https://github.com/nasa/spaceapps/discussions/1777) | CarolynW / Paula / Nick -GO-Team | "teams refrain from starting on their projects until the start of the official November 14-15 hackathon (Saturday, 9am local time of your Local Event; if Universal Event, start time is Saturday, 9am of the Team Owner's area of residence). Working ahead of the hackathon can lead to disqualification. However, before the hackathon starts, you may select a challenge to work on, review the resources, research the topic, and form your team" |
| [#1872](https://github.com/nasa/spaceapps/discussions/1872) | Nick-GO-Team, 2026-11-09 | "I would hold off on discussing features or sketching out UI as working ahead of the hackathon can lead to disqualification and the removal of any awards your project wins." |
| [#1787](https://github.com/nasa/spaceapps/discussions/1787) | Nick-GO-Team, 2026-11-04 | "We do not expect you to have a completely finished, fully-developed solution… we want you to be able to demonstrate progress toward a solution… using dummy data or a mock API is completely fine!" |
| [#1849](https://github.com/nasa/spaceapps/discussions/1849) | Nick-GO-Team, 2026-11-06 | "In order to be eligible for Global Awards, **you must use at least one NASA data source** that is included with the Resources of each challenge." AI permitted; generated content "may not use, contain, or modify any NASA branding or design elements"; disclose AI use: images/videos "visible watermark", audio and "**Code and data: Must acknowledge AI generation in descriptive text and metadata.**" "Our judges will consider originality, intent, and execution in the context of AI-assisted work." |
| [#1857](https://github.com/nasa/spaceapps/discussions/1857) | CarolynW-GO-Team, 2026-11-09 | "There is a **30-second limit for project demonstration videos**." Longer material goes in as a separate project link (no length limit). "The project demo is one of the first things judges will review." No recognizable names/voices/likenesses of persons under 18. |
| [#1920](https://github.com/nasa/spaceapps/discussions/1920) | Janelle-GO-Team | Submission and judging guides go live Friday 2026-11-13: `spaceappschallenge.org/resources/project-submission-guide`, `…/resources/judging-awards-guide`. |

Community (non-organizer) answer, **unverified**: deadline Sunday 2026-11-15
23:59 local ([#1955](https://github.com/nasa/spaceapps/discussions/1955)).
Confirm in the submission guide (issue #1, A0).

### 1.2 Consequences for this repo (owner position 2026-11-12: current work is research + setup)

- Owner states the pre-14th work is topic research and setup. To keep that
  defensible: (a) list the owner's prior Lean corpus (`proofs/Analog/Prior/*`,
  ported FastOpt screening/certificate) as **prior work used as a reference
  library** in the submission's resources list, and make it open-source;
  (b) no app/UI/engine/ingest code before 2026-11-14 09:00 local; (c) the
  submission text says plainly what existed before the window.
- AI disclosure is mandatory for code and data → `AI-USAGE.md` + commit
  trailers (already present) + a line in the submission description (backlog W14).
- Any NASA data source we lean on must be one **listed in the challenge
  Resources tab** → A0 (#1) gates the dataset choice for the Global-Awards path.

## 2. NASA Moon to Mars Objectives (September 2022)

Source: <https://www.nasa.gov/wp-content/uploads/2022/09/m2m-objectives-exec-summary.pdf>,
HTTP 200, 3,393,404 bytes, sha256
`40b5af872fc5a3fd2eb79dad9b17b00f8af4fa241a636b6711dd0097ee66aca3`
(fetched 2026-11-12T19:18Z; to be snapshotted into `data/snapshots/` by the
data lane — this doc only records the probe). Also probed: Architecture
Definition Document Rev A (`rev-a-acr23-esdmd-001-m2madd.pdf`, 200, 74.8 MB,
sha256 `816349b2…4e6b`), which decomposes these objectives into use cases.

9 recurring tenets (RT-1…9) plus 63 objectives in 10 goal families, counted
from the PDF text: LPS 4, HS 4, HBS 3, PPS 2, SE 7, AS 6 (science); LI 9,
MI 4 (infrastructure); TH 12 (transportation & habitation); OP 12 (operations). Superscript L/M/LM marks lunar, Martian or both.

**The objective that licenses this project's pitch, verbatim:**

> **OP-1L:** "Conduct human research and technology demonstrations on the
> surface of Earth, low-Earth orbit platforms, cislunar platforms, and on the
> surface of the moon, to evaluate the effects of extended mission durations
> on the performance of crew and systems, reduce risk, and shorten the
> timeframe for system testing and readiness prior to the initial human Mars
> exploration campaign."

Also: **TH-3L** names "Mars analog activities" on the lunar surface — so the
Moon is itself treated as a Mars analog.

### 2.1 Objectives with an Earth-testable surface component (candidate v0 set)

Verbatim objective text is in the PDF; the "dimensions" column is **our
proposal** (maps onto the frozen `contracts/` dimension enum) and becomes data
only via backlog W10 with review.

| ID | Objective (shortened) | Earth-testable component | Required dimensions (proposed) | Not testable on Earth (permanent mismatch) |
|---|---|---|---|---|
| OP-5LM | Operate surface mobility systems (EVA suits, tools, vehicles) | Traverse + EVA procedures on rough, dusty, unvegetated terrain | terrain, surfaceMaterial, dustProcess, thermal | gravity (suit/vehicle dynamics), pressureRegime (dust charging, suit pressure) |
| LI-5L | Precision landing | Hazard-detection / terrain-relative-navigation tests at low sun angle | terrain, illumination | gravity, pressureRegime (plume-surface interaction) |
| LI-6L / TH-7M | Surface mobility / explore-operate-live | Long rover traverses, navigation without GPS-like aids | terrain, surfaceMaterial, operations | gravity |
| SE-3LM | Core frozen volatiles (PSRs / Mars ice) | Drilling/coring frozen ground in cold, dark conditions | waterIce, thermal, subsurface, illumination | pressureRegime (sublimation), radiation |
| AS-3LM / OP-3LM / LI-7L / MI-4M | Characterize resources; ISRU | Prospecting + ISRU trials on basaltic/anorthositic or icy ground | surfaceMaterial, waterIce, subsurface | pressureRegime, gravity |
| LPS-4M | Habitability and evidence of life | Biosignature-instrument tests in hyperarid / evaporite / cold settings | surfaceMaterial, thermal, waterIce, dustProcess | radiation (surface sterilization) |
| LPS-1/LPS-2 + SE-1LM | Impact chronology, geologic processes; crew science training | Field-geology training at impact / volcanic structures | terrain, surfaceMaterial | — (training transfers fully) |
| LI-1L | Power generation | Solar-array ops under low-elevation, horizon-skimming sun | illumination, terrain, thermal | radiation, pressureRegime (thermal balance) |
| OP-2LM / SE-2LM | Ops with comm delay; Earth-based science support | Isolated, remote field ops with simulated latency | operations | — |

Not Earth-testable at all as a primary objective (shown as such, never
rated): HBS-1 (biological effects of the space environment), AS-6/OP-6
(partial-gravity effects), PPS-1 (radio-quiet far side), HS-* (heliophysics).
Showing these honestly is part of the pitch ("what Earth cannot rehearse").

## 3. Prior art for a readiness ladder on analog sites (search 2026-11-12)

No published "analog readiness level" scale was found. Nearest work, to cite:

- Stern et al. 2025 (JGR Planets; summary at
  [astrobiology.com](https://astrobiology.com/2025/01/06/a-comprehensive-framework-for-assessing-terrestrial-analogue-field-sites-for-ocean-worlds/)):
  science question → required processes/parameters → site match, with a
  matrix + radar charts. Our ladder is the evidence-staged, mission-objective
  version of the same idea.
- Lee et al. 2010, via the
  [terrestrial analogue site overview](https://en.wikipedia.org/wiki/Terrestrial_analogue_site):
  fidelity "for the usage sought" is the key criterion; fidelity scored per
  aspect (geomorphological, geochemical, exobiological, exploration).
- NASA report [NTRS 20000105009](https://ntrs.nasa.gov/citations/20000105009):
  importance of each site characteristic depends on the planned activity;
  use lower-fidelity sites early in development, higher-fidelity later — the
  explicit link between analog fidelity and technology maturation (TRL).
- [Frontiers in Space Technologies 2025](https://www.frontiersin.org/journals/space-technologies/articles/10.3389/frspt.2025.1391331/full):
  low/mid/high/"peak" fidelity tiers for human-factors analog scenarios.

To be pulled into `research/corpus/` by W4 (#5) with DOIs.
