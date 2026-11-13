#!/usr/bin/env python3
"""Grade the data.nasa.gov triage queues (doc 05 §3, issue #32).

Input:  data/snapshots/registry-probes/<date>/ckan-queues.json  (written by
        scripts/registry_probe.py)
Output: data/catalog/triage/ckan-triage-<date>.csv  (one row per unique record)
        data/catalog/triage/README.md               (method + counts; generated)

This is a RULE-BASED PRE-GRADE, not expert review. Every grade carries the rule
that fired, so a reviewer can overturn rules rather than individual guesses.
Grades:
  candidate-data   Moon/Mars/Earth-analog surface data product touching one of
                   our dimensions -> worth resolving to its archive and probing
                   for a registry row.
  reference        Documents, lab/simulant/biology studies, mission
                   releases-as-bundles: literature or context for W4/W12, not a
                   global data layer.
  low-level        Raw / calibrated / scene-level instrument records (EDR, PDS
                   level 1-3, SAR scenes): the registry uses the derived product.
  off-topic        Matched the query keyword for an unrelated reason (e.g.
                   THEMIS-ARTEMIS heliophysics, atmospheric-chemistry campaigns,
                   other bodies).
  unclear          No rule fired; needs a human look.
Usage: python3 scripts/triage_ckan.py [<date>]
"""
from __future__ import annotations

import collections
import csv
import json
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]

BODY = [  # first match wins
    ("moon", r"\b(moon|lunar|lro|lola|lroc|diviner|dlre|lamp|lend|mini-?rf|apollo|clementine|kaguya|selene|chandrayaan|m3|lunar prospector|artemis program)\b"),
    ("mars", r"\b(mars|martian|mgs|mro|mola|hirise|ctx|crism|themis(?!-artemis)|tes|odyssey|mex|phoenix|curiosity|msl|perseverance|insight|viking|pathfinder|jezero|gale)\b"),
    ("other-body", r"\b(venus|mercury|messenger|jupiter|saturn|titan|europa|enceladus|asteroid|comet|67p|rosetta|vesta|ceres|pluto|bennu|ryugu|io\b|ganymede|callisto|phobos|deimos)\b"),
    ("earth", r"\b(earth|terrestrial|arctic|antarctic|alaska|permafrost|tundra|siberia|greenland|canada|soil|glacier|landsat|modis|aster|srtm|airborne|field campaign)\b"),
]
RULES = [  # (grade, rule-id, regex on title+name); first match wins
    ("off-topic", "heliophysics-artemis", r"themis-artemis|artemis-p[12]|\bartemis p[12]\b|magnetic ?field|plasma|solar wind|magnetosph"),
    ("reference", "radiation-instrument-crater", r"lro moon crater|cosmic ray telescope"),  # CRaTER, not craters; radiation = permanent mismatch
    ("off-topic", "other-body", r"\b(venus|mercury|messenger|jupiter|saturn|titan|europa|enceladus|asteroid|comet|67p|rosetta|vesta|ceres|pluto|bennu|ryugu|ganymede|callisto)\b"),
    ("off-topic", "engineering-non-site", r"\b(circuit|electronic|amplifier|converter|asic|fpga|battery|engine|turbine|combustion|wind tunnel)\b"),
    ("off-topic", "atmospheric-chemistry-campaign", r"\b(arctas|carve|tarfox|owlets|radiosonde|sun photometer|trace gas|aerosol|methane|ch4|co2|ozone|fluxe?s?|airborne flasks|hsrl|dial\b|meteorite landings)"),
    ("off-topic", "ecology-or-social", r"\b(vegetation|biomass|forest|fire history|burned|subsistence|oral history|knowledge exchange|footprint files|experiment plan|shorelines|gas seepage)\b"),
    ("low-level", "raw-or-calibrated-record", r"\b(laser ranging|calibrated reduced data record|calibrated rdr|edr|raw|level 0|level 1(\.\d)?|calibrated radiance|radr|pedr|precision experiment|aggregated experiment|radiometry data|tracking data|single look complex|ground range detected|polsar|stokes|metadata|packetized|telemetry|[123] (rdr|cdr|cal))\b"),
    ("reference", "impact-experiment-lcross", r"\blcross\b"),
    ("reference", "catalogue-or-portal", r"\b(gazetteer|mapbook|gcmd|master directory|photo gallery|presentations?|human robotic systems|hrs\b|apxs targets|sample catalog|field photos)"),
    ("reference", "in-situ-surface-measurement", r"\b(apollo|alsep|moessbauer|apxs|traverse gravimeter|surface electrical properties|heat flow)\b"),
    ("reference", "archive-release-or-portal", r"pds lunar reconnaissance orbiter data \d|photojournal|\bceos\b|directory portal|panoramas"),
    ("reference", "lab-or-biology", r"\b(simulant|transcriptom|plant|arabidopsis|microb|bacteri|organism|gene|protein|rodent|mice|cell culture|biofilm|astronaut|crew)\b"),
    ("reference", "document-or-release", r"\b(report|workshop|proceedings|abstract|paper|thesis|release \d+|data release|data delivery|handbook|user'?s guide)\b"),
    ("candidate-data", "surface-product", r"\b(dem|dtm|topograph\w*|altimet\w*|elevation|slope|roughness|gdr|megdr|mosaic|maps?|gridded|thermal inertia|albedo|temperature|mineral\w*|spectra|reflectance|emissivity|neutron|gamma|hydrogen|ice|frost|radar|craters?|rocks?|boulders?|regolith|cumulative products?|resource product|shape model)\b"),
    ("candidate-data", "earth-sar-product", r"radiometric terrain corrected"),
    ("candidate-data", "earth-cryosphere-product", r"\b(permafrost|active layer|ground ice|boreholes?|ground temperature|frozen ground|soil temperature|thaw depths?|thaw slump|thermokarst|soil characteristics|pedons|soil database|soils data|snow depth|freezing and thawing indices|geocryolog\w*|soil matric)\b"),
]


