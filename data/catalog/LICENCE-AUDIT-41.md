# Product-specific licence review — issue #41

Review date: 2026-11-12 (America/Toronto); source/probe timestamps use UTC
2026-11-13. Baseline: `7ba4941`. Work order:
[#41](https://github.com/andrewkoumoudjian/cosmic-consultants/issues/41).

## Scope and result

Seven previously unverified candidates were reviewed. The existing
`ody-grs-pds` row is narrowed to the **legacy PDS3
`ODY-M-GRS-5-ELEMENTS-V1.0` element-concentration maps**. Its named
[NASA catalogue record][ODY-RECORD] declares `us-pd` and gives a public-domain
label URL. The other six candidates remain unresolved: the inspected sources
did not establish applicable reuse terms for the registry product. Unresolved
does not mean prohibited; it means this review cannot clear the product.

The row remains a **candidate**, with `analysisReady: false`. This review
does not adopt a dataset, certify valid coverage, download scientific payloads,
produce site ratings or begin implementation-window work. `license.verified`
retains the existing registry meaning: expected text found in the live source,
with the result recorded in the probe evidence. It is not a blanket grant for
all files served by an archive.

After the selected probes, **52 of 68** registry rows have a verified licence
declaration (previously 51); **16** remain unverified. These are registry-text
verification counts, not blanket publication clearances or scientific ratings.

| Registry id | What the inspected sources establish | Action |
|---|---|---|
| `ody-grs-pds` | The exact NASA catalogue record names `ODY-M-GRS-5-ELEMENTS-V1.0`, declares `us-pd`, and links a public-domain label. The product-specific PDS page describes the maps, observation period and grids. | Narrow the row's title, endpoint, coverage and intended scope to that legacy product; licence probe checks record name, classification and PDS dataset id together. |
| `m3-pds` | The M3 volume page identifies the archive; applicable reuse terms were not established there. | Keep `unresolved` / `verified: false`. Do not substitute rights for a different derived M3 dataset or for processing software. |
| `mars-geologic-map-sim3292` | Linked FGDC metadata gives access constraints `None` and requests citation of authors. The DOI `10.5066/P9PBKSGE` identifies an interactive map and has an empty rights list in inspected DataCite metadata. | Keep unresolved. A citation request, an access statement and an interactive-map record are not an explicit licence for every scientific data asset. |
| `robbins-mars-craters` | Collection JSON has no `license` or `rights` field. Its canonical link targets a geologic-map image rather than an identified crater-data release. | Keep unresolved. Do not transfer a preview image's public-domain statement to the crater database. |
| `robbins-moon-craters` | Product landing page identifies the database; applicable reuse terms were not established in this review. | Keep unresolved; citation of Robbins's paper does not itself establish a dataset licence. |
| `lroc-nac-boulders-watkins` | Product landing page identifies the database; applicable reuse terms were not established in this review. | Keep unresolved; paper/preview-image terms are not assumed to cover the database. |
| `nsidc-ggd318-permafrost` | Linked `GGD318.002` OAI/DIF metadata has no `Use_Constraints` or `Access_Constraints` element. The matching DOI metadata has an empty `rightsList`. | Keep unresolved. Neither the absence of a constraint field nor free access supplies an explicit applicable reuse statement. |

## Odyssey scope: what is and is not verified

The [product-specific PDS page][ODY-ARCHIVE] and the exact catalogue record
identify observations collected **2002-06-04 through 2005-04-03**, first released
in March 2006. The archive describes water, potassium, thorium and other element
maps. It lists unsmoothed products on **2 x 2, 5 x 5 and 10 x 10 degree bins**,
and smoothed products on **5 x 5 degree bins**. The catalogue description
states that non-radioactive species are masked in polar regions. These
product-description facts replace the former open-ended period and approximate
grid description; they are not independently measured coverage statistics.

The archive page now announces a PDS4 conversion dated 2026-10-01. The licence
check here is tied to the named **legacy PDS3 V1.0 catalogue record**; it does
not establish a blanket licence for the conversion or all other GRS products.
W6 must pin the matching dataset id, release, selected table/grid and masks.
The page probe does not demonstrate that every legacy asset is downloadable.

A separately inspected NASA record declares `us-pd` for averaged-neutron
`ODY-M-GRS-5-AND-V2.0`. That is **not** the product selected by this change,
and its terms were not used to clear the element maps. Product identities must
stay distinct even within the same instrument suite.

Two other harvest records for the same legacy element product use
`other-license-specified` (linking government-works guidance) and `notspecified`.
Their names, declarations and response fingerprints are retained in the evidence
file. This update reports the explicit `us-pd` declaration of the selected
record; it does not silently reconcile the different harvest classifications.
Reviewers must keep that distinction when deciding which exact assets to use.

## Windows text-encoding correction

The existing provenance helper used the operating system's default encoding
for YAML reads/writes. On this Windows host, its Unicode summary ellipsis was
written as CP1252 byte `0x85`, and a strict UTF-8 read failed. Generated text
must remain portable across the Windows contributor and Linux CI environments.

`scripts/registry_probe.py` now explicitly reads/writes UTF-8 for registry YAML,
JSON evidence and the index. The inventory builder does the same for its
registry/CSV inputs and CSV outputs. The affected local generated rows were
normalized to UTF-8, then written again from the recorded fresh probe results
using the corrected helper. The previous committed probe logs were preserved.
Evidence-file paths also use portable `/` separators. These are text-I/O and
path-serialization corrections; no probe criteria, feature mapping or
scientific computation is changed.

## Evidence and reproducibility

The new run-specific evidence file is
[`licence-review-41.json`](../snapshots/registry-probes/2026-11-13/licence-review-41.json).
It contains:

- documentation/catalogue fetch URLs, UTC timestamps, HTTP statuses, byte
  lengths and full SHA-256 fingerprints;
- extracted product names, publisher licence classifications, rights-list and
  use-constraint fields used in the review;
- fresh existing-helper probes for the seven selected registry rows, including
  per-pattern licence-match evidence;
- the hash of the retained full prior `probe-log.json`, which was not overwritten.

One catalogue query returned an unrelated, effectively unfiltered page despite
HTTP 200. It is preserved as **rejected evidence** with the reason recorded;
none of its unrelated records or its result count establishes product rights.
The positive Odyssey check uses `package_show` for one exact catalogue name
and checks both that name and the PDS identifier in the response. A successful
HTTP request alone is not a successful dataset-identity check.

`INDEX.md` is regenerated with the existing helper from fresh selected probes
and retained prior evidence for the remaining rows; it does **not** claim that
every registry endpoint was fetched again. The existing feature-inventory
builder mechanically copies the changed licence fields into its two CSV views.
No feature mapping, dependency group, schema or gate algorithm is changed.

## Remaining review work

- Obtain product-specific terms or a documented applicable publisher policy
  for the six unresolved reviewed candidates, resolving any third-party scope
  rather than inferring rights from a host name.
- Resolve the remaining unreviewed licence gaps separately. This is not a
  complete legal or scientific audit of the registry.
- Review the exact legacy-product scope before ingest. A licence-text match
  does not establish suitability, validity, independence or challenge eligibility.
- Preserve the original publication/data citations and actual source assets
  in any adopted snapshot manifest.

Runtime status: registry/source review complete, subject to the recorded probe
results. Scientific status: **proposed**; no experiment or analog conclusion.
Owner review is required before merging the provenance change.

[ODY-RECORD]: https://data.nasa.gov/api/3/action/package_show?id=ody-mars-gamma-ray-spectrometer-5-element-concentration-v1-0
[ODY-ARCHIVE]: https://pds-geosciences.wustl.edu/missions/odyssey/grs_elements.html
