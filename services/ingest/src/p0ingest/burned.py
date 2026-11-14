"""Burned area per H3 cell and calendar month from MODIS MCD64A1 v061 (streamed, not stored).

Issue #65 (W25). 32,160 monthly 500 m tiles (2015-2024) are downloaded one at a
time, decoded, folded into per-hexagon pixel counts and dropped. The ledger
records every granule's URL, sha256, size and fetch time, so the counts can be
audited without keeping the raw files (same rule as Copernicus DEM in terrain.py).

Layer `Burn Date` (int16): >0 burned (day of year), 0 mapped and not burned,
-1 not mapped, -2 water. A pixel counts in the denominator when it is mapped
land (>= 0). Per hexagon, month and year:

    share = burned pixels / mapped pixels      (only when mapped pixels > 0)

`burned_pct_<mm>` is 100 x the mean of those shares over the years that had
mapped pixels that month (not pooled pixels, so a big mapped year can't drown a
small one). No mapped pixel in any year gives null.

Run:  uv run python -m p0ingest.burned [--workers 32] [--limit N]
Then: uv run python -m p0ingest.context   (adds the 13 columns to L2)
"""
from __future__ import annotations

import argparse
import datetime as dt
import gzip
import hashlib
import json
import os
import re
import sys
import tempfile
import threading
import time
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor
from pathlib import Path

import h3
import numpy as np
import pyarrow.parquet as pq
import requests
from pyhdf.SD import SD, SDC

from .grid import DERIVED
from .snapshots import MANIFEST, REPO, SNAP, UA, _AuthSession, _token, catalog_row, sha256

DATASET = "modis-mcd64a1"
CONCEPT_ID = "C2565786756-LPCLOUD"
CMR_URL = "https://cmr.earthdata.nasa.gov/search/granules.json"
TEMPORAL = "2015-01-01T00:00:00Z,2024-12-31T23:59:59Z"
YEARS = tuple(range(2015, 2025))
EXPECTED_GRANULES = 32160
RES = 4

# MODIS sinusoidal grid (MCD64A1 500 m): sphere R, pixel size, upper-left corner, 2400 px per tile.
R_SPHERE = 6371007.181
PIXEL_M = 463.31271653
X0, Y0 = -20015109.354, 10007554.677
TILE_PX = 2400

LIST_REL = f"data/snapshots/{DATASET}/granule-list-2015-2024.txt"
TILEMAPS = DERIVED / f"burned-r{RES}-tilemaps"
CHECKPOINT = DERIVED / f"burned-r{RES}-checkpoint.npz"
PARTIAL = DERIVED / f"burned-r{RES}-ledger.partial.jsonl"
LEDGER = DERIVED / f"burned-r{RES}-ledger.jsonl.gz"
COUNTS = DERIVED / f"burned-r{RES}-counts.npz"
RUN_META = DERIVED / f"burned-r{RES}.meta.json"
CHECKPOINT_EVERY = 400
_NAME = re.compile(r"MCD64A1\.A(\d{4})(\d{3})\.h(\d{2})v(\d{2})\.061\.")

# Columns this module adds to L2 (documented in context-r4.meta.json and DATA-PIPELINE.md §5)
MONTH_COLS = [f"burned_pct_{m:02d}" for m in range(1, 13)]
YEARS_COL = "burned_years_mapped"
YEARS_BY_MONTH_COL = "burned_years_by_month"
CODE_NO_PIXELS = "no-mapped-pixels"       # hexagon had MCD64A1 pixels, none mapped land in any year this month
CODE_NO_COVERAGE = "outside-mcd64a1-tiles"  # no MCD64A1 pixel at all (e.g. Antarctica)


# --------------------------------------------------------------------------- hexagons

def l1_cells() -> tuple[list[str], np.ndarray]:
    """H3 cell ids of the 91,800 land hexagons in L1 order, and the same as uint64."""
    path = DERIVED / "cells-r4.parquet"
    if not path.is_file():
        path = Path("/home/drew/cosmic-consultants/data/snapshots/_derived/cells-r4.parquet")
    hexes = pq.read_table(path, columns=["h3"]).column("h3").to_pylist()
    if len(hexes) != 91800:
        raise RuntimeError(f"expected 91,800 L1 land cells, got {len(hexes)}")
    return hexes, np.array([int(c, 16) for c in hexes], dtype=np.uint64)


# --------------------------------------------------------------------------- granule list

