"""Prepare source-native Lunar Prospector GRS & LRO LEND ALD maps (#101).

1. Lunar Prospector GRS elemental abundance maps (LP-L-GRS-5-ELEM-ABUNDANCE-V1.0):
   gamma-ray spectral-unmixing weight fractions (Prettyman et al. 2006) on the
   archive's 2, 5 and 20 degree equal-area pixels. Published error-matrix columns
   are kept raw; the added 1-sigma columns are the label-declared square root
   of the diagonal terms.

2. LRO LEND Averaged LEND Data maps (LEND_RDR_ALD in LRO-L-LEND-4/5-RDR-V1.0,
   archived in lro-l-lend-2-edr-v1/lrolen_0xxx): spatial relative neutron
   count-rate maps (ALDE 1 deg -80..80, ALDN 0.5 deg >80N, ALDS 0.5 deg <-80S)
   for both mission epochs (20090915 Nominal Mission, 20111211 Science Mission).
   Zero-exposure cells (exposure <= 0, PDS sentinel -1.0) become explicit nulls
   with JSON missing_reason.

Gap kept explicit: LEND ALD provides relative counting rates, NOT calibrated
hydrogen/WEH wt% or epithermal suppression percentages, and LP-NS (LP-L-NS-3-RDR-V1.0)
has only time-series files. Converting count rates to H wt% needs altitude,
solar-modulation and collimator-response modelling (out of ingest scope), so
h_wt_neutron stays missing in lend-pds-gap-report.json.

Run: python -m p0ingest.moon_nuclear fetch|build|check
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

OUT = SNAP / "_derived" / "planetary" / "lp-grs-pds"
LEND_OUT = SNAP / "_derived" / "planetary" / "lend"
LP = "https://pds-geosciences.wustl.edu/lunar/lp-l-grs-5-elem-abundance-v1/lp_9001/"
LEND = "https://pds-geosciences.wustl.edu/lro/lro-l-lend-2-edr-v1/lrolen_0xxx/"

PRODUCTS = {
    "2DEG": "lpgrs-high1-elem-abundance-2deg.parquet",
    "5DEG": "lpgrs-high1-elem-abundance-5deg.parquet",
    "20DEG": "lpgrs-high1-elem-abundance-20deg.parquet",
}
EXPECTED_ROWS = {"2DEG": 11306, "5DEG": 1790, "20DEG": 114}
EXPECTED_COLS = 61
DIAGONAL_1SIGMA = {  # error-matrix term -> derived 1-sigma column, per label text
    "e5_5": ("feo_1sigma_g_g", "g/g"),
    "e6_6": ("k_1sigma_ppm", "ppm"),
    "e7_7": ("th_1sigma_ppm", "ppm"),
}
RANGES = {
    "5DEG": {"am": (21.0, 24.5), "neutron_den": (5e-7, 2.5e-6),
             "w_mgo": (0.0, 0.20), "w_al2o3": (0.0, 0.40), "w_sio2": (0.30, 0.55),
             "w_cao": (0.0, 0.22), "tio2": (0.0, 0.10), "w_feo": (0.0, 0.30),
             "w_k": (0.0, 4000.0), "w_th": (0.0, 15.0), "w_u": (0.0, 4.0)},
    "20DEG": {"am": (21.0, 24.5), "neutron_den": (5e-7, 2.5e-6),
              "w_mgo": (0.0, 0.20), "w_al2o3": (0.0, 0.40), "w_sio2": (0.30, 0.55),
              "w_cao": (0.0, 0.22), "tio2": (0.0, 0.10), "w_feo": (0.0, 0.30),
              "w_k": (0.0, 4000.0), "w_th": (0.0, 15.0), "w_u": (0.0, 4.0)},
    "2DEG": {"am": (21.0, 24.5), "neutron_den": (0.0, 5e-4),
             "w_mgo": (0.0, 0.30), "w_al2o3": (0.0, 0.55), "w_sio2": (0.15, 0.70),
             "w_cao": (0.0, 0.35), "tio2": (0.0, 0.20), "w_feo": (0.0, 0.32),
             "w_k": (0.0, 5000.0), "w_th": (0.0, 15.0), "w_u": (0.0, 4.0)},
}
ID_COLUMNS = ["pixel_index", "min_lat", "max_lat", "min_lon", "max_lon"]

LEND_ALD_PRODUCTS = {
    ("alde", "20090915"): ("data/2009/20090915/lend_rdr_alde_20090915", 57600, (-80.0, 80.0), "1.0 deg x 1.0 deg (-80..80)"),
    ("aldn", "20090915"): ("data/2009/20090915/lend_rdr_aldn_20090915", 14400, (80.0, 90.0), "0.5 deg x 0.5 deg (80..90 N)"),
    ("alds", "20090915"): ("data/2009/20090915/lend_rdr_alds_20090915", 14400, (-90.0, -80.0), "0.5 deg x 0.5 deg (-90..-80 S)"),
    ("alde", "20111211"): ("data/2011/20111211/lend_rdr_alde_20111211", 57600, (-80.0, 80.0), "1.0 deg x 1.0 deg (-80..80)"),
    ("aldn", "20111211"): ("data/2011/20111211/lend_rdr_aldn_20111211", 14400, (80.0, 90.0), "0.5 deg x 0.5 deg (80..90 N)"),
    ("alds", "20111211"): ("data/2011/20111211/lend_rdr_alds_20111211", 14400, (-90.0, -80.0), "0.5 deg x 0.5 deg (-90..-80 S)"),
}
LEND_RECORD_BYTES = 310
LEND_EXPECTED_COLS = 23
LEND_DETECTORS = ("stn1", "setn", "stn2", "stn3", "csetn")
LEND_ID_COLUMNS = ["pixel_index", "start_utc_time", "stop_utc_time", "lat_deg", "lon_east_deg", "lon_deg"]
LEND_RECORD_DTYPE = np.dtype([
    ("start_utc", "S23"), ("stop_utc", "S23"),
    ("lat", ">f4"), ("lon", ">f4"), ("spare", ">f4"),
    ("stn1_exposure", ">f4"), ("stn1_rate", ">f4"), ("stn1_err", ">f4"),
    ("setn_exposure", ">f4"), ("setn_rate", ">f4"), ("setn_err", ">f4"),
    ("stn2_exposure", ">f4"), ("stn2_rate", ">f4"), ("stn2_err", ">f4"),
    ("stn3_exposure", ">f4"), ("stn3_rate", ">f4"), ("stn3_err", ">f4"),
    ("csetn_exposure", ">f4"), ("csetn_rate", ">f4"), ("csetn_err", ">f4"),
    ("shen_exposure", ">16f4"), ("shen_rate", ">16f4"), ("shen_err", ">16f4"),
])


def expected_column_names() -> list[str]:
    """Format-file column names in declared order, E[i,j] -> ei_j."""
    return (["pixel_index", "min_lat", "max_lat", "min_lon", "max_lon", "am",
             "neutron_den", "w_mgo", "w_al2o3", "w_sio2", "w_cao", "tio2",
             "w_feo", "w_k", "w_th", "w_u"]
            + [f"e{i}_{j}" for i in range(9) for j in range(i, 9)])


def sources():
    yield from (("lp-grs-pds", LP + path) for path in (
        "aareadme.txt", "catalog/dataset.cat", "index/index.tab",
        "data/LPGRS_ELEM_ABUNDANCE.FMT",
        *[f"data/LPGRS_HIGH1_ELEM_ABUNDANCE_{p}.{e}" for p in PRODUCTS for e in ("LBL", "TAB")]))
    yield from (("lend", LEND + path) for path in (
        "readme.txt", "aareadme.txt", "catalog/edr_ds.cat", "catalog/rdr_ds.cat",
        "label/lend_rdr_ald.fmt",
        *[f"{stem}.{ext}" for stem, *_ in LEND_ALD_PRODUCTS.values() for ext in ("lbl", "dat")]))


def parse_label(path: Path) -> dict:
    """Minimal PDS3 detached-label reader for LP GRS fixed tables."""
    text = path.read_text(encoding="utf-8", errors="strict")
    if "LP-L-GRS-5-ELEM-ABUNDANCE-V1.0" not in text:
        raise ValueError(f"unsupported dataset in {path.name}")

    def scalar(key: str) -> str | None:
        match = re.search(rf"^\s*{key}\s*=\s*[\"']?([^'\"\r\n]+)[\"']?\s*$", text, re.M)
        return match.group(1).strip() if match else None
    table = re.search(r"OBJECT\s*=\s*TABLE(.*?)END_OBJECT\s*=\s*TABLE", text, re.S)
    if table is None:
        raise ValueError(f"no TABLE object in {path.name}")
    rows = re.search(r"^\s*ROWS\s*=\s*(\d+)", table.group(1), re.M)
    columns = re.search(r"^\s*COLUMNS\s*=\s*(\d+)", table.group(1), re.M)
    if rows is None or columns is None:
        raise ValueError(f"label {path.name} does not declare ROWS/COLUMNS")
    structure = re.search(r'\^STRUCTURE\s*=\s*"([^"]+)"', text)
    return {
        "recordBytes": int(scalar("RECORD_BYTES")),
        "fileRecords": int(scalar("FILE_RECORDS")),
        "rows": int(rows.group(1)),
        "columns": int(columns.group(1)),
        "productId": scalar("PRODUCT_ID"),
        "dataSetId": scalar("DATA_SET_ID"),
        "startTime": scalar("START_TIME"),
        "stopTime": scalar("STOP_TIME"),
        "structure": structure.group(1) if structure else None,
    }


def parse_fmt(path: Path) -> list[dict]:
    """Read LPGRS_ELEM_ABUNDANCE.FMT: one dict per declared COLUMN."""
    text = path.read_text(encoding="utf-8", errors="strict")
    blocks = re.findall(r"OBJECT\s*=\s*COLUMN\s*(.*?)END_OBJECT\s*=\s*COLUMN", text, re.S)
    columns = []
    for block in blocks:
        name = re.search(r'NAME\s*=\s*"([^"]*)"', block)
        data_type = re.search(r"DATA_TYPE\s*=\s*(\S+)", block)
        start = re.search(r"START_BYTE\s*=\s*(\d+)", block)
        size = re.search(r"BYTES\s*=\s*(\d+)", block)
        unit = re.search(r'UNIT\s*=\s*"([^"]*)"', block)
        if not all((name, data_type, start, size)):
            raise ValueError("incomplete COLUMN block in format file")
        if data_type.group(1) not in ("ASCII_REAL", "ASCII_INTEGER"):
            raise ValueError(f"unsupported {name.group(1)} data type {data_type.group(1)}")
        columns.append({
            "name": name.group(1).strip().lower().replace("[", "").replace("]", "").replace(",", "_"),
            "data_type": data_type.group(1),
            "start0": int(start.group(1)) - 1,
            "bytes": int(size.group(1)),
            "unit": unit.group(1) if unit else None,
        })
    return columns


def parse_lend_fmt(path: Path) -> list[dict]:
    """Read lend_rdr_ald.fmt: 23 binary columns totalling 310 bytes."""
    text = path.read_text(encoding="utf-8", errors="strict")
    blocks = re.findall(r"OBJECT\s*=\s*COLUMN\s*(.*?)END_OBJECT\s*=\s*COLUMN", text, re.S)
    columns = []
    for block in blocks:
        name = re.search(r"NAME\s*=\s*([A-Z0-9_]+)", block)
        data_type = re.search(r"DATA_TYPE\s*=\s*(\S+)", block)
        start = re.search(r"START_BYTE\s*=\s*(\d+)", block)
        size = re.search(r"BYTES\s*=\s*(\d+)", block)
        items = re.search(r"ITEMS\s*=\s*(\d+)", block)
        if not all((name, data_type, start, size)):
            raise ValueError("incomplete COLUMN block in LEND ALD fmt")
        if data_type.group(1) not in ("CHARACTER", "IEEE_REAL"):
            raise ValueError(f"unsupported LEND column type {data_type.group(1)}")
        columns.append({
            "name": name.group(1).lower(),
            "data_type": data_type.group(1),
            "start0": int(start.group(1)) - 1,
            "bytes": int(size.group(1)),
            "items": int(items.group(1)) if items else 1,
        })
    if len(columns) != LEND_EXPECTED_COLS:
        raise ValueError(f"LEND ALD fmt columns {len(columns)} != {LEND_EXPECTED_COLS}")
    if sum(c["bytes"] for c in columns) != LEND_RECORD_BYTES:
        raise ValueError("LEND ALD fmt byte total != 310")
    return columns


def parse_lend_label(path: Path) -> dict:
    """Minimal PDS3 detached-label reader for LEND_RDR_ALD tables."""
    text = path.read_text(encoding="utf-8", errors="strict")
    if "LRO-L-LEND-4/5-RDR-V1.0" not in text:
        raise ValueError(f"unsupported dataset in {path.name}")

    def scalar(key: str) -> str | None:
        match = re.search(rf"^\s*{key}\s*=\s*[\"']?([^'\"\r\n]+)[\"']?\s*$", text, re.M)
        return match.group(1).strip() if match else None
    table = re.search(r"OBJECT\s*=\s*TABLE(.*?)END_OBJECT\s*=\s*TABLE", text, re.S)
    if table is None:
        raise ValueError(f"no TABLE object in {path.name}")
    rows = re.search(r"^\s*ROWS\s*=\s*(\d+)", table.group(1), re.M)
    columns = re.search(r"^\s*COLUMNS\s*=\s*(\d+)", table.group(1), re.M)
    row_bytes = re.search(r"^\s*ROW_BYTES\s*=\s*(\d+)", table.group(1), re.M)
    structure = re.search(r'\^STRUCTURE\s*=\s*"([^"]+)"', text)
    if not all((rows, columns, row_bytes, structure)):
        raise ValueError(f"incomplete TABLE metadata in {path.name}")
    return {
        "recordBytes": int(scalar("RECORD_BYTES")),
        "fileRecords": int(scalar("FILE_RECORDS")),
        "rowBytes": int(row_bytes.group(1)),
        "rows": int(rows.group(1)),
        "columns": int(columns.group(1)),
        "productId": scalar("PRODUCT_ID"),
        "productType": scalar("PRODUCT_TYPE"),
        "dataSetId": scalar("DATA_SET_ID"),
        "missionPhase": scalar("MISSION_PHASE_NAME"),
        "startTime": scalar("START_TIME"),
        "stopTime": scalar("STOP_TIME"),
        "tableFile": scalar(r"\^TABLE"),
        "structure": structure.group(1),
    }


def read_lend_ald(dat_path: Path, label: dict) -> pl.DataFrame:
    """Decode one fixed-length binary LEND_RDR_ALD map file."""
    if label["recordBytes"] != LEND_RECORD_BYTES or label["rowBytes"] != LEND_RECORD_BYTES:
        raise ValueError(f"{dat_path.name}: unexpected record bytes {label['recordBytes']}")
    if label["columns"] != LEND_EXPECTED_COLS or label["rows"] != label["fileRecords"]:
        raise ValueError(f"{dat_path.name}: unexpected label structure")
    expected_size = label["rows"] * LEND_RECORD_BYTES
    if dat_path.stat().st_size != expected_size:
        raise ValueError(f"{dat_path.name}: size {dat_path.stat().st_size} != {expected_size}")
    raw = np.fromfile(dat_path, dtype=LEND_RECORD_DTYPE)
    if len(raw) != label["rows"]:
        raise ValueError(f"{dat_path.name}: read {len(raw)} rows != {label['rows']}")
    if np.any(raw["shen_exposure"] > 0):
        raise ValueError(f"{dat_path.name}: unexpected non-zero SHEN exposure; update schema to keep it")
    lat = raw["lat"].astype(np.float64)
    lon_east = raw["lon"].astype(np.float64)
    lon_deg = ((lon_east + 180.0) % 360.0) - 180.0

    data: dict[str, object] = {
        "pixel_index": np.arange(len(raw), dtype=np.uint32),
        "start_utc_time": [s.decode("ascii").strip() for s in raw["start_utc"]],
        "stop_utc_time": [s.decode("ascii").strip() for s in raw["stop_utc"]],
        "lat_deg": lat,
        "lon_east_deg": lon_east,
        "lon_deg": lon_deg,
    }
    null_masks: dict[str, np.ndarray] = {}
    null_reasons: dict[str, np.ndarray] = {}
    value_cols: list[str] = []
    for det in LEND_DETECTORS:
        exp = raw[f"{det}_exposure"].astype(np.float64)
        rate = raw[f"{det}_rate"].astype(np.float64)
        err = raw[f"{det}_err"].astype(np.float64)
        exp_bad = (~np.isfinite(exp)) | (exp <= 0.0)
        rate_bad = exp_bad | (~np.isfinite(rate))
        err_bad = exp_bad | (~np.isfinite(err)) | (err < 0.0)

        exp_col, rate_col, err_col = f"{det}_exposure_s", f"{det}_rate_rel", f"{det}_err_rel"
        data[exp_col] = np.where(exp_bad, np.nan, exp)
        data[rate_col] = np.where(rate_bad, np.nan, rate)
        data[err_col] = np.where(err_bad, np.nan, err)
        for cname, mask in ((exp_col, exp_bad), (rate_col, rate_bad), (err_col, err_bad)):
            value_cols.append(cname)
            null_masks[cname] = mask
            r_arr = np.full(len(raw), "", dtype=object)
            r_arr[exp_bad] = "exposure-zero"
            nonfin = (~exp_bad) & mask
            if np.any(nonfin):
                r_arr[nonfin] = "non-finite-or-negative-err"
            null_reasons[cname] = r_arr

    # Fast reason JSON building grouped by identical per-row mask+reason signatures.
    reason_cache: dict[tuple[str, ...], str] = {}
    reasons: list[str] = []
    cols_sorted = sorted(value_cols)
    reason_lists = [null_reasons[c].tolist() for c in cols_sorted]
    for i in range(len(raw)):
        sig = tuple(reason_lists[j][i] for j in range(len(cols_sorted)))
        cached = reason_cache.get(sig)
        if cached is None:
            cached = json.dumps(
                {cols_sorted[j]: sig[j] for j in range(len(cols_sorted)) if sig[j]},
                sort_keys=True,
            )
            reason_cache[sig] = cached
        reasons.append(cached)

    frame = pl.DataFrame(data).with_columns(
        pl.col("pixel_index").cast(pl.UInt32),
        *[pl.when(pl.col(c).is_nan()).then(None).otherwise(pl.col(c)).alias(c) for c in value_cols],
        pl.Series("missing_reason", reasons, dtype=pl.String),
    )
    return frame


def _lend_meta(kind: str, epoch: str, label: dict, grid_desc: str) -> dict:
    return {
        "body": "Moon",
        "datasetId": "lend",
        "productId": label["productId"],
        "productType": label["productType"],
        "missionPhase": label["missionPhase"],
        "gridKind": kind,
        "epoch": epoch,
        "quantity": (
            "LEND averaged relative neutron counting rates (normalized by equatorial baseline, "
            "background-subtracted; LEND_RDR_ALD) and statistical error for STN1, SETN, STN2, "
            "STN3 and collimated CSETN1-4 detectors. NOT calibrated H/WEH wt% or suppression %."
        ),
        "pixelGeometry": (
            f"{grid_desc}; cell centre (lat_deg, lon_east_deg) from record fields "
            "LUNARCENTRIC_LATITUDE and LUNARCENTIC_EAST_LONGITUDE [0..360 E]; lon_deg in [-180..180]"
        ),
        "timeSupport": f"{label['missionPhase']} ({label['startTime']} to {label['stopTime']})",
        "quality": (
            "Zero-exposure bins (exposure <= 0, PDS -1.0 sentinel) mapped to null with missing_reason "
            "'exposure-zero'. All 16 SHEN channels have SHEN_EXPOSURE == 0 and -1.0 fill in every "
            "file (verified by assertion) and are omitted. Science Mission (20111211) lacks "
            "SETN/STN2/STN3 (exposure=0) and omits >~85 deg polar cells where elliptical orbit lacked exposure."
        ),
        "archiveNotes": (
            "lend_rdr_ald.fmt declares UNIT='COUNTS/SECOND' on *_EXPOSURE columns whose "
            "DESCRIPTION states seconds ('Exposure time..., sec'); stored here as *_exposure_s."
        ),
    }


def _decode(row: bytes, column: dict) -> tuple[float | int | None, str | None]:
    """One fixed-width slice to a number; returns (value, reason-if-null)."""
    text = row[column["start0"]:column["start0"] + column["bytes"]].decode("ascii").strip()
    if not text:
        return None, "empty-source-field"
    try:
        value = float(text) if column["data_type"] == "ASCII_REAL" else int(text)
    except ValueError:
        return None, "value-not-numeric"
    if not math.isfinite(value):
        return None, "non-finite-source-value"
    return value, None


def read_table(path: Path, columns: list[dict], label: dict) -> pl.DataFrame:
    """Decode the fixed-length LP GRS table into raw value columns plus per-row reasons."""
    if len(columns) != EXPECTED_COLS or label["columns"] != EXPECTED_COLS:
        raise ValueError("unexpected column count; review before preparing")
    record = label["recordBytes"]
    if path.stat().st_size != label["rows"] * record or label["rows"] != label["fileRecords"]:
        raise ValueError(f"{path.name}: file size differs from the detached label")
    raw = np.memmap(path, dtype=np.uint8, mode="r")
    ends = np.ndarray((label["rows"],), dtype="S2", buffer=raw, offset=record - 2, strides=(record,))
    if np.any(ends != b"\r\n"):
        raise ValueError(f"{path.name}: row delimiter changed")
    value_names = [c["name"] for c in columns] + [name for name, _ in DIAGONAL_1SIGMA.values()]
    values: dict[str, list] = {name: [] for name in value_names}
    reasons: list[str] = []
    with path.open("rb") as stream:
        for _ in range(label["rows"]):
            row = stream.read(record)
            row_reasons: dict[str, str] = {}
            for column in columns:
                value, reason = _decode(row, column)
                values[column["name"]].append(value)
                if reason is not None:
                    row_reasons[column["name"]] = reason
            for term, (name, _) in DIAGONAL_1SIGMA.items():
                value = values[term][-1]
                sigma = None if value is None else math.sqrt(value)
                values[name].append(sigma)
                row_reasons[name] = None if sigma is not None else "source-error-matrix-term-missing"
            reasons.append(json.dumps(
                {name: why for name, why in row_reasons.items() if why is not None}, sort_keys=True))
    frame = pl.DataFrame(values).with_columns(
        pl.col("pixel_index").cast(pl.UInt32),
        pl.Series("missing_reason", reasons, dtype=pl.String))
    return frame


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


def _units(fmt: list[dict]) -> dict:
    units = {c["name"]: c["unit"] for c in fmt}
    units.update({name: unit for _, (name, unit) in DIAGONAL_1SIGMA.items()})
    return units


def _meta(product: str, label: dict) -> dict:
    degree = product[:-3]
    return {
        "body": "Moon",
        "quantity": ("gamma-ray-derived elemental weight fractions (spectral unmixing, "
                     "Prettyman et al. 2006): oxides [g/g], K [ppm], Th [ppm]; w_u is U "
                     "[ppm] tied U=0.27*Th by the unmixing algorithm. 1-sigma columns are "
                     "the label-declared sqrt of the error-matrix diagonals: feo_1sigma_g_g "
                     "= sqrt(E[5,5]), k_1sigma_ppm = sqrt(E[6,6]), th_1sigma_ppm = sqrt(E[7,7])"),
        "pixelGeometry": ("archive equal-area pixels indexed west-to-east, south-to-north "
                          "from 0; boundaries are the min/max lat/lon columns of each row"),
        "spatialSupport": (f"{degree}-degree equal-area pixels; GRS footprint ~5 deg arc "
                           "length at 100 km altitude (label), so 2-deg pixels oversample "
                           "the instrument footprint"),
        "timeSupport": (f"static map of HIGH1-epoch data ({label['startTime']} to "
                        f"{label['stopTime']} per label); no month or year assigned"),
        "quality": ("values exactly as published; the full upper-triangle error matrix is "
                    "kept raw (columns e0_0..e8_8). Archive note for the 2-degree product "
                    "(dataset.cat): non-FeO/TiO2/K/Th oxides are poorly evaluated, 'caution "
                    "is recommended'"),
        "missingReason": "empty JSON per fully-populated row; keys would name the null value columns exactly",
        "neutronHydrogen": ("NOT provided here: LEND ALD carries relative neutron counting rates "
                            "(see lend/ outputs), and LP-NS has only time-series files; no count rate "
                            "was converted into a wt% or suppression percentage (gap, see lend-pds-gap-report.json)"),
        "productId": label["productId"],
    }


def _check_null_reason(frame: pl.DataFrame, id_cols: list[str] = ID_COLUMNS) -> None:
    """Each row's missing_reason JSON keys are exactly its null value columns."""
    value_columns = sorted(c for c in frame.columns if c not in id_cols and c != "missing_reason")
    null_sigs = frame.select(
        [pl.col(c).is_null().alias(c) for c in value_columns] + ["missing_reason"]
    )
    # Group by identical (missing_reason, null-column pattern) so 57k rows verify in milliseconds.
    grouped = null_sigs.unique()
    for row in grouped.iter_rows(named=True):
        keys = sorted(json.loads(row["missing_reason"]))
        nulls = sorted(c for c in value_columns if row[c])
        if keys != nulls:
            raise ValueError(f"missing_reason keys {keys} do not match nulls {nulls}")


