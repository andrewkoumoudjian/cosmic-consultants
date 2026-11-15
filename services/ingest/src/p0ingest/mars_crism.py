"""Prepare source-native MRO CRISM MTRDR spectral summary-parameter maps (#105).

The PDS Geosciences MTRDR bundle (mrocr_4001, data set MRO-M-CRISM-5-RDR-
MPTARGETED-V1.0) ships every map-projected targeted scene as separate product
files. The SU files are the "SPECTRAL_SUMMARY_PARAMETERS" image products: 60
bands of the official CRISM summary parameters (band names carried in the
product label; definitions per Viviano-Beck et al. 2014 and the CRISM Data
Product SIS). This module reads those SU cubes for nine regional MTRDR scenes
around six Mars landing/valley regions, keeps the native scene grid and
coordinates, and converts only the product's own fill value (65535.0) to null.

No resampling, no H3, no thresholds, no detected/not-detected flags, no
scoring. Missing stays missing: null with a per-row JSON missing_reason.

Run: python -m p0ingest.mars_crism fetch|build|check
"""
from __future__ import annotations

import argparse
import json
import math
import re
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import polars as pl
import pyarrow.parquet as pq

from .snapshots import REPO, SNAP, fetch, load_manifest, sha256

BUNDLE = "https://pds-geosciences.wustl.edu/mro/mro-m-crism-5-rdr-mptargeted-v1/mrocr_4001/"
SNAP_DIR = SNAP / "crism-mro"
OUT = SNAP / "_derived" / "planetary" / "crism-mtrdr"
TABLE = OUT / "crism-mtrdr-summary.parquet"

BUNDLE_ID = "MRO-M-CRISM-5-RDR-MPTARGETED-V1.0"
FILL = 65535.0  # SU fill value, verified against every fetched cube at build

# Official 60-band summary-parameter set of the v3 (MTR3) SU products, in
# label band order (checked against every fetched SU label; Viviano-Beck et
# al. 2014, JGR 119 "Revised CRISM spectral parameters and summary products",
# CRISM Data Product SIS Table 3-12).
SU_BANDS = (
    "R770 RBR BD530_2 SH600_2 SH770 BD640_2 BD860_2 BD920_2 RPEAK1 BDI1000VIS "
    "R440 IRR1 BDI1000IR OLINDEX3 R1330 BD1300 LCPINDEX2 HCPINDEX2 VAR ISLOPE1 "
    "BD1400 BD1435 BD1500_2 ICER1_2 BD1750_2 BD1900_2 BD1900R2 BDI2000 BD2100_2 "
    "BD2165 BD2190 MIN2200 BD2210_2 D2200 BD2230 BD2250 MIN2250 BD2265 BD2290 "
    "D2300 BD2355 SINDEX2 ICER2_2 MIN2295_2480 MIN2345_2537 BD2500_2 BD3000 "
    "BD3100 BD3200 BD3400_2 CINDEX2 BD2600 IRR2 IRR3 R530 R600 R1080 R1506 "
    "R2529 R3920"
).split()

# Feature -> source parameter names (research/features/landing_site_features.csv,
# VIVIANO-2014 / CRISM-SIS naming kept verbatim).
FEATURE_PARAMS = {
    "crism_hydration": ["BD1900_2", "BD1900R2"],
    "crism_fe_mg_smectite": ["D2300", "BD2290"],
    "crism_al_oh": ["BD2210_2", "BD2165"],
    "crism_sulfate": ["SINDEX2", "BD2100_2"],
    "crism_carbonate": ["BD2500_2", "MIN2295_2480", "MIN2345_2537"],
    "mafic_bd_1um": ["OLINDEX3", "LCPINDEX2", "HCPINDEX2"],
}
PARAMS = sorted({p for v in FEATURE_PARAMS.values() for p in v})
assert len(PARAMS) == 14 and all(p in SU_BANDS for p in PARAMS)

# Regions: site context used to pick scenes; each scene keeps its exact
# labelled footprint. Gale: no v3 MTRDR scene in the archived 2006-2012 index
# covers the Bradbury landing site (-4.59, 137.44); the two scenes below
# bracket the lower Aeolis Mons / dune field instead (stated as a gap).
REGIONS = {
    "jezero": {"site": "Jezero crater floor + western delta (Perseverance 2021)", "anchor": (18.38, 77.58)},
    "gale": {"site": "Gale crater / Aeolis Mons lower mound and dune field (Curiosity 2012)",
             "anchor": (-5.25, 137.75),
             "gap": "Bradbury landing (-4.59, 137.44) uncovered by any archived v3 MTRDR scene"},
    "meridiani": {"site": "Meridiani Planum, Opportunity 2004 landing area", "anchor": (-1.99, -5.53)},
    "gusev": {"site": "Gusev crater floor, Spirit 2004 landing area", "anchor": (-14.57, 175.48)},
    "mawrth": {"site": "Mawrth Vallis phyllosilicate exposure (Noachian clays)", "anchor": (25.0, -19.0)},
    "nili": {"site": "Nili Fossae carbonate/phyllosilicate belt", "anchor": (21.6, 74.6)},
}

