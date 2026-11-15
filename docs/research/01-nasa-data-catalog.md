# 01 — NASA Open APIs data catalog inventory (`api.nasa.gov`)

Date: 2026-11-12. Status: research only, no implementation.
Source of truth used: the live catalog file the portal itself renders,
[`https://api.nasa.gov/assets/json/apis.json`](https://api.nasa.gov/assets/json/apis.json)
(166,186 bytes, 16 entries), plus live `DEMO_KEY`/no-key probes run 2026-11-12.

## 0. What the portal is (and is not)

| Fact (verbatim from portal assets) | Implication for us |
|---|---|
| "This catalog focuses on broadly useful and user friendly APIs and **does not hold every NASA API**." (`assets/html/overview.html`) | `api.nasa.gov` alone cannot support the challenge. Earth/Moon/Mars analysis data lives in Earthdata, PDS and USGS Astrogeology (section 4). |
| "this page acts as a central catalog and key service for public APIs. **It does not hold the actual API code.**" (`assets/html/browseAPI.html`) | Each entry is a pointer to an independently run service with its own uptime and docs. Pin and probe each one we depend on. |
| Catalog bugs go to [`github.com/nasa/api-docs`](https://github.com/nasa/api-docs) | The catalog is open source; entries can be diffed in git. |
| No auth required to explore. Registered key: **1,000 req/hour**, aggregated across all `api.nasa.gov` calls, rolling window, `X-RateLimit-Limit` / `X-RateLimit-Remaining` headers. `DEMO_KEY`: **30 req/IP/hour, 50 req/IP/day**. | Any bulk pull needs a real key, server-side caching, and must not be done from the browser. `DEMO_KEY` is for smoke tests only. |

## 1. The 16 catalog entries, with challenge relevance

Relevance is scored against the analog challenge (see
[`02-challenge-brief.md`](02-challenge-brief.md)):
**T1** = can feed the core Earth↔Moon/Mars comparison, **T2** = supporting/context,
**T3** = not usable for this challenge.

| # | API (`name` in `apis.json`) | What it serves | Tier | Concrete use / reason |
|---|---|---|---|---|
| 1 | APOD | Astronomy Picture of the Day imagery + metadata. **Migrated 2026-09-10 to WordPress API** (`science.nasa.gov/wp-json/wp/v2/apod-basic`); `concept_tags`, `hd`, `thumbs` disabled; **legacy API offline 2026-12-01**. | T3 | Outreach garnish only. Migration deadline is a breaking-change risk; do not build on it. Probe 2026-11-12: legacy endpoint still answered. |
| 2 | Asteroids NeoWs | Near-Earth-object feed/lookup/browse (JPL data, `api.nasa.gov/neo/rest/v1/...`). | T3 | No surface/analog content. |
| 3 | DONKI | Space-weather notifications/knowledge: CME, CME Analysis, GST, SEP, FLR, HSS, WSA-Enlil, notifications. | T2 | Quantifies one axis where **every Earth analog breaks down**: radiation/space-weather environment. Useful for the "where the analogy fails" panel, not for site scoring. |
| 4 | EONET | Curated natural events (storms, dust storms, volcanoes, wildfires, sea/lake ice...) linkable to NRT imagery. Catalog links stale v2.1 docs; **v3 is live** (`eonet.gsfc.nasa.gov/api/v3/events`, probe OK). | **T1** | *Process* analogs, which the brief explicitly asks for: terrestrial dust-storm and volcanic event frequency/intensity per candidate site. |
| 5 | EPIC | DSCOVR full-disc Earth imagery + metadata from L1. | T2 | Global visual context only; resolution far too coarse for site characterization. |
| 6 | Exoplanet | Programmatic NASA Exoplanet Archive queries. | T3 | Irrelevant bodies. |
| 7 | GIBS | Global Imagery Browse Services: WMTS/WMS global full-resolution satellite imagery, "over 1,000 products", most daily within hours, some ~30 years deep; rendered by Worldview. Probe: EPSG:4326 `GetCapabilities` returned **3,950 `ows:Identifier` elements** (layers × tile-matrix sets). | **T1** | The Earth half of the product: basemap + analysis layers (land-surface temperature, snow/ice, aerosols/dust, vegetation indices, night lights) in any web map or GIS. No key needed for tiles. |
| 8 | Insight | InSight Mars Weather Service: per-sol temperature, wind, pressure at Elysium Planitia. Catalog warns of "SIGNIFICANT MISSING DATA"; docs last updated 2021-03-30. Probe returned sol 675 (2020-10-19) era data — the lander is retired, so this is a **frozen archive**, not live weather. | **T1** (with caveat) | The only *in-situ* Mars environmental ground truth in the catalog: temperature/pressure/wind envelopes an Earth analog must be compared against. Cite as 2018–2022 archive, never as current conditions. |
| 9 | NASA Image and Video Library | Search/asset/album API for `images.nasa.gov` (`images-api.nasa.gov/search|asset|...`). | T2 | Ground/aerial photography of known analog sites and missions for site dossiers and storytelling. Not analysis data. |
| 10 | Open Science Data Repository (OSDR) | Search, metadata and file retrieval for space-biology studies (also federates NCBI GEO, EBI PRIDE). | T2 | The biology/habitability axis: organisms under radiation, microgravity, regolith-simulant and extreme-environment exposure. Supports extremophile claims about a site. |
| 11 | Satellite Situation Center (SSCWeb) | Geocentric spacecraft locations in geophysical-region/magnetic-field frames. | T3 | Orbital mechanics of Earth satellites; no surface analog value. |
| 12 | SSD/CNEOS | JPL small-body services: CAD, Fireball, Mission Design, NHATS, Scout, Sentry, SBDB. | T3 | Fireball data is tangentially about impact flux, but not needed to characterize a site. |
| 13 | Techport | NASA technology-project inventory as JSON. | T2 | Find prior NASA analog field campaigns, ISRU and habitat tech to cite in "how this site could be used" sections. |
| 14 | TechTransfer | Searchable patents, software, spinoffs. | T3 | No site data. |
| 15 | TLE API | Two-line elements for Earth-orbiting objects (third-party host `tle.ivanstanojevic.me`). | T3 | Irrelevant; also an external dependency NASA does not operate. |
| 16 | Vesta/Moon/Mars Trek WMTS | OGC WMTS tiles powering Moon Trek / Mars Trek / Vesta Trek (SSERVI + JPL Trek team): basemaps and data layers for the Moon and Mars. **Probe caveat:** the catalog's `api.nasa.gov/{mars,moon,vesta}-wmts/catalog/` paths returned `File does not exist`/404 on 2026-11-12; the maintained entry point is `trek.nasa.gov/tiles/apidoc/trekAPI.html?body=moon|mars`. | **T1** | The Moon/Mars half of the product: target-body basemaps and layers in the same WMTS idiom as GIBS, so one map client can show Earth candidate ↔ lunar/Martian target side by side. Verify every layer URL against `trek.nasa.gov` directly before committing to it. |

### Reading of the catalog

- Only **4 of 16** entries can carry the core task (GIBS, Trek WMTS, EONET, InSight),
  and two of those need handling care (InSight is frozen; Trek links must be taken from
  `trek.nasa.gov`, not the catalog proxy paths).
- The catalog contains **no elevation, geology/mineralogy, gravity, subsurface or
  per-point climate service**. Those are exactly the dimensions the challenge brief
  lists first. They must come from section 4 sources — which the brief permits
  ("NASA and other space agencies", "open sources").
- Several once-famous `api.nasa.gov` services (e.g. Mars Rover Photos, Earth imagery)
  are **not in the current 16-entry catalog**. Do not cite them from memory or old
  blog posts; if needed, re-verify existence at build time.

## 2. Live probe log (2026-11-12, reproducible)

| Probe | Result |
|---|---|
| `GET api.nasa.gov/assets/json/apis.json` | 200, 166,186 B, 16 entries |
| `GET api.nasa.gov/planetary/apod?api_key=DEMO_KEY` | 200 JSON dated 2026-11-12 (legacy path still up pre-2026-12-01) |
| `GET api.nasa.gov/insight_weather/?api_key=DEMO_KEY&feedtype=json&ver=1.0` | 200 JSON, sol 675: `AT.av −62.314 °C`, `PRE.av 750.563 Pa` |
| `GET eonet.gsfc.nasa.gov/api/v3/events?limit=2` | 200 JSON (e.g. `EONET_26157` Typhoon Cempaka) |
| `GET gibs.earthdata.nasa.gov/wmts/epsg4326/best/wmts.cgi?...GetCapabilities` | XML with 3,950 identifiers |
| `GET api.nasa.gov/{mars,vesta}-wmts/catalog/` | `File does not exist` |
| `GET api.nasa.gov/moon-wmts/catalog/` | 404 page |

## 3. Access rules that constrain architecture

1. One registered key = 1,000 req/h **shared across services** → all catalog-API calls
   go through a cached server-side proxy/ingest job, never per-visitor browser calls.
2. Tile services (GIBS, Trek WMTS) are the scalable path for the interactive map;
   JSON APIs are for ingest-time enrichment that we snapshot into our own store.
3. Everything ingestible must be snapshotted with provenance (URL, fetch date,
   response hash): InSight is frozen, APOD is migrating, Trek catalog paths already rot.

## 4. Required data beyond this catalog (named, not yet inventoried in depth)

These are the sources that actually carry elevation, geology, mineralogy and climate
for all three bodies. Each needs its own ingest contract before use; listing here is a
scope statement, not a claim of verified access.

| Body | Source | Carries |
|---|---|---|
| Earth | NASA Earthdata (CMR Search/STAC, VEDA) + GIBS | MODIS/VIIRS LST, snow, aerosols; Landsat/Sentinel via USGS/ESA |
| Earth | SRTM / ASTER GDEM / Copernicus DEM (OpenTopography, Earthdata) | Elevation, slope, roughness |
| Earth | NASA POWER | Per-point climatology (temperature, wind, insolation) for candidate sites |
| Earth | USGS / national geological surveys, OneGeology | Lithology, mineralogy |
| Moon | PDS: LRO LOLA (DEM), LROC (imagery), Diviner (temperature), LEND (hydrogen) | South-pole target characterization |
| Moon | USGS Astrogeology STAC/WMS, Moon Trek layers | Analysis-ready mosaics, illumination/PSR maps |
| Mars | PDS: MOLA (DEM), HiRISE/CTX (imagery), CRISM (mineralogy), THEMIS | Landing-site terrain and composition |
| Mars | ESA Planetary Science Archive (Mars Express HRSC), Mars Trek layers | Independent DEM/imagery |
| Both | NASA PDS Orbital Data Explorer, `planetary.data.nasa.gov` | Discovery across nodes |

Next research step (not done here): one row per *dataset* (not portal) with license,
resolution, coverage, STAC/WMTS endpoint and a live probe — same standard as section 2.
