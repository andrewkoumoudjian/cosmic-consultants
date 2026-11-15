"""Terrain per H3 cell from Copernicus GLO-30 COG overviews (streamed, not stored).

We read only overview level 2 (8x decimated, ~240 m) of each 1x1 deg tile over
HTTP range requests. Nothing raw is kept. The ledger records every tile's
URL, array shape and the sha256 of the exact array we used, so a re-run can be
checked bit for bit.
"""
from __future__ import annotations

import gzip
import hashlib
import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone

import numpy as np
import rasterio
from rasterio.env import Env

from .grid import CMG_STEP, DERIVED, RES, cmg_cell_map, group_index
from .snapshots import SNAP, fetch

BASE = "https://copernicus-dem-30m.s3.amazonaws.com"
OVERVIEW_LEVEL = 2  # levels are 2x, 4x, 8x; index 2 = 8x (~240 m)
BINS = np.array([0, 5, 15, 30, 90.01])  # slope bins in degrees
GDAL_ENV = dict(GDAL_DISABLE_READDIR_ON_OPEN="EMPTY_DIR", CPL_VSIL_CURL_ALLOWED_EXTENSIONS=".tif",
                GDAL_HTTP_MULTIRANGE="YES", GDAL_HTTP_MAX_RETRY="4", GDAL_HTTP_RETRY_DELAY="2",
                VSI_CACHE="FALSE")


def tile_list() -> list[str]:
    p = fetch("copernicus-dem-glo30", f"{BASE}/tileList.txt")
    return [t.strip() for t in p.read_text().split() if t.strip()]


def _slope_deg(z: np.ndarray, dx: np.ndarray, dy: float) -> np.ndarray:
    """Compute slope [deg] on a potentially NaN-masked DEM without ocean contamination.

    Interior pixels use central differences when both neighbors are finite, falling
    back to one-sided differences at masked water/void boundaries. Invalid pixels
    stay NaN.
    """
    valid = np.isfinite(z)
    h, w = z.shape
    gx = np.full((h, w), np.nan, dtype=np.float64)
    gy = np.full((h, w), np.nan, dtype=np.float64)

    if w >= 2:
        # Interior central difference where both left and right exist
        both_x = valid[:, :-2] & valid[:, 2:]
        gx[:, 1:-1] = np.where(both_x, (z[:, 2:] - z[:, :-2]) / (2.0 * dx), gx[:, 1:-1])
        # Forward / backward one-sided differences where one neighbor is masked/edge
        fwd_x = valid[:, :-1] & valid[:, 1:] & ~np.isfinite(gx[:, :-1])
        gx[:, :-1] = np.where(fwd_x, (z[:, 1:] - z[:, :-1]) / dx, gx[:, :-1])
        bwd_x = valid[:, :-1] & valid[:, 1:] & ~np.isfinite(gx[:, 1:])
        gx[:, 1:] = np.where(bwd_x, (z[:, 1:] - z[:, :-1]) / dx, gx[:, 1:])
    if h >= 2:
        both_y = valid[:-2, :] & valid[2:, :]
        gy[1:-1, :] = np.where(both_y, (z[2:, :] - z[:-2, :]) / (2.0 * dy), gy[1:-1, :])
        fwd_y = valid[:-1, :] & valid[1:, :] & ~np.isfinite(gy[:-1, :])
        gy[:-1, :] = np.where(fwd_y, (z[1:, :] - z[:-1, :]) / dy, gy[:-1, :])
        bwd_y = valid[:-1, :] & valid[1:, :] & ~np.isfinite(gy[1:, :])
        gy[1:, :] = np.where(bwd_y, (z[1:, :] - z[:-1, :]) / dy, gy[1:, :])

    return np.where(valid & np.isfinite(gx) & np.isfinite(gy), np.degrees(np.arctan(np.hypot(gx, gy))), np.nan)


