# ADR-0006: Use NASA EONET events in step 5 (risks)

Date: 2026-11-14 (America/Toronto). Work order: #59 (W18). PR: #62.
Status: **accepted by the repo owner, Andrew Koumoudjian (@andrewkoumoudjian),
2026-11-14.** In this session he answered "Yes, please proceed" to the EONET
question posted on PR #62
(https://github.com/andrewkoumoudjian/cosmic-consultants/pull/62#issuecomment-6882088580).

## Context

Step 5 of the mission planner (ADR-0005) shows the natural hazards near a
site. NASA's EONET v3 lists notable natural events with names, dates, points
and source links. EONET publishes no licence of its own. Evidence we probed
on 2026-11-14 (log: `data/snapshots/registry-probes/2026-11-14/`):

- `https://eonet.gsfc.nasa.gov/what-is-eonet`: "All EONET metadata and services
  are intended to be used for visualization and general information purposes
  only and should not be construed as 'official' with regards to spatial or
  temporal extent". EONET "has been supported by the following: Earth Science
  Data Systems Program (ESDS)".
- NASA Earthdata data policy
  (`https://www.earthdata.nasa.gov/engage/open-data-services-software-policies`):
  "NASA commits to the full and open sharing of Earth science data ... There
  will be no period of exclusive access".
- Event records come from outside sources (in our snapshot most often GDACS,
  IRWIN, InciWeb, PDC and Smithsonian volcano reports), each
  linked from the event.

## Decision

1. We use EONET under NASA's full and open data policy, with EONET's
   disclaimer shown next to the data. Catalog licence id:
   `nasa-esds-open-data-eonet-disclaimer`.
2. We only show **named events**: title, start date, category and source link.
   Counts per cell are allowed as "events recorded by EONET near here". We never
   show a rate, a probability or "safe". A zero reads "none recorded in EONET".
3. Snapshot: one frozen pull of all 2015–2024 events (`status=all`), hashed in
   `MANIFEST.json`. New data means a new snapshot.
4. "Near here" means any event geometry within 50 km of the H3 cell centre.
   Polygons count by the mean of their vertices.

## Consequences

- L2 `eonet_<category>_events` and `_months` are filled, and
  `_derived/eonet-events-r4.parquet` lists the events behind each count.
- If a source behind an event asks us to remove it, we drop it with a new
  snapshot and say so in the changelog.
- WDPA (protected areas) stays withheld. Its terms limit redistribution, and
  this decision does not cover it.
