# Submission capture rehearsal — 2026-11-15

The public submission planner loads and its brief downloads. This is a
recording rehearsal for #24, not a finished video or scientific acceptance.
Codex / GPT-6 (exact serving ID not exposed) / Codex desktop / provider OpenAI /
Derek Gallagher (@Derick12345678). No application or deployment was changed.

## Build and request

- URL: <https://cosmic-planner-submission.pages.dev/planner>
- Observed on 2026-11-15, approximately 17:03–17:08 UTC.
- Served [build-manifest.json](build-manifest.json): 10,953 bytes, SHA-256
  `2cd4e1899bc6111dbe0c3c6251b1392ab4fa1fdf673cc6ea86542c52b1e4b0fe`.
  This matches the source hash printed in the downloaded brief.
- Request: Moon; Robotic mobility & navigation; LI-5L; January; robotic;
  14 days; team 6; terrain and illumination required; no custom hard limits;
  show 50. Both bands stayed at their defaults.
- Selected cell: `8401b65ffffffff`, displayed as 68.6°N 54.6°E. This is a
  demonstration of a conditional trait match, not a site recommendation.
- Browser URL after reaching Risks:
  <https://cosmic-planner-submission.pages.dev/planner?body=moon&obj=LI-5L&cat=robotic-mobility-navigation&type=robotic&months=1-1&days=14&team=6&must=terrain,illumination&sort=terrain&top=50&pins=8401b65ffffffff#step=7>
  Copy link was clicked, but clipboard reading returned empty. URL restoration
  was not tested. Do not treat this URL as a passed share-link round trip.

## Actual observations

These counts describe this request and release only. They are not new
calculations or independent checks of the source datasets.

1. Destination and Category opened. The category resolved to LI-5L.
2. [Requirements](requirements.txt) displayed terrain `0 ≤ x < 10°` and
   illumination `0 ≤ x ≤ 10°`, both Required, and January month controls.
   It also displayed DEM nodata and MOD11C3 QA limitations.
3. [Sites](sites.txt) displayed 7,599 matches, 84,185 misses and 16 unknowns
   out of 91,800 cells. It said the match order was arbitrary because the
   required traits tied. Do not call the first row the best site.
4. Selected the first match using the Compare button's keyboard activation.
   A pointer click timed out before selection; keyboard activation worked.
5. [Unknown sites](unknown-sites.txt) showed missing terrain as `no data`.
   Their Compare buttons were disabled. The earlier match remained selected.
6. [Limitations](limitations.txt) showed gravity, air pressure and radiation;
   a mean-slope versus local-maximum scale caveat; the illumination proxy;
   and the selected cell's **95% water cover** warning.
7. [Logistics](logistics.txt) showed protected land as `no data` and said cost,
   permits, vehicles and communications were not in the data.
8. [Risks](risks.txt) showed qualitative categories and the warning that no
   EONET events recorded does not mean safe. Past campaigns were listed with
   geographic distance, not S8 trait closeness.
9. Download brief produced [mission-brief-LI-5L.md](mission-brief-LI-5L.md).
   Reading it confirmed the selected cell, request, band origins, scale
   caveats, permanent breakdowns and manifest hash. It explicitly says S8
   closeness is not checked. **It does not include the on-screen 95% water
   warning or the complete logistics/risk tables.** Do not call it a complete
   record of those reports; keep the on-screen warning in the recording.
10. Browser warning/error log query returned `[]`. This covers messages
    exposed by the browser tool, not a complete network or performance audit.

## Capture files and limits

[Requirements screenshot](requirements.png), [unknown-list screenshot](unknown-sites.png),
[limitations screenshot](limitations.png), and [final report screenshot](final-report.png)
show the rehearsed screens at the browser's narrow default viewport; these
are evidence captures, not final video frames or a desktop-layout check.
Text files are browser DOM snapshots. The manifest
is the fetched release file; the brief is the browser download, copied without
editing. [checksums.json](checksums.json) records the artifact hashes.

No video, voiceover, slide deck, duration check, new Lean run, source-data
audit, month-edit test, three-site comparison, CSV export or share-link restore
is claimed. Runtime status: executed for this rehearsal. Scientific status:
partial, as the app says. Recheck the selected build and submission rules
before final recording and publication.
