"""Deterministic source QA replays, license checks, and ledger audits (work order #76).

Preserves all historical `_derived/` artifacts untouched while measuring:
- Catalog license verification before reading any source.
- Full 120-granule (2014-2023) MODIS MOD11C3 v061 LST + QC_Day/QC_Night replay and
  H3 res-4 25%-coverage sensitivity across candidate QC policies.
- ESA CCI Permafrost v5.0 native fill (raw > 100 / 255) replay from pinned NetCDFs.
- Malaria Atlas 2015 travel-time GeoTIFF nodata/non-finite replay from pinned ZIP.
- Copernicus GLO-30 DEM historical ledger integrity + live S3 WBM/EDM QA probes.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import gzip
import hashlib
import json
import os
from pathlib import Path
import sys
import time
import zipfile

import numpy as np
import yaml

from .grid import CMG_N, CMG_M, DERIVED, RES, cmg_cell_map, group_index
from .monthly import MIN_PIXEL_SHARE
from .snapshots import CATALOG, MANIFEST, REPO, SNAP, sha256

COPERNICUS_S3_BASE = "https://copernicus-dem-30m.s3.amazonaws.com"
DEFAULT_PROBE_TILES = (
    "Copernicus_DSM_COG_10_N68_00_E055_00_DEM",  # Pechora Sea / coastal tundra
    "Copernicus_DSM_COG_10_N47_00_W087_00_DEM",  # Lake Superior (100% inland water WBM=2)
    "Copernicus_DSM_COG_10_N53_00_E108_00_DEM",  # Lake Baikal (inland water WBM=2 + land)
    "Copernicus_DSM_COG_10_S04_00_W064_00_DEM",  # Amazon river (WBM=3 + lake + land)
    "Copernicus_DSM_COG_10_N38_00_W111_00_DEM",  # Utah (MDRS desert/canyon + EDM=2/4)
    "Copernicus_DSM_COG_10_S24_00_W070_00_DEM",  # Atacama coast
    "Copernicus_DSM_COG_10_N75_00_W090_00_DEM",  # Devon Island (Haughton, Arctic coast)
)


def resolve_snapshots_root(snapshots_dir: Path | None = None) -> Path:
    """Resolve `data/snapshots` directory, honouring explicit overrides / COSMIC_SNAPSHOTS_DIR."""
    if snapshots_dir is not None:
        return Path(snapshots_dir)
    env = os.environ.get("COSMIC_SNAPSHOTS_DIR")
    if env:
        return Path(env)
    return SNAP


def verify_catalog_licenses(
    dataset_ids: list[str] | tuple[str, ...],
    catalog_dir: Path = CATALOG,
) -> dict[str, dict]:
    """Verify that every dataset has `license.verified: true` and an open/usable license id."""
    out: dict[str, dict] = {}
    for dsid in dataset_ids:
        path = Path(catalog_dir) / f"{dsid}.yaml"
        if not path.is_file():
            raise FileNotFoundError(f"{dsid}: missing catalog row {path}")
        row = yaml.safe_load(path.read_text(encoding="utf-8"))
        lic = row.get("license") or {}
        lic_id = str(lic.get("id") or "").strip()
        verified = bool(lic.get("verified"))
        if not verified or not lic_id or lic_id in {"restricted", "unresolved"}:
            raise PermissionError(f"{dsid}: license not verified or restricted ({lic!r})")
        out[dsid] = {"licenseId": lic_id, "verified": verified}
    return out


def verified_manifest_file(entry: dict, repo_root: Path, snapshots_root: Path | None = None) -> Path:
    """Resolve and SHA256-verify a `MANIFEST.json` entry without silent fallback."""
    rel = entry["localPath"]
    candidates = [repo_root / rel]
    if snapshots_root is not None and rel.startswith("data/snapshots/"):
        candidates.insert(0, snapshots_root / rel[len("data/snapshots/"):])
    path = next((c for c in candidates if c.is_file()), None)
    if path is None:
        raise FileNotFoundError(f"missing pinned snapshot: {rel}")
    actual = sha256(path)
    if actual != entry["sha256"]:
        raise ValueError(f"sha256 mismatch for {rel}: expected {entry['sha256']}, got {actual}")
    return path


def decode_mod11c3_qc(qc: np.ndarray) -> dict[str, np.ndarray]:
    """Decode MODIS MOD11C3 v061 8-bit QC_Day / QC_Night bitfields."""
    q = np.asarray(qc, dtype=np.uint8)
    return {
        "mand_qa": q & np.uint8(0x03),          # bits 0-1: 00 good, 01 other QA, 10 cloud, 11 not produced
        "data_quality": (q >> 2) & np.uint8(0x03),  # bits 2-3
        "emis_err": (q >> 4) & np.uint8(0x03),  # bits 4-5
        "lst_err": (q >> 6) & np.uint8(0x03),   # bits 6-7: 0 <=1K, 1 <=2K, 2 <=3K, 3 >3K
    }


def mod11c3_policy_masks(lst_raw: np.ndarray, qc: np.ndarray) -> dict[str, np.ndarray]:
    """Return boolean valid-pixel masks for candidate MOD11C3 QA policies."""
    valid = np.asarray(lst_raw) >= 7500
    fields = decode_mod11c3_qc(qc)
    mand = fields["mand_qa"]
    err = fields["lst_err"]
    return {
        "P0-baseline": valid,
        "P1-err-le-3k": valid & (err <= 2),
        "P2-err-le-2k": valid & (err <= 1),
        "P3-mand-qa-00-only": valid & (mand == 0),
        "P4-err-le-1k": valid & (err == 0),
    }


def _load_cmg_h3_grid(snapshots_root: Path) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Load the pinned CMG -> H3 res-4 pixel mapping from `grid.py` cache or compute it."""
    cache = snapshots_root / "_derived" / f"cmg_h3r{RES}.npy"
    if cache.is_file():
        cellmap = np.load(cache)
    else:
        cellmap, _ = cmg_cell_map(RES)
    order, cells, starts = group_index(cellmap)
    ncell = len(cells)
    size = np.diff(np.append(starts, len(order))).astype(np.float64)
    need = MIN_PIXEL_SHARE * size
    gid_of_order = np.repeat(np.arange(ncell), np.diff(np.append(starts, len(order))))
    return order, gid_of_order, need, np.array([ncell], dtype=np.int64)


