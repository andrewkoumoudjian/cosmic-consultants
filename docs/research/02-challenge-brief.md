# 02 — Challenge brief inventory: facts, requirements, propositions

Challenge: **Identify Earth Locations that Analog the Permanent Moon Base Locations and Mars**
URL: https://www.spaceappschallenge.org/2026/challenges/permanent-moon-base-locations-and-mars/
Extracted 2026-11-12 from the page's embedded GraphQL payload (the page is JS-rendered;
quotes below are verbatim from that payload). Research only.

Legend: **[F]** stated fact on the page · **[R]** requirement on a submission ·
**[P]** proposition — a testable claim our project would assert, derived from the brief.
Derived items say so; nothing below silently upgrades an inference into a NASA statement.

## 1. Page metadata [F]

| Field | Value |
|---|---|
| Title | Identify Earth Locations that Analog the Permanent Moon Base Locations and Mars |
| Slug | `permanent-moon-base-locations-and-mars` |
| First published | 2026-09-17T14:21:29Z |
| Last published | 2026-10-29T19:56:20Z (brief may still change; re-diff before building) |
| Live | `true` |
| Categories | Advanced, Intermediate, Beginner/Youth (all three — the challenge is open at every level) |
| Skills | Earth Science · Planets & Moons · Software · Space Exploration |
| Resources tab | "*Resources will be available on Friday, November 13.*" — i.e. **2026-11-13, the day after this inventory**. Re-read then; dataset list and judging guide are expected with it. |
| Judging field on page | `null` — no challenge-specific rubric is published on this page as of 2026-11-12. |

## 2. The brief, verbatim (condensed without rewording)

**Excerpt.** "Selecting future landing sites and lunar base locations depends on many
factors, including topography, geology, environment, and available resources, to name
a few. Places on Earth that have analogous characteristics to the Moon or Mars – the
Atacama Desert, Haughton Crater, Death Valley – allow mission teams to test equipment
and methods before they fly; however, such terrestrial analog sites are not entirely
well characterized. Your challenge is to use open Earth, Moon, and Mars data from NASA
and other space agencies to identify and characterize new terrestrial analogs for
future bases or landing sites, drawing on deserts, polar regions, volcanic and arid
terrains, caves, and other environments that share conditions with the lunar or
Martian surface, then present your findings as a map, visualization, or other tool."

**Background.** "Earth is our most accessible laboratory for preparing to explore the
Moon and Mars… no location on Earth perfectly reproduces another planetary
environment, and different locations may provide useful analogs for different
characteristics." Dimensions named: "geology and surface materials, terrain type and
topography, atmospheric and aeolian processes such as dust storms, temperature and
other environmental extremes, water or ice, biological and habitability
characteristics, subsurface environments, and conditions relevant to robotic or human
operations." Anti-goals stated: "The goal is **not simply to rediscover well-known
analog sites, or to find one place that simply looks like the Moon or Mars.**"
Encouraged: "combine datasets creatively… explain what makes them analogous and what
does not… identifying a compelling individual site… to developing maps, similarity
metrics, machine learning approaches, or other innovative methods."

**Objectives.** "identify and characterize one or more locations on Earth that could
serve as useful analogs for candidate permanent Moon-base locations or future Mars
landing and exploration sites… Explore what makes your Earth location analogous…
**Your analog does not need to match the Moon or Mars in every way. Explain which
characteristics or processes provide a strong analogy, where the analogy breaks down,
and how studying or using your Earth analog could help prepare for the exploration of
the Moon or Mars.**" Form is open: "written report, an interactive map, visualization,
app, story, similarity-ranking system, ML tool, or another innovative approach… a
single compelling location, compare several locations… or a method for systematically
searching Earth for previously unrecognized analogs."

**Potential Considerations** (explicitly optional: "You may (but are not required to)"):

1. Think beyond visual similarity; use data to justify analogy.
2. Dimensions: geology/mineralogy/surface materials; terrain/elevation/slope/
   roughness/craters; temperature/illumination/environmental extremes; water/ice/
   permafrost/resources; dust/wind/erosion; biology/extremophiles/habitability/
   biosignatures; caves/lava tubes/subsurface; landing/mobility/navigation/robotic/
   human-operations/construction conditions.
3. Partial analogy is expected: name what matches, how strongly, and what does not.
4. Processes as well as places (sedimentation, dust storms, volcanism, erosion, ice
   dynamics, water-driven alteration — present or past on Moon/Mars).
5. Look beyond well-known sites: "Antarctica, the Atacama Desert, Iceland, Hawaii are
   already widely studied."
6. Whole Earth including subsurface: polar, deserts, mountains, volcanoes, impact
   craters, salt flats, glaciers, caves, lava tubes, mines.
7. Combine multiple datasets (terrain, temperature, geology, vegetation, water, ice,
   aerosols…) to reveal relationships a single dataset hides.
8. Scale: a specific crater/valley/volcanic field/cave/small area can beat a whole desert.
9. Connect to exploration: science return, instrument/tech testing, ops preparation,
   resource/habitability search, risk reduction.
10. Methods welcome: GIS, statistics, similarity metrics, ML, interactive apps, games.
11. Hard limits of any Earth analog: "Earth cannot reproduce… reduced gravity, the
    lunar vacuum, the thin Martian atmosphere, or their radiation environments.
    Recognizing these differences is part of good scientific analysis."
12. "Surprise us": unexpected location, unexpected connection, or new method.

## 3. Requirements on a submission

### 3.1 Stated in the brief [R]

