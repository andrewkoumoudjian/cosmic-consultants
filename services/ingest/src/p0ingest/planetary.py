"""Prepare source-native Diviner PRP and TES thermal-inertia data (#74).

Direct decoding and declared quality filtering only. No resampling, Earth H3,
derived similarity, target bands or newly inferred scientific quantities.
Run: python -m p0ingest.planetary fetch|build|check
"""
from __future__ import annotations

import argparse
import json
import os
import re
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import polars as pl
import pyarrow.parquet as pq

from .snapshots import REPO, SNAP, fetch, load_manifest, sha256

OUT = SNAP / "_derived" / "planetary"
DIVINER = "https://pds-geosciences.wustl.edu/lro/urn-nasa-pds-lro_diviner_derived1/data_derived_prp/"
TES = "https://pds-geosciences.wustl.edu/mgs/mgs-m-tes-5-timap-v1/mgst_9001/"
NS = {"p": "http://pds.nasa.gov/pds4/pds/v1"}


def sources():
    yield from (("diviner-l4", DIVINER + "dlre_prp_south." + ext) for ext in ("xml", "lbl", "tab"))
    for prefix in ("day_", "night_", "msk_day_", "msk_night_"):
        for ext in ("lbl", "img"):
            yield "tes-mgs", TES + "data/global_ti_" + prefix + "2007." + ext
    yield from (("tes-mgs", TES + path) for path in ("aareadme.txt", "catalog/dataset.cat", "catalog/dsmap.cat"))


def read_character_label(path: Path) -> dict:
    root = ET.parse(path).getroot()
    table = root.find("p:File_Area_Observational/p:Table_Character", NS)
    if table is None:
        raise ValueError("expected one PDS4 character table")
    def text(element, tag):
        value = element.findtext("p:" + tag, namespaces=NS)
        if value is None:
            raise ValueError(f"missing label field {tag}")
        return value.strip()
    record = table.find("p:Record_Character", NS)
    if record is None or text(table, "record_delimiter") != "Carriage-Return Line-Feed":
        raise ValueError("unsupported character record layout")
    fields = []
    length = int(text(record, "record_length"))
    for field in record.findall("p:Field_Character", NS):
        if text(field, "data_type") != "ASCII_Real":
            raise ValueError("unsupported character data type")
        item = {"name": text(field, "name"), "start": int(text(field, "field_location")) - 1,
                "length": int(text(field, "field_length")), "unit": text(field, "unit"),
                "description": text(field, "description")}
        constants = field.find("p:Special_Constants", NS)
        item["invalid"] = [] if constants is None else [float(c.text) for c in constants]
        if item["start"] < 0 or item["length"] < 1 or item["start"] + item["length"] > length - 2:
            raise ValueError("field outside record")
        fields.append(item)
    if len(fields) != int(text(record, "fields")) or len({f["name"] for f in fields}) != len(fields):
        raise ValueError("duplicate or incomplete character fields")
    return {"records": int(text(table, "records")), "offset": int(text(table, "offset")),
            "recordBytes": length, "fields": fields}


def character_batches(path: Path, spec: dict, batch_size: int = 100_000):
    size = spec["offset"] + spec["records"] * spec["recordBytes"]
    if path.stat().st_size != size or batch_size < 1:
        raise ValueError("character table byte count or batch size differs from label")
    raw = np.memmap(path, dtype=np.uint8, mode="r")
    width = spec["recordBytes"]
    for start in range(0, spec["records"], batch_size):
        count = min(batch_size, spec["records"] - start)
        offset = spec["offset"] + start * width
        ends = np.ndarray((count,), dtype="S2", buffer=raw, offset=offset + width - 2, strides=(width,))
        if np.any(ends != b"\r\n"):
            raise ValueError(f"record delimiter changed at batch {start}")
        columns = {"source_record": pl.Series(np.arange(start, start + count, dtype=np.uint32))}
        for field in spec["fields"]:
            values = np.ndarray((count,), dtype=f'S{field["length"]}', buffer=raw,
                                offset=offset + field["start"], strides=(width,)).astype(np.float64)
            if not np.isfinite(values).all():
                raise ValueError(f"non-finite source field {field['name']}")
            invalid = np.isin(values, field["invalid"])
            series = pl.Series(field["name"], values)
            if field["invalid"]:
                columns[field["name"] + "_source_value"] = series
                series = series.set(pl.Series(invalid), None)
            columns[field["name"]] = series
        yield pl.DataFrame(columns)


