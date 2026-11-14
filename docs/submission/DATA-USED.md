# Data used (W14, #25)

Status as of 2026-11-14 ~16:45 EST, from `data/snapshots/MANIFEST.json` at
main `03a040e`, the catalog rows in `data/catalog/` and open PRs. **Re-check
every status at feature freeze** (AGENTS.md rule 2). Only rows that feed a
published number go on the project page.

"On tab" = listed on the challenge Resources tab
([docs/challenge/challenge-page.md](../challenge/challenge-page.md#resources-tab)),
either directly or through the portal named.

## NASA

| Dataset | What we use it for | Licence (catalog row) | On tab | Status |
|---|---|---|---|---|
| MODIS/Terra LST monthly (MOD11C3 v061), DOI 10.5067/MODIS/MOD11C3.061 | Ground temperature per hexagon and month (L1, L1m) | CC0 | via Earthdata Search | on main (2023); 2014–2022 in #72 |
| MODIS land cover (MCD12C1 v061) | Barren, snow/ice and water share (L1) | CC0 | via Earthdata Search | on main |
| MODIS BRDF/albedo (MCD43C3 v061) | Earth albedo per hexagon | CC0 | via Earthdata Search | in PR #77 |
| MODIS burned area (MCD64A1) | Burned area by month (risks) | check catalog row at freeze | via Earthdata Search | #65 in progress |
| MERRA-2 aerosol (M2TMNXAER) | Dust optical depth by month | CC0 | via Earthdata Search | built on #68, not merged yet |
| NASA EONET v3 events | Named natural events near each site (risks) | NASA open data, EONET disclaimer (ADR-0006) | no (NASA, not on tab) | on main |
| **LRO Diviner Level 4** (polar products) | Moon south-pole surface temperature | US public domain | **yes, named on the tab** | downloaded, hashed and decoded (#75); not yet tied to target locations (#74) |
| MGS TES (thermal inertia, albedo, dust) | Mars thermal and surface targets | US public domain | via NASA PDS | decoded (#75); map projection under review (#74) |
| NASA GIBS (Worldview tiles) | Map base layer in the app | NASA open | via Worldview | used by `apps/atlas` |

## Other space agencies

| Dataset | Agency | Use | Licence | On tab | Status |
|---|---|---|---|---|---|
| Copernicus DEM GLO-30 (2021 release) | ESA / Copernicus | Elevation and slope (L1) | Copernicus DEM licence | via Copernicus Data Space | on main |
| ESA CCI Permafrost extent v5.0 (NH + Antarctica) | ESA | Permafrost probability (L1) | ESA CCI terms | via ESA Open Science Catalog | on main |
| CSA RCM / RADARSAT-1, JAXA G-Portal | CSA, JAXA | Inventoried only (`data/sources/agency-portals.yaml`, #74) | as recorded there | yes | not used for any number. Say so, don't list them as data used |

## Non-agency data

| Dataset | Use | Licence | Status |
|---|---|---|---|
| Global travel time to cities 2015 (Weiss et al.) | Travel time (logistics) | CC BY 3.0 (attribution required) | on main |
| OurAirports | Nearest paved-runway airport | public domain | on main |
| ORNL DAAC Pelletier soil/regolith thickness | Depth to bedrock (subsurface proxy) | check catalog row at freeze | in PR #77 |
| WDPA protected areas | Protected-land share | restricted, so we ship null unless the licence allows derived numbers (DATA-PIPELINE §9 #10) | not used |
| Past-campaign source documents (`campaign-sources`) | Quotes for the 6 campaign rows | per source, recorded in each campaign file | on main |

## Attribution text to paste (CC BY and agency terms)

- Travel time: Weiss, D.J. et al. (2018), *A global map of travel time to cities to assess inequalities in accessibility in 2015*, Nature 553. CC BY 3.0.
- Copernicus DEM: "© DLR e.V. 2010–2014 and © Airbus Defence and Space GmbH 2014–2018, provided under COPERNICUS by the European Union and ESA; all rights reserved." ⚠ Check this wording against the stored licence text before pasting.
- ESA CCI Permafrost: cite the product DOI from the catalog row. ⚠ Fill it in at freeze.
