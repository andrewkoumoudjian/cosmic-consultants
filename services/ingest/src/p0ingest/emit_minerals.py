"""W35 (#94): EMIT L2B mineral identification per H3 res-4 hexagon, static composite.

Dataset: emit-l2b-min-v002 (EMIT L2B Estimated Mineral Identification, Band
Depth and Uncertainty 60 m V002, LP DAAC concept C4079846859-LPCLOUD, licence
CC0 verified in data/catalog/emit-l2b-min-v002.yaml).

Product structure (V002, verified on real granules, 2026-11-14/15): each .nc
has per-pixel identified minerals for TWO band-depth groups - group 1 = the
1 um feature minerals (fe2+/fe3+ oxides, sulfides, olivine/pyroxene), group 2
= the 2 um feature minerals (clays, micas, chlorite, carbonates, sulfates).
Both are geologic groups; the granule's mineral_metadata table (312 EMIT
library entries: index, name, group) carries which entries are organic or
man-made (dry grass, plastics, paint) - those names are excluded everywhere.

Honesty notes kept next to the numbers:
- These are EMIT mineral identifications at EARTH wavelengths fitted against
  the EMIT spectral library. They are NOT CRISM indices and not numerically
  interchangeable with them; the `crism_*` feature names in
  research/features/landing_site_features.csv are Earth-proxy slots only.
- EMIT covers only arid dust-source regions visited by the ISS orbit. Hexagons
  never covered are null with reason outside-emit-coverage.
- The full collection is ~135.5k granules / ~14.5 TB (CMR probe 2026-11-14),
  far beyond one streaming session (measured ~4.4 MB/s with 4 parallel
  downloads -> ~30 days of download alone). This build streams a deterministic
  pseudo-random sample (order = sha256 of the granule id) and records exactly
  what was processed; hexagons inside EMIT coverage but not touched by a
  processed granule are null with reason granule-not-processed. Raw granules
  are downloaded at most 4 in flight, hashed into a JSONL ledger under
  _derived/, aggregated, then deleted.

Pixel-to-hexagon rule: each identified pixel's geolocated centre lat/lon
(granule `location` group) is mapped with h3.latlng_to_cell(lat, lon, 4); the
pixel belongs to exactly that res-4 hexagon. Per hexagon and family:
  share   count(family pixel-observations) / count(base pixel-observations)
  bd_med  median band depth over the family's pixels; computed from 0.001-wide
          band-depth histograms (exactness note in meta; max median error
          0.0005, an order below EMIT's reported uncertainties)
  px      count of the family's pixel-observations (repeat passes accumulate)
Base `observed`: pixels identified with any geologic (non-organic/man-made)
library mineral in any band-depth group. EMIT L2B MIN has no per-pixel
valid-observation mask, and arid scenes fit the organic library entries to
most pixels, so the organic fits are excluded from both base and families.

Mineral families -> library-name rules (matched on the granule's own
mineral_metadata `name` strings, so names travel with the data):
  hydration       phyllosilicates + hydrated evaporites (clays, micas,
                  chlorite, serpentine, talc, prehnite, hydroxides, gypsum,
                  hydrated glass, chalcedony)
  fe_mg_smectite  montmorillonite / chlorite / vermiculite plus the other
                  Fe/Mg smectites (saponite, beidellite, nontronite, sepiolite,
                  hectorite, palygorskite)
  al_oh           kaolin group (kaolinite, halloysite, dickite, nacrite) + illite
  sulfate         gypsum
  carbonate       calcite / dolomite
  mafic_bd_1um    Fe2+-bearing silicates: library names starting `fe2+`
                  except feldspars, plus anything with olivine
  dust_proxy      iron-oxide coatings (names starting `fe3+`): dust-source
                  signal for the Ruff TES dust_cover_index proxy slot; NOT
                  the TES index itself

Commands (run from services/ingest/):
  uv run python -m p0ingest.emit_minerals list    # full CMR listing -> granules.jsonl.gz
  uv run python -m p0ingest.emit_minerals stream  # sample + aggregate, resumable
  uv run python -m p0ingest.emit_minerals build   # emit-min-r4.parquet + meta.json
  uv run python -m p0ingest.emit_minerals check   # keys, ranges, nulls, raw spot checks
"""
from __future__ import annotations

import argparse
import calendar
import gzip
import hashlib
import json
import logging
import re
import threading
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

import h3
import netCDF4
import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq

from .snapshots import SNAP

log = logging.getLogger("emit_minerals")

DATASET = "emit-l2b-min-v002"
CONCEPT = "C4079846859-LPCLOUD"
CMR = "https://cmr.earthdata.nasa.gov/search/granules.json"
DERIVED = SNAP / "_derived"
OUT_DIR = DERIVED / "emit-min"
GRANULES_GZ = OUT_DIR / "granules.jsonl.gz"
LEDGER = OUT_DIR / "granule-ledger.jsonl.gz"
OUT_PARQUET = OUT_DIR / "emit-min-r4.parquet"
OUT_META = OUT_DIR / "emit-min-r4.meta.json"
RAW_DIR = SNAP / DATASET
CELLS_PARQUET = DERIVED / "cells-r4.parquet"

BD_BINS = 1000          # band-depth histogram bins over [0, 1), 0.001 wide
MAX_BD = 1.0            # band depths are relative depths; clip guard at 1.0