| # | Requirement | Source phrase |
|---|---|---|
| R1 | Identify **≥1 Earth location** as analog for candidate permanent Moon-base sites and/or future Mars landing/exploration sites. | Objectives |
| R2 | **Characterize** it with open data — not just name or photograph it. | "identify and characterize", "such terrestrial analog sites are not entirely well characterized" |
| R3 | Use **open Earth, Moon and Mars data from NASA and other space agencies** (other open sources and locally obtained data also allowed). | Excerpt, Background |
| R4 | State **where the analogy breaks down**, per characteristic. | Objectives (bold above) |
| R5 | State **how the analog helps** Moon/Mars exploration (science, testing, ops, resources, risk). | Objectives, Consideration 9 |
| R6 | Present as **map, visualization, or other tool** (report/app/story/ranking/ML all acceptable). | Excerpt, Objectives |
| R7 | Non-requirements, stated: no need to match on every dimension; Potential Considerations are optional; single-site, multi-site and systematic-search scopes are all legitimate. | Objectives, Considerations preamble |

### 3.2 Platform-level requirements (outside this page; verify on 2026-11-13)

| # | Requirement | Evidence status |
|---|---|---|
| R8 | A project must **use NASA data** to be eligible for Global Awards. | Secondary sources (local-event judging pages). Consistent with R3, but confirm in the official 2026 Judging & Awards guide expected 2026-11-13. |
| R9 | Judging rubric: 2025 criteria (Impact, Creativity, Validity, Relevance, Presentation family) are being **carried provisionally** by third-party guides; the official 2026 rubric and weights are **not published yet**. Any percentages found online today are inferred, not official. | Third-party recon pages explicitly mark weights "Stated for 2025; carried to 2026". Treat as planning prior only. |
| R10 | Global path: local/universal judging → NASA + space-agency-partner SME judging → executive committee; 10 Global Winner categories historically include Best Use of Science, Best Use of Data, Best Use of Technology, Best Mission Concept, Galactic Impact. | Secondary sources; category list to confirm for 2026. |

**Action item A0 (2026-11-13):** re-fetch this challenge page's Resources tab and the
Judging & Awards + Project Submission guides; diff against this file; update R8–R10.

## 4. Facts the brief asserts (inputs we may rely on) [F]

- F1. Landing/base site selection is multi-factor: topography, geology, environment, resources.
- F2. Named exemplar analogs: **Atacama Desert, Haughton Crater, Death Valley**.
- F3. Named saturated/widely-studied regions to look beyond: **Antarctica, Atacama, Iceland, Hawaii**.
- F4. Existing analog sites are "not entirely well characterized" — characterization itself is valued work.
- F5. No Earth location reproduces reduced gravity, lunar vacuum, thin Martian atmosphere, or Moon/Mars radiation. These four are permanent mismatch dimensions.
- F6. Analog value is **per-characteristic**, not global: a site can be an excellent geology analog and a poor temperature analog simultaneously.
- F7. Data scope is three bodies (Earth, Moon, Mars) and multi-agency; local/field data may supplement.

## 5. Propositions a strong submission must assert and defend [P]

These are the claims *our* project will be judged on. Each maps to brief text and to
the evidence type that could falsify it — this is the checklist the build must satisfy.

| # | Proposition | Brief basis | Falsified by |
|---|---|---|---|
| P1 | Site S matches target T (Moon base site or Mars landing site) on dimension d within a stated tolerance, measured from open data. | R1–R3, F6 | Independent dataset placing S outside tolerance on d |
| P2 | The match is **not** merely visual: at least one non-imagery dataset (DEM, spectra, climate, event record) supports each claimed dimension. | Consideration 1 | Audit showing claims rest on imagery alone |
| P3 | For every claimed dimension there is an explicit mismatch statement, including the four permanent ones (gravity, vacuum/atmosphere, radiation + dimension-specific). | R4, F5 | A dimension claimed with no breakdown analysis |
| P4 | S is **not a rediscovery**: S (or its specific sub-area at the claimed scale) is absent from, or materially under-characterized in, the published analog literature. | Anti-goal, F3–F4 | Prior paper/site catalog characterizing S for the same dimension |
| P5 | The search that found S is **systematic over a stated domain** (not cherry-picked): the domain, screening criteria and rejection reasons are reproducible. | "search globally and systematically", Consideration 8 | Non-reproducible selection narrative |
| P6 | Rankings/scores, if any, are **auditable**: weights, tolerances and dataset versions are published, and score sensitivity to weight choice is reported. | Consideration 10 + R2 (derived) | Black-box score with no parameters |
| P7 | Using S would concretely de-risk a named mission activity (instrument test, traverse, ISRU trial, EVA ops, landing rehearsal). | R5 | No named activity, or activity impossible at S (access, protection status, safety) |
| P8 | Every number on the map/report traces to a cited dataset snapshot with fetch date and version. | R2–R3 (derived, needed for credibility under SME judging) | Untraceable figure |

## 6. What the brief leaves open (our design freedom — and risk)

- **Target choice:** Moon permanent base (in practice: south-polar region), Mars
  landing/exploration sites, or both. "Both" doubles target-characterization work.
- **Scale choice:** one hero site vs ranked atlas vs search method. The brief blesses
  all three; judges weighing Impact/Creativity will punish a hero site that is F3-saturated.
- **Deliverable:** interactive map is the excerpt's first-named form; a defensible
  written characterization can ride along as per-site dossiers (brief also invites
  public-facing written documentation).
- **No prescribed datasets, metrics or thresholds** until the Resources tab lands (A0).