def replay_mod11c3(
    manifest_entries: list[dict],
    *,
    repo_root: Path = REPO,
    snapshots_root: Path | None = None,
    catalog_dir: Path = CATALOG,
) -> dict:
    """Run full SHA256-verified MOD11C3 pixel + QC-bit + cell-month policy replay."""
    from pyhdf.SD import SD, SDC

    verify_catalog_licenses(["modis-mod11c3"], catalog_dir=catalog_dir)
    sroot = resolve_snapshots_root(snapshots_root)
    mod11 = sorted(
        [e for e in manifest_entries if e.get("datasetId") == "modis-mod11c3"],
        key=lambda e: e["localPath"],
    )
    if not mod11:
        raise ValueError("No modis-mod11c3 entries found in MANIFEST.json")

    t0 = time.time()
    order, gid_of_order, need, ncell_arr = _load_cmg_h3_grid(sroot)
    ncell = int(ncell_arr[0])

    policies = ("P0-baseline", "P1-err-le-3k", "P2-err-le-2k", "P3-mand-qa-00-only", "P4-err-le-1k")
    sides: dict[str, dict] = {}
    for side in ("Day", "Night"):
        sides[side] = {
            "totalPixels": 0,
            "retainedRawGe7500": 0,
            "maskedRawLt7500": 0,
            "mandatoryQaAllPixels": [0, 0, 0, 0],
            "lstErrorOnValid": [0, 0, 0, 0],
            "dataQualityOnValid": [0, 0, 0, 0],
            "emisErrorOnValid": [0, 0, 0, 0],
            "anomalies": {"rawGe7500WithBadMandQa": 0, "rawLt7500WithGoodMandQa": 0},
            "cellMonths2023Kept": {p: 0 for p in policies},
            "cellYearMonthsAllKept": {p: 0 for p in policies},
        }

    granule_records = []
    n_2023 = 0
    for entry in mod11:
        path = verified_manifest_file(entry, repo_root, sroot)
        is_2023 = ".A2023" in entry["localPath"]
        if is_2023:
            n_2023 += 1
        sd = SD(str(path), SDC.READ)
        g_rec = {"localPath": entry["localPath"], "sha256": entry["sha256"], "is2023": is_2023, "sides": {}}
        try:
            for side, lname, qname in (("Day", "LST_Day_CMG", "QC_Day"), ("Night", "LST_Night_CMG", "QC_Night")):
                lst = sd.select(lname)[:]
                qc = sd.select(qname)[:]
                valid = lst >= 7500
                fields = decode_mod11c3_qc(qc)
                mand = fields["mand_qa"]
                dq = fields["data_quality"]
                emis = fields["emis_err"]
                err = fields["lst_err"]

                n_tot = int(lst.size)
                n_val = int(np.count_nonzero(valid))
                n_msk = n_tot - n_val
                hi_bad = int(np.count_nonzero(valid & (mand >= 2)))
                lo_ok = int(np.count_nonzero((~valid) & (mand <= 1)))

                acc = sides[side]
                acc["totalPixels"] += n_tot
                acc["retainedRawGe7500"] += n_val
                acc["maskedRawLt7500"] += n_msk
                acc["anomalies"]["rawGe7500WithBadMandQa"] += hi_bad
                acc["anomalies"]["rawLt7500WithGoodMandQa"] += lo_ok
                acc["mandatoryQaAllPixels"] = [
                    a + int(b) for a, b in zip(acc["mandatoryQaAllPixels"], np.bincount(mand.ravel(), minlength=4))
                ]
                acc["lstErrorOnValid"] = [
                    a + int(b) for a, b in zip(acc["lstErrorOnValid"], np.bincount(err[valid], minlength=4))
                ]
                acc["dataQualityOnValid"] = [
                    a + int(b) for a, b in zip(acc["dataQualityOnValid"], np.bincount(dq[valid], minlength=4))
                ]
                acc["emisErrorOnValid"] = [
                    a + int(b) for a, b in zip(acc["emisErrorOnValid"], np.bincount(emis[valid], minlength=4))
                ]

                lst_ord = lst.ravel()[order]
                qc_ord = qc.ravel()[order]
                masks = mod11c3_policy_masks(lst_ord, qc_ord)
                for pname, m in masks.items():
                    cnt = np.bincount(gid_of_order[m], minlength=ncell)
                    kept = int(np.count_nonzero(cnt >= need))
                    acc["cellYearMonthsAllKept"][pname] += kept
                    if is_2023:
                        acc["cellMonths2023Kept"][pname] += kept

                g_rec["sides"][side] = {
                    "inputValues": n_tot,
                    "maskedInputValues": n_msk,
                    "retainedInputValues": n_val,
                }
        finally:
            sd.end()
        granule_records.append(g_rec)

    return {
        "generatedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "datasetId": "modis-mod11c3",
        "license": verify_catalog_licenses(["modis-mod11c3"], catalog_dir=catalog_dir)["modis-mod11c3"],
        "granuleCount": len(mod11),
        "granuleCount2023": n_2023,
        "cellCount": ncell,
        "minPixelShare": MIN_PIXEL_SHARE,
        "elapsedS": round(time.time() - t0, 1),
        "sides": sides,
        "granules": granule_records,
    }