# Selected SU scenes, as published in the bundle's per-month index tables
# (mtrdr*yymm_index.tab). One scene = one static CRISM targeted observation.
SCENES = {
    "jezero": [
        "MTRDR/2007/2007_178/FRT000066A4/FRT000066A4_07_SU166J_MTR3",
        "MTRDR/2007/2007_029/HRL000040FF/HRL000040FF_07_SU183J_MTR3",
    ],
    "gale": [
        "MTRDR/2010/2010_288/FRT0001B696/FRT0001B696_07_SU165J_MTR3",
        "MTRDR/2007/2007_361/FRT0000901A/FRT0000901A_07_SU165J_MTR3",
    ],
    "meridiani": [
        "MTRDR/2006/2006_334/FRT0000334D/FRT0000334D_07_SU165J_MTR3",
    ],
    "gusev": [
        "MTRDR/2006/2006_326/FRT00003192/FRT00003192_07_SU165J_MTR3",
    ],
    "mawrth": [
        "MTRDR/2008/2008_249/FRT0000C596/FRT0000C596_07_SU166J_MTR3",
        "MTRDR/2009/2009_076/FRT000119DC/FRT000119DC_07_SU166J_MTR3",
    ],
    "nili": [
        "MTRDR/2007/2007_277/FRT0000805F/FRT0000805F_07_SU166J_MTR3",
    ],
}
SKIPPED = [
    "FRT00004F75 (Nili Fossae) skipped: 838 MB single SU cube; FRT0000805F "
    "already covers the carbonate belt",
]
GAPS = [
    "No global CRISM summary-parameter mosaic exists in PDS (checked "
    "pds-geosciences holdings 2026-11-14); the CRISM team's global MSP/MSW "
    "mosaic is published outside PDS with no licence record, so it is not "
    "used. Regional MTRDR scenes instead, listed in SCENES.",
    "Gale Bradbury landing site not covered (see REGIONS.gale).",
]

INDEX_FILES = ["aareadme.txt", "readme.txt", "errata.txt", "catalog/mtr_map.cat",
               "index/indxinfo.txt", "index/mtrdr0609_index.lbl",
               "document/crism_dpsis.pdf"]  # Data Product SIS (PDF; the .htm twin is refused as text/html)
index_tabs = """mtrdr0609 mtrdr0611 mtrdr0612 mtrdr0701 mtrdr0702 mtrdr0703 mtrdr0704 mtrdr0705
mtrdr0706 mtrdr0707 mtrdr0708 mtrdr0709 mtrdr0710 mtrdr0711 mtrdr0712 mtrdr0801
mtrdr0802 mtrdr0803 mtrdr0804 mtrdr0805 mtrdr0806 mtrdr0807 mtrdr0808 mtrdr0809
mtrdr0810 mtrdr0811 mtrdr0812 mtrdr0901 mtrdr0902 mtrdr0903 mtrdr0904 mtrdr0905
mtrdr0906 mtrdr0907 mtrdr0908 mtrdr1001 mtrdr1002 mtrdr1003 mtrdr1004 mtrdr1005
mtrdr1006 mtrdr1007 mtrdr1010 mtrdr1011 mtrdr1012 mtrdr1101 mtrdr1103 mtrdr1104
mtrdr1105 mtrdr1106 mtrdr1107 mtrdr1108 mtrdr1109 mtrdr1110 mtrdr1112 mtrdr1202
mtrdr1203 mtrdr1204 mtrdr1205""".split()
assert len(index_tabs) == 59, len(index_tabs)


def sources():
    for rel in INDEX_FILES:
        yield "crism-mro", BUNDLE + rel
    for stem in index_tabs:
        yield "crism-mro", BUNDLE + f"index/{stem}_index.tab"
    for paths in SCENES.values():
        for p in paths:
            for ext in (".LBL", ".HDR", ".IMG"):
                yield "crism-mro", BUNDLE + p + ext


# ---------------------------------------------------------------- label parse
def label_value(text: str, key: str, cast=float) -> float:
    m = re.search(rf"^\s*{key}\s*=\s*([-+0-9.eE]+)", text, re.M)
    if m is None:
        raise ValueError(f"label field {key} missing")
    return cast(m.group(1))


