# Data used (W14, #25)

Status as of **2026-11-15 ~03:15 UTC**, from `data/snapshots/MANIFEST.json`
(853 entries, 42 datasets), the `license` block of each `data/catalog/<id>.yaml`
row and the source lists in `data/pipeline/columns.yaml`, all at main
`60edc9c`. **Re-check every status at feature freeze** (AGENTS.md rule 2).

Only rows in section 1 feed a number the workflow shows, so only those go on
the project page as "data used". Section 2 is prepared but not read by the
engine yet. Say "prepared", or leave it out. "Verified" means the catalog
row's `license.verified` is `true` (a probe matched the licence text). It does
not mean the data is scientifically right.

"On tab" = listed on the challenge Resources tab
([docs/challenge/challenge-page.md](../challenge/challenge-page.md#resources-tab)),
either directly or through the portal named.

## 1. Feeds the assembled tables (`_derived/assembled/sites-r4*`, #127)

### NASA

| Dataset | What we use it for | Licence (catalog) | On tab | Status |
|---|---|---|---|---|
| MODIS/Terra LST monthly (MOD11C3 v061), DOI 10.5067/MODIS/MOD11C3.061 | Ground temperature per hexagon and month, 2023 plus 2014–2022 spread | CC0, verified | via Earthdata Search | on main (120 granules). ⚠ QC-bit filtering not applied yet (#76) |
| MODIS/Aqua LST monthly (MYD11C3 v061) | Second (afternoon/night) temperature per month | CC0, verified | via Earthdata Search | on main (#117) |
| MODIS land cover (MCD12C1 v061) | Barren, snow/ice and water share | CC0, verified | via Earthdata Search | on main |
| MODIS BRDF/albedo (MCD43C3 v061) | Earth albedo per hexagon and month | CC0, verified | via Earthdata Search | on main (#77, wording fixed #118, rebuilt #127) |
| MODIS burned area (MCD64A1 v061) | Burned share by calendar month, 2015–2024 (risks) | CC0, verified | via Earthdata Search | on main (#91) |
| MERRA-2 aerosol (M2TMNXAER) | Dust optical depth by month | CC0, verified | via Earthdata Search | on main (#120), required since #127 |
| MERRA-2 surface flux + single-level (M2TMNXFLX, M2TMNXSLV) | 10 m wind speed by month | CC0, verified | via Earthdata Search | on main (#116) |
| NASA EONET v3 events | Named natural events near each site (risks) | NASA open data + EONET disclaimer (ADR-0006), verified | no (NASA, not on tab) | on main |
| NASA GIBS (Worldview tiles) | Map base layer in the app | NASA open | via Worldview | used by `apps/atlas` (no numbers) |

### Other space agencies

| Dataset | Agency | Use | Licence (catalog) | On tab | Status |
|---|---|---|---|---|---|
| Copernicus DEM GLO-30 (2021 release) | ESA / Copernicus | Elevation and slope | Copernicus DEM licence, verified | via Copernicus Data Space | on main |
| ESA CCI Permafrost extent v5.0 (NH + Antarctica) | ESA | Permafrost probability | ESA CCI terms, verified | via ESA Open Science Catalog | on main. Null outside 25–85° N / 60–85° S |

### Non-agency data

| Dataset | Use | Licence (catalog) | Status |
|---|---|---|---|
| Global travel time to cities 2015 (Weiss et al.) | Travel time (logistics) | CC BY 3.0, verified (attribution required) | on main |
| OurAirports | Nearest paved-runway airport | public domain, verified | on main |
| ORNL DAAC global soil, regolith and sediment thickness | Depth to bedrock (subsurface proxy) | ORNL DAAC open, no restriction, verified | on main (#77). Modelled, 50 m cap, null below 60° S |
| Past-campaign source documents (`campaign-sources`) | Quotes for the 6 campaign rows | per source, recorded in each MANIFEST entry | on main |

## 2. Prepared on main, not read by the engine yet

These are Moon/Mars target products and extra Earth layers, fetched and hashed
with their own checks. None feeds a workflow number until the engine reads it.

| Dataset | Body | Licence (catalog) | Status |
|---|---|---|---|
| **LRO Diviner Level 4** (GCP, GDR, PCP, polar resource products) | Moon | US public domain, verified. **Named on the tab** | on main (#75, #131) |
| LRO LEND neutron maps | Moon | US public domain, verified | on main (#115) |
| Lunar Prospector GRS/NS maps | Moon | US public domain, verified | on main (#115) |
| LRO LAMP, Mini-RF, LROC WAC global | Moon | US public domain, verified | on main (#130) |
| Kaguya MI FeO map (Lemelin et al.) | Moon (JAXA) | JAXA conditions, verified | on main (#130) |
| Unified Geologic Map of the Moon; LROC pits atlas | Moon | CC0 / US public domain, verified | on main (#124) |
| Artemis III candidate regions; IAU nomenclature centres | Moon, Mars | US public domain (Artemis row: **not verified**) | on main (#113) |
| MGS TES; MGS MOLA MEGDR | Mars | US public domain, verified | on main (TES #75, MEGDR #133) |
| MOLA–HRSC blended DEM; CTX and HiRISE DTMs | Mars | CC0 + CC BY-SA 3.0 IGO / CC0, verified | on main (#133) |
| Mars Odyssey GRS element maps | Mars | US public domain, verified | on main (#125) |
| MRO CRISM MTRDR; THEMIS IR controlled mosaics; MCS | Mars | US public domain / CC0, verified | on main (#126, #123) |
| Mars landed-mission site documents | Mars | US public domain (**not verified**) | on main (#113) |
| MODIS VCF (MOD44B), MOD21C3 | Earth | CC0, verified | VCF on main (#129), not yet assembled. MOD21C3 probed only |
| EMIT L2B minerals | Earth | CC0, verified | on main (#135): per-hexagon composite from a deterministic streamed sample, not every granule |

## 3. Blocked or not used. Don't list these as data used

| Dataset | Why |
|---|---|
| WDPA protected areas | Restricted licence. `protected_pct` is 100 % null (`licence-restricted`) |
| ALOS PALSAR RTC (#111) | Module on main, but scenes need an interactive Earthdata login (401 with a token). Rows stay null |
| LROC NAC boulders (Watkins); Robbins Moon craters | Licence **unresolved**. Values not used |
| NSIDC GGD318 permafrost; Earth Impact Database | Access blocked (#129) |
| M3 (Moon Mineralogy Mapper); SWIM Mars ice | M3 licence blocked (#130); SWIM host down (#125) |
| CSA RCM / RADARSAT-1, JAXA G-Portal | Inventoried only (`data/sources/agency-portals.yaml`, #74). No numbers |

## Attribution text to paste (CC BY and agency terms)

- Travel time: Weiss, D.J. et al. (2018), *A global map of travel time to cities to assess inequalities in accessibility in 2015*, Nature 553. CC BY 3.0.
- Copernicus DEM: "© DLR e.V. 2010–2014 and © Airbus Defence and Space GmbH 2014–2018, provided under COPERNICUS by the European Union and ESA; all rights reserved." ⚠ Check this wording against the stored licence text before pasting.
- ESA CCI Permafrost: cite the product DOI from the catalog row. ⚠ Fill it in at freeze.
- MOLA–HRSC blended DEM (if it reaches section 1): CC BY-SA 3.0 IGO needs attribution and share-alike. ⚠ Copy the credit line from its catalog row.
- Kaguya MI (if it reaches section 1): JAXA conditions need the JAXA credit. ⚠ Copy it from the catalog row.