def load_verified_mod11c3_receipt(
    receipt_path: Path,
    manifest_entries: list[dict],
    *,
    repo_root: Path = REPO,
    snapshots_root: Path | None = None,
) -> dict | None:
    """Return `receipt_path` payload ONLY if every granule path+sha256 matches MANIFEST.json and disk."""
    if not receipt_path.is_file():
        return None
    doc = json.loads(receipt_path.read_text(encoding="utf-8"))
    expected = sorted(
        [(e["localPath"], e["sha256"]) for e in manifest_entries if e.get("datasetId") == "modis-mod11c3"]
    )
    recorded = sorted([(g["localPath"], g["sha256"]) for g in doc.get("granules", [])])
    if expected != recorded or not expected:
        return None
    sroot = resolve_snapshots_root(snapshots_root)
    for e in manifest_entries:
        if e.get("datasetId") == "modis-mod11c3":
            verified_manifest_file(e, repo_root, sroot)
    return doc


def replay_permafrost(
    manifest_entries: list[dict],
    *,
    repo_root: Path = REPO,
    snapshots_root: Path | None = None,
    catalog_dir: Path = CATALOG,
) -> list[dict]:
    """Replay ESA CCI Permafrost v5.0 native fill (`raw > 100`, code 255) from pinned NetCDFs."""
    import rasterio

    dsids = ("esa-cci-permafrost-extent-nh", "esa-cci-permafrost-extent-antarctica")
    licenses = verify_catalog_licenses(dsids, catalog_dir=catalog_dir)
    sroot = resolve_snapshots_root(snapshots_root)
    out = []
    for dsid in dsids:
        entry = next((e for e in manifest_entries if e.get("datasetId") == dsid), None)
        if entry is None:
            raise FileNotFoundError(f"missing MANIFEST entry for {dsid}")
        path = verified_manifest_file(entry, repo_root, sroot)
        with rasterio.open(f"netcdf:{path}:PFR") as ds:
            arr = ds.read(1)
        total = int(arr.size)
        mask = arr > 100
        masked = int(np.count_nonzero(mask))
        uvals, ucnts = np.unique(arr[mask], return_counts=True)
        out.append({
            "datasetId": dsid,
            "source": entry["localPath"],
            "sha256": entry["sha256"],
            "license": licenses[dsid],
            "shape": list(arr.shape),
            "actualRule": "raw > 100 (fill 255) masked prior to 5x5 block average to 0.05 deg CMG",
            "inputValues": total,
            "maskedInputValues": masked,
            "retainedInputValues": total - masked,
            "maskedCodeCounts": {str(int(k)): int(v) for k, v in zip(uvals, ucnts)},
        })
    return out


