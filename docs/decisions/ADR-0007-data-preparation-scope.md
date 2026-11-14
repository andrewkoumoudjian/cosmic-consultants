# ADR-0007: Data preparation follows IDEA and the full feature inventory

Date: 2026-11-14. Status: implementing the owner's explicit instructions in
work order #69. This decision does not approve a new scientific comparison.

Andrew confirmed that the team's Google Doc takes precedence over repository
product docs, and selected its IDEA table over the generated six-step tab.
He also confirmed acquisition, transformation and preparation of the full
GitHub feature inventory as the current scope.

## Decisions

1. The workflow's core modules are mission objectives, site analysis and
   comparison, and gap analysis. Combined operations (logistics and risks)
   and mission presets are should-have modules. Historical step IDs in
   internal column metadata are compatibility references, not UI authority.
2. Preparation tracks every feature ID in
   `research/features/landing_site_features.csv` (55 in this revision),
   plus workflow context and past-campaign data. The updated IDEA tab has
   19 categories and a maximum of eight selected metrics; the maximum limits
   a user selection, not the dataset or menu length. The 55 features are a
   baseline, not a cap. The base yearly/monthly tables and three objective
   rows are a starting subset.
3. A related input does not complete a feature. Preserve the feature's
   quantity, units, spatial baseline, aggregation, time window, quality flags,
   source/version/hash and caveats. Monthly composites cannot become daily
   extrema by renaming; coarse cell slope cannot become a fine-baseline
   slope; permafrost probability cannot become ice depth. Regional and
   site-level support remains explicit; H3 joins do not add resolution.
4. Each source builder owns its module and table. Assembly joins declared
   columns and computes only the documented preparation summaries. Missing
   support and permanent limitations remain visible. No synthetic source
   values, default fills or hidden feature omissions are permitted.
5. The full feature-preparation report separates available related inputs
   from implemented features. Category-level trait availability does not
   establish that every test in that category is supported. Exact feature
   builders and their applicable frozen statements still need acceptance.
6. Use Polars for assembly. Keep reproducible manifests, input/output hashes,
   key and missingness checks, cleaning counts and hash-verified Drive
   delivery. No new UI, chatbot, scoring rule or fastopt implementation is
   included in this work order. Mathematical/scientific claims retain the
   applicable Lean-first gates.

Source of workflow authority:
https://docs.google.com/document/d/1up_LJPlljDuY-xak0Licddnoj8MakBiD1pv_Vywj8yQ/edit?tab=t.191x2ca9c4uw

Owner scope record:
https://github.com/andrewkoumoudjian/cosmic-consultants/issues/69#issuecomment-6882822837

## Acceptance

- Every inventory feature appears once in the preparation mapping and report.
  Done when: deleting a mapping fails validation and the real report contains
  all 55 current IDs.
- Source values and nulls survive joins unchanged. Done when: tests detect
  one-null/one-value differences, reason text is preserved, and real joins pass.
- Outputs have complete declared key domains. Done when: invalid months,
  years, duplicate keys and unknown cells fail checks.
- Delivery is separate from generation. Done when: Drive checksums match
  accepted local artifacts; a running transfer is reported as pending.

The cleaning audit reports actual input threshold counts separately from
output nulls. Missing historical input accounting stays unknown. It found
that the old DEM nodata-filter label was inaccurate and MOD11C3 QC-bit
filtering is absent. Those source-quality limits appear in the cleaning and
coverage reports; #76 owns their audit/rebuild. Merging assembly does not
accept those source methods or close the full data-preparation work order.
