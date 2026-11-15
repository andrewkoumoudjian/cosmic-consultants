# 05 — NASA Open Data Portal inventory (`data.nasa.gov/dataset/`)

Date: 2026-11-12. Research only. All counts below were read live from the portal's
own API on this date (probe log §6); re-run the probes before citing them later —
this is a harvested catalog and counts move.

## 1. What this portal is

| Fact | Evidence |
|---|---|
| Platform | **CKAN** (`/api/3/action/...`, `status_show`: "NASA Open Data Portal"). Not Socrata — the Socrata catalog API answers `Domain not found: data.nasa.gov`. |
| Size | **36,518 datasets** (`package_search?rows=0` → `count: 36518`; the HTML page agrees: "36,518 datasets found"). |
| Organizations | Exactly **1**: NASA (`organization=nasa`, record created 2025-03-31). "Groups" facet: *no groups match*. There is no topical browsing hierarchy — search is the only entry. |
| Provenance model | **Harvested metadata, not hosted data.** Sample record extras: `harvest_source_title: Science Discovery Engine`, `accessLevel: public`, `bureauCode: {026:00}`, `identifier: https://doi.org/10.48322/...`, `catalog_conformsTo: project-open-data v1.1`. Resources point outward (e.g. `ftps://spdf.gsfc.nasa.gov/...`), resource `datastore_active: False`. |
| Machine interfaces | CKAN Action API v3 (`package_search`, `package_show`, `tag_list`, `organization_list`…); full-catalog **DCAT feed `GET /data.json` = 96,728,566 bytes**; `GET /catalog.xml` (RDF/XML) answered only 878,967 bytes — implausibly small next to `data.json`, treat as partial until verified. Extensions include `datastore`, `harvest`, `dcat`, `s3filestore`. |
| Record shape | Standard CKAN package: `name, title, notes, tags[], groups[], organization, license_id, metadata_created/modified, resources[] (format, mimetype, url, datastore_active…), extras[] (DOI, harvest provenance…), tracking_summary`. |

**Verdict up front:** this portal is a **discovery and provenance layer** for the
project — the place to *find* dataset identifiers, DOIs and license fields. It is
not where analysis-ready Earth/Moon/Mars bytes live; those remain Earthdata/PDS/
USGS/Trek as inventoried in
[`01-nasa-data-catalog.md`](01-nasa-data-catalog.md) §4.
Every record we adopt must be resolved to its source archive and probed there.

## 2. Composition (facets from the live portal, 2026-11-12)

### Licenses — reuse cannot be assumed in bulk

| `license_id` | Datasets | Reading |
|---|---:|---|
| `other-license-specified` | 22,009 | License text lives in record extras (sample: `usa.gov/government-works`); must be read per dataset. |
| `notspecified` | 7,628 | Unknown until resolved to source. Exclude by default. |
| `us-pd` | 6,880 | US public domain — clean reuse (cross-checked: `fq=license_id:us-pd` → 6,880). |
| `cc-zero` | 1 | Negligible. |

Only ~19% of the catalog is self-declared public domain. Our dataset registry needs
a per-dataset license field resolved from `extras.license` / source archive, never
inherited from "it's on data.nasa.gov".

### Resource formats — a document/binary archive, not a tabular data lake

Datasets having ≥1 resource of the format (portal facet; records overlap across rows):

| Format | Datasets | | Format | Datasets |
|---|---:|---|---|---:|
| BIN | 15,847 | | ZIP | 2,086 |
| HTML | 13,710 | | TXT | 2,002 |
| ISO | 10,651 | | XML | 420 |
| PDF | 10,181 | | TAR | 268 |
| PNG | 4,431 | | **CSV** (`fq` count) | **131** |
| JPEG | 2,190 | | **JSON** (`fq` count) | **45** |

BIN/ISO dominance = harvested PDS/SPDF mission volumes. Machine-readable tabular
holdings are a rounding error (CSV+JSON ≈ 0.5%). Expect per-dataset bespoke readers
at the source archives; budget ingest work accordingly and prefer STAC/WMTS sources
from doc 01 wherever the same measurement exists there.

### Tags — mission-harvest vocabulary, not a curated topic taxonomy

Top tags: `__` 7,673 (empty/placeholder), `international-rosetta-mission` 3,806,
`67p-churyumov-gerasimenko` 2,977, `earth-science` 2,379, `mars` 1,321, `nasa` 1,086,
then GCMD-style `earth-science-…-atmospheric-water-vapor…` long tails (~1,000 each).
21% of records carry the junk `__` tag. **Do not build the registry on tags alone**;
use full-text + extras (DOI, harvest source) + source-archive resolution.

