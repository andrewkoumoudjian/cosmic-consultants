# Literature corpus: what is here and what is missing

Work order: W4, issue #5. Run 2026-11-15 06:18-06:19 UTC by opencode
(deepseek/deepseek-flash, OpenCode, human: Nico @Niccc333).

**The point:** this folder now holds a rebuildable, DOI-deduped BibTeX file of
3,889 works from the four doc 03 queries. Crossref answered; OpenAlex was
blocked by a rate limit. **Nothing here has been read.** The curated core in
[doc 03](../docs/research/03-literature-inventory.md) stays the only cited set.

## Files

| File | What it is | Bytes | sha256 (start) |
|---|---|---|---|
| `corpus.bib` | 3,889 BibTeX entries, one per DOI | 1,572,772 | `f652cc6e1237088d` |
| `corpus-index.csv` | Same entries as a table: key, doi, title, year, type, container, source, queries | 754,979 | `665543366bbd34fe` |
| `harvest-report.json` | Per-query request summary (first-page URL, page count, rows, error), counts by type and year, output hashes, BibTeX check | - | - |
| `doi-spotcheck.json` | 10 sampled DOIs with the HTTP status and timestamp from a live probe | - | - |
| `harvest.py` | The harness. Standard library only; installs nothing | - | - |
| `queries.json` | The four queries, doc 03's 2026-11-12 OpenAlex counts, and a note on the reconstructed q4 | - | - |

## Method

- Queries: the four in doc 03 section 0. Query strings are in `queries.json`.
  Doc 03 does not quote the fourth (narrow lunar-south-pole) string, so
  `"lunar south pole landing site"` is a reconstruction and is labelled as one.
- Crossref: `GET api.crossref.org/works?query.bibliographic=...&rows=200&offset=...&select=...`,
  five pages per query (1,000 rows), relevance order, 1 s between pages.
  The report stores the first-page URL per query, the page count and any error;
  it does not store every page URL or a per-page status. No page failed (an error
  would have stopped that query and been recorded).
- OpenAlex: `GET api.openalex.org/works?search=...` with cursor paging. Every
  attempt returned **HTTP 429** (see below).
- Dedupe: DOI, lowercased and stripped of the `https://doi.org/` prefix.
  Records without a DOI would fall back to normalized title + year; none needed
  the fallback.
- BibTeX: type map Crossref to BibTeX (`journal-article` to `article`, and so
  on); keys are author + year + a title fragment, de-duplicated with a number.

## Results

- 4,000 raw rows in, **3,889 unique DOIs** out. All 3,889 carry a DOI.
- Per query (records can appear in more than one query):
  q1 995, q2 997, q3 997, q4 996.
- Crossref's own totals are **not topical counts**: 711,621 / 4,435,013 /
  466,720 / 1,412,296. The API matches words loosely, so the numbers say
  nothing about how many papers are on topic. Do not quote them as corpus size.
- Doc 03's 2026-11-12 OpenAlex counts (3,491 / 1,692 / 1,341 / 199) were **not**
  re-probed today. Under the evidence rule they are stale until a run succeeds.

By type: article 1,614; inproceedings 929; incollection 633; misc 615;
techreport 46; phdthesis 35; book 17.

By year (top 15 of the set): 2027 7, 2026 380, 2025 368, 2024 277, 2023 208,
2022 201, 2021 190, 2020 142, 2019 89, 2018 82, 2017 83, 2016 89, 2015 85,
2014 87, 2013 61. **227 entries have no year**, and **39 have no title**;
both are kept (rule 6: preserve partial work) and are flagged here.

Quality warnings, measured not guessed:

- 153 entries share a near-identical title and year with another entry under a
  different DOI (preprint versions, table DOIs, duplicated records).
- Off-topic hits are in the relevance-ranked slice, same as doc 03 warned:
  sampled examples include an analog-to-digital converter thesis and a
  maritime drone landing paper.
- This is a search snapshot, not a systematic review. It does not replace
  reading.

## BibTeX validity

`python research/corpus/harvest.py --validate-only` reads the written file and
checks key uniqueness and brace balance. Current output, rc=0:

```text
entries 3889, uniqueKeys 3889, duplicateKeys [], braceBalance 0
sha256 f652cc6e1237088d569ac19323d64f5e44db6265ad41addd97f046fcc81d4768
```

`assign_keys` now checks every emitted key against the full set, so a natural
key cannot collide with an earlier suffixed one on a rerun.

## DOI spot-check

Ten DOIs, at least one from each query, resolved through
`api.crossref.org/works/{doi}` on 2026-11-15, all **HTTP 200**. The full list
with statuses and timestamps is in `doi-spotcheck.json`. Examples:

- `10.1007/978-1-4020-8682-3_28` - Scale Modeling for Landing of a Lunar Probe
- `10.52202/083076-0079` - EXP 91 Aurora Mission: human adaptation on Mars
- `10.21203/rs.3.rs-11172801/v1` - Design of Lunar Soil Simulant
- `10.3847/psj/adbc6c` - VIPER landing site prospectivity, Mons Mouton

## Why OpenAlex is missing

Each OpenAlex call returned HTTP 429:

> Rate limit exceeded. Insufficient budget. This request has no API key, so it
> counts against the free daily budget shared by everyone on your network's IP
> address, and that budget is used up ($0 remaining; resets at midnight UTC).

The response also recommends a free API key. `harvest.py` reads
`OPENALEX_API_KEY` from the environment and adds it to the request, so the
OpenAlex half runs without code changes once a key exists:

```text
python research/corpus/harvest.py
```

Re-running rewrites `corpus.bib`, `corpus-index.csv` and
`harvest-report.json` from the live APIs. Counts will drift; the report records
the exact run time and every URL.

## Reading status

None of these works has been read for this project. Do not cite an entry from
`corpus.bib` in a claim until someone has read it and recorded that in an issue
or a data file. Doc 03 section 1-6 remains the cited core.