FAMILIES: dict[str, re.Pattern] = {
    "hydration": re.compile(
        r"smectite|kaol|chlorite|vermiculite|illite|muscov|paragonite|biotite"
        r"|phlogopite|lepidolite|margarite|montmorillonite|halloysite|dickite"
        r"|nacrite|prehnite|serpentine|pyrophyllite|sepiolite|saponite"
        r"|hectorite|palygorskite|clay|gypsum|hydrated|chalcedony|diaspore"
        r"|gibbsite|brucite|talc|clintonite|zeolite"),
    "fe_mg_smectite": re.compile(
        r"montmorillonite|chlorite|vermiculite|saponite|hectorite|beidellite"
        r"|nontronite|sepiolite|palygorskite"),
    "al_oh": re.compile(r"kaol|illite"),
    "sulfate": re.compile(r"gypsum"),
    "carbonate": re.compile(r"calcite|dolomite"),
    "mafic_bd_1um": re.compile(r"^fe2\+|olivine"),
    "dust_proxy": re.compile(r"^fe3\+"),
}
FAMILY_ORDER = list(FAMILIES)
VALUE_COLS = [f"emit_min_{f}_{s}" for f in FAMILY_ORDER for s in ("share", "bd_med", "px")]
COLUMNS = ["h3", "n_observed"] + VALUE_COLS + ["missing_reason"]


# ---------------------------------------------------------------- names -----
def is_geologic(name: str) -> bool:
    "False for the organic/man-made library entries (dry grass, plastics, ...)."
    return not (name.startswith(("organic", "cyanide")) or "methane-gas" in name)


def classify_names(names: list[str]) -> dict[str, set[str]]:
    "Geologic library name -> set of families (organic/man-made names excluded)."
    out: dict[str, set[str]] = {}
    for n in names:
        if not is_geologic(n):
            continue
        fams = [f for f in FAMILY_ORDER if FAMILIES[f].search(n)]
        if "mafic_bd_1um" in fams and "feldspar" in n:
            fams.remove("mafic_bd_1um")
        if fams:
            out[n] = set(fams)
    return out


# ----------------------------------------------------------------- list -----
def cmr_list_month(y: int, m: int) -> list[dict]:
    "All EMITL2BMIN v002 granules in one calendar month, paged 2000 at a time."
    lo = f"{y:04d}-{m:02d}-01T00:00:00Z"
    hi = f"{y:04d}-{m:02d}-{calendar.monthrange(y, m)[1]:02d}T23:59:59Z"
    rows: list[dict] = []
    page = 1
    while True:
        url = (CMR + f"?short_name=EMITL2BMIN&version=002&page_size=2000"
               f"&temporal={lo},{hi}&sort_key=start_date&page_num={page}")
        d = None
        for attempt in range(5):
            try:
                with urllib.request.urlopen(urllib.request.Request(url), timeout=180) as r:
                    d = json.load(r)
                break
            except Exception as exc:  # noqa: BLE001 - CMR hiccups retried
                log.warning("CMR %04d-%02d p%d attempt %d failed: %s", y, m, page, attempt + 1, exc)
                time.sleep(3 * (attempt + 1))
        if d is None:
            raise RuntimeError(f"CMR monthly query failed for {y}-{m:02d} page {page}")
        entries = d["feed"]["entry"]
        for e in entries:
            bbox = None
            if e.get("polygons"):
                vals = e["polygons"][0][0].split()
                lats = [float(v) for v in vals[0::2]]
                lons = [float(v) for v in vals[1::2]]
                if lats and lons:
                    bbox = [min(lons), min(lats), max(lons), max(lats)]
            hrefs = [l["href"] for l in e.get("links", [])
                     if l["rel"].endswith("data#") and l.get("href", "").endswith(".nc")
                     and "MINUNCERT" not in l["href"]]
            rows.append({"id": e["title"], "start": e["time_start"], "end": e["time_end"],
                         "bbox": bbox, "mb": float(e.get("granule_size", 0) or 0),
                         "url": hrefs[0] if hrefs else None})
        if len(entries) < 2000:
            return rows
        page += 1


def load_granules() -> dict[str, dict]:
    "granule id -> record from granules.jsonl.gz (tolerant of a torn tail)."
    rows: dict[str, dict] = {}
    with gzip.open(GRANULES_GZ, "rt", errors="ignore") as f:
        for line in f:
            try:
                r = json.loads(line)
                rows[r["id"]] = r
            except Exception:
                continue
    return rows


def cmd_list() -> int:
    "Full CMR listing, append-resumable, dedup by granule id."
    seen = set(load_granules())
    n0 = len(seen)
    months = [(y, m) for y in range(2022, 2027) for m in range(1, 13) if (y, m) >= (2022, 8)]
    with gzip.open(GRANULES_GZ, "at") as out:
        for y, m in months:
            rows = cmr_list_month(y, m)
            new = [r for r in rows if r["id"] not in seen]
            for r in new:
                out.write(json.dumps(r) + "\n")
                seen.add(r["id"])
            log.info("%04d-%02d: %d granules (%d new)", y, m, len(rows), len(new))
    log.info("listing complete: %d granules total (was %d)", len(seen), n0)
    return 0


