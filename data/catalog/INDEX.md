# Dataset registry index (generated 2026-11-13 by `scripts/registry_probe.py`; do not hand-edit)

Status values: `candidate` (probed, not yet adopted by a work order) · `restricted` (license limits use) · `unresolved` (endpoint or license not confirmed live). A license counts as verified only when its expected text was found live (see probe log).

| datasetId | body | dimensions | archive | status | license | lic. verified | probe |
|---|---|---|---|---|---|---|---|
| [alos-palsar-rtc-high](alos-palsar-rtc-high.yaml) | earth | terrain, operations | Earthdata (ASF DAAC) | candidate | asf-alos-palsar-rtc-eula | yes | CMR C1206487504-ASF: HTTP 200, ALOS_PSR_RTC_HIGH v1, DOI 10.5067/Z97HFCNKR6VA, granules 506657 |
| [arcticdem](arcticdem.yaml) | earth | terrain | Polar Geospatial Center via AWS Registry of Open Data | candidate | cc-by-4.0 | yes | HTTP 200, 11617 B, sha256 849ac06a12aa… |
| [aster-gdem-v3](aster-gdem-v3.yaml) | earth | terrain | Earthdata (LP DAAC, LPCLOUD) | candidate | cc0 | yes | CMR C1711961296-LPCLOUD: HTTP 200, ASTGTM v003, DOI 10.5067/ASTER/ASTGTM.003, granules 22912 |
| [aster-ged-ag100](aster-ged-ag100.yaml) | earth | surfaceMaterial, thermal | Earthdata (LP DAAC, LPCLOUD) | candidate | cc0 | yes | CMR C2763266348-LPCLOUD: HTTP 200, AG100 v003, DOI 10.5067/COMMUNITY/ASTER_GED/AG100.003, granules 24873 |
| [aster-ged-ag1km](aster-ged-ag1km.yaml) | earth | surfaceMaterial, thermal | Earthdata (LP DAAC, LPCLOUD) | candidate | cc0 | yes | CMR C2763266350-LPCLOUD: HTTP 200, AG1km v003, DOI 10.5067/COMMUNITY/ASTER_GED/AG1KM.003, granules 24873 |
| [copernicus-dem-glo30](copernicus-dem-glo30.yaml) | earth | terrain | ESA Copernicus via AWS Registry of Open Data | candidate | copernicus-dem-licence | yes | HTTP 200, 10002 B, sha256 04b2d63198ac… |
| [earth-impact-database](earth-impact-database.yaml) | earth | terrain | PASSC (unresolved) | unresolved | unresolved | no | HTTP 200, 114 B, sha256 6dc9c7fc93bb… — PROBE FAILED (expectation not met) |
| [emit-l2b-min-v002](emit-l2b-min-v002.yaml) | earth | surfaceMaterial | Earthdata (LP DAAC, LPCLOUD) | candidate | cc0 | yes | CMR C4079846859-LPCLOUD: HTTP 200, EMITL2BMIN v002, DOI 10.5067/EMIT/EMITL2BMIN.002, granules 124877 |
| [eonet-v3-events](eonet-v3-events.yaml) | earth | dustProcess | NASA EONET | candidate | unresolved | no | HTTP 200, 4469 B, sha256 a3e9c492a313… |
| [esa-cci-permafrost-extent-antarctica](esa-cci-permafrost-extent-antarctica.yaml) | earth | waterIce, thermal | CEDA (ESA CCI) | candidate | esa-cci-permafrost-terms | yes | HTTP 200, 60652 B, sha256 abc77a7a6abe… |
| [esa-cci-permafrost-extent-nh](esa-cci-permafrost-extent-nh.yaml) | earth | waterIce, thermal | CEDA (ESA CCI) | candidate | esa-cci-permafrost-terms | yes | HTTP 200, 60852 B, sha256 12868e41675e… |
| [gibs-wmts](gibs-wmts.yaml) | earth | — | Earthdata GIBS | candidate | cc0 | yes | HTTP 200, 5319261 B, sha256 4c0c1ecfef51…, layers 1330 |
| [glim-0p5deg](glim-0p5deg.yaml) | earth | surfaceMaterial | PANGAEA | candidate | cc-by-3.0 | yes | HTTP 200, 27662 B, sha256 3f99fe1da8a1… |
| [merra2-m2t1nxslv](merra2-m2t1nxslv.yaml) | earth | thermal, operations | Earthdata (GES DISC) | candidate | cc0 | yes | CMR C1276812863-GES_DISC: HTTP 200, M2T1NXSLV v5.12.4, DOI 10.5067/VJAFPLI1CSIV, granules 17076 |
| [merra2-m2tmnxaer](merra2-m2tmnxaer.yaml) | earth | dustProcess | Earthdata (GES DISC) | candidate | cc0 | yes | CMR C1276812866-GES_DISC: HTTP 200, M2TMNXAER v5.12.4, DOI 10.5067/FH9A0MLJPC7N, granules 561 |
| [merra2-m2tmnxslv](merra2-m2tmnxslv.yaml) | earth | thermal, operations | Earthdata (GES DISC) | candidate | cc0 | yes | CMR C1276812859-GES_DISC: HTTP 200, M2TMNXSLV v5.12.4, DOI 10.5067/AP1B0BA5PD2K, granules 561 |
| [modis-mcd12c1](modis-mcd12c1.yaml) | earth | surfaceMaterial | Earthdata (LP DAAC, LPCLOUD) | candidate | cc0 | yes | CMR C2484078896-LPCLOUD: HTTP 200, MCD12C1 v061, DOI 10.5067/MODIS/MCD12C1.061, granules 25 |
| [modis-mcd43a3-albedo](modis-mcd43a3-albedo.yaml) | earth | surfaceMaterial, thermal | Earthdata (LP DAAC, LPCLOUD) | candidate | cc0 | yes | CMR C2278860820-LPCLOUD: HTTP 200, MCD43A3 v061, DOI 10.5067/MODIS/MCD43A3.061, granules 2997734 |
| [modis-mcd43c3-albedo](modis-mcd43c3-albedo.yaml) | earth | surfaceMaterial, thermal | Earthdata (LP DAAC, LPCLOUD) | candidate | cc0 | yes | CMR C2532068039-LPCLOUD: HTTP 200, MCD43C3 v061, DOI 10.5067/MODIS/MCD43C3.061, granules 9748 |
| [modis-mod11a2](modis-mod11a2.yaml) | earth | thermal | Earthdata (LP DAAC, LPCLOUD) | candidate | cc0 | yes | CMR C2269056084-LPCLOUD: HTTP 200, MOD11A2 v061, DOI 10.5067/MODIS/MOD11A2.061, granules 388853 |
| [modis-mod11c1-daily](modis-mod11c1-daily.yaml) | earth | thermal | Earthdata (LP DAAC, LPCLOUD) | candidate | cc0 | yes | CMR C2565788888-LPCLOUD: HTTP 200, MOD11C1 v061, DOI 10.5067/MODIS/MOD11C1.061, granules 9643 |
| [modis-mod11c3](modis-mod11c3.yaml) | earth | thermal | Earthdata (LP DAAC, LPCLOUD) | candidate | cc0 | yes | CMR C2565788897-LPCLOUD: HTTP 200, MOD11C3 v061, DOI 10.5067/MODIS/MOD11C3.061, granules 321 |
| [modis-mod13c2](modis-mod13c2.yaml) | earth | surfaceMaterial | Earthdata (LP DAAC, LPCLOUD) | candidate | cc0 | yes | CMR C2565788914-LPCLOUD: HTTP 200, MOD13C2 v061, DOI 10.5067/MODIS/MOD13C2.061, granules 321 |
| [modis-mod21c3](modis-mod21c3.yaml) | earth | thermal | Earthdata (LP DAAC, LPCLOUD) | candidate | cc0 | yes | CMR C2565791050-LPCLOUD: HTTP 200, MOD21C3 v061, DOI 10.5067/MODIS/MOD21C3.061, granules 323 |
| [modis-mod44b](modis-mod44b.yaml) | earth | surfaceMaterial | Earthdata (LP DAAC, LPCLOUD) | candidate | cc0 | yes | CMR C2565805839-LPCLOUD: HTTP 200, MOD44B v061, DOI 10.5067/MODIS/MOD44B.061, granules 7564 |
| [modis-myd11c3](modis-myd11c3.yaml) | earth | thermal | Earthdata (LP DAAC, LPCLOUD) | candidate | cc0 | yes | CMR C2565794044-LPCLOUD: HTTP 200, MYD11C3 v061, DOI 10.5067/MODIS/MYD11C3.061, granules 292 |
| [nasa-power-climatology](nasa-power-climatology.yaml) | earth | thermal, illumination | NASA LaRC POWER | candidate | unresolved | no | HTTP 200, 1379 B, sha256 cc42282c69d8… |
| [nasadem-hgt](nasadem-hgt.yaml) | earth | terrain | Earthdata (LP DAAC, LPCLOUD) | candidate | cc0 | yes | CMR C2763264762-LPCLOUD: HTTP 200, NASADEM_HGT v001, DOI 10.5067/MEASURES/NASADEM/NASADEM_HGT.001, granules 14520 |
| [nsidc-ggd318-permafrost](nsidc-ggd318-permafrost.yaml) | earth | waterIce | NSIDC | candidate | unresolved | no | HTTP 200, 111118 B, sha256 9485d55339c9… |
| [rema](rema.yaml) | earth | terrain | Polar Geospatial Center via AWS Registry of Open Data | candidate | cc-by-4.0 | yes | HTTP 200, 11614 B, sha256 a04dde8186e5… |
| [smap-spl3smp-e](smap-spl3smp-e.yaml) | earth | waterIce | Earthdata (NSIDC DAAC) | candidate | cc0 | yes | CMR C2938664763-NSIDC_CPRD: HTTP 200, SPL3SMP_E v006, DOI 10.5067/M20OXIZHY3RJ, granules 4166 |
| [soilgrids](soilgrids.yaml) | earth | subsurface | ISRIC | candidate | cc-by-4.0 | yes | HTTP 200, 279476 B, sha256 e32f3952255b… |
| [travel-time-to-cities-2015](travel-time-to-cities-2015.yaml) | earth | operations | unresolved (Malaria Atlas Project / figshare) | unresolved | unresolved | no | HTTP 200, 60488 B, sha256 fd5465d4f113… — PROBE FAILED (expectation not met) |
| [wdpa-protected-areas](wdpa-protected-areas.yaml) | earth | operations | UNEP-WCMC Protected Planet | restricted | wdpa-terms-noncommercial | yes | HTTP 200, 55864 B, sha256 3f70d4737af1… |
| [crism-mro](crism-mro.yaml) | mars | surfaceMaterial | PDS Geosciences Node | candidate | us-pd | yes | HTTP 200, 58477 B, sha256 df7a7e7bf3c9… |
| [ctx-dtms-usgs-stac](ctx-dtms-usgs-stac.yaml) | mars | terrain | USGS Astrogeology STAC | candidate | cc0-1.0 | yes | STAC mro_ctx_controlled_usgs_dtms: HTTP 200, license CC0-1.0, items 44628 |
| [hirise-dtms-usgs-stac](hirise-dtms-usgs-stac.yaml) | mars | terrain | USGS Astrogeology STAC | candidate | cc0-1.0 | yes | STAC mro_hirise_socet_dtms: HTTP 200, license CC0-1.0, items 1262 |
| [insight-weather-archive](insight-weather-archive.yaml) | mars | thermal | api.nasa.gov | candidate | unresolved | no | HTTP 429, 174 B, sha256 3f95d2152942… — PROBE FAILED (HTTP 429) |
| [mars-dust-climatology-lmd](mars-dust-climatology-lmd.yaml) | mars | dustProcess | LMD (Mars Climate Database team) | candidate | cc-by-sa-3.0 | yes | HTTP 200, 12713 B, sha256 2a4ed4397a87… |
| [mars-geologic-map-sim3292](mars-geologic-map-sim3292.yaml) | mars | surfaceMaterial | USGS Publications Warehouse | candidate | unresolved | no | HTTP 200, 83871 B, sha256 471f4d8f9f82… |
| [mars-trek-wmts](mars-trek-wmts.yaml) | mars | — | NASA Solar System Treks | candidate | unresolved | no | HTTP 200, 7040 B, sha256 2fb4722b5af0…, layers 1 |
| [mcs-mro](mcs-mro.yaml) | mars | thermal, dustProcess | PDS Atmospheres Node | candidate | us-pd | yes | HTTP 200, 70345 B, sha256 c3a8eab5de2d… |
| [mgc3-mars-caves](mgc3-mars-caves.yaml) | mars | subsurface | USGS Astrogeology (Astropedia); PDS archive bundle | candidate | us-pd | yes | HTTP 200, 24560 B, sha256 ab8f70427c79… |
| [mola-hrsc-blended-dem](mola-hrsc-blended-dem.yaml) | mars | terrain | USGS Astrogeology (Astropedia) | candidate | cc0+cc-by-sa-3.0-igo | yes | HTTP 200, 36482 B, sha256 c27c8dbc0b5e… |
| [mola-megdr](mola-megdr.yaml) | mars | terrain | PDS Geosciences Node | candidate | us-pd | yes | HTTP 200, 12896 B, sha256 a5fb768fdf2a… |
| [ody-grs-pds](ody-grs-pds.yaml) | mars | surfaceMaterial, waterIce | PDS Geosciences Node | candidate | unresolved | no | HTTP 200, 29231 B, sha256 81a37882aa26… |
| [robbins-mars-craters](robbins-mars-craters.yaml) | mars | terrain | USGS Astrogeology (pygeoapi) | candidate | unresolved | no | HTTP 200, 2950 B, sha256 1e89ec9cc43e… |
| [swim-mars-ice](swim-mars-ice.yaml) | mars | waterIce | PSI SWIM project | candidate | unresolved | no | HTTP 200, 13418 B, sha256 3e264e6c5001… |
| [tes-mgs](tes-mgs.yaml) | mars | thermal, surfaceMaterial, dustProcess | PDS Geosciences Node | candidate | us-pd | yes | HTTP 200, 27468 B, sha256 7b4e7ce99eec… |
| [themis-ir-controlled-mosaics](themis-ir-controlled-mosaics.yaml) | mars | thermal, surfaceMaterial | USGS Astrogeology STAC | candidate | cc0-1.0 | yes | STAC mo_themis_controlled_mosaics: HTTP 200, license CC0-1.0, items 56 |
| [diviner-l4](diviner-l4.yaml) | moon | thermal, waterIce | PDS Geosciences Node | candidate | us-pd | yes | HTTP 200, 39498 B, sha256 89f3c4412e54… |
| [kaguya-mi-59mpp](kaguya-mi-59mpp.yaml) | moon | surfaceMaterial | USGS Astrogeology (Astropedia) | candidate | jaxa-conditions | yes | HTTP 200, 27722 B, sha256 e6bed4e61f76… |
| [kaguya-tc-dtm-southpolar](kaguya-tc-dtm-southpolar.yaml) | moon | terrain | USGS Astrogeology STAC | candidate | cc0-1.0 | yes | STAC kaguya_terrain_camera_usgs_dtms_v2_southpolar: HTTP 200, license CC0-1.0, items 19646 |
| [lamp](lamp.yaml) | moon | waterIce | PDS Imaging Node | candidate | us-pd | yes | HTTP 200, 193632 B, sha256 e849112f7665… |
| [lend](lend.yaml) | moon | waterIce | PDS Geosciences Node | candidate | us-pd | yes | HTTP 200, 31256 B, sha256 1f28ac413c32… |
| [lola-gdr](lola-gdr.yaml) | moon | terrain | PDS Geosciences Node | candidate | us-pd | yes | HTTP 200, 582 B, sha256 b8146dff064c… |
| [lola-polar-illumination](lola-polar-illumination.yaml) | moon | illumination | NASA GSFC PGDA (products also on PDS) | candidate | unresolved | no | HTTP 200, 27981 B, sha256 aca046555f29… |
| [lola-shots-usgs-stac](lola-shots-usgs-stac.yaml) | moon | terrain | USGS Astrogeology STAC | candidate | cc0-1.0 | yes | STAC lunar_orbiter_laser_altimeter: HTTP 200, license CC0-1.0, items 288 |
| [lola-south-pole-ldem-2023](lola-south-pole-ldem-2023.yaml) | moon | terrain, illumination, waterIce | NASA GSFC PGDA | candidate | citation-required-no-license-stated | yes | HTTP 200, 30348 B, sha256 cd41983f4a9f… |
| [lp-grs-pds](lp-grs-pds.yaml) | moon | surfaceMaterial, waterIce | PDS Geosciences Node | candidate | us-pd | yes | HTTP 200, 24306 B, sha256 9742a3163af1… |
| [lroc-nac-boulders-watkins](lroc-nac-boulders-watkins.yaml) | moon | terrain | USGS Astrogeology (Astropedia) | candidate | unresolved | no | HTTP 200, 18873 B, sha256 cf68d0d4f08c… |
| [lroc-pits-atlas](lroc-pits-atlas.yaml) | moon | subsurface | LROC (ASU) | candidate | unresolved | no | HTTP 200, 40605 B, sha256 74fb23d82359… |
| [lroc-wac-global](lroc-wac-global.yaml) | moon | — | LROC (ASU) RDR | candidate | us-pd | yes | HTTP 200, 36654 B, sha256 0880337b772f… |
| [m3-pds](m3-pds.yaml) | moon | surfaceMaterial, waterIce | PDS Imaging Node | candidate | unresolved | no | HTTP 200, 6960 B, sha256 2543dca3defa… |
| [minirf-pds](minirf-pds.yaml) | moon | waterIce, terrain | PDS Geosciences Node | candidate | us-pd | yes | HTTP 200, 38682 B, sha256 6de9eac71b68… |
| [moon-trek-wmts](moon-trek-wmts.yaml) | moon | — | NASA Solar System Treks | candidate | unresolved | no | HTTP 200, 7241 B, sha256 44ea74fb1697…, layers 1 |
| [robbins-moon-craters](robbins-moon-craters.yaml) | moon | terrain | USGS Astrogeology (Astropedia) | candidate | unresolved | no | HTTP 200, 30423 B, sha256 1bbc71617adc… |
| [unified-geologic-map-moon](unified-geologic-map-moon.yaml) | moon | surfaceMaterial | USGS Astrogeology (Astropedia) | candidate | cc0 | yes | HTTP 200, 26134 B, sha256 967908b8032a… |
