# 03 — Research-paper inventory: terrestrial analogs for Moon/Mars bases

Date: 2026-11-12. Research only.

## 0. Honest scope statement on "ALL papers"

A literal inventory of *all* papers on this subject does not exist and cannot be
produced in one pass: OpenAlex full-text counts on 2026-11-12 were **3,491** works for
"terrestrial analog sites Mars Moon planetary analog", **1,692** for "Mars landing site
selection criteria human exploration", **1,341** for "lunar regolith simulant ISRU
resource", **199** for the narrow lunar-south-pole query — with heavy off-topic noise
at the top of citation-sorted lists. What follows is therefore:

1. the **reproducible method** (queries + counts) so the corpus can be regenerated and extended mechanically;
2. a **curated core bibliography** — every entry below was returned by those queries or
   is a canonical program/reference verifiable at the given DOI/URL — annotated with
   what it gives us and what it forecloses for originality;
3. the **originality gap analysis** the proposal in
   [`04-monorepo-multiagent-lean-proposal.md`](../proposals/04-monorepo-multiagent-lean-proposal.md) is built on.

Full-corpus harvesting (OpenAlex/Crossref/Semantic Scholar → deduped BibTeX in
`research/corpus/`) is proposed as a build-phase work order, not hand-done here.

## 1. Analog theory and site catalogs (the frame everyone cites)

