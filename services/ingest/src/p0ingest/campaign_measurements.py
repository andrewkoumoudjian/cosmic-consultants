"""Extract reported ARADS test results from its hashed article (#74).

No inference of site suitability or engineering requirements. Native units,
verbatim source passage and its character offsets accompany every result.
Run: python -m p0ingest.campaign_measurements
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone

import polars as pl
import yaml

from .snapshots import REPO, SNAP, sha256


def extract_arads(text: str) -> list[dict]:
    pattern = (r"The deepest sample that was acquired with fully remote operations required "
               r"(?P<cycles>\d+) command cycles to drill to (?P<depth>\d+)\s*cm depth "
               r"with sample collection and delivery to (?P<instruments>\d+) instruments\.")
    matches = list(re.finditer(pattern, text))
    dates = list(re.finditer(r"Our field work was performed in September (?P<year>\d{4})", text))
    if len(matches) != 1 or len(dates) != 1:
        raise ValueError("ARADS result/date passage is absent or ambiguous; review the source")
    match = matches[0]
    common = {"campaign_id": "atacama-arads-2019", "test": "deepest fully remote sample acquisition and delivery",
              "evidence_role": "achieved result", "is_universal_requirement": False,
              "test_date_year": int(dates[0]["year"]), "test_date_month": 9, "test_date_day": None,
              "time_evidence_quote": dates[0].group(0), "quote": match.group(0),
              "source_char_start": match.start(), "source_char_end": match.end(),
              "unknown_in_this_extraction": ["test-day weather", "grain-size distribution", "soil bearing strength", "shear strength", "depth-specific sample result"]}
    return [{**common, "quantity": quantity, "value": int(match[group]), "unit": unit}
            for group, quantity, unit in [("cycles", "command cycles", "command cycles"),
                                           ("depth", "achieved drilling depth", "cm"),
                                           ("instruments", "sample delivery instrument count", "instruments")]]


def main():
    campaign_path = REPO / "data/campaigns/atacama-arads-2019.yaml"
    campaign = yaml.safe_load(campaign_path.read_text())
    source = next(s for s in campaign["sources"] if s["ref"] == "arads-2019-article")
    path = REPO / source["localPath"]
    if sha256(path) != source["sha256"]:
        raise ValueError("ARADS raw article hash differs from campaign source record")
    rows = extract_arads(path.read_text())
    for row in rows:
        row.update({"source_url": source["url"], "source_sha256": source["sha256"],
                    "source_path": source["localPath"], "source_license_note": source["licenceNote"],
                    "site": campaign["site"]["name"], "scientific_status": "executed-unreviewed"})
    out = SNAP / "_derived/campaign-measurements"
    out.mkdir(parents=True, exist_ok=True)
    output = out / "arads-2019-results.parquet"
    pl.DataFrame(rows).write_parquet(output, compression="zstd")
    report = {"generatedAt": datetime.now(timezone.utc).isoformat(), "rows": len(rows),
              "input": source, "campaign_metadata_sha256": sha256(campaign_path),
              "output": {"path": str(output.relative_to(REPO)), "sha256": sha256(output), "bytes": output.stat().st_size},
              "checks": {"source_hash": True, "unique_result_passage": True, "unique_month_year_passage": True,
                         "all_exact_quote_spans": all(path.read_text()[r["source_char_start"]:r["source_char_end"]] == r["quote"] for r in rows)},
              "limitations": "One reported Earth analog test result; not in-situ lunar/Martian measurements, universal limits, complete campaign conditions or independent validation."}
    (out / "extraction-report.json").write_text(json.dumps(report, indent=2) + "\n")
    print(f"PASS ARADS: {len(rows)} sourced quantities; input hash and exact source spans; output {sha256(output)}")


if __name__ == "__main__":
    main()
