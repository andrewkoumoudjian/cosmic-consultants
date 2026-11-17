"""Rebuild the literature corpus from live OpenAlex and Crossref probes.

Stdlib only. Writes corpus.bib, corpus-index.csv and harvest-report.json into
the output directory. Reading status is not inferred: nothing here is "read".
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import re
import sys
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

UA = "cosmic-consultants-corpus/1.0 (+https://github.com/andrewkoumoudjian/cosmic-consultants)"
CROSSREF = "https://api.crossref.org/works"
OPENALEX = "https://api.openalex.org/works"
TYPE_MAP = {
    "journal-article": "article",
    "proceedings-article": "inproceedings",
    "book-chapter": "incollection",
    "book": "book",
    "monograph": "book",
    "posted-content": "misc",
    "dissertation": "phdthesis",
    "report": "techreport",
    "dataset": "misc",
    "peer-review": "misc",
}


def utc_now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def fetch_json(url, timeout=45, attempts=3):
    last = None
    for attempt in range(1, attempts + 1):
        request = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return json.loads(response.read().decode("utf-8")), None
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", "replace")[:400]
            last = f"HTTP {exc.code}: {body}"
            if exc.code in (429, 500, 502, 503) and attempt < attempts:
                time.sleep(5 * attempt)
                continue
            return None, last
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            last = f"{type(exc).__name__}: {exc}"
            if attempt < attempts:
                time.sleep(3 * attempt)
                continue
            return None, last
    return None, last


def normalize_doi(value):
    if not value:
        return ""
    doi = str(value).strip().lower()
    for prefix in ("https://doi.org/", "http://doi.org/", "https://dx.doi.org/", "doi:"):
        if doi.startswith(prefix):
            doi = doi[len(prefix):]
    return doi.strip()


def clean_title(value):
    if isinstance(value, list):
        value = value[0] if value else ""
    text = re.sub(r"<[^>]+>", "", str(value or ""))
    return re.sub(r"\s+", " ", text).strip()


def ascii_slug(text, limit=40):
    folded = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    slug = re.sub(r"[^A-Za-z0-9]+", "-", folded).strip("-").lower()
    return slug[:limit] or "anon"


def bib_escape(value):
    return str(value).replace("&", r"\&").replace("%", r"\%").replace("#", r"\#")


def crossref_record(item, query_id):
    year = ""
    parts = (item.get("issued") or {}).get("date-parts") or [[None]]
    if parts and parts[0] and parts[0][0]:
        year = str(parts[0][0])
    authors = []
    for author in item.get("author") or []:
        family = (author.get("family") or "").strip()
        given = (author.get("given") or "").strip()
        if family and given:
            authors.append(f"{family}, {given}")
        elif family or author.get("name"):
            authors.append(family or author.get("name", ""))
    container = clean_title(item.get("container-title"))
    title = clean_title(item.get("title"))
    return {
        "doi": normalize_doi(item.get("DOI")),
        "title": title,
        "year": year,
        "type": TYPE_MAP.get(item.get("type", ""), "misc"),
        "authors": authors,
        "container": container,
        "url": item.get("URL", ""),
        "source": "crossref",
        "queries": [query_id],
    }


def openalex_record(item, query_id):
    authors = []
    for authorship in item.get("authorships") or []:
        name = ((authorship.get("author") or {}).get("display_name") or "").strip()
        if name:
            authors.append(name)
    location = item.get("primary_location") or {}
    source = location.get("source") or {}
    return {
        "doi": normalize_doi(item.get("doi")),
        "title": clean_title(item.get("title")),
        "year": str(item.get("publication_year") or ""),
        "type": TYPE_MAP.get(item.get("type", ""), "misc"),
        "authors": authors,
        "container": source.get("display_name") or "",
        "url": location.get("landing_page_url") or item.get("id", ""),
        "source": "openalex",
        "queries": [query_id],
    }


def harvest_crossref(query, pages, rows, report):
    items = []
    entry = {"source": "crossref", "query": query["id"], "url": "", "pages": 0,
             "fetched": 0, "totalReported": None, "error": None, "started": utc_now()}
    for page in range(pages):
        params = {
            "query.bibliographic": query["text"],
            "rows": str(rows),
            "offset": str(page * rows),
            "select": "DOI,title,issued,container-title,author,type,URL",
        }
        url = f"{CROSSREF}?{urllib.parse.urlencode(params)}"
        entry["url"] = entry["url"] or url
        payload, error = fetch_json(url)
        if error:
            entry["error"] = error
            break
        message = payload.get("message") or {}
        entry["totalReported"] = message.get("total-results")
        batch = message.get("items") or []
        entry["pages"] += 1
        entry["fetched"] += len(batch)
        items.extend(crossref_record(item, query["id"]) for item in batch)
        if len(batch) < rows:
            break
        time.sleep(1.0)
    entry["finished"] = utc_now()
    report.append(entry)
    return items


def harvest_openalex(query, pages, per_page, report):
    items = []
    entry = {"source": "openalex", "query": query["id"], "url": "", "pages": 0,
             "fetched": 0, "totalReported": None, "error": None, "started": utc_now()}
    cursor = "*"
    for _ in range(pages):
        params = {
            "search": query["text"],
            "per-page": str(per_page),
            "cursor": cursor,
            "select": "id,doi,title,publication_year,type,primary_location,authorships",
        }
        if os.environ.get("OPENALEX_API_KEY"):
            params["api_key"] = os.environ["OPENALEX_API_KEY"]
        url = f"{OPENALEX}?{urllib.parse.urlencode(params)}"
        entry["url"] = entry["url"] or url
        payload, error = fetch_json(url)
        if error:
            entry["error"] = error
            break
        meta = payload.get("meta") or {}
        entry["totalReported"] = meta.get("count")
        batch = payload.get("results") or []
        entry["pages"] += 1
        entry["fetched"] += len(batch)
        items.extend(openalex_record(item, query["id"]) for item in batch)
        cursor = meta.get("next_cursor")
        if not batch or not cursor:
            break
        time.sleep(1.0)
    entry["finished"] = utc_now()
    report.append(entry)
    return items


def merge(records):
    merged = {}
    order = []
    for record in records:
        key = record["doi"] or ("title:" + ascii_slug(record["title"], 120) + ":" + record["year"])
        if key in merged:
            existing = merged[key]
            for query in record["queries"]:
                if query not in existing["queries"]:
                    existing["queries"].append(query)
            if not existing["doi"] and record["doi"]:
                existing["doi"] = record["doi"]
            for field in ("title", "year", "container", "url"):
                if not existing.get(field) and record.get(field):
                    existing[field] = record[field]
            if not existing.get("authors") and record.get("authors"):
                existing["authors"] = record["authors"]
            continue
        record = dict(record)
        merged[key] = record
        order.append(key)
    return [merged[key] for key in order]


def assign_keys(records):
    used = set()
    for record in records:
        family = "anon"
        if record["authors"]:
            first = record["authors"][0]
            family = first.split(",")[0] if "," in first else first.split(" ")[-1]
        base = ascii_slug(f"{family}{record['year']}{record['title'][:24]}")
        key = base
        suffix = 1
        while key in used:
            suffix += 1
            key = f"{base}{suffix}"
        used.add(key)
        record["key"] = key
    return records


def validate_bib(path):
    text = path.read_text(encoding="utf-8")
    keys = re.findall(r"(?m)^@\w+\{([^,]+),", text)
    duplicates = sorted({key for key in keys if keys.count(key) > 1})
    balance = text.count("{") - text.count("}")
    report = {
        "entries": len(keys),
        "uniqueKeys": len(set(keys)),
        "duplicateKeys": duplicates,
        "braceBalance": balance,
        "sha256": sha256(path),
    }
    if duplicates or balance != 0:
        raise ValueError(f"invalid BibTeX output: {report}")
    return report


def write_bib(path, records):
    lines = []
    for record in records:
        fields = [
            ("title", "{" + record["title"] + "}" if record["title"] else ""),
            ("author", " and ".join(record["authors"])),
            ("year", record["year"]),
            ("doi", record["doi"]),
            ("journal", record["container"]),
            ("url", record["url"]),
            ("note", "source: " + record["source"] + "; queries: " + ",".join(record["queries"])),
        ]
        body = ",\n".join(
            f"  {name} = {{{bib_escape(value)}}}" for name, value in fields if value
        )
        lines.append(f"@{record['type']}{{{record['key']},\n{body}\n}}")
    path.write_text("\n\n".join(lines) + "\n", encoding="utf-8")


def write_index(path, records):
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(["key", "doi", "title", "year", "type", "container", "source", "queries"])
        for record in records:
            writer.writerow([record["key"], record["doi"], record["title"], record["year"],
                             record["type"], record["container"], record["source"],
                             ";".join(record["queries"])])


def sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, default=Path(__file__).resolve().parent)
    parser.add_argument("--queries", type=Path)
    parser.add_argument("--crossref-pages", type=int, default=5)
    parser.add_argument("--crossref-rows", type=int, default=200)
    parser.add_argument("--openalex-pages", type=int, default=20)
    parser.add_argument("--openalex-per-page", type=int, default=200)
    parser.add_argument("--skip-openalex", action="store_true")
    parser.add_argument("--validate-only", action="store_true")
    args = parser.parse_args(argv)

    out = args.out
    if args.validate_only:
        print(json.dumps(validate_bib(out / "corpus.bib"), indent=2))
        return 0
    queries_path = args.queries or out / "queries.json"
    config = json.loads(queries_path.read_text(encoding="utf-8"))
    queries = config["queries"]

    report = []
    records = []
    started = utc_now()
    for query in queries:
        records.extend(harvest_crossref(query, args.crossref_pages, args.crossref_rows, report))
    if not args.skip_openalex:
        for query in queries:
            records.extend(harvest_openalex(query, args.openalex_pages, args.openalex_per_page, report))
    merged = assign_keys(merge(records))

    merged.sort(key=lambda r: (r["year"] == "", r["year"] or "", (r["authors"] or [""])[0], r["title"]),
                reverse=True)
    bib_path = out / "corpus.bib"
    index_path = out / "corpus-index.csv"
    write_bib(bib_path, merged)
    write_index(index_path, merged)
    bib_check = validate_bib(bib_path)

    titles = {}
    near_duplicates = 0
    for record in merged:
        fingerprint = ascii_slug(record["title"], 120) + "|" + record["year"]
        titles[fingerprint] = titles.get(fingerprint, 0) + 1
        if titles[fingerprint] > 1:
            near_duplicates += 1

    per_query = {}
    for query in queries:
        per_query[query["id"]] = {
            "text": query["text"],
            "doc03OpenAlexCount": query.get("doc03Count"),
            "records": sum(1 for r in merged if query["id"] in r["queries"]),
        }
    report_path = out / "harvest-report.json"
    summary = {
        "formatVersion": 1,
        "started": started,
        "finished": utc_now(),
        "queriesFile": str(queries_path.name),
        "sources": report,
        "perQuery": per_query,
        "rawRecords": len(records),
        "mergedRecords": len(merged),
        "withDoi": sum(1 for r in merged if r["doi"]),
        "withoutDoi": sum(1 for r in merged if not r["doi"]),
        "nearDuplicateTitles": near_duplicates,
        "byYear": {str(year): sum(1 for r in merged if r["year"] == str(year))
                   for year in sorted({r["year"] for r in merged if r["year"]}, reverse=True)[:15]},
        "byType": {kind: sum(1 for r in merged if r["type"] == kind)
                   for kind in sorted({r["type"] for r in merged})},
        "outputs": {
            bib_path.name: {"bytes": bib_path.stat().st_size, "sha256": sha256(bib_path)},
            index_path.name: {"bytes": index_path.stat().st_size, "sha256": sha256(index_path)},
        },
        "bibCheck": bib_check,
        "readingStatus": "none read; doc 03 curated core remains the cited set",
    }
    report_path.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: summary[key] for key in
                      ("rawRecords", "mergedRecords", "withDoi", "withoutDoi")}, indent=2))
    for entry in report:
        print(f"{entry['source']}/{entry['query']}: pages={entry['pages']} "
              f"fetched={entry['fetched']} total={entry['totalReported']} "
              f"error={entry['error']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