def _manifest_append(entry: dict) -> None:
    """Append-only edit of MANIFEST.json (never re-sorts, so other lanes' entries don't move)."""
    m = json.loads(MANIFEST.read_text(encoding="utf-8"))
    if any(e.get("localPath") == entry["localPath"] for e in m["entries"]):
        raise RuntimeError(f"{entry['localPath']} already in MANIFEST.json; append-only")
    m["entries"].append(entry)
    tmp = MANIFEST.with_suffix(".tmp")
    tmp.write_text(json.dumps(m, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    os.replace(tmp, MANIFEST)


def granule_list() -> list[str]:
    """Granule URLs for 2015-2024, from CMR (cached as a hashed listing, like Copernicus tileList.txt)."""
    path = REPO / LIST_REL
    if path.is_file():
        urls = path.read_text().split()
        if len(urls) != EXPECTED_GRANULES:
            raise RuntimeError(f"{path}: {len(urls)} URLs, expected {EXPECTED_GRANULES}")
        return urls
    row = catalog_row(DATASET)
    if not (row.get("license") or {}).get("verified"):
        raise RuntimeError("MCD64A1 licence not verified in its catalog row")
    sess = requests.Session()
    sess.headers.update(UA)
    urls, page, hits = [], 1, None
    while True:
        r = sess.get(CMR_URL, params={"collection_concept_id": CONCEPT_ID, "temporal": TEMPORAL,
                                      "page_size": 2000, "page_num": page, "sort_key": "start_date"}, timeout=120)
        r.raise_for_status()
        hits = int(r.headers["CMR-Hits"])
        entries = r.json()["feed"]["entry"]
        if not entries:
            break
        for e in entries:
            hrefs = [lk["href"] for lk in e.get("links", [])
                     if lk["href"].startswith("https://") and lk["href"].endswith(".hdf")]
            if len(hrefs) != 1:
                raise RuntimeError(f"{e['title']}: expected one https .hdf link, got {hrefs}")
            urls.append(hrefs[0])
        page += 1
    urls = sorted(set(urls), key=lambda u: u.rsplit("/", 1)[-1])
    if hits != EXPECTED_GRANULES or len(urls) != EXPECTED_GRANULES:
        raise RuntimeError(f"CMR hits {hits}, URLs {len(urls)}; expected {EXPECTED_GRANULES}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(urls) + "\n")
    _manifest_append({
        "datasetId": DATASET,
        "sourceUrl": f"{CMR_URL}?collection_concept_id={CONCEPT_ID}&temporal={TEMPORAL}&page_size=2000",
        "fetchedAt": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "sha256": sha256(path), "bytes": path.stat().st_size,
        "license": row["license"]["id"], "licenseVerified": True, "localPath": LIST_REL,
    })
    return urls


def parse_name(url: str) -> tuple[int, int, int, int]:
    """(year, month, h, v) from a granule URL; the file is the month that starts on that day of year."""
    m = _NAME.search(url.rsplit("/", 1)[-1])
    if not m:
        raise ValueError(f"not an MCD64A1 granule name: {url}")
    year, doy, h, v = (int(g) for g in m.groups())
    day = dt.date(year, 1, 1) + dt.timedelta(days=doy - 1)
    if day.day != 1:
        raise ValueError(f"granule date {day} is not the first of a month: {url}")
    return year, day.month, h, v


# --------------------------------------------------------------------------- pixel -> hexagon

def _tilemap_path(h: int, v: int) -> Path:
    return TILEMAPS / f"h{h:02d}v{v:02d}.npz"


def build_tilemap(args) -> str:
    """Row index (into the 91,800-cell list) of the hexagon containing each pixel centre; -1 = none."""
    h, v, sorted_ids, order = args
    path = _tilemap_path(h, v)
    if path.exists():
        return path.name
    x = X0 + (h * TILE_PX + np.arange(TILE_PX) + 0.5) * PIXEL_M
    y = Y0 - (v * TILE_PX + np.arange(TILE_PX) + 0.5) * PIXEL_M
    phi = y / R_SPHERE                                          # latitude [rad], per row
    lam = x[None, :] / (R_SPHERE * np.cos(phi)[:, None])        # longitude [rad]
    ok = (np.abs(lam) <= np.pi) & (np.abs(phi) < np.pi / 2)[:, None]
    lat = np.degrees(np.broadcast_to(phi[:, None], lam.shape))[ok]
    lon = np.degrees(lam)[ok]
    cells = np.fromiter((int(h3.latlng_to_cell(a, b, RES), 16) for a, b in zip(lat.tolist(), lon.tolist())),
                        dtype=np.uint64, count=lat.size)
    pos = np.searchsorted(sorted_ids, cells)
    pos[pos >= len(sorted_ids)] = 0
    hit = sorted_ids[pos] == cells
    idx = np.full(TILE_PX * TILE_PX, -1, dtype=np.int32)
    flat = np.flatnonzero(ok.ravel())
    idx[flat[hit]] = order[pos[hit]].astype(np.int32)
    TILEMAPS.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp.npz")
    np.savez_compressed(tmp, idx=idx.reshape(TILE_PX, TILE_PX))
    tmp.replace(path)
    return path.name


# --------------------------------------------------------------------------- decode (worker process)

_MAPS: dict[tuple[int, int], np.ndarray] = {}


def _tilemap(h: int, v: int) -> np.ndarray:
    key = (h, v)
    if key not in _MAPS:
        if len(_MAPS) >= 3:
            _MAPS.pop(next(iter(_MAPS)))
        _MAPS[key] = np.load(_tilemap_path(h, v))["idx"]
    return _MAPS[key]


def decode(path: str, h: int, v: int, n_cells: int) -> dict:
    """Per-hexagon pixel counts for one granule: burned, mapped land (incl. burned), unmapped (-1)."""
    sd = SD(path, SDC.READ)
    bd = sd.select("Burn Date")[:]
    sd.end()
    if bd.shape != (TILE_PX, TILE_PX) or bd.dtype != np.int16:
        raise RuntimeError(f"unexpected Burn Date array {bd.dtype} {bd.shape}")
    if bd.min() < -2 or bd.max() > 366:
        raise RuntimeError(f"Burn Date outside [-2, 366]: {bd.min()}..{bd.max()}")
    idx = _tilemap(h, v)
    sel = idx >= 0
    i, b = idx[sel], bd[sel]
    tot = np.bincount(i, minlength=n_cells)
    cells = np.flatnonzero(tot)
    burned = np.bincount(i[b > 0], minlength=n_cells)[cells]
    mapped = np.bincount(i[b >= 0], minlength=n_cells)[cells]
    unmapped = np.bincount(i[b == -1], minlength=n_cells)[cells]
    return {"cells": cells.astype(np.int32), "burned": burned.astype(np.int32),
            "mapped": mapped.astype(np.int32), "unmapped": unmapped.astype(np.int32)}


# --------------------------------------------------------------------------- the streaming run

class Run:
    def __init__(self, urls: list[str], workers: int, n_cells: int):
        self.urls, self.workers, self.n = urls, workers, n_cells
        self.lock = threading.Lock()
        shape = (len(YEARS), 12, n_cells)
        self.burned = np.zeros(shape, np.int32)
        self.mapped = np.zeros(shape, np.int32)
        self.unmapped = np.zeros(shape, np.int32)
        self.done: set[str] = set()
        self.failures: dict[str, str] = {}
        self.sum_bytes = 0
        self.since_ckpt = 0
        self.t0 = time.time()
        self.partial = None

    # -- resume
    def resume(self) -> None:
        if not (CHECKPOINT.exists() and PARTIAL.exists()):
            PARTIAL.write_text("")
            return
        ck = np.load(CHECKPOINT)
        k = int(ck["ledger_lines"])
        lines = PARTIAL.read_text().splitlines()[:k]
        if len(lines) != k:
            raise RuntimeError(f"checkpoint says {k} ledger lines, partial ledger has {len(lines)}")
        self.burned, self.mapped, self.unmapped = ck["burned"], ck["mapped"], ck["unmapped"]
        self.done = {json.loads(line)["url"] for line in lines}
        self.sum_bytes = sum(json.loads(line)["bytes"] for line in lines)
        PARTIAL.write_text("".join(line + "\n" for line in lines))   # drop lines written after the checkpoint
        print(f"resumed: {len(self.done)} granules already in the ledger", flush=True)

    def checkpoint(self) -> None:
        self.partial.flush()
        os.fsync(self.partial.fileno())
        k = len(self.done)
        tmp = CHECKPOINT.with_suffix(".tmp.npz")
        np.savez(tmp, burned=self.burned, mapped=self.mapped, unmapped=self.unmapped, ledger_lines=k)
        tmp.replace(CHECKPOINT)
        self.since_ckpt = 0
        rate = (time.time() - self.t0)
        print(f"[{round(rate)} s] {k}/{len(self.urls)} granules, {len(self.failures)} failed, "
              f"{self.sum_bytes / 1e6:.0f} MB read, checkpoint saved", flush=True)

    # -- one granule
    def fetch_decode(self, sess: requests.Session, pool: ProcessPoolExecutor, url: str) -> None:
        year, month, h, v = parse_name(url)
        last = None
        for attempt in range(5):
            tmp = None
            try:
                r = sess.get(url, timeout=(30, 300), allow_redirects=True)
                if r.status_code >= 400:
                    raise RuntimeError(f"HTTP {r.status_code}")
                if "text/html" in r.headers.get("Content-Type", ""):
                    raise RuntimeError("HTML instead of data (login page?)")
                body = r.content
                if len(body) < 1000:
                    raise RuntimeError(f"only {len(body)} bytes")
                fetched = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
                fd, tmp = tempfile.mkstemp(suffix=".hdf", dir="/dev/shm" if os.path.isdir("/dev/shm") else None)
                with os.fdopen(fd, "wb") as f:
                    f.write(body)
                res = pool.submit(decode, tmp, h, v, self.n).result()
                rec = {"url": url, "sha256": hashlib.sha256(body).hexdigest(), "bytes": len(body),
                       "fetchedAt": fetched, "year": year, "month": month,
                       "burnedPx": int(res["burned"].sum()), "mappedPx": int(res["mapped"].sum())}
                with self.lock:
                    c = res["cells"]
                    self.burned[year - YEARS[0], month - 1, c] += res["burned"]
                    self.mapped[year - YEARS[0], month - 1, c] += res["mapped"]
                    self.unmapped[year - YEARS[0], month - 1, c] += res["unmapped"]
                    self.partial.write(json.dumps(rec, separators=(",", ":")) + "\n")
                    self.done.add(url)
                    self.failures.pop(url, None)
                    self.sum_bytes += len(body)
                    self.since_ckpt += 1
                    if self.since_ckpt >= CHECKPOINT_EVERY:
                        self.checkpoint()
                return
            except Exception as exc:  # noqa: BLE001 - retried, then recorded
                last = f"{type(exc).__name__}: {str(exc)[:200]}"
                time.sleep(2 ** attempt)
            finally:
                if tmp and os.path.exists(tmp):
                    os.unlink(tmp)
        with self.lock:
            self.failures[url] = last or "unknown"

    def go(self) -> None:
        tok = _token()
        if not tok:
            raise RuntimeError("no Earthdata token at ~/.config/cosmic-consultants/earthdata-token")
        self.resume()
        todo = [u for u in self.urls if u not in self.done]
        print(f"{len(todo)} granules to fetch ({len(self.done)} done)", flush=True)
        self.partial = PARTIAL.open("a", encoding="utf-8")
        local = threading.local()

        def session() -> requests.Session:
            if not hasattr(local, "s"):
                local.s = _AuthSession(tok)
                local.s.headers["Authorization"] = f"Bearer {tok}"
            return local.s

        import multiprocessing as mp
        with ProcessPoolExecutor(max_workers=min(8, os.cpu_count() or 2), mp_context=mp.get_context("spawn")) as pool:
            with ThreadPoolExecutor(self.workers) as ex:
                list(ex.map(lambda u: self.fetch_decode(session(), pool, u), todo))
        with self.lock:
            self.checkpoint()
        self.partial.close()


def finalize(run: Run, urls: list[str]) -> dict:
    """Write the sorted gzip ledger (reproducible bytes) and the final counts."""
    recs = [json.loads(line) for line in PARTIAL.read_text().splitlines()]
    recs.sort(key=lambda r: r["url"].rsplit("/", 1)[-1])
    with open(LEDGER, "wb") as raw, gzip.GzipFile(fileobj=raw, mode="wb", mtime=0, filename="") as gz:
        for r in recs:
            gz.write((json.dumps(r, separators=(",", ":")) + "\n").encode())
    np.savez_compressed(COUNTS, burned=run.burned, mapped=run.mapped, unmapped=run.unmapped)
    meta = {
        "generatedAt": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "dataset": DATASET, "years": [YEARS[0], YEARS[-1]], "granulesExpected": len(urls),
        "granulesInLedger": len(recs), "granulesFailed": len(run.failures),
        "failures": run.failures, "bytesRead": sum(r["bytes"] for r in recs),
        "secondsThisRun": round(time.time() - run.t0, 1),
        "listing": {"path": LIST_REL, "sha256": sha256(REPO / LIST_REL)},
        "ledger": {"path": str(LEDGER.relative_to(REPO)), "sha256": sha256(LEDGER), "bytes": LEDGER.stat().st_size},
        "counts": {"path": str(COUNTS.relative_to(REPO)), "sha256": sha256(COUNTS)},
    }
    RUN_META.write_text(json.dumps(meta, indent=2) + "\n")
    return meta


def run(workers: int = 32, limit: int | None = None) -> dict:
    hexes, ids = l1_cells()
    order = np.argsort(ids)
    sorted_ids = ids[order]
    urls = granule_list()
    # Order by tile, then date: neighbouring downloads share one tile map in the decoder's cache.
    urls = sorted(urls, key=lambda u: (parse_name(u)[2:], parse_name(u)[:2]))
    if limit:
        urls = urls[:limit]
    tiles = sorted({parse_name(u)[2:] for u in urls})
    todo = [(h, v, sorted_ids, order) for h, v in tiles if not _tilemap_path(h, v).exists()]
    if todo:
        t = time.time()
        print(f"building {len(todo)} pixel->hexagon tile maps ({len(tiles)} tiles in the list)", flush=True)
        import multiprocessing as mp
        with ProcessPoolExecutor(max_workers=os.cpu_count() or 4, mp_context=mp.get_context("spawn")) as ex:
            list(ex.map(build_tilemap, todo, chunksize=1))
        print(f"tile maps done in {round(time.time() - t)} s", flush=True)
    r = Run(urls, workers, len(hexes))
    r.go()
    if r.failures:
        print(f"{len(r.failures)} granules failed after retries", flush=True)
    return finalize(r, urls)


# --------------------------------------------------------------------------- columns for L2

def load_columns() -> dict:
    """Arrays context.py turns into the 13 L2 columns (needs a finished run)."""
    ck = np.load(COUNTS)
    burned, mapped, unmapped = (ck[k].astype(np.float64) for k in ("burned", "mapped", "unmapped"))
    valid = mapped > 0                                           # (years, 12, cells)
    share = np.where(valid, burned / np.maximum(mapped, 1), 0.0)
    ny = valid.sum(0)                                            # (12, cells) years that had mapped pixels
    pct = np.where(ny > 0, 100.0 * share.sum(0) / np.maximum(ny, 1), np.nan)
    covered = (mapped + unmapped).sum(axis=(0, 1)) > 0           # any MCD64A1 pixel ever in this hexagon
    years_any = valid.any(1).sum(0)                              # years with mapped pixels in >= 1 month
    return {"pct": pct, "years_by_month": ny.astype(np.int8), "years_any": years_any.astype(np.int8),
            "covered": covered}


def years_by_month_str(ny: np.ndarray) -> list[str]:
    """12-character string per cell: years (0-9, 'a' = 10) with mapped pixels in each month, January first."""
    digits = np.array(list("0123456789a"))
    return ["".join(row) for row in digits[ny.T]]


def spot_checks() -> None:
    """Print burned_pct_<mm> at fire-prone places and at ice, from the finished L2 file."""
    table = pq.read_table(DERIVED / "context-r4.parquet")
    ix = {h: i for i, h in enumerate(table["h3"].to_pylist())}
    places = {"Arnhem Land, N Australia": (-13.0, 131.5), "Central African Republic (savanna)": (7.0, 22.0),
              "Sahel, southern Niger/Nigeria": (12.0, 8.0), "Butte County, California": (39.8, -121.6),
              "Antarctica interior": (-80.0, 0.0), "Greenland interior": (72.0, -40.0),
              "Death Valley": (36.24, -116.82)}
    for name, (la, lo) in places.items():
        cell = h3.latlng_to_cell(la, lo, RES)
        i = ix.get(cell)
        if i is None:
            print(json.dumps({"spot": name, "lat": la, "lon": lo, "h3": cell, "note": "not a land cell in L1"}))
            continue
        reasons = json.loads(table["missing_reason"][i].as_py())
        print(json.dumps({"spot": name, "h3": cell,
                          "burned_pct": [None if table[c][i].as_py() is None else round(table[c][i].as_py(), 3)
                                         for c in MONTH_COLS],
                          YEARS_COL: table[YEARS_COL][i].as_py(),
                          YEARS_BY_MONTH_COL: table[YEARS_BY_MONTH_COL][i].as_py(),
                          "missing": {k: v for k, v in reasons.items() if k.startswith("burned")}}))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--workers", type=int, default=32)
    ap.add_argument("--limit", type=int, default=None, help="first N granules (testing only)")
    ap.add_argument("--spots", action="store_true", help="only print spot checks from context-r4.parquet")
    a = ap.parse_args()
    if a.spots:
        spot_checks()
        sys.exit(0)
    out = run(a.workers, a.limit)
    print(json.dumps({k: v for k, v in out.items() if k != "failures"}, indent=1))
    if out["failures"]:
        print("FAILURES:", json.dumps(out["failures"], indent=1))
    sys.exit(0 if not out["granulesFailed"] and not a.limit else 1)
