# Pitch and demo script

Working title: **Proving Grounds — Plan Moon and Mars field tests on Earth**.
The product name remains a placeholder for the owner to approve.

Status: **draft copy and storyboard, not a recorded video**. Updated 2026-11-15
(America/Toronto), work order [W13 #24](https://github.com/andrewkoumoudjian/cosmic-consultants/issues/24).
The original copy landed through [#143](https://github.com/andrewkoumoudjian/cosmic-consultants/issues/143).
The selected submission build now has an independently replayed capture route:
[receipt, screenshots and downloaded brief](submission-capture-2026-11-15/README.md).
This replaces the obsolete ARL pitch with the workflow in
[ADR-0005](../decisions/ADR-0005-mission-planning-workflow.md) and the
[mission plan](../plan/MISSION-PLANNER.md). It changes no scientific rules.

## What to say

**One-liner:** Plan a Moon or Mars field test on Earth: choose the objective
and months, compare the requirements, and carry the matches, gaps and unknowns
into a sourced mission brief.

**Short spoken story, after the capture checks below pass:**

“A field test needs a clear question: what are we trying to rehearse, and when?
Proving Grounds starts with a Moon or Mars objective and a month window. We
compare Earth sites against the test requirements, one trait at a time.

“A requirement can match, miss with a gap in its own units, or remain unknown.
We keep the missing evidence visible. You can compare candidate sites, inspect
the limits of the analogy, and export a brief with the requirements and sources.

“Earth cannot reproduce lunar or Martian gravity, air pressure and radiation.
This helps a team plan a particular field test; choosing and authorizing a real
campaign still needs field checks, permissions and scientific review.”

## Evidence behind the script

Capture rehearsal: 2026-11-15, using the owner's selected
[submission planner](https://cosmic-planner-submission.pages.dev/planner).
The served release manifest SHA-256 is
`2cd4e1899bc6111dbe0c3c6251b1392ab4fa1fdf673cc6ea86542c52b1e4b0fe`.
The [owner's deployment post](https://github.com/andrewkoumoudjian/cosmic-consultants/issues/6#issuecomment-6897826199)
identifies app `6d6cf35` and engine `ae2b3ce`; those commit labels are reported
deployment metadata, not recovered from a browser display. The manifest hash
was independently fetched and matched to the downloaded brief.

| Claim or screen | Source | Evidence and capture rule |
|---|---|---|
| Objective/month controls, comparison, brief download and unknown requirement | [Capture receipt](submission-capture-2026-11-15/README.md) | Independently replayed Moon / Robotic mobility & navigation / LI-5L / January. Selected one match, inspected unknowns in the list, opened limitations/logistics/risks and downloaded the brief. Month controls were observed at their January defaults; changing months and restoring a shared URL were not tested in this pass. |
| Match/miss/unknown, native-unit gaps, no combined site score | [ADR-0005 D2–D4](../decisions/ADR-0005-mission-planning-workflow.md), [trait map](../../data/requirements/trait-map.yaml) | Governing rules and proposed bands. Verify the displayed rows, origins and caveats; these files alone are not runtime tests. |
| Lean and Python/browser agreement | [Implementation-session evidence](https://github.com/andrewkoumoudjian/cosmic-consultants/issues/6#issuecomment-6888310833), [Lean gates](../decisions/ADR-0001-scope-collaboration-lean-first.md) | Session-reported build/audit and conformance results. Link the actual release receipts for detailed proof claims; do not call the whole application or geology formally verified. |
| Sources and hashes | [Pipeline](../plan/DATA-PIPELINE.md), [snapshot manifest](../../data/snapshots/MANIFEST.json) | Trace the displayed example to actual stored inputs before saying it is sourced. A catalog entry is not evidence of complete coverage. |
| Physical limits | [ADR-0005 D4](../decisions/ADR-0005-mission-planning-workflow.md) | Show the objective's applicable list. pressureRegime covers lunar vacuum and thin Martian air; do not imply Earth reproduces either. |
| Logistics, season, hazards and past campaigns | [Workflow steps 4–6](../plan/MISSION-PLANNER.md) | Include only what the recorded build supplies. Unavailable sections stay labelled; planned features are not delivered features. |

The earlier preview's TLS failure is historical. The public submission site
loaded in this rehearsal. The separate dark `mission-ui` preview still has
sample data; it is not the build selected for this capture. Recheck #6 and the
served manifest before recording, since deployment contents can change.

## Thirty-second capture storyboard

Record the actual release. These are intended shots: a failed capture gate
means revise the shot/script or leave the video unready.

| Time | Actual screen action | Voiceover |
|---|---|---|
| 0–5 s | Destination: Moon; Category: Robotic mobility & navigation | “Where on Earth can we rehearse a Moon or Mars mission?” |
| 5–12 s | Requirements: LI-5L, January; show terrain and illumination bands | “Choose the objective and months. Compare Earth sites against your test requirements.” |
| 12–20 s | Sites: select a match, then show Unknown in the group menu | “See what matches and what the data cannot tell you.” |
| 20–25 s | Limitations: keep gravity, pressure, radiation and the water-cover caveat visible | “A match still needs field checks. Earth cannot reproduce every condition.” |
| 25–30 s | Risks: Download brief; show the saved Markdown file | “Export the evidence and gaps into a field-test brief.” |

The slots total **30 seconds**, including the title card. Use one consistent
request/site selection across compare, gaps and export. Open the downloaded
brief to check its contents. Avoid a live result count or a named “best site”
in the voiceover. Rehearse narration against the slots before recording.
This is an edited sequence of real screens, not a promise that the full flow
loads in 30 seconds. Unknown-site Compare controls were disabled in the
rehearsal: show those rows in the Sites list rather than staging an unknown
inside the comparison. The first listed match had 95% water cover, so do not
present it as a recommended field site or crop away its warning. Show the
source-QA caveats in the longer walkthrough. The brief currently omits the
water-cover warning; show that warning on screen and say that the brief needs
to be read alongside the reports.

## Two-to-three-minute walkthrough

1. **Set the question (about 25 s).** Select Mars OP-5LM or Moon LI-5L in the
   recorded release. Explain the months and one band's origin: target,
   precedent, team or user. Do not describe every band as NASA's choice.
2. **Compare (about 40 s).** Explain one match and one miss or unknown with
   its unit/reason. Use three-site comparison only if the release supports it;
   otherwise state the limit rather than staging a fake drawer.
3. **Change a requirement (about 30 s).** Change a band or month window and
   show the actual response. A shortlist depends on stated requirements; it
   is not a universal Moon/Mars-likeness score.
4. **Explain the limits (about 25 s).** Show what Earth cannot test and one
   missing measurement or scale caveat. Mean slope over a hexagon does not
   certify every traverse within it.
5. **Carry evidence forward (about 30 s).** Export the brief; point to the
   active objective, months, sites, limitations and one traceable source.
   Show unavailable later sections as unavailable rather than filling them.

These segments total about 150 seconds. Add logistics, hazards or a cited
campaign comparison only if supported by the capture, trimming another
segment to keep focus. This is separate from the 30-second video.

## Judge Q&A

- **Who is it for?** Teams planning rover, instrument or human field rehearsals.
  It organizes candidate-site evidence and open questions for a particular test.
- **Who chooses the requirements?** Each band records its origin and rationale.
  Some are team choices or proxies; edits are user choices. Even a sourced
  number may have the wrong spatial or temporal scale for a particular test.
- **Is it a site similarity score?** No. Comparison stays per trait. Where the
  release uses Pareto layers, they order trade-offs without adding the traits
  into a site score.
- **What if data is missing?** It stays unknown with its reason. That is neither
  a match nor proof a site is unsuitable. A missing band is also unknown.
- **What does Lean establish?** It checks stated mathematical rules under their
  assumptions. Release-specific build/audit and engine/browser tests support
  the runtime claim within their scope. They do not certify source data,
  ecological impact, field safety or a team's chosen threshold.
- **Can Earth reproduce the Moon or Mars?** Only selected characteristics and
  processes for a stated test. Gravity, pressure and radiation remain limits.
- **Can a matching site host a campaign?** Access, permissions, costs, hazards
  and field measurements need separate review. EONET's zero recorded events
  is not a safety finding ([ADR-0006](../decisions/ADR-0006-eonet-for-risks.md)).
- **Did known analogs validate the system?** The separate
  [calibration report](../qa/CALIBRATION.md) records a limited check against
  known campaigns. This capture does not rerun or establish that result.
  A fixture or cited past campaign is not independent method validation.
- **What comes next?** Identify the selected test's source gaps and field
  checks, validate them with campaign teams, then expand requirements when
  the evidence and proof gates are ready.

## Recording and release receipt

Before recording, save the app URL/commit, release manifest SHA-256, request
JSON/share link, site IDs, capture date, supported steps and exported brief.
Match one shown value and one unknown to their source/reason. Record synthetic
versus real data; keep the mock label in every synthetic shot. The
[#136 acceptance checklist PR](https://github.com/andrewkoumoudjian/cosmic-consultants/pull/137)
can guide checks; it is a test plan, not evidence that a release passed.

Before publication, W13/W14 owners check the current submission guide, measure
final duration (for example, `ffprobe -v error -show_entries format=duration -of default=noprint_wrappers=1:nokey=1 demo.mp4`),
test the project link without private network access, and review captured
features and source/AI disclosures. The
[organizer-ruling inventory](../research/07-spaceapps-rules-and-m2m-objectives.md)
is dated research, not a fresh check of submission rules. Keep NASA branding
and insignia out of generated material, retain required AI watermarks and
exclude minors' recognizable likenesses/voices under the team's recording
constraints. This copy is AI-assisted and needs team review.

Do not claim first-ever novelty, complete Earth coverage, a universally best
site, field safety, mission approval odds, completed calibration or scientific
acceptance without separate evidence. Do not show the retired ARL ladder as
the current product. Video, deck, final captures and submission remain
outstanding W13/W14 deliverables.