def parse_scene_label(path: Path) -> dict:
    text = path.read_text(errors="strict")
    if BUNDLE_ID not in text:
        raise ValueError(f"unexpected bundle in {path.name}")
    image = re.search(r"OBJECT\s*=\s*IMAGE\s*\r?\n(.*?)\r?\nEND_OBJECT\s*=\s*IMAGE", text, re.S)
    proj = re.search(r"OBJECT\s*=\s*IMAGE_MAP_PROJECTION\s*\r?\n(.*?)END_OBJECT\s*=\s*IMAGE_MAP_PROJECTION", text, re.S)
    if image is None or proj is None:
        raise ValueError(f"label missing IMAGE or IMAGE_MAP_PROJECTION: {path.name}")
    body = proj.group(1)
    names_block = re.search(r"BAND_NAME\s*=\s*\((.*?)\)", image.group(1), re.S)
    if names_block is None:
        raise ValueError(f"no BAND_NAME list in {path.name}")
    names = [n.strip().strip('"') for n in names_block.group(1).split(",") if n.strip()]
    if re.search(r"^\s*SAMPLE_TYPE\s*=\s*PC_REAL\b", image.group(1), re.M) is None:
        raise ValueError(f"SAMPLE_TYPE not PC_REAL in {path.name}")
    labels = {}
    for key in ("LINES", "LINE_SAMPLES", "BANDS", "SAMPLE_BITS"):
        labels[key] = label_value(image.group(1), key, int)
    if labels["BANDS"] != 60 or names != SU_BANDS:
        raise ValueError(f"summary band set changed in {path.name}: {labels['BANDS']} bands")
    if labels["SAMPLE_BITS"] != 32:
        raise ValueError(f"SAMPLE_BITS changed in {path.name}")

    p = {key: label_value(body, key) for key in
         ("CENTER_LATITUDE", "CENTER_LONGITUDE", "MAP_SCALE", "MAP_RESOLUTION",
          "MINIMUM_LATITUDE", "MAXIMUM_LATITUDE", "WESTERNMOST_LONGITUDE",
          "EASTERNMOST_LONGITUDE", "LINE_PROJECTION_OFFSET", "SAMPLE_PROJECTION_OFFSET",
          "A_AXIS_RADIUS")}
    for key in ("LINE_FIRST_PIXEL", "LINE_LAST_PIXEL", "SAMPLE_FIRST_PIXEL", "SAMPLE_LAST_PIXEL"):
        p[key] = label_value(body, key, int)
    p["productId"] = re.search(r'PRODUCT_ID\s*=\s*"?([^"\s]+)"?', text).group(1)
    p["observationId"] = p["productId"].split("_")[0]
    p["observationType"] = re.search(r'OBSERVATION_TYPE\s*=\s*"?(\S+?)"?\s*[\r\n]', text).group(1)
    p["startTime"] = re.search(r"START_TIME\s*=\s*(\S+)", text).group(1)
    p["stopTime"] = re.search(r"STOP_TIME\s*=\s*(\S+)", text).group(1)
    p["solarLongitude"] = label_value(text, "SOLAR_LONGITUDE")
    p["bands"] = names
    p["corrections"] = {k.split(":")[1].replace("_CORR_FLAG", "").lower(): re.search(
        rf'^{k}\s*=\s*"?(\w+)"?', text, re.M).group(1)
        for k in ("MRO:PHOTOMETRIC_CORR_FLAG", "MRO:ATMOSPHERIC_CORR_FLAG",
                  "MRO:EMPIRICAL_GEOM_NORM_FLAG", "MRO:EMPIRICAL_SMILE_CORR_FLAG")}
    if re.search(r"^\s*BAND_STORAGE_TYPE\s*=\s*BAND_SEQUENTIAL", image.group(1), re.M) is None:
        raise ValueError(f"band storage changed in {path.name}")
    return {"label": labels,
            "projection": {k: p[k] for k in (
                "CENTER_LATITUDE", "CENTER_LONGITUDE", "MAP_SCALE", "MAP_RESOLUTION",
                "MINIMUM_LATITUDE", "MAXIMUM_LATITUDE", "WESTERNMOST_LONGITUDE",
                "EASTERNMOST_LONGITUDE", "LINE_PROJECTION_OFFSET", "SAMPLE_PROJECTION_OFFSET",
                "LINE_FIRST_PIXEL", "LINE_LAST_PIXEL", "SAMPLE_FIRST_PIXEL", "SAMPLE_LAST_PIXEL",
                "A_AXIS_RADIUS")},
            "productId": p["productId"], "observationId": p["observationId"],
            "observationType": p["observationType"], "startTime": p["startTime"],
            "stopTime": p["stopTime"], "solarLongitude": p["solarLongitude"],
            "bands": p["bands"], "corrections": p["corrections"]}