def build() -> dict:
    inputs = verify_inputs()
    OUT.mkdir(parents=True, exist_ok=True)
    LEND_OUT.mkdir(parents=True, exist_ok=True)
    now_iso = datetime.now(timezone.utc).isoformat()
    report = {
        "generatedAt": now_iso,
        "inputs": [e for e in inputs if e["datasetId"] == "lp-grs-pds"],
        "runtimeStatus": "executed", "scientificStatus": "executed-unreviewed",
        "scope": ("source-native decoding of LP GRS elemental abundance maps and LEND ALD "
                  "relative neutron count-rate maps; no resampling to Earth H3, no "
                  "count-rate-to-hydrogen conversion, no analogy quantities"),
        "outputs": {},
        "archiveObservations": [
            ("The 2-degree table's NEUTRON_DEN column (declared 'Neutron number "
             "density g/cm3' in the shared format file) runs ~5.8e-05..1.9e-04 g/cm3, "
             "about 100x the 5- and 20-degree tables (~6e-07..1.9e-06). Values are "
             "kept exactly as published; the archive documentation (aareadme.txt, "
             "dataset.cat, FMT) does not explain the difference, and no conversion "
             "was applied."),
            ("2-degree MgO/Al2O3/SiO2/CaO have poorer precision than the 5- and "
             "20-degree tables (dataset.cat Limitations: 'caution is recommended in "
             "using 2-degree elemental abundances other than FeO, TiO2, K, and Th')."),
        ],
        "gapNeutronHydrogen": {
            "datasets": ["lend", "lp-grs-pds neutron-spectrometer products"],
            "feature": "h_wt_neutron",
            "evidence": {
                "lend": ("PDS Geosciences LRO bundle lro-l-lend-2-edr-v1/lrolen_0xxx holds "
                         "LEND_RDR_ALD spatial relative count-rate maps (now decoded under "
                         "data/snapshots/_derived/planetary/lend/), NOT calibrated hydrogen/WEH "
                         "wt% or epithermal suppression percentages."),
                "lp-ns": ("LP-L-NS-3-RDR-V1.0 index (index/INDEX.TAB) lists 15 neutron "
                          "spectrometer products, all 8- or 32-second counting-rate and "
                          "position time-series files; no binned map product."),
            },
            "conclusion": ("No PDS map of epithermal-neutron suppression percentage or "
                           "hydrogen/WEH wt% exists for either instrument. Deriving one "
                           "needs altitude, solar-modulation and collimator-response "
                           "modelling - a new scientific product, out of ingest scope. "
                           "h_wt_neutron stays missing from this family."),
        },
    }
    fmt = parse_fmt(REPO / "data/snapshots/lp-grs-pds/LPGRS_ELEM_ABUNDANCE.FMT")
    names = [c["name"] for c in fmt]
    if names != expected_column_names():
        raise ValueError("format-file columns changed; review before preparing")
    missing_terms = [term for term in DIAGONAL_1SIGMA if term not in names]
    if missing_terms:
        raise ValueError(f"error-matrix diagonal terms missing from format file: {missing_terms}")
    for product, filename in PRODUCTS.items():
        label = parse_label(REPO / f"data/snapshots/lp-grs-pds/LPGRS_HIGH1_ELEM_ABUNDANCE_{product}.LBL")
        if label["productId"] != f"LPGRS_HIGH1_ELEM_ABUNDANCE_{product}":
            raise ValueError(f"{product}: label product id mismatch")
        if label["rows"] != EXPECTED_ROWS[product]:
            raise ValueError(f"{product}: row count changed; review before preparing")
        frame = read_table(REPO / f"data/snapshots/lp-grs-pds/LPGRS_HIGH1_ELEM_ABUNDANCE_{product}.TAB",
                           fmt, label)
        _check_null_reason(frame)
        out = OUT / filename
        part = out.with_suffix(".part")
        pq.write_table(frame.to_arrow().replace_schema_metadata(
            {"cosmic-consultants": json.dumps(_meta(product, label))}), part, compression="zstd")
        part.rename(out)
        reasons = {r if r else "valid": n for r, n in
                   frame.group_by("missing_reason").len().sort("missing_reason").iter_rows()}
        report["outputs"][filename] = {
            "rows": frame.height,
            "meta": _meta(product, label),
            "units": _units(fmt),
            "sha256": sha256(out), "bytes": out.stat().st_size,
            "nullCounts": {c: frame[c].null_count() for c in frame.columns if frame[c].null_count()},
            "reasonCounts": reasons,
        }

    # Build LEND ALD spatial count-rate tables
    parse_lend_fmt(SNAP / "lend" / "lend_rdr_ald.fmt")
    lend_report = {
        "generatedAt": now_iso,
        "datasetId": "lend",
        "inputs": [e for e in inputs if e["datasetId"] == "lend"],
        "runtimeStatus": "executed",
        "scientificStatus": "executed-unreviewed",
        "scope": (
            "source-native decoding of LRO LEND_RDR_ALD averaged relative neutron count-rate "
            "maps (ALDE, ALDN, ALDS; 20090915 Nominal and 20111211 Science epochs). No "
            "resampling to H3 and no count-rate-to-hydrogen conversion."
        ),
        "outputs": {},
        "gapNeutronHydrogen": report["gapNeutronHydrogen"],
    }
    for (kind, epoch), (stem, expected_rows, lat_bounds, grid_desc) in LEND_ALD_PRODUCTS.items():
        fname = Path(stem).name
        lbl_path = SNAP / "lend" / f"{fname}.lbl"
        dat_path = SNAP / "lend" / f"{fname}.dat"
        label = parse_lend_label(lbl_path)
        if label["rows"] != expected_rows:
            raise ValueError(f"{fname}: rows {label['rows']} != {expected_rows}")
        frame = read_lend_ald(dat_path, label)
        _check_null_reason(frame, LEND_ID_COLUMNS)
        lo_lat, hi_lat = lat_bounds
        if frame.filter((pl.col("lat_deg") < lo_lat) | (pl.col("lat_deg") > hi_lat)).height:
            raise ValueError(f"{fname}: lat_deg outside {lat_bounds}")
        out_name = f"lend-rdr-{kind}-{epoch}.parquet"
        out = LEND_OUT / out_name
        part = out.with_suffix(".part")
        meta = _lend_meta(kind, epoch, label, grid_desc)
        pq.write_table(frame.to_arrow().replace_schema_metadata(
            {"cosmic-consultants": json.dumps(meta)}), part, compression="zstd")
        part.rename(out)
        reasons = {r if r else "valid": n for r, n in
                   frame.group_by("missing_reason").len().sort("missing_reason").iter_rows()}
        lend_info = {
            "rows": frame.height,
            "meta": meta,
            "sha256": sha256(out),
            "bytes": out.stat().st_size,
            "nullCounts": {c: frame[c].null_count() for c in frame.columns if frame[c].null_count()},
            "reasonCounts": reasons,
        }
        lend_report["outputs"][out_name] = lend_info
        report["outputs"][f"lend/{out_name}"] = lend_info

    (OUT / "preparation-report.json").write_text(json.dumps(report, indent=2) + "\n")
    (LEND_OUT / "preparation-report.json").write_text(json.dumps(lend_report, indent=2) + "\n")
    (LEND_OUT / "lend-pds-gap-report.json").write_text(json.dumps({
        "datasetId": "lend",
        "generatedAt": report["generatedAt"],
        "evidenceFiles": sorted(f"data/snapshots/lend/{p.name}" for p in sorted((SNAP / "lend").glob("*"))),
        "feature": "h_wt_neutron",
        **report["gapNeutronHydrogen"],
    }, indent=2) + "\n")
    return report


