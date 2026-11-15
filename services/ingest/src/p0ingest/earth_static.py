"""W38 (#97): earth_static — Earth context source tables that are neither L1/L1m
nor planetary-native, built per H3 res-4 land cell (91,800 master cells,
data/snapshots/_derived/cells-r4.parquet).

Sources attempted (work order #97), one table each:
1. nsidc-ggd318-permafrost (Circum-Arctic Map of Permafrost and Ground-Ice
   Conditions v2, static vector): NOT delivered, on access grounds. The NSIDC
   legacy data host refuses TCP and the remaining host requires an interactive
   Earthdata OAuth login we do not have (`probe_ggd318()` writes the evidence
   to _derived/earth-static-probes.json). The licence itself is resolvable
   (user guide: reuse permitted with a citation, Brown et al. 2002,
   DOI 10.7265/skbg-kf16) — not the blocker. No values used, none invented.
2. modis-mod44b (MODIS/Terra Vegetation Continuous Fields yearly 250 m,
   v061): DELIVERED as _derived/vcf-r4.parquet — per hexagon, median and
   mean percent tree cover, percent non-tree vegetation and percent
   non-vegetated (bare) of the latest complete yearly series (annual period
   starting DOY 65; completeness rule below). CC0 (catalog row verified).
3. earth-impact-database (PASSC, UNB): NOT delivered — passc.net serves a
   114-byte JavaScript redirect to a parked page (/lander). Re-probed with
   HTTP evidence by `probe_eid()`. No values used.

MOD44B pixel-to-hexagon rule (same text lives in the table meta):
  native 250 m pixel centre -> lat/lon by the exact inverse of the MODIS
  spherical sinusoid (sphere R = 6371007.181 m from the tiles' ProjParams,
  central meridian 0: phi = y/R, lambda = x/(R cos(phi)); the tile width
  1111950.5197666666 m equals R*2*pi/36, pinning the sphere; cross-checked
  against GDAL proj4 in the tests) -> the 0.05 deg CMG lattice pixel
  (3600x7200, same lattice as grid.py) containing the centre -> H3 res-4
  cell of that lattice pixel via the pinned land-share map
  grid.cmg_cell_map (pixel centre inside the H3 res-4 cell through
  h3.latlng_to_cell on the lattice pixel's centre).
Per 0.05 deg lattice pixel: arithmetical mean of the valid native pixels
inside it, per layer. Per hexagon: MEDIAN over the hexagon's lattice-pixel
means (rounded to whole percent; median = mean of the two middle values,
same convention as the other ingest tables) and the exact MEAN over the
hexagon's native valid pixels (sum of sums / sum of counts). Support
counts are kept at both scales.

QA (the product's declared terms only, v061 user guide): the three percent
layers are valid 0-100; 200 is water and 253 is fill/outside projection;
water and fill never enter statistics and are counted separately. The
Quality/Cloud bit layers are advisory per the guide ("Use of quality bits
should be restricted to pixels with valid vegetation cover values") and are
NOT applied as a mask — the guide declares no masking rule.
Known product limit (user guide, C61): areas with sparse training samples
(e.g. high latitudes) are "not retrieved and populated with fill value of
0", so a 0 there may mean not-retrieved rather than measured 0%.
"""
from __future__ import annotations

import json
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

import h3
import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq
from pyhdf.SD import SD, SDC

from .grid import CMG_M, CMG_N, CMG_STEP, DERIVED, RES, cmg_cell_map, group_index
from .regolith import _hist_median, master_keys  # read-only reuse of the master-key + histogram-median helpers
from .snapshots import SNAP, fetch, load_manifest, sha256

DATASET = "modis-mod44b"
CMR_COLLECTION = "C2565805839-LPCLOUD"
GUIDE_URL = "https://lpdaac.usgs.gov/documents/1494/MOD44B_User_Guide_V61.pdf"
CMR_PAGE_SIZE = 1000
CMR_MAX_PAGES = 10
MIN_SERIES_TILES = 290  # completeness floor if no pair of series matches

CODE_WATER, CODE_FILL = 200, 253
LAYERS = ("percent_tree_cover", "percent_nontree_vegetation", "percent_nonvegetated")
SDS = {"percent_tree_cover": "Percent_Tree_Cover",
       "percent_nontree_vegetation": "Percent_NonTree_Vegetation",
       "percent_nonvegetated": "Percent_NonVegetated"}
VALUE_COLS = ([f"vcf_{k}_pct_median" for k in LAYERS]
              + [f"vcf_{k}_pct_mean" for k in LAYERS])
NO_DATA_CODE = "no-vcf-lattice-px"

SPHERE_R = 6371007.181  # m: the tiles' ProjParams semi-major; R*2*pi/36 = 1111950.5197666666 m = tile width
TILE_PX_M = 1111950.5197666666 / 4800  # 231.65635826395825 m per native pixel

