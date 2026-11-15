"""Prepare source-native Diviner global/polar derived maps (#100, W41).

LRO Diviner derived bundle 1 (PDS Geosciences node), all mission-cumulative
static products - no daily or per-orbit granules, satisfying the at-most-
monthly time-resolution rule:

- GCP  (18 x 10-degree latitude bands): bolometric brightness temperature
  binned at 0.5 deg x 0.5 deg x 0.25 h lunar local time, cumulative average of
  all nadir observations 2009-07-05..2015-04-01. Serves tsurf_max, tsurf_min,
  tsurf_range. The native (cell x local-time) grid is kept and a per-cell
  summary (max/min/range over the product's own local-time axis) is derived.
- GDR L3 STD_CF: cumulative Christiansen Feature position map (mid-infrared
  emissivity maximum near 8 um), 32 pixels/degree, -60..+60 deg. Serves
  cf_position.
- GDR L3 RA_AVG: cumulative rock-abundance map (Bandfield et al. 2011
  two-component night-time fit, the ten night local-time bins averaged), 32
  pixels/degree, -60..+60 deg. Serves the rock_abund_div probe.
- PRP north: north-polar triangles with model annual average/maximum
  temperature and ice-stability depth (mirror of the south PRP prepared in
  planetary.py, #74).

Direct decoding, label-declared filtering and reductions over the product's
own declared axes only. No resampling to H3, no inferred target bands, no
analogy or scoring. Missing stays missing: null value columns carry a JSON
``missing_reason`` whose keys are exactly the null value columns of that row.
Run: python -m p0ingest.moon_diviner fetch|build|check
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

OUT = SNAP / "_derived" / "planetary" / "diviner-l4"
BASE = "https://pds-geosciences.wustl.edu/lro/urn-nasa-pds-lro_diviner_derived1"
# GCP band tags, south to north (10-degree bands, label-declared latitude edges).
GCP_BANDS = ("90s80s", "80s70s", "70s60s", "60s50s", "50s40s", "40s30s", "30s20s", "20s10s",
             "10s00s", "00n10n", "10n20n", "20n30n", "30n40n", "40n50n", "50n60n", "60n70n",
             "70n80n", "80n90n")
INVALID = -9998.0   # label invalid_constant (channel below sensitivity sentinel)
UNKNOWN = -9999.0   # label unknown_constant (bin contained no observations)
LT_BINS = 96        # 0.25 h local-time bins in the 24 h lunar day
PDS_NS = {"p": "http://pds.nasa.gov/pds4/pds/v1"}
PRP_FIELDS = ["tri1_x", "tri1_y", "tri1_z", "tri2_x", "tri2_y", "tri2_z", "tri3_x", "tri3_y",
              "tri3_z", "tri_clon", "tri_clat", "tri_calt", "temp_avg", "temp_max", "ice_depth"]
GDR_EXPECTED = {"dgdr_std_cf_clc_cyl_032_img": ("STANDARD CF", "cf_position"),
                "dgdr_ra_avg_cyl_032_img": ("ROCK ABUNDANCE", "rock_abund_div")}


def band_edges(tag: str) -> tuple[float, float]:
    """South-to-north degree edges of a GCP band tag like 30s20s or 00n10n."""
    text = re.fullmatch(r"(\d{2})([ns])(\d{2})([ns])", tag)
    if text is None:
        raise ValueError(f"bad GCP band tag {tag}")
    def edge(number: str, hemisphere: str) -> float:
        return -float(number) if hemisphere == "s" else float(number)
    low, high = edge(text[1], text[2]), edge(text[3], text[4])
    if high <= low or high - low != 10.0:
        raise ValueError(f"GCP band tag {tag} is not a south-to-north 10-degree band")
    return low, high


def sources():
    for band in GCP_BANDS:
        for ext in ("xml", "lbl", "tab"):
            yield "diviner-l4", f"{BASE}/data_derived_gcp/global_cumul_avg_cyl_{band}_002.{ext}"
    for name in GDR_EXPECTED:
        for ext in ("img", "lbl", "xml"):
            yield "diviner-l4", f"{BASE}/data_derived_gdr_l3/cylindrical/img/{name}.{ext}"
    for ext in ("xml", "lbl", "tab"):
        yield "diviner-l4", f"{BASE}/data_derived_prp/dlre_prp_north.{ext}"


# ---- PDS4 character-table reader (PRP north + GCP labels) -------------------


def read_character_label(path: Path) -> dict:
    """Parse a PDS4 Table_Character label: layout, fields, special constants."""
    root = ET.parse(path).getroot()
    table = root.find("p:File_Area_Observational/p:Table_Character", PDS_NS)
    if table is None:
        raise ValueError("expected one PDS4 character table")
    def text(element, tag):
        value = element.findtext("p:" + tag, namespaces=PDS_NS)
        if value is None:
            raise ValueError(f"missing label field {tag}")
        return value.strip()
    record = table.find("p:Record_Character", PDS_NS)
    if record is None or text(table, "record_delimiter") != "Carriage-Return Line-Feed":
        raise ValueError("unsupported character record layout")
    length = int(text(record, "record_length"))
    fields = []
    for field in record.findall("p:Field_Character", PDS_NS):
        if text(field, "data_type") != "ASCII_Real":
            raise ValueError("unsupported character data type")
        item = {"name": text(field, "name"), "start": int(text(field, "field_location")) - 1,
                "length": int(text(field, "field_length"))}
        unit = field.findtext("p:unit", namespaces=PDS_NS)
        item["unit"] = unit.strip() if unit is not None else None
        constants = field.find("p:Special_Constants", PDS_NS)
        item["invalid"] = [] if constants is None else [float(c.text) for c in constants]
        if item["start"] < 0 or item["length"] < 1 or item["start"] + item["length"] > length - 2:
            raise ValueError("field outside record")
        fields.append(item)
    if len(fields) != int(text(record, "fields")) or len({f["name"] for f in fields}) != len(fields):
        raise ValueError("duplicate or incomplete character fields")
    offset_text = table.findtext("p:offset", namespaces=PDS_NS)
    offset = int(offset_text) if offset_text else None
    return {"records": int(text(table, "records")), "offset": offset,
            "recordBytes": length, "fields": fields}


def resolve_offset(path: Path, spec: dict) -> dict:
    """Resolve a missing <offset> to the trailing bytes beyond records*recordBytes."""
    spec = dict(spec)
    if spec["offset"] is None:
        spec["offset"] = path.stat().st_size - spec["records"] * spec["recordBytes"]
    if spec["offset"] < 0 or spec["offset"] > spec["recordBytes"]:
        raise ValueError("header offset out of range")
    return spec


def character_batches(path: Path, spec: dict, batch_size: int = 100_000):
    """Fixed-width ASCII_Real records with label-declared exclusions (PRP north)."""
    if path.stat().st_size != spec["offset"] + spec["records"] * spec["recordBytes"]:
        raise ValueError("PRP byte count differs from label")
    raw = np.memmap(path, dtype=np.uint8, mode="r")
    width = spec["recordBytes"]
    for start in range(0, spec["records"], batch_size):
        count = min(batch_size, spec["records"] - start)
        offset = spec["offset"] + start * width
        ends = np.ndarray((count,), dtype="S2", buffer=raw, offset=offset + width - 2, strides=(width,))
        if np.any(ends != b"\r\n"):
            raise ValueError(f"record delimiter changed at batch {start}")
        columns: dict[str, pl.Series | np.ndarray] = {}
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
        columns["source_record"] = np.arange(start, start + count, dtype=np.uint32)
        yield pl.DataFrame(columns)


# ---- GCP bands ---------------------------------------------------------------


def read_gcp_label(path: Path) -> dict:
    """Validate a GCP PDS4 label and resolve the header-line offset."""
    spec = resolve_offset(path, read_character_label(path))
    names = [f["name"].lower() for f in spec["fields"]]
    expected = ["center_longitude", "center_latitude", "local_time", "t3", "t4", "t5",
                "t6", "t7", "t8", "t9", "tbol"]
    if names != expected or spec["records"] != 1_382_400:
        raise ValueError("GCP product layout changed; review before preparing")
    return spec


def _gcp_column(path: Path, spec: dict, name: str) -> np.ndarray:
    field = next(f for f in spec["fields"] if f["name"].lower() == name)
    return _fixed_offset_column(path, spec, field)


def _fixed_offset_column(path: Path, spec: dict, field: dict) -> np.ndarray:
    """One fixed-width ASCII_Real column as float64, byte-exact against the label."""
    count, width = spec["records"], spec["recordBytes"]
    raw = np.memmap(path, dtype=np.uint8, mode="r")
    values = np.ndarray((count,), dtype=f'S{field["length"]}', buffer=raw,
                        offset=spec["offset"] + field["start"], strides=(width,)).astype(np.float64)
    if not np.isfinite(values).all():
        raise ValueError(f"non-finite source field {field['name']}")
    return values


def bin_gcp_columns(clon: np.ndarray, clat: np.ndarray, ltim: np.ndarray, tbol: np.ndarray,
                    low: float, high: float) -> tuple[pl.DataFrame, pl.DataFrame, dict]:
    """Bin raw GCP columns into (native cell x local-time frame, per-cell summary, stats)."""
    clon_bin = np.rint((clon + 179.75) / 0.5).astype(np.int64)
    clat_bin = np.rint((clat + 89.75) / 0.5).astype(np.int64)
    ltim_bin = np.rint((ltim - 0.125) / 0.25).astype(np.int64)
    if clon_bin.min() < 0 or clon_bin.max() > 719 or clat_bin.min() < 0 or clat_bin.max() > 359 \
            or ltim_bin.min() < 0 or ltim_bin.max() > LT_BINS - 1:
        raise ValueError("GCP bin index out of range")
    if np.abs(clon - (-179.75 + 0.5 * clon_bin)).max() > 1e-6 \
            or np.abs(clat - (-89.75 + 0.5 * clat_bin)).max() > 1e-6 \
            or np.abs(ltim - (0.125 + 0.25 * ltim_bin)).max() > 0.0051:
        raise ValueError("GCP centres off the declared 0.5 deg / 0.25 h bin grid")
    lat = -89.75 + 0.5 * clat_bin
    if lat.min() < low + 0.25 - 1e-6 or lat.max() > high - 0.25 + 1e-6:
        raise ValueError("GCP latitude centres outside the band")
    invalid = tbol == INVALID
    unknown = tbol == UNKNOWN
    if (tbol[~(invalid | unknown)] <= 0).any():
        raise ValueError("GCP non-sentinel bolometric temperature at or below 0 K")
    order = np.lexsort((ltim_bin, clon_bin, clat_bin))
    tbol_series = pl.Series(tbol[order].astype(np.float32))
    tbol_series = tbol_series.set(pl.Series((invalid | unknown)[order]), None)
    native = pl.DataFrame({
        "clat_bin": pl.Series(clat_bin[order].astype(np.uint16), dtype=pl.UInt16),
        "clon_bin": pl.Series(clon_bin[order].astype(np.uint16), dtype=pl.UInt16),
        "ltim_bin": pl.Series(ltim_bin[order].astype(np.uint8), dtype=pl.UInt8),
        "tbol": tbol_series,
        "missing_reason": pl.Series(
            np.where(invalid[order], np.uint8(2), np.where(unknown[order], np.uint8(1), np.uint8(0)))
        ).replace_strict({0: None, 1: "source-no-observation", 2: "source-invalid-constant"},
                         return_dtype=pl.String),
    })
    summary = (
        native.group_by("clat_bin", "clon_bin")
        .agg(pl.col("tbol").max().alias("tsurf_max"), pl.col("tbol").min().alias("tsurf_min"),
             pl.col("tbol").count().alias("support_bins"))
        .with_columns((pl.col("tsurf_max") - pl.col("tsurf_min")).alias("tsurf_range"))
        .with_columns(pl.col("support_bins").cast(pl.UInt8))
        .with_columns(gcp_missing_reason())
        .sort("clat_bin", "clon_bin")
    )
    return native, summary, {"invalid": int(invalid.sum()), "unknown": int(unknown.sum())}


def gcp_band(tag: str, directory: Path) -> tuple[pl.DataFrame, pl.DataFrame, dict]:
    """Parse one GCP band into (native cell x local-time frame, per-cell summary, stats)."""
    low, high = band_edges(tag)
    stem = directory / f"global_cumul_avg_cyl_{tag}_002"
    spec = read_gcp_label(stem.with_suffix(".xml"))
    tab = stem.with_suffix(".tab")
    return bin_gcp_columns(
        _gcp_column(tab, spec, "center_longitude"), _gcp_column(tab, spec, "center_latitude"),
        _gcp_column(tab, spec, "local_time"), _gcp_column(tab, spec, "tbol"), low, high)


def gcp_missing_reason() -> pl.Expr:
    """JSON object with exactly the keys of the null value columns ('' when none)."""
    body = pl.concat_str([
        pl.when(pl.col("tsurf_max").is_null()).then(pl.lit('"tsurf_max":"no-valid-source-bins"')).otherwise(None),
        pl.when(pl.col("tsurf_min").is_null()).then(pl.lit('"tsurf_min":"no-valid-source-bins"')).otherwise(None),
        pl.when(pl.col("tsurf_range").is_null()).then(pl.lit('"tsurf_range":"no-valid-source-bins"')).otherwise(None),
    ], separator=",", ignore_nulls=True).fill_null("")
    return (pl.lit("{") + body + pl.lit("}")).alias("missing_reason")


# ---- GDR L3 cumulative maps (CF position, rock abundance) --------------------


def read_gdr_label(label: Path, image: Path, stem: str) -> dict:
    """Read a PDS3 IMG label: shape, scaling, missing constant, projection."""
    text = label.read_text()
    match = re.search(r"OBJECT\s*=\s*IMAGE\s*\n(.*?)END_OBJECT\s*=\s*IMAGE", text, re.S)
    if not match or not re.search(rf'NAME\s*=\s*"{GDR_EXPECTED[stem][0]}"', text):
        raise ValueError(f"unsupported GDR label {label.name}")
    def value(key):
        found = re.search(rf"^\s*{key}\s*=\s*(\S+)", match.group(1), re.M)
        if not found:
            raise ValueError(f"missing IMAGE field {key}")
        return found.group(1)
    if value("SAMPLE_TYPE") != "LSB_INTEGER" or int(value("SAMPLE_BITS")) != 16:
        raise ValueError("unsupported GDR byte layout")
    shape = int(value("LINES")), int(value("LINE_SAMPLES"))
    if image.stat().st_size != shape[0] * shape[1] * 2:
        raise ValueError("GDR image byte count differs from label")
    projection = re.search(
        r"OBJECT\s*=\s*IMAGE_MAP_PROJECTION\s*\n(.*?)END_OBJECT\s*=\s*IMAGE_MAP_PROJECTION", text, re.S)
    if projection is None:
        raise ValueError("missing IMAGE_MAP_PROJECTION")
    def proj(key, cast=float):
        found = re.search(rf"^\s*{key}\s*=\s*(\S+)", projection.group(1), re.M)
        if not found:
            raise ValueError(f"missing projection field {key}")
        return cast(found.group(1))
    ptype = re.search(r'MAP_PROJECTION_TYPE\s*=\s*"([^"]*)"', projection.group(1))
    if proj("MAP_RESOLUTION", int) != 32 or ptype is None or ptype.group(1) != "SIMPLE CYLINDRICAL":
        raise ValueError("unexpected GDR projection")
    return {"shape": shape, "scale": float(value("SCALING_FACTOR")), "missing": int(value("MISSING_CONSTANT")),
            "minLat": proj("MINIMUM_LATITUDE"), "maxLat": proj("MAXIMUM_LATITUDE"),
            "derivedMin": float(value("DERIVED_MINIMUM")), "derivedMax": float(value("DERIVED_MAXIMUM"))}


def gdr_batches(path: Path, label_spec: dict, value_column: str, batch_lines: int = 100):
    """Yield pixel frames for one GDR IMG; label-declared missing constant excluded."""
    dn = np.memmap(path, dtype="<i2", mode="r", shape=label_spec["shape"])
    missing_dn = label_spec["missing"]
    low, high = label_spec["derivedMin"], label_spec["derivedMax"]
    for start in range(0, label_spec["shape"][0], batch_lines):
        block = np.asarray(dn[start:start + batch_lines])
        height, width = block.shape
        values = block.astype(np.float32) * np.float32(label_spec["scale"])
        missing = (block == missing_dn).ravel()
        outside = (~missing) & ((values.ravel() < low - 1e-6) | (values.ravel() > high + 1e-6))
        yield pl.DataFrame({
            "source_line": np.repeat(np.arange(start, start + height, dtype=np.uint16), width),
            "source_sample": np.tile(np.arange(width, dtype=np.uint16), height),
            "source_dn": pl.Series(block.ravel().astype(np.int16), dtype=pl.Int16),
            value_column: pl.Series(values.ravel().astype(np.float32)).set(
                pl.Series(missing | outside), None),
            "missing_reason": pl.Series(
                np.where(missing, np.uint8(2), np.where(outside, np.uint8(1), np.uint8(0)))
            ).replace_strict({0: None, 1: "outside-label-derived-range", 2: "source-missing-constant"},
                             return_dtype=pl.String),
        })


# ---- shared output helpers ----------------------------------------------------


def native_schema() -> "pa.Schema":
    """Arrow schema for the native GCP cell x local-time table."""
    import pyarrow as pa
    return pa.schema([("clat_bin", pa.uint16()), ("clon_bin", pa.uint16()),
                      ("ltim_bin", pa.uint8()), ("tbol", pa.float32()),
                      ("missing_reason", pa.large_string())])


def write_batches(path: Path, frames) -> dict:
    part = path.with_suffix(".part")
    rows = 0
    nulls: dict[str, int] = {}
    reasons: dict[str, int] = {}
    writer = None
    try:
        for frame in frames:
            table = frame.to_arrow()
            if writer is None:
                if len(set(table.schema.names)) != len(table.schema.names):
                    raise ValueError("duplicate output columns")
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


# ---- build --------------------------------------------------------------------


def build() -> dict:
    inputs = verify_inputs()
    OUT.mkdir(parents=True, exist_ok=True)
    lunar = SNAP / "diviner-l4"
    report = {"generatedAt": datetime.now(timezone.utc).isoformat(), "issue": 100,
              "inputs": [{"datasetId": e["datasetId"], "sourceUrl": e["sourceUrl"], "sha256": e["sha256"],
                          "bytes": e["bytes"], "license": e["license"]} for e in inputs],
              "runtimeStatus": "executed", "scientificStatus": "executed-unreviewed",
              "scope": "source-native decoding; label-declared filtering; max/min/range reduction over "
                       "the product's own local-time axis; no resampling, no inferred quantities",
              "outputs": {}}

    # 1. GCP: native cell x local-time table + per-cell tsurf summary
    # (single parse pass: each band is decoded once; native frame streams to
    # parquet, its summary is kept in memory for the summary table)
    native_path = OUT / "gcp-tbol-localtime.parquet"
    part = native_path.with_suffix(".part")
    writer = pq.ParquetWriter(part, native_schema(), compression="zstd")
    summaries, stats, rows, nulls = [], {}, 0, {}
    try:
        for band in GCP_BANDS:
            native, summary, band_stats = gcp_band(band, lunar)
            writer.write_table(native.to_arrow())
            summaries.append(summary)
            stats[band] = band_stats
            rows += native.height
            for key, count in zip(native.columns, native.null_count().row(0)):
                nulls[key] = nulls.get(key, 0) + count
            print(f"GCP {band}: {native.height:,} rows, {band_stats}", flush=True)
    finally:
        writer.close()
    os.replace(part, native_path)
    native_meta = {"rows": rows, "nullCounts": nulls, "sha256": sha256(native_path),
                   "bytes": native_path.stat().st_size}
    native_meta.update({
        "body": "Moon", "quantity": "tbol: mission-cumulative-average bolometric brightness temperature (K)",
        "nativeGrid": {"latitudeBins": 360, "longitudeBins": 720, "localTimeBins": LT_BINS,
                       "decode": {"latitudeDeg": "-89.75 + 0.5*clat_bin",
                                  "longitudeDeg": "-179.75 + 0.5*clon_bin",
                                  "localTimeHours": "0.125 + 0.25*ltim_bin"}},
        "timeSupport": "static; cumulative average of all nadir observations 2009-07-05 to 2015-04-01 "
                       "per 0.25 h local-time bin; not monthly, not instantaneous",
        "missingReason": {"tbol": "source-invalid-constant = label invalid_constant -9998 (value not usable); "
                                  "source-no-observation = label unknown_constant -9999 (bin had no observations)"},
        "quality": "only label-declared sentinels excluded; binning checked against label geometry"})
    report["outputs"]["gcp-tbol-localtime.parquet"] = native_meta

    summaries = [s for s in summaries]
    summary = pl.concat(summaries).sort("clat_bin", "clon_bin").with_columns(
        pl.col("clat_bin").cast(pl.Float32).mul(0.5).sub(89.75).alias("clat"),
        pl.col("clon_bin").cast(pl.Float32).mul(0.5).sub(179.75).alias("clon"))
    summary = summary.select("clat", "clon", "tsurf_max", "tsurf_min", "tsurf_range", "support_bins",
                             "clat_bin", "clon_bin").with_columns(gcp_missing_reason())
    if summary.height != 360 * 720 or summary.select("clat_bin", "clon_bin").n_unique() != summary.height:
        raise ValueError("GCP summary cells are not a unique full 0.5-degree grid")
    if summary["tsurf_max"].is_null().sum() != (summary["support_bins"] == 0).sum():
        raise ValueError("GCP summary nulls disagree with zero-support cells")
    summary_meta = write_batches(OUT / "gcp-tsurf.parquet", iter([summary]))
    summary_meta.update({
        "body": "Moon", "quantity": "tsurf_max/tsurf_min/tsurf_range (K): maximum, minimum and range over the "
                  "96 local-time bins of the cumulative-average bolometric map; support_bins counts valid bins of 96",
        "surrogateNote": "each local-time bin holds the 2009-2015 cumulative average, so tsurf_max underestimates the "
                         "extreme of single-orbit retrievals; range is over binned means, not same-day extrema",
        "timeSupport": "static; derived from one mission-cumulative product, no time axis of its own",
        "missingReason": {"tsurf_max": "no-valid-source-bins", "tsurf_min": "no-valid-source-bins",
                          "tsurf_range": "no-valid-source-bins"},
    })
    report["outputs"]["gcp-tsurf.parquet"] = summary_meta

    # 2. CF position (STD_CF) and 3. rock abundance (RA_AVG)
    for stem, (_, value_column) in GDR_EXPECTED.items():
        img = lunar / f"{stem}.img"
        spec = read_gdr_label(img.with_suffix(".lbl"), img, stem)
        output = {"cf_position": "cf-position.parquet", "rock_abund_div": "rock-abundance.parquet"}[value_column]
        meta = write_batches(OUT / output, gdr_batches(img, spec, value_column))
        meta.update({
            "body": "Moon", "quantity": GDR_QUANTITY[value_column], "valueColumn": value_column,
            "nativeGrid": {"lines": spec["shape"][0], "samples": spec["shape"][1],
                           "decode": {"latitudeDeg": f"{spec['maxLat']} - (source_line + 0.5) / 32",
                                      "longitudeDeg": "(source_sample + 0.5) / 32"},
                           "mapping": "simple cylindrical, planetocentric (label IMAGE_MAP_PROJECTION)",
                           "resolution": "32 pixels/degree"},
            "coverage": {"minLat": spec["minLat"], "maxLat": spec["maxLat"]},
            "timeSupport": GDR_TIME[value_column],
            "missingReason": {value_column: "source-missing-constant = label MISSING_CONSTANT -32768; "
                                            "outside-label-derived-range (not expected; counted in report)"},
            "quality": "label-declared DN scaling (DN * SCALING_FACTOR) applied verbatim; the product's own "
                       "declared QA (night-time incidence constraints for RA) is in the source product, not re-applied"})
        report["outputs"][output] = meta
        print(stem, meta["rows"], meta["sha256"], flush=True)

    # 4. PRP north
    spec = resolve_offset(lunar / "dlre_prp_north.xml", read_character_label(lunar / "dlre_prp_north.xml"))
    if [f["name"] for f in spec["fields"]] != PRP_FIELDS or spec["records"] != 2_880_000:
        raise ValueError("Diviner PRP north layout changed; review before preparing")
    expected_units = ["km"] * 9 + ["degree", "degree", "km", "Kelvin", "Kelvin", "meter"]
    if [f.get("unit") for f in spec["fields"]] != expected_units:
        raise ValueError("Diviner PRP north units changed; review before preparing")
    if spec["fields"][-1]["invalid"] != [-999.0]:
        raise ValueError("Diviner PRP north ice_depth exclusion changed; review before preparing")
    north_meta = write_batches(OUT / "diviner-north-prp.parquet",
                               character_batches(lunar / "dlre_prp_north.tab", spec))
    north_meta.update({
        "fields": spec["fields"], "body": "Moon",
        "coordinates": "source triangle vertices, km; planetocentric positive-east centres; 1737.4 km reference sphere",
        "timeSupport": "annual model statistics from thermal model fits to the first mapping-orbit year; "
                       "no observation year attached",
        "temperatureMeaning": "temp_avg: model annual average 2 cm below surface; temp_max: model annual maximum at "
                              "surface; Kelvin",
        "iceMeaning": "calculated ice-stability depth, not measured ice occurrence/depth; source -999 excluded when "
                      "calculated depth exceeds 2.8738 m; zero retained",
        "missingReason": {"ice_depth": "source exclusion: calculated stability depth exceeds 2.8738 m"},
        "quality": "only label-declared exclusion applied; map positions carry ~0.3-0.5 deg uncertainty (PR #87); "
                   "CAVEAT: 65,481 records carry an undocumented ice_depth sentinel -1.00000 (not the -999.0 "
                   "exclusion and not a physical depth); kept verbatim, no invented QA — downstream users should "
                   "treat ice_depth in [-1, 0) as unexplained source values"})
    report["outputs"]["diviner-north-prp.parquet"] = north_meta

    report["gcpBandStats"] = stats
    (OUT / "preparation-report.json").write_text(json.dumps(report, indent=2) + "\n")
    return report


GDR_QUANTITY = {
    "cf_position": "Christiansen Feature position (um): wavelength of the mid-infrared emissivity maximum near 8 um, "
                   "a silicate-composition proxy; model of channel 3/4/5 emissivity, not a direct measurement",
    "rock_abund_div": "rock abundance (fraction 0-1): areal fraction of rocks estimated by the Bandfield et al. 2011 "
                      "two-component thermal fit to night-time channels 6/7/8; model estimate, underestimates rocks "
                      "<~0.5 m",
}
GDR_TIME = {
    "cf_position": "static cumulative map, observations 2009-07-05 to 2010-11-30, best local time per longitude",
    "rock_abund_div": "static cumulative map, night-time local times 19:30-05:30, observations 2009-07-05 to "
                      "2010-11-30, the ten local-time bins averaged",
}


# ---- check --------------------------------------------------------------------


def _load_output(name: str) -> pl.DataFrame:
    return pl.read_parquet(OUT / name)


def check() -> None:
    verify_inputs()
    report = json.loads((OUT / "preparation-report.json").read_text())
    for name, meta in report["outputs"].items():
        path = OUT / name
        if sha256(path) != meta["sha256"] or path.stat().st_size != meta["bytes"]:
            raise ValueError(f"output hash/size mismatch: {name}")
        if pq.ParquetFile(path).metadata.num_rows != meta["rows"]:
            raise ValueError(f"output row count mismatch: {name}")
        print(f"PASS {name}: hash, size, rows", flush=True)

    lunar = SNAP / "diviner-l4"
    native = _load_output("gcp-tbol-localtime.parquet")
    if native.height != 360 * 720 * LT_BINS:
        raise ValueError("GCP native table is not the full 0.5-degree x 96-bin grid")
    if native.select("clat_bin", "clon_bin", "ltim_bin").n_unique() != native.height:
        raise ValueError("GCP native keys duplicated")
    if native["tbol"].is_null().sum() != native["missing_reason"].is_not_null().sum():
        raise ValueError("GCP native missing_reason disagrees with tbol nulls")
    allowed = {"source-invalid-constant", "source-no-observation"}
    if set(native["missing_reason"].drop_nulls().unique()) - allowed:
        raise ValueError("unexpected GCP native missing reason")
    if native.filter((pl.col("tbol") <= 0) | (pl.col("tbol") > 500))["tbol"].count():
        raise ValueError("GCP tbol outside physical range (0, 500] K")

    summary = _load_output("gcp-tsurf.parquet")
    if summary.height != 360 * 720 or summary.select("clat_bin", "clon_bin").n_unique() != summary.height:
        raise ValueError("GCP summary keys duplicated or incomplete")
    if summary.filter((pl.col("tsurf_max") < pl.col("tsurf_min")) |
                      ((pl.col("tsurf_max") - pl.col("tsurf_min") - pl.col("tsurf_range")).abs() > 1e-3)).height:
        raise ValueError("GCP summary range inconsistent with max/min")
    if summary.filter(pl.col("tsurf_max").is_not_null() &
                      ((pl.col("tsurf_max") > 500) | (pl.col("tsurf_min") < 0))).height:
        raise ValueError("GCP summary temperature outside physical range")
    for row in summary.filter(pl.col("tsurf_max").is_null()).head(200).iter_rows(named=True):
        keys = sorted(json.loads(row["missing_reason"]).keys())
        if keys != ["tsurf_max", "tsurf_min", "tsurf_range"]:
            raise ValueError(f"GCP summary missing_reason keys wrong: {keys}")
    for row in summary.filter(pl.col("tsurf_max").is_not_null()).head(200).iter_rows(named=True):
        if json.loads(row["missing_reason"]) != {}:
            raise ValueError("GCP summary missing_reason set on a complete row")

    spot = 0
    spot += check_gcp_cell(lunar, "00n10n", 5.25, -179.75)       # equatorial band
    spot += check_gcp_cell(lunar, "10s00s", -5.25, 100.25)       # southern band
    spot += check_gcp_cell(lunar, "80n90n", 89.75, -30.25)       # polar band
    spot += check_gcp_support(lunar)
    spot += check_gdr(lunar, "dgdr_std_cf_clc_cyl_032_img", "cf-position.parquet", "cf_position", 2.0, 10.0)
    spot += check_gdr(lunar, "dgdr_ra_avg_cyl_032_img", "rock-abundance.parquet", "rock_abund_div", 0.0, 1.1)
    spot += check_prp_north(lunar)
    if spot < 7:
        raise ValueError("expected at least 7 raw spot checks")
    print(f"PASS spot checks: {spot} raw comparisons", flush=True)


def check_gcp_cell(lunar: Path, band: str, clat: float, clon: float) -> int:
    """Compare one cell's 96 local-time values against the raw band table (spot check)."""
    spec = read_gcp_label(lunar / f"global_cumul_avg_cyl_{band}_002.xml")
    tab = lunar / f"global_cumul_avg_cyl_{band}_002.tab"
    cell = pl.DataFrame({
        "clat": _gcp_column(tab, spec, "center_latitude"),
        "clon": _gcp_column(tab, spec, "center_longitude"),
        "ltim": _gcp_column(tab, spec, "local_time"),
        "tbol": _gcp_column(tab, spec, "tbol"),
    }).filter((pl.col("clat") == clat) & (pl.col("clon") == clon))
    if cell.height != LT_BINS:
        raise ValueError(f"raw GCP cell {band} {clat}/{clon} does not have {LT_BINS} local-time rows")
    clat_bin, clon_bin = int(round((clat + 89.75) / 0.5)), int(round((clon + 179.75) / 0.5))
    prepared = pl.scan_parquet(OUT / "gcp-tbol-localtime.parquet").filter(
        (pl.col("clat_bin") == clat_bin) & (pl.col("clon_bin") == clon_bin)).sort("ltim_bin").collect()
    if prepared.height != LT_BINS:
        raise ValueError(f"prepared GCP cell {band} {clat}/{clon} does not have {LT_BINS} rows")
    raw_sorted = cell.sort("ltim")
    ltim_bin_expected = np.rint((raw_sorted["ltim"].to_numpy() - 0.125) / 0.25).astype(np.int64)
    if not np.array_equal(prepared["ltim_bin"].to_numpy(), ltim_bin_expected):
        raise ValueError("local-time bin mapping changed")
    raw_values = raw_sorted["tbol"].to_numpy()
    prepared_values = prepared["tbol"].to_numpy().astype(np.float64)
    mismatches = sum(1 for raw_value, prepared_value in zip(raw_values, prepared_values)
                     if (raw_value in (INVALID, UNKNOWN)) != (prepared_value != prepared_value)
                     or (raw_value not in (INVALID, UNKNOWN) and abs(prepared_value - raw_value) > 1e-3))
    if mismatches:
        raise ValueError(f"GCP cell {band} {clat}/{clon}: {mismatches} local-time values differ from raw")
    summary = pl.scan_parquet(OUT / "gcp-tsurf.parquet").filter(
        (pl.col("clat_bin") == clat_bin) & (pl.col("clon_bin") == clon_bin)).collect()
    if summary.height != 1:
        raise ValueError(f"no summary row for GCP cell {band} {clat}/{clon}")
    row = summary.row(0, named=True)
    valid = raw_values[(raw_values != INVALID) & (raw_values != UNKNOWN)]
    if valid.size == 0:
        if any(row[k] is not None for k in ("tsurf_max", "tsurf_min", "tsurf_range")) or row["support_bins"] != 0:
            raise ValueError("all-invalid raw cell should have null tsurf values and support 0")
    else:
        if abs(row["tsurf_max"] - valid.max()) > 1e-3 or abs(row["tsurf_min"] - valid.min()) > 1e-3 \
                or int(row["support_bins"]) != valid.size:
            raise ValueError("GCP summary disagrees with raw cell max/min/support")
    print(f"PASS GCP cell {band} clat={clat} clon={clon}: {LT_BINS} local-time values match raw", flush=True)
    return 1