def mask_tile_arrays(
    z: np.ndarray,
    wbm: np.ndarray | None = None,
    edm: np.ndarray | None = None,
    nodata: float | None = None,
) -> tuple[np.ndarray, dict[str, int]]:
    """Mask water bodies (WBM != 0) and void/nodata pixels (EDM == 0 or nodata) to NaN."""
    z_out = z.astype(np.float64, copy=True)
    void_mask = ~np.isfinite(z_out)
    if nodata is not None and np.isfinite(nodata):
        void_mask |= z_out == float(nodata)
    if edm is not None:
        void_mask |= edm == 0
    water_mask = (wbm != 0) & ~void_mask if wbm is not None else np.zeros(z_out.shape, dtype=bool)
    invalid = void_mask | water_mask
    z_out[invalid] = np.nan
    counts = {
        "totalPixels": int(z_out.size),
        "maskedWaterPixels": int(np.count_nonzero(water_mask)),
        "maskedVoidPixels": int(np.count_nonzero(void_mask)),
        "retainedLandPixels": int(z_out.size - np.count_nonzero(invalid)),
    }
    return z_out, counts


def _read_tile(tile: str, rank: np.ndarray, mask_water: bool = True):
    url = f"{BASE}/{tile}/{tile}.tif"
    stem = tile[:-4] if tile.endswith("_DEM") else tile
    wbm_url = f"{BASE}/{tile}/AUXFILES/{stem}_WBM.tif"
    edm_url = f"{BASE}/{tile}/AUXFILES/{stem}_EDM.tif"
    t = time.time()
    wbm = edm = None
    wbm_available = False
    with Env(**GDAL_ENV):
        with rasterio.open("/vsicurl/" + url, OVERVIEW_LEVEL=OVERVIEW_LEVEL) as ds:
            z = ds.read(1).astype(np.float64)
            tr = ds.transform
            nodata = ds.nodata
        if mask_water:
            try:
                with rasterio.open("/vsicurl/" + wbm_url, OVERVIEW_LEVEL=OVERVIEW_LEVEL) as wds:
                    wbm = wds.read(1)
                with rasterio.open("/vsicurl/" + edm_url, OVERVIEW_LEVEL=OVERVIEW_LEVEL) as eds:
                    edm = eds.read(1)
                wbm_available = True
            except Exception:  # noqa: BLE001 - recorded per tile in ledger
                wbm = edm = None
    digest = hashlib.sha256(z.astype("<f4").tobytes()).hexdigest()
    z_clean, mcounts = mask_tile_arrays(z, wbm=wbm if mask_water else None, edm=edm if mask_water else None, nodata=nodata)
    h, w = z_clean.shape
    lat = tr.f + tr.e * (np.arange(h) + 0.5)
    lon = tr.c + tr.a * (np.arange(w) + 0.5)
    dy = abs(tr.e) * 110574.0
    dx = (tr.a * 111320.0 * np.cos(np.radians(lat)))[:, None]
    slope = _slope_deg(z_clean, dx, dy)
    r = np.clip(((90.0 - lat) / CMG_STEP).astype(int), 0, 3599)
    c = np.clip(((lon + 180.0) / CMG_STEP).astype(int), 0, 7199)
    idx = rank[r[:, None], c[None, :]]
    keep = (idx >= 0) & np.isfinite(z_clean) & np.isfinite(slope)
    rec = {
        "tile": tile,
        "url": url,
        "shape": [h, w],
        "arraySha256": digest,
        "wbmAvailable": wbm_available,
        **mcounts,
        "secs": round(time.time() - t, 2),
    }
    return rec, idx[keep], z_clean[keep], slope[keep]