def grade(rec: dict) -> tuple[str, str, str]:
    text = f"{rec.get('title') or ''} {rec.get('name') or ''}".lower()
    body = next((b for b, rx in BODY if re.search(rx, text)), "unknown")
    for g, rid, rx in RULES:
        if re.search(rx, text):
            return g, rid, body
    return "unclear", "no-rule", body


def main() -> int:
    snaps = sorted((ROOT / "data/snapshots/registry-probes").glob("*/ckan-queues.json"))
    if len(sys.argv) > 1:
        snaps = [ROOT / f"data/snapshots/registry-probes/{sys.argv[1]}/ckan-queues.json"]
    src = snaps[-1]
    day = src.parent.name
    q = json.loads(src.read_text())
    recs: dict[str, dict] = {}
    for qname, v in q["queues"].items():
        for r in v.get("records", []):
            e = recs.setdefault(r["name"], {**r, "queues": []})
            e["queues"].append(qname)
    out_dir = ROOT / "data/catalog/triage"
    out_dir.mkdir(parents=True, exist_ok=True)
    rows = []
    for name in sorted(recs):
        r = recs[name]
        g, rid, body = grade(r)
        rows.append({"name": name, "title": (r.get("title") or "").strip(), "queues": ";".join(r["queues"]),
                     "grade": g, "rule": rid, "body": body, "license_id": r.get("license_id"),
                     "identifier": r.get("identifier"), "harvest_source": r.get("harvest_source"),
                     "first_resource": r.get("first_resource")})
    out = out_dir / f"ckan-triage-{day}.csv"
    with out.open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    by = collections.Counter(r["grade"] for r in rows)
    by_rule = collections.Counter((r["grade"], r["rule"]) for r in rows)
    by_body = collections.Counter((r["grade"], r["body"]) for r in rows)
    total_rows = sum(len(v.get("records", [])) for v in q["queues"].values())
    lines = [f"# data.nasa.gov triage (generated by `scripts/triage_ckan.py` from `{src.relative_to(ROOT)}`; do not hand-edit)", "",
             f"Queues (doc 05 §3): " + ", ".join(f"{k} {v.get('count')}" for k, v in q["queues"].items())
             + f". {total_rows} queue rows = **{len(rows)} unique records** (records appear in several queues).", "",
             "**Method:** rule-based pre-grade on title + CKAN name (rules listed in the script, first match wins). "
             "Not expert review. A `candidate-data` grade means \"worth resolving to its archive and probing\", "
             "never \"adopted\". Override a grade by changing a rule, not by editing the CSV.", "",
             "| Grade | Records |", "|---|---:|"] + [f"| {g} | {n} |" for g, n in by.most_common()] + [
             "", "| Grade | Rule | Records |", "|---|---|---:|"] + [f"| {g} | `{r}` | {n} |" for (g, r), n in sorted(by_rule.items())] + [
             "", "| Grade | Body | Records |", "|---|---|---:|"] + [f"| {g} | {b} | {n} |" for (g, b), n in sorted(by_body.items())]
    (out_dir / "README.md").write_text("\n".join(lines) + "\n")
    print(f"{len(rows)} unique records -> {out.relative_to(ROOT)}; " + ", ".join(f"{g} {n}" for g, n in by.most_common()))
    return 0


if __name__ == "__main__":
    sys.exit(main())