def replay_travel_time(
    manifest_entries: list[dict],
    *,
    repo_root: Path = REPO,
    snapshots_root: Path | None = None,
    catalog_dir: Path = CATALOG,
) -> dict:
    """Replay Malaria Atlas 2015 travel-time GeoTIFF nodata/non-finite counts from pinned ZIP."""
    import rasterio

    dsid = "travel-time-to-cities-2015"
    licenses = verify_catalog_licenses([dsid], catalog_dir=catalog_dir)
    sroot = resolve_snapshots_root(snapshots_root)
    entry = next((e for e in manifest_entries if e.get("datasetId") == dsid), None)
    if entry is None:
        raise FileNotFoundError(f"missing MANIFEST entry for {dsid}")
    path = verified_manifest_file(entry, repo_root, sroot)
    with zipfile.ZipFile(path) as zf:
        tifs = [n for n in zf.namelist() if n.lower().endswith((".tif", ".tiff"))]
    if not tifs:
        raise RuntimeError(f"no GeoTIFF found in {path}")
    uri = f"/vsizip/{path.resolve()}/{tifs[0]}"
    total = nodata_cnt = nonfinite_cnt = 0
    with rasterio.open(uri) as src:
        shape = list(src.shape)
        nodata_val = src.nodata
        for _, win in src.block_windows(1):
            arr = src.read(1, window=win, masked=False)
            total += int(arr.size)
            nd = (arr == nodata_val) if nodata_val is not None else np.zeros(arr.shape, dtype=bool)
            nf = (~np.isfinite(arr)) & (~nd)
            nodata_cnt += int(np.count_nonzero(nd))
            nonfinite_cnt += int(np.count_nonzero(nf))
    masked = nodata_cnt + nonfinite_cnt
    return {
        "datasetId": dsid,
        "source": entry["localPath"],
        "sha256": entry["sha256"],
        "license": licenses[dsid],
        "tifEntry": tifs[0],
        "shape": shape,
        "nodataValue": nodata_val,
        "actualRule": "nodata and non-finite pixels excluded inside H3 res-4 polygons",
        "inputValues": total,
        "nodataPixels": nodata_cnt,
        "nonfinitePixels": nonfinite_cnt,
        "maskedInputValues": masked,
        "retainedInputValues": total - masked,
    }


