"""Prepare source-native Mars ice-context data (#106).

Two static, dataset-native map families. No resampling, no H3, no daily or
8-day granules, no similarity or cross-body comparison.

1. Odyssey GRS suite (PDS Geosciences, ODY-M-GRS-5-ELEMENTS-V1.0): the
   published derived element concentration maps (water-equivalent hydrogen
   from the gamma/neutron-suite inversion, thorium, potassium and the K/Th
   ratio map). The water map is model-derived (see catalog/dataset.cat in
   the snapshot), and only the label's NOT_APPLICABLE_CONSTANT becomes null.
2. SWIM ice consistency layers (PSI, Morgan et al. 2021), when the source
   host is reachable; swim_status() records live evidence. During the
   #106 session start swim.psi.edu returned HTTP 523 (origin down) on
   every attempt; those probes are recorded, not hidden.

Missing stays missing: each prepared row carries a JSON `missing_reason`
whose keys are exactly the null value columns of that row.

Run: python -m p0ingest.mars_ice fetch|build|check|drive
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess  # nosec B404 - fixed rclone argv only
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import polars as pl

from .snapshots import REPO, SNAP, fetch, load_manifest, sha256

OUT_GRS = SNAP / "_derived" / "planetary" / "ody-grs-pds"
OUT_SWIM = SNAP / "_derived" / "planetary" / "swim-mars-ice"
GRS = "https://pds-geosciences.wustl.edu/ody/ody-m-grs-5-elements-v1/odgm_xxxx/"
SWIM_HOME = "https://swim.psi.edu/"

# PDS stem -> prepared file name. weh = water-equivalent hydrogen from the
# mapped H2O concentration; sr = smoothed (10-deg boxcar, re-binned 5x5).
GRS_PRODUCTS = {
    "h2o_sr_5x5": "grs-weh-5deg-smoothed.parquet",
    "h2o_2x2": "grs-weh-2deg-unsmoothed.parquet",
    "th_sr_5x5": "grs-th-5deg-smoothed.parquet",
    "k_sr_5x5": "grs-k-5deg-smoothed.parquet",
    "kvsth_sr_5x5": "grs-kth-ratio-5deg-smoothed.parquet",
}
# Published bin-centre layouts (label-driven names kept as fallbacks).
EXPECTED_BINS = {
    "grs-weh-5deg-smoothed.parquet": (5.0, -87.5, 87.5, 2.5, 357.5),
    "grs-th-5deg-smoothed.parquet": (5.0, -87.5, 87.5, 2.5, 357.5),
    "grs-k-5deg-smoothed.parquet": (5.0, -87.5, 87.5, 2.5, 357.5),
    "grs-kth-ratio-5deg-smoothed.parquet": (5.0, -87.5, 87.5, 2.5, 357.5),
    "grs-weh-2deg-unsmoothed.parquet": (2.0, -87.0, 87.0, 1.0, 359.0),
}
# Our sanity bounds around the published values (documented in the report);
# the only source-declared exclusion is NOT_APPLICABLE_CONSTANT = 9999.999.
RANGES = {
    "grs-weh-5deg-smoothed.parquet": (-15.0, 100.0),
    "grs-weh-2deg-unsmoothed.parquet": (-15.0, 100.0),
    "grs-th-5deg-smoothed.parquet": (0.0, 5.0),
    "grs-k-5deg-smoothed.parquet": (0.0, 5000.0),
    "grs-kth-ratio-5deg-smoothed.parquet": (0.0, 20000.0),
}
NA = 9999.999
NA_REASON = "source-na-9999.999"


# stem -> PDS subdirectory under data/
GRS_DIRS = {"h2o_sr_5x5": "smoothed", "th_sr_5x5": "smoothed", "k_sr_5x5": "smoothed",
            "kvsth_sr_5x5": "smoothed", "h2o_2x2": "unsmoothed/2x2"}


def sources():
    urls = [GRS + name for name in ("aareadme.txt", "catalog/dataset.cat",
                                    "catalog/ref.cat", "voldesc.cat")]
    for stem in GRS_PRODUCTS:
        for ext in ("lbl", "tab"):
            urls.append(GRS + "data/" + GRS_DIRS[stem] + "/" + stem + "." + ext)
    yield from (("ody-grs-pds", u) for u in urls)
    yield from (("swim-mars-ice", u) for u in swim_sources())


def swim_sources():
    """SWIM URLs resolved by probe; empty while the host is unreachable."""
    return []


def fetch_grs() -> None:
    for stem in GRS_PRODUCTS:
        for ext in ("lbl", "tab"):
            fetch("ody-grs-pds", GRS + "data/" + GRS_DIRS[stem] + "/" + stem + "." + ext)
    for name in ("aareadme.txt", "catalog/dataset.cat", "catalog/ref.cat", "voldesc.cat"):
        fetch("ody-grs-pds", GRS + name)


def read_grs_label(path: Path) -> dict:
    """Minimal PDS3 TABLE label reader for the GRS five-column ASCII tables."""
    text = path.read_text()
    if "ODY-M-GRS-5-ELEMENTS-V1.0" not in text:
        raise ValueError(f"unsupported GRS data set in {path.name}")

    def field(pattern: str) -> str:
        found = re.search(pattern, text)
        if not found:
            raise ValueError(f"label field missing in {path.name}: {pattern}")
        return found.group(1)

    rows = int(field(r"ROWS\s*=\s*(\d+)"))
    record_bytes = int(field(r"RECORD_BYTES\s*=\s*(\d+)"))
    columns = []
    for block in re.findall(r"OBJECT\s*=\s*COLUMN(.*?)END_OBJECT\s*=\s*COLUMN", text, re.S):
        def col_field(pattern: str, b=block):
            found = re.search(pattern, b)
            if not found:
                raise ValueError(f"column field missing in {path.name}: {pattern}")
            return found.group(1)
        name = col_field(r'NAME\s*=\s*"([^"]+)"')
        start = int(col_field(r"START_BYTE\s*=\s*(\d+)"))
        nbytes = int(col_field(r"\bBYTES\s*=\s*(\d+)"))
        unit = col_field(r'UNIT\s*=\s*"([^"]+)"')
        invalid = float(col_field(r"NOT_APPLICABLE_CONSTANT\s*=\s*([\d.]+)")) \
            if "NOT_APPLICABLE_CONSTANT" in block else None
        if start < 1 or nbytes < 1 or start + nbytes - 2 > record_bytes + 1:
            raise ValueError(f"column {name} outside record in {path.name}")
        columns.append({"name": name, "start": start - 1, "bytes": nbytes,
                        "unit": unit, "invalid": invalid})
    if len(columns) != 5 or len({c["name"] for c in columns}) != 5:
        raise ValueError(f"expected five distinct declared columns in {path.name}")
    return {"rows": rows, "recordBytes": record_bytes, "columns": columns}


# target value-column names per prepared file, in label column order
VALUE_COLUMNS = {
    "grs-weh-5deg-smoothed.parquet": ["weh_wt_pct", "weh_sigma_wt_pct", "weh_sigma_cfs_wt_pct"],
    "grs-weh-2deg-unsmoothed.parquet": ["weh_wt_pct", "weh_sigma_wt_pct", "weh_sigma_cfs_wt_pct"],
    "grs-th-5deg-smoothed.parquet": ["th_ppm", "th_sigma_ppm", "th_sigma_cfs_ppm"],
    "grs-k-5deg-smoothed.parquet": ["k_ppm", "k_sigma_ppm", "k_sigma_cfs_ppm"],
    "grs-kth-ratio-5deg-smoothed.parquet": ["kth_ratio_ppm_as_labelled", "kth_ratio_sigma_ppm_as_labelled",
                                            "kth_ratio_sigma_cfs_ppm_as_labelled"],
}


def read_grs_table(path: Path, spec: dict) -> pl.DataFrame:
    """Label-driven fixed-width decode of one GRS concentration table (NA kept)."""
    raw = np.memmap(path, dtype=np.uint8, mode="r")
    # PDS3 RECORD_BYTES here counts payload + CR; the file carries CR LF per row,
    # so the true stride is RECORD_BYTES + 1. Derive it from the file and verify.
    stride = path.stat().st_size // spec["rows"]
    if path.stat().st_size != spec["rows"] * stride or stride < spec["recordBytes"] + 1:
        raise ValueError(f"GRS table byte count differs from label: {path.name}")
    data = {"source_row": np.arange(spec["rows"], dtype=np.uint32)}
    for column in spec["columns"]:
        name = column["name"].lower().replace(" ", "_")
        values = np.ndarray((spec["rows"],), dtype=f'S{column["bytes"]}', buffer=raw,
                            offset=column["start"], strides=(stride,)).astype(np.float64)
        if not np.isfinite(values).all():
            raise ValueError(f"non-finite source field {column['name']} in {path.name}")
        data[name] = values
    return pl.DataFrame(data)


def clean_grs(table: pl.DataFrame, file_name: str) -> pl.DataFrame:
    """Rename to the stable value columns; only the label NA constant becomes null."""
    target = VALUE_COLUMNS[file_name]
    arrays = [table["concentration"].to_numpy(), table["sigma"].to_numpy(),
              table["sigma_with_cfs"].to_numpy()]
    data = {}
    for name, array in zip(target, arrays):
        series = pl.Series(name, array).set(pl.Series(array == NA), None)
        data[name] = series
    null_masks = [array == NA for array in arrays]
    reasons = []
    for row in range(table.height):
        nulls = {name: NA_REASON for name, is_na in zip(target, [m[row] for m in null_masks]) if is_na}
        reasons.append(json.dumps(nulls, sort_keys=True) if nulls else None)
    return pl.DataFrame({
        "source_row": table["source_row"],
        "latitude": table["latitude"],
        "longitude": table["longitude"],
        "source_concentration": table["concentration"],
        "source_sigma": table["sigma"],
        "source_sigma_with_cfs": table["sigma_with_cfs"],
        **data,
        "missing_reason": pl.Series(reasons),
    })


def write_parquet(path: Path, frame: pl.DataFrame) -> dict:
    part = path.with_suffix(".part")
    frame.write_parquet(part, compression="zstd")
    os.replace(part, path)
    return {"rows": frame.height, "sha256": sha256(path), "bytes": path.stat().st_size}


def verify_inputs() -> list[dict]:
    entries = {e["sourceUrl"]: e for e in load_manifest()["entries"]}
    checked = []
    for dataset, url in sources():
        entry = entries.get(url)
        if entry is None or entry["datasetId"] != dataset:
            raise ValueError(f"missing snapshot entry: {url}")
        path = REPO / entry["localPath"]
        if path.stat().st_size != entry["bytes"] or sha256(path) != entry["sha256"]:
            raise ValueError(f"input hash/size mismatch: {path}")
        checked.append(entry)
    return checked


def _near_set(values: np.ndarray, expected: np.ndarray, tol: float = 1e-6) -> bool:
    if len(values) != len(expected):
        return False
    return bool(np.allclose(np.sort(values), np.sort(expected), rtol=0, atol=tol))


def _expected_grid(file_name: str) -> tuple[np.ndarray, np.ndarray]:
    step, lat0, lat1, lon0, lon1 = EXPECTED_BINS[file_name]
    return (np.arange(lat0, lat1 + 1e-9, step), np.arange(lon0, lon1 + 1e-9, step))


def product_meta(file_name: str, spec: dict, stem: str) -> dict:
    return {"body": "Mars",
            "key": ["latitude", "longitude"],
            "valueColumns": VALUE_COLUMNS[file_name],
            "sourceUnits": [c["unit"] for c in spec["columns"]],
            "sourceProduct": stem,
            "sourceDataset": "ODY-M-GRS-5-ELEMENTS-V1.0",
            "productVersion": "2.0",
            "timeSupport": "observations 2002-06-04 to 2005-04-03; static published map.",
            "modelStatus": "model-derived mapping product: concentrations are an inversion against "
                           "forward-modelled counts with water/iron correction factors "
                           "(catalog/dataset.cat); not a direct measurement",
            "sensingDepth": "order of the top ~1 m of regolith (gamma-line moment ~tens of cm; the "
                            "neutron spectrometer and HEND sample deeper). The archive does not state "
                            "a metre value; this is a literature property of the technique "
                            "(Boynton et al. 2007, dataset.cat references), not a per-pixel number.",
            "coverage": "dataset.cat masks non-radioactive species (including H2O) to exclude polar "
                        "regions; bins outside coverage keep the published NA and stay null.",
            "missingReason": NA_REASON,
            "quality": "only the label NOT_APPLICABLE_CONSTANT (9999.999) becomes null; published "
                       "negative concentrations (background subtracted beyond signal) are retained "
                       "exactly as published; sigma and sigma-with-correction-factor columns are "
                       "retained unchanged as the published uncertainty layers"}


def build() -> dict:
    inputs = verify_inputs()
    OUT_GRS.mkdir(parents=True, exist_ok=True)
    report = {"generatedAt": datetime.now(timezone.utc).isoformat(), "inputs": inputs,
              "runtimeStatus": "executed", "scientificStatus": "executed-unreviewed",
              "issue": "#106",
              "scope": "source-native derived-map decoding; only the label NA becomes null; "
                       "no resampling, no H3, no similarity or cross-body comparison",
              "outputs": {}}
    for stem, file_name in GRS_PRODUCTS.items():
        spec = read_grs_label(SNAP / "ody-grs-pds" / (stem + ".lbl"))
        table = clean_grs(read_grs_table(SNAP / "ody-grs-pds" / (stem + ".tab"), spec), file_name)
        latitudes, longitudes = _expected_grid(file_name)
        if not _near_set(table["latitude"].unique().to_numpy(), latitudes) or \
                not _near_set(table["longitude"].unique().to_numpy(), longitudes):
            raise ValueError(f"published bin-centre layout changed: {file_name}")
        if table.height != spec["rows"] or table["source_row"].n_unique() != spec["rows"] or \
                table.select(["latitude", "longitude"]).unique().height != table.height:
            raise ValueError(f"row count or duplicate (latitude, longitude) keys: {file_name}")
        result = write_parquet(OUT_GRS / file_name, table)
        result.update(product_meta(file_name, spec, stem))
        report["outputs"][file_name] = result
    (OUT_GRS / "preparation-report.json").write_text(json.dumps(report, indent=2) + "\n")
    return report


def _spot_picks(n_rows: int) -> list[int]:
    """Deterministic 5-row sample spread across the table."""
    quarter = n_rows // 4
    return [quarter, 2 * quarter, 3 * quarter - 1, n_rows // 3, n_rows - 2]


def check() -> None:
    verify_inputs()
    report = json.loads((OUT_GRS / "preparation-report.json").read_text())
    spot_checks = 0
    for name, meta in report["outputs"].items():
        path = OUT_GRS / name
        if sha256(path) != meta["sha256"] or path.stat().st_size != meta["bytes"]:
            raise ValueError(f"output hash/size mismatch: {name}")
        table = pl.read_parquet(path)
        target = meta["valueColumns"]
        if table.select(["latitude", "longitude"]).unique().height != table.height:
            raise ValueError(f"duplicate (latitude, longitude) keys: {name}")
        if table.height != meta["rows"]:
            raise ValueError(f"row count mismatch: {name}")
        keys = table.select(["latitude", "longitude", "missing_reason"])
        rows = list(table.select(target + ["source_row"]).iter_rows(named=True))
        for row in list(table.drop(["source_row"]).iter_rows(named=True)):
            try:
                reasons = set(json.loads(row["missing_reason"])) if row["missing_reason"] else set()
            except json.JSONDecodeError as exc:
                raise ValueError(f"missing_reason is not JSON in {name}") from exc
            nulls = {k for k, v in row.items() if k != "missing_reason" and v is None}
            if reasons != nulls:
                raise ValueError(f"missing_reason keys != null value columns in {name}: {reasons} vs {nulls}")
        low, high = RANGES[name]
        bad = table.filter(pl.col(target[0]).is_not_null() &
                           ((pl.col(target[0]) < low) | (pl.col(target[0]) > high))).height
        if bad:
            raise ValueError(f"{bad} values outside documented plausibility range in {name}")
        if not ((table["source_concentration"] == NA).to_numpy()
                == table[target[0]].is_null().to_numpy()).all():
            raise ValueError(f"label NA and nulls disagree in {name}")
        # >= 5 raw spot checks per product: independent whitespace-split parse
        stem = meta["sourceProduct"]
        raw = (SNAP / "ody-grs-pds" / (stem + ".tab")).read_text().splitlines()
        if len(raw) != meta["rows"]:
            raise ValueError(f"raw table row count changed: {stem}")
        for row_index in _spot_picks(len(raw)):
            parts = raw[row_index].split()
            row = table.row(row_index, named=True)
            if int(row["source_row"]) != row_index:
                raise ValueError(f"source_row misaligned in {name} at {row_index}")
            if len(parts) != 5:
                raise ValueError(f"unexpected raw column count in {stem} at {row_index}")
            for column, parsed in zip(("latitude", "longitude"), parts[0:2]):
                if abs(row[column] - float(parsed)) > 1e-9:
                    raise ValueError(f"spot check coordinate mismatch in {name} row {row_index}")
            for column, parsed in zip(("source_concentration", "source_sigma",
                                       "source_sigma_with_cfs"), parts[2:5]):
                if abs(row[column] - float(parsed)) > 1e-9:
                    raise ValueError(f"spot check raw value mismatch in {name} row {row_index}")
            spot_checks += 1
        print(f"PASS {name}: {meta['rows']:,} rows; hash, size, keys, ranges, missing reasons, 5 spot checks",
              flush=True)
    if spot_checks < 25:
        raise ValueError(f"expected >= 25 spot checks (5 per product), got {spot_checks}")


def swim_status() -> dict:
    """Live HTTP probe of the SWIM host, recorded as plain evidence."""
    import requests
    from .snapshots import UA
    result = {"url": SWIM_HOME, "probedAt": datetime.now(timezone.utc).isoformat()}
    try:
        r = requests.get(SWIM_HOME, headers=UA, timeout=30)
        result["httpStatus"] = r.status_code
        result["bytes"] = len(r.content)
    except Exception as exc:  # noqa: BLE001 - the failure itself is the evidence
        result["httpStatus"] = None
        result["error"] = repr(exc)
    return result


def drive() -> None:
    """Copy raw + derived outputs to the shared Drive and verify checksums."""
    targets = [("data/snapshots/ody-grs-pds", "snapshots/ody-grs-pds"),
               ("data/snapshots/_derived/planetary/ody-grs-pds",
                "snapshots/_derived/planetary/ody-grs-pds")]
    for local_rel, remote_rel in targets:
        local = REPO / local_rel
        if not local.exists():
            continue
        subprocess.run(["rclone", "copy", str(local), "ccdrive:" + remote_rel], check=True)
        subprocess.run(["rclone", "check", "--one-way", "--checksum", str(local),
                        "ccdrive:" + remote_rel], check=True)


def main():
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument("action", choices=["fetch", "build", "check", "drive", "swim_status"])
    action = parser.parse_args().action
    if action == "fetch":
        for dataset, url in sources():
            print(fetch(dataset, url), flush=True)
    elif action == "build":
        report = build()
        for name, meta in report["outputs"].items():
            print(name, meta.get("rows"), meta.get("sha256"), flush=True)
    elif action == "drive":
        drive()
    elif action == "swim_status":
        print(json.dumps(swim_status()), flush=True)
    else:
        check()


if __name__ == "__main__":
    main()
