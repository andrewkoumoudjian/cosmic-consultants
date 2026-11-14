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


def _read_tile(tile: str, rank: np.ndarray):
    url = f"{BASE}/{tile}/{tile}.tif"
    t = time.time()
    with Env(**GDAL_ENV):
        with rasterio.open("/vsicurl/" + url, OVERVIEW_LEVEL=OVERVIEW_LEVEL) as ds:
            z = ds.read(1).astype(np.float64)
            tr = ds.transform
    digest = hashlib.sha256(z.astype("<f4").tobytes()).hexdigest()
    h, w = z.shape
    lat = tr.f + tr.e * (np.arange(h) + 0.5)
    lon = tr.c + tr.a * (np.arange(w) + 0.5)
    dy = abs(tr.e) * 110574.0
    dx = (tr.a * 111320.0 * np.cos(np.radians(lat)))[:, None]
    gy, gx = np.gradient(z)
    slope = np.degrees(np.arctan(np.hypot(gx / dx, gy / dy)))
    r = np.clip(((90.0 - lat) / CMG_STEP).astype(int), 0, 3599)
    c = np.clip(((lon + 180.0) / CMG_STEP).astype(int), 0, 7199)
    idx = rank[r[:, None], c[None, :]]
    keep = idx >= 0
    rec = {"tile": tile, "url": url, "shape": [h, w], "arraySha256": digest, "secs": round(time.time() - t, 2)}
    return rec, idx[keep], z[keep], slope[keep]


def run(res: int = RES, workers: int = 32, limit: int | None = None) -> dict:
    cellmap, _ = cmg_cell_map(res)
    order, cells, starts = group_index(cellmap)
    rank = np.full(cellmap.size, -1, dtype=np.int32)
    gid = np.repeat(np.arange(len(cells), dtype=np.int32), np.diff(np.append(starts, len(order))))
    rank[order] = gid
    rank = rank.reshape(cellmap.shape)

    n = len(cells)
    cnt = np.zeros(n); zs = np.zeros(n); zmin = np.full(n, np.inf); zmax = np.full(n, -np.inf)
    ssum = np.zeros(n); hist = np.zeros((n, len(BINS) - 1))
    tiles = tile_list()[:limit]
    ledger_path = DERIVED / f"terrain-r{res}-ledger.jsonl.gz"
    fails = []
    t0 = time.time()
    with gzip.open(ledger_path, "wt") as led, ThreadPoolExecutor(workers) as ex:
        futs = {ex.submit(_read_tile, t, rank): t for t in tiles}
        for i, f in enumerate(as_completed(futs), 1):
            tile = futs[f]
            try:
                rec, idx, z, s = f.result()
            except Exception as exc:  # noqa: BLE001 - recorded, cells stay partial
                fails.append(tile)
                led.write(json.dumps({"tile": tile, "error": str(exc)[:300]}) + "\n")
                continue
            led.write(json.dumps(rec) + "\n")
            np.add.at(cnt, idx, 1); np.add.at(zs, idx, z); np.add.at(ssum, idx, s)
            np.minimum.at(zmin, idx, z); np.maximum.at(zmax, idx, z)
            b = np.clip(np.searchsorted(BINS, s, side="right") - 1, 0, len(BINS) - 2)
            np.add.at(hist, (idx, b), 1)
            if i % 1000 == 0:
                print(f"{i}/{len(tiles)} tiles, {len(fails)} failed, {round(time.time()-t0)} s", flush=True)
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
               "failed": fails, "overviewLevel": OVERVIEW_LEVEL, "approxResolutionM": 240,
               "cellsWithTerrain": int(has.sum()), "seconds": round(time.time() - t0, 1),
               "ledger": str(ledger_path.relative_to(SNAP.parent.parent))}
    (DERIVED / f"terrain-r{res}.meta.json").write_text(json.dumps(summary, indent=2) + "\n")
    return summary


if __name__ == "__main__":
    lim = int(sys.argv[1]) if len(sys.argv) > 1 else None
    print(json.dumps(run(limit=lim), indent=1))
