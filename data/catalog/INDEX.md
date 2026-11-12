# Dataset registry index (generated 2026-11-12 by `scripts/registry_probe.py`; do not hand-edit)

Status values: `candidate` (probed, not yet adopted by a work order) · `restricted` (license limits use) · `unresolved` (endpoint or license not confirmed live). A license counts as verified only when its expected text was found live (see probe log).

| datasetId | body | dimensions | archive | status | license | lic. verified | probe |
|---|---|---|---|---|---|---|---|
| [aster-gdem-v3](aster-gdem-v3.yaml) | earth | terrain | Earthdata (LP DAAC, LPCLOUD) | candidate | cc0 | yes | CMR C1711961296-LPCLOUD: HTTP 200, ASTGTM v003, DOI 10.5067/ASTER/ASTGTM.003, granules 22912 |
| [copernicus-dem-glo30](copernicus-dem-glo30.yaml) | earth | terrain | ESA Copernicus via AWS Registry of Open Data | candidate | copernicus-dem-licence | yes | HTTP 200, 10002 B, sha256 04b2d63198ac… |
| [eonet-v3-events](eonet-v3-events.yaml) | earth | dustProcess | NASA EONET | candidate | unresolved | no | HTTP 200, 4469 B, sha256 a3e9c492a313… |
| [esa-cci-permafrost-extent-antarctica](esa-cci-permafrost-extent-antarctica.yaml) | earth | waterIce, thermal | CEDA (ESA CCI) | candidate | esa-cci-permafrost-terms | yes | HTTP 200, 60652 B, sha256 d0a1644130b7… |
| [esa-cci-permafrost-extent-nh](esa-cci-permafrost-extent-nh.yaml) | earth | waterIce, thermal | CEDA (ESA CCI) | candidate | esa-cci-permafrost-terms | yes | HTTP 200, 60852 B, sha256 a6226efb71e9… |
| [gibs-wmts](gibs-wmts.yaml) | earth | — | Earthdata GIBS | candidate | cc0 | yes | HTTP 200, 5319261 B, sha256 2576475e8a19…, layers 1330 |
| [glim-0p5deg](glim-0p5deg.yaml) | earth | surfaceMaterial | PANGAEA | candidate | cc-by-3.0 | yes | HTTP 200, 27662 B, sha256 3f99fe1da8a1… |
| [merra2-m2tmnxaer](merra2-m2tmnxaer.yaml) | earth | dustProcess | Earthdata (GES DISC) | candidate | cc0 | yes | CMR C1276812866-GES_DISC: HTTP 200, M2TMNXAER v5.12.4, DOI 10.5067/FH9A0MLJPC7N, granules 561 |
| [modis-mcd12c1](modis-mcd12c1.yaml) | earth | surfaceMaterial | Earthdata (LP DAAC, LPCLOUD) | candidate | cc0 | yes | CMR C2484078896-LPCLOUD: HTTP 200, MCD12C1 v061, DOI 10.5067/MODIS/MCD12C1.061, granules 25 |
| [modis-mod11a2](modis-mod11a2.yaml) | earth | thermal | Earthdata (LP DAAC, LPCLOUD) | candidate | cc0 | yes | CMR C2269056084-LPCLOUD: HTTP 200, MOD11A2 v061, DOI 10.5067/MODIS/MOD11A2.061, granules 388853 |
| [modis-mod11c3](modis-mod11c3.yaml) | earth | thermal | Earthdata (LP DAAC, LPCLOUD) | candidate | cc0 | yes | CMR C2565788897-LPCLOUD: HTTP 200, MOD11C3 v061, DOI 10.5067/MODIS/MOD11C3.061, granules 321 |
| [modis-mod13c2](modis-mod13c2.yaml) | earth | surfaceMaterial | Earthdata (LP DAAC, LPCLOUD) | candidate | cc0 | yes | CMR C2565788914-LPCLOUD: HTTP 200, MOD13C2 v061, DOI 10.5067/MODIS/MOD13C2.061, granules 321 |
| [modis-mod44b](modis-mod44b.yaml) | earth | surfaceMaterial | Earthdata (LP DAAC, LPCLOUD) | candidate | cc0 | yes | CMR C2565805839-LPCLOUD: HTTP 200, MOD44B v061, DOI 10.5067/MODIS/MOD44B.061, granules 7564 |
| [modis-myd11c3](modis-myd11c3.yaml) | earth | thermal | Earthdata (LP DAAC, LPCLOUD) | candidate | cc0 | yes | CMR C2565794044-LPCLOUD: HTTP 200, MYD11C3 v061, DOI 10.5067/MODIS/MYD11C3.061, granules 292 |
| [nasa-power-climatology](nasa-power-climatology.yaml) | earth | thermal, illumination | NASA LaRC POWER | candidate | unresolved | no | HTTP 200, 1379 B, sha256 66317835294b… |
| [nasadem-hgt](nasadem-hgt.yaml) | earth | terrain | Earthdata (LP DAAC, LPCLOUD) | candidate | cc0 | yes | CMR C2763264762-LPCLOUD: HTTP 200, NASADEM_HGT v001, DOI 10.5067/MEASURES/NASADEM/NASADEM_HGT.001, granules 14520 |
| [nsidc-ggd318-permafrost](nsidc-ggd318-permafrost.yaml) | earth | waterIce | NSIDC | candidate | unresolved | no | HTTP 200, 111118 B, sha256 a08b15115ba8… |
| [travel-time-to-cities-2015](travel-time-to-cities-2015.yaml) | earth | operations | unresolved (Malaria Atlas Project / figshare) | unresolved | unresolved | no | HTTP 200, 61222 B, sha256 29513c14e8cc… — PROBE FAILED (expectation not met) |
| [wdpa-protected-areas](wdpa-protected-areas.yaml) | earth | operations | UNEP-WCMC Protected Planet | restricted | wdpa-terms-noncommercial | yes | HTTP 200, 55864 B, sha256 6a8769da7649… |
| [crism-mro](crism-mro.yaml) | mars | surfaceMaterial | PDS Geosciences Node | candidate | unresolved | no | HTTP 200, 58477 B, sha256 df7a7e7bf3c9… |
| [ctx-dtms-usgs-stac](ctx-dtms-usgs-stac.yaml) | mars | terrain | USGS Astrogeology STAC | candidate | cc0-1.0 | yes | STAC mro_ctx_controlled_usgs_dtms: HTTP 200, license CC0-1.0, items 44628 |
| [hirise-dtms-usgs-stac](hirise-dtms-usgs-stac.yaml) | mars | terrain | USGS Astrogeology STAC | candidate | cc0-1.0 | yes | STAC mro_hirise_socet_dtms: HTTP 200, license CC0-1.0, items 1262 |
| [insight-weather-archive](insight-weather-archive.yaml) | mars | thermal | api.nasa.gov | candidate | unresolved | no | HTTP 200, 36505 B, sha256 c5df364deee3… |
| [mars-dust-climatology-lmd](mars-dust-climatology-lmd.yaml) | mars | dustProcess | LMD (Mars Climate Database team) | candidate | unresolved | no | HTTP 200, 12713 B, sha256 2a4ed4397a87… |
| [mars-trek-wmts](mars-trek-wmts.yaml) | mars | — | NASA Solar System Treks | candidate | unresolved | no | HTTP 200, 7040 B, sha256 2fb4722b5af0…, layers 1 |
| [mcs-mro](mcs-mro.yaml) | mars | thermal, dustProcess | PDS Atmospheres Node | candidate | unresolved | no | HTTP 200, 70345 B, sha256 c3a8eab5de2d… |
| [mola-hrsc-blended-dem](mola-hrsc-blended-dem.yaml) | mars | terrain | USGS Astrogeology (Astropedia) | candidate | cc0+cc-by-sa-3.0-igo | yes | HTTP 200, 36482 B, sha256 9309a442805b… |
| [mola-megdr](mola-megdr.yaml) | mars | terrain | PDS Geosciences Node | candidate | unresolved | no | HTTP 200, 12896 B, sha256 a5fb768fdf2a… |
| [swim-mars-ice](swim-mars-ice.yaml) | mars | waterIce | PSI SWIM project | candidate | unresolved | no | HTTP 200, 13418 B, sha256 3e264e6c5001… |
| [tes-mgs](tes-mgs.yaml) | mars | thermal, surfaceMaterial, dustProcess | PDS Geosciences Node | candidate | unresolved | no | HTTP 200, 27468 B, sha256 7b4e7ce99eec… |
| [themis-ir-controlled-mosaics](themis-ir-controlled-mosaics.yaml) | mars | thermal, surfaceMaterial | USGS Astrogeology STAC | candidate | cc0-1.0 | yes | STAC mo_themis_controlled_mosaics: HTTP 200, license CC0-1.0, items 56 |
| [diviner-l4](diviner-l4.yaml) | moon | thermal, waterIce | PDS Geosciences Node | candidate | unresolved | no | HTTP 200, 39498 B, sha256 89f3c4412e54… |
| [kaguya-tc-dtm-southpolar](kaguya-tc-dtm-southpolar.yaml) | moon | terrain | USGS Astrogeology STAC | candidate | cc0-1.0 | yes | STAC kaguya_terrain_camera_usgs_dtms_v2_southpolar: HTTP 200, license CC0-1.0, items 19646 |
| [lamp](lamp.yaml) | moon | waterIce | PDS Imaging Node | candidate | unresolved | no | HTTP 200, 193632 B, sha256 e849112f7665… |
| [lend](lend.yaml) | moon | waterIce | PDS Geosciences Node | candidate | unresolved | no | HTTP 200, 31256 B, sha256 1f28ac413c32… |
| [lola-gdr](lola-gdr.yaml) | moon | terrain | PDS Geosciences Node | candidate | unresolved | no | HTTP 200, 582 B, sha256 b8146dff064c… |
| [lola-polar-illumination](lola-polar-illumination.yaml) | moon | illumination | NASA GSFC PGDA (products also on PDS) | candidate | unresolved | no | HTTP 200, 27981 B, sha256 aca046555f29… |
| [lola-shots-usgs-stac](lola-shots-usgs-stac.yaml) | moon | terrain | USGS Astrogeology STAC | candidate | cc0-1.0 | yes | STAC lunar_orbiter_laser_altimeter: HTTP 200, license CC0-1.0, items 288 |
| [lola-south-pole-ldem-2023](lola-south-pole-ldem-2023.yaml) | moon | terrain, illumination, waterIce | NASA GSFC PGDA | candidate | citation-required-no-license-stated | yes | HTTP 200, 30348 B, sha256 cd41983f4a9f… |
| [lroc-wac-global](lroc-wac-global.yaml) | moon | — | LROC (ASU) RDR | candidate | unresolved | no | HTTP 200, 36654 B, sha256 0880337b772f… |
| [moon-trek-wmts](moon-trek-wmts.yaml) | moon | — | NASA Solar System Treks | candidate | unresolved | no | HTTP 200, 7241 B, sha256 44ea74fb1697…, layers 1 |