def audit_terrain_ledger(
    tile_list_path: Path,
    ledger_path: Path,
    *,
    cells_parquet: Path | None = None,
    terrain_npz: Path | None = None,
) -> dict:
    """Audit historical Copernicus GLO-30 ledger without fabricating missing mask counts."""
    tiles = {line.strip() for line in tile_list_path.read_text(encoding="utf-8").splitlines() if line.strip()}
    ledger_tiles: set[str] = set()
    errors = 0
    has_sha = 0
    has_mask_fields = 0
    wbm_available_count = 0
    shapes: dict[str, int] = {}
    masked_water_sum = 0
    masked_void_sum = 0
    retained_land_sum = 0

    with gzip.open(ledger_path, "rt", encoding="utf-8") as f:
        for line in f:
            obj = json.loads(line)
            ledger_tiles.add(obj["tile"])
            if "error" in obj:
                errors += 1
            if obj.get("arraySha256"):
                has_sha += 1
            if "maskedWaterPixels" in obj or "wbmAvailable" in obj:
                has_mask_fields += 1
            if obj.get("wbmAvailable"):
                wbm_available_count += 1
            masked_water_sum += int(obj.get("maskedWaterPixels") or 0)
            masked_void_sum += int(obj.get("maskedVoidPixels") or 0)
            retained_land_sum += int(obj.get("retainedLandPixels") or 0)
            sh = "x".join(str(x) for x in obj.get("shape", []))
            shapes[sh] = shapes.get(sh, 0) + 1

    water_masked = has_mask_fields > 0 and wbm_available_count == len(ledger_tiles) and errors == 0
    out: dict = {
        "tileListSha256": sha256(tile_list_path),
        "ledgerSha256": sha256(ledger_path),
        "expectedTiles": len(tiles),
        "ledgerTiles": len(ledger_tiles),
        "missingTiles": len(tiles - ledger_tiles),
        "extraTiles": len(ledger_tiles - tiles),
        "errorTiles": errors,
        "tilesWithArraySha256": has_sha,
        "tilesWithMaskFields": has_mask_fields,
        "waterMasked": water_masked,
        "shapes": shapes,
        # Never fabricate historical mask counts when the build read unmasked arrays:
        "appliedNodataFilterCount": None if water_masked else 0,
        "invalidInputValues": (masked_water_sum + masked_void_sum) if water_masked else None,
        "maskedWaterPixels": masked_water_sum if water_masked else None,
        "maskedVoidPixels": masked_void_sum if water_masked else None,
        "retainedLandPixels": retained_land_sum if water_masked else None,
    }
    if terrain_npz is not None and terrain_npz.is_file():
        t = np.load(terrain_npz)
        out["terrainNpzSha256"] = sha256(terrain_npz)
        out["totalOutputDemPixels"] = int(t["dem_pixels"].sum())
    if cells_parquet is not None and cells_parquet.is_file():
        import polars as pl
        df = pl.read_parquet(
            cells_parquet,
            columns=["h3", "dem_pixels", "elev_min_m", "elev_max_m", "slope_mean_deg", "water_pct", "land_pct_mean"],
        )
        out["cellsOverlap"] = {
            "totalCells": df.height,
            "cellsWithDemPixels": df.filter(pl.col("dem_pixels") > 0).height,
            "cellsNullSlope": df.filter(pl.col("slope_mean_deg").is_null()).height,
            "cellsWaterPctGt50WithSlope": df.filter(
                (pl.col("water_pct") > 50.0) & pl.col("slope_mean_deg").is_not_null()
            ).height,
            "cellsLandPctLt50WithSlope": df.filter(
                (pl.col("land_pct_mean") < 50.0) & pl.col("slope_mean_deg").is_not_null()
            ).height,
            "cellsZeroSlopeZeroElev": df.filter(
                (pl.col("slope_mean_deg") == 0.0) & (pl.col("elev_min_m") == 0.0) & (pl.col("elev_max_m") == 0.0)
            ).height,
        }
    return out