def check_gcp_support(lunar: Path) -> int:
    """One band's total valid-bin count equals the same count recomputed from raw (spot check)."""
    band = "00n10n"
    spec = read_gcp_label(lunar / f"global_cumul_avg_cyl_{band}_002.xml")
    tab = lunar / f"global_cumul_avg_cyl_{band}_002.tab"
    tbol = _gcp_column(tab, spec, "tbol")
    raw_valid = int(((tbol != INVALID) & (tbol != UNKNOWN)).sum())
    prepared_valid = pl.scan_parquet(OUT / "gcp-tbol-localtime.parquet").filter(
        (pl.col("clat_bin") >= 180) & (pl.col("clat_bin") < 200)).select(
        pl.col("tbol").count()).collect().item()
    if prepared_valid != raw_valid:
        raise ValueError(f"GCP band {band} valid count differs from raw: {prepared_valid} vs {raw_valid}")
    print(f"PASS GCP band {band}: valid-bin count {raw_valid:,} matches recompute", flush=True)
    return 1


def check_gdr(lunar: Path, stem: str, output: str, value_column: str, low: float, high: float,
              line: int = 1000, sample: int = 5000) -> int:
    """Compare two pixels plus the full null count against the raw IMG (spot check)."""
    img = lunar / f"{stem}.img"
    spec = read_gdr_label(img.with_suffix(".lbl"), img, stem)
    reality = np.memmap(img, dtype="<i2", mode="r", shape=spec["shape"])
    raw_dn = int(reality[line, sample])
    prepared = pl.scan_parquet(OUT / output).filter(
        (pl.col("source_line") == line) & (pl.col("source_sample") == sample)).collect()
    if prepared.height != 1:
        raise ValueError(f"no row for {output} at {line}/{sample}")
    row = prepared.row(0, named=True)
    if row["source_dn"] != raw_dn:
        raise ValueError(f"{output} DN disagrees with raw at {line}/{sample}")
    expected_value = raw_dn * spec["scale"] if raw_dn != spec["missing"] else None
    if (row[value_column] is None) != (expected_value is None) or (
            expected_value is not None and abs(row[value_column] - expected_value) > 1e-6):
        raise ValueError(f"{output} value disagrees with raw scaling at {line}/{sample}")
    raw_missing = int((np.asarray(reality) == spec["missing"]).sum())
    prepared_missing = pl.scan_parquet(OUT / output).filter(
        pl.col("missing_reason") == "source-missing-constant").select(pl.len()).collect().item()
    prepared_nulls = pl.scan_parquet(OUT / output).filter(pl.col(value_column).is_null()).select(
        pl.len()).collect().item()
    if prepared_nulls != prepared_missing + pl.scan_parquet(OUT / output).filter(
            pl.col("missing_reason") == "outside-label-derived-range").select(pl.len()).collect().item():
        raise ValueError(f"{output} null count inconsistent with its missing reasons")
    if prepared_missing != raw_missing:
        raise ValueError(f"{output} null count {prepared_missing} != raw missing count {raw_missing}")
    value = pl.read_parquet(OUT / output, columns=[value_column])[value_column].drop_nulls()
    if value.len() and (value.min() < spec["derivedMin"] - 1e-6 or value.max() > spec["derivedMax"] + 1e-6):
        raise ValueError(f"{output} values outside label derived range")
    if value.len() and (value.min() < low or value.max() > high):
        raise ValueError(f"{output} values outside advisory physical range [{low}, {high}]")
    print(f"PASS {output}: pixel ({line},{sample}) + null count {prepared_missing:,} match raw", flush=True)
    return 1