def check() -> None:
    verify_inputs()
    report = json.loads((OUT / "preparation-report.json").read_text())
    fmt = parse_fmt(REPO / "data/snapshots/lp-grs-pds/LPGRS_ELEM_ABUNDANCE.FMT")
    for product, filename in PRODUCTS.items():
        label = parse_label(REPO / f"data/snapshots/lp-grs-pds/LPGRS_HIGH1_ELEM_ABUNDANCE_{product}.LBL")
        path = OUT / filename
        entry = report["outputs"][filename]
        if sha256(path) != entry["sha256"] or path.stat().st_size != entry["bytes"]:
            raise ValueError(f"output hash/size mismatch: {filename}")
        frame = pl.from_arrow(pq.ParquetFile(path).read())
        if frame.height != EXPECTED_ROWS[product] or label["rows"] != EXPECTED_ROWS[product]:
            raise ValueError(f"{filename}: row count mismatch")
        if frame["pixel_index"].n_unique() != frame.height or frame["pixel_index"].to_list() != sorted(frame["pixel_index"].to_list()):
            raise ValueError(f"{filename}: pixel_index not unique or not ordered")
        ranges = dict(RANGES["5DEG"])
        ranges.update(RANGES[product])
        for column, (low, high) in ranges.items():
            count = frame.filter((pl.col(column) < low) | (pl.col(column) > high)).height
            if count:
                raise ValueError(f"{filename}: {column} outside physical range ({count} rows)")
        for low_name, high_name in (("min_lat", "max_lat"), ("min_lon", "max_lon")):
            if frame.filter(pl.col(low_name) >= pl.col(high_name)).height:
                raise ValueError(f"{filename}: {low_name} >= {high_name}")
        if frame.filter((pl.col("min_lat") < -90) | (pl.col("max_lat") > 90) |
                        (pl.col("min_lon") < -180) | (pl.col("max_lon") > 180)).height:
            raise ValueError(f"{filename}: pixel bounds outside -90..90 / -180..180")
        for column in (c["name"] for c in fmt if c["name"] not in ID_COLUMNS):
            if frame[column].null_count():
                raise ValueError(f"{filename}: unexpected nulls in {column}")
        _check_null_reason(frame)
        for term, (name, _) in DIAGONAL_1SIGMA.items():
            bad = frame.filter(pl.col(name).is_null() |
                               ((pl.col(name) - pl.col(term).sqrt()).abs() > 1e-12)).height
            if bad:
                raise ValueError(f"{filename}: 1-sigma column {name} inconsistent with {term}")
        _spot_checks(product, frame, fmt)
        print(f"PASS {filename}: {frame.height:,} rows; hashes, ranges, reasons, spot checks", flush=True)

    lend_report = json.loads((LEND_OUT / "preparation-report.json").read_text())
    parse_lend_fmt(SNAP / "lend" / "lend_rdr_ald.fmt")
    for (kind, epoch), (stem, expected_rows, lat_bounds, _) in LEND_ALD_PRODUCTS.items():
        fname = Path(stem).name
        out_name = f"lend-rdr-{kind}-{epoch}.parquet"
        path = LEND_OUT / out_name
        entry = lend_report["outputs"][out_name]
        if sha256(path) != entry["sha256"] or path.stat().st_size != entry["bytes"]:
            raise ValueError(f"lend output hash/size mismatch: {out_name}")
        frame = pl.from_arrow(pq.ParquetFile(path).read())
        if frame.height != expected_rows:
            raise ValueError(f"{out_name}: row count {frame.height} != {expected_rows}")
        if frame["pixel_index"].n_unique() != frame.height or frame["pixel_index"].to_list() != sorted(frame["pixel_index"].to_list()):
            raise ValueError(f"{out_name}: pixel_index not unique or not ordered")
        lo_lat, hi_lat = lat_bounds
        if frame.filter((pl.col("lat_deg") < lo_lat) | (pl.col("lat_deg") > hi_lat)).height:
            raise ValueError(f"{out_name}: lat_deg outside {lat_bounds}")
        if frame.filter((pl.col("lon_east_deg") < 0) | (pl.col("lon_east_deg") > 360) |
                        (pl.col("lon_deg") < -180) | (pl.col("lon_deg") > 180)).height:
            raise ValueError(f"{out_name}: lon outside bounds")
        for det in LEND_DETECTORS:
            if frame.filter(pl.col(f"{det}_exposure_s").is_not_null() & (pl.col(f"{det}_exposure_s") <= 0)).height:
                raise ValueError(f"{out_name}: non-positive exposure for {det}")
            if frame.filter(pl.col(f"{det}_err_rel").is_not_null() & (pl.col(f"{det}_err_rel") < 0)).height:
                raise ValueError(f"{out_name}: negative error for {det}")
            # Relative count rate bounds check where populated
            if frame.filter(pl.col(f"{det}_rate_rel").is_not_null() &
                            ((pl.col(f"{det}_rate_rel") < -20.0) | (pl.col(f"{det}_rate_rel") > 100.0))).height:
                raise ValueError(f"{out_name}: {det}_rate_rel outside [-20, 100]")
        _check_null_reason(frame, LEND_ID_COLUMNS)
        _lend_spot_checks(SNAP / "lend" / f"{fname}.dat", frame, kind, epoch)
        print(f"PASS {out_name}: {frame.height:,} rows; hashes, ranges, reasons, 5 binary spot checks", flush=True)

    gap = json.loads((LEND_OUT / "lend-pds-gap-report.json").read_text())
    if gap["datasetId"] != "lend" or not gap["conclusion"].startswith("No PDS map"):
        raise ValueError("neutron-hydrogen gap report missing or changed")
    for name in ("readme.txt", "aareadme.txt", "edr_ds.cat", "rdr_ds.cat", "lend_rdr_ald.fmt"):
        if not (SNAP / "lend" / name).exists():
            raise ValueError(f"lend evidence file not snapshotted: {name}")
    print("PASS lend gap: LEND_RDR_ALD relative count rates prepared; no H/WEH wt% map exists", flush=True)


