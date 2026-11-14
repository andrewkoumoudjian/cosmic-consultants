"""Prepare source-native Lunar Prospector GRS elemental abundance maps (#101).

Gamma-ray spectral-unmixing weight fractions (Prettyman et al. 2006) decoded
from the PDS detached labels of LP-L-GRS-5-ELEM-ABUNDANCE-V1.0, on the
archive's 2, 5 and 20 degree equal-area pixels. Published error-matrix
columns are kept raw; the added 1-sigma columns are the label-declared
square root of the diagonal terms (label text: "The square root of the
diagonal of the error matrix gives the propagated uncertainty").

No neutron-derived hydrogen map is produced. Both neutron instruments exist
in PDS only as time series: LEND EDR/RDR daily binary tables and LP NS
mission-long 8/32-second counting-rate tables (LP-L-NS-3-RDR-V1.0). No PDS
map product exists for either, and converting a count rate into a suppression
percentage or a hydrogen/WEH wt% would be a new scientific product. Missing
stays missing: h_wt_neutron from LEND/LP-NS is recorded as a gap.

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
# Physical ranges (Prettyman et al. 2006, LP GRS global maps). The dataset
# catalog documents the ~21.4-23.9 amu average-atomic-mass range; lunar
# literature bounds the oxides (FeO to ~0.25 g/g in mare, TiO2 to ~0.1,
# anorthosite Al2O3 ~0.35). The 2-degree product is explicitly flagged by the
# archive as poorly evaluated outside FeO/TiO2/K/Th, so its ranges are
# widened and its tabulated neutron number density (~1e-4 g/cm3) sits two
# orders of magnitude above the 5/20-degree tables (~1.5e-6) with no
# explanation in the archive documentation; values are kept as published.
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
# Key/coordinate columns: no physical range, never null in this archive.
ID_COLUMNS = ["pixel_index", "min_lat", "max_lat", "min_lon", "max_lon"]


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
        "readme.txt", "aareadme.txt", "catalog/edr_ds.cat", "catalog/rdr_ds.cat"))


def parse_label(path: Path) -> dict:
    """Minimal PDS3 detached-label reader for this archive's fixed tables."""
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
        # PDS names like E[0,0] become e0_0 to keep parquet column names plain.
        columns.append({
            "name": name.group(1).strip().lower().replace("[", "").replace("]", "").replace(",", "_"),
            "data_type": data_type.group(1),
            "start0": int(start.group(1)) - 1,
            "bytes": int(size.group(1)),
            "unit": unit.group(1) if unit else None,
        })
    return columns


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
    """Decode the fixed-length table into raw value columns plus per-row reasons."""
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
            # derived 1-sigma columns inherit the null state of their term
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
        "neutronHydrogen": ("NOT provided here: no PDS map product exists for LEND or the LP "
                            "neutron spectrometer; no count rate was converted into a wt% or "
                            "suppression percentage (gap, see preparation-report.json)"),
        "productId": label["productId"],
    }


def build() -> dict:
    inputs = verify_inputs()
    OUT.mkdir(parents=True, exist_ok=True)
    LEND_OUT.mkdir(parents=True, exist_ok=True)
    report = {
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "inputs": inputs,
        "runtimeStatus": "executed", "scientificStatus": "executed-unreviewed",
        "scope": ("source-native decoding of LP GRS elemental abundance maps and the "
                  "label-declared error-matrix diagonal; no resampling to Earth H3, no "
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
                         "EDR/RDR binary time-series tables only (readme.txt: 'raw, "
                         "uncalibrated, calibrated, derived, and ancillary data as binary "
                         "time series tables'). The aareadme product list (EDR_SCI, "
                         "RDR_RCHK/RSCI/DLD/DLX/ALD/ALF) contains no map product."),
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
    (OUT / "preparation-report.json").write_text(json.dumps(report, indent=2) + "\n")
    (LEND_OUT / "lend-pds-gap-report.json").write_text(json.dumps({
        "datasetId": "lend",
        "generatedAt": report["generatedAt"],
        "evidenceFiles": sorted(f"data/snapshots/lend/{p.name}" for p in sorted((SNAP / "lend").glob("*"))),
        "feature": "h_wt_neutron",
        **report["gapNeutronHydrogen"],
    }, indent=2) + "\n")
    return report


def _check_null_reason(frame: pl.DataFrame) -> None:
    """Each row's missing_reason JSON keys are exactly its null value columns."""
    value_columns = [c for c in frame.columns if c not in ID_COLUMNS and c != "missing_reason"]
    raw = {c: frame[c].to_list() for c in value_columns}
    for index, reason in enumerate(frame["missing_reason"].to_list()):
        keys = sorted(json.loads(reason))
        nulls = sorted(name for name in value_columns if raw[name][index] is None)
        if keys != nulls:
            raise ValueError(f"missing_reason keys do not match nulls at row {index}")


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
    gap = json.loads((LEND_OUT / "lend-pds-gap-report.json").read_text())
    if gap["datasetId"] != "lend" or not gap["conclusion"].startswith("No PDS map"):
        raise ValueError("neutron-hydrogen gap report missing or changed")
    for name in ("readme.txt", "aareadme.txt", "edr_ds.cat", "rdr_ds.cat"):
        if not (SNAP / "lend" / name).exists():
            raise ValueError(f"lend evidence file not snapshotted: {name}")
    print("PASS lend: PDS gap recorded, no neutron-H values used", flush=True)


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
    kreep = at(25.0, -55.0)   # Oceanus Procellarum, KREEP terrane
    if kreep is None or kreep["w_th"] is None or kreep["w_th"] <= 4.0:
        raise ValueError("Procellarum spot check: KREEP thorium not elevated")
    mare = at(9.0, 33.0)      # Mare Tranquillitatis
    if mare is None or mare["w_feo"] is None or mare["w_feo"] < 0.10:
        raise ValueError("Mare Tranquillitatis spot check: FeO not mare-elevated")
    farside = at(-15.0, 155.0)  # farside highlands
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
