"""Count the cleaning rules actually used, without changing source values.

Output null counts are never substituted for unavailable input filter counts.
Historical streaming gaps and unapplied filters stay explicit. Run standalone
with `python -m p0ingest.clean_audit`, before/alongside the assembler.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys

import numpy as np
import polars as pl
from pyhdf.SD import SD, SDC
import yaml

from .grid import DERIVED
from .snapshots import CATALOG, REPO, load_manifest, sha256
from .source_qa import (
    audit_terrain_ledger,
    decode_mod11c3_qc,
    load_verified_mod11c3_receipt,
    replay_mod11c3,
    replay_permafrost,
    replay_travel_time,
    resolve_snapshots_root,
    verified_manifest_file,
    verify_catalog_licenses,
)

DEFAULT_MOD11C3_RECEIPT = REPO / "docs" / "qa" / "source-qa-76" / "mod11c3-qa-replay.json"


def mask_counts(values, invalid):
    mask = invalid(values)
    n_bad = int(np.count_nonzero(mask))
    return {"inputValues": int(values.size), "maskedInputValues": n_bad,
            "retainedInputValues": int(values.size - n_bad)}


def output_counts(frame, columns):
    return {"outputRows": frame.height, "maskedInputValues": None,
            "columns": {c: {"nullOutputRows": frame[c].null_count(), "nonNullOutputRows": frame.height - frame[c].null_count()} for c in columns}}


def _read_meta(path: Path) -> dict | None:
    if not path.is_file():
        return None
    doc = json.loads(path.read_text(encoding="utf-8"))
    doc["_metaSha256"] = sha256(path)
    return doc


def build(
    snapshots_dir: Path | None = None,
    *,
    out_path: Path | None = None,
    full_modis_replay: bool = False,
    mod11c3_receipt_path: Path = DEFAULT_MOD11C3_RECEIPT,
) -> dict:
    sroot = resolve_snapshots_root(snapshots_dir)
    der = sroot / "_derived"
    registry = REPO / "data/pipeline/columns.yaml"
    qa_policy = REPO / "data/pipeline/qa-policy.yaml"
    reg = yaml.safe_load(registry.read_text(encoding="utf-8"))
    policy_doc = yaml.safe_load(qa_policy.read_text(encoding="utf-8")) if qa_policy.is_file() else {}
    licenses = verify_catalog_licenses(
        [
            "copernicus-dem-glo30",
            "modis-mod11c3",
            "modis-myd11c3",
            "modis-mcd12c1",
            "esa-cci-permafrost-extent-nh",
            "esa-cci-permafrost-extent-antarctica",
            "travel-time-to-cities-2015",
        ],
        catalog_dir=CATALOG,
    )

    report = {
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "registrySha256": sha256(registry),
        "qaPolicy": {
            "path": str(qa_policy.relative_to(REPO)) if qa_policy.is_file() else None,
            "sha256": sha256(qa_policy) if qa_policy.is_file() else None,
            "status": policy_doc.get("status", "missing"),
            "followupIssue": 76,
        },
        "licenses": licenses,
        "runtimeStatus": "executed",
        "scientificStatus": "partial / executed-unreviewed",
        "meaning": "Diagnostic counts only; source filters and scientific validity are not established by output null counts.",
        "rules": {},
        "inputs": {},
        "rawReplays": [],
        "warnings": [],
    }

    applications: dict[str, set[str]] = {}
    for table in reg["tables"].values():
        for column in table.get("columns", []):
            if column.get("status") != "active":
                continue
            sid, name = column["from"].split(".", 1)
            applications.setdefault(sid, set()).add(name)
            for rule in column["clean"]:
                report["rules"].setdefault(rule, {"applications": [], "maskedInputValues": None})["applications"].append(
                    {"source": sid, "column": name}
                )
    for sid, columns in applications.items():
        path = der / reg["sources"][sid]["path"]
        frame = pl.read_parquet(path, columns=sorted(columns))
        report["inputs"][sid] = {"path": f"data/snapshots/_derived/{reg['sources'][sid]['path']}", "sha256": sha256(path), **output_counts(frame, sorted(columns))}

    entries = load_manifest()["entries"]

    # 1. Replay exact threshold, scale, and QC-bit audit on 2023 MOD11C3 granules (L1/L1m).
    lst = sorted(
        [e for e in entries if e.get("datasetId") == "modis-mod11c3" and ".A2023" in e.get("localPath", "")],
        key=lambda e: e["localPath"],
    )
    if len(lst) != 12:
        raise ValueError("cleaning replay needs the twelve 2023 LST inputs")

    qc_err_sum = {"Day": [0, 0, 0, 0], "Night": [0, 0, 0, 0]}
    qc_mand_sum = {"Day": [0, 0, 0, 0], "Night": [0, 0, 0, 0]}
    qc_anomalies = 0
    for entry in lst:
        sd = SD(str(verified_manifest_file(entry, REPO, sroot)), SDC.READ)
        try:
            for side, band, qband in (("Day", "LST_Day_CMG", "QC_Day"), ("Night", "LST_Night_CMG", "QC_Night")):
                values = sd.select(band)[:]
                qc = sd.select(qband)[:]
                valid = values >= 7500
                fields = decode_mod11c3_qc(qc)
                qc_anomalies += int(np.count_nonzero(valid & (fields["mand_qa"] >= 2)))
                qc_anomalies += int(np.count_nonzero((~valid) & (fields["mand_qa"] <= 1)))
                qc_mand_sum[side] = [a + int(b) for a, b in zip(qc_mand_sum[side], np.bincount(fields["mand_qa"].ravel(), minlength=4))]
                qc_err_sum[side] = [a + int(b) for a, b in zip(qc_err_sum[side], np.bincount(fields["lst_err"][valid], minlength=4))]
                report["rawReplays"].append({
                    "rule": "lst-fill",
                    "source": entry["localPath"],
                    "sha256": entry["sha256"],
                    "band": band,
                    "grain": "native global CMG pixel value",
                    "actualRule": "raw < 7500 masked; remaining values multiplied by 0.02 K",
                    **mask_counts(values, lambda x: x < 7500),
                    "qcBitFiltering": "not applied by current builder; audited via QC_Day/QC_Night",
                })
        finally:
            sd.end()

    report["rules"]["lst-fill"]["maskedInputValues"] = sum(r["maskedInputValues"] for r in report["rawReplays"] if r["rule"] == "lst-fill")
    report["rules"]["lst-fill"]["qcAudit2023"] = {
        "mandatoryQaAllPixels": qc_mand_sum,
        "lstErrorOnValid": qc_err_sum,
        "rawVsMandQaAnomalies": qc_anomalies,
    }
    report["rules"]["lst-scale"]["scaledInputValues"] = sum(r["retainedInputValues"] for r in report["rawReplays"] if r["rule"] == "lst-fill")

    # 1b. Full 120-granule (2014-2023) MOD11C3 QA replay (verified against all 120 manifest SHA256s).
    modis_full = None if full_modis_replay else load_verified_mod11c3_receipt(
        mod11c3_receipt_path, entries, repo_root=REPO, snapshots_root=sroot
    )
    if modis_full is None:
        modis_full = replay_mod11c3(entries, repo_root=REPO, snapshots_root=sroot, catalog_dir=CATALOG)
    report["mod11c3FullReplay"] = {
        "granuleCount": modis_full["granuleCount"],
        "granuleCount2023": modis_full["granuleCount2023"],
        "minPixelShare": modis_full["minPixelShare"],
        "sides": modis_full["sides"],
        "receiptSha256": sha256(mod11c3_receipt_path) if mod11c3_receipt_path.is_file() else None,
    }

    monthly = pl.read_parquet(der / "cells-r4-monthly.parquet", columns=["missing_reason"])
    reason = monthly["missing_reason"]
    report["rules"]["lst-coverage-25pct"]["rejectedCellMonthsBySide"] = {
        side: int(reason.str.contains(side + ":too-few-lst-pixels", literal=True).sum()) for side in ["day", "night"]
    }
    report["rules"]["lst-coverage-25pct"]["grain"] = "cell-month-side; day/night counts can overlap"

    # 2. MCD12C1 land-cover shares
    landcover = next(e for e in entries if e.get("datasetId") == "modis-mcd12c1")
    sd = SD(str(verified_manifest_file(landcover, REPO, sroot)), SDC.READ)
    try:
        for band, layer in [("barren_pct", 16), ("snow_ice_pct", 15), ("water_pct", 0)]:
            values = sd.select("Land_Cover_Type_1_Percent")[:, :, layer]
            report["rawReplays"].append({
                "rule": "mcd12c1-shares",
                "source": landcover["localPath"],
                "sha256": landcover["sha256"],
                "band": band,
                "grain": "native global CMG pixel value",
                "actualRule": "raw > 100 masked",
                **mask_counts(values, lambda x: x > 100),
            })
    finally:
        sd.end()
    report["rules"]["mcd12c1-shares"]["maskedInputValues"] = sum(
        r["maskedInputValues"] for r in report["rawReplays"] if r["rule"] == "mcd12c1-shares"
    )

    # 3. MOD11C3 January 2023 Percent_land_in_grid mask
    january = next(e for e in lst if ".A2023001." in e["localPath"])
    sd = SD(str(verified_manifest_file(january, REPO, sroot)), SDC.READ)
    try:
        values = sd.select("Percent_land_in_grid")[:]
        report["rules"]["mod11c3-land-share"].update({
            "source": january["localPath"],
            "sha256": january["sha256"],
            "grain": "native CMG pixels for land-mask selection",
            **mask_counts(values, lambda x: x <= 0),
        })
    finally:
        sd.end()

    # 4. ESA CCI Permafrost v5.0 native fill=255 replay from pinned NetCDFs
    cells = pl.read_parquet(der / "cells-r4.parquet", columns=["lat", "permafrost_pct"])
    in_domain = (pl.col("lat").is_between(25, 85)) | (pl.col("lat").is_between(-85, -60))
    report["rules"]["outside-model-null"]["outputRowsOutsideModel"] = cells.filter(~in_domain).height
    pf_replays = replay_permafrost(entries, repo_root=REPO, snapshots_root=sroot, catalog_dir=CATALOG)
    for pf_rep in pf_replays:
        report["rawReplays"].append({"rule": "esa-cci-fill-255", **pf_rep})
    report["rules"]["esa-cci-fill-255"].update({
        "status": "replayed-from-pinned-netcdf",
        "grain": "native 0.01 deg PFR pixels (NH + Antarctica)",
        "maskedInputValues": sum(r["maskedInputValues"] for r in pf_replays),
        "retainedInputValues": sum(r["retainedInputValues"] for r in pf_replays),
        "byProduct": {r["datasetId"]: {"inputValues": r["inputValues"], "maskedInputValues": r["maskedInputValues"], "sha256": r["sha256"]} for r in pf_replays},
    })

    # 5. Travel Time to Cities 2015 native nodata replay from pinned ZIP
    tt_rep = replay_travel_time(entries, repo_root=REPO, snapshots_root=sroot, catalog_dir=CATALOG)
    report["rawReplays"].append({"rule": "raster-nodata", **tt_rep})
    report["rules"]["raster-nodata"].update({
        "status": "replayed-from-pinned-geotiff",
        "grain": "native 30 arcsec travel-time raster pixels",
        "inputValues": tt_rep["inputValues"],
        "maskedInputValues": tt_rep["maskedInputValues"],
        "retainedInputValues": tt_rep["retainedInputValues"],
        "nodataValue": tt_rep["nodataValue"],
    })
    report["rules"]["pixel-centre-in-hexagon"]["status"] = (
        "output-counts-only; polygon rasterization pixel-assignment log not emitted by context.py"
    )

    # 6. Copernicus GLO-30 historical ledger audit (preserve unmasked status; never fabricate counts)
    dem_audit = audit_terrain_ledger(
        sroot / "copernicus-dem-glo30" / "tileList.txt",
        der / "terrain-r4-ledger.jsonl.gz",
        cells_parquet=der / "cells-r4.parquet",
        terrain_npz=der / "terrain-r4.npz",
    )
    report["rules"]["dem-unmasked-source"].update({
        "status": "quality-gap" if not dem_audit["waterMasked"] else "wbm-edm-masked",
        "reason": "terrain._read_tile reads unmasked arrays; historical ledger has 26,450 arraySha256 digests and 0 nodata/water rejections. Policy proposed in ADR-0015 prior to rebuild.",
        **dem_audit,
    })

    # 7. Context metadata + other family builder metadata
    for rule in ["paved-open-runways-only", "eonet-dedupe-per-event", "within-50km"]:
        report["rules"][rule]["status"] = "recorded source-build counts; no independent geographic validation in this audit"
    context_meta = _read_meta(der / "context-r4.meta.json")
    if context_meta:
        report["inputs"]["context-metadata"] = {"path": "data/snapshots/_derived/context-r4.meta.json", "sha256": context_meta["_metaSha256"]}
        report["rules"]["paved-open-runways-only"]["recordedAirportCountUsed"] = context_meta["airportCountUsed"]
        for rule in ["eonet-dedupe-per-event", "within-50km"]:
            report["rules"][rule]["recordedCounts"] = context_meta["eonetEvents"]
    report["rules"]["licence-restricted-null"]["withheldCellRows"] = report["inputs"]["context-r4"]["columns"]["protected_pct"]["nullOutputRows"]

    vcf_meta = _read_meta(der / "vcf-r4.meta.json")
    if vcf_meta and "computed" in vcf_meta and "nativePixelCodes" in vcf_meta["computed"]:
        npc = vcf_meta["computed"]["nativePixelCodes"]["percent_tree_cover"]
        report["inputs"]["vcf-metadata"] = {"path": "data/snapshots/_derived/vcf-r4.meta.json", "sha256": vcf_meta["_metaSha256"]}
        report["rules"]["mod44b-exclude-water-200-fill-253"].update({
            "status": "recorded-builder-native-counts",
            "maskedInputValues": int(npc["water"] + npc["fill"] + npc["other"]),
            "recordedBreakdown": npc,
        })
        report["rules"]["mod44b-valid-0-100"].update({
            "status": "recorded-builder-native-counts",
            "retainedInputValues": int(npc["valid"]),
        })

    reg_meta = _read_meta(der / "regolith-r4.meta.json")
    if reg_meta and "computed" in reg_meta:
        report["inputs"]["regolith-metadata"] = {"path": "data/snapshots/_derived/regolith-r4.meta.json", "sha256": reg_meta["_metaSha256"]}
        for rname in ("ornl-nodata", "published-range-0-50m", "published-range-0-4.2m"):
            if rname in report["rules"]:
                report["rules"][rname].update({
                    "status": "builder-diagnostics-only; raw input ZIPs absent locally",
                    "recordedDiagnostics": reg_meta["computed"],
                })

    dust_meta = _read_meta(der / "dust-r4.meta.json")
    if dust_meta:
        report["inputs"]["dust-metadata"] = {"path": "data/snapshots/_derived/dust-r4.meta.json", "sha256": dust_meta["_metaSha256"]}
        report["rules"]["merra2-fill"].update({
            "status": "recorded-builder-native-fill-counts",
            "recordedDustNativeFillCellsByMonth": dust_meta.get("nativeFillCellsByMonth"),
        })

    wind_meta = _read_meta(der / "wind-r4.meta.json")
    if wind_meta:
        report["inputs"]["wind-metadata"] = {"path": "data/snapshots/_derived/wind-r4.meta.json", "sha256": wind_meta["_metaSha256"]}
        report["rules"]["merra2-fill"]["recordedWindNativeFillCellsByGranule"] = wind_meta.get("nativeFillCellsByGranule")

    burned_meta = _read_meta(der / "burned-r4-monthly.meta.json")
    if burned_meta:
        report["inputs"]["burned-metadata"] = {"path": "data/snapshots/_derived/burned-r4-monthly.meta.json", "sha256": burned_meta["_metaSha256"]}
        for rname in ("mcd64-unmapped", "mcd64-water", "mapped-years-only"):
            report["rules"][rname].update({
                "status": "recorded-builder-qa-and-reason-counts",
                "recordedQa": burned_meta.get("qa"),
            })

    emit_meta = _read_meta(der / "emit-min/emit-min-r4.meta.json")
    if emit_meta:
        report["inputs"]["emit-metadata"] = {"path": "data/snapshots/_derived/emit-min/emit-min-r4.meta.json", "sha256": emit_meta["_metaSha256"]}
        for rname in ("emit-glt-mask", "emit-library-mineral-filter"):
            report["rules"][rname].update({
                "status": "recorded-builder-qa-sample-counts",
                "recordedQa": emit_meta.get("qa"),
            })

    aqua_meta = _read_meta(der / "aqua-lst-r4-monthly.meta.json")
    if aqua_meta:
        report["inputs"]["aqua-lst-metadata"] = {"path": "data/snapshots/_derived/aqua-lst-r4-monthly.meta.json", "sha256": aqua_meta["_metaSha256"]}
    for rname in ("myd11c3-fill", "myd11c3-scale", "myd11c3-coverage-25pct"):
        if rname in report["rules"]:
            report["rules"][rname]["status"] = "raw-snapshot-absent-locally; 12 MYD11C3 HDF4 granules in MANIFEST not present on disk"

    report["warnings"].append("DEM nodata/water filtering was claimed by old column metadata but is not applied by the current unmasked terrain builder; historical artifacts stay untouched until ADR-0015 is frozen.")
    report["warnings"].append("MOD11C3 QC-bit filtering is not applied by the current builder; replay audits all 120 granules (2014-2023) without altering derived tables.")
    report["warnings"].append("MYD11C3, MCD43C3, MERRA-2, ORNL, MOD44B, and EMIT full raw files are absent locally; no missing input counts are invented.")
    report["completeInputFilterAccounting"] = False

    out = out_path or (der / "assembled/cleaning-report.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(f"Cleaning report: {len(report['rules'])} active rules; {len(report['rawReplays'])} raw threshold replays; historical count/QA gaps explicit")
    return report


def _main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Build cleaning-report.json with deterministic raw QA replays.")
    p.add_argument("--snapshots", type=Path, default=None)
    p.add_argument("--out", type=Path, default=None)
    p.add_argument("--full-modis-replay", action="store_true")
    args = p.parse_args(argv)
    build(args.snapshots, out_path=args.out, full_modis_replay=args.full_modis_replay)
    return 0


if __name__ == "__main__":
    sys.exit(_main())
