"""Prepare source-native Moon spectral and radar maps (#102, W43).

Static (at-most-monthly) maps, source-native grids, declared quality
handling only. No resampling to H3, no scoring, no cross-body comparison.
Outputs live under data/snapshots/_derived/planetary/<datasetId>/ with a
preparation report per dataset.

- kaguya-mi-59mpp: FeO weight percent map (Lemelin et al. 2016, Kaguya MI
  Mineral Map "May 2016", JAXA / Univ. of Hawaii) at the USGS-published
  reduced 4 ppd grid (50N-50S). Gap: no Kaguya MI TiO2 abundance map is
  published on this host and the MI reflectance bands are only distributed
  at 512 ppd (~21-24 GB per band, above the shared 20 GB raw cap).
- minirf-pds: Mini-RF global circular polarization ratio mosaic, 32 ppd,
  S-band (2380 MHz) zoom-SAR, LRO-L-MRFLRO-5-GLOBAL-MOSAIC-V1.0.
- lroc-wac-global: USGS reduction (303 ppd) of the ASU LRO WAC global
  morphology mosaic, aggregated 101x101 -> 3 ppd boxcar with native support
  counts. Values are mean 8-bit grayscale DN = relative reflectance of the
  broadband visible WAC mosaic, NOT physical Lambert/bolometric albedo.
- lamp: LAMP GDR v1.0 H2O absorption feature depth (off-band/on-band albedo
  ratio) maps, north and south polar stereographic, 240 m/pixel, cumulative
  (static; no monthly version exists for the ratio maps). Off-band is
  155.57-189.57 nm, on-band is 129.57-155.57 nm. The feature-row name
  lya_offon is kept, with this exact wavelength record; the ratio is billed
  in PDS as a dimensionless H2O absorption feature depth, not Lyman-alpha.
- m3-pds: not prepared. Licence unresolved since audit #41 and no PDS
  published global derived band-depth map exists (only per-strip L1B/L2).
  No bytes fetched; recorded as a gap in reports and README.

MD5 cross-checks against source .md5 files where the archive publishes one.
Run: python -m p0ingest.moon_spectral fetch|build|check
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import re
from pathlib import Path

import numpy as np
import polars as pl
import pyarrow.parquet as pq
import rasterio
from rasterio.windows import Window

from .snapshots import REPO, SNAP, fetch, load_manifest, sha256

OUT = SNAP / "_derived" / "planetary"

USGS = "https://asc-pds-services.s3.us-west-2.amazonaws.com/mosaic/"
MINIRF = "https://pds-geosciences.wustl.edu/lro/lro-l-mrflro-5-global-mosaic-v1/lromrf_1001/data/32ppd/"
LAMP = "https://planetarydata.jpl.nasa.gov/img/data/lro/lamp/gdr/LROLAM_2001/DATA/RATIO/"
LAMP_CAT = "https://planetarydata.jpl.nasa.gov/img/data/lro/lamp/gdr/LROLAM_2001/CATALOG/"

KAGUYA_FEO_TIF = USGS + "Lunar_MI_mineral_maps/4ppd/Lunar_Kaguya_MIMap_MineralDeconv_FeOWeightPercent_50N50S.tif"
KAGUYA_FEO_MD5 = KAGUYA_FEO_TIF + ".md5"
KAGUYA_FEO_LBL = USGS + "Lunar_MI_mineral_maps/Lunar_Kaguya_MIMap_MineralDeconv_FeOWeightPercent_50N50S.lbl"
CPR_IMG = MINIRF + "global_cpr_32ppd_simp_0c.img"
CPR_LBL = MINIRF + "global_cpr_32ppd_simp_0c.lbl"
CPR_XML = MINIRF + "global_cpr_32ppd_simp_0c.xml"
WAC_TIF = USGS + "LRO_WAC_Mosaic_Global_303ppd.tif"
WAC_FGDC = WAC_TIF + ".xml"
LAMP_DSMAP = LAMP_CAT + "DSMAP_POLAR.CAT"
LAMP_GDR_DS = LAMP_CAT + "LAMP_GDR_DS.CAT"

MISSING = "source-missing-constant"
NOT_FINITE = "source-not-finite"
NODATA = "source-nodata"
NO_VALID = "no-valid-native-samples"

# Physical-plausibility bounds: values outside fail loudly, never clipped
# or filled (AGENTS.md rule 3: missing stays missing).
RANGES = {
    "feo_wt": (0.0, 120.0),         # stored algorithm output; kept as-is, see outlierNote
    "cpr_minirf": (-1.0e6, 1.0e6),  # power ratio; wide preparation-corruption guard, see
                                    # outlierNote in the report (producer ratio artifacts of
                                    # -2.4e4 .. 2.2e5 are kept as stored, never clipped)
    "albedo_wac_dn": (0.0, 255.0),  # mean of native 8-bit DN
    "lya_offon": (-5.0e7, 5.0e7),   # dimensionless ratio; wide preparation-corruption guard,
                                    # see outlierNote in the report (denominator-noise
                                    # artifacts of -2.5e7..6.4e6 are kept as stored)
}

TABLES = {
    "kaguya-mi-59mpp/kaguya-mi-feo-4ppd.parquet": {
        "columns": ["source_line", "source_sample", "feo_wt", "missing_reason"],
        "value": "feo_wt", "rows": 400 * 1440, "reasons": {NODATA}},
    "minirf-pds/minirf-cpr-32ppd.parquet": {
        "columns": ["source_line", "source_sample", "cpr_minirf", "missing_reason"],
        "value": "cpr_minirf", "rows": 5760 * 11520, "reasons": {MISSING, NOT_FINITE}},
    "lroc-wac-global/lroc-wac-albedo-3ppd.parquet": {
        "columns": ["source_line", "source_sample", "albedo_wac_dn", "native_sample_count", "missing_reason"],
        "value": "albedo_wac_dn", "rows": 540 * 1080, "reasons": set()},
    "lamp/lamp-gdr-ratio-albedo-80n.parquet": {
        "columns": ["source_line", "source_sample", "lya_offon", "missing_reason"],
        "value": "lya_offon", "rows": 2501 * 2501, "reasons": {NOT_FINITE}},
    "lamp/lamp-gdr-ratio-albedo-80s.parquet": {
        "columns": ["source_line", "source_sample", "lya_offon", "missing_reason"],
        "value": "lya_offon", "rows": 2501 * 2501, "reasons": {NOT_FINITE}},
}


def sources():
    yield "kaguya-mi-59mpp", KAGUYA_FEO_TIF
    yield "kaguya-mi-59mpp", KAGUYA_FEO_MD5
    yield "kaguya-mi-59mpp", KAGUYA_FEO_LBL
    yield "minirf-pds", CPR_IMG
    yield "minirf-pds", CPR_LBL
    yield "minirf-pds", CPR_XML
    yield "lroc-wac-global", WAC_TIF
    yield "lroc-wac-global", WAC_FGDC
    yield "lamp", LAMP + "LAMP_80n_240mpp_ratio_albed_01.img"
    yield "lamp", LAMP + "LAMP_80n_240mpp_ratio_albed_01.lbl"
    yield "lamp", LAMP + "LAMP_80s_240mpp_ratio_albed_01.img"
    yield "lamp", LAMP + "LAMP_80s_240mpp_ratio_albed_01.lbl"
    yield "lamp", LAMP_DSMAP
    yield "lamp", LAMP_GDR_DS


def pds3_scalar(label: str, key: str) -> str:
    match = re.search(rf"^\s*{key}\s*=\s*\"?([^\"<>\r\n]*?)\"?\s*(?:<[^>]*>)?\s*$", label, re.M)
    if match is None:
        raise ValueError(f"PDS3 label missing {key}")
    return match.group(1).strip()


def pds3_object(label: str, name: str) -> str:
    match = re.search(rf"OBJECT\s*=\s*{name}\s*\n(.*?)END_OBJECT\s*=\s*{name}", label, re.S)
    if match is None:
        raise ValueError(f"PDS3 label missing {name} object")
    return match.group(1)


def raw_path(dataset_id: str, url: str) -> Path:
    return SNAP / dataset_id / url.rsplit("/", 1)[-1].split("?")[0]


def read_pc_real(path: Path, lines: int, samples: int) -> np.ndarray:
    """Read a PDS3 PC_REAL image. PC_PRODUCT 'PC' prefix means little-endian
    (MSB_* would be big-endian); both Mini-RF and LAMP GDR label PC_REAL.
    Byte-count guard against a truncated download."""
    if path.stat().st_size != lines * samples * 4:
        raise ValueError(f"{path.name}: byte count differs from PDS3 label")
    return np.memmap(path, dtype="<f4", mode="r", shape=(lines, samples))


# A 64-bit MISSING_CONSTANT (-1.7976931e308) is not representable in the
# stored 32-bit real: producer-side double->float truncation saturates to
# -3.4028226550889e38 (just inside FLT_MAX). Any sample of |v| >= 1e38 is
# therefore that declared missing constant, never a physical value.
SENTINEL_ABS = 1e38


def real_frames(values: np.ndarray, name: str, reason: str, missing: bool = False):
    """Yield source-native frames: one row per stored sample; non-finite
    stored samples and (if missing) the declared MISSING_CONSTANT become
    null with missing_reason."""
    lines, samples = values.shape
    batch = max(1, 2_000_000 // samples)
    for start in range(0, lines, batch):
        block = np.array(values[start:start + batch], dtype=np.float64)
        height = block.shape[0]
        finite = np.isfinite(block).ravel()
        absent = np.zeros_like(finite)
        if missing:
            absent |= np.abs(block.ravel()) >= SENTINEL_ABS
        keep = finite & ~absent
        raw = block.ravel()
        raw[~keep] = 0.0
        why = np.where(absent & finite, MISSING, reason)
        frame = pl.DataFrame({
            "source_line": np.repeat(np.arange(start, start + height, dtype=np.uint16), samples),
            "source_sample": np.tile(np.arange(samples, dtype=np.uint16), height),
            "raw": pl.Series(raw),
        })
        yield frame.with_columns([
            pl.when(pl.Series(keep)).then(pl.col("raw")).otherwise(None).alias(name),
            pl.when(pl.Series(keep)).then(None).otherwise(pl.Series(why)).alias("missing_reason"),
        ]).drop("raw")


def mask_frame(lines: np.ndarray, samples: np.ndarray, values: np.ndarray, valid: np.ndarray,
               name: str, reason: str) -> pl.DataFrame:
    """Frame for GeoTIFF-backed tables with a declared valid mask."""
    mask = pl.Series(valid.ravel())
    raw = np.where(valid, values, 0.0).ravel()
    frame = pl.DataFrame({
        "source_line": np.repeat(lines, len(samples)),
        "source_sample": np.tile(samples, len(lines)),
        "raw": pl.Series(raw),
    })
    return frame.with_columns([
        pl.when(mask).then(pl.col("raw")).otherwise(None).alias(name),
        pl.when(mask).then(None).otherwise(pl.lit(reason)).alias("missing_reason"),
    ]).drop("raw")


def write_batches(path: Path, frames) -> dict:
    path.parent.mkdir(parents=True, exist_ok=True)
    part = path.with_name(path.name + ".part")
    rows = 0
    nulls: dict = {}
    reasons: dict = {}
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
            for reason, count in frame.group_by("missing_reason").len().iter_rows():
                key = str(reason) if reason is not None else "valid"
                reasons[key] = reasons.get(key, 0) + count
    finally:
        if writer is not None:
            writer.close()
    if rows == 0:
        raise ValueError("source has zero rows")
    os.replace(part, path)
    return {"rows": rows, "nullCounts": nulls, "reasonCounts": reasons,
            "sha256": sha256(path), "bytes": path.stat().st_size}


def verify_source_md5(md5_path: Path, payload: Path) -> str:
    token = md5_path.read_text().split()[0].strip().lower()
    digest = hashlib.md5()
    with payload.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    if token != digest.hexdigest():
        raise ValueError(f"source md5 mismatch for {payload.name}")
    return token


def spot_key(values: np.ndarray, line: int, sample: int) -> float | None:
    raw = float(values[line, sample])
    return raw if np.isfinite(raw) else None


def assert_reason_contract(frame: pl.DataFrame, value: str) -> None:
    broken = frame.filter(pl.col(value).is_null() != pl.col("missing_reason").is_not_null()).height
    if broken:
        raise ValueError(f"missing_reason contract broken for {value}: {broken} rows")


def check_minirf_label(path: Path) -> dict:
    text = path.read_text()
    if pds3_scalar(text, "DATA_SET_ID") != "LRO-L-MRFLRO-5-GLOBAL-MOSAIC-V1.0":
        raise ValueError("Mini-RF product family changed")
    if pds3_scalar(text, "TARGET_NAME") != "MOON":
        raise ValueError("Mini-RF target changed")
    img = pds3_object(text, "IMAGE")
    if [pds3_scalar(img, key) for key in ("LINES", "LINE_SAMPLES", "SAMPLE_BITS", "SAMPLE_TYPE")] \
            != ["5760", "11520", "32", "PC_REAL"]:
        raise ValueError("Mini-RF image layout changed; review before preparing")
    missing = float(pds3_scalar(img, "MISSING_CONSTANT"))
    if missing != -1.7976931e308:
        raise ValueError("Mini-RF missing constant changed; review before preparing")
    proj = pds3_object(text, "IMAGE_MAP_PROJECTION")
    if pds3_scalar(proj, "MAP_PROJECTION_TYPE") != "SIMPLE CYLINDRICAL":
        raise ValueError("Mini-RF projection changed")
    if [pds3_scalar(proj, key) for key in ("CENTER_LATITUDE", "CENTER_LONGITUDE", "A_AXIS_RADIUS")] \
            != ["0.0", "0.0", "1737.4"]:
        raise ValueError("Mini-RF projection parameters changed")
    return {"lines": 5760, "samples": 11520, "frequency_hz": float(pds3_scalar(text, "CENTER_FREQUENCY").split()[0])}


def parse_lamp_label(path: Path, side: str) -> dict:
    text = path.read_text()
    if pds3_scalar(text, "DATA_SET_ID") != "LRO-L-LAMP-5-GDR-V1.0":
        raise ValueError("LAMP volume changed")
    img = pds3_object(text, "IMAGE")
    if [pds3_scalar(img, key) for key in ("LINES", "LINE_SAMPLES", "SAMPLE_BITS", "SAMPLE_TYPE")] \
            != ["2501", "2501", "32", "PC_REAL"]:
        raise ValueError("LAMP ratio map layout changed; review before preparing")
    description_match = re.search(r'DESCRIPTION\s*=\s*"(.*?)"', img, re.S)
    description = description_match.group(1).replace("\r\n", " ") if description_match else ""
    if "off-band to on-band albedo ratio" not in description:
        raise ValueError("LAMP ratio map meaning changed; review before preparing")
    proj = pds3_object(text, "IMAGE_MAP_PROJECTION")
    center = float(pds3_scalar(proj, "CENTER_LATITUDE"))
    if center != {"n": 90.0, "s": -90.0}[side] or pds3_scalar(proj, "MAP_PROJECTION_TYPE") != "POLAR STEREOGRAPHIC":
        raise ValueError(f"LAMP {side} map projection changed")
    if [pds3_scalar(proj, key) for key in ("MAP_SCALE", "MAP_RESOLUTION")] != ["240", "126.347"]:
        raise ValueError("LAMP map scale changed")
    return {"lines": 2501, "samples": 2501, "center_latitude": center}


def dataset_report(dataset_id: str, inputs: list[dict]) -> dict:
    return {
        "generatedAt": dt.datetime.now(dt.timezone.utc).isoformat(),
        "workOrder": "issue #102 (W43) Moon spectral and radar maps",
        "datasetId": dataset_id,
        "runtimeStatus": "executed",
        "scientificStatus": "executed-unreviewed",
        "scope": "source-native decoding and declared quality handling only; no resampling to "
                 "H3, no scoring, no cross-body comparison, no inferred target bands",
        "inputs": [entry for entry in inputs if entry["datasetId"] == dataset_id],
        "outputs": {},
        "gaps": [],
    }


def save_report(dataset_id: str, report: dict) -> None:
    directory = OUT / dataset_id
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "preparation-report.json").write_text(json.dumps(report, indent=2) + "\n")


def verify_inputs() -> list[dict]:
    entries = {entry["sourceUrl"]: entry for entry in load_manifest()["entries"]}
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


def build_kaguya(inputs: list[dict]) -> None:
    payload = raw_path("kaguya-mi-59mpp", KAGUYA_FEO_TIF)
    md5_path = raw_path("kaguya-mi-59mpp", KAGUYA_FEO_MD5)
    label_path = raw_path("kaguya-mi-59mpp", KAGUYA_FEO_LBL)
    verify_source_md5(md5_path, payload)
    label = label_path.read_text()
    label_meta = {
        "labelDataSetId": pds3_scalar(label, "DataSetId"),
        "productVersion": pds3_scalar(label, "ProductVersionId"),
        "producer": pds3_scalar(label, "ProducerInstitutionName"),
        "reference": pds3_scalar(label, "ProducerFullName"),
    }
    if label_meta["productVersion"] != "May 2016" or "Lemelin" not in label_meta["reference"]:
        raise ValueError("Kaguya MI FeO product identity changed; review before preparing")
    with rasterio.open(payload) as ds:
        if (ds.count, ds.width, ds.height) != (1, 1440, 400):
            raise ValueError(f"Kaguya 4ppd grid changed: {(ds.count, ds.width, ds.height)}")
        if abs(ds.transform.a - 0.25) > 1e-9 or abs(ds.transform.f - 50.0) > 1e-6 \
                or abs(ds.transform.c + 180.0) > 1e-9:
            raise ValueError("Kaguya 4ppd geotransform changed; review before preparing")
        declared = ds.read_masks(1) > 0
        data = ds.read(1).astype(np.float64)
        nodata = ds.nodata
        geotransform = [ds.transform.a, ds.transform.b, ds.transform.c,
                        ds.transform.d, ds.transform.e, ds.transform.f]
    finite = np.isfinite(data)
    valid = declared & finite
    low, high = RANGES["feo_wt"]
    if valid.any() and (data[valid].min() < low or data[valid].max() > high):
        raise ValueError("Kaguya FeO outside physical-plausibility range; review before preparing")
    outliers = int((data[valid] > 40).sum())
    impossible = int((data[valid] > 100).sum())
    frame = mask_frame(np.arange(400, dtype=np.uint16), np.arange(1440, dtype=np.uint16),
                       data, valid, "feo_wt", NODATA)
    assert_reason_contract(frame, "feo_wt")
    result = write_batches(OUT / "kaguya-mi-59mpp" / "kaguya-mi-feo-4ppd.parquet", [frame])
    result.update({
        "body": "Moon",
        "quantity": "feo_wt: iron(II) oxide abundance in weight percent",
        "outlierNote": f"{outliers} stored samples exceed 40 wt% and {impossible} exceed "
                       "100 wt% (algorithm divergence on extreme pixels upstream); kept "
                       "as-is because no QA rule is declared in the source metadata and "
                       "no invented masking is allowed; flagged as a limitation for any "
                       "scoring use",
        "valueMeaning": "FeO wt% derived from Kaguya (SELENE) Multiband Imager multispectral "
                        "reflectances (9 bands, 414-1548 nm; FeO sensitive at 749 nm and "
                        "1248 nm), Lucey-type method; deconvolution map by Lemelin et al. "
                        "(2016), product version May 2016 (JAXA / Univ. of Hawaii)",
        "grid": "USGS-published reduced 4 pixels/deg GeoTIFF (0.25 deg/pixel); simple "
                "cylindrical; planetocentric latitude, positive-east longitude, "
                "180W..180E, 50N..50S; Moon_2000 sphere radius 1737.4 km",
        "geotransformUpperLeft": geotransform,
        "support": "1 native map sample per row (no aggregation)",
        "timeSupport": "static map (Kaguya MI observations; product version May 2016)",
        "missingReasons": {NODATA: f"declared GeoTIFF nodata={nodata!r} or non-finite sample"},
        "labelNote": "the fetched PDS .lbl documents the full-resolution 59 m/pixel (512 ppd) "
                     "version of the same May 2016 product; the prepared table uses the "
                     "USGS 4 ppd reduction, md5-verified against the archive .md5",
        "labelMeta": label_meta,
    })
    report = dataset_report("kaguya-mi-59mpp", inputs)
    report["outputs"]["kaguya-mi-feo-4ppd.parquet"] = result
    report["gaps"] = [
        {"feature": "tio2_wt", "status": "gap",
         "evidence": "no published Kaguya MI TiO2 abundance map on the USGS host: prefix "
                     "mosaic/Lunar_ fully listed (316 keys, probed 2026-11-14) with no TiO2 "
                     "product; a Clementine UVVIS colour-ratio global 200 m map exists there "
                     "(4.46 GB) but belongs to a different dataset family and cannot "
                     "substitute without its own registry row and licence"},
        {"feature": "kaguya-mi reflectance bands (414-1548 nm)", "status": "gap",
         "evidence": "USGS distributes the MI multispectral band mosaics only at 512 ppd "
                     "(~21-24 GB per band), above the shared-machine 20 GB raw cap; no "
                     "reduced-resolution reflectance version is published",
         "atMostMonthlyNote": "these are static maps, so the time rule is not the blocker; "
                              "the size cap is"},
    ]
    save_report("kaguya-mi-59mpp", report)


def build_minirf(inputs: list[dict]) -> None:
    payload = raw_path("minirf-pds", CPR_IMG)
    spec = check_minirf_label(raw_path("minirf-pds", CPR_LBL))
    values = read_pc_real(payload, spec["lines"], spec["samples"])
    frames = real_frames(values, "cpr_minirf", NOT_FINITE, missing=True)
    result = write_batches(OUT / "minirf-pds" / "minirf-cpr-32ppd.parquet", frames)
    del values
    low, high = RANGES["cpr_minirf"]
    table = pl.scan_parquet(OUT / "minirf-pds" / "minirf-cpr-32ppd.parquet")
    outside = table.filter(pl.col("cpr_minirf").is_not_null()
                           & ~pl.col("cpr_minirf").is_between(low, high)).select(pl.len()).collect().item()
    if outside:
        raise ValueError(f"Mini-RF CPR outside preparation-guard range: {outside} rows")
    negatives = table.filter(pl.col("cpr_minirf") < 0).select(
        pl.len().alias("n"), pl.col("cpr_minirf").min().alias("lo")).collect().row(0)
    over20 = table.filter(pl.col("cpr_minirf") > 20).select(
        pl.len().alias("n"), pl.col("cpr_minirf").max().alias("hi")).collect().row(0)
    result.update({
        "body": "Moon",
        "quantity": "cpr_minirf: circular polarization ratio (dimensionless power ratio)",
        "valueMeaning": "CPR = same-sense circular polarization / opposite-sense circular "
                        "polarization (SC/OS) from LRO Mini-RF zoom-SAR, S-band centre "
                        f"frequency {spec['frequency_hz'] / 1e6:.1f} MHz (12.6 cm wavelength); "
                        "PDS Level 3 derived mosaic ingesting Level 2 Stokes-1 and CPR files "
                        "(ISIS), higher CPR < blocks, rough ejecta, possible ice",
        "grid": "global mosaic 32 pixels/deg (5760 x 11520); simple cylindrical; "
                "planetocentric latitude, positive-east longitude; sphere radius 1737.4 km",
        "support": "1 native mosaic sample per row",
        "timeSupport": "static mosaic of Mini-RF observations 2009-07-19 to 2010-12-26 (label "
                       "START_TIME/STOP_TIME); product v1.0 2011-10-20",
        "observedFrequency": f"{spec['frequency_hz']} Hz (S-band); no other frequency step is "
                             "published as a global 32 ppd mosaic in this dataset",
        "outlierNote": "kept as stored (declared-QA-only policy): producer ratio artifacts "
                       f"remain in the table - {negatives[0]} negative samples "
                       f"(min {negatives[1]}, from a slightly negative OS denominator) and "
                       f"{over20[0]} samples above 20 (max {over20[1]}, OS near zero); "
                       "99.9% of valid samples lie below 1.92; NOT clipped or nulled",
        "missingReasons": {
            MISSING: "label MISSING_CONSTANT (-1.7976931e308, a 64-bit real) is not "
                     "representable in the stored 32-bit PC_REAL; producer-side truncation "
                     "saturates it to -3.4028226550889e38, so every stored sample with "
                     "|v| >= 1e38 is the declared missing constant",
            NOT_FINITE: "non-finite stored sample (ISIS NaN fill)"},
    })
    report = dataset_report("minirf-pds", inputs)
    report["outputs"]["minirf-cpr-32ppd.parquet"] = result
    save_report("minirf-pds", report)


def boxcar(values: np.ndarray, valid: np.ndarray, factor: int):
    """Native support count + block-sum boxcar mean for integer factor aggregation."""
    if values.ndim != 2 or values.shape[0] % factor or values.shape[1] % factor:
        raise ValueError("native grid must divide evenly by the factor")
    height, width = values.shape
    sums = np.where(valid, values, 0.0).reshape(height // factor, factor, width // factor, factor).sum(axis=(1, 3))
    counts = valid.reshape(height // factor, factor, width // factor, factor).sum(axis=(1, 3))
    return sums, counts.astype(np.int64)


def build_wac(inputs: list[dict]) -> None:
    payload = raw_path("lroc-wac-global", WAC_TIF)
    fgdc = raw_path("lroc-wac-global", WAC_FGDC).read_text()
    access = re.search(r"<accconst>([^<]*)</accconst>", fgdc)
    use = re.search(r"<useconst>([^<]*)</useconst>", fgdc)
    # The shipped GeoTIFF is 109164 x 54582 uint8 with nodata NOT declared.
    # Trailing 42 rows / 84 samples (the last partial 101-cell beyond 540x1080
    # output cells at the -90 / +180 edges) are cropped; no native sample is
    # resampled. nodata=None means the product declares every 8-bit DN valid,
    # so the only honest QA rule is all-valid; no missing rows are produced.
    factor, out_rows, out_samples = 101, 540, 1080
    native_w, native_h = 109_164, 54_582
    crop_w, crop_h = native_w - out_samples * factor, native_h - out_rows * factor
    assert (crop_w, crop_h) == (84, 42), (crop_w, crop_h)
    stats_min = stats_max = None
    with rasterio.open(payload) as ds:
        if (ds.count, ds.width, ds.height) != (1, native_w, native_h):
            raise ValueError(f"WAC mosaic grid changed: {(ds.count, ds.width, ds.height)}")
        if ds.dtypes[0] not in ("uint8", "int8"):
            raise ValueError(f"WAC mosaic dtype changed: {ds.dtypes[0]}")
        if ds.nodata is not None:
            raise ValueError("WAC mosaic now declares nodata; re-derive the QA rule")
        if abs(ds.transform.a - 360.0 / native_w) > 1e-12 or abs(ds.transform.f - 90.0) > 1e-6 \
                or abs(ds.transform.e + 360.0 / native_w) > 1e-12 \
                or abs(ds.transform.c + 180.0) > 1e-6:
            raise ValueError("WAC mosaic geotransform changed; review before preparing")
        frames = []
        for ty in range(out_rows):
            strip = ds.read(1, window=Window(0, ty * factor, out_samples * factor, factor))
            sums, counts = boxcar(strip, np.ones_like(strip, dtype=bool), factor)
            sums, counts = sums.ravel(), counts.ravel()
            mean = np.divide(sums, counts, out=np.zeros_like(sums), where=counts > 0)
            covered = mean[counts > 0]
            if covered.size:
                stats_min = covered.min() if stats_min is None else min(stats_min, covered.min())
                stats_max = covered.max() if stats_max is None else max(stats_max, covered.max())
            frames.append(pl.DataFrame({
                "source_line": np.full(out_samples, ty, dtype=np.uint16),
                "source_sample": np.arange(out_samples, dtype=np.uint16),
                "albedo_wac_dn": pl.Series(mean),
                "native_sample_count": counts.astype(np.uint16),
                "missing_reason": pl.Series([None] * out_samples, dtype=pl.Utf8),
            }))
            del strip
        rows_total = pl.concat(frames)
    assert_reason_contract(rows_total, "albedo_wac_dn")
    result = write_batches(OUT / "lroc-wac-global" / "lroc-wac-albedo-3ppd.parquet", [rows_total])
    del rows_total
    low, high = RANGES["albedo_wac_dn"]
    if stats_min is not None and (stats_min < low or stats_max > high):
        raise ValueError(f"WAC DN means outside {low}..{high}: {stats_min}..{stats_max}")
    result.update({
        "body": "Moon",
        "quantity": "albedo_wac_dn: mean native 8-bit grayscale DN of the WAC morphology mosaic",
        "valueMeaning": "USGS 303 ppd reduction of the ASU LRO WAC global morphology mosaic "
                        "(broadband visible reflectance image mosaic). Stored 8-bit DN is "
                        "relative reflectance (relative brightness), NOT physical "
                        "Lambert/bolometric albedo. Not relabelled: the 'albedo' feature row "
                        "for lroc-wac-global is served only as this relative quantity, and the "
                        "physical-albedo gap is recorded in report.gaps.",
        "aggregation": f"native 303 ppd grid {native_w}x{native_h} aggregated with an integer "
                       f"{factor}x{factor} boxcar (mean of native DN, no cos(lat) area "
                       f"weighting; pole-area limitation: equal sample weighting is recorded, "
                       f"not corrected) to a 540x1080 grid; the trailing {crop_h} rows / "
                       f"{crop_w} samples (last partial boxcar cell at the -90 / +180 edges, "
                       "< 0.28 deg of mosaic) are cropped, never resampled; "
                       "native_sample_count keeps the valid native samples per output cell "
                       "(all cells 10201; product not colour-ramped, not scaled)",
        "grid": "derived table ~3 pixels/deg (output cell = 101 native pixels = "
                "0.3331 deg at the shipped native pixel scale 360/109164 deg); "
                "simple cylindrical; GCS_Moon_2000; planetocentric, positive east; "
                "global minus the cropped trailing edges; "
                "output pixel = 0.333 deg (~10 km at the equator)",
        "support": "mean of exactly 10201 native 8-bit samples per row (native_sample_count column)",
        "timeSupport": "static mosaic (ASU WAC images 2009-2011; USGS reduced product, FGDC "
                       "pubdate 2011-03-15)",
        "missingReasons": {"none": "the GeoTIFF declares no nodata and no fill constant; "
                                   "every 8-bit DN 0..255 is treated as a valid relative-"
                                   "reflectance observation, so the WAC table has no "
                                   "missing rows"},
        "licenceEvidence": {"fgdcAccessConstraints": access.group(1).strip() if access else None,
                            "fgdcUseConstraints": use.group(1).strip() if use else None},
        "cellStats": {"validCells": 540 * 1080, "emptyCells": 0,
                      "min": float(stats_min) if stats_min is not None else None,
                      "max": float(stats_max) if stats_max is not None else None},
    })
    report = dataset_report("lroc-wac-global", inputs)
    report["outputs"]["lroc-wac-albedo-3ppd.parquet"] = result
    report["gaps"] = [
        {"feature": "albedo (physical Lambert/bolometric)", "status": "gap",
         "evidence": "the WAC morphology mosaic publication is an 8-bit relative-reflectance "
                     "image; no physical-albedo gridded product is published in this source "
                     "family at a coarse resolution, so the prepared table keeps native DN "
                     "units and serves them as albedo_wac_dn only"},
    ]
    save_report("lroc-wac-global", report)


def build_lamp(side: str, inputs: list[dict]) -> None:
    name = f"LAMP_8{'0n' if side == 'n' else '0s'}_240mpp_ratio_albed_01.img"
    payload = raw_path("lamp", name)
    spec = parse_lamp_label(raw_path("lamp", name[:-4] + ".lbl"), side)
    out = OUT / "lamp" / f"lamp-gdr-ratio-albedo-8{'0n' if side == 'n' else '0s'}.parquet"
    values = read_pc_real(payload, spec["lines"], spec["samples"])
    frames = real_frames(values, "lya_offon", NOT_FINITE)
    result = write_batches(out, frames)
    del values
    low, high = RANGES["lya_offon"]
    scanned = pl.scan_parquet(out)
    outside = scanned.filter(pl.col("lya_offon").is_not_null()
                             & ~pl.col("lya_offon").is_between(low, high)).select(pl.len()).collect().item()
    if outside:
        raise ValueError(f"LAMP {side} ratio outside preparation-guard range: {outside} rows")
    stats = scanned.select(pl.col("lya_offon").min().alias("lo"),
                           pl.col("lya_offon").max().alias("hi"),
                           pl.col("lya_offon").mean().alias("mean")).collect()
    negatives = scanned.filter(pl.col("lya_offon") < 0).select(pl.len()).collect().item()
    over10 = scanned.filter(pl.col("lya_offon") > 10).select(pl.len()).collect().item()
    result.update({
        "body": "Moon",
        "quantity": "lya_offon: off-band / on-band far-UV albedo ratio, dimensionless "
                    "(PDS 'H2O absorption feature depth' map)",
        "valueMeaning": "ratio of the off-band (155.57-189.57 nm) albedo to the on-band "
                        "(129.57-155.57 nm) albedo, cumulative ensemble average over LAMP "
                        "night-side observations; the spectral-slope signature associated with "
                        "H2O absorption (frost or hydration). This is NOT a Lyman-alpha-band "
                        "quantity; the features registry row name lya_offon is kept as the key "
                        "name while the exact bandpass is stated here (no relabelling of one "
                        "quantity as another).",
        "bandpass": {"off_band_nm": [155.57, 189.57], "on_band_nm": [129.57, 155.57],
                     "lyman_alpha_also_possible_nm": [119.57, 123.57],
                     "source": "LAMP_GDR_DS.CAT in the volume (fetched, manifests as an input)",
                     "lymanAlphaNote": "a separate Lyman-alpha range exists in the GDR, but the "
                                       "ratio maps use off/on, not LyA"},
        "grid": "polar stereographic (MEAN EARTH/POLAR AXIS OF DE421), center latitude "
                f"{spec['center_latitude']:.0f}, 2501 x 2501, 240 m/pixel at the pole "
                "(126.347 pix/deg), coverage pole-ward of 80 deg",
        "support": "1 native map sample per row",
        "timeSupport": "static cumulative map (nominal ESMD mission phase; the GDR publishes no "
                       "monthly ratio maps, only monthly brightness/albedo)",
        "missingReasons": {NOT_FINITE: "non-finite stored samples (the label declares no PDS3 "
                                       "special constant for this product)"},
        "outlierNote": "kept as stored (declared-QA-only policy; the label declares no "
                       "special constants): producer ratio artifacts remain in the table - "
                       f"{negatives} negative samples (on-band denominator noise; min "
                       f"{stats.item(0, 0)}) and {over10} samples above 10 (max "
                       f"{stats.item(0, 1)}); the physically expected frost/hydration "
                       "signature sits near 0.1-3; NOT clipped or nulled",
        "valueStats": {"min": stats.item(0, 0), "max": stats.item(0, 1), "mean": stats.item(0, 2)},
    })
    report_file = OUT / "lamp" / "preparation-report.json"
    # the two polar maps share one report: merge instead of clobbering the
    # other side's output entry
    report = (json.loads(report_file.read_text()) if report_file.exists()
              else dataset_report("lamp", inputs))
    report["outputs"][out.name] = result
    save_report("lamp", report)


def gaps() -> list[dict]:
    recorded = []
    for path in sorted(OUT.glob("*/preparation-report.json")):
        try:
            report = json.loads(path.read_text())
        except json.JSONDecodeError:
            continue
        recorded.extend({"datasetId": report.get("datasetId"), "gap": gap}
                        for gap in report.get("gaps", []))
    recorded.append({
        "datasetId": "m3-pds",
        "features": ["mafic_bd_1um", "oh_3um"],
        "status": "blocked",
        "licence": "unresolved (audit #41 retained verified:false; a NASA/PDS host or another "
                   "derived M3 product's licence is not a blanket grant for these volumes)",
        "availability": "no published global derived band-depth / spectral-parameter map located "
                        "on the PDS imaging host (probed 2026-11-14, "
                        "https://planetarydata.jpl.nasa.gov/img/data/m3/ HTTP 200, volume "
                        "listing shows per-strip V1/V2 products); per-strip L1B processing is "
                        "out of scope per the work order and would still be licence-unresolved",
        "action": "no bytes fetched by the resolve-licence-first rule; revisit if the owner "
                  "resolves an explicit M3 reuse licence or points to a published global "
                  "derived map",
    })
    return recorded


def build() -> dict:
    inputs = verify_inputs()
    build_kaguya(inputs)
    build_minirf(inputs)
    build_wac(inputs)
    build_lamp("n", inputs)
    build_lamp("s", inputs)
    save_report("m3-pds", {
        "generatedAt": dt.datetime.now(dt.timezone.utc).isoformat(),
        "workOrder": "issue #102 (W43) Moon spectral and radar maps",
        "datasetId": "m3-pds",
        "runtimeStatus": "partial",
        "scientificStatus": "blocked",
        "scope": "licence-unresolved dataset: no bytes fetched (resolve-licence-first rule)",
        "inputs": [entry for entry in inputs if entry["datasetId"] == "m3-pds"],
        "outputs": {},
        "gaps": gaps(),
    })
    (OUT / "moon-spectral-gaps.json").write_text(json.dumps(gaps(), indent=2) + "\n")
    return {"datasets": ["kaguya-mi-59mpp", "minirf-pds", "lroc-wac-global", "lamp",
                         "m3-pds (gap, no fetch)"]}


def _expect_reason(reason: str | None, raw: float | None, declared: set[str], where: str) -> None:
    if raw is None:
        if reason not in declared:
            raise ValueError(f"{where}: null value without declared reason (got {reason!r})")
    else:
        if reason is not None:
            raise ValueError(f"{where}: value carrying missing_reason {reason!r}")


def check() -> None:
    inputs = verify_inputs()
    for name, spec in TABLES.items():
        path = OUT / name
        reported = None
        for dataset in ("kaguya-mi-59mpp", "minirf-pds", "lroc-wac-global", "lamp"):
            report_file = OUT / dataset / "preparation-report.json"
            if not report_file.exists():
                continue
            meta = json.loads(report_file.read_text())["outputs"].get(path.name)
            if meta is not None:
                if meta["sha256"] != sha256(path) or meta["bytes"] != path.stat().st_size:
                    raise ValueError(f"output hash/size mismatch: {name}")
                reported = meta
        if reported is None:
            raise ValueError(f"no preparation report entry for {name}")
        frame = pl.scan_parquet(path)
        schema = frame.collect_schema().names()
        if schema != spec["columns"]:
            raise ValueError(f"{name}: columns {schema} != {spec['columns']}")
        rows = frame.select(pl.len()).collect().item()
        if rows != spec["rows"]:
            raise ValueError(f"{name}: rows {rows} != {spec['rows']}")
        value = spec["value"]
        low, high = RANGES[value]
        outside = frame.filter(pl.col(value).is_not_null()
                               & ~pl.col(value).is_between(low, high)).select(pl.len()).collect().item()
        if outside:
            raise ValueError(f"{name}: {outside} values outside {low}..{high}")
        bare_nulls = frame.filter(pl.col(value).is_null()
                                  & pl.col("missing_reason").is_null()).select(pl.len()).collect().item()
        if bare_nulls:
            raise ValueError(f"{name}: {bare_nulls} null values without missing_reason")
        rated = frame.filter(pl.col(value).is_not_null()
                             & pl.col("missing_reason").is_not_null()).select(pl.len()).collect().item()
        if rated:
            raise ValueError(f"{name}: {rated} valid values carrying missing_reason")
        bad = set(frame.filter(pl.col(value).is_null())
                  .select("missing_reason").unique().drop_nulls()
                  .collect().get_column("missing_reason").to_list()) - spec["reasons"]
        if bad:
            raise ValueError(f"{name}: undeclared reasons {bad}")
        keys = frame.select((((pl.col("source_line").cast(pl.UInt32) * 65536))
                             + pl.col("source_sample")).n_unique().alias("n")).collect().item()
        if keys != rows:
            raise ValueError(f"{name}: {rows - keys} duplicate (line, sample) keys")
        print(f"PASS {name}: {rows:,} rows; columns, ranges, contract, uniqueness OK", flush=True)
    spot_checks()
    print(f"inputs verified: {len(inputs)} manifest entries", flush=True)


def spot_checks() -> None:
    def coords(lines: int, samples: int) -> list[tuple[int, int]]:
        return [(0, 0), (lines - 1, samples - 1), (lines // 2, samples // 2),
                (7, 3008 % samples), (81, 4477 % samples)]

    def table_row(table: Path, line: int, sample: int, columns: list[str]):
        row = pl.scan_parquet(table).filter((pl.col("source_line") == line)
                                            & (pl.col("source_sample") == sample)) \
            .select(columns).collect()
        if row.height != 1:
            raise ValueError(f"spot check {line},{sample}: table row not unique")
        return row.row(0)

    feo_table = OUT / "kaguya-mi-59mpp" / "kaguya-mi-feo-4ppd.parquet"
    with rasterio.open(raw_path("kaguya-mi-59mpp", KAGUYA_FEO_TIF)) as ds:
        for line, sample in coords(400, 1440):
            got, reason = table_row(feo_table, line, sample, ["feo_wt", "missing_reason"])
            raw = float(ds.read(1, window=Window(sample, line, 1, 1))[0, 0])
            declared = raw == ds.nodata or not np.isfinite(raw)
            _expect_reason(reason, None if declared else raw, {NODATA}, f"kaguya {line},{sample}")
            if not declared and (got is None or abs(got - raw) > 1e-9):
                raise ValueError(f"kaguya spot {line},{sample}: raw {raw} vs table {got!r}")
            if declared and got is not None:
                raise ValueError(f"kaguya spot {line},{sample}: raw nodata vs table {got!r}")
    print("PASS kaguya spot checks (5 coordinates)", flush=True)

    cpr_table = OUT / "minirf-pds" / "minirf-cpr-32ppd.parquet"
    cpr_raw = read_pc_real(raw_path("minirf-pds", CPR_IMG), 5760, 11520)
    for line, sample in coords(5760, 11520):
        got, reason = table_row(cpr_table, line, sample, ["cpr_minirf", "missing_reason"])
        raw = float(cpr_raw[line, sample])
        declared_missing = not np.isfinite(raw) or abs(raw) >= SENTINEL_ABS
        raw = None if (declared_missing or not np.isfinite(raw)) else raw
        _expect_reason(reason, raw, {MISSING, NOT_FINITE}, f"minirf {line},{sample}")
        if raw is not None and abs(got - raw) > 1e-9:
            raise ValueError(f"minirf spot {line},{sample}: raw {raw} vs table {got!r}")
    print("PASS minirf spot checks (5 coordinates)", flush=True)

    for side in ("n", "s"):
        table = OUT / "lamp" / f"lamp-gdr-ratio-albedo-8{'0n' if side == 'n' else '0s'}.parquet"
        values = read_pc_real(raw_path("lamp", f"LAMP_8{'0n' if side == 'n' else '0s'}_240mpp_ratio_albed_01.img"), 2501, 2501)
        for line, sample in coords(2501, 2501):
            got, reason = table_row(table, line, sample, ["lya_offon", "missing_reason"])
            raw = float(values[line, sample])
            raw = raw if np.isfinite(raw) else None
            _expect_reason(reason, raw, {NOT_FINITE}, f"lamp {side} {line},{sample}")
            if raw is not None and abs(got - raw) > 1e-9:
                raise ValueError(f"lamp {side} spot {line},{sample}: raw {raw} vs table {got!r}")
        print(f"PASS lamp {side} spot checks (5 coordinates)", flush=True)

    wac_table = OUT / "lroc-wac-global" / "lroc-wac-albedo-3ppd.parquet"
    factor = 101
    with rasterio.open(raw_path("lroc-wac-global", WAC_TIF)) as ds:
        for ty, tx in [(0, 0), (539, 1079), (270, 540), (42, 777), (177, 901)]:
            strip = ds.read(1, window=Window(tx * factor, ty * factor, factor, factor))
            count = int(strip.size)
            got, got_count, reason = table_row(wac_table, ty, tx,
                                               ["albedo_wac_dn", "native_sample_count", "missing_reason"])
            if int(got_count) != count:
                raise ValueError(f"wac spot {ty},{tx}: support {got_count} vs recompute {count}")
            expect = float(strip.astype(np.float64).sum()) / count
            if got is None or abs(got - expect) > 1e-9:
                raise ValueError(f"wac spot {ty},{tx}: recomputed {expect} vs table {got!r}")
            if reason is not None:
                raise ValueError(f"wac spot {ty},{tx}: value carries missing_reason")
    print("PASS wac spot checks (5 cells recomputed from raw)", flush=True)


def main():
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument("action", choices=["fetch", "build", "check"])
    action = parser.parse_args().action
    if action == "fetch":
        for dataset, url in sources():
            print(fetch(dataset, url), flush=True)
    elif action == "build":
        print(build(), flush=True)
    else:
        check()


if __name__ == "__main__":
    main()