def validate_geometry(meta: dict) -> dict:
    """Per-pixel lat/lon steps from the label, checked against all four corners.

    MTR_MAP.CAT defines the rolling equirectangular projection; resolving its
    LINE/SAMPLE_PROJECTION_OFFSET sign conventions reduces to a linear map on
    this scene window, which the label's own MINIMUM/MAXIMUM_LATITUDE and
    WESTERNMOST/EASTERNMOST_LONGITUDE keywords pin exactly. lat(line) =
    MAXIMUM_LATITUDE - line0 * dlat; lon(sample) = WESTERNMOST + sample0 * dlon
    (0-based pixel centres).
    """
    p = meta["projection"]
    km_per_deg_lat = p["A_AXIS_RADIUS"] * math.pi / 180.0
    km_per_deg_lon = km_per_deg_lat * math.cos(math.radians(p["CENTER_LATITUDE"]))
    dlat = p["MAP_SCALE"] / km_per_deg_lat
    dlon = p["MAP_SCALE"] / km_per_deg_lon
    lines = p["LINE_LAST_PIXEL"] - p["LINE_FIRST_PIXEL"] + 1
    samples = p["SAMPLE_LAST_PIXEL"] - p["SAMPLE_FIRST_PIXEL"] + 1
    checks = {
        "dlat_vs_corners": abs(dlat * (lines - 1) - (p["MAXIMUM_LATITUDE"] - p["MINIMUM_LATITUDE"])),
        "dlon_vs_corners": abs(dlon * (samples - 1) - (p["EASTERNMOST_LONGITUDE"] - p["WESTERNMOST_LONGITUDE"])),
    }
    if max(checks.values()) > 0.002:
        raise ValueError(f"projection corner check failed for {meta['productId']}: {checks}")
    return {"dlatPx": dlat, "dlonPx": dlon, "checks": checks, "lines": lines, "samples": samples}


def pixel_latlon(meta: dict, geom: dict) -> tuple[np.ndarray, np.ndarray]:
    """0-based pixel centres -> (lat, lon) per index line/sample (Float32)."""
    p = meta["projection"]
    lat = (p["MAXIMUM_LATITUDE"] - geom["dlatPx"] * np.arange(geom["lines"], dtype=np.float64)).astype(np.float32)
    lon = (p["WESTERNMOST_LONGITUDE"] + geom["dlonPx"] * np.arange(geom["samples"], dtype=np.float64)).astype(np.float32)
    return lat, lon


# ------------------------------------------------------------------- building
def verify_inputs() -> list[dict]:
    entries = {e["sourceUrl"]: e for e in load_manifest()["entries"]}
    checked = []
    for dataset, url in sources():
        entry = entries.get(url)
        if entry is None or entry["datasetId"] != dataset or not entry["licenseVerified"]:
            raise ValueError(f"missing licensed snapshot: {url}")
        path = REPO / entry["localPath"]
        if path.stat().st_size != entry["bytes"] or sha256(path) != entry["sha256"]:
            raise ValueError(f"input hash/size mismatch: {path}")
        checked.append(entry)
    return checked


WHOLE_FILL_REASON = "{" + ",".join(f'"{p}":"fill-{int(FILL)}"' for p in PARAMS) + "}"