def probe_copernicus_wbm_edm(
    tiles: tuple[str, ...] = DEFAULT_PROBE_TILES,
    *,
    overview_level: int = 2,
    catalog_dir: Path = CATALOG,
) -> dict:
    """Probe live Copernicus GLO-30 COG + AUXFILES WBM/EDM masks on S3 without altering _derived/."""
    import rasterio
    from rasterio.env import Env

    lic = verify_catalog_licenses(["copernicus-dem-glo30"], catalog_dir=catalog_dir)["copernicus-dem-glo30"]
    gdal_env = dict(GDAL_DISABLE_READDIR_ON_OPEN="EMPTY_DIR", AWS_NO_SIGN_REQUEST="YES", GDAL_HTTP_MAX_RETRY="3")
    rows = []
    with Env(**gdal_env):
        for tile in tiles:
            stem = tile[:-4] if tile.endswith("_DEM") else tile
            dem_url = f"{COPERNICUS_S3_BASE}/{tile}/{tile}.tif"
            wbm_url = f"{COPERNICUS_S3_BASE}/{tile}/AUXFILES/{stem}_WBM.tif"
            edm_url = f"{COPERNICUS_S3_BASE}/{tile}/AUXFILES/{stem}_EDM.tif"
            with rasterio.open("/vsicurl/" + dem_url, OVERVIEW_LEVEL=overview_level) as dds:
                z = dds.read(1)
                nodata = dds.nodata
            with rasterio.open("/vsicurl/" + wbm_url, OVERVIEW_LEVEL=overview_level) as wds:
                wbm = wds.read(1)
            with rasterio.open("/vsicurl/" + edm_url, OVERVIEW_LEVEL=overview_level) as eds:
                edm = eds.read(1)
            wu, wc = np.unique(wbm, return_counts=True)
            eu, ec = np.unique(edm, return_counts=True)
            rows.append({
                "tile": tile,
                "overviewLevel": overview_level,
                "shape": list(z.shape),
                "demNodata": nodata,
                "demSha256": hashlib.sha256(z.astype("<f4").tobytes()).hexdigest(),
                "wbmSha256": hashlib.sha256(wbm.tobytes()).hexdigest(),
                "edmSha256": hashlib.sha256(edm.tobytes()).hexdigest(),
                "exactZeroElevPixels": int(np.count_nonzero(z == 0.0)),
                "oceanNonZeroElevPixels": int(np.count_nonzero((wbm == 1) & (z != 0.0))),
                "wbmCounts": {str(int(k)): int(v) for k, v in zip(wu, wc)},
                "edmCounts": {str(int(k)): int(v) for k, v in zip(eu, ec)},
            })
    return {
        "generatedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "datasetId": "copernicus-dem-glo30",
        "license": lic,
        "overviewLevel": overview_level,
        "tiles": rows,
    }


def _main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Work order #76 source QA replays and live DEM WBM/EDM probes.")
    sub = p.add_subparsers(dest="cmd", required=True)
    for name in ("replay-mod11c3", "probe-dem", "audit-all"):
        sp = sub.add_parser(name)
        sp.add_argument("--repo", type=Path, default=REPO)
        sp.add_argument("--snapshots", type=Path, default=None)
        sp.add_argument("--out", type=Path, default=None)
    args = p.parse_args(argv)
    repo = args.repo.resolve()
    sroot = resolve_snapshots_root(args.snapshots) if args.snapshots else (repo / "data" / "snapshots")
    manifest = json.loads((repo / "data" / "snapshots" / "MANIFEST.json").read_text(encoding="utf-8"))
    catalog_dir = repo / "data" / "catalog"
    out_dir = args.out or (repo / "docs" / "qa" / "source-qa-76")
    out_dir.mkdir(parents=True, exist_ok=True)

    if args.cmd in ("replay-mod11c3", "audit-all"):
        res = replay_mod11c3(manifest["entries"], repo_root=repo, snapshots_root=sroot, catalog_dir=catalog_dir)
        (out_dir / "mod11c3-qa-replay.json").write_text(json.dumps(res, indent=2) + "\n", encoding="utf-8")
        print(f"Wrote {out_dir / 'mod11c3-qa-replay.json'} ({res['granuleCount']} granules)")
    if args.cmd in ("probe-dem", "audit-all"):
        probe = probe_copernicus_wbm_edm(catalog_dir=catalog_dir)
        probe["historicalLedgerAudit"] = audit_terrain_ledger(
            sroot / "copernicus-dem-glo30" / "tileList.txt",
            sroot / "_derived" / "terrain-r4-ledger.jsonl.gz",
            cells_parquet=sroot / "_derived" / "cells-r4.parquet",
            terrain_npz=sroot / "_derived" / "terrain-r4.npz",
        )
        (out_dir / "dem-wbm-probe.json").write_text(json.dumps(probe, indent=2) + "\n", encoding="utf-8")
        print(f"Wrote {out_dir / 'dem-wbm-probe.json'} ({len(probe['tiles'])} live tiles)")
    return 0


if __name__ == "__main__":
    sys.exit(_main())