def read_tes_image(path: Path, label: Path) -> np.ndarray:
    text = label.read_text()
    if '"MGS-M-TES-5-TIMAP-V1.0"' not in text:
        raise ValueError("unsupported TES product")
    match = re.search(r"OBJECT\s*=\s*IMAGE\s*\n(.*?)END_OBJECT\s*=\s*IMAGE", text, re.S)
    if not match:
        raise ValueError("missing PDS3 IMAGE object")
    def value(key):
        found = re.search(rf"^\s*{key}\s*=\s*(\S+)", match.group(1), re.M)
        if not found:
            raise ValueError(f"missing IMAGE field {key}")
        return found.group(1)
    bits = int(value("SAMPLE_BITS"))
    if value("SAMPLE_TYPE") != "MSB_INTEGER" or bits not in (8, 16):
        raise ValueError("unsupported TES byte layout")
    shape = int(value("LINES")), int(value("LINE_SAMPLES"))
    if min(shape) < 1 or path.stat().st_size != shape[0] * shape[1] * bits // 8:
        raise ValueError("TES image byte count differs from label")
    return np.memmap(path, dtype=">i2" if bits == 16 else "u1", mode="r", shape=shape)


def clean_tes(values: np.ndarray, mask: np.ndarray, start_line: int = 0) -> pl.DataFrame:
    if values.shape != mask.shape or values.ndim != 2 or not np.isin(mask, [0, 1]).all():
        raise ValueError("TES mask must have the image shape and only 0/1 values")
    height, width = values.shape
    frame = pl.DataFrame({"source_line": np.repeat(np.arange(start_line, start_line + height, dtype=np.uint16), width),
                          "source_sample": np.tile(np.arange(width, dtype=np.uint16), height),
                          "source_thermal_inertia": np.asarray(values, dtype=np.int16).ravel(),
                          "source_interpolation_mask": np.asarray(mask).ravel()})
    valid_range = pl.col("source_thermal_inertia").is_between(5, 5000)
    original = pl.col("source_interpolation_mask") == 1
    return frame.with_columns(
        pl.when(original & valid_range).then(pl.col("source_thermal_inertia")).otherwise(None).alias("thermal_inertia"),
        pl.when(~original).then(pl.lit("source-interpolated")).when(~valid_range)
        .then(pl.lit("outside-source-computed-range")).otherwise(None).alias("missing_reason"))


def write_batches(path: Path, frames) -> dict:
    part = path.with_suffix(".part")
    rows = 0
    nulls = {}
    reasons = {}
    writer = None
    try:
        for frame in frames:
            table = frame.to_arrow()
            if writer is None:
                writer = pq.ParquetWriter(part, table.schema, compression="zstd")
            writer.write_table(table)
            rows += frame.height
            for key, count in zip(frame.columns, frame.null_count().row(0)):
                nulls[key] = nulls.get(key, 0) + count
            if "missing_reason" in frame.columns:
                for reason, count in frame.group_by("missing_reason").len().iter_rows():
                    key = reason if reason is not None else "valid"
                    reasons[key] = reasons.get(key, 0) + count
    finally:
        if writer is not None:
            writer.close()
    if rows == 0:
        raise ValueError("source has zero rows")
    os.replace(part, path)
    return {"rows": rows, "nullCounts": nulls, "reasonCounts": reasons,
            "sha256": sha256(path), "bytes": path.stat().st_size}


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


