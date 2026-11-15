# Mission workflow acceptance checklist

Work order: [#136](https://github.com/andrewkoumoudjian/cosmic-consultants/issues/136).
For the integration owner of [#132](https://github.com/andrewkoumoudjian/cosmic-consultants/issues/132).
Written 2026-11-14 (America/Toronto). **Test plan only; no workflow case below has been executed by this document's author.**

## Sources and boundaries

The baseline is main `e4925899150634819a4a170202e15b7b5723b9e7`:
[workflow](../plan/MISSION-PLANNER.md), [pipeline](../plan/DATA-PIPELINE.md),
[trait map](../../data/requirements/trait-map.yaml),
[ADR-0005](../decisions/ADR-0005-mission-planning-workflow.md), and
[EONET policy](../decisions/ADR-0006-eonet-for-risks.md).
These specify intent; they do not prove that the current app implements it.
The baseline app still contains the older readiness map. Use the integration
owner's documented planner entry point, not an assumed URL or command.

Dependencies reviewed for this checklist (recheck their revisions before a run):

| Dependency | Pinned revision | What it supplies |
|---|---|---|
| [#79](https://github.com/andrewkoumoudjian/cosmic-consultants/pull/79) | `d11885486068d490e1bc1170e34904bb8c631cd8` | Request and site-plan contracts; still a PR at review time |
| [#84](https://github.com/andrewkoumoudjian/cosmic-consultants/pull/84) | `f4adc058a063ee44e7ceb10ec8c77b8e776233ac` | S7/S8 statements; proof acceptance is a separate gate |
| [#122](https://github.com/andrewkoumoudjian/cosmic-consultants/pull/122) | `cfce8b48b647c6e13668abb8c653b1895e6b8220` | URL codec |

The [#132 freeze record](https://github.com/andrewkoumoudjian/cosmic-consultants/issues/132#issuecomment-6888097788)
records S7's statement hash and the strict-boundary mismatch with #79.
Its zero-gap contract correction and common Float32 input policy are integration
dependencies, not decisions made by this checklist. Do not silently relax a schema
or invent a numeric tolerance to make a case pass.

## Run receipt

Copy this into the test report. Keep each case's result as **pass**, **fail**,
**blocked**, or **not run**, with the observed output and an evidence link.

```text
Date/time and tester:
App URL/entry point and commit:
Engine commit; contract revisions; statement/proof acceptance references:
Browser/version; engine/runtime version:
Mode: synthetic / real (run separately)
Build-manifest path and SHA-256; recorded input/output hashes:
Plan URL; request JSON; selected site IDs:
Cases: ID | result | observed value/message | screenshot/log/export path
```

Use developer-provided fixtures in an isolated test build for the synthetic cases.
The values below are invented test inputs, **not observations or site claims**.
Never edit a snapshot, a production artifact, or a real site's values to force a case.
If fixture injection is unavailable, mark those cases blocked and retain the inputs
for the engine/browser conformance suite. A mock pass does not satisfy real-data acceptance.

Start with this request; omit optional fields to keep the test small:

```json
{"version":1,"body":"mars","objectiveId":"OP-5LM","missionType":"robotic","months":{"start":6,"end":8}}
```

Its query is `?body=mars&obj=OP-5LM&type=robotic&months=6-8`.
Repeat the real-data journey with `body=moon&obj=LI-5L&type=instrument&months=11-2`.
All unmentioned fixture requirements match; explicit priority overrides must be
recorded so the trait map's defaults cannot change the meaning of a test.

## Core cases (P0)

| ID | Setup and action | Done when | Capture |
|---|---|---|---|
| C01 | Open each starting request above. Inspect the selected body, objective, mission type and months. | Inputs agree with the request; every objective requirement appears once with its unit, band origin and caveat. A missing band remains visible. | Request and requirement rows |
| C02 | Make terrain **must**, with band `[0,5]`; synthetic sites A/B/C have terrain values `5`, `6`, and `null` with a reason. | A matches; B misses with gap `1 deg`, side above; C is unknown with its reason. Classes are respectively allMatch, someMiss, noMissSomeUnknown. Null is neither zero nor match. | Engine and browser rows for all three |
| C03 | At value `5`, switch `[0,5]` to `[0,5)` using `hiStrict: true`. | Verdict changes from match to miss with geometric gap `0`. It stays a miss in the UI/export; schema validation passes under the corrected contract. **Blocked until #132's contract correction is available.** | Exact input, verdict and validator output |
| C04 | Supply a known value but a null band; separately supply a null Earth column. | Both remain unknown with the applicable missing-band/column explanation; no number or threshold is invented. | Rows and reasons |
| C05 | Synthetic monthly thermal band `[0,10]`; Jun/Jul/Aug values `5/null/11`, then `5/null/6`, then `5/6/7`. Thermal is must. | Aggregate verdicts are miss (worst gap `1`), unknown, match respectively; each selected month is retained. A miss takes precedence over an unknown month. | Per-month and aggregate rows |
| C06 | Select months `11-2`; place an out-of-band value in January and another in June. Then select `6-8`. | First run uses Nov, Dec, Jan, Feb, including January's miss and excluding June; second uses only Jun, Jul, Aug. No annual value substitutes for monthly data. | Selected month keys and verdicts |
| C07 | Set access max `240`; synthetic access values `240`, `241`, null. | Outcomes are pass, fail, unknown. Known failure is filtered; unknown is flagged and is not filtered by this limit alone. It is not labelled reachable or approved. | Limit rows and eligibility |
| C08 | With identical hard limits, move an out-of-band terrain requirement from must to nice. | Its miss stays visible but no longer disqualifies the site on that requirement. Nice rows do not change the must-only funnel class. | Before/after rows and class |
| C09 | On one fixed artifact set, tighten `[0,5]` to `[0,4]`, then add a must requirement. Compare surviving site IDs. | Each new surviving set is a subset of the previous set. Compare sets, not counts alone. Do not require the Pareto shortlist itself to be a subset. | Sorted IDs or hashes plus set differences |
| C10 | Give fully known eligible sites two gap vectors A=`(1,3)`, B=`(3,1)`, C=`(4,4)`; test shortlist logic separately from must-miss filtering. | A/B are non-dominated; C is in a later layer. In the full workflow a site failing a must requirement stays filtered, regardless of this ranking example. No sum of gaps ranks sites. | Candidate domain, layers and sort trait |
| C11 | Encode, reload and decode a request with `must=terrain`, `band=terrain:0..5%3C`, `months=11-2`, `top=20`. Also try duplicate `body` and `months=13-2`. | Valid fields and strictness survive reload; malformed links give errors without silently using defaults. Compare canonical semantics: omitted versus null top, false strictness and empty optional lists may normalize. | Original/query/decoded request and errors |
| C12 | Pin IDs `842a107ffffffff`, `8428309ffffffff`, `84be8d9ffffffff` in the test build, then pin a fourth available cell. | At most three compare columns appear; a fourth pin replaces the oldest with feedback. Shared links restore the pins. If those cells are absent, use three recorded IDs from the loaded artifact. | IDs/order, URL and compare screenshot |
| C13 | Inspect the same site in finder, compare, gap card and brief under one request. | Units, values, month selection, verdicts and reasons agree everywhere. The objective's Earth limitations remain visible: gravity, pressureRegime and radiation where listed; pressure reads as lunar vacuum or thin Martian air as appropriate. | Four surfaces for one site |
| C14 | Disconnect artifact loading or force an unavailable artifact; separately choose limits that exclude every known candidate. | Load failure shows an error/retry state and does not label stale results current. Empty results explain the failed limits rather than drawing a fake best site. A no-data cell stays unknown. | Error and empty-result screens |
| C15 | Export from step 1, then after selecting/comparing sites and visiting supported later steps. | Brief identifies objective, months, sites, requirement rows, limitations and sources. Unvisited/unavailable sections say not checked/unknown rather than vanishing or receiving invented values. Scientist notes are attributed. Export content agrees with the active request. | Both exported files and source request |

C10 tests the ranking helper's known candidate domain; it does not prescribe how
unknown gaps participate in Pareto layers. That policy must come from the accepted
contract/implementation. Mark unknown-ranking checks blocked if it is unspecified.
The large-integer codec issue is tracked in the [PR #122 review](https://github.com/andrewkoumoudjian/cosmic-consultants/pull/122#issuecomment-6888178326);
it is a separate low-priority boundary test, not a reason to invent integer bounds here.

## Supported later steps and real-data release

| ID | Setup and action | Done when | Capture |
|---|---|---|---|
| R01 | For synthetic months, use `(mustTraitsMatch, reachable)` values `(true,true)`, `(true,null)`, `(null,true)`, `(false,true)`. | Only the first is a field-season month. The strip has all twelve distinct months; unknown reachability is not green. | Season JSON and strip |
| R02 | Open an EONET row with zero recorded events, then one with an event. Open burned-area data for selected months. | Zero reads none recorded in EONET, not safe/no events happened. Event names/dates and source links are visible. Burned area has its native unit and missing reasons; no hazard probability, rate or combined score appears. | Risk rows, disclaimer and links |
| R03 | If step 6 is enabled, compare cited campaigns under a fixed recorded trait set, including a campaign missing one required trait. | Ranked campaigns cover the same trait set; missing-trait campaigns are separate. Shares sum to closeness under the accepted numeric policy; zero-spread/binary traits show same/different. Without accepted S8 proofs or required data, mark blocked, not passed. | Campaign sources, trait set, scales and shares |
| R04 | Run both body requests against one verified real build, without fixture overrides. Compare engine and browser on identical published numeric values, including a non-exact decimal such as a published Float32 value near a band edge. | Both complete; verdicts/classes/months/gaps agree under #132's accepted numeric policy. Record exact disagreements; no new tolerance is introduced by this checklist. | Engine output, browser output, golden comparison and hashes |
| R05 | Trace one numeric verdict, one unknown and one exported source reference back through the build manifest to their recorded inputs. | Hashes match actual files; unknown retains its reason; the brief identifies the data build. Synthetic mode has a persistent mock label and cannot pass as a real run by merely removing the banner. | Hash commands/results and export |

## Reporting the result

Report C01–C15 and R01–R05 separately. P0 requires the core journey and real-data
checks R04/R05 for both bodies; R01/R02 apply when their steps are included.
R03 is the plan's P1 precedent feature. Missing P1 work is explicit, not a false P0
failure or a completed feature. Unavailable P0 behavior remains a release gap.

Attach actual build/test logs and the integration owner's pinned Lean build and
audit receipts before claiming runtime conformance to accepted proofs. This document
provides neither a new proof acceptance nor scientific validation of datasets, bands,
terrain scale, site safety or field access. Do not label mock results scientific evidence.
