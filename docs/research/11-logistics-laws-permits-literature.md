# 11 — Laws and permits on the Logistics page: can we model them instead of collecting them?

Date: 2026-11-15. Research only — no code, no contracts, no UI, no snapshots.
Work order: [#188](https://github.com/andrewkoumoudjian/cosmic-consultants/issues/188).
Branch: `research/188-logistics-permits-review`. Base: `main` @ `1ffa5a0`.
Reads with: [ADR-0005](../decisions/ADR-0005-mission-planning-workflow.md) (the
mission planner), [ADR-0006](../decisions/ADR-0006-eonet-for-risks.md) (how we
handled a licence-limited source), [doc 08](08-landing-site-feature-set.md),
[doc 09](09-measurement-lineage-and-corroboration.md),
[doc 03](03-literature-inventory.md) (house style for literature).

## 0. The short answer

**Most of it can be derived. Three things cannot, and they are small.**

1. The permit and protected-land facts on the Logistics page today come from
   **one** number, `protected_pct`, and that number is **empty for every cell**
   because the WDPA licence stops us publishing it. So the honest problem is not
   "collect permits by hand" — it is "get a lawful, publishable number and a
   real source for the rules that apply".
2. The **rules themselves** are published documents (park management plans,
   Antarctic Treaty measures, national statutes, planetary-protection
   directives). There is mature tooling to read them: legal-text benchmarks
   (CUAD, LegalBench, LexGLUE) and legal retrieval models. We can derive
   "which regime, which obligations, which instrument" without typing rules in
   by hand. We cannot derive "you are allowed to drill here" — that is legal
   advice, and we should not publish it.
3. The **environment a permit sits in** (how strict, how accessible, how risky,
   how well governed) is modelled in the published literature and is computable
   from open data — but it is context, never a permission and never a site score
   (AGENTS.md rule 4).
4. The part that genuinely needs a human is a **short list per named site**: who
   issues the permit, what it costs, how long it takes, and whether the local
   community agrees. That is one small table for the sites in the demo, not a
   per-cell data collection project.
5. Anything we cannot vouch for must show as **unknown**. The codebase already
   has that idea (`missing_reason`, "no data" outcomes, and the S7i rule that
   unknown never fails a limit). The literature gives us the tool to do it
   properly: **conformal prediction** — a way to publish a number only when the
   model is calibrated enough to, and to say "unknown" otherwise.

## 1. What the Logistics page says today (code, not memory)

Facts and where they come from, at `main` @ `1ffa5a0`:

| Fact | Where | Quote / behaviour |
|---|---|---|
| The Logistics step lists six measures per site | `apps/planner/src/steps/Reports.tsx` (`logisticsFacts` in `apps/planner/src/model.ts`) | Travel to the nearest city (median), Travel fastest 10 % of the cell, Nearest paved-runway airport, **Protected land in the cell**, Water cover in the cell, Elevation lowest→highest |
| The page says so itself | `apps/planner/src/steps/Reports.tsx` | "Not in this data: cost, permits, vehicles, comms. Use the checklist." |
| The engine's permit line is a prompt, not a fact | `services/engine/src/planner/logistics.py` (`checklist`) | `permits` prompt is written from `protected_pct`; `answer` starts `None`, `from: "scientist"` |
| `protected_pct` is empty for every cell | `services/ingest/src/p0ingest/context.py` | `"protected_pct": pa.nulls(n, pa.float64())`; `missing["protected_pct"] = "licence-restricted"` |
| Why | `data/catalog/wdpa-protected-areas.yaml` (licence probed live 2026-11-14) | Protected Planet terms: derivative works may not be put to commercial use without written permission; WDPCA materials "may not be sub-licensed" or redistributed, including within derivative works. "No WDPA snapshot or derived `protected_pct` is published." |
| The `protected` limit can therefore never be checked | `services/engine/src/planner/logistics.py` (`limits`) | outcome is `unknown` → the page shows "no data" |
| The risk step loses its land-use evidence too | `apps/planner/src/model.ts` (`ecoEvidence`) | with `protected_pct` missing: "Verify national park boundaries, indigenous/local stewardship, and land-use permits before field commitment." |
| The precedent for how we treat this | `docs/decisions/ADR-0006-eonet-for-risks.md` | EONET was allowed under NASA's open-data policy with the disclaimer shown; "WDPA (protected areas) stays withheld." |

So today the answer to "what law applies here?" on that page is: *we don't know,
and the page tells the scientist to go and check.* The question behind this
review is whether we can do better without breaking the licence rules or
inventing data.

## 2. Method (dated, reproducible)

- **Counts**: OpenAlex REST, `GET https://api.openalex.org/works?search=<query>&per_page=1`,
  read from `meta.count`. Full-text relevance search, so counts are upper bounds
  with noise — every count is paired with what we read into it.
- **Citations**: every DOI below was resolved on **2026-11-15** through
  `GET https://api.crossref.org/works/<doi>` and the title, venue and year read
  back from the record. Two candidate DOIs failed (they resolved to a different
  paper or to nothing) and were **dropped, not cited** — one of them was the
  journal version of the policy-uncertainty paper, so this doc cites the NBER
  working-paper DOI that did resolve.
- arXiv identifiers were resolved at `https://arxiv.org/abs/<id>`.
- Licence rules, treaties and index products are cited by publisher URL, not as
  literature.

## 3. The literature on this exact question is nearly empty

| Query (OpenAlex `search`, 2026-11-15) | `meta.count` | What it tells us |
|---|---|---|
| `"planetary analogue site" governance` | **2** | Nobody has published how analogue sites are governed. |
| `"analogue site" "protected area" field research` | **22** | The closest existing corner: protected status vs. fieldwork. |
| `"planetary analogue" logistics accessibility` | **21** | Access and logistics for analogue sites are basically unpublished. |
| `"planetary analogue" permit access` | 79 | Noisy; top hits are data-accessibility papers, not permits. |
| `planetary analogue site governance regulation` | 1,224 | Same story with noise; top hits are governance-of-research papers. |
| `legal case embedding analogical reasoning` | 1 | Legal analogical reasoning has almost no citation graph yet. |
| `contract clause type extraction regulatory NLP` | 1,232 | But *reading* contracts and regulations is a mature, cited field. |
| `conformal prediction selective classification abstention` | 1,150 | Publishing "unknown" with a guarantee is a real tool. |
| `spatial accessibility index transportation` | 124,911 | The access half of the page sits on a huge literature. |

**Reading:** we cannot buy a ready-made "permit burden" model, because nobody
has built one. But the *two* halves we need are both mature: reading law, and
computing access/context from open data.

## 4. Four families of substitutes, with the literature behind each

### A. The law already exists — read it instead of typing it

Most rules that bind a field campaign are written down and published: park
management plans, special-use-permit rules, Antarctic Treaty measures, national
mining codes, planetary-protection directives. Reading them is a solved
NLP problem.

| Work | What it gives us | What it forecloses / limit |
|---|---|---|
| Henderson et al. 2021, "CUAD: An Expert-Annotated NLP Dataset for Legal Contract Review", *arXiv:2103.06268* — 41 expert-labelled clause types (government regulation, licence grant, restrictions, liability, termination…) | The label set for a permit-clause extractor. We do not have to invent a permit taxonomy. | Hand-rolled parsing with no benchmark is not defensible. |
| Guha et al. 2023, "LegalBench", *NeurIPS 2023*, [doi:10.2139/ssrn.4583531](https://doi.org/10.2139/ssrn.4583531) | A standard suite of legal-reasoning tasks to benchmark any extractor we write. | We must report on it, not just claim quality. |
| Chalkidis et al. 2022, "LexGLUE", *ACL 2022*, [doi:10.18653/v1/2022.acl-long.297](https://doi.org/10.18653/v1/2022.acl-long.297) | Benchmarks and ready legal encoders to start from. | Fine-tuning a legal encoder is not a contribution. |
| Tang et al. 2024, "CaseLink", *SIGIR 2024*, [doi:10.1145/3626772.3657693](https://doi.org/10.1145/3626772.3657693); 2026, "LEXA", *World Wide Web*, [doi:10.1007/s11280-026-01407-w](https://doi.org/10.1007/s11280-026-01407-w) | Modern legal retrieval: find the rules that apply to a case. Our version: find the rules that apply to a place. | The retriever is not our contribution; the *place→regime* link is. |
| Cheney & Newman 2020, "Planetary Protection in the New Space Era: Science and Governance", *Front. Astron. Space Sci.*, [doi:10.3389/fspas.2020.589817](https://doi.org/10.3389/fspas.2020.589817) | The sample-handling and contamination rules that apply to analog campaigns are **published policy**. | "Biology rules" on the page must cite policy, not folklore. |
| *Protocol on Environmental Protection to the Antarctic Treaty* (Madrid Protocol, 1991), *Polar Record*, [doi:10.1017/s0032247400018763](https://doi.org/10.1017/s0032247400018763) | McMurdo's whole permit regime is one written instrument (plus ATCM Measures and NSF Antarctic Program rules). | Antarctica's block can be derived from documents, not from interviews. |

**Honest limit:** extraction gives *obligations text and instrument links*. It
does not give a permission, and it must not be shown as one.

### B. Compute the protected-land share ourselves from data we may publish

The WDPA block is a licence problem, not a science problem. Other sources of
protected land exist with terms that allow derived use, and each needs its own
licence check before we touch it (the repo's `data/catalog` rows exist for
exactly this).

| Source / work | What it gives us | Limit to state in the catalogue |
|---|---|---|
| OpenStreetMap `boundary=protected_area`, `leisure=nature_reserve`, `landuse=conservation` polygons | A protected-land share we can compute ourselves, per cell, with a hashed snapshot | ODbL is **share-alike**: a derived database may have to be published under ODbL. That is an owner decision, not an agent decision. |
| Haklay 2008, "OpenStreetMap: User-Generated Street Maps", *IEEE Pervasive Comput.*, [doi:10.1109/mprv.2008.80](https://doi.org/10.1109/mprv.2008.80); 2010, "How good is volunteered geographical information?", *Environ. Plan. B*, [doi:10.1068/b35097](https://doi.org/10.1068/b35097) | The base layer and the first honesty check on it. | — |
| Barron et al. 2013, "A Comprehensive Framework for Intrinsic OpenStreetMap Quality Analysis", *Trans. GIS*, [doi:10.1111/tgis.12073](https://doi.org/10.1111/tgis.12073) | **Intrinsic** quality measures (no reference data needed) → a per-cell confidence for every OSM-derived logistics field. | — |
| Herfort et al. 2023, *Nat. Commun.*, [doi:10.1038/s41467-023-39698-6](https://doi.org/10.1038/s41467-023-39698-6) | Quantified **inequality of OSM completeness** — the strongest published warning that a missing road tag does not mean "no road". | Abstain where coverage is thin; never read "no access" from "no tag". |
| "A Review of OpenStreetMap Data", in *Mapping and the Citizen Sensor* (Ubiquity Press eBooks), 2017, [doi:10.5334/bbf.c](https://doi.org/10.5334/bbf.c) | Systematic coverage review; sets expectations about rural and desert bias. | Cited by title and DOI; the Crossref record lists no authors. |
| National open data (for example PAD-US for the United States, national park and land agencies elsewhere) | Per-country protected land with open terms, and a real authority to point at. | More per-country work; each source gets its own catalogue row and licence probe. |
| Licence literature: "Open licensing and databases", *IFOSSLR* 2012, [doi:10.5033/ifosslr.v4i1.62](https://doi.org/10.5033/ifosslr.v4i1.62); "Towards a Benchmark for Shared Databases", *Datenbank-Spektrum* 2022, [doi:10.1007/s13222-022-00429-8](https://doi.org/10.1007/s13222-022-00429-8); FAIR principles, *Sci. Data* 2016, [doi:10.1038/sdata.2016.18](https://doi.org/10.1038/sdata.2016.18) | The vocabulary for "we may compute this and publish the result" versus "we may not redistribute derived material". | Not legal advice; the licence text decides, and the owner decides what to ship. |
| "Mapping global development potential for renewable energy, fossil fuels, mining and agriculture sectors", *Sci. Data* 2019, [doi:10.1038/s41597-019-0084-8](https://doi.org/10.1038/s41597-019-0084-8) | Precedent for a **published, openly licensed derived suitability layer** — the shape a lawful protected-land layer would take. | It is a suitability layer, not a legal one. |

**Honest limit:** a computed protected-land share is a *fact about land status*.
It says nothing about whether a permit would be granted, who grants it, or how
long it takes. And every source needs its own licence probe before use — the
WDPA row already shows what that probe looks like.

### C. Model the setting a permit sits in (context, never a permission)

| Work | What it gives us | Limit |
|---|---|---|
| Shah & Baylis et al. 2021, "What determines the effectiveness of national protected area networks?", *Environ. Res. Lett.*, [doi:10.1088/1748-9326/ac05ed](https://doi.org/10.1088/1748-9326/ac05ed) | Published models of how well protected land is actually managed — the difference between "protected on paper" and "protected in practice". | Country and network level, not a cell value. |
| Pullin & Bangpan 2013, "Human well-being impacts of terrestrial protected areas", *Environ. Evidence*, [doi:10.1186/2047-2382-2-19](https://doi.org/10.1186/2047-2382-2-19) | Evidence that protected status affects local people — so "consent" is a real field, not a formality. | Does not tell us the answer for our sites. |
| Ward & Stringer 2018, *J. Environ. Manage.*, [doi:10.1016/j.jenvman.2018.09.018](https://doi.org/10.1016/j.jenvman.2018.09.018) | Co-management and perceived livelihood impacts — the governance mechanism behind "who has a say". | — |
| Baker, Bloom & Davis 2016, "An Index of Global Economic Policy Uncertainty", NBER w22740, [doi:10.3386/w22740](https://doi.org/10.3386/w22740) | A published index for "how fast rules change", which is the honest way to express "the permit rules here may change". | Country-month level. |
| UNCTAD *Liner Shipping Connectivity Index*, *Review of Maritime Transport* 2011, [doi:10.18356/c55ec994-en](https://doi.org/10.18356/c55ec994-en); robustness check in *Maritime Econ. Logistics* 2021, [doi:10.1057/s41278-021-00185-8](https://doi.org/10.1057/s41278-021-00185-8) | A computed "how connected is this country to freight" number — the kind of model the page can show instead of a collected one. | Country level, and not a permit. |
| "The value proposition of the Global Health Security Index", *BMJ Global Health* 2020, [doi:10.1136/bmjgh-2020-003648](https://doi.org/10.1136/bmjgh-2020-003648) | A worked precedent of a composite index with published sub-scores and stated uncertainty — the pattern to copy for a "regulatory setting" block. | Not about permits. |
| Geurs & van Wee 2004, *J. Transport Geography*, [doi:10.1016/j.jtrangeo.2003.10.005](https://doi.org/10.1016/j.jtrangeo.2003.10.005) | The accessibility model family behind "how far is this from everything" — the method behind our existing travel-time raster. | Already used; cite it, do not re-invent it. |
| Román et al. 2018, "NASA's Black Marble nighttime lights product suite", *Remote Sens. Environ.*, [doi:10.1016/j.rse.2018.03.017](https://doi.org/10.1016/j.rse.2018.03.017); Gibson & Olivia 2020, *J. Econ. Surveys*, [doi:10.1111/joes.12387](https://doi.org/10.1111/joes.12387) | Night lights as a proxy for "is there power and activity near here" — and the econometrics of when that proxy is fair to use. | A proxy is a proxy; it must say so. |
| Pesaresi et al. 2024, "Advances on the Global Human Settlement Layer…", *Int. J. Digital Earth*, [doi:10.1080/17538947.2024.2390454](https://doi.org/10.1080/17538947.2024.2390454) | Built-up and settlement surfaces → "is there infrastructure near here". | — |
| Python & Illian 2018, *JRSSA-A*, [doi:10.1111/rssa.12384](https://doi.org/10.1111/rssa.12384); "Tourism, terrorism and political instability", *Ann. Tour. Res.* 1998, [doi:10.1016/s0160-7383(97)00093-5](https://doi.org/10.1016/s0160-7383(97)00093-5); "Tourist security, terrorism risk management and tourist safety", *Ann. Tour. Res.* 2021, [doi:10.1016/j.annals.2021.103207](https://doi.org/10.1016/j.annals.2021.103207) | Published models for "how risky is working here" — the safety side of gate 5, with intervals rather than a verdict. | Safety risk is not the same as EONET's "events recorded". |

### D. Decide *what* to collect by model (this is the part that saves the most time)

| Work | What it gives us |
|---|---|
| Campos et al. 2024, "Conformal Prediction for NLP: A Survey", *TACL*, [doi:10.1162/tacl_a_00715](https://doi.org/10.1162/tacl_a_00715) | Calibrated abstention for language outputs: publish a permit field only when the extractor is confident enough, otherwise publish "unknown". |
| Angelopoulos & Bates 2023, "Conformal Prediction: A Gentle Introduction", *Found. Trends ML*, [doi:10.1561/2200000101](https://doi.org/10.1561/2200000101) | The accessible statement of the guarantee. |
| Angelopoulos, Bates, Candès et al. 2025, "Learn then test: Calibrating predictive algorithms to achieve risk control", *Ann. Appl. Stat.*, [doi:10.1214/24-aoas1998](https://doi.org/10.1214/24-aoas1998) | Risk-controlling calibration of *any* predictor, including a document parser. |
| Active learning (OpenAlex probe `active learning information gain annotation budget geospatial` → 1,010 works, 2026-11-15) | Rank candidate sites by what a human look would most change, so collection happens only where it matters. |

**Why this fits us:** the codebase already has `missing_reason` codes, "no data"
limit outcomes, and the S7i rule that an unknown never removes a site. A
conformal layer is the missing piece: it makes "unknown" a *calibrated* choice
rather than a shrug, and it tells us which sites a human should look at first.

## 5. Field-by-field verdict for the Logistics page

| Logistics field | Can it be derived? | Method | Evidence class | Human needed? |
|---|---|---|---|---|
| Protected land in the cell | **Yes, from a source we may publish** | compute from an open protected-area source with its own catalogue row and licence probe (OSM polygons, national open data) | modelled/derived from observed polygons, with a coverage-confidence flag | no (licence check + owner sign-off) |
| Which regime applies (national park, protected area, mining claim, free land, Antarctic) | **Partly** | classify by published instrument + OSM tags; human confirms the label | modelled (parsed) | yes, once per *named site* |
| Which obligations (file a plan, get a permit, biosecurity, sample export) | **Partly** | extract obligation spans from the published instrument (CUAD-style clause types) | modelled (parsed) | no, if we show the text |
| Who issues the permit and how to apply | **No** | agency page, one row per site | observed (manual) | yes |
| Fees, lead times | **No** | agency page | observed (manual) | yes |
| Local community / landholder consent | **No** | agency + community sources | observed (manual) | yes |
| Travel time to city / airport distance | **Already computed** | MAP travel-time raster, OurAirports | observed + derived | no |
| Power, water, comms, lodging nearby | **Partly** | night lights, GHSL built-up, OSM tags | modelled | no |
| Season window | **Already computed** | monthly traits + EONET months | observed + derived | no |
| Safety risk | **Partly** | published risk models + EONET rows, each with its own caveat | modelled | no |
| "May we do X here?" | **Never** | not automated | — | legal advice; we publish instruments, not permissions |

**Net effect:** the Logistics page can carry a **laws and permits** block built
from published instruments and computed land status, with one small manual
table for the named sites in the demo, and it never has to say "we don't know"
for the whole block.

## 6. The irreducible manual list (and how to keep it small)

One row per **named site** (not per cell), with: regime class, issuing
authority, instrument title + URL, date checked, and the sha256 of the page we
read. For a 20-site shortlist that is 20 short rows — an afternoon, not a data
project — and it becomes a normal snapshot under `data/snapshots/` with a
catalogue row like every other source.

## 7. What must not be automated

1. **A permission.** Publishing "you may sample here" is legal advice. We
   publish the instrument, the authority and the date; the scientist decides.
2. **Community consent.** Rights of indigenous and local communities are not
   derivable from a model or a polygon (Pullin & Bangpan 2013).
3. **Anything a model is unsure about.** Unknown stays unknown (rule 3).

## 8. If we act on this, the repo rules apply (out of scope here)

This review changes nothing by itself. If the owner wants any of it:

- **Contract lane first**: a new field on `contracts/site-plan.schema.json`
  (the `logistics` block) and, if it becomes a trait, `contracts/trait-map.schema.json`.
  A new `checklist[].item` value or a new `logistics` property needs a contract
  change before code (rule 5).
- **Statements before verdicts (ADR-0001)**: any new field that can change a
  verdict, a limit outcome or a shortlist needs its own frozen statement first.
  S7–S10 are frozen; this would be new work, not an edit.
- **Data lane**: new sources need a `data/catalog/*.yaml` row with a live
  licence probe before the first fetch, exactly as the WDPA row shows.
- **Provenance (rule 3)**: every published number keeps URL, date, hash and
  licence. A model-derived value inherits the provenance of its inputs, plus the
  model's own version and calibration date.
- **No scalar creep (rule 4)**: indices and proxies are context lines. No site
  gets one score, and nothing here averages across traits.

## 9. Risks

| Risk | Why it is real | What we do about it |
|---|---|---|
| Licence breach | WDPA already blocks one field; ODbL share-alike can reach our tables | Licence probe + catalogue row before first use; owner sign-off; never publish a derived field from a restricted source |
| Crowdsourced data bias | OSM completeness is uneven (Herfort et al. 2023) | Intrinsic quality metric per cell; abstain when thin; never read "no road" from "no tag" |
| Model confidently wrong | Legal extraction hallucinates clauses | Calibrated abstention (conformal), human-checked spans, and the source text shown next to the claim |
| Proxy read as permission | Indices look like answers | Label every line with its evidence class; never place a context line in a verdict path |
| Stale law | Rules change | Date and hash every instrument; stale ⇒ unknown |
| Scalar creep | A composite "regulatory index" is tempting | Context only; per-trait view stays as it is |

## 10. Recommendation, in plain English

1. **Do not collect permits per cell.** There are no cells with permits; permits
   are per site and per regime, and the rules are written down.
2. **Get a publishable protected-land number** from a source whose terms allow
   derived use, with its own catalogue row and licence probe. That alone makes
   the `protected` limit checkable and gives the risk step its land-use evidence.
3. **Add a "laws and permits" block to the Logistics page** that is derived from
   published instruments: which regime, which obligations, which authority, as of
   which date — with the instrument link and the extracted text. Keep the
   scientist's checklist for what instruments cannot say.
4. **Publish "unknown" on purpose.** Use calibrated abstention so the page
   never guesses, and use it to rank which sites a human should check next.
5. **Never publish a permission**, and never let a context index into a verdict.

## 11. Open questions for the owner

1. Is a *computed* protected-land share (from an open source) acceptable to
   ship, given the ODbL share-alike question? If yes, which source do we want
   first: OSM polygons (global, ODbL) or national open data (cleaner terms, one
   country at a time)?
2. Do we want the "laws and permits" block to name **named sites only** (a
   dossier-style list) rather than per-cell? Recommendation: yes — it matches
   how permits work and avoids pretending we know a hex boundary's legal status.
3. Do we want to write to Protected Planet for written permission to publish the
   derived share? The catalogue note says no download or snapshot without
   permission; a one-line ask could unblock the cleanest source.
4. Who owns the small manual table (named site → authority, fees, lead time) —
   a research agent per region, or the owner?

## 12. Reproduction (2026-11-15)

```
counts  : GET https://api.openalex.org/works?search=<urlencoded query>&per_page=1   → meta.count
verify  : GET https://api.crossref.org/works/<doi>                                   → title, venue, year
arxiv   : GET https://arxiv.org/abs/<id>
licence : GET https://www.protectedplanet.net/en/legal                                (already recorded in data/catalog/wdpa-protected-areas.yaml, probed 2026-11-14)
```

Queries used: `"planetary analogue site" governance` (2) · `"analogue site"
"protected area" field research` (22) · `"planetary analogue" logistics
accessibility` (21) · `"planetary analogue" permit access` (79) · `planetary
analogue site governance regulation` (1,224) · `"terrestrial analogue" permit
access` (262) · `legal case embedding analogical reasoning` (1) · `contract
clause type extraction regulatory NLP` (1,232) · `conformal prediction selective
classification abstention` (1,150) · `spatial accessibility index transportation`
(124,911) · `spatial model travel risk crime` (48,573) · `active learning
information gain annotation budget geospatial` (1,010) · `permit processing time
mining renewable energy applications dataset` · `policy uncertainty index
investment regulation` · `protected areas alternative open data` · `open database
licence share alike derived database`.

## 13. Limits of this review

- Research only. No code, contract, data or UI change is included, and none
  should be made from this doc without the work orders in §8.
- The Logistics screen in Nic's Figma build (`apps/mission-ui`) is still local
  and not pushed, so this review reads the **shipped** planner Logistics step
  (PR #182) and the engine module behind it. If the Figma screen has different
  fields, the field-by-field table in §5 needs one more pass.
- No DOI in this doc was cited without resolving it on the date above; two
  candidates were dropped rather than cited.
- The licence questions in §4B are flagged, not answered. Only the owner (with
  counsel if needed) can decide what we are allowed to publish.
