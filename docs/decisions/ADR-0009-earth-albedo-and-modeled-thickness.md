# ADR-0009: Preserve Earth albedo sampling and modeled thickness meaning

Date: 2026-11-14. Status: implementing source preparation in #66 / PR #77.
Scientific status: partial / executed-unreviewed.

The owner's scope is acquisition, transformation, preparation and underlying
technology. This batch adds related source inputs to the full feature work;
it does not establish Earth/Moon/Mars comparability.

- Keep twelve MCD43C3 v061 retrievals dated the 15th of each 2023 month.
  Each uses a 16-day source window; the selected windows leave calendar
  gaps. Done when: source dates/windows survive in metadata and nothing
  calls them calendar-month means or independent daily observations.
- Keep shortwave white-sky and black-sky albedo distinct. White-sky is
  bihemispherical reflectance under isotropic diffuse illumination;
  black-sky is directional-hemispherical reflectance. Done when: both keep
  their native scale/fill, source meaning and separate pixel support.
- Retain the work order's best-quality rule (QA=0) and 25% cell-pixel
  support threshold. Done when: each field has its own mask/count, nulls
  have reasons, and QA counts refer to the unmodified source arrays.
- Keep ORNL DAAC 1304 as a static model of different subsurface layers,
  with its native geographic coverage and uncertainty. Done when:
  upland regolith/soil and lowland sediment are separate; fill stays null;
  the guide's experimental/high-uncertainty warning is retained.
  Soil float32 values are normalized to a checked 0.01 m grid for the
  histogram; the maximum normalization difference is recorded explicitly.
- Treat 50 m as the source's published upper valid bound for the byte
  layers. Its range table does not establish clipping or censoring.
  Done when: counts at the maximum are labelled over mapped master-cell
  pixels and no claim calls them global native-raster totals.
- Verify input hashes before processing, preserve native units and source
  support, and hash-check delivery. Done when: builders reject changed
  inputs and delivered outputs match the recorded snapshots.

These products are not lunar bolometric albedo, measured ice-table depth or
measured lunar regolith thickness. Exact feature completion and new physical
comparisons require their own evidence and applicable Lean-first gates.
The yearly albedo value is a mean of the retained dated retrievals, not an
annual energy-integrated albedo. Missing source support remains explicit.

Primary evidence:
- NASA MCD43C3 catalog: https://data.nasa.gov/dataset/modis-terraaqua-brdf-albedo-albedo-daily-l3-global-0-05deg-cmg-v061-0cdb1
- ORNL guide (hashed in MANIFEST): https://data.ornldaac.earthdata.nasa.gov/public/global_soil/Global_Soil_Regolith_Sediment/comp/Global_Soil_Regolith_Sediment.pdf