EID_URL = "http://www.passc.net/EarthImpactDatabase/New%20website_05-2018/Index.html"
GGD318_GUIDE = "https://nsidc.org/sites/default/files/ggd318-v002-userguide.pdf"
PIXEL_RULE = (
    "native 250 m pixel centre -> exact inverse MODIS spherical sinusoid "
    "(R=6371007.181 m per the tiles' ProjParams, lambda0=0: phi=y/R, "
    "lambda=x/(R*cos(phi))) -> the 0.05 deg CMG "
    "lattice pixel (3600x7200, grid.py) containing it -> H3 res-4 cell of that lattice "
    "pixel via the pinned MOD11C3 A2023001 land-share map (grid.cmg_cell_map, "
    "h3.latlng_to_cell on the lattice pixel centre)")


# ---------------------------------------------------------------- CMR + fetch

def _cmr_get(url: str, retries: int = 5):
    import requests
    last = None
    for a in range(retries):
        try:
            r = requests.get(url, timeout=(30, 120), headers={
                "Accept": "application/json",
                "User-Agent": "cosmic-consultants-p0ingest/0.1 (NASA Space Apps 2026)"})
            r.raise_for_status()
            return r
        except Exception as exc:  # noqa: BLE001 - retried with backoff, then re-raised
            last = exc
            time.sleep(2 ** a)
    raise RuntimeError(f"CMR query failed after {retries} tries: {url}: {last}")


def _series_of(gid: str) -> str:
    return gid.split(".")[1][:5]  # 'A2025'


def granule_rows() -> list[dict]:
    """All v061 granules of the collection, newest first, from CMR."""
    rows, page = [], 0
    while page < CMR_MAX_PAGES:
        page += 1
        r = _cmr_get(f"https://cmr.earthdata.nasa.gov/search/granules.json"
                     f"?collection_concept_id={CMR_COLLECTION}"
                     f"&sort_key=-start_date&page_size={CMR_PAGE_SIZE}&page_num={page}")
        ents = r.json()["feed"]["entry"]
        if not ents:
            break
        for e in ents:
            hrefs = [l["href"] for l in e.get("links", [])
                     if l["href"].startswith("https") and l["href"].endswith(".hdf")]
            if hrefs:
                rows.append({"granule": e["producer_granule_id"], "url": hrefs[0]})
        if len(ents) < CMR_PAGE_SIZE:
            break
    return rows


def choose_series(rows: list[dict]) -> tuple[str, dict]:
    """Latest yearly series whose tile set equals the previous series's
    (tiles can land late; equality across series = complete)."""
    by_series: dict[str, set] = {}
    for r in rows:
        by_series.setdefault(_series_of(r["granule"]), set()).add(r["granule"].split(".")[2])
    series = sorted(by_series, reverse=True)
    info: dict = {"tilesPerSeries": {k: len(v) for k, v in sorted(by_series.items())[-3:]}}
    for y in series:
        prev = next((p for p in series if p < y), None)
        if prev and by_series[y] == by_series[prev]:
            info.update(rule=f"tile set of {y} matches {prev} ({len(by_series[y])} tiles)",
                        complete=True, selected=y)
            return y, info
        if len(by_series[y]) >= MIN_SERIES_TILES:
            info.update(rule=(f"no older series matched; took newest {y} with "
                              f"{len(by_series[y])} tiles (completeness unverified, "
                              f"floor {MIN_SERIES_TILES})"),
                        complete=False, selected=y)
            return y, info
    raise RuntimeError("no MOD44B yearly series in the CMR listing")


def fetch_mod44b(workers: int = 4) -> dict:
    """Fetch the user guide + every granule of the chosen series through
    snapshots.fetch (MANIFEST url/time/sha256/bytes/licence), <=4 parallel."""
    rows = granule_rows()
    year, info = choose_series(rows)
    print(f"series {year}: {info['rule']}", flush=True)
    fetch(DATASET, GUIDE_URL)
    sel = [r for r in rows if _series_of(r["granule"]) == year]

    def grab(r: dict) -> int:
        return fetch(DATASET, r["url"]).stat().st_size

    got = 0
    with ThreadPoolExecutor(workers) as ex:
        for _ in ex.map(grab, sel):
            got += 1
            if got % 25 == 0:
                print(f"  {got}/{len(sel)} granules", flush=True)
    print(f"fetched {got}/{len(sel)} granules for {year}", flush=True)
    return {"year": year, "series": info, "granules": got}


# ------------------------------------------------------------------ geometry