def run(res: int = RES, workers: int = 32, limit: int | None = None, mask_water: bool = True) -> dict:
    cellmap, _ = cmg_cell_map(res)
    order, cells, starts = group_index(cellmap)
    rank = np.full(cellmap.size, -1, dtype=np.int32)
    gid = np.repeat(np.arange(len(cells), dtype=np.int32), np.diff(np.append(starts, len(order))))
    rank[order] = gid
    rank = rank.reshape(cellmap.shape)

    n = len(cells)
    tiles = sorted(tile_list())[:limit]
    parts = DERIVED / f"terrain-r{res}-parts"
    parts.mkdir(parents=True, exist_ok=True)
    CHUNK = 1000
    fails = []
    t0 = time.time()
    # Resumable: each chunk of 1,000 tiles is saved as its own part file, so a
    # killed run picks up at the first missing chunk.
    for ci in range(0, len(tiles), CHUNK):
        part = parts / f"part-{ci // CHUNK:03d}.npz"
        if part.exists():
            continue
        chunk = tiles[ci:ci + CHUNK]
        cnt = np.zeros(n); zs = np.zeros(n); zmin = np.full(n, np.inf); zmax = np.full(n, -np.inf)
        ssum = np.zeros(n); hist = np.zeros((n, len(BINS) - 1))
        ledger = []
        with ThreadPoolExecutor(workers) as ex:
            futs = {ex.submit(_read_tile, t, rank, mask_water): t for t in chunk}
            for f in as_completed(futs):
                tile = futs[f]
                try:
                    rec, idx, z, s = f.result()
                except Exception as exc:  # noqa: BLE001 - recorded, cells stay partial
                    ledger.append({"tile": tile, "error": str(exc)[:300]})
                    continue
                ledger.append(rec)
                np.add.at(cnt, idx, 1); np.add.at(zs, idx, z); np.add.at(ssum, idx, s)
                np.minimum.at(zmin, idx, z); np.maximum.at(zmax, idx, z)
                b = np.clip(np.searchsorted(BINS, s, side="right") - 1, 0, len(BINS) - 2)
                np.add.at(hist, (idx, b), 1)
        tmp = part.with_suffix(".tmp.npz")
        np.savez_compressed(tmp, cnt=cnt, zs=zs, zmin=zmin, zmax=zmax, ssum=ssum, hist=hist,
                            ledger=np.array([json.dumps(r) for r in sorted(ledger, key=lambda r: r["tile"])]))
        tmp.replace(part)
        print(f"{min(ci + CHUNK, len(tiles))}/{len(tiles)} tiles, chunk {ci // CHUNK} saved, {round(time.time()-t0)} s", flush=True)

    cnt = np.zeros(n); zs = np.zeros(n); zmin = np.full(n, np.inf); zmax = np.full(n, -np.inf)
    ssum = np.zeros(n); hist = np.zeros((n, len(BINS) - 1))
    water_masked_px = void_masked_px = retained_land_px = 0
    ledger_path = DERIVED / f"terrain-r{res}-ledger.jsonl.gz"
    with gzip.open(ledger_path, "wt") as led:
        for ci in range(0, len(tiles), CHUNK):
            p = np.load(parts / f"part-{ci // CHUNK:03d}.npz")
            cnt += p["cnt"]; zs += p["zs"]; ssum += p["ssum"]; hist += p["hist"]
            zmin = np.minimum(zmin, p["zmin"]); zmax = np.maximum(zmax, p["zmax"])
            for line in p["ledger"]:
                s_line = str(line)
                led.write(s_line + "\n")
                obj = json.loads(s_line)
                if "error" in obj:
                    fails.append(obj["tile"])
                else:
                    water_masked_px += int(obj.get("maskedWaterPixels", 0))
                    void_masked_px += int(obj.get("maskedVoidPixels", 0))
                    retained_land_px += int(obj.get("retainedLandPixels", 0))
    has = cnt > 0
    nan = lambda a: np.where(has, a, np.nan)  # noqa: E731
    out = {
        "h3": np.array([format(int(c), "x") for c in cells]),
        "dem_pixels": cnt,
        "elev_mean_m": nan(zs / np.maximum(cnt, 1)), "elev_min_m": nan(zmin), "elev_max_m": nan(zmax),
        "slope_mean_deg": nan(ssum / np.maximum(cnt, 1)),
        "slope_frac_lt5": nan(hist[:, 0] / np.maximum(cnt, 1)),
        "slope_frac_lt15": nan((hist[:, 0] + hist[:, 1]) / np.maximum(cnt, 1)),
        "slope_frac_gt30": nan(hist[:, 3] / np.maximum(cnt, 1)),
    }
    np.savez_compressed(DERIVED / f"terrain-r{res}.npz", **out)
    summary = {"generatedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"), "tiles": len(tiles),
               "chunks": (len(tiles) + CHUNK - 1) // CHUNK,
               "failed": fails, "overviewLevel": OVERVIEW_LEVEL, "approxResolutionM": 240,
               "waterMasked": mask_water,
               "totalMaskedWaterPixels": water_masked_px,
               "totalMaskedVoidPixels": void_masked_px,
               "totalRetainedLandPixels": retained_land_px,
               "cellsWithTerrain": int(has.sum()), "secondsThisRun": round(time.time() - t0, 1),
               "ledger": str(ledger_path.relative_to(SNAP.parent.parent))}
    (DERIVED / f"terrain-r{res}.meta.json").write_text(json.dumps(summary, indent=2) + "\n")
    return summary


if __name__ == "__main__":
    lim = int(sys.argv[1]) if len(sys.argv) > 1 else None
    print(json.dumps(run(limit=lim), indent=1))