| Work | Gives us | Forecloses / must beat |
|---|---|---|
| Preston & Dartnell 2014, "Planetary habitability: lessons learned from terrestrial analogues", *Int. J. Astrobiology*, [doi:10.1017/S1473550413000396](https://doi.org/10.1017/S1473550413000396) (c≈168) | Standard taxonomy of analogue types and their limits; vocabulary for per-dimension analogy. | Narrative reviews of known sites are done. A new list of famous sites adds nothing. |
| Foucher et al. 2021, "Definition and use of functional analogues in planetary exploration", *Planet. Space Sci.*, [doi:10.1016/j.pss.2021.105162](https://doi.org/10.1016/j.pss.2021.105162) | "Functional analogue" formalism: analogy is relative to a *purpose/instrument*, not absolute. Directly motivates purpose-indexed scoring. | Any single scalar "Mars-likeness score" contradicts the field's own definition. |
| Martins et al. 2017, "Earth as a Tool for Astrobiology — A European Perspective", *Space Sci. Rev.*, [doi:10.1007/s11214-017-0369-1](https://doi.org/10.1007/s11214-017-0369-1) | European analog-site inventory (Rio Tinto, Svalbard, etc.) and EuroMoonMars practice. | European sites are well catalogued; novelty likely lies outside Europe or at sub-site scale. |
| Merino et al. 2019, "Living at the Extremes: Extremophiles and the Limits of Life in a Planetary Context", *Front. Microbiol.*, [doi:10.3389/fmicb.2019.00780](https://doi.org/10.3389/fmicb.2019.00780) (c≈713) | Habitability-axis ground truth: which extremes co-occur on Earth vs Moon/Mars. | — |
| Hays et al. 2017, "Biosignature Preservation and Detection in Mars Analog Environments", *Astrobiology*, [doi:10.1089/ast.2016.1627](https://doi.org/10.1089/ast.2016.1627) | What analog sites must preserve to be useful for life-detection testing. | — |
| Cabrol 2018/2017, ecosystem perspective on biosignature exploration, *Astrobiology*, [doi:10.1089/ast.2017.1756](https://doi.org/10.1089/ast.2017.1756); Harris et al. 2022, remote/in-situ analog characterization across scales, [doi:10.3389/fspas.2022.849078](https://doi.org/10.3389/fspas.2022.849078) | Multi-scale coupling: orbital → field → lab. Our atlas must state its scale per claim. | Single-scale (orbital-only) characterization is known-weak. |
| Ten Kate & Preston 2022, "Earth Analogues" (book chapter), [doi:10.1201/9781003338277-20](https://doi.org/10.1201/9781003338277-20); Wikipedia "Terrestrial analogue site" catalog table (coordinates per site) | Machine-readable starting list of *already-known* sites = our exclusion/validation set for proposition P4 (not-a-rediscovery). | Any "discovery" already in this table fails P4. |

## 2. Classic sites and analog programs (the saturated set)

| Site / program | Anchor reference | Status for us |
|---|---|---|
| Haughton Impact Crater, Devon Island, CA — Haughton-Mars Project (since 1997) | NASA analogs fact sheet; HMP literature; terrestrial-analogue catalog | Brief-named exemplar. Validation site only — a correct method must rank it highly for Mars-crater dimensions. |
| Atacama Desert, CL (+ Ojos del Salado) | Kereszturi et al. 2020, *Astrobiology*, [doi:10.1089/ast.2019.2165](https://doi.org/10.1089/ast.2019.2165) | Brief-named, saturated. Validation for aridity/UV/temperature-swing dimensions. |
| Death Valley, US | Brief-named | Validation for aeolian/salt-flat processes. |
| Rio Tinto, ES; Svalbard, NO; Iceland volcanic terrains; Lanzarote/Chinijo Geopark | Martínez-Frías et al. 2017, *Episodes*, [doi:10.18814/epiiugs/2017/v40i4/017035](https://doi.org/10.18814/epiiugs/2017/v40i4/017035); Hadland et al. 2024, *Commun. Earth Environ.*, [doi:10.1038/s43247-024-01280-3](https://doi.org/10.1038/s43247-024-01280-3) | Saturated European set. |
| Basaltic terrains, Idaho & Hawaiʻi | Hughes et al. 2019, *Astrobiology*, [doi:10.1089/ast.2018.1847](https://doi.org/10.1089/ast.2018.1847); NASA BASALT program | Saturated US volcanic set; Hawaiʻi brief-named as saturated. |
| Mistastin Lake impact structure, Labrador, CA | Mader 2015, Western U thesis "The Mistastin Lake Impact Structure As A Terrestrial Analogue Site For Lunar Science And Exploration" | **Canadian lunar analog, less globally famous.** Candidate for deep characterization at sub-site scale rather than "discovery". |
| Human analog missions: HMP, MDRS (Utah), FMARS (Devon Is.), HI-SEAS (Mauna Loa), Desert RATS (Arizona), NEEMO, ESA CAVES/PANGAEA | "Human analog mission" survey literature; NASA `nasa_facts_analogs_2011.pdf` | Ops/human-factors analogy exists and is program-driven; our edge must be environmental-data-driven, not habitat-simulation. |
| Legged-robot analog field tests (ETH RSL) | Arm et al. 2023, "Scientific exploration of challenging planetary analog environments with a team of legged robots", *Science Robotics*, [doi:10.1126/scirobotics.ade9548](https://doi.org/10.1126/scirobotics.ade9548) (c≈139) | Shows where robotics analog testing is heading: terrain-traversability characterization is a valued, current dimension. |

## 3. Lunar south pole / permanent base site selection (the target side)

| Work | Gives us |
|---|---|
| Gawronska et al. 2020, "Geologic context and potential EVA targets at the lunar south pole", *Adv. Space Res.*, [doi:10.1016/j.asr.2020.05.035](https://doi.org/10.1016/j.asr.2020.05.035) | What a base site must be near: geology + EVA traverse targets. |
| Lemelin et al. 2021, "Framework for Coordinated Efforts in the Exploration of Volatiles in the South Polar Region", *Planet. Sci. J.*, [doi:10.3847/PSJ/abf3c5](https://doi.org/10.3847/PSJ/abf3c5) | Volatile/PSR framework — the resource axis for permanent bases. |
| Bickel et al. 2021, "Peering into lunar permanently shadowed regions with deep learning", *Nat. Commun.*, [doi:10.1038/s41467-021-25882-z](https://doi.org/10.1038/s41467-021-25882-z) | ML over LROC for PSRs; precedent that ML-on-open-data is publishable, not novel per se. |
| **Peña-Asensio, Neira-Acosta & Sánchez-Lozano 2024, "Evaluating potential landing sites for the Artemis III mission using a multi-criteria decision making approach", *Acta Astronautica*, [doi:10.1016/j.actaastro.2024.10.049](https://doi.org/10.1016/j.actaastro.2024.10.049)** | **Closest prior art to "just do MCDA scoring"**: AHP-style multi-criteria ranking of Artemis III candidate regions. Any scalar-weighted-score submission is a re-run of this paper aimed at Earth. Our differentiator must be structural (section 7). |
| Liu et al. 2023, "A New Blind Selection Approach for Lunar Landing Zones Based on Engineering Constraints Using Sliding Window", *Remote Sens.*, [doi:10.3390/rs15123184](https://doi.org/10.3390/rs15123184) | Constraint-first (slope, roughness) blind search over DEMs — the screening idiom, uncertified. |
| Crawford 2015, "Lunar resources: A review", *Prog. Phys. Geogr.*, [doi:10.1177/0309133314567585](https://doi.org/10.1177/0309133314567585) (c≈430); Elvis et al. 2021 on concentrated lunar resources & governance, [doi:10.1098/rsta.2019.0563](https://doi.org/10.1098/rsta.2019.0563) | Resource geography + the scarcity/conflict framing that makes *which* site matter. |
| Kaczmarzyk & Musiał 2021, lunar base power systems parametric study, *Energies*, [doi:10.3390/en14041141](https://doi.org/10.3390/en14041141); Evans & Graham 2020 FLARE architecture, [doi:10.1016/j.actaastro.2020.07.032](https://doi.org/10.1016/j.actaastro.2020.07.032) | Illumination/power as first-class site dimensions (Earth analog: polar night / insolation regimes). |
| Wang et al. 2024, Chang'E-7 objectives, *Natl. Sci. Rev.*, [doi:10.1093/nsr/nwad329](https://doi.org/10.1093/nsr/nwad329); Jia et al. 2023, lunar water-ice exploration, [doi:10.34133/space.0026](https://doi.org/10.34133/space.0026) | Non-NASA south-pole program: multi-agency targets the brief invites. |

## 4. Mars landing-site selection and surface operations (the other target)

| Work | Gives us |
|---|---|
| Drake, Hoffman & Beaty 2010, "Human exploration of Mars, Design Reference Architecture 5.0", *IEEE AERO*, [doi:10.1109/AERO.2010.5446736](https://doi.org/10.1109/AERO.2010.5446736) (c≈604); Hoffman & Kaplan 1997 Reference Mission | Human-Mars site requirements baseline (latitude, elevation, water, science diversity). |
| Kirk et al. 2008, HiRISE stereo meter-scale slopes of Phoenix candidate sites, *JGR*, [doi:10.1029/2007JE003000](https://doi.org/10.1029/2007JE003000) | Terrain-safety quantification standard (slope distributions at meter scale). |
| Stoker et al. 2010, "Habitability of the Phoenix landing site", *JGR*, [doi:10.1029/2009JE003421](https://doi.org/10.1029/2009JE003421) | Worked example of per-site habitability characterization joining landed + analog data. |
| Gómez-Elvira et al. 2012, REMS environmental suite, *Space Sci. Rev.*, [doi:10.1007/s11214-012-9921-1](https://doi.org/10.1007/s11214-012-9921-1); InSight weather archive (see catalog doc) | In-situ Mars climate envelopes an Earth analog's climate must be compared to, dimension by dimension. |
| Viviano et al. 2014, CRISM spectral parameters, *JGR Planets*, [doi:10.1002/2014JE004627](https://doi.org/10.1002/2014JE004627) | Mineralogy comparison method (spectral parameters), reusable on Earth hyperspectral data. |

## 5. Caves and lava tubes (subsurface dimension)

| Work | Gives us |
|---|---|
| Sauro et al. 2020, "Lava tubes on Earth, Moon and Mars: A review on their size and morphology revealed by comparative planetology", *Earth-Sci. Rev.*, [doi:10.1016/j.earscirev.2020.103288](https://doi.org/10.1016/j.earscirev.2020.103288) (c≈215) | The comparative dataset: tube dimensions scale with gravity — Earth tubes are systematically smaller; mismatch is quantifiable, not hand-wavy. |
| Cushing 2012, "Candidate cave entrances on Mars", *J. Cave Karst Stud.*, [doi:10.4311/2010EX0167R](https://doi.org/10.4311/2010EX0167R); Cushing et al. 2015 on atypical pit craters, [doi:10.1002/2014JE004735](https://doi.org/10.1002/2014JE004735) | Mars target catalog for cave analogy. |
| Wynne et al. 2022, "Fundamental Science and Engineering Questions in Planetary Cave Exploration", *JGR Planets*, [doi:10.1029/2022JE007194](https://doi.org/10.1029/2022JE007194) | Open questions list = ready-made "exploration relevance" claims (P7). |
| Muñoz et al. 2026, Ape Cave lava-tube morphometry statistical framework, *JGR Planets*, [doi:10.1029/2026JE010115](https://doi.org/10.1029/2026JE010115) | Current-year precedent: rigorous statistical morphometry of one Earth tube as planetary analog. A single-site submission must match this bar. |

## 6. Regolith, ISRU and construction (resource/ops dimensions)

Taylor, Pieters & Britt 2016, simulant evaluations, [doi:10.1016/j.pss.2016.04.005](https://doi.org/10.1016/j.pss.2016.04.005);
Long-Fox & Britt 2023, simulant characterization, [doi:10.3389/frspt.2023.1255535](https://doi.org/10.3389/frspt.2023.1255535);
Meurisse et al. 2018, solar 3D printing of regolith, [doi:10.1016/j.actaastro.2018.06.063](https://doi.org/10.1016/j.actaastro.2018.06.063);
Lomax et al. 2020, electrochemical O₂/metal from regolith, [doi:10.1016/j.pss.2019.104748](https://doi.org/10.1016/j.pss.2019.104748);
Kokaly et al. 2017, USGS Spectral Library v7, [doi:10.3133/ds1035](https://doi.org/10.3133/ds1035) — the Earth-side spectral reference for mineral matching.

Relevance: an analog site whose surface material feeds simulant/ISRU process testing
scores on a dimension most hackathon entries ignore — "available resources" is named
in the excerpt's first sentence.

## 7. Originality gap analysis (what nobody above does)

1. **Direction of search.** Literature starts from known Earth sites and argues
   Moon/Mars relevance. Almost nobody inverts it: fix the *target* (e.g. an Artemis
   south-polar candidate region, a named Mars human-landing reference zone) as a
   multi-dimensional envelope, then search **all of Earth** for matches. The brief
   explicitly invites this ("search globally and systematically… previously
   unrecognized analogs") — it is the intended-but-hard path.
2. **Scalar scores are taken.** Weighted-sum MCDA for site selection is published
   (Peña-Asensio et al. 2024). Foucher et al. 2021 already explain why a single score
   is conceptually wrong (analogy is purpose-relative). Submitting another weighted
   sum is neither original nor defensible.
3. **No screening certificates.** Blind DEM searches exist (Liu et al. 2023) but
   without proof that discarded terrain could not have won under the stated criteria.
   A *certified* elimination — "these 98% of cells provably cannot enter the frontier
   under any weights in the declared family" — does not exist in this literature.
4. **Partial analogy is preached, not formalized.** Papers list matching/mismatching
   traits in prose. A machine-checkable per-dimension analogy *vector* with explicit
   breakdown dimensions (including the brief's four permanent mismatches) is open.
5. **Living data vs static papers.** Site characterizations are frozen PDFs; EONET/
   GIBS-class event and time-series data (dust-storm climatology, thermal cycles) are
   not folded into analog dossiers. Process-analog quantification is thin.

These five gaps, not "a nicer map", are where an efficient and unique entry lives.
The proposal doc maps each gap to a component and to the author's prior work.
