"""Count the cleaning rules actually used, without changing source values.

Output null counts are never substituted for unavailable input filter counts.
Historical streaming gaps and unapplied filters stay explicit. Run standalone
with `python -m p0ingest.clean_audit`, before/alongside the assembler.
"""
from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path

import numpy as np
import polars as pl
from pyhdf.SD import SD, SDC
import yaml

from .grid import DERIVED
from .snapshots import REPO, load_manifest, sha256


def mask_counts(values, invalid):
    mask = invalid(values)
    return {"inputValues": int(values.size), "maskedInputValues": int(np.count_nonzero(mask)),
            "retainedInputValues": int(values.size - np.count_nonzero(mask))}


def output_counts(frame, columns):
    return {"outputRows": frame.height, "maskedInputValues": None,
            "columns": {c: {"nullOutputRows": frame[c].null_count(), "nonNullOutputRows": frame.height - frame[c].null_count()} for c in columns}}


def build():
    registry = REPO / "data/pipeline/columns.yaml"
    reg = yaml.safe_load(registry.read_text())
    report = {"generatedAt": datetime.now(timezone.utc).isoformat(), "registrySha256": sha256(registry),
              "runtimeStatus": "executed", "scientificStatus": "partial / executed-unreviewed",
              "meaning": "Diagnostic counts only; source filters and scientific validity are not established by output null counts.",
              "rules": {}, "inputs": {}, "rawReplays": [], "warnings": []}
    applications = {}
    for table in reg["tables"].values():
        for column in table.get("columns", []):
            if column.get("status") != "active": continue
            sid, name = column["from"].split(".", 1)
            applications.setdefault(sid, set()).add(name)
            for rule in column["clean"]:
                report["rules"].setdefault(rule, {"applications": [], "maskedInputValues": None})["applications"].append({"source": sid, "column": name})
    for sid, columns in applications.items():
        path = DERIVED / reg["sources"][sid]["path"]
        frame = pl.read_parquet(path, columns=sorted(columns))
        report["inputs"][sid] = {"path": str(path.relative_to(REPO)), "sha256": sha256(path), **output_counts(frame, sorted(columns))}
    entries = load_manifest()["entries"]
    def verified(entry):
        path = REPO / entry["localPath"]
        if not path.exists() or sha256(path) != entry["sha256"]:
            raise ValueError(f"missing or changed raw input: {entry['localPath']}")
        return path
    # Replay the exact threshold and scale rules currently used by read_lst.
    lst = [e for e in entries if e.get("datasetId") == "modis-mod11c3" and ".A2023" in e.get("localPath", "")]
    for entry in lst:
        sd = SD(str(verified(entry)), SDC.READ)
        for band in ("LST_Day_CMG", "LST_Night_CMG"):
            values = sd.select(band)[:]
            report["rawReplays"].append({"rule": "lst-fill", "source": entry["localPath"], "sha256": entry["sha256"],
                "band": band, "grain": "native global CMG pixel value", "actualRule": "raw < 7500 masked; remaining values multiplied by 0.02 K",
                **mask_counts(values, lambda x: x < 7500), "qcBitFiltering": "not applied by current builder"})
        sd.end()
    if len(lst) != 12: raise ValueError("cleaning replay needs the twelve 2023 LST inputs")
    report["rules"]["lst-fill"]["maskedInputValues"] = sum(r["maskedInputValues"] for r in report["rawReplays"])
    report["rules"]["lst-scale"]["scaledInputValues"] = sum(r["retainedInputValues"] for r in report["rawReplays"])
    monthly = pl.read_parquet(DERIVED / "cells-r4-monthly.parquet", columns=["missing_reason"])
    reason = monthly["missing_reason"]
    report["rules"]["lst-coverage-25pct"]["rejectedCellMonthsBySide"] = {
        side: int(reason.str.contains(side + ":too-few-lst-pixels", literal=True).sum()) for side in ["day", "night"]}
    report["rules"]["lst-coverage-25pct"]["grain"] = "cell-month-side; day/night counts can overlap"
    landcover = next(e for e in entries if e.get("datasetId") == "modis-mcd12c1")
    sd = SD(str(verified(landcover)), SDC.READ)
    for band, layer in [("barren_pct", 16), ("snow_ice_pct", 15), ("water_pct", 0)]:
        values = sd.select("Land_Cover_Type_1_Percent")[:, :, layer]
        report["rawReplays"].append({"rule": "mcd12c1-shares", "source": landcover["localPath"], "sha256": landcover["sha256"],
            "band": band, "grain": "native global CMG pixel value", "actualRule": "raw > 100 masked", **mask_counts(values, lambda x: x > 100)})
    sd.end()
    report["rules"]["mcd12c1-shares"]["maskedInputValues"] = sum(r["maskedInputValues"] for r in report["rawReplays"] if r["rule"] == "mcd12c1-shares")
    # The legacy rule name was wrong: grid.land_percent uses January MOD11C3.
    january = next(e for e in lst if ".A2023001." in e["localPath"])
    sd = SD(str(REPO / january["localPath"]), SDC.READ)
    values = sd.select("Percent_land_in_grid")[:]
    report["rules"]["mod11c3-land-share"].update({"source": january["localPath"], "sha256": january["sha256"],
        "grain": "native CMG pixels for land-mask selection", **mask_counts(values, lambda x: x <= 0)})
    sd.end()
    # Domain/null counts describe outputs; native fill counts require source replay.
    cells = pl.read_parquet(DERIVED / "cells-r4.parquet", columns=["lat", "permafrost_pct"])
    in_domain = ((pl.col("lat").is_between(25, 85)) | (pl.col("lat").is_between(-85, -60)))
    report["rules"]["outside-model-null"]["outputRowsOutsideModel"] = cells.filter(~in_domain).height
    report["rules"]["esa-cci-fill-255"]["status"] = "output-counts-only; native raw >100 mask count not recorded in original builder"
    report["rules"]["dem-unmasked-source"].update({"status": "quality-gap", "appliedNodataFilterCount": 0,
        "invalidInputValues": None, "reason": "terrain._read_tile reads unmasked arrays; original ledger has array hashes/shapes but no nodata rejection counts. Needs a separate source audit/rebuild."})
    report["warnings"].append("DEM nodata filtering was claimed by old column metadata but is not applied by the current terrain builder; values remain unchanged and scientifically unreviewed.")
    report["warnings"].append("MOD11C3 QC-bit filtering is not applied; replay counts the actual raw-value threshold, not an invented QA pass.")
    for rule in ["raster-nodata", "pixel-centre-in-hexagon"]:
        report["rules"][rule]["status"] = "output-counts-only; original source pixel filter/assignment counts unavailable"
    for rule in ["paved-open-runways-only", "eonet-dedupe-per-event", "within-50km"]:
        report["rules"][rule]["status"] = "recorded source-build counts; no independent geographic validation in this audit"
    context_path = DERIVED / "context-r4.meta.json"
    context = json.loads(context_path.read_text())
    report["inputs"]["context-metadata"] = {"path": str(context_path.relative_to(REPO)), "sha256": sha256(context_path)}
    report["rules"]["paved-open-runways-only"]["recordedAirportCountUsed"] = context["airportCountUsed"]
    for rule in ["eonet-dedupe-per-event", "within-50km"]:
        report["rules"][rule]["recordedCounts"] = context["eonetEvents"]
    report["rules"]["licence-restricted-null"]["withheldCellRows"] = report["inputs"]["context-r4"]["columns"]["protected_pct"]["nullOutputRows"]
    report["completeInputFilterAccounting"] = False
    out = DERIVED / "assembled/cleaning-report.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2) + "\n")
    print(f"Cleaning report: {len(report['rules'])} active rules; {len(report['rawReplays'])} raw threshold replays; historical count/QA gaps explicit")
    return report


if __name__ == "__main__":
    build()