def scene_frame(region: str, scene_rel: str, directory: Path = SNAP_DIR) -> tuple[pl.DataFrame, dict]:
    scene_name = Path(scene_rel).name
    lbl_path = directory / (scene_name + ".LBL")
    img_path = directory / (scene_name + ".IMG")
    meta = parse_scene_label(lbl_path)
    n_lines = meta["label"]["LINES"]
    n_samples = meta["label"]["LINE_SAMPLES"]
    n_bands = meta["label"]["BANDS"]
    if img_path.stat().st_size != n_lines * n_samples * n_bands * 4:
        raise ValueError(f"image byte count differs from label: {img_path.name}")
    geom = validate_geometry(meta)
    lat1d, lon1d = pixel_latlon(meta, geom)

    cube = np.memmap(img_path, dtype="<f4", mode="r").reshape(n_lines, n_samples, n_bands)
    band_pos = {name: i for i, name in enumerate(meta["bands"])}
    columns = {}
    null_masks = []
    for p in PARAMS:
        raw = np.asarray(cube[:, :, band_pos[p]].astype(np.float32, copy=True)).ravel()
        fill = ~np.isfinite(raw) | (raw == FILL).astype(bool)
        raw[fill] = np.float32("nan")
        series = pl.Series(raw)
        if fill.any():
            series = series.set(pl.Series(fill), None)
        columns[p] = series
        null_masks.append(fill)
    del cube

    all_same = all(m is null_masks[0] or bool((m == null_masks[0]).all()) for m in null_masks)
    reasons_obj = np.empty(n_lines * n_samples, dtype=object)
    reasons_obj[:] = "{}"
    if all_same:
        reasons_obj[null_masks[0]] = WHOLE_FILL_REASON
    else:  # partial per-parameter fill: exact per-row JSON
        for i in np.nonzero(np.any(null_masks, axis=0))[0]:
            keys = [p for p, m in zip(PARAMS, null_masks) if m[i]]
            reasons_obj[i] = "{" + ",".join(f'"{k}":"fill-{int(FILL)}"' for k in keys) + "}"

    n = n_lines * n_samples
    frame = pl.DataFrame({
        "region": pl.Series([region] * n),
        "observation_id": pl.Series([meta["observationId"]] * n),
        "product_id": pl.Series([meta["productId"]] * n),
        "source_line": pl.Series(np.tile(np.arange(n_lines, dtype=np.uint16), (n_samples, 1)).T.ravel()),
        "source_sample": pl.Series(np.tile(np.arange(n_samples, dtype=np.uint16), (n_lines, 1)).ravel()),
        "latitude": pl.Series(np.repeat(lat1d, n_samples)),
        "longitude": pl.Series(np.tile(lon1d, n_lines)),
        **{p: columns[p] for p in PARAMS},
        "missing_reason": pl.Series(list(reasons_obj)),
    })

    scene_meta = {
        "region": region,
        "scenePath": scene_rel,
        "productId": meta["productId"],
        "observationType": meta["observationType"],
        "startTime": meta["startTime"],
        "stopTime": meta["stopTime"],
        "solarLongitudeDeg": meta["solarLongitude"],
        "nativeGrid": {"lines": n_lines, "samples": n_samples, "bands": n_bands},
        "mapScaleKmPx": meta["projection"]["MAP_SCALE"],
        "mapResolutionPxPerDeg": meta["projection"]["MAP_RESOLUTION"],
        "projection": {k: meta["projection"][k] for k in (
            "CENTER_LATITUDE", "CENTER_LONGITUDE", "MINIMUM_LATITUDE", "MAXIMUM_LATITUDE",
            "WESTERNMOST_LONGITUDE", "EASTERNMOST_LONGITUDE", "LINE_PROJECTION_OFFSET",
            "SAMPLE_PROJECTION_OFFSET", "A_AXIS_RADIUS")},
        "projectionType": "EQUIRECTANGULAR (rolling, per MTR_MAP.CAT)",
        "geometryChecks": geom["checks"],
        "dlatDegPx": geom["dlatPx"],
        "dlonDegPx": geom["dlonPx"],
        "coordinateRule": "pixel centres of the scene-native equirectangular grid; "
                          "lat/lon linear from the label's own corner keywords, "
                          "validated to < 0.002 deg against all four corners "
                          "(equivalent to the MTR_MAP.CAT equations)",
        "corrections": meta["corrections"],
        "footprintLat": [meta["projection"]["MINIMUM_LATITUDE"], meta["projection"]["MAXIMUM_LATITUDE"]],
        "footprintLon": [meta["projection"]["WESTERNMOST_LONGITUDE"], meta["projection"]["EASTERNMOST_LONGITUDE"]],
        "fillValue": FILL,
        "partialFillRows": int(n - int((null_masks[0] == null_masks[-1]).sum()) if not all_same else 0),
        "uniformPixelWideFill": bool(all_same),
        "validPx": {p: int((~m).sum()) for p, m in zip(PARAMS, null_masks)},
        "fillPx": {p: int(m.sum()) for p, m in zip(PARAMS, null_masks)},
        "noThresholds": True,
    }
    return frame, scene_meta


def _verify_index_selection() -> dict[str, dict]:
    """Every selected scene must appear in the published index tables."""
    out: dict[str, dict] = {}
    wanted = [Path(rel).name for rels in SCENES.values() for rel in rels]
    for tab in sorted(SNAP_DIR.glob("mtrdr*_index.tab")):
        text = tab.read_text(errors="replace")
        for name in wanted:
            if name in out:
                continue
            for line in text.splitlines():
                if name in line and "MPTARGETED_RDR" in line:
                    out[name] = {"indexTab": tab.name, "productType": "MPTARGETED_RDR"}
                    break
    missing = [n for n in wanted if n not in out]
    if missing:
        raise ValueError(f"selected scenes missing from fetched index tables: {missing}")
    return out