def check_prp_north(lunar: Path, record: int = 1_500_000) -> int:
    """Compare one triangle row against the raw PRP north table (spot check)."""
    spec = resolve_offset(lunar / "dlre_prp_north.xml", read_character_label(lunar / "dlre_prp_north.xml"))
    raw = np.memmap(lunar / "dlre_prp_north.tab", dtype=np.uint8, mode="r")
    offset = spec["offset"] + record * spec["recordBytes"]
    expected = {}
    for field in spec["fields"]:
        raw_text = bytes(raw[offset + field["start"]:offset + field["start"] + field["length"]]).decode("ascii")
        value = float(raw_text)
        expected[field["name"]] = None if value in field["invalid"] else value
    prepared = pl.scan_parquet(OUT / "diviner-north-prp.parquet").filter(
        pl.col("source_record") == record).collect()
    if prepared.height != 1:
        raise ValueError(f"no prepared row for north PRP record {record}")
    row = prepared.row(0, named=True)
    for name, value in expected.items():
        got = row[name]
        if (got is None) != (value is None) or (value is not None and abs(got - value) > 1e-9):
            raise ValueError(f"north PRP {name} disagrees with raw at record {record}")
    temp = pl.read_parquet(OUT / "diviner-north-prp.parquet", columns=["temp_avg", "temp_max"])
    for name in ("temp_avg", "temp_max"):
        column = temp[name].drop_nulls()
        if column.len() and (column.min() <= 0 or column.max() > 500):
            raise ValueError(f"north PRP {name} outside physical range (0, 500] K")
    ice = pl.read_parquet(OUT / "diviner-north-prp.parquet", columns=["ice_depth", "temp_avg", "temp_max"])
    ice = ice.filter(pl.col("ice_depth").is_not_null())
    if ice["ice_depth"].len() and ice["temp_avg"].min() <= 0:
        raise ValueError("north PRP non-positive temp_avg")
    negatives = ice.filter(pl.col("ice_depth") < 0).group_by("ice_depth").len()
    if negatives.height:
        print(f"NOTE north PRP ice_depth: {negatives} undocumented negative source values kept as-is "
              "(only -999.0 is label-declared; no invented QA applied)", flush=True)
    print("PASS diviner-north-prp.parquet: record "
          f"{record} values match raw; temp ranges OK", flush=True)
    lat = pl.read_parquet(OUT / "diviner-north-prp.parquet", columns=["tri_clat"])["tri_clat"]
    if lat.min() < 0:
        raise ValueError("north PRP contains southern-hemisphere triangles")
    return 1


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
