# Test-driven data preparation: current gaps and expansion

Date: 2026-11-14. Work orders: #69 (preparation/report fixes),
[#74](https://github.com/andrewkoumoudjian/cosmic-consultants/issues/74)
(source acquisition and physical processing). Runtime: source-processing audit;
scientific status: partial, no new site-suitability result.

## What changed in the requirements

The authoritative [Google Doc IDEA tab](https://docs.google.com/document/d/1up_LJPlljDuY-xak0Licddnoj8MakBiD1pv_Vywj8yQ/edit?tab=t.191x2ca9c4uw)
now contains 19 categories grouped into mobility/landing, science,
resources/construction, operations and hardware testing. It also gives
12-item metric menus for robotic mobility and geology/sampling. Up to eight
metrics may be selected; that does not limit the data inventory or truncate
those menus. The document's High/Medium/Limited support labels are planning
statements, not verified data coverage.

`data/pipeline/test-categories.yaml` retains the source text, revision,
captured response hash, all 19 category rows, primary/secondary input roles
and complete detailed menus. Exact metric units, statistics and test-support
interpretation require source review in #74; this file does not manufacture them.

The 55-feature inventory remains a baseline. The new metrics add requirements
that cannot be fulfilled by merely adding names to its columns.

## Current assembly, checked against the files

| Part | What exists | What is missing |
|---|---|---|
| Earth | Yearly/monthly H3 traits, historical temperature composites, access and named events; individual source builders underway | Exact feature-specific baselines, several physical properties, local/field evidence and broader source coverage |
| Moon/Mars | Two generic envelope files, with three Moon and two Mars bounds, plus candidate source registry rows | Selected target-site geometries, actual target measurements, time/support/QA and output provenance for each metric |
| Past missions | Six cited campaign YAMLs with locations, broad goals, published constraints, outcomes and sources | Structured test IDs, instruments/configurations, procedures, actual test-environment observations, failure criteria and links to selectable tests |
| Campaign join | Earth-cell values joined to campaign locations | A distinction between reference-year site context and conditions actually observed during the campaign; now explicitly labelled in #69 |
| User test matching | Three NASA objective rows and ten preliminary trait-map rules | A test-indexed requirements and evidence graph covering the updated categories and metric menus |

All six campaign `objectivesExercised[].objectiveId` values are currently
null. That is honest: the source did not state one of our NASA IDs. A new
project test taxonomy can classify supported campaign activities as an
explicit reviewed interpretation; it must not pretend the original paper
named those IDs.

## Four connected data products are needed

1. **Test requirements.** Stable category/test/metric IDs, observable, unit,
   spatial baseline, time window, primary/secondary role, measurement method,
   equipment context, source/basis and explicit unknowns. A user requirement
   is separate from a documented engineering limit or precedent.
2. **Planetary target features.** One record per body, selected target site,
   metric and support/window. Keep native coordinates/reference frame, source
   resolution, quality/error layers, statistic, input hash and missing reason.
   Do not force planetary rasters onto the Earth H3 grid or convert a generic
   landing limit into a measured target feature.
3. **Earth test-site features.** The corresponding Earth observable at its
   real resolution/time support. Record direct/proxy/unknown relationships
   and approved transforms separately. Coarse global screening can precede
   finer local assessment; it does not resolve obstacle spacing or rock strength.
4. **Campaign test evidence.** Campaign and test IDs, actual site/dates,
   instrument/configuration, procedure, metric/value/unit, conditions,
   outcome/failure/lesson and exact quote/source/hash. Preserve trial results
   as observations; do not promote them to universal selection thresholds.

Assembly then connects selected tests and metrics to the relevant target
profile, Earth observations and comparable past-test evidence. Support and
missingness must be assessed per selected metric, not inferred from a broad
category's presence in a table. A scene's current appearance or a 2023 cell
average is not evidence of its condition during a 2010 field trial.

## Planetary source work to prepare

The live [NASA LOLA product page](https://pgda.gsfc.nasa.gov/products/90)
provides elevation, slope, effective-resolution and error products, plus
roughness/slope products with explicitly named baselines. This is a concrete
acquisition path for target terrain; source citation/licence and selected
site/support still need checking before publication.

The [PDS Diviner archive](https://pds-geosciences.wustl.edu/missions/lro/diviner.htm)
and [PDS TES archive](https://pds-geosciences.wustl.edu/missions/mgs/tes.html)
remain primary discovery paths for lunar and Martian products. Discovering
an archive is not selecting a quantity or obtaining a target measurement.
Pin the exact product, variable, calibration, temporal statistic and quality
flags before deriving a target profile. A current USGS blended-DEM page
attempt failed during this audit; do not treat that attempted URL as verified.

The next target builders should handle lunar terrain/roughness, lighting and
shadow geometry, thermal products and ice evidence; and Mars terrain,
thermal/material observations, dust/wind and ice evidence. Geometry,
reference frames, wavelengths and material-model differences remain explicit.
These are acquisition requirements, not claims that those tables exist.

## Data expansion beyond the 55-feature baseline

| New requirement | Preparation path / honest boundary |
|---|---|
| Grain-size distribution, loose-layer depth, bearing/shear strength, friction | Evaluate soil/geotechnical sources and campaign measurements; soil class or modeled depth alone does not measure these properties |
| Outcrop access, fractures, stratigraphy, alteration, hardness, porosity/permeability | Combine mapped geology with site-scale imagery/field evidence; a lithology class is not a mechanical measurement |
| Seismic noise and subsurface structure | Instrument/campaign records and appropriate geophysical products; preserve observation period and configuration |
| Ice thickness, type and depth | Distinguish glacier/ground-ice evidence, modeled frozen ground, ice content and drillable depth |
| Visual landmarks, obstacle spacing and fine roughness | Site-scale imagery/DEMs and explicit operating scale; global coarse cells remain screening context |
| Cave geometry, access, thermal stability and shielding | Site-specific inventories/measurements; cave presence does not establish radiation protection |
| Communications, sky view and isolation | Terrain/horizon and operational evidence; no claim that Earth reproduces lunar direct-to-Earth links |
| Microbial activity, biosignature preservation and contamination | Biological/geochemical field evidence with sampling protocol and date; aridity or remoteness is not biological clearance |

No source listed as a candidate is accepted solely because the Doc labels
its category High. Missing evidence stays explicit. #74 continues actual source
acquisition, physical transformations and past-test extraction. It does not
build application interfaces. Existing #65/#66/#68 source builders continue
in their assigned files.