def build() -> dict:
    inputs = verify_inputs()
    OUT.mkdir(parents=True, exist_ok=True)
    index_rows = _verify_index_selection()
    report = {
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "runtimeStatus": "executed",
        "scientificStatus": "executed-unreviewed",
        "scope": "source-native MTRDR SU summary parameters; native scene grids; "
                 "no resampling, no thresholds, no detected flags, no scoring",
        "parameterDefinitions": "official band names and formulas as distributed in the "
                                "MTRDR SU products (values read, not recomputed); "
                                "Viviano-Beck et al. 2014 (JGR 119), CRISM Data Product SIS",
        "timeSupport": "one row per pixel of one targeted CRISM observation "
                       "(seconds-long static scene); no temporal compositing; "
                       "observation date kept per scene",
        "fillValue": FILL,
        "missingReasonSchema": "per-row JSON: keys = exactly this row's null parameter "
                               "columns, value 'source-fill-65535'; empty object if all valid",
        "gaps": GAPS,
        "skippedScenes": SKIPPED,
        "inputCount": len(inputs),
        "indexedFrom": {k: v["indexTab"] for k, v in sorted(index_rows.items())},
        "outputs": {},
        "table": {},
    }

    part = TABLE.with_suffix(".parquet.part")
    scene_reports = []
    rows_total = 0
    writer = None
    try:
        for region, rels in SCENES.items():
            for rel in rels:
                frame, scene_meta = scene_frame(region, rel)
                scene_meta["sha256"] = sha256(SNAP_DIR / (Path(rel).name + ".IMG"))
                scene_meta["imgBytes"] = (SNAP_DIR / (Path(rel).name + ".IMG")).stat().st_size
                arrow = frame.to_arrow()
                if writer is None:
                    writer = pq.ParquetWriter(part, arrow.schema, compression="zstd")
                writer.write_table(arrow)
                rows_total += frame.height
                scene_reports.append(scene_meta)
                del frame, arrow
    finally:
        if writer is not None:
            writer.close()
    if rows_total == 0:
        raise ValueError("no scene produced rows")
    import os
    os.replace(part, TABLE)

    for scene in scene_reports:
        report["outputs"][Path(scene["scenePath"]).name + ".LBL"] = scene
    stats = pl.read_parquet(TABLE, columns=PARAMS).select(
        [pl.col(p).min().alias(p + "__min") for p in PARAMS] +
        [pl.col(p).max().alias(p + "__max") for p in PARAMS] +
        [pl.col(p).median().alias(p + "__median") for p in PARAMS] +
        [pl.col(p).is_null().sum().alias(p + "__nulls") for p in PARAMS]).row(0, named=True)
    observed = {p: {"min": stats[p + "__min"], "max": stats[p + "__max"],
                    "median": stats[p + "__median"], "nullRows": int(stats[p + "__nulls"])}
                for p in PARAMS}
    report["table"] = {"path": str(TABLE.relative_to(REPO)), "rows": rows_total,
                       "sha256": sha256(TABLE), "bytes": TABLE.stat().st_size}
    report["observedExtremes"] = observed
    report["decodeSanityEnvelope"] = {"lo": -10000.0, "hi": 10000.0,
        "note": "guards decode errors only; genuine source tails outside are kept verbatim"}
    meta = {
        "table": "crism-mtrdr-summary.parquet",
        "rows": rows_total,
        "key": ["observation_id", "source_line", "source_sample"],
        "parameters": PARAMS,
        "parameterUnits": {p: "dimensionless (band depth / index, source-native)" for p in PARAMS},
        "parameterFeatureMap": FEATURE_PARAMS,
        "regions": REGIONS,
        "sceneFootprints": {Path(v["scenePath"]).name: {
            "region": v["region"], "obs": v["productId"], "type": v["observationType"],
            "startTime": v["startTime"], "lat": v["footprintLat"], "lon": v["footprintLon"],
            "nativeGrid": v["nativeGrid"], "scaleKmPx": v["mapScaleKmPx"]}
            for v in scene_reports},
        "supportCounts": {Path(v["scenePath"]).name: v["validPx"] for v in scene_reports},
        "fillValue": FILL,
        "coordinateRule": "scene-native equirectangular pixel centres; no H3, no resampling",
        "noThresholds": True,
        "gaps": GAPS,
        "citation": "Viviano-Beck et al. 2014 (JGR 119, doi:10.1002/2013JE004527); "
                    "CRISM Data Product SIS; MRO-M-CRISM-5-RDR-MPTARGETED-V1.0, PDS Geosciences Node",
    }
    (OUT / "crism-mtrdr-summary.meta.json").write_text(json.dumps(meta, indent=2) + "\n")
    (OUT / "preparation-report.json").write_text(json.dumps(report, indent=2) + "\n")
    return report