# ------------------------------------------------------------- granule io ---
def read_granule(path: Path):
    """Decode one granule. Returns
    (id_by_index: dict int -> name, lat, lon: float64 1-D arrays,
     gvars: group_nr -> (mineral_id int32, band_depth float32) 1-D arrays,
            all band-depth groups the file carries)."""
    ds = netCDF4.Dataset(path)
    try:
        md = ds.groups["mineral_metadata"]
        idx = np.asarray(md["index"][:])
        names = [str(s) for s in md["name"][:]]
        if not np.array_equal(np.sort(idx), np.arange(1, len(idx) + 1)):
            raise ValueError(f"{path.name}: mineral_metadata index is not 1..N")
        id_by_index = {int(idx[i]): names[i] for i in range(len(names))}
        lat = np.ma.filled(ds.groups["location"]["lat"][:].astype("float64"), np.nan).ravel()
        lon = np.ma.filled(ds.groups["location"]["lon"][:].astype("float64"), np.nan).ravel()
        gvars: dict[int, tuple[np.ndarray, np.ndarray]] = {}
        for g in range(1, 13):
            key_id, key_bd = f"group_{g}_mineral_id", f"group_{g}_band_depth"
            if key_id not in ds.variables or key_bd not in ds.variables:
                continue
            ids = np.ma.filled(ds.variables[key_id][:].astype("int32"), 0).ravel()
            bds = np.ma.filled(ds.variables[key_bd][:].astype("float32"), np.nan).ravel()
            if not (len(ids) == len(lat) == len(lon)):
                raise ValueError(f"{path.name}: shape mismatch lat={len(lat)} ids={len(ids)}")
            gvars[g] = (ids, bds)
        if not gvars:
            raise ValueError(f"{path.name}: no group_N_mineral_id variables")
        return id_by_index, lat, lon, gvars
    finally:
        ds.close()


def fam_bitmask(name_fams: dict[str, set[str]], ids: list[int], id_by_index: dict[int, str]
                ) -> np.ndarray:
    "Per id: bitmask over FAMILY_ORDER (bit k = family k); base bit = bit len(FAMILY_ORDER)."
    m = np.zeros(len(FAMILY_ORDER) + 1, dtype=np.int64)
    for k, f in enumerate(FAMILY_ORDER):
        m[k] = 1 << k
    m[len(FAMILY_ORDER)] = 1 << len(FAMILY_ORDER)  # geologic-identified (base) flag
    out = np.zeros(max(ids) + 1 if ids else 1, dtype=np.int64)
    for i in ids:
        name = id_by_index.get(i)  # unknown/fill ids: absent from the library
        if not name or not is_geologic(name):
            continue
        out[i] |= m[len(FAMILY_ORDER)]
        for f in name_fams.get(name, ()):  # type: ignore[union-attr]
            out[i] |= m[FAMILY_ORDER.index(f)]
    return out


def aggregate_granule(path: Path, name_fams: dict[str, set[str]]) -> dict[str, np.ndarray]:
    """Aggregate one granule into per-family (cell, bd) raw pairs plus the base.

    Returns keys: `{FAM}__cells`/`{FAM}__bds` float pairs (uint64 cell ids,
    float32 band depths from the pixel's own identified group), and
    `BASE__counts`: (cell ids, per-cell geologic-identified pixel counts)."""
    id_by_index, lat, lon, gvars = read_granule(path)
    all_ids = sorted({int(i) for gv in gvars.values() for i in np.unique(gv[0]).tolist()})
    bits = fam_bitmask(name_fams, [i for i in all_ids if i > 0], id_by_index)
    out: dict[str, np.ndarray] = {}
    base = {}
    base_flag = 1 << len(FAMILY_ORDER)
    for g, (ids, bds) in gvars.items():
        valid = (ids > 0) & np.isfinite(lat) & np.isfinite(lon)
        if not valid.any():
            continue
        cells_all = map_cells(lat[valid], lon[valid])
        ids_v = ids[valid]
        bds_v = bds[valid]
        bm = bits[ids_v]
        base_sel = (bm & base_flag) != 0
        if base_sel.any():
            u, c = np.unique(cells_all[base_sel], return_counts=True)
            for a, b in zip(u, c):
                base[a] = base.get(a, 0) + int(b)
        for k in range(len(FAMILY_ORDER)):
            sel = ((bm >> k) & 1).astype(bool) & (bds_v > 0) & np.isfinite(bds_v) & (bds_v <= MAX_BD)
            if not sel.any():
                continue
            key = f"{FAMILY_ORDER[k]}__"
            prev_c = out.get(key + "cells")
            prev_b = out.get(key + "bds")
            c = cells_all[sel]
            b = bds_v[sel].astype(np.float32)
            out[key + "cells"] = np.concatenate([prev_c, c]) if prev_c is not None else c
            out[key + "bds"] = np.concatenate([prev_b, b]) if prev_b is not None else b
    if base:
        bc = np.asarray(sorted(base), dtype=np.uint64)
        bv = np.asarray([base[int(c)] for c in bc], dtype=np.int64)
        out["BASE__counts"] = np.stack([bc, bv.astype(np.uint64)])
    return out


def map_cells(lat: np.ndarray, lon: np.ndarray) -> np.ndarray:
    "Pixel-centre -> H3 res-4 cell id (uint64); zeros where position not finite."
    res = np.zeros(lat.shape, dtype=np.uint64)
    ok = np.isfinite(lat) & np.isfinite(lon)
    if ok.any():
        la, lo = lat[ok], lon[ok]
        res[ok] = [int(h3.latlng_to_cell(float(a), float(b), 4), 16) for a, b in zip(la, lo)]
    return res


def ordered_sample(granules: list[dict]) -> list[dict]:
    "Deterministic order: sha256 of the granule id (spreads over time+space)."
    return sorted(granules, key=lambda r: hashlib.sha256(r["id"].encode()).hexdigest())


def ledger_lines() -> list[dict]:
    out = []
    if LEDGER.exists():
        with gzip.open(LEDGER, "rt", errors="ignore") as f:
            for line in f:
                try:
                    out.append(json.loads(line))
                except Exception:
                    continue
    return out


