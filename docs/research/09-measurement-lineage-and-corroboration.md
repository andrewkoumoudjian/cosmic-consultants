# 09 — Measurement lineage and corroboration: research requirements

Date: 2026-11-12 (America/Toronto). Work order: [#39](https://github.com/andrewkoumoudjian/cosmic-consultants/issues/39).
Status: **proposed research**, for W10 [#15](https://github.com/andrewkoumoudjian/cosmic-consultants/issues/15),
W5 [#18](https://github.com/andrewkoumoudjian/cosmic-consultants/issues/18) and
W6 [#19](https://github.com/andrewkoumoudjian/cosmic-consultants/issues/19).
Baseline reviewed: `7ba4941` (registry v2 and doc 08 v1).

This answers the [question to @Derick12345678](https://github.com/andrewkoumoudjian/cosmic-consultants/issues/7#issuecomment-6840364817):
is `independenceGroup` enough, or should lineage be a list? The earlier thermal,
frozen-ground, coverage and spectral findings were accepted in #38; this note
records the remaining requirements rather than reopening those corrections.

## 1. Recommendation and decision boundary

Keep `independenceGroup` as a coarse discovery hint. Propose a structured list
of versioned dependencies, with roles, which can form a graph as derived
products are added. Neither different group names nor a graph with no recorded
overlap proves statistical independence. An incomplete graph can miss a shared
input, and two independent instruments can still have correlated errors.

The unit of review is **a measured feature at a specified location and time
support**, not a product title. A group-count summary is useful for finding
possible checks, but is not itself evidence that ARL gate 3 passes. Coverage,
comparability, valid observations and the independence justification also need
review. This is a proposed review requirement; no executable gate or new
contract is defined here. Binding policy changes need the normal contract/ADR
review and Lean statement/proof gates where applicable.

## 2. Primary-source findings

### A. Daily and composite MODIS products reuse observations

The [MOD11A2 v061 metadata][S2] describes an eight-day mean of corresponding
MOD11A1 pixels. The [MOD11C3 v061 description][S3] describes monthly
compositing and averaging of MOD11C1 daily files, and supplies quality,
observation-time and clear-sky-count information.

**Implication proposed for review:** `modis-mod11c1-daily` and
`modis-mod11c3` cannot supply two independent observation streams merely by
having different ids. An annual maximum over monthly means is a different
statistic from a maximum over quality-screened daily retrievals. Neither
statistic by itself establishes an all-weather, continuously observed annual
extreme. Preserve the observation and aggregation support in the measurement.

### B. NASADEM has mixed and version-specific dependencies

The [NASADEM_HGT v001 metadata][S1] identifies SRTM telemetry, ASTER GDEM
**Version 2**, ICESat/GLAS control, AW3D30 and interpolation among its inputs
and processing improvements. It describes a NUM layer identifying scene count
and source per pixel, and land coverage between 60 N and 56 S.

The registry currently places `nasadem-hgt` in `srtm-radar` and
`aster-gdem-v3` in `optical-stereo`. The labels alone cannot establish
independence. Conversely, this collection description does not show that every
NASADEM pixel used ASTER, or that the exact ASTER observations used in Version
2 equal those contributing to Version 3. Inspect the applicable provenance
flags and versioned processing documentation before making a cell-level claim.
This review has not decoded any NUM values or inspected any raster.

**Implication proposed for review:** record potential shared inputs in the
collection dependency graph and distinguish them from confirmed contributions
to the selected pixel. Where contribution is unresolved, do not count this pair
as independently corroborating evidence solely from the two group labels.

### C. Changing the retrieval algorithm is a different kind of check

The [MOD21C3 v061 metadata][S4] distinguishes the MOD21 temperature/emissivity
separation retrieval from the MOD11 split-window method, both using MODIS
thermal observations. It also describes dust/cloud-related high-temperature
outliers and the need for quality/error filtering. Such retrieval differences
may be useful for sensitivity analysis; they do not automatically supply an
independent sensor observation.

The same metadata abstract calls MOD21C3 monthly but later mentions an
eight-day period and MOD21A2. That apparent copy/aggregation inconsistency is
**unresolved** here. W6 should verify the product-specific specification rather
than infer an exact compositing recipe from that paragraph. No new QC threshold
is proposed in this note.

### D. Reanalysis needs a variable-specific comparison

NASA's [MERRA-2 system description][S6] specifies a land-surface model,
observation-corrected precipitation, prescribed boundary conditions and
assimilated, radiatively interactive aerosols. Its [FAQ][S5] explains which
surface meteorological observations are assimilated. These describe a coupled
model/assimilation system, not a second direct MODIS surface-temperature
retrieval.

Doc 08 and `research/features/build_feature_inventory.py` currently call
MERRA-2 hourly TS the independent thermal check. **This review has not
established the variable-level dependency/error independence needed for that
claim.** MERRA-2 remains a useful candidate comparison, not rejected data.
W5/W6 should document the exact TS quantity, spatial support, observation/model
time support and statistic being compared with clear-sky MODIS retrievals.
Hourly modeled extremes and satellite-overpass extrema are not automatically
the same observable. A general `reanalysis` group does not resolve this.

## 3. Information for the contract reviewers

These are proposed information requirements, **not adopted field names or a
schema**. They may be held in a review note until W10 chooses a representation.

| Information | Why it matters |
|---|---|
| Dataset id, collection/product version, granule/asset identity, source URL and snapshot hash | Identifies the exact input rather than a mutable product family. |
| Feature/variable, quantity, units and derivation | Stops a mineral class, band depth, emissivity or temperature proxy silently becoming a different physical measurement. |
| Statistic, time interval, acquisition/overpass time and aggregation | Distinguishes means, sampled extrema, model-hourly values and continuous/full-day claims. |
| Spatial support, native resolution, resampling and valid-data masks | A collection rectangle or resampled pixel is not evidence of an observation at the required scale. |
| Upstream product versions and dependency roles | Distinguishes primary observations, retrieval/ancillary inputs, ground control, model forcing, void fill and post-processing. |
| Dependency scope and completeness | Marks collection-level possible inputs versus confirmed pixel/time contributions; missing lineage stays explicitly unknown. |
| Pair-specific independence/comparability assessment with source citations and reviewer rationale | A list intersection can detect a known overlap, but cannot establish independence when it finds none. |

Do not invent input proportions or source flags absent from documentation.
Different versions of a dependency must not be silently treated as wholly
independent, or as byte-identical observations. Two products with different
retrievals may support an algorithmic check without satisfying the requirement
for independent observations.

## 4. Questions to resolve before computing gate 3

1. **W10 / #15:** distinguish evidence metadata from a reviewed corroboration
   assessment. Can the representation express shared input, unresolved lineage,
   incompatible quantity/support, and an approved comparable pair with reasons?
   A boolean derived only from unequal `independenceGroup` strings is inadequate.
2. **W5 / #18:** freeze each compared observable and statistic before selecting
   tolerances. Decide whether different features within one dimension actually
   corroborate the same claim; dimension membership alone is insufficient.
3. **W6 / #19:** retain native QA/source flags and actual valid support with
   snapshots. Regridding or filling gaps must preserve those distinctions.
4. **Reviewers:** define what independence means for this project and what
   empirical/theoretical evidence supports a pair. Neither this note nor the
   source metadata establishes a calibrated error-correlation model.
5. **Unknown handling:** unresolved comparability or lineage is an unverified
   gate-3 assessment; it is not evidence that the site is unsuitable. If usable
   measurements support lower gates, preserve that evidence separately. An
   out-of-coverage required dimension still has no observation. Exact ARL
   semantics belong to S6; no new level is assigned here.

These questions do not authorize work on the implementation-window tasks early.
No new contracts, Lean statements, tolerances, site evidence classifications,
rasters, numerical losses or atlas levels were produced for #39.

## 5. Source-access evidence and limits

All six requests returned HTTP 200. Times below are **UTC on 2026-11-13**
(the Toronto review date above is still November 12). Hashes identify the
response bytes inspected; HTML can change without a scientific product change.
These are documentation fingerprints, not dataset/granule snapshot hashes.
Raw responses were retained locally for review; no scientific payload was fetched.

| Source | UTC | Bytes | SHA-256 |
|---|---|---:|---|
| [S1 NASADEM CMR][S1] | 03:42:07 | 12,436 | `aa87b8f816317e51faa6490d9add82e4946b5dedd88067d3bea178652eb337ea` |
| [S2 MOD11A2 CMR][S2] | 03:42:07 | 15,157 | `6c52eba598a3fb0a3e103e784de0debd0fbf3635d521c1097b21071971728071` |
| [S3 MOD11C3 LAADS][S3] | 03:42:07 | 40,795 | `de1fc4c06da7adeca99a8db46c2386bbc6679791c371054fab1ffbc9a61415c2` |
| [S4 MOD21C3 CMR][S4] | 03:42:07 | 16,457 | `141ca4aefacf9c7c1f7d72e2472df2fafc0b2cb77c168594a6d381fa87b4173c` |
| [S5 MERRA-2 FAQ][S5] | 03:42:07 | 66,682 | `855f44c6e732d58a91b4ded81843d93bcffefbf1b663a5f18a8d1bc1daba59dc` |
| [S6 MERRA-2 system][S6] | 03:42:08 | 43,353 | `7913e88c7878fdceca64f70164c3872f8ed7f15fef85ec2cc588e165d1a4e315` |

Runtime status: source review completed. Scientific status: **proposed**, with
variable-specific independence, pixel support and product-recipe questions
explicitly unresolved. This does not certify any candidate site's suitability.

[S1]: https://cmr.earthdata.nasa.gov/search/concepts/C2763264762-LPCLOUD.umm_json
[S2]: https://cmr.earthdata.nasa.gov/search/concepts/C2269056084-LPCLOUD.umm_json
[S3]: https://ladsweb.modaps.eosdis.nasa.gov/missions-and-measurements/products/MOD11C3
[S4]: https://cmr.earthdata.nasa.gov/search/concepts/C2565791050-LPCLOUD.umm_json
[S5]: https://gmao.gsfc.nasa.gov/gmao-products/merra-2/faq_merra-2/
[S6]: https://gmao.gsfc.nasa.gov/gmao-products/merra-2/system-characteristics_merra-2/