# --------------------------------------------------------------------- checks
def check() -> None:
    verify_inputs()
    report = json.loads((OUT / "preparation-report.json").read_text())
    if not report.get("table") or report["table"].get("sha256") is None:
        raise ValueError("preparation report predates the current build")
    if sha256(TABLE) != report["table"]["sha256"] or TABLE.stat().st_size != report["table"]["bytes"]:
        raise ValueError("output hash/size mismatch: crism-mtrdr-summary.parquet")

    frame = pl.scan_parquet(TABLE)
    schema = frame.collect_schema()
    expected_cols = ["region", "observation_id", "product_id", "source_line", "source_sample",
                     "latitude", "longitude", *PARAMS, "missing_reason"]
    if list(schema.names()) != expected_cols:
        raise ValueError(f"column set changed: {list(schema.names())}")

    dupes = (frame.group_by(["observation_id", "source_line", "source_sample"]).len()
                  .filter(pl.col("len") > 1).select(pl.len()).collect().item())
    if dupes:
        raise ValueError(f"{dupes} duplicate (observation_id, source_line, source_sample) keys")

    # decode-garbage envelope (sanity only, NOT a detection threshold and NOT a
    # filter): band depths/dropoffs sit near [-1, 1] but the source definitions
    # produce genuine large-magnitude tails where denominators approach zero
    # (e.g. observed OLINDEX3 min -2203 at a near-zero-R1506 pixel); nothing is
    # dropped or altered outside the envelope - the check rejects only values
    # impossible from a correct <f4 decode (wrong endianness/offset/Inf)
    LO, HI = -10000.0, 10000.0
    bad = 0
    for p in PARAMS:
        bad += frame.filter(pl.col(p).is_not_null() &
                            (~pl.col(p).is_finite() | (pl.col(p) < LO) | (pl.col(p) > HI))
                            ).select(pl.len()).collect().item()
    if bad:
        raise ValueError(f"{bad} value(s) outside decode-sanity envelope [{LO}, {HI}]")

    for name, sm in report["outputs"].items():
        outside = frame.filter(
            (pl.col("product_id") == sm["productId"]) &
            ((pl.col("latitude") < sm["footprintLat"][0] - 0.002) |
             (pl.col("latitude") > sm["footprintLat"][1] + 0.002) |
             (pl.col("longitude") < sm["footprintLon"][0] - 0.002) |
             (pl.col("longitude") > sm["footprintLon"][1] + 0.002))
        ).select(pl.len()).collect().item()
        if outside:
            raise ValueError(f"{outside} rows outside the declared footprint of {sm['productId']}")

    # missing_reason: parseable JSON whose keys are exactly the row's null
    # parameter columns. The JSON vocabulary is finite (empty object or
    # subsets of PARAMS with value "fill-65535"), so verify every distinct
    # string, then verify key counts against row null counts per row.
    distinct = frame.select("missing_reason").unique().collect().to_series().to_list()
    for reason in distinct:
        obj = json.loads(reason)
        if not isinstance(obj, dict) or set(obj) - set(PARAMS):
            raise ValueError(f"bad missing_reason JSON: {reason!r}")
        for k, v in obj.items():
            if v != f"fill-{int(FILL)}":
                raise ValueError(f"bad missing_reason value for {k} in {reason!r}")
    decoded = frame.select(["missing_reason", *PARAMS]).with_columns(
        nulls=pl.sum_horizontal([pl.col(p).is_null().cast(pl.Int32) for p in PARAMS]),
        keys=pl.col("missing_reason").str.count_matches(f'fill-{int(FILL)}'),
        open_ok=pl.col("missing_reason").str.starts_with("{") &
                pl.col("missing_reason").str.ends_with("}"))
    mismatched = decoded.filter((pl.col("nulls") != pl.col("keys")) | ~pl.col("open_ok")).select(pl.len()).collect().item()
    if mismatched:
        raise ValueError(f"{mismatched} rows where missing_reason keys != null parameter columns")

    # region anchors inside their scenes' footprints (known coordinates)
    for region, rels in SCENES.items():
        anchor_lat, anchor_lon = REGIONS[region]["anchor"]
        covered = report["outputs"][Path(rels[0]).name + ".LBL"]
        if not (covered["footprintLat"][0] - 0.2 <= anchor_lat <= covered["footprintLat"][1] + 0.2):
            raise ValueError(f"region anchor {region} outside chosen scene footprint")
        if not (min(covered["footprintLon"][0], covered["footprintLon"][1]) - 0.2 <= anchor_lon <=
                max(covered["footprintLon"][0], covered["footprintLon"][1]) + 0.2):
            raise ValueError(f"region anchor {region} outside chosen scene footprint")

    raw_frame = frame.collect()
    spots = spot_pixels()
    value_comparisons = 0
    for product_id, line, sample in spots:
        scene = next(v for v in report["outputs"].values() if v["productId"] == product_id)
        img = SNAP_DIR / (Path(scene["scenePath"]).name + ".IMG")
        n_samples = scene["nativeGrid"]["samples"]
        lt = raw_frame.filter((pl.col("product_id") == product_id) &
                              (pl.col("source_line") == line) & (pl.col("source_sample") == sample))
        if lt.height != 1:
            raise ValueError(f"spot check key missing: {product_id} {line} {sample}")
        # independent raw read: fresh handle, direct band indexing
        with open(img, "rb") as fh:
            base = (int(line) * int(n_samples) + int(sample)) * 60 * 4
            fh.seek(base)
            pixel = np.frombuffer(fh.read(60 * 4), dtype="<f4")
        raw = {name: pixel[i] for name, i in ((n, SU_BANDS.index(n)) for n in SU_BANDS)}
        for p in PARAMS:
            got = lt[p].item()
            v = raw[p]
            if v == FILL or not np.isfinite(v):
                if got is not None:
                    raise ValueError(f"spot check fill mismatch {product_id} {line} {sample} {p}")
            else:
                if got is None:
                    raise ValueError(f"spot check: table null where raw valid {product_id} {line} {sample} {p}")
                if not math.isclose(float(v), float(got), rel_tol=0.0, abs_tol=1e-6):
                    raise ValueError(f"spot check value mismatch {product_id} {line} {sample} {p}: "
                                     f"{float(v)} vs {float(got)}")
                value_comparisons += 1
            in_reason = json.loads(lt["missing_reason"].item())
            if (p in in_reason) != (got is None):
                raise ValueError(f"spot check missing_reason key mismatch {product_id} {line} {sample} {p}")
        geo = (lt["latitude"].item(), lt["longitude"].item())
        if not (scene["footprintLat"][0] - 0.002 <= geo[0] <= scene["footprintLat"][1] + 0.002 and
                scene["footprintLon"][0] - 0.002 <= geo[1] <= scene["footprintLon"][1] + 0.002):
            raise ValueError(f"spot check coordinate outside footprint: {product_id} {geo}")
    if value_comparisons < 5:
        raise ValueError(f"only {value_comparisons} raw value comparisons across spot pixels")
    print(f"PASS crism-mtrdr-summary: {raw_frame.height:,} rows, "
          f"{len(spots)} spot pixels, {value_comparisons} raw value comparisons")