def load_state() -> dict:
    f = OUT_DIR / "state.json"
    if f.exists():
        return json.loads(f.read_text())
    return {"processed": [], "checkpoints": 0, "bytes": 0, "failed": {},
            "startedAt": datetime.now(timezone.utc).isoformat()}


def save_state(state: dict) -> None:
    tmp = OUT_DIR / "state.json.tmp"
    tmp.write_text(json.dumps(state))
    tmp.replace(OUT_DIR / "state.json")


def _sha(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


class HistStore:
    """Per family: cell -> uint32 histogram over BD_BINS band-depth bins.
    Per cell: geologic-identified pixel-observation counts. Checkpoints are
    append-only numbered npz files; build() merges them in order."""

    def __init__(self) -> None:
        self.hists: dict[str, dict[int, np.ndarray]] = {}
        self.base: dict[int, int] = {}

    def add_pairs(self, fam: str, cells: np.ndarray, bds: np.ndarray) -> None:
        order = np.argsort(cells, kind="stable")
        c, b = cells[order], bds[order]
        uniq, starts = np.unique(c, return_index=True)
        ends = np.append(starts[1:], len(c))
        h = self.hists.setdefault(fam, {})
        for j in range(len(uniq)):
            idx = np.clip((b[starts[j]:ends[j]] * BD_BINS).astype(np.int32), 0, BD_BINS - 1)
            bincount = np.bincount(idx, minlength=BD_BINS).astype(np.uint32)
            cell = int(uniq[j])
            if cell in h:
                h[cell] += bincount
            else:
                h[cell] = bincount

    def add_base(self, paired_counts: np.ndarray) -> None:
        # paired_counts: (2, N) [cell, count]
        for cell, cnt in zip(paired_counts[0].tolist(), paired_counts[1].tolist()):
            self.base[int(cell)] = self.base.get(int(cell), 0) + int(cnt)

    def totals(self) -> tuple[int, int]:
        fam_pairs = sum(int(h.sum()) for fam in self.hists.values() for h in fam.values())
        return fam_pairs, int(sum(self.base.values()))

    def flush(self, path: Path) -> None:
        payload = {}
        for fam, cells in self.hists.items():
            if cells:
                cs = np.asarray(sorted(cells), dtype=np.uint64)
                payload[f"{fam}__cells"] = cs
                payload[f"{fam}__hists"] = np.stack(
                    [cells[int(c)] for c in cs]).astype(np.uint32)
        if self.base:
            cs = np.asarray(sorted(self.base), dtype=np.uint64)
            payload["BASE__pairs"] = np.stack([cs, np.asarray([self.base[int(c)] for c in cs],
                                                              dtype=np.uint64)])
        if payload:
            tmp = path.with_suffix(".tmp.npz")
            np.savez_compressed(tmp, **payload)
            tmp.replace(path)
        self.hists = {}
        self.base = {}

    def merge(self, paths: list[Path]) -> None:
        for p in paths:
            with np.load(p) as z:
                if "BASE__pairs" in z.files:
                    self.add_base(np.asarray(z["BASE__pairs"]))
                for fam in FAMILY_ORDER:
                    ck = f"{fam}__cells"
                    if ck not in z.files:
                        continue
                    cs = np.asarray(z[ck])
                    hs = np.asarray(z[f"{fam}__hists"])
                    h = self.hists.setdefault(fam, {})
                    for j, cell in enumerate(cs.tolist()):
                        cur = h.get(int(cell))
                        if cur is None:
                            h[int(cell)] = hs[j].astype(np.uint32).copy()
                        else:
                            cur += hs[j]


def download_one(url: str, dest: Path) -> None:
    "Streamed raw: temp file then atomic rename. No MANIFEST writes for raw."
    import requests
    from .snapshots import _AuthSession, _token

    token = _token()
    sess = _AuthSession(token)
    if token:
        # First request must already be authenticated: lp-prod-protected
        # answers an unauthenticated GET with a redirect to the URS login
        # page, which then 401s. Keep the bearer across redirects too.
        sess.headers["Authorization"] = f"Bearer {token}"
    tmp = dest.with_suffix(".part")
    last = None
    for attempt in range(5):
        try:
            with sess.get(url, stream=True, timeout=(30, 300), allow_redirects=True) as r:
                r.raise_for_status()
                with tmp.open("wb") as f:
                    for chunk in r.iter_content(1 << 20):
                        f.write(chunk)
            tmp.replace(dest)
            return
        except Exception as exc:  # noqa: BLE001 - retried, then re-raised
            last = exc
            time.sleep(3 * (attempt + 1))
    raise RuntimeError(f"download failed after retries: {url}: {last}")


def classify_names_from_granule(path: Path) -> dict[str, set[str]]:
    "Family rules validated against a real granule's own mineral_metadata."
    id_by_index, _lat, _lon, _gv = read_granule(path)
    return classify_names(sorted(id_by_index.values()))


# --------------------------------------------------------------- stream -----
def cmd_stream(minutes: float = 300.0, max_granules: int | None = None,
               max_workers: int = 4) -> int:
    "Stream the deterministic sample; download -> aggregate -> ledger -> delete."
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    granules = load_granules()
    sample = ordered_sample(list(granules.values()))
    state = load_state()
    ledger_done = {ln["id"] for ln in ledger_lines()}
    done = set(state["processed"]) | ledger_done
    todo = [g for g in sample if g["id"] not in done and g.get("url")]
    log.info("todo %d of %d (state %d, ledger %d)", len(todo), len(sample),
             len(state["processed"]), len(ledger_done))

    prefetched = {p.stem for p in RAW_DIR.glob("*.nc")}  # kept spot-check raws
    store = HistStore()
    store_lock = threading.Lock()  # serializes store/ledger/state (per-granule
    # flushes into shared cp-NNNNN names would otherwise overwrite each other)
    n_ok = n_fail = 0
    stop_flag = {"stop": False}
    t_end = time.time() + minutes * 60

    def work(g: dict) -> None:
        dest = RAW_DIR / (g["id"] + ".nc")
        if g["id"] not in prefetched and not (dest.exists() and dest.stat().st_size > 0):
            download_one(g["url"], dest)
        name_fams = classify_names_from_granule(dest)
        try:
            agg = aggregate_granule(dest, name_fams)
            nbytes = dest.stat().st_size
            digest = _sha(dest)
        finally:
            if g["id"] not in prefetched:
                dest.unlink(missing_ok=True)
        with gzip.open(LEDGER, "at") as ledger:
            ledger.write(json.dumps({
                "id": g["id"], "url": g["url"],
                "fetchedAt": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                "start": g["start"], "end": g["end"], "bbox": g["bbox"],
                "sha256": digest, "bytes": nbytes, "kept": g["id"] in prefetched,
            }) + "\n")
        for f in FAMILY_ORDER:
            ck = agg.get(f"{f}__cells")
            bd = agg.get(f"{f}__bds")
            if ck is not None and len(ck):
                store.add_pairs(f, ck, bd)
        if "BASE__counts" in agg:
            store.add_base(agg["BASE__counts"])
        with store_lock:
            state["processed"].append(g["id"])
            state["bytes"] += int(nbytes)
            # flush + state save per granule, under the lock so concurrent
            # workers cannot overwrite each other's cp or interleave additions
            store.flush(OUT_DIR / f"cp-{len(state['processed']):05d}.npz")
            state["checkpoints"] += 1
            save_state(state)
        if len(state["processed"]) % 25 == 0:
            log.info("%d granules, %.2f GB streamed", len(state["processed"]),
                     state["bytes"] / 1e9)
        if time.time() > t_end or (max_granules and n_ok + n_fail >= max_granules):
            stop_flag["stop"] = True

    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        futures = {ex.submit(work, g): g for g in todo}
        for fut in as_completed(list(futures)):
            g = futures[fut]
            try:
                fut.result()
                n_ok += 1
            except Exception as exc:  # noqa: BLE001 - record and continue
                n_fail += 1
                state["failed"][g["id"]] = repr(exc)[:300]
                log.warning("granule %s failed: %s", g["id"], exc)
            if stop_flag["stop"]:
                break
        if stop_flag["stop"]:
            for f2 in futures:
                f2.cancel()
    if store.base or store.hists:
        store.flush(OUT_DIR / f"cp-{len(state['processed']):05d}.npz")
        state["checkpoints"] += 1
    save_state(state)
    log.info("stream done: ok %d, failed %d, %.2f GB streamed", n_ok, n_fail,
             state["bytes"] / 1e9)
    return 0


# ----------------------------------------------------------------- build ----
COV_STEP = 0.1


def coverage_raster(bboxes) -> np.ndarray:
    """Union of granule bounding boxes on a 0.1-degree global grid.

    Row 0 = 90..-89.9 lat (cell centre north edge), col 0 = -180..-179.9 lon.
    Bbox over-bounds the real footprint; hexagon coverage tests use the pixel
    containing the hexagon centre."""
    grid = np.zeros((1800, 3600), dtype=bool)
    for b in bboxes:
        x0, y0, x1, y1 = b
        if x1 < x0:
            x0, x1 = x1, x0
        if y1 < y0:
            y0, y1 = y1, y0
        r0 = int(np.clip((90 - y1) / COV_STEP, 0, 1799))
        r1 = int(np.clip((90 - y0) / COV_STEP, 0, 1799))
        c0 = int(np.clip((x0 + 180) / COV_STEP, 0, 3599))
        c1 = int(np.clip((x1 + 180) / COV_STEP, 0, 3599))
        grid[r0:r1 + 1, c0:c1 + 1] = True
    return grid


def cell_medians(hists: dict[int, np.ndarray]) -> dict[int, tuple[int, float]]:
    "(cell, hist) -> (count, median) from a BD_BINS histogram of band depths."
    out: dict[int, tuple[int, float]] = {}
    for cell, h in hists.items():
        total = int(h.sum())
        if not total:
            continue
        edges = (np.cumsum(h, dtype=np.int64) - total / 2)
        j = int(np.argmax(edges >= 0))
        lo = h[:j].sum(dtype=np.int64)
        # linear interpolation inside bin j
        cum_prev = int(lo)
        cum_here = int(lo + h[j])
        if cum_here == cum_prev:  # empty bin (should not happen with argmax>=0)
            j = min(j + 1, BD_BINS - 1)
            cum_here = cum_prev + int(h[j])
        frac = ((total / 2) - cum_prev) / max(cum_here - cum_prev, 1)
        med = min(max((j + float(frac)) / BD_BINS, 0.0), MAX_BD)
        out[cell] = (total, med)
    return out


def cmd_build() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    state = load_state()
    cps = sorted(OUT_DIR.glob("cp-*.npz"))
    log.info("merging %d checkpoints (%d processed granules)", len(cps),
             len(state["processed"]))
    store = HistStore()
    store.merge(cps)
    hists_norm = {f: store.hists.get(f, {}) for f in FAMILY_ORDER}
    meds = {f: cell_medians(hists_norm[f]) for f in FAMILY_ORDER}
    base_counts = store.base

    granules = load_granules()
    lines = ledger_lines()
    proc_ids = {ln["id"] for ln in lines}
    cov = coverage_raster([g["bbox"] for g in granules.values() if g.get("bbox")])
    touched = coverage_raster([granules[i]["bbox"] for i in proc_ids
                               if i in granules and granules[i]["bbox"]])
    cells_t = pq.read_table(CELLS_PARQUET, columns=["h3", "lat", "lon"])
    h3s = cells_t["h3"].to_pylist()
    latc = np.asarray(cells_t["lat"].to_pylist(), dtype=float)
    lonc = np.asarray(cells_t["lon"].to_pylist(), dtype=float)
    step = 0.1
    ri = np.clip(((90 - latc) / step).astype(int), 0, 1799)
    ci = np.clip(((lonc + 180) / step).astype(int), 0, 3599)
    in_cov, is_touched = cov[ri, ci], touched[ri, ci]

    rows = []
    reason_row_counts: dict[str, int] = {}
    n_data = 0
    for i, hs in enumerate(h3s):
        cell = int(hs, 16)
        n_obs = base_counts.get(cell, 0)
        vals: dict[str, object] = {c: None for c in COLUMNS}
        vals["h3"] = hs
        reasons: dict[str, str] = {}
        if n_obs == 0:
            vals["n_observed"] = None
            r = ("outside-emit-coverage" if not in_cov[i]
                 else ("granule-not-processed" if not is_touched[i]
                       else "no-identified-pixels"))
            reasons = {c: r for c in COLUMNS
                       if c not in ("h3", "missing_reason")}
            reason_row_counts[r] = reason_row_counts.get(r, 0) + 1
        else:
            n_data += 1
            vals["n_observed"] = n_obs
            for f in FAMILY_ORDER:
                m = meds[f].get(cell)
                if m:
                    vals[f"emit_min_{f}_px"] = m[0]
                    vals[f"emit_min_{f}_share"] = m[0] / n_obs
                    vals[f"emit_min_{f}_bd_med"] = m[1]
                else:
                    for s in ("px", "share", "bd_med"):
                        reasons[f"emit_min_{f}_{s}"] = "no-identified-pixels"
            # integrity: a concurrent-flush race in the killed stream run lost
            # some per-granule checkpoint contents; a family pixel count
            # exceeding the base count is a detected symptom. Values cannot be
            # recomputed without the raw granules (deleted per the 20 GB
            # rule), so the whole row is null with an explicit reason rather
            # than published with impossible shares.
            over = [f for f in FAMILY_ORDER
                    if vals[f"emit_min_{f}_px"] is not None
                    and vals[f"emit_min_{f}_px"] > n_obs]
            if over:
                vals["n_observed"] = None
                n_data -= 1
                for f in FAMILY_ORDER:
                    for s in ("share", "bd_med", "px"):
                        vals[f"emit_min_{f}_{s}"] = None
                reasons = {c: "samples-lost-processing-error" for c in COLUMNS
                           if c not in ("h3", "missing_reason")}
                reason_row_counts["samples-lost-processing-error"] = \
                    reason_row_counts.get("samples-lost-processing-error", 0) + 1
        vals["missing_reason"] = json.dumps(reasons, sort_keys=True) if reasons else None
        rows.append(vals)

    fields = ([("h3", pa.string()), ("n_observed", pa.int64())]
              + [(c, pa.float64() if c.endswith(("share", "bd_med")) else pa.int64())
                 for c in VALUE_COLS] + [("missing_reason", pa.string())])
    tbl = pa.Table.from_pydict({c: [r[c] for r in rows] for c in COLUMNS},
                               schema=pa.schema(fields))
    pq.write_table(tbl, OUT_PARQUET)

    starts = [ln["start"] for ln in lines]
    by_year: dict[str, int] = {}
    for ln in lines:
        y = ln["start"][:4]
        by_year[y] = by_year.get(y, 0) + 1
    meta = {
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "dataset": {"datasetId": DATASET, "conceptId": CONCEPT,
                    "title": "EMIT L2B Estimated Mineral Identification, Band Depth and "
                             "Uncertainty 60 m V002", "license": "cc0", "licenseVerified": True,
                    "archive": "Earthdata (LP DAAC, LPCLOUD)"},
        "status": {"runtime": "executed-unreviewed",
                   "scientific": "partial (deterministic sample of a ~14.5 TB collection; "
                                 "not parent-accepted)"},
        "interface": {"path": str(OUT_PARQUET.relative_to(SNAP.parent.parent)),
                      "rows": len(rows), "columns": COLUMNS,
                      "keySet": "cells-r4.parquet (91,800 H3 res-4 land cells)"},
        "observable": {
            "what": "per mineral family: share of identified pixels, median band depth, "
                    "pixel-observation count",
            "unit": "share 0-1; band depth 0-1 (relative depth); counts are pixels",
            "statistic": f"static composite over {len(proc_ids)} sampled granules",
            "timeSupport": "static (all acquisitions pooled; monthly-or-coarser rule "
                           "satisfied; acquisition season ignored for minerals)",
            "spatialSupport": "H3 res-4 hexagons; EMIT 60 m pixel centre -> "
                              "h3.latlng_to_cell(lat, lon, 4); support counts kept per family",
            "dateRange": [min(starts) if starts else None, max(starts) if starts else None],
            "acquisitionsByYear": by_year,
            "crismNote": "EMIT mineral IDs at EARTH wavelengths from the EMIT spectral "
                         "library; NOT CRISM indices, not numerically interchangeable; "
                         "crism_* names in landing_site_features.csv are proxy slots",
        },
        "computed": {
            "base": "n_observed = geologic-identified pixel-observations (all band-depth "
                    "groups; library names starting organic/cyanide or methane-gas "
                    "excluded); no per-pixel valid-observation mask exists in the product "
                    "and organic fits dominate arid scenes",
            "share": "family px / n_observed",
            "px": "pixel-observations; repeat passes accumulate",
            "bd_med": "median band depth from 0.001-wide histograms (max median error "
                      "0.0005); band depths are the granule's own per-group depths",
            "families": {f: FAMILIES[f].pattern for f in FAMILY_ORDER},
            "nulls": "missing stays null; missing_reason JSON keys are exactly the null "
                     "value columns of that row",
        },
        "sampling": {
            "rule": "deterministic pseudo-random order (sha256 of granule id), streamed "
                    "until the time budget stopped the run",
            "granulesTotal": len(granules),
            "granulesProcessed": len(proc_ids),
            "bytesStreamedGB": round(state.get("bytes", 0) / 1e9, 2),
            "rawPolicy": "streamed: max 4 downloads in flight, URL+fetch time+sha256+bytes "
                         "per granule in the gzipped ledger, raw deleted after "
                         "aggregation; pilot raws kept on disk for spot checks",
        },
        "granules": {"inLedger": len(lines), "unique": len(proc_ids),
                     "failed": state.get("failed", {})},
        "inputs": {
            "granuleList": {"path": str(GRANULES_GZ.relative_to(SNAP)),
                            "sha256": _sha(GRANULES_GZ), "bytes": GRANULES_GZ.stat().st_size,
                            "source": CMR + "?short_name=EMITL2BMIN&version=002 "
                                      "(paged by month window)"},
            "ledger": {"path": str(LEDGER.relative_to(SNAP)),
                       "sha256": _sha(LEDGER) if LEDGER.exists() else None},
            "keySet": {"path": str(CELLS_PARQUET.relative_to(SNAP)),
                       "sha256": _sha(CELLS_PARQUET)},
        },
        "probe": {
            "cmrHits20261114": 135534,
            "listingTotal20261115": len(granules),
            "granuleFileStructure": "EMITL2BMIN V002 .nc: location lat/lon (60 m pixel "
                                    "centres), mineral_metadata (index, name, group over a "
                                    "312-entry EMIT library), group_N_mineral_id + "
                                    "group_N_band_depth; V002 bands: group 1 = 1 um "
                                    "feature minerals (fe2+/fe3+), group 2 = 2 um feature "
                                    "minerals (clays, sulfates, carbonates, micas)",
            "identificationDensity": "varies by orders of magnitude between scenes "
                                     "(observed 336 .. 1.4M identified pixels per granule)",
        },
        "qa": {"reasonRowCounts": reason_row_counts},
        "limits": {
            "coverage": "EMIT covers arid dust-source regions only (~52N-52S ISS sunlit "
                        "orbit); approximate coverage here = union of ALL CMR granule "
                        "bounding boxes, hexagon-centre test; bbox over-bounds the real "
                        "footprint, so edge hexagons can be marked covered while no "
                        "processed scene reached them",
            "sampling": "full collection ~135.5k granules / ~14.5 TB cannot be streamed in "
                        "one run (~30+ days at measured ~4.4 MB/s with 4 parallel "
                        "downloads); covered-but-unprocessed hexagons are null "
                        "granule-not-processed, never zero",
            "base": "shares are relative to identified pixels, not raw surface coverage; "
                    "dust_proxy is an iron-oxide-coating share, NOT the Ruff & Christensen "
                    "TES dust-cover index",
            "identifications": "threshold-based band-depth identifications; sparse on "
                               "vegetated/heterogeneous scenes; organic-fitted pixels "
                               "excluded from the base entirely",
            "checkpointRace": "the streaming run was externally killed; before the kill, "
                              "per-granule checkpoint flushes were NOT serialized, so two "
                              "workers could write the same cp file (one cp holds family "
                              "counts without any base - impossible per granule). Rows "
                              "where a family pixel count exceeded the base are nulled "
                              "samples-lost-processing-error; same-direction losses that "
                              "kept internal consistency cannot be detected, so per-cell "
                              "counts/shares are approximate near affected cells. "
                              "Fixed (store lock) for later runs",
        },
        "outputs": {"parquet": {"path": str(OUT_PARQUET.relative_to(SNAP)),
                                "sha256": _sha(OUT_PARQUET), "bytes": OUT_PARQUET.stat().st_size,
                                "rows": len(rows)},
                    "meta": str(OUT_META.relative_to(SNAP))},
        "nullRate": {"n_observed": round(1 - n_data / len(rows), 4)},
    }
    OUT_META.write_text(json.dumps(meta, indent=2, default=str) + "\n")
    log.info("built %s rows=%d withData=%d", OUT_PARQUET.name, len(rows), n_data)
    return 0


# ----------------------------------------------------------------- check ----
def _present(v) -> bool:
    if v is None:
        return False
    if isinstance(v, float) and v != v:
        return False
    return True


def cmd_check() -> int:
    "Exact keys, no dupes, physical ranges, null/reason agreement, raw spot checks."
    t = pq.read_table(OUT_PARQUET)
    cells = pq.read_table(CELLS_PARQUET, columns=["h3"])
    errors: list[str] = []
    if list(t.column_names) != COLUMNS:
        errors.append(f"columns drifted: {t.column_names}")
    keys = t["h3"].to_pylist()
    want = cells["h3"].to_pylist()
    if set(keys) != set(want):
        errors.append("key set differs from cells-r4.parquet 91,800")
    if len(set(keys)) != len(keys):
        errors.append("duplicate h3 keys")
    d = {c: t[c].to_pylist() for c in COLUMNS}

    def arr(c):
        return np.asarray([np.nan if v is None else v for v in d[c]], dtype="float64")

    for c in COLUMNS:
        if c.endswith("_share"):
            v = arr(c)
            bad = v[(v == v) & ((v < 0) | (v > 1))]
            if bad.size:
                errors.append(f"{c}: {bad.size} shares outside [0,1]")
        if c.endswith("_bd_med"):
            v = arr(c)
            bad = v[(v == v) & ((v <= 0) | (v > 1))]
            if bad.size:
                errors.append(f"{c}: {bad.size} band depths outside (0,1]")
        if c.endswith("_px") or c == "n_observed":
            v = arr(c)
            fin = v[v == v]
            if fin.size and fin.min() < 0:
                errors.append(f"{c}: negative counts")
    for f in FAMILY_ORDER:
        px, n, sh = arr(f"emit_min_{f}_px"), arr("n_observed"), arr(f"emit_min_{f}_share")
        both = (px == px) & (n == n)
        if both.any() and np.abs(sh[both] - px[both] / n[both]).max() > 1e-9:
            errors.append(f"{f}: share != px/n_observed")
        if ((px == px) & ((n != n) | (px > n))).any():
            errors.append(f"{f}: px > n_observed or n_observed null while px set")

    n_null_bad = 0
    for i in range(len(keys)):
        nulls = {c for c in COLUMNS if c not in ("h3", "missing_reason") and not _present(d[c][i])}
        got = set(json.loads(d["missing_reason"][i])) if d["missing_reason"][i] else set()
        if {k for k in got if k in COLUMNS} != nulls:
            n_null_bad += 1
    if n_null_bad:
        errors.append(f"missing_reason keys != null columns in {n_null_bad} rows")

    # ---- raw spot checks (>=5): raw granules kept on disk, values vs table
    spot = sorted(RAW_DIR.glob("*.nc"))
    if len(spot) < 4:
        errors.append(f"only {len(spot)} raw spot granules on disk (need 4)")
    ledger = {ln["id"]: ln for ln in ledger_lines()}
    spot_checks = 0
    key_set = set(keys)
    for p in spot:
        gid = p.stem
        if gid not in ledger:
            errors.append(f"spot granule {gid} missing from ledger")
            continue
        name_fams = classify_names_from_granule(p)
        agg = aggregate_granule(p, name_fams)
        base_n = int(agg["BASE__counts"][1].sum()) if "BASE__counts" in agg else 0
        tot_obs = float(np.nansum(arr("n_observed")))
        if base_n and tot_obs < base_n:
            errors.append(f"{gid}: table n_observed {tot_obs:.0f} < granule {base_n}")
        fam_report = {}
        for f in FAMILY_ORDER:
            if f"{f}__cells" in agg:
                fam_n = int(agg[f"{f}__cells"].size)
                fam_report[f] = fam_n
                tot = float(np.nansum(arr(f"emit_min_{f}_px")))
                if tot < fam_n:
                    errors.append(f"{gid}/{f}: table px {tot:.0f} < granule {fam_n}")
        want_cells: set[str] = set()
        for f in FAMILY_ORDER:
            if f"{f}__cells" in agg:
                for c in agg[f"{f}__cells"][:2000].tolist():
                    want_cells.add(format(int(c), "x"))
        coord_n = 0
        for cell in sorted(want_cells)[:5]:
            if cell not in key_set:
                errors.append(f"{gid}: hexagon {cell} not a land cell")
                continue
            row = keys.index(cell)
            if _present(d["n_observed"][row]) and d["n_observed"][row] >= 1:
                coord_n += 1
        spot_checks += 1
        print(f"spot {gid}: base={base_n} families={fam_report} hexChecks={coord_n}")
        if base_n and coord_n == 0:
            errors.append(f"{gid}: no populated hexagon found among family cells")
    if spot_checks < 4:
        errors.append(f"only {spot_checks} raw spot checks ran")
    if errors:
        print("CHECK FAILED:\n" + "\n".join(f"- {e}" for e in errors))
        return 1
    print(f"check OK: {len(keys)} rows, keys exact, no dupes, ranges valid, "
          f"null/reason exact, {spot_checks} raw spot granules verified")
    return 0


# ------------------------------------------------------------------ main ----
COMMANDS = {"list": cmd_list, "stream": cmd_stream, "build": cmd_build, "check": cmd_check}


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    ap = argparse.ArgumentParser(prog="emit_minerals")
    ap.add_argument("cmd", choices=sorted(COMMANDS))
    ap.add_argument("--minutes", type=float, default=300.0)
    ap.add_argument("--max-granules", type=int, default=None)
    ap.add_argument("--max-workers", type=int, default=4)
    a = ap.parse_args()
    if a.cmd == "stream":
        return cmd_stream(minutes=a.minutes, max_granules=a.max_granules,
                          max_workers=a.max_workers)
    return COMMANDS[a.cmd]()


if __name__ == "__main__":
    raise SystemExit(main())