def _lend_spot_checks(dat_path: Path, frame: pl.DataFrame, kind: str, epoch: str) -> None:
    """Re-read 5 raw binary records via direct seek and compare to parquet."""
    keys = [0, frame.height // 4, frame.height // 2, 3 * frame.height // 4, frame.height - 1]
    with dat_path.open("rb") as stream:
        for key in keys:
            stream.seek(key * LEND_RECORD_BYTES)
            rec = np.frombuffer(stream.read(LEND_RECORD_BYTES), dtype=LEND_RECORD_DTYPE)[0]
            if abs(float(rec["lat"]) - float(frame["lat_deg"][key])) >= 1e-5:
                raise ValueError(f"{dat_path.name} row {key}: lat mismatch")
            if abs(float(rec["lon"]) - float(frame["lon_east_deg"][key])) >= 1e-5:
                raise ValueError(f"{dat_path.name} row {key}: lon mismatch")
            for det in LEND_DETECTORS:
                exp = float(rec[f"{det}_exposure"])
                got_exp = frame[f"{det}_exposure_s"][key]
                got_rate = frame[f"{det}_rate_rel"][key]
                if exp <= 0.0:
                    if got_exp is not None or got_rate is not None:
                        raise ValueError(f"{dat_path.name} row {key} {det}: expected null for zero exposure")
                else:
                    if abs(exp - float(got_exp)) > 1e-4 or abs(float(rec[f"{det}_rate"]) - float(got_rate)) > 1e-4:
                        raise ValueError(f"{dat_path.name} row {key} {det}: binary spot-check mismatch")
    if (kind, epoch) == ("alds", "20090915"):
        cabeus = frame.filter(((pl.col("lat_deg") + 84.75).abs() < 0.3) & ((pl.col("lon_east_deg") - 324.25).abs() < 0.3)).row(0, named=True)
        bg = frame.filter(((pl.col("lat_deg") + 80.25).abs() < 0.3) & ((pl.col("lon_east_deg") - 180.25).abs() < 0.3)).row(0, named=True)
        if cabeus["csetn_rate_rel"] >= bg["csetn_rate_rel"]:
            raise ValueError("LEND ALDS Cabeus PSR check: CSETN relative count rate not suppressed vs 80.25S bg")


def _spot_checks(product: str, frame: pl.DataFrame, columns: list[dict]) -> None:
    """Re-read 5 raw rows with plain IO (independent of the build code path)."""
    data_path = REPO / f"data/snapshots/lp-grs-pds/LPGRS_HIGH1_ELEM_ABUNDANCE_{product}.TAB"
    record = data_path.stat().st_size // frame.height
    keys = [0, frame.height // 4, frame.height // 2, 3 * frame.height // 4, frame.height - 1]
    with data_path.open("rb") as stream:
        for key in keys:
            stream.seek(key * record)
            row = stream.read(record)
            if row[-2:] != b"\r\n":
                raise ValueError("spot-check row lacks CRLF terminator")
            for column in columns:
                value, _ = _decode(row, column)
                got = frame[column["name"]][key]
                if value is not None and got is not None and float(value) != float(got):
                    raise ValueError(f"spot-check mismatch row {key} column {column['name']}")
    if product != "5DEG":
        return

    def at(lat: float, lon: float) -> dict | None:
        hit = frame.filter((pl.col("min_lat") <= lat) & (pl.col("max_lat") >= lat) &
                           (pl.col("min_lon") <= lon) & (pl.col("max_lon") >= lon))
        return hit.row(0, named=True) if hit.height else None
    kreep = at(25.0, -55.0)
    if kreep is None or kreep["w_th"] is None or kreep["w_th"] <= 4.0:
        raise ValueError("Procellarum spot check: KREEP thorium not elevated")
    mare = at(9.0, 33.0)
    if mare is None or mare["w_feo"] is None or mare["w_feo"] < 0.10:
        raise ValueError("Mare Tranquillitatis spot check: FeO not mare-elevated")
    farside = at(-15.0, 155.0)
    if farside is None or farside["w_feo"] is None or farside["w_feo"] >= 0.09 or farside["w_th"] >= 3.0:
        raise ValueError("farside-highlands spot check: FeO/Th not low")
    if not (21.0 <= frame["am"].min() and frame["am"].max() <= 24.5):
        raise ValueError("average atomic mass outside the documented ~21.4-23.9 amu range")


def main() -> None:
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
