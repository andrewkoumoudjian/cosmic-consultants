# Challenge page: Identify Earth Locations that Analog the Permanent Moon Base Locations and Mars

Verbatim copy of the official NASA Space Apps Challenge 2026 page, kept so every
contributor reads the same text. Analysis of this text (facts, requirements,
propositions) is in [`../research/02-challenge-brief.md`](../research/02-challenge-brief.md).
The challenge author's video is transcribed in
[`video-transcript.md`](video-transcript.md).

## Provenance

| Field | Value |
|---|---|
| URL | https://www.spaceappschallenge.org/2026/challenges/permanent-moon-base-locations-and-mars/ |
| Fetched (latest) | 2026-11-14T14:15:30Z, HTTP 200, 85,777 bytes (A0, issue #1) |
| sha256 of fetched HTML (latest) | `38ae19ad5f8a4ac0c4a8df05e5798112b93a1369d895fc3e852dad06064d057b` |
| Fetched (first) | 2026-11-12T21:10:42Z, HTTP 200, 79,220 bytes, sha256 `0a17b0c77a144b4a951eeb468ee806de8813ae3c0609f017ec250698564fbb73` |
| Extraction | The page is JS-rendered. Text was taken from the embedded Next.js payload (`ChallengePage` object) and converted to Markdown: headings, bold, italics, lists and links were kept, and no words were changed. `detailsContent` is 9,658 chars of HTML. |
| Main text changed since first fetch? | No. A word-by-word diff of the 2026-11-14 `detailsContent` against the text below found no changes. |
| `firstPublishedAt` | 2026-09-17T14:21:29.086000Z |
| `lastPublishedAt` | 2026-11-13T03:52:04.820266Z (was 2026-10-29T19:56:20.753650Z). This is when the Resources tab went live. |
| Categories | Advanced · Intermediate · Beginner/Youth |
| Skills | Earth Science · Planets & Moons · Software · Space Exploration |
| Resources tab (`resourcesTabContent`) | Live. 5,240 chars of HTML, sha256 `80ed3e90333dd11f1e0cff79d5498f71575cd734a41520f08b5467b1f0f11038`. Copied [below](#resources-tab). |
| Teams tab | empty |
| TLS note | The site's certificate chains to the old Comodo "AAA Certificate Services" root, which many trust stores no longer include, so `curl` and some crawlers fail. We did **not** turn off certificate checks. The issuer cert from the site's own AIA link (`http://cert.ssl.com/SSL.com-TLS-I-RSA-R1.cer`) is signed by the trusted "SSL.com TLS RSA Root CA 2022" (`openssl verify` → OK). We added that cert to the CA bundle for the fetch. |

---

## Summary

Selecting future landing sites and lunar base locations depends on many factors, including topography, geology, environment, and available resources, to name a few. Places on Earth that have analogous characteristics to the Moon or Mars – the Atacama Desert, Haughton Crater, Death Valley – allow mission teams to test equipment and methods before they fly; however, such terrestrial analog sites are not entirely well characterized. Your challenge is to use open Earth, Moon, and Mars data from NASA and other space agencies to identify and characterize new terrestrial analogs for future bases or landing sites, drawing on deserts, polar regions, volcanic and arid terrains, caves, and other environments that share conditions with the lunar or Martian surface, then present your findings as a map, visualization, or other tool.

## Background

Earth is our most accessible laboratory for preparing to explore the Moon and Mars. Scientists and engineers already use terrestrial “analog” environments — deserts, polar regions, volcanic landscapes, impact craters, and caves — to study planetary processes and test instruments, technologies, and exploration concepts. However, no location on Earth perfectly reproduces another planetary environment, and different locations may provide useful analogs for different characteristics.

As humanity prepares for sustained exploration of the Moon and future human exploration of Mars, we could use open Earth, Moon, and Mars data to search globally and systematically for terrestrial environments that may provide useful — and perhaps previously unrecognized — analogs. Participants might consider dimensions such as geology and surface materials, terrain type and topography, atmospheric and aeolian processes such as dust storms, temperature and other environmental extremes, water or ice, biological and habitability characteristics, subsurface environments, and conditions relevant to robotic or human operations.

The goal is not simply to rediscover well-known analog sites, or to find one place that simply looks like the Moon or Mars. Participants are encouraged to combine datasets creatively to identify and characterize locations anywhere on Earth, explain what makes them analogous and what does not, and show how these environments could help conduct lunar or Mars science and exploration. Solutions might range from identifying a compelling individual site, environment, or geophysical process to developing maps, similarity metrics, machine learning approaches, or other innovative methods for discovering and comparing planetary analogs. You might consider Earth, Moon, Mars data obtained from various NASA and other space agencies missions, as well as data and images obtained locally.

## Objectives

Your challenge is to search our own planet Earth for places, environments and processes that could serve as analogs and can help us explore the Moon and Mars. Using open NASA Earth data together with available Moon and Mars data from other space agencies and open sources, identify and characterize one or more locations on Earth that could serve as useful analogs for candidate permanent Moon-base locations or future Mars landing and exploration sites. Explore what makes your Earth location analogous to the Moon or Mars. You might compare data and images of geology and surface materials, terrain and topography, temperature and environmental extremes, water or ice, dust and atmospheric processes, biology and habitability, caves or subsurface environments, or conditions relevant to robotic and human exploration. Your analog does not need to match the Moon or Mars in every way. Explain which characteristics or processes provide a strong analogy, where the analogy breaks down, and how studying or using your Earth analog could help prepare for the exploration of the Moon or Mars.

Be creative in how you search for, analyze, and communicate your analog. You could develop a written report, an interactive map, visualization, app, story, similarity-ranking system, ML tool, or another innovative approach. You might investigate a single compelling location, compare several locations around the world, or develop a method for systematically searching Earth for previously unrecognized analogs. Use open data from NASA and other space agencies as your window into Earth, the Moon, and Mars—and show us what our home planet can teach us about exploring the next ones. You might consider documenting your findings in a written format to share with other enthusiasts interested in the topic and to educate the public.

## Potential Considerations

*You may (but are not required to) consider the following:*

- **Think beyond visual similarity.** Two places may look alike but differ substantially in geology, environment, or physical processes. Use data to explain why your proposed Earth location is a meaningful analog.
- **Consider different dimensions of analogy**, including:
  - Geology, mineralogy, and surface materials
  - Terrain, elevation, slope, roughness, craters, and other topographic features
  - Temperature, illumination, and environmental extremes
  - Water, ice, permafrost, and other potential resources
  - Dust, wind, erosion, and other atmospheric or surface processes
  - Biology, extremophiles, habitability, and biosignatures
  - Caves, lava tubes, underground environments, and other subsurface features
  - Conditions relevant to landing, mobility, navigation, robotic operations, human exploration, or construction
- **An analog does not have to match everything.** An Earth location might be an excellent geological analog but a poor temperature analog, for example. Identify what is similar, how similar it is, and what is different.
- **Think about processes as well as places.** Earth processes such as sedimentation, dust storms, volcanic activity, erosion, ice dynamics, or water-driven alteration may provide insights into processes occurring today — or that occurred in the past — on the Moon or Mars.
- **Look beyond well-known analog sites.** Locations such as Antarctica, the Atacama Desert, Iceland, Hawaii are already widely studied. For example, NASA's global Earth-observation datasets may allow you to discover compelling analogs in places that have received much less attention.
- **Explore the whole Earth, including below its surface.** Polar regions, deserts, mountains, volcanoes, impact craters, salt flats, glaciers, caves, lava tubes, mines, and other environments could all offer interesting possibilities.
- **Use multiple datasets when useful.** Combining observations of terrain, temperature, geology, vegetation, water, ice, aerosols, or other characteristics may reveal relationships that are difficult to recognize using a single dataset.
- **Consider scale.** A continent or desert does not need to be treated as a single analog. A particular crater, valley, volcanic field, cave system, or even a small area within a much larger region could provide a much stronger match.
- **Connect your analog to exploration.** Explain how the location or process you identify could help scientists and engineers understand Moon, Mars, or both; test instruments or technologies, prepare robotic or human operations; search for resources or signs of habitability; or reduce exploration risks.
- **Be creative with your approach.** Maps and visualizations are welcome, but solutions could also use geographic information systems (GIS), statistical analysis, similarity metrics, machine learning, interactive applications, games, or other innovative methods.
- **Remember Earth's limits as an analog.** Earth cannot reproduce important lunar and Martian conditions such as reduced gravity, the lunar vacuum, the thin Martian atmosphere, or their radiation environments. Recognizing these differences is part of good scientific analysis.
- **Surprise us.** A strong solution may identify an unexpected Earth location, reveal an unexpected connection between Earth and Moon or Mars, or introduce a new way of using Earth data to help enable future exploration.

*For data and resources related to this challenge, refer to the Resources tab at the top of the page. More resources may be added before the hackathon begins.*

## Resources tab

Verbatim from `resourcesTabContent`, fetched 2026-11-14T14:15:30Z. Link URLs are
copied exactly, including the organizers' `utm_source` tags.

*NASA does not endorse any non-U.S. Government entity and is not responsible for information contained on non-U.S. Government websites. For non-U.S. Government websites, participants must comply with any data use parameters of that specific website.*

### **NASA Data & Resources**

**Earth**

- [**NASA Earthdata Search**](https://search.earthdata.nasa.gov/?utm_source=%27chatgpt.com%27)**:** NASA's primary portal for discovering and accessing Earth science observations.
- [**NASA Worldview**](https://worldview.earthdata.nasa.gov/index.html?utm_source=%27chatgpt.com%27)**:** An easy-to-use interactive environment for visually exploring NASA satellite imagery and environmental observations.

**Moon and Mars**

- [**NASA Planetary Data System (PDS)**](https://pds.nasa.gov/?utm_source=%27chatgpt.com%27)**:** NASA's long-term archive for planetary science data from NASA orbital, lander, and rover missions. It provides access to lunar and Martian mission observations spanning imagery, geoscience, atmospheres, plasma environments, cartography, and other measurements.
- [**NASA Lunar Reconnaissance Orbiter (LRO)**](https://pds-geosciences.wustl.edu/missions/lro/?utm_source=%27chatgpt.com%27)**:** LRO provides extensive observations of the lunar surface through instruments including LROC, LOLA, Diviner, LEND, Mini-RF and others.
- [**NASA LRO Diviner Lunar Data**](https://pds-geosciences.wustl.edu/missions/lro/diviner.htm?utm_source=%27chatgpt.com%27)**:** Diviner maps lunar surface temperatures and provides especially useful products for studying the lunar poles. Its polar and resource products could be compared with extreme cold, ice-bearing, or other terrestrial environments.

### **Space Agency Partner Resources**

**CSA (Canadian Space Agency)**

- [**RADARSAT Constellation Mission (RCM) - Data**](https://donnees-data.asc-csa.gc.ca/en/dataset/rcm)**:** RCM is Canada's new generation of Earth observation satellites. The RCM includes a trio of Earth observation satellites, capable of scanning Earth day or night and in any weather conditions. The RCM is designed to provide effective solutions in three main areas: Maritime surveillance (ice, surface wind, oil pollution and ship monitoring); Disaster management (mitigation, warning, response and recovery); and Ecosystem monitoring (agriculture, wetlands, forestry and coastal change monitoring).
- [**RADARSAT 1 - Data**](https://donnees-data.asc-csa.gc.ca/en/dataset/radarsat1)**:** Launched in November 1995, RADARSAT-1 provided Canada and the world with an operational radar satellite system capable of timely delivery of large amounts of data. Equipped with a powerful synthetic aperture radar (SAR) instrument, it acquired images of the Earth day or night, in all weather and through cloud cover, smoke and haze. All data products in the Canadian RADARSAT-1 archive have been released under an open license.
- [**Synthetic Aperture Radar (SAR) Python Tutorial**](https://github.com/asc-csa/Synthetic_Aperture_Radar_Tutorial)**:** This tutorial demonstrates how to work with SAR imagery using Python and QGIS. It includes easy and practical steps for accessing and visualizing data.

**ESA (European Space Agency)**

- [**Copernicus Data Space Ecosystem**](https://dataspace.copernicus.eu/?utm_source=%27chatgpt.com%27)**:** Provides free and open access to Sentinel Earth-observation data covering land, oceans, and atmosphere, with tools for visualization and processing.
- [**ESA Open Science Catalog**](https://opensciencedata.esa.int/?utm_source=%27chatgpt.com%27)**:** A catalog of publicly available geoscience datasets, products, experiments, and workflows.

**JAXA (Japan Aerospace Exploration Agency)**

- [**JAXA G-Portal**](https://gportal.jaxa.jp/gpr/index/index?utm_source=%27chatgpt.com%27)**:** Provides Earth-observation products from JAXA missions, searchable by variables such as precipitation, snow, vegetation, etc.

### What this means for us (our notes, not page text)

- The Global Awards rule needs at least one NASA dataset from this tab. **LRO Diviner and LOLA** (both listed under LRO) cover our Moon thermal and terrain dimensions, so we already meet that rule if the engine uses them.
- Our Earth sources (MODIS, NASADEM, MERRA-2) come through **Earthdata Search**, which is listed. Each one still needs to be a single named product with a registry row.
- Nothing here forces a scope change, so no new ADR is needed.
- New option: **RADARSAT-1** (open licence) for radar roughness on Earth. It could pair with LRO Mini-RF on the Moon. Not planned yet; flagged for the W6 owner.