## 3. Challenge-relevant slices (Solr counts, `rows=0`, 2026-11-12)

`tag:` = exact tag facet query; `q=` = CKAN full-text over title/notes/tags — noisy
upper bounds, useful for triage only. A count here is **not** a relevance judgement.

| Slice | Count | Reading for the analog atlas |
|---|---:|---|
| `tags:mars` | 1,321 | Curated-ish Mars core. |
| `tags:earth-science` | 2,379 | Earth-observation core (GCMD-tagged). |
| `q=mars` | 2,955 | Full-text upper bound; includes every note mentioning Mars. |
| `q=lunar` | 596 | Moon full-text pool. |
| `q=topography` | 796 | Cross-body terrain pool — high-value triage queue. |
| `q=HiRISE` | 723 | Mostly PDS volume records; imagery itself stays at PDS/UA. |
| `q=analog` | 439 | Includes analog *electronics/instruments* noise; hand-triage required. |
| `q=permafrost` | 200 | Earth cryosphere pool — directly relevant to ice/permafrost dimensions. |
| `q=crater` | 176 | Impact-crater records across bodies. |
| `q=regolith` | 52 | Small, tractable, high-signal queue (simulants/ISRU). |
| `q="landing site"` | 43 | Small queue; expect mostly mission documents. |
| `q=LOLA` | 40 | Lunar DEM lineage — resolve to PDS LRO node. |
| `q=Artemis` | 27 | **Trap:** top hits are THEMIS-**ARTEMIS** heliophysics probes near the Moon (`artemis-p1/p2-field-plasma-merged-data`), not the Artemis human program. Disambiguate by record, never by keyword. |
| `q=MOLA` | 25 | Mars DEM lineage — resolve to PDS Geosciences. |
| `q="lava tube"` | 1 | The portal has effectively no lava-tube holdings; subsurface dimension must come from literature/USGS/speleological sources (lit. doc §5). |

## 4. Worked sample records (what a record really contains)

`q=Artemis, rows=2` (both modified 2026-11-05 — harvest is current):

- `artemis-p2-field-plasma-merged-data-near-moon` — 12 resources, formats BIN/HTML/TXT,
  license `other-license-specified`, tags `[magneticfield, thermalplasma]`,
  DOI `10.48322/szem-vt65`, first resource `ftps://spdf.gsfc.nasa.gov/pub/data/themis/...`,
  `datastore_active: False`.

Pattern to assume everywhere: **metadata rich, bytes elsewhere, legacy protocols
(FTPS) still in URLs.** Ingest contracts must record the *resolved, probed* source
URL, not copy the CKAN resource URL on faith.

## 5. How this portal plugs into the proposed architecture

1. **Registry seed, one harvest:** pull `/data.json` (97 MB) once into
   `data/snapshots/` content-addressed, index locally; never scrape the HTML and
   never re-query per visitor. Refresh is a dated diff, like all snapshots.
2. **Triage queues from §3:** regolith (52), landing site (43), LOLA (40), MOLA (25),
   permafrost (200), crater (176) are small enough for full manual grading;
   `mars`/`topography`/`earth-science` pools get sampled grading with stated rules.
3. **Per-dataset registry row** (doc 01 §4 standard): CKAN `name` + DOI, resolved
   source archive + probed endpoint, license resolved to text, body/dimension tags
   from *our* vocabulary, analysis-ready yes/no. CKAN tags and `q=` hits are leads,
   never registry truth.
4. **Exclusions by default:** `license_id=notspecified` and `__`-only-tagged records
   enter only after source resolution proves license and content.

## 6. Probe log (reproducible)

```
GET /api/3/action/package_search?rows=0            -> 200, count 36518
GET /api/3/action/status_show                      -> NASA Open Data Portal, extensions incl. datastore/harvest/dcat
GET /api/3/action/organization_list?all_fields=true-> 1 org (NASA, created 2025-03-31)
GET /api/3/action/package_search?<slice>&rows=0    -> counts in §3 (curl --retry 3; facet-wide query timed out once, slices OK)
GET /api/3/action/package_search?q=Artemis&rows=2  -> §4 samples
HEAD /data.json                                    -> 200, 96,728,566 B
HEAD /catalog.xml                                  -> 200, 878,967 B (flagged as suspect-partial)
GET /dataset/ (HTML)                               -> facets in §2, "36,518 datasets found"
```

Known gaps in this inventory (next work orders, not done here): tag-vocabulary size,
counts by `harvest_source_title`, `metadata_created` distribution, Datastore-active
record count, and `/catalog.xml` completeness check against `/data.json`.