def spot_pixels() -> list[tuple[str, int, int]]:
    """Deterministic spot pixels, one per scene: a fully valid pixel and a fully
    filled pixel chosen by a hash of the product id (stable for a given file)."""
    import hashlib

    checks = []
    rels_by_product = {Path(rel).name: rel for rels in SCENES.values() for rel in rels}
    for scene_name, rel in sorted(rels_by_product.items()):
        meta = parse_scene_label(SNAP_DIR / (scene_name + ".LBL"))
        geom = validate_geometry(meta)
        n_lines, n_samples = geom["lines"], geom["samples"]
        cube = np.memmap(SNAP_DIR / (scene_name + ".IMG"), dtype="<f4", mode="r").reshape(n_lines, n_samples, 60)
        # per-pixel fill: any non-finite or fill value anywhere in the spectrum
        fillpix = np.zeros((n_lines, n_samples), dtype=bool)
        for b in range(60):
            band = cube[:, :, b]
            fillpix |= ~np.isfinite(band) | (band == FILL)
        valid = np.argwhere(~fillpix)
        if len(valid) == 0:
            raise ValueError(f"no valid pixels in {scene_name}")
        seed = int(hashlib.sha256(rel.encode()).hexdigest()[:8], 16)
        v = valid[seed % len(valid)]
        fill_sel = np.argwhere(fillpix)
        f = fill_sel[(seed >> 3) % len(fill_sel)] if len(fill_sel) else v
        checks.append((meta["productId"], int(v[0]), int(v[1])))
        if len(fill_sel):
            checks.append((meta["productId"], int(f[0]), int(f[1])))
        del cube, fillpix, valid, fill_sel
    return checks


def main():
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument("action", choices=["fetch", "build", "check"])
    action = parser.parse_args().action
    if action == "fetch":
        for dataset, url in sources():
            print(fetch(dataset, url), flush=True)
    elif action == "build":
        report = build()
        print(json.dumps({"rows": report["table"]["rows"], "sha256": report["table"]["sha256"]}), flush=True)
    else:
        check()


if __name__ == "__main__":
    main()
