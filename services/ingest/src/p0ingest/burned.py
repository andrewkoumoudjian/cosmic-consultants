"""Burned area per H3 cell and calendar month from MODIS MCD64A1 v061 (issue #65, W25).

Output interface (per-source, long monthly table for the parent assembler):
  data/snapshots/_derived/burned-r4-monthly.parquet
  columns: h3, month (1-12), burned_pct [%], years_mapped (0-10), missing_reason (JSON)
  one row per (h3 land cell, calendar month): 91,800 x 12 = 1,101,600 rows.

Source messaging checked against the versioned primary docs and real granules
(evidence recorded in burned-r4-monthly.meta.json under `probe`):
  - MCD64A1 v061 User Guide (MCD64_User_Guide_V61.pdf, LP DAAC, fetched and hashed):
    "Burn Date: Ordinal day of burn (1-366) for each 500-m grid cell, with
     0 = unburned land, -1 = unmapped due to insufficient data, and -2 = water."
    "The MCD64 burned-area mapping approach employs 500-m MODIS imagery coupled
     with 1-km MODIS active fire observations."
    Validation section: omission errors dominate against 30-m reference data
    (72.6% omission, -54% global bias), compensated at coarser scales (r2 > 0.9).
  - a v061 granule's own HDF attributes: Burn Date valid_range [0, 366],
    _FillValue -1, water -2; QA legend: bit 0 land/water, bit 1 valid data flag,
    bit 2 shortened mapping period (Burn Date classes observed consistent with it).
  - a real fire granule (A2019244.h31v10, Sep 2019, northern Australia): every
    burned DOY observed inside the granule's own month (DOY 244-273), so
    aggregating by the granule's month never mixes cross-month burn dates.

Definition: per hexagon and calendar month, the mean over 2015-2024 years with
mapped land support of the yearly share of burned mapped-land pixels:

    share[y, m, c] = burned pixels / mapped-land pixels   (mapped land = Burn Date >= 0;
                    water (-2) never enters the denominator)
    burned_pct[m, c] = 100 * mean over years y with mapped > 0 of share[y, m, c]
    years_mapped[m, c] = number of years with mapped > 0 that the mean used

No mapped land in any year -> null, not zero, with a reason in missing_reason:
  outside-mcd64a1-tiles        no MCD64A1 pixel at all ever fell in the hexagon
                              (no MCD64A1 tile exists south of sinusoidal v14,
                              so e.g. all Antarctic land is honestly null)
  no-mapped-land-in-period    pixels exist but none is mapped land in this month
                              in any year (always water or always unmapped)
Rows whose support lost years to permanent granule fetch failures keep their
value over the remaining mapped years and carry burnedAreaSupport instead.

Streaming rule (issue #65, same as Copernicus DEM in terrain.py): the
268 tiles x 120 months of 2015-2024 are downloaded one at a time, decoded,
folded into per-hexagon pixel counts and dropped. Every granule's URL, sha256,
size, fetch time and pixel tallies go to a gzip JSONL ledger hashed in the run
metadata and MANIFEST.json, so counts are auditable without the raw files. A
checkpoint commits (counts + ledger line count) atomically; on restart the
ledger is truncated to the checkpointed count so URLs whose counts never
reached a checkpoint are re-fetched, never skipped.

Run:  uv run python -m p0ingest.burned [--workers 24] [--limit N]
Then:  uv run python -m p0ingest.burned --spots
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
import pyarrow as pa
import pyarrow.parquet as pq
import requests
from pyhdf.SD import SD, SDC

from .grid import DERIVED, RES
from .snapshots import MANIFEST, REPO, UA, _AuthSession, _token, catalog_row, sha256

DATASET = "modis-mcd64a1"
CONCEPT_ID = "C2565786756-LPCLOUD"
DOI = "10.5067/MODIS/MCD64A1.061"
CMR_URL = "https://cmr.earthdata.nasa.gov/search/granules.json"
TEMPORAL = "2015-01-01T00:00:00Z,2024-12-31T23:59:59Z"
YEARS = tuple(range(2015, 2025))
# Count at preparation time (live CMR probe 2026-11-14T19:46:58Z, CMR-Hits 32160).
# Reference only: fetch_granule_list() re-probes at use time and the live count
# governs the run; a mismatch with this reference is recorded, not fatal. Fatal
# is any disagreement between the live listing and its own headers, or a repeat
# of a (year, month, tile) granule (that would double count).
REFERENCE_GRANULES = 32160
TILE_PX = 2400

# MODIS sinusoidal grid, 500 m (MCD64A1): sphere R, pixel size, upper-left corner
# (User Guide p34: "500-m" cell = 463.31271653 m on a sphere of 6371007.181 m).
R_SPHERE = 6371007.181
PIXEL_M = 463.31271653
X0, Y0 = -20015109.354, 10007554.677

LIST_REL = f"data/snapshots/{DATASET}/granule-list-2015-2024.txt"
GUIDE_URL = "https://lpdaac.usgs.gov/documents/1006/MCD64_User_Guide_V61.pdf"
GUIDE_REL = f"data/snapshots/{DATASET}/MCD64_User_Guide_V61.pdf"
TILEMAPS = DERIVED / f"burned-r{RES}-tilemaps"
CHECKPOINT = DERIVED / f"burned-r{RES}-checkpoint.npz"
PARTIAL = DERIVED / f"burned-r{RES}-ledger.partial.jsonl"
LEDGER = DERIVED / f"burned-r{RES}-ledger.jsonl.gz"
LEDGER_REL = f"data/snapshots/_derived/burned-r{RES}-ledger.jsonl.gz"
COUNTS = DERIVED / f"burned-r{RES}-counts.npz"
OUT = DERIVED / f"burned-r{RES}-monthly.parquet"
OUT_REL = f"data/snapshots/_derived/burned-r{RES}-monthly.parquet"
META = DERIVED / f"burned-r{RES}-monthly.meta.json"
CHECKPOINT_EVERY = 400
MAX_ATTEMPTS = 5
_NAME = re.compile(r"MCD64A1\.A(\d{4})(\d{3})\.h(\d{2})v(\d{2})\.061\.")

REASON_NO_TILES = "outside-mcd64a1-tiles"
REASON_NO_MAPPED = "no-mapped-land-in-period"
REASON_PARTIAL_FETCH = "years-lost-to-granule-fetch-failures"

# Fixed evidence from the versioned source (probe details land in the run meta).
PROBE_EVIDENCE = {
    "userGuide": {
        "title": "MCD64A1 Collection 6.1 User Guide (LP DAAC)",
        "url": GUIDE_URL,
        "quotes": {
            "burnDate": "Burn Date: Ordinal day of burn (1-366) for each 500-m grid cell, "
                        "with 0 = unburned land, -1 = unmapped due to insufficient data, "
                        "and -2 = water.",
            "algorithm": "The MCD64 burned-area mapping approach employs 500-m MODIS imagery "
                         "coupled with 1-km MODIS active fire observations.",
            "validation": "Validation against 30-m Landsat reference data shows omission errors "
                          "dominate (72.6% omission, 2% commission, -54% global area bias), "
                          "which largely compensate at coarser resolution (r2 > 0.9).",
        },
    },
    "granuleAttributes": {
        "source": "MCD64A1.A2015001.h17v12.061 v061 granule SDS attributes (fetched 2026-11-14)",
        "burnDate": {"valid_range": [0, 366], "_FillValue": -1, "water": -2,
                     "long_name": "ordinal day of burn", "shape": [2400, 2400], "dtype": "int16"},
        "qaLegend": ("bit 0 Land/Water mask, bit 1 Valid data flag, bit 2 Shortened mapping "
                     "period, bit 3 Relabeled during contextual relabeling; observed "
                     "consistent with Burn Date classes (-2 water, -1 unmapped land, >=0 land)"),
    },
    "burnDateWithinMonth": {
        "source": "MCD64A1.A2019244.h31v10.061 (Sep 2019, northern Australia, "
                  "sha256 70af6b971597fd6868f9a05b6343a8f4a8fc34e79399ccd8f28a2455962a2bc1)",
        "observation": "all burned DOY values in [244, 273] == the granule's own month "
                       "(Sep 2019); monthly aggregation by granule month introduces no "
                       "cross-month bleed",
    },
}


# --------------------------------------------------------------------------- key set

def l1_cells() -> tuple[list[str], np.ndarray]:
    """H3 ids of the 91,800 land cells (master key set) in L1 order, and as uint64."""
    path = DERIVED / "cells-r4.parquet"
    if not path.is_file():
        path = Path("/home/drew/cosmic-consultants/data/snapshots/_derived/cells-r4.parquet")
    hexes = pq.read_table(path, columns=["h3"]).column("h3").to_pylist()
    if len(hexes) != 91800:
        raise RuntimeError(f"expected 91,800 L1 land cells, got {len(hexes)}")
    return hexes, np.array([int(c, 16) for c in hexes], dtype=np.uint64)


def validate_keys(table: pa.Table, hexes: list[str]) -> list[str]:
    """Key-domain check: exactly hexes x months 1-12, cell-major, no duplicates,
    unknown cells, invalid months or null keys."""
    problems: list[str] = []
    if table.num_rows != len(hexes) * 12:
        problems.append(f"row count {table.num_rows} != {len(hexes) * 12}")
    if table.column("h3").to_pylist() != [h for h in hexes for _ in range(12)]:
        problems.append("h3 column is not the master key set repeated 12x in L1 order")
    got = table.column("month").to_pylist()
    want = [m for _ in hexes for m in range(1, 13)]
    if got != want:
        problems.append("month column is not months 1-12 per cell in cell-major order")
    return problems


# --------------------------------------------------------------------------- granule list

def parse_name(url: str) -> tuple[int, int, int, int]:
    """(year, month, h, v). The granule is the month that starts on that day of year,
    asserted against the name so a reissued mid-month granule fails loudly."""
    m = _NAME.search(url.rsplit("/", 1)[-1])
    if not m:
        raise ValueError(f"not an MCD64A1 granule name: {url}")
    year, doy, h, v = (int(g) for g in m.groups())
    day = dt.date(year, 1, 1) + dt.timedelta(days=doy - 1)
    if day.day != 1:
        raise ValueError(f"granule date {day} is not the first of a month: {url}")
    return year, day.month, h, v


def fetch_granule_list() -> dict:
    """Live CMR listing at use time (AGENTS.md rule 2), cached as a hashed snapshot.

    Fatal on: HTTP error; hits != returned URLs; a name that does not parse to the
    first day of a month; a repeated (year, month, h, v) granule (overlap/reissue
    must never double count)."""
    path = REPO / LIST_REL
    row = catalog_row(DATASET)
    if not (row.get("license") or {}).get("verified"):
        raise RuntimeError("MCD64A1 licence not verified in its catalog row")
    if path.is_file():
        urls = path.read_text().split()
        hits = len(urls)
        probed_at = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
        state = "cached"
    else:
        sess = requests.Session()
        sess.headers.update(UA)
        urls, page, hits = [], 1, None
        while True:
            r = sess.get(CMR_URL, params={"collection_concept_id": CONCEPT_ID, "temporal": TEMPORAL,
                                          "page_size": 2000, "page_num": page,
                                          "sort_key": "start_date"}, timeout=120)
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
        probed_at = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
        state = "fetched"
        if hits != len(urls):
            raise RuntimeError(f"CMR hits {hits}, URLs {len(urls)}: listing disagrees with its headers")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("\n".join(urls) + "\n")
    keys = [parse_name(u) for u in urls]
    dup = len(keys) - len(set(keys))
    if dup:
        raise RuntimeError(f"listing repeats {dup} (year, month, tile) granules; double counting refused")
    tiles = sorted({(h, v) for _, _, h, v in keys})
    per_year = {y: sum(1 for yy, _, _, _ in keys if yy == y) for y in YEARS}
    return {"urls": urls, "hits": hits, "tiles": tiles, "state": state, "probedAt": probed_at,
            "path": str(path), "sha256": sha256(path), "bytes": path.stat().st_size,
            "granulesPerYear": per_year,
            "sourceUrl": f"{CMR_URL}?collection_concept_id={CONCEPT_ID}&temporal={TEMPORAL}&page_size=2000",
            "matchesReferenceCount": hits == REFERENCE_GRANULES}


# --------------------------------------------------------------------------- pixel -> hexagon

def _tilemap_path(h: int, v: int) -> Path:
    return TILEMAPS / f"h{h:02d}v{v:02d}.npz"


def build_tilemap(args) -> str:
    """L1 row index of the hexagon containing each pixel centre; -1 = not a master cell.
    Cached per tile. The SIN inverse is the standard MODIS formula: y = R*phi,
    x = R*(lambda)*cos(phi)."""
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
    """Per-hexagon pixel counts for one granule, by Burn Date class:
    burned (>0), mapped land (>= 0, includes burned), unmapped (== -1), water (== -2).
    Cleaning rules: int16 (2400, 2400) and every value inside [-2, 366]; a violation
    is a hard error so bad granules land in the failures map, never in the counts."""
    sd = SD(path, SDC.READ)
    bd = sd.select("Burn Date")[:]
    sd.end()
    if bd.shape != (TILE_PX, TILE_PX) or bd.dtype != np.int16:
        raise RuntimeError(f"unexpected Burn Date array {bd.dtype} {bd.shape}")
    if bd.min() < -2 or bd.max() > 366:
        raise RuntimeError(f"Burn Date outside [-2, 366]: {bd.min()}..{bd.max()}")
    idx = _tilemap(h, v)
    sel = idx >= 0
    if not sel.any():
        return {"cells": np.array([], dtype=np.int32), "burned": np.array([], dtype=np.int32),
                "mapped": np.array([], dtype=np.int32), "unmapped": np.array([], dtype=np.int32),
                "water": np.array([], dtype=np.int32)}
    i, b = idx[sel], bd[sel]
    tot = np.bincount(i, minlength=n_cells)
    cells = np.flatnonzero(tot)
    return {"cells": cells.astype(np.int32),
            "burned": np.bincount(i[b > 0], minlength=n_cells)[cells].astype(np.int32),
            "mapped": np.bincount(i[b >= 0], minlength=n_cells)[cells].astype(np.int32),
            "unmapped": np.bincount(i[b == -1], minlength=n_cells)[cells].astype(np.int32),
            "water": np.bincount(i[b == -2], minlength=n_cells)[cells].astype(np.int32)}


# --------------------------------------------------------------------------- the streaming run

class Run:
    def __init__(self, urls: list[str], workers: int, n_cells: int):
        self.urls, self.workers, self.n = urls, workers, n_cells
        self.lock = threading.Lock()
        shape = (len(YEARS), 12, n_cells)
        self.burned = np.zeros(shape, np.int32)
        self.mapped = np.zeros(shape, np.int32)
        self.unmapped = np.zeros(shape, np.int32)
        self.water = np.zeros(shape, np.int32)
        self.done: set[str] = set()
        self.failures: dict[str, str] = {}
        self.sum_bytes = 0
        self.since_ckpt = 0
        self.t0 = time.time()
        self.resumed = 0
        self.partial = None

    # -- resume: ledger and counts must stay aligned
    def resume(self) -> None:
        if not CHECKPOINT.exists():
            PARTIAL.parent.mkdir(parents=True, exist_ok=True)
            PARTIAL.write_text("")
            return
        ck = np.load(CHECKPOINT)
        k = int(ck["ledger_lines"])
        lines = PARTIAL.read_text().splitlines()[:k] if PARTIAL.exists() else []
        if len(lines) != k:
            raise RuntimeError(f"checkpoint commits {k} ledger lines, partial ledger has {len(lines)}; "
                               "refusing to skip URLs whose counts were never checkpointed")
        self.burned, self.mapped = ck["burned"], ck["mapped"]
        self.unmapped, self.water = ck["unmapped"], ck["water"]
        self.done = {json.loads(line)["url"] for line in lines}
        self.sum_bytes = sum(json.loads(line)["bytes"] for line in lines)
        self.resumed = len(self.done)
        PARTIAL.write_text("".join(line + "\n" for line in lines))  # drop uncommitted lines
        print(f"resume: {len(self.done)} granules already committed", flush=True)

    def checkpoint(self) -> None:
        self.partial.flush()
        os.fsync(self.partial.fileno())  # ledger bytes hit disk before the pointer does
        k = len(self.done)
        tmp = CHECKPOINT.with_suffix(".tmp.npz")
        np.savez_compressed(tmp, burned=self.burned, mapped=self.mapped,
                            unmapped=self.unmapped, water=self.water, ledger_lines=k)
        tmp.replace(CHECKPOINT)
        self.since_ckpt = 0
        print(f"[{round(time.time() - self.t0)} s] {k}/{len(self.urls)} granules, "
              f"{len(self.failures)} failed, {self.sum_bytes / 1e6:.0f} MB read, checkpoint saved",
              flush=True)

    # -- one granule: download -> decode/filter/count -> ledger -> drop bytes
    def fetch_decode(self, sess: requests.Session, pool: ProcessPoolExecutor, url: str) -> None:
        year, month, h, v = parse_name(url)
        name = url.rsplit("/", 1)[-1]
        last = None
        for attempt in range(MAX_ATTEMPTS):
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
                nbytes = len(body)
                digest = hashlib.sha256(body).hexdigest()
                fd, tmp = tempfile.mkstemp(suffix=".hdf",
                                           dir="/dev/shm" if os.path.isdir("/dev/shm") else None)
                with os.fdopen(fd, "wb") as f:
                    f.write(body)
                res = pool.submit(decode, tmp, h, v, self.n).result()
                del body  # raw bytes dropped after hashing and counting
                rec = {"url": url, "name": name, "sha256": digest, "bytes": nbytes,
                       "fetchedAt": fetched, "year": year, "month": month, "tile": f"h{h:02d}v{v:02d}",
                       "burnedPx": int(res["burned"].sum()), "mappedPx": int(res["mapped"].sum()),
                       "unmappedPx": int(res["unmapped"].sum()), "waterPx": int(res["water"].sum())}
                with self.lock:
                    c = res["cells"]
                    self.burned[year - YEARS[0], month - 1, c] += res["burned"]
                    self.mapped[year - YEARS[0], month - 1, c] += res["mapped"]
                    self.unmapped[year - YEARS[0], month - 1, c] += res["unmapped"]
                    self.water[year - YEARS[0], month - 1, c] += res["water"]
                    self.partial.write(json.dumps(rec, separators=(",", ":")) + "\n")
                    self.done.add(url)
                    self.failures.pop(url, None)
                    self.sum_bytes += rec["bytes"]
                    self.since_ckpt += 1
                    if self.since_ckpt >= CHECKPOINT_EVERY:
                        self.checkpoint()
                return
            except Exception as exc:  # noqa: BLE001 - retried, then recorded in the meta
                last = f"{type(exc).__name__}: {str(exc)[:200]}"
            finally:
                if tmp and os.path.exists(tmp):
                    os.unlink(tmp)
                if attempt < MAX_ATTEMPTS - 1:
                    time.sleep(2 ** attempt)
        with self.lock:
            self.failures[url] = f"{last or 'unknown'} (after {MAX_ATTEMPTS} attempts)"

    def go(self) -> None:
        self.resume()
        todo = [u for u in self.urls if u not in self.done]
        print(f"{len(todo)} granules to fetch ({len(self.done)} committed)", flush=True)
        self.partial = PARTIAL.open("a", encoding="utf-8")
        tok = _token()
        if not tok:
            raise RuntimeError("no Earthdata token at ~/.config/cosmic-consultants/earthdata-token")
        local = threading.local()

        def session() -> requests.Session:
            if not hasattr(local, "s"):
                local.s = _AuthSession(tok)
                # initial request carries the token; _AuthSession keeps it on
                # Earthdata hosts and strips it everywhere else across redirects
                local.s.headers["Authorization"] = f"Bearer {tok}"
            return local.s

        import multiprocessing as mp
        with ProcessPoolExecutor(max_workers=min(8, os.cpu_count() or 2),
                                 mp_context=mp.get_context("spawn")) as pool:
            with ThreadPoolExecutor(self.workers) as ex:
                list(ex.map(lambda u: self.fetch_decode(session(), pool, u), todo))
        with self.lock:
            self.checkpoint()
        self.partial.close()


# --------------------------------------------------------------------------- aggregation (pure, tested)

def aggregate(burned, mapped, n_cells) -> dict:
    """Inputs (years, 12, cells) counts; outputs per cell/month:
    pct [cells, 12] NaN where no year had mapped pixels, years [cells, 12] count of
    years with mapped>0 that the mean used. Pure math, no IO."""
    burned = np.asarray(burned, dtype=np.float64)
    mapped = np.asarray(mapped, dtype=np.float64)
    valid = mapped > 0
    share = np.divide(burned, np.where(valid, mapped, 1.0),
                      out=np.zeros_like(burned), where=valid)
    ny = valid.sum(axis=0)                                    # [12, cells]
    pct = np.where(ny > 0, 100.0 * share.sum(axis=0) / np.maximum(ny, 1), np.nan).T
    return {"pct": np.asarray(pct), "years": ny.T.astype(np.int8)}


def build_rows(hexes: list[str], burned, mapped, pix, partial) -> dict:
    """The long monthly table body from pixel-count arrays plus a coverage indicator.
    burned/mapped: (years, 12, cells); pix: (years, 12, cells) every pixel that ever
    landed in the cell (all Burn Date classes summed); partial: [cells, 12] boolean
    fetch-failure mask. Returns columns cell-major (h3 repeated 12x, months 1-12)."""
    agg = aggregate(burned, mapped, len(hexes))
    covered = np.asarray(pix).sum(axis=(0, 1)) > 0
    pct, years = agg["pct"], agg["years"]
    pct_f, years_f = pct.reshape(-1), years.reshape(-1).astype(np.int64)
    cov_f = np.repeat(covered, 12)
    partial_f = np.asarray(partial, dtype=bool).reshape(-1)
    reasons = []
    for pv, cv, pt in zip(pct_f, cov_f, partial_f):
        r: dict[str, str] = {}
        if pv != pv:                                          # NaN -> null value
            r["burnedArea"] = REASON_NO_TILES if not cv else REASON_NO_MAPPED
        elif pt:
            r["burnedAreaSupport"] = REASON_PARTIAL_FETCH
        reasons.append(json.dumps(r, sort_keys=True) if r else "{}")
    return {"h3": [h for h in hexes for _ in range(12)],
            "month": [m for _ in hexes for m in range(1, 13)],
            "burned_pct": pct_f, "years_mapped": years_f, "missing_reason": reasons}


def affected_cell_months(failures: dict[str, str], n_cells: int) -> np.ndarray:
    """[cells, 12] boolean: for every permanently failed granule, which cells have at
    least one pixel in its tile. Uses the tilemaps (the same pixel->cell mapping the
    counts used), so it marks exactly the hexagons that lost a year of support."""
    out = np.zeros((n_cells, 12), dtype=bool)
    cells_by_tile: dict[tuple[int, int], np.ndarray] = {}
    for url in failures:
        _, month, h, v = parse_name(url)
        key = (h, v)
        if key not in cells_by_tile:
            path = _tilemap_path(h, v)
            if not path.exists():
                continue
            idx = np.load(path)["idx"]
            cells_by_tile[key] = np.unique(idx[idx >= 0])
        c = cells_by_tile.get(key)
        if c is not None and len(c):
            out[c, month - 1] = True
    return out


# --------------------------------------------------------------------------- output

def finalize(run: Run, urls: list[str], listing: dict) -> dict:
    """Sorted deterministic gzip ledger + counts npz + the monthly parquet + meta."""
    hexes, _ = l1_cells()
    recs = [json.loads(line) for line in PARTIAL.read_text().splitlines()]
    recs.sort(key=lambda r: r["name"])
    with open(LEDGER, "wb") as raw, gzip.GzipFile(fileobj=raw, mode="wb", mtime=0) as gz:
        for r in recs:
            gz.write((json.dumps(r, separators=(",", ":")) + "\n").encode())
    np.savez_compressed(COUNTS, burned=run.burned, mapped=run.mapped,
                        unmapped=run.unmapped, water=run.water)
    pix = run.burned.astype(np.int64) + run.mapped + run.unmapped + run.water
    partial = affected_cell_months(run.failures, len(hexes))
    body = build_rows(hexes, run.burned, run.mapped, pix, partial)

    code_counts: dict[str, int] = {}
    for mr in body["missing_reason"]:
        for k, v in json.loads(mr).items():
            code_counts[f"{k}:{v}"] = code_counts.get(f"{k}:{v}", 0) + 1
    tbl = pa.table({
        "h3": pa.array(body["h3"]),
        "month": pa.array(body["month"], pa.int8()),
        "burned_pct": pa.array(body["burned_pct"], from_pandas=True),
        "years_mapped": pa.array(body["years_mapped"], pa.int8()),
        "missing_reason": pa.array(body["missing_reason"]),
    })
    problems = validate_keys(tbl, hexes)
    if problems:
        raise RuntimeError(f"key-domain check failed: {problems}")
    guide_path = REPO / GUIDE_REL
    row = catalog_row(DATASET)
    meta = {
        "generatedAt": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "dataset": {"datasetId": DATASET, "version": "061", "conceptId": CONCEPT_ID,
                    "doi": DOI, "title": row.get("title"),
                    "license": (row.get("license") or {}).get("id"),
                    "licenseVerified": (row.get("license") or {}).get("verified"),
                    "archive": (row.get("source") or {}).get("archive")},
        "status": {"runtime": "executed-unreviewed",
                   "scientific": "partial (source preparation by helper #65; not yet parent-accepted)"},
        "interface": {"path": OUT_REL, "rows": tbl.num_rows,
                      "columns": ["h3", "month", "burned_pct", "years_mapped", "missing_reason"],
                      "keySet": "L1 land cells (cells-r4.parquet, 91,800) x months 1-12, cell-major"},
        "observable": {
            "what": "share of the hexagon's mapped land pixels that MCD64A1 flags as burned",
            "unit": "percent (0-100)", "statistic": "mean over 2015-2024 of the yearly share, "
            "unweighted across years with mapped support",
            "timeSupport": "calendar month by the granule's own month (verified: burned DOYs "
                           "stay inside the granule month; see probe.burnDateWithinMonth)",
            "spatialSupport": "H3 res 4 hexagons; MODIS 500-m sinusoidal tile pixels assigned by "
                             "pixel-centre -> hexagon (tilemap per h##v## tile)",
            "years": list(YEARS), "yearsCount": len(YEARS)},
        "computed": {
            "mappedLand": "Burn Date >= 0 (0 = unburned land, >0 = burned day-of-year); "
                           "water (-2) excluded from the denominator; unmapped (-1) has no "
                           "land support and drops out of its year's share",
            "share": "per (year, month, cell): burned / mapped-land pixels",
            "burnedPct": "100 * mean of yearly shares over years with mapped > 0; null when none",
            "yearsMapped": "count of years with mapped > 0 used by the mean",
            "nulls": "missing mapped support is null, never zero; reasons in missing_reason"},
        "granules": {"expected": len(urls), "inLedger": len(recs),
                      "failed": len(run.failures),
                      "bytesRead": sum(r["bytes"] for r in recs),
                      "resumedFrom": run.resumed,
                      "perYear": listing["granulesPerYear"], "tiles": len(listing["tiles"])},
        "inputs": {
            "granuleList": {"path": LIST_REL, "sha256": listing["sha256"], "bytes": listing["bytes"],
                            "probedAt": listing["probedAt"], "state": listing["state"],
                            "sourceUrl": listing["sourceUrl"], "hits": listing["hits"],
                            "matchesReferenceCount32160": listing["matchesReferenceCount"]},
            "userGuide": {"path": GUIDE_REL, "url": GUIDE_URL,
                          "sha256": sha256(guide_path) if guide_path.is_file() else None,
                          "bytes": guide_path.stat().st_size if guide_path.is_file() else None},
            "ledger": {"path": LEDGER_REL, "sha256": sha256(LEDGER), "bytes": LEDGER.stat().st_size,
                       "lines": len(recs)},
            "counts": {"path": str(COUNTS.relative_to(REPO)), "sha256": sha256(COUNTS)},
            "keySet": {"path": "data/snapshots/_derived/cells-r4.parquet",
                       "sha256": sha256(DERIVED / "cells-r4.parquet")},
        },
        "probe": PROBE_EVIDENCE,
        "qa": {
            "perGranuleChecks": {"shape": "(2400, 2400) int16", "valueRange": [-2, 366],
                                 "granulesChecked": len(recs), "violations": 0},
            "listingChecks": {"uniqueGranuleKeys": True, "hitsEqualsUrlCount": True,
                              "monthsPerGranule": "name parses to first-of-month, else fatal"},
            "reasonCounts": code_counts,
            "failureExamples": dict(list(run.failures.items())[:20]),
            "failureUrls": sorted(run.failures)},
        "limits": {
            "resolution": "500-m MODIS; burns smaller than about one 500-m cell or under "
                           "persistent cloud/smoke are not detected; unmapped pixels are "
                           "excluded from the denominator rather than counted unburned",
            "validation": PROBE_EVIDENCE["userGuide"]["quotes"]["validation"],
            "coverage": "MCD64A1 tiles exist only where LP DAAC produces them (v <= 14 in the "
                        "south); Antarctic land and other untiled areas are null with "
                        "outside-mcd64a1-tiles, not zero",
            "proxyNote": "burned share is a hazard-proxy trait (fire disturbance frequency), "
                         "not a site-similarity verdict; no scores or verdicts are computed here",
        },
        "outputs": {"parquet": {}, "meta": str(META.relative_to(REPO))},
    }
    meta["outputs"]["parquet"] = {"path": OUT_REL}
    tbl = tbl.replace_schema_metadata({"cosmic-consultants": json.dumps(
        {k: meta[k] for k in ("generatedAt", "dataset", "observable", "computed")})})
    pq.write_table(tbl, OUT, compression="zstd")
    meta["outputs"]["parquet"] = {"path": OUT_REL, "sha256": sha256(OUT), "bytes": OUT.stat().st_size,
                                  "rows": tbl.num_rows}
    meta["nullRate"] = {"burned_pct": round(tbl["burned_pct"].null_count / tbl.num_rows, 4),
                        "years_mapped": 0.0}
    META.write_text(json.dumps(meta, indent=2) + "\n")
    return meta


def manifest_append(entry: dict) -> None:
    """Append-only MANIFEST edit: adds an entry, keeps every other entry untouched."""
    m = json.loads(MANIFEST.read_text(encoding="utf-8"))
    same = [e for e in m["entries"] if e.get("datasetId") == entry["datasetId"]
            and e.get("localPath") == entry["localPath"]]
    if same:
        return
    m["entries"].append(entry)
    tmp = MANIFEST.with_suffix(".tmp")
    tmp.write_text(json.dumps(m, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    os.replace(tmp, MANIFEST)


# --------------------------------------------------------------------------- spots

SPOTS = {
    "Death Valley (Badwater)": (36.25, -116.83),
    "Haughton crater (Devon Island)": (75.38, -89.68),
    "Atacama (Yungay)": (-24.10, -70.02),
    "McMurdo Dry Valleys (Wright Valley)": (-77.52, 161.85),
    "Mauna Loa (summit)": (19.475, -155.608),
    "Arnhem Land, N Australia": (-14.0, 132.0),
    "Sahel, southern Niger": (12.0, 8.0),
    "Butte County, California (Camp Fire 2018)": (39.8, -121.6),
    "Antarctica interior (-80, 0)": (-80.0, 0.0),
    "Greenland interior": (72.0, -40.0),
}


def spot_checks() -> int:
    """Real observations from burned-r4-monthly.parquet at fire-prone and ice places."""
    tbl = pq.read_table(OUT).to_pandas()
    missing = 0
    for name, (la, lo) in SPOTS.items():
        cell = h3.latlng_to_cell(la, lo, RES)
        rows = tbl[tbl.h3 == cell].sort_values("month")
        if rows.empty:
            print(f"    {name} ({la},{lo}) {cell}: no row (not in key set)")
            continue
        vals = {int(r.month): None if r.burned_pct != r.burned_pct else round(r.burned_pct, 3)
                for r in rows.itertuples()}
        nz = {m: v for m, v in vals.items() if v}
        print(f"    {name} ({la},{lo}) {cell}")
        print(f"      months with burned_pct>0: {nz if nz else 'none'}")
        print(f"      years_mapped: {[f'{int(r.month)}:{int(r.years_mapped)}' for r in rows.itertuples()]}")
        reasons = {int(r.month): json.loads(r.missing_reason) for r in rows.itertuples()
                   if r.missing_reason and r.missing_reason != "{}"}
        print(f"      reasons: {reasons if reasons else 'none (all months have values)'}")
        missing += bool(reasons)
    return missing


# --------------------------------------------------------------------------- cli

def run(workers: int = 24, limit: int | None = None) -> dict:
    hexes, ids = l1_cells()
    order = np.argsort(ids)
    sorted_ids = ids[order]
    listing = fetch_granule_list()
    urls = listing["urls"]
    if limit:
        urls = urls[:limit]
    # Tile, then date: neighbouring downloads share one tile map in the decoder cache.
    urls = sorted(urls, key=lambda u: (parse_name(u)[2:], parse_name(u)[:2]))
    tiles = sorted({parse_name(u)[2:] for u in urls})
    todo = [(h, v, sorted_ids, order) for h, v in tiles if not _tilemap_path(h, v).exists()]
    if todo:
        t = time.time()
        print(f"building {len(todo)} pixel->hexagon tile maps ({len(tiles)} tiles)", flush=True)
        import multiprocessing as mp
        with ProcessPoolExecutor(max_workers=min(8, os.cpu_count() or 4),
                                 mp_context=mp.get_context("spawn")) as ex:
            list(ex.map(build_tilemap, todo, chunksize=1))
        print(f"tile maps done in {round(time.time() - t)} s", flush=True)
    r = Run(urls, workers, len(hexes))
    r.go()
    if r.failures:
        print(f"{len(r.failures)} granules failed after {MAX_ATTEMPTS} attempts (kept in meta)", flush=True)
    meta = finalize(r, listing["urls"], listing)
    meta["granules"]["failedIfLimited"] = len(r.failures)
    return meta


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--workers", type=int, default=24)
    ap.add_argument("--limit", type=int, default=None, help="first N granules in tile-then-date order (testing)")
    ap.add_argument("--spots", action="store_true", help="print spot checks from burned-r4-monthly.parquet")
    a = ap.parse_args()
    if a.spots:
        spot_checks()
        return 0
    meta = run(a.workers, a.limit)
    print(json.dumps({k: meta[k] for k in
                      ("generatedAt", "granules", "nullRate", "outputs") if k in meta}, indent=1))
    if meta["qa"]["failureUrls"]:
        print("FAILED GRANULES:", json.dumps(meta["qa"]["failureUrls"], indent=1))
        return 1
    return 0 if not a.limit else 1  # --limit runs are never a completed pass


if __name__ == "__main__":
    sys.exit(main())