def build() -> dict:
    inputs = verify_inputs()
    OUT.mkdir(parents=True, exist_ok=True)
    report = {"generatedAt": datetime.now(timezone.utc).isoformat(), "inputs": inputs,
              "runtimeStatus": "executed", "scientificStatus": "executed-unreviewed",
              "scope": "source-native decoding and declared filtering; no inferred target bands or analogy", "outputs": {}}
    lunar = SNAP / "diviner-l4"
    spec = read_character_label(lunar / "dlre_prp_south.xml")
    expected = ["tri1_x", "tri1_y", "tri1_z", "tri2_x", "tri2_y", "tri2_z", "tri3_x", "tri3_y", "tri3_z",
                "tri_clon", "tri_clat", "tri_calt", "temp_avg", "temp_max", "ice_depth"]
    if [f["name"] for f in spec["fields"]] != expected or spec["records"] != 2_880_000:
        raise ValueError("Diviner product layout changed; review before preparing")
    units = ["km"] * 9 + ["degree", "degree", "km", "Kelvin", "Kelvin", "meter"]
    if [f["unit"] for f in spec["fields"]] != units or spec["fields"][-1]["invalid"] != [-999.0]:
        raise ValueError("Diviner source units or exclusion changed; review before preparing")
    result = write_batches(OUT / "diviner-south-prp.parquet", character_batches(lunar / "dlre_prp_south.tab", spec))
    result.update({"fields": spec["fields"], "body": "Moon", "coordinates": "source triangle vertices, km; planetocentric positive-east centres; 1737.4 km reference sphere",
                   "timeSupport": "annual model statistics; PDS4 start/stop are inapplicable; no inferred observation year",
                   "temperatureMeaning": "temp_avg: model annual average 2 cm below surface; temp_max: model annual maximum at surface; Kelvin",
                   "iceMeaning": "calculated ice-stability depth, not measured ice occurrence/depth; source -999 excluded when calculated depth exceeds 2.8738 m; zero retained",
                   "missingReason": {"ice_depth": "source exclusion: calculated stability depth exceeds 2.8738 m"},
                   "quality": "only label-declared exclusion applied; no independent validation; no finer spatial support assigned"})
    report["outputs"]["diviner-south-prp.parquet"] = result
    mars = SNAP / "tes-mgs"
    if "IAU_1991" not in (mars / "aareadme.txt").read_text():
        raise ValueError("TES reference frame changed; review before preparing")
    for phase in ("day", "night"):
        name = f"global_ti_{phase}_2007"
        mask_name = f"global_ti_msk_{phase}_2007"
        values = read_tes_image(mars / (name + ".img"), mars / (name + ".lbl"))
        mask = read_tes_image(mars / (mask_name + ".img"), mars / (mask_name + ".lbl"))
        if values.shape != (3600, 7200) or mask.shape != values.shape:
            raise ValueError("TES global map layout changed")
        filename = f"tes-thermal-inertia-{phase}.parquet"
        frames = (clean_tes(values[start:start + 100], mask[start:start + 100], start) for start in range(0, 3600, 100))
        result = write_batches(OUT / filename, frames)
        result.update({"body": "Mars", "units": "J/(m^2*K*sqrt(s))", "quantity": "model-derived apparent thermal inertia, not surface temperature",
                       "spatialSupport": "source 20 pixels/degree, labelled map scale 2.96 km/pixel; native source grid retained",
                       "coordinates": "zero-based source_line/source_sample; SIMPLE CYLINDRICAL; planetocentric east-positive, IAU_1991, sphere radius 3396 km; retain label/DSMAP equations before spatial extraction",
                       "spatialExtractionStatus": "pending projection review: DSMAP LINE/SAMPLE equation signs conflict with its stated upper-left/edge convention; no geographic extraction or target association performed",
                       "timeSupport": "February 1999 to April 2004 observations; map publication 2007; archive 2009; no contemporary or seasonal claim",
                       "quality": "source mask=0 is interpolated and excluded; only mask=1 and values 5..5000 retained; raw source integers/mask remain available"})
        report["outputs"][filename] = result
    (OUT / "preparation-report.json").write_text(json.dumps(report, indent=2) + "\n")
    return report


def check() -> None:
    verify_inputs()
    report = json.loads((OUT / "preparation-report.json").read_text())
    for name, meta in report["outputs"].items():
        path = OUT / name
        if sha256(path) != meta["sha256"] or path.stat().st_size != meta["bytes"]:
            raise ValueError(f"output hash/size mismatch: {name}")
        if pq.ParquetFile(path).metadata.num_rows != meta["rows"]:
            raise ValueError(f"output row count mismatch: {name}")
        frame = pl.scan_parquet(path)
        if "tes-" in name:
            bad = frame.filter((pl.col("thermal_inertia").is_not_null()) &
                               ((pl.col("source_interpolation_mask") != 1) | ~pl.col("source_thermal_inertia").is_between(5, 5000))).select(pl.len()).collect().item()
            null_disagreement = frame.filter(pl.col("thermal_inertia").is_null() != pl.col("missing_reason").is_not_null()).select(pl.len()).collect().item()
            changed = frame.filter(pl.col("thermal_inertia").is_not_null() & (pl.col("thermal_inertia") != pl.col("source_thermal_inertia"))).select(pl.len()).collect().item()
            if bad or null_disagreement or changed:
                raise ValueError(f"TES filtering failed: {bad}/{null_disagreement}/{changed}")
        else:
            bad = frame.filter(pl.col("ice_depth").is_null() != (pl.col("ice_depth_source_value") == -999)).select(pl.len()).collect().item()
            if bad:
                raise ValueError("Diviner exclusion changed")
        print(f"PASS {name}: {meta['rows']:,} rows; hash, size and source filtering", flush=True)


def main():
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument("action", choices=["fetch", "build", "check"])
    action = parser.parse_args().action
    if action == "fetch":
        for dataset, url in sources():
            print(fetch(dataset, url), flush=True)
    elif action == "build":
        report = build()
        for name, meta in report["outputs"].items():
            print(name, meta["rows"], meta["sha256"], flush=True)
    else:
        check()


if __name__ == "__main__":
    main()