def parse_struct(path) -> dict:
    """Parse the HDF-EOS StructMetadata.0 of a MODIS SIN tile."""
    sd = SD(str(path), SDC.READ)
    try:
        sm = sd.attributes().get("StructMetadata.0", "")
    finally:
        sd.end()

    def num(key):
        m = re.search(key + r"\s*=\s*([-\d.]+)", sm)
        if not m:
            raise RuntimeError(f"{path}: no {key} in StructMetadata.0")
        return float(m.group(1))

    def pair(key):
        m = re.search(key + r"\s*=\s*\(([-\d.]+),([-\d.]+)\)", sm)
        if not m:
            raise RuntimeError(f"{path}: no {key} in StructMetadata.0")
        return float(m.group(1)), float(m.group(2))

    x_ul, y_ul = pair("UpperLeftPointMtrs")
    x_lr, y_lr = pair("LowerRightMtrs")
    return {"x_ul": x_ul, "y_ul": y_ul, "x_lr": x_lr, "y_lr": y_lr,
            "rows": int(num("YDim")), "cols": int(num("XDim"))}


def inverse_sin(x: np.ndarray, y: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Exact inverse of the spherical sinusoid (lambda0=0): phi = y/R,
    lambda = x/(R cos(phi)). x, y in metres; returns (lat_deg, lon_deg)."""
    phi = y / SPHERE_R
    lam = x / (SPHERE_R * np.cos(phi))
    return np.degrees(phi), np.degrees(lam)


def forward_sin(lat_deg: np.ndarray, lon_deg: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Forward spherical sinusoid (lambda0=0), metres — the test reference."""
    phi = np.radians(lat_deg)
    return SPHERE_R * np.radians(lon_deg) * np.cos(phi), SPHERE_R * phi


def _tile_coords(meta: dict) -> tuple[np.ndarray, np.ndarray]:
    """Native pixel-centre (lat_deg, lon_deg) grids of one tile."""
    if meta["rows"] != 4800 or meta["cols"] != 4800:
        raise RuntimeError(f"tile is {meta['rows']}x{meta['cols']}, expected 4800x4800")
    px_y = (meta["y_ul"] - meta["y_lr"]) / meta["rows"]
    px_x = (meta["x_lr"] - meta["x_ul"]) / meta["cols"]
    if abs(px_x - TILE_PX_M) > 1e-4 or abs(px_y - TILE_PX_M) > 1e-4:
        raise RuntimeError(f"pixel size {px_x}x{px_y} m, expected {TILE_PX_M} m")
    rows = np.arange(meta["rows"])
    cols = np.arange(meta["cols"])
    y = meta["y_ul"] - (rows + 0.5) * px_y          # (rows,)
    x = meta["x_ul"] + (cols + 0.5) * px_x          # (cols,)
    phi = y / SPHERE_R
    lam = x[None, :] / (SPHERE_R * np.cos(phi))[:, None]
    lat = np.broadcast_to(np.degrees(phi)[:, None], (meta["rows"], meta["cols"]))
    lon = np.degrees(lam)
    return lat, lon


# ------------------------------------------------------------ tile reading

def _bin_layers(layer_vals: dict[str, np.ndarray], lat: np.ndarray, lon: np.ndarray) -> dict:
    """Bin native pixels into 0.05 deg CMG lattice sums/counts per layer.
    Valid = declared 0-100; 200 water / 253 fill are counted, never averaged;
    any other code raises (the guide defines no others). Pixel centres beyond
    the globe ellipse (|inverted lon| > 180 deg — MODIS SIN tiles tile the
    plane, so corner strips carry no Earth) are excluded as 'offglobe'; a
    pixel off the lattice WITHOUT being beyond the ellipse means a geometry
    bug and raises. noqa: the off-globe strips can carry residual model
    output (observed code 11) despite no retrieval existing there; they are
    counted per layer and never binned."""
    irow = ((90.0 - lat) / CMG_STEP).astype(np.int64)
    icol = ((180.0 + lon) / CMG_STEP).astype(np.int64)
    on = ((irow >= 0) & (irow < CMG_N) & (icol >= 0) & (icol < CMG_M))
    off_geom = np.abs(np.radians(lon)) > np.pi + 1e-9
    if (~on & ~off_geom).any():
        raise RuntimeError("pixel centre off the CMG lattice but not beyond the "
                           "globe ellipse — geometry bug")
    flat = (irow * CMG_M + icol)[on]
    out: dict = {"lattice": {}, "native": {}}
    for key, v in layer_vals.items():
        valid = (v <= 100) & on
        water = (v == CODE_WATER) & on
        fill = (v == CODE_FILL) & on
        other = on & ~(v <= 100) & (v != CODE_WATER) & (v != CODE_FILL)
        n_other = int(other.sum())
        if n_other:
            raise RuntimeError(f"{key}: {n_other} native pixels with codes outside "
                               f"{{0..100, {CODE_WATER}, {CODE_FILL}}}")
        sums = np.bincount(flat[valid[on]], weights=v[on][valid[on]].astype(np.float64),
                           minlength=CMG_N * CMG_M)
        cnt = np.bincount(flat[valid[on]], minlength=CMG_N * CMG_M)
        out["lattice"][key] = {"sum": sums.astype(np.int32), "n": cnt.astype(np.uint16)}
        out["native"][key] = {"valid": int(valid.sum()), "water": int(water.sum()),
                              "fill": int(fill.sum()), "other": n_other,
                              "offglobe": int((~on).sum())}
    return out


def read_tile(path) -> dict:
    """One MOD44B v061 granule -> lattice sums/counts + native code counts."""
    meta = parse_struct(path)
    lat, lon = _tile_coords(meta)
    sd = SD(str(path), SDC.READ)
    try:
        vals = {k: sd.select(SDS[k])[:] for k in LAYERS}
    finally:
        sd.end()
    out = _bin_layers(vals, lat, lon)
    out["tile"] = str(path).rsplit("/", 1)[-1]
    return out


class Acc:
    """Per-lattice accumulators over all tiles of the series."""

    def __init__(self):
        self.sum = {k: np.zeros(CMG_N * CMG_M, np.int32) for k in LAYERS}
        self.n = {k: np.zeros(CMG_N * CMG_M, np.uint16) for k in LAYERS}
        self.native = {k: {"valid": 0, "water": 0, "fill": 0, "other": 0,
                           "offglobe": 0} for k in LAYERS}
        self.tiles = 0

    def add(self, tile: dict):
        for k in LAYERS:
            np.add(self.sum[k], tile["lattice"][k]["sum"], out=self.sum[k], casting="unsafe")
            np.add(self.n[k], tile["lattice"][k]["n"], out=self.n[k], casting="unsafe")
            for f in self.native[k]:
                self.native[k][f] += tile["native"][k][f]
        self.tiles += 1

    def water_fill(self) -> dict:
        return {k: self.native[k]["water"] + self.native[k]["fill"] for k in LAYERS}


# --------------------------------------------------------------------- build

def _manifest_block() -> list[dict]:
    return [{"localPath": e["localPath"], "sha256": e["sha256"], "bytes": e["bytes"]}
            for e in load_manifest()["entries"] if e.get("datasetId") == DATASET]


def _all_manifest_hdfs() -> list[tuple[str, str]]:
    return [(e["localPath"].rsplit("/", 1)[-1], e["localPath"])
            for e in load_manifest()["entries"]
            if e.get("datasetId") == DATASET and e["localPath"].endswith(".hdf")]


def series_on_disk() -> str:
    """Latest yearly series present in MANIFEST (fetch_mod44b's choice)."""
    years = {f.split(".")[1][:5] for f, _ in _all_manifest_hdfs()}
    if not years:
        raise RuntimeError("no MOD44B .hdf in MANIFEST; run --fetch first")
    return max(years)


def _mean_from_lattice(acc: Acc, k: str, flat_to_hex: np.ndarray, n: int) -> np.ndarray:
    """Exact native-pixel mean per master cell: sums add exactly across the
    lattice pixels mapped to one cell."""
    nz = np.nonzero(acc.n[k] > 0)[0]
    s = np.bincount(flat_to_hex[nz], weights=acc.sum[k][nz], minlength=n)
    c = np.bincount(flat_to_hex[nz], weights=acc.n[k][nz], minlength=n)
    return np.where(c > 0, s / np.maximum(c, 1), np.nan)


def per_hex(acc: Acc, res: int = RES, cells: np.ndarray | None = None,
            cellmap: np.ndarray | None = None) -> dict:
    """Lattice accumulators -> per master-cell aggregates via grid.py's pinned
    land-share pixel->hex map. Lattice pixels outside any master cell drop."""
    master = master_keys(res) if cells is None else cells
    n = len(master)
    master_int = np.array([int(h, 16) for h in master.tolist()], dtype=np.uint64)
    if cellmap is None:
        cellmap, _ = cmg_cell_map(res)
    order, cell_ids, starts = group_index(cellmap)
    if not (cell_ids == master_int).all():
        raise RuntimeError("grid.cmg_cell_map cells != cells-r4.parquet master keys")
    gid = np.repeat(np.arange(n, dtype=np.int64),
                    np.diff(np.append(starts, len(order))))
    flat_to_hex = np.zeros(CMG_N * CMG_M, np.int64)
    flat_to_hex[order] = gid
    visited = np.zeros(CMG_N * CMG_M, bool)
    visited[order] = True

    out: dict = {"lattice_dropped_px": {}, "native": acc.native}
    # _hist_median treats bin 0 as "fill"; shift pct bins by one so the
    # valid VCF value 0% lands in bin 1 (bin 0 stays empty).
    H = 102
    hist = {k: np.zeros((n, H), np.int32) for k in LAYERS}
    got_px = {k: np.zeros(n, np.int32) for k in LAYERS}
    npx = {k: np.zeros(n, np.int64) for k in LAYERS}
    for k in LAYERS:
        nz = np.nonzero((acc.n[k] > 0) & visited)[0]
        out["lattice_dropped_px"][k] = int(((acc.n[k] > 0) & ~visited).sum())
        mean = acc.sum[k][nz] / acc.n[k][nz].astype(np.int64)
        pct = np.clip(np.rint(mean), 0, 100).astype(np.int64) + 1
        hist[k] += np.bincount(flat_to_hex[nz] * H + pct,
                               minlength=n * H).reshape(n, H).astype(np.int32)
        got_px[k] += np.bincount(flat_to_hex[nz], minlength=n).astype(np.int32)
        npx[k] += np.bincount(flat_to_hex[nz], weights=acc.n[k][nz],
                              minlength=n).astype(np.int64)
    for k in LAYERS:
        out[k] = {"median": _hist_median(hist[k], np.arange(H, dtype=np.float64) - 1.0),
                  "mean_native": _mean_from_lattice(acc, k, flat_to_hex, n),
                  "lattice_px": got_px[k], "native_px": npx[k]}
    return out


def row_reasons(n_rows: int, have: np.ndarray) -> list[str]:
    """missing_reason per row: keys exactly the null value columns of that row."""
    reasons = []
    for i in range(n_rows):
        r = {}
        if not have[i]:
            for c in VALUE_COLS:
                r[c] = NO_DATA_CODE
        reasons.append(json.dumps(r, sort_keys=True))
    return reasons


def build(res: int = RES, limit: int | None = None) -> dict:
    """Aggregate every granule of the latest on-disk series into the master
    cells; write _derived/vcf-r{res}.parquet + lattice npz + meta."""
    t0 = time.time()
    year = series_on_disk()
    hdfs = sorted((f, r) for f, r in _all_manifest_hdfs()
                  if f.split(".")[1][:5] == year)
    if limit:
        hdfs = hdfs[:limit]
    acc = Acc()
    for i, (fname, rel) in enumerate(hdfs, 1):
        acc.add(read_tile(SNAP.parent.parent / rel))
        if i % 25 == 0 or i == len(hdfs):
            print(f"  {i}/{len(hdfs)} tiles, {time.time() - t0:.0f} s", flush=True)
    np.savez_compressed(DERIVED / f"vcf-r{res}-cmg.npz",
                        **{f"sum_{k}": acc.sum[k] for k in LAYERS},
                        **{f"n_{k}": acc.n[k] for k in LAYERS})
    px = per_hex(acc, res)
    master = master_keys(res)
    n = len(master)

    have = px[LAYERS[0]]["lattice_px"] > 0
    for k in LAYERS[1:]:
        if not (px[k]["lattice_px"] == px[LAYERS[0]]["lattice_px"]).all():
            raise RuntimeError("layer lattice supports differ; split missing "
                               "reasons per layer before shipping")
    table = {
        "h3": pa.array(master),
        **{f"vcf_{k}_pct_median": pa.array(px[k]["median"], from_pandas=True) for k in LAYERS},
        **{f"vcf_{k}_pct_mean": pa.array(px[k]["mean_native"], from_pandas=True) for k in LAYERS},
        "vcf_lattice_px": pa.array(px[LAYERS[0]]["lattice_px"], pa.int32()),
        **{f"vcf_{k}_valid_native_px": pa.array(px[k]["native_px"], pa.int64()) for k in LAYERS},
        "missing_reason": pa.array(row_reasons(n, have)),
    }
    out = DERIVED / f"vcf-r{res}.parquet"
    meta = {
        "generatedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "h3Res": res, "cells": int(n), "family": "earth-context-vcf",
        "dataset": DATASET, "series": year, "granulesAggregated": len(hdfs),
        "observable": ("MODIS/Terra Vegetation Continuous Fields v061, yearly: percent "
                       "tree cover, percent non-tree vegetation, percent non-vegetated "
                       "(bare); latest complete annual series (period starts DOY 65)"),
        "statistic": ("per 0.05 deg lattice pixel: mean of the valid native 250 m pixels; "
                      "per hexagon: median over its lattice pixels' means (rounded to whole "
                      "%) and exact mean over its native valid pixels"),
        "pixelToHex": PIXEL_RULE,
        "qa": ("declared codes only: 0-100 valid, 200 water, 253 fill/outside projection "
               "(v061 user guide); the guide declares no masking rule for the percent "
               "layers, so Quality/Cloud bit layers are NOT applied as a mask; water/fill "
               "never enter statistics"),
        "knownLimits": ("C61 user guide: areas with sparse training samples (e.g. high "
                        "latitudes) are not retrieved and populated with fill value 0, so "
                        "a 0 there can mean not-retrieved rather than measured 0%"),
        "inputs": {e["localPath"]: {"sha256": e["sha256"], "bytes": e["bytes"]}
                   for e in _manifest_block()},
        "computed": {"nativePixelCodes": acc.native,
                     "latticeDroppedPx": px["lattice_dropped_px"],
                     "waterFillNativePx": acc.water_fill(),
                     "latticeNpz": f"data/snapshots/_derived/vcf-r{res}-cmg.npz"},
        "missing": {"rule": "hexagons whose mapped lattice pixels hold no valid native "
                            "MOD44B pixel stay null with missing_reason no-vcf-lattice-px",
                    "cells": int((~have).sum())},
    }
    tbl = pa.table(table)
    tbl = tbl.replace_schema_metadata({"cosmic-consultants": json.dumps(meta)})
    pq.write_table(tbl, out, compression="zstd")
    meta.update(path=str(out.relative_to(SNAP.parent.parent)), sha256=sha256(out),
                bytes=out.stat().st_size, seconds=round(time.time() - t0, 1))
    meta["nullRate"] = {c: round(tbl[c].null_count / n, 4) for c in tbl.column_names
                        if c != "missing_reason"}
    (DERIVED / f"vcf-r{res}.meta.json").write_text(json.dumps(meta, indent=2) + "\n")
    return meta


# -------------------------------------------------------------------- probes

def _http_get(url: str, timeout: int = 60):
    import requests
    return requests.get(url, timeout=timeout, allow_redirects=True)


def probe_eid() -> dict:
    """Re-probe passc.net with HTTP evidence; detect the parked redirect."""
    try:
        r = _http_get(EID_URL)
        parked = bool(re.search(r'window\.location\.href\s*=\s*"/lander"', r.text)) \
            or len(r.content) < 500
        return {"url": EID_URL, "httpStatus": r.status_code, "bytes": len(r.content),
                "finalUrl": r.url, "parked": bool(parked), "bodyStart": r.text[:160],
                "reachable": bool(r.status_code == 200 and not parked),
                "probedAt": datetime.now(timezone.utc).isoformat(timespec="seconds")}
    except Exception as exc:  # noqa: BLE001
        return {"url": EID_URL, "error": f"{type(exc).__name__}: {exc}"[:300],
                "reachable": False,
                "probedAt": datetime.now(timezone.utc).isoformat(timespec="seconds")}


def probe_ggd318() -> dict:
    """Probe the GGD318 hosts. Evidence only — its values are NOT used here."""
    out: dict = {"probedAt": datetime.now(timezone.utc).isoformat(timespec="seconds")}
    try:
        r = _http_get("https://nsidc.org/data/ggd318/versions/2")
        out["landing"] = {"status": r.status_code, "bytes": len(r.content)}
    except Exception as exc:  # noqa: BLE001
        out["landing"] = {"error": f"{type(exc).__name__}: {exc}"[:300]}
    try:
        r2 = _http_get("https://daacdata.apps.nsidc.org/public/DATASETS/ggd318/")
        out["daacdata"] = {"status": r2.status_code, "bytes": len(r2.content),
                           "finalUrl": r2.url,
                           "ursLoginRequired": "urs.earthdata" in (r2.url or "")}
    except Exception as exc:  # noqa: BLE001
        out["daacdata"] = {"error": f"{type(exc).__name__}: {exc}"[:300]}
    try:
        r3 = _http_get(GGD318_GUIDE)
        out["userGuide"] = {"status": r3.status_code, "bytes": len(r3.content),
                            "condition": "reuse permitted with citation (Brown et al. 2002, "
                                         "DOI 10.7265/skbg-kf16)"}
    except Exception as exc:  # noqa: BLE001
        out["userGuide"] = {"error": f"{type(exc).__name__}: {exc}"[:300]}
    out["verdict"] = ("blocked on access: legacy NSIDC ECS host refuses TCP; daacdata "
                      "requires interactive URS OAuth; no values used")
    return out


def write_probes() -> dict:
    ev = {"earth-impact-database": probe_eid(), "nsidc-ggd318-permafrost": probe_ggd318()}
    (DERIVED / "earth-static-probes.json").write_text(json.dumps(ev, indent=2) + "\n")
    return ev


# -------------------------------------------------------------------- check

def check(res: int = RES) -> dict:
    """Integrity checks on _derived/vcf-r{res}.parquet + 5 raw spot checks."""
    tbl = pq.read_table(DERIVED / f"vcf-r{res}.parquet")
    master = master_keys(res)
    n = tbl.num_rows
    errs: list[str] = []
    h3s = tbl["h3"].to_pylist()
    if len(set(h3s)) != n:
        errs.append("duplicate h3 keys")
    if set(h3s) != set(master.tolist()) or n != len(master):
        errs.append("h3 key set != cells-r4.parquet master keys")
    val_cols = [c for c in tbl.column_names
                if c.endswith("pct_median") or c.endswith("pct_mean")]
    arrays = {c: np.asarray(tbl[c].to_numpy(), dtype=np.float64) for c in val_cols}
    for c, a in arrays.items():
        ok = np.isnan(a) | ((a >= 0) & (a <= 100))
        if not ok.all():
            errs.append(f"{c}: values outside the physical range 0-100 "
                        f"({int((~ok).sum())} rows)")
    lattice = np.asarray(tbl["vcf_lattice_px"].to_numpy(), dtype=np.int64)
    if (lattice < 0).any():
        errs.append("vcf_lattice_px negative")
    for k in LAYERS:
        a = np.asarray(tbl[f"vcf_{k}_valid_native_px"].to_numpy(), dtype=np.int64)
        if (a < 0).any():
            errs.append(f"vcf_{k}_valid_native_px negative")
        if (a[lattice == 0] > 0).any():
            errs.append(f"{k}: native pixels counted without lattice pixels")
        if (lattice > 0).any() and (a[lattice > 0] <= 0).any():
            errs.append(f"{k}: lattice pixels without native pixels")
    # missing_reason keys == exactly the null value columns of that row
    vals = {c: tbl[c].to_pylist() for c in val_cols}
    bad = 0
    for i, txt in enumerate(tbl["missing_reason"].to_pylist()):
        try:
            keys = set(json.loads(txt))
        except Exception:
            bad += 1
            continue
        null_cols = {c for c in val_cols if vals[c][i] is None}
        if keys != null_cols:
            bad += 1
    if bad:
        errs.append(f"missing_reason keys != null value columns on {bad} rows")
    spot = spot_checks(res)
    for s in spot["checks"]:
        if not s.get("ok"):
            errs.append(f"spot check {s['name']}: {s.get('error', 'failed')}")
    return {"rows": n, "errors": errs, "spotChecks": spot["checks"], "ok": not errs}


def spot_checks(res: int = RES, coords=None) -> dict:
    """5 known coordinates. For each: find the covering granule(s) by bounding
    box, read the raw native pixel, recompute the containing 0.05 deg lattice
    pixel's mean/count per layer independently of the build path (explicit
    native row/col re-gathering) and compare against the stored lattice npz,
    then check the lattice pixel's hexagon is the table's key set."""
    npz_path = DERIVED / f"vcf-r{res}-cmg.npz"
    if not npz_path.exists():
        return {"checks": [{"name": "*", "ok": False, "error": "vcf-r4-cmg.npz missing"}],
                "failures": 1}
    npz = np.load(npz_path)
    sum_l = {k: npz[f"sum_{k}"] for k in LAYERS}
    cnt_l = {k: npz[f"n_{k}"] for k in LAYERS}
    master = master_keys(res).tolist()
    coords = coords or [(-3.10, -60.02, "central amazon"), (23.40, 12.50, "central sahara"),
                        (55.00, -105.00, "boreal canada"), (41.90, -93.60, "iowa cropland"),
                        (72.57, -38.46, "greenland ice sheet")]
    checks = []
    failures = 0
    for lat, lon, name in coords:
        rec: dict = {"name": name, "lat": lat, "lon": lon}
        try:
            phi = np.radians(lat)
            x = float(SPHERE_R * np.radians(lon) * np.cos(phi))
            y = float(SPHERE_R * phi)
            hits = []
            for fname, rel in _all_manifest_hdfs():
                meta = parse_struct(SNAP.parent.parent / rel)
                if meta["x_ul"] <= x <= meta["x_lr"] and meta["y_lr"] <= y <= meta["y_ul"]:
                    hits.append((rel, meta))
            if not hits:
                raise RuntimeError("no fetched granule covers this coordinate")
            rel = hits[0][0]
            meta = hits[0][1]
            px_y = (meta["y_ul"] - meta["y_lr"]) / meta["rows"]
            px_x = (meta["x_lr"] - meta["x_ul"]) / meta["cols"]
            r = int((meta["y_ul"] - y) / px_y)
            c = int((x - meta["x_ul"]) / px_x)
            lat_c, lon_c = inverse_sin(
                np.array([meta["x_ul"] + (c + 0.5) * px_x]),
                np.array([meta["y_ul"] - (r + 0.5) * px_y]))
            flat = int((90.0 - lat_c[0]) / CMG_STEP) * CMG_M + int((180.0 + lon_c[0]) / CMG_STEP)
            rec["rawPixel"] = {"granule": rel.rsplit("/", 1)[-1], "row": r, "col": c}
            sd = SD(str(SNAP.parent.parent / rel), SDC.READ)
            raw = {k: int(sd.select(SDS[k])[r, c]) for k in LAYERS}
            sd.end()
            rec["rawValues"] = raw
            if any(v > 100 and v not in (CODE_WATER, CODE_FILL) for v in raw.values()):
                raise RuntimeError(f"unexpected native codes {raw}")
            # independent lattice recomputation: re-gather the native pixels of
            # this lattice pixel by explicit row/col ranges in every covering tile
            irow, icol = flat // CMG_M, flat % CMG_M
            lat_lo, lat_hi = 90.0 - CMG_STEP * (irow + 1), 90.0 - CMG_STEP * irow
            lon_lo, lon_hi = -180.0 + CMG_STEP * icol, -180.0 + CMG_STEP * (icol + 1)
            fresh: dict = {}
            for rel2, _ in hits:
                m2 = parse_struct(SNAP.parent.parent / rel2)
                p_y = (m2["y_ul"] - m2["y_lr"]) / m2["rows"]
                p_x = (m2["x_lr"] - m2["x_ul"]) / m2["cols"]
                rr = np.arange(m2["rows"])
                cc = np.arange(m2["cols"])
                y_rows = m2["y_ul"] - (rr + 0.5) * p_y
                phi_rows = y_rows / SPHERE_R
                lat_rows = np.degrees(phi_rows)
                rmask = np.nonzero((lat_rows >= lat_lo) & (lat_rows < lat_hi))[0]
                if not len(rmask):
                    continue
                x_cols = m2["x_ul"] + (cc + 0.5) * p_x
                s2 = SD(str(SNAP.parent.parent / rel2), SDC.READ)
                for k in LAYERS:
                    v = s2.select(SDS[k])[int(rmask[0]):int(rmask[-1]) + 1, :]
                    lam = x_cols[None, :] / (SPHERE_R * np.cos(phi_rows[rmask]))[:, None]
                    lon_px = np.degrees(lam)
                    cmask = (lon_px >= lon_lo) & (lon_px < lon_hi)
                    ok_v = v[cmask]
                    ok_v = ok_v[ok_v <= 100]
                    fresh[k] = fresh.get(k, 0) + int(np.sum(ok_v))
                    fresh["n_" + k] = fresh.get("n_" + k, 0) + int(ok_v.size)
                s2.end()
            rec["freshLattice"] = {k: (fresh[k], fresh["n_" + k])
                                   for k in LAYERS if "n_" + k in fresh}
            for k in LAYERS:
                if "n_" + k not in fresh:
                    continue
                if int(cnt_l[k][flat]) != fresh["n_" + k] \
                        or int(sum_l[k][flat]) != fresh[k]:
                    raise RuntimeError(
                        f"{k} lattice mismatch at CMG ({flat // CMG_M},{flat % CMG_M}): "
                        f"stored sum/n = {int(sum_l[k][flat])}/{int(cnt_l[k][flat])}, "
                        f"fresh {fresh[k]}/{fresh['n_' + k]} "
                        f"(raw pixel {raw[k]})")
            # the lattice pixel's hexagon must be in the table key set
            hexid = format(int(h3.latlng_to_cell(
                90.0 - CMG_STEP * (irow + 0.5), -180.0 + CMG_STEP * (icol + 0.5), res),
                16), "x")
            rec["hexagon"] = hexid
            rec["inTable"] = hexid in master
            rec["ok"] = True
        except Exception as exc:  # noqa: BLE001
            rec["ok"] = False
            rec["error"] = f"{type(exc).__name__}: {exc}"[:300]
        failures += 0 if rec.get("ok") else 1
        checks.append(rec)
    return {"checks": checks, "failures": failures}


def main(argv: list[str] | None = None) -> int:
    argv = argv or sys.argv[1:]
    if argv[:1] == ["--fetch"]:
        print(json.dumps(fetch_mod44b(), indent=1))
        return 0
    if argv[:1] == ["check"]:
        c = check()
        print(json.dumps(c, indent=1, default=str)[:6000])
        return 0 if c["ok"] else 1
    if argv[:1] == ["probe"]:
        for k, v in write_probes().items():
            print(k, json.dumps(v)[:400])
        return 0
    if argv[:1] == ["build"]:
        m = build(limit=int(argv[1]) if len(argv) > 1 else None)
        print(json.dumps({k: m[k] for k in ("path", "sha256", "bytes", "seconds",
                                            "nullRate")}, indent=1))
        return 0
    print("usage: python -m p0ingest.earth_static [--fetch | build [limit] | check | probe]")
    return 2


if __name__ == "__main__":
    sys.exit(main())
