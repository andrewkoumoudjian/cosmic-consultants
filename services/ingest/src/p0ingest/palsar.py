"""W37 (#96): ALOS PALSAR L-band radar backscatter for the campaign-site hexagons.

Source: alos-palsar-rtc-high (ASF DAAC, CMR collection C1206487504-ASF, DOI
10.5067/Z97HFCNKR6VA; licence "© NASA [Year], Includes Material © JAXA, METI
[Year]" per the registry row, verified 2026-11-12 by the W3 licence audit).

The global Hi-Res RTC family is ~506k single-date scenes (FBD dual-pol ~300 MB
each), so a global composite is infeasible here. This table is therefore
REGIONAL on purpose (subset rule, also recorded in the meta JSON):

  For each of the six campaign files in data/campaigns/ take the site's H3
  res-4 cell plus its ring-1 neighbours (H3 grid_disk(cell, 1)), i.e. 7 cells
  per site. The six files give 5 distinct parent cells (FMARS and HMP-2015
  share Devon Island), hence exactly 35 table keys.

Per key the table records the median of gamma0 in dB over a stride-30 pixel
subgrid (every 30th row and column of the 12.5 m raster = 1/900 of pixels,
a deterministic decimation) pooled across the selected scenes, plus per-band
valid-subpixel counts and the acquisition dates of the pooled scenes. Scenes
are ALOS PALSAR FBD (HH+HV) RTC_Hi-Res granules whose CMR footprint polygon
covers a hexagon's centre + 6 boundary vertices; a greedy cover picks the
fewest scenes, newest acquisition first.

PROXY LIMITS (stated, not hidden): PALSAR is L-band (1.26 GHz) LINEAR
polarization. The engineering targets radar_ka_backscatter (Mars, Ka band)
and cpr_minirf (Moon, circular polarization ratio) are a different band AND a
different polarization basis. No conversion was made and none is claimed;
these columns are a weak Earth-side analogue only.

Time support: static composite of single-date ALOS-1 scenes (mission span
2006-03..2011-04, per-scene dates recorded). The at-most-monthly owner rule is
respected: no sub-scene/multi-date time series is built.

Run: python -m p0ingest.palsar --query | --fetch | --build | --check
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import zipfile
from pathlib import Path

try:
    import h3
    import numpy as np
    import pyarrow as pa
    import pyarrow.parquet as pq
    import rasterio
    import requests
    import yaml
    from rasterio.warp import transform as warp_transform
except ImportError as exc:  # pragma: no cover - env issue, not code issue
    raise SystemExit(f"missing dependency ({exc}); run: cd services/ingest && uv sync --frozen") from exc

from . import snapshots
from .snapshots import REPO, SNAP, fetch, load_manifest

DATASET = "alos-palsar-rtc-high"
COLLECTION = "C1206487504-ASF"
CMR_GRANULES = "https://cmr.earthdata.nasa.gov/search/granules.umm_json"
RES = 4
STRIDE = 30  # every 30th row and column of the 12.5 m raster (1/900 of pixels)
WINDOW = 1024  # read-window size in pixels, snapped to multiples of STRIDE
MIN_VALID_SAMPLES = 50  # a median needs at least this many valid subgrid pixels
DB_RANGE = (-45.0, 20.0)  # plausible L-band gamma0 dB guard for the check
OUT_DIR = SNAP / "_derived"
OUT_PARQUET = OUT_DIR / "palsar-r4-sites.parquet"
OUT_META = OUT_DIR / "palsar-r4-sites.meta.json"
SELECTION_FILE = OUT_DIR / "palsar-r4-scene-selection.json"
CAMPAIGNS_DIR = REPO / "data" / "campaigns"
RAW_DIR = SNAP / DATASET
VALUE_COLS = ("gamma0_hh_db", "gamma0_hv_db", "gamma0_hh_valid_pixels", "gamma0_hv_valid_pixels")
MISSING_ASF_BLOCK = "asf-eula-not-approved"  # when raw scenes could not be fetched
MISSING_NO_SCENE = "no-fbd-scene-covers"
MISSING_THIN = "not-enough-valid-pixels"
MISSING_NO_RAW = "scene-batch-unfetched"


# --------------------------------------------------------------------- sites


def campaign_sites(campaigns_dir: Path = CAMPAIGNS_DIR) -> list[dict]:
    """The six campaign files -> one row each: campaign, file, parent cell, lat/lon."""
    rows = []
    for path in sorted(Path(campaigns_dir).glob("*.yaml")):
        doc = yaml.safe_load(path.read_text(encoding="utf-8"))
        site = doc.get("site") or {}
        cell = site.get("h3r4")
        if not cell:
            raise ValueError(f"{path}: no site.h3r4")
        if not h3.is_valid_cell(cell) or h3.get_resolution(cell) != RES:
            raise ValueError(f"{path}: site.h3r4 {cell} is not a valid H3 res-{RES} cell")
        rows.append({"campaign": doc["name"], "file": path.name, "cell": cell,
                     "lat": float(site["lat"]), "lon": float(site["lon"])})
    if len(rows) < 6:
        raise ValueError(f"expected 6 campaign files under {campaigns_dir}, found {len(rows)}")
    return rows


def site_clusters(rows: list[dict]) -> dict[str, dict]:
    """Parent cell -> {cells: 7-cell cluster (grid_disk 1), sites, files}."""
    by_parent: dict[str, dict] = {}
    for row in rows:
        entry = by_parent.setdefault(row["cell"], {
            "cells": sorted(h3.grid_disk(row["cell"], 1)), "sites": [], "files": []})
        entry["sites"].append(row["campaign"])
        entry["files"].append(row["file"])
    for entry in by_parent.values():
        if len(entry["cells"]) != 7:
            raise ValueError("H3 ring-1 neighbour set is not 7 cells; grid geometry unexpected")
    return by_parent


def cluster_bbox(cells: list[str]) -> tuple[float, float, float, float]:
    """(lon_min, lat_min, lon_max, lat_max) over the clusters' centres AND hexagon
    boundary vertices (vertices reach past the centre bounding box), padded 0.05 deg."""
    lats, lons = [], []
    for c in cells:
        for lon, lat in cell_pts(c):
            lats.append(lat)
            lons.append(lon)
    pad = 0.05
    return min(lons) - pad, min(lats) - pad, max(lons) + pad, max(lats) + pad


# --------------------------------------------------------------------- CMR


def _attrs(umm: dict) -> dict:
    return {a["Name"]: a["Values"][0] for a in umm.get("AdditionalAttributes", []) if a["Values"]}


def _granule(umm: dict) -> dict:
    a = _attrs(umm)
    polygon: list[tuple[float, float]] = []
    try:
        ring = umm["SpatialExtent"]["HorizontalSpatialDomain"]["Geometry"]["GPolygons"][0]["Boundary"]["Points"]
        polygon = [(p["Longitude"], p["Latitude"]) for p in ring]
    except (KeyError, IndexError):
        pass
    urls = [r["URL"] for r in umm.get("RelatedUrls", []) if r.get("Type") == "GET DATA"]
    return {"ur": umm["GranuleUR"], "acq": a.get("ACQUISITION_DATE"),
            "pol": a.get("POLARIZATION"), "beam": a.get("BEAM_MODE_TYPE"),
            "bytes": float(a.get("BYTES", 0.0)), "polygon": polygon,
            "url": urls[0] if urls else None}


def cmr_granules(bbox: tuple[float, float, float, float], max_pages: int = 20) -> list[dict]:
    """All collection granules intersecting a (lon_min, lat_min, lon_max, lat_max) box."""
    granules: list[dict] = []
    hits, page = None, 1
    while True:
        r = requests.get(CMR_GRANULES, params={"concept_id": COLLECTION, "bounding_box":
                                               ",".join(f"{v:.5f}" for v in bbox),
                                               "page_size": 1000, "page_num": page}, timeout=(30, 300))
        r.raise_for_status()
        payload = r.json()
        items = payload.get("items", [])
        if hits is None:
            hits = payload.get("hits")
        granules.extend(_granule(i["umm"]) for i in items)
        if hits is None or len(granules) >= hits or page >= max_pages or not items:
            break
        page += 1
    return granules


# --------------------------------------------------------------------- geometry


def _point_in_ring(x: float, y: float, ring: list[tuple[float, float]]) -> bool:
    """Ray casting on a polygon ring of (lon, lat) vertices; duplicate wrap vertex tolerated."""
    inside = False
    n = len(ring)
    if n < 3:
        return False
    j = n - 1
    for k in range(n):
        x1, y1 = ring[k]
        x2, y2 = ring[j]
        if (y1 > y) != (y2 > y):
            x_int = (x2 - x1) * (y - y1) / (y2 - y1) + x1
            if x < x_int:
                inside = not inside
        j = k
    return inside


def cell_pts(cell: str) -> list[tuple[float, float]]:
    """Hexagon coverage points as (lon, lat): centre + 6 boundary vertices."""
    lat, lng = h3.cell_to_latlng(cell)
    return [(lng, lat)] + [(lng_v, lat_v) for lat_v, lng_v in h3.cell_to_boundary(cell)]


def covered_cells(granule: dict, cells: list[str]) -> set[str]:
    """Cells whose centre + 6 vertices all fall inside the granule's CMR footprint."""
    if not granule["polygon"]:
        return set()
    pts = {c: cell_pts(c) for c in cells}
    return {c for c in cells if all(_point_in_ring(x, y, granule["polygon"]) for x, y in pts[c])}


def select_scenes(granules: list[dict], cells: list[str]) -> tuple[list[dict], list[str]]:
    """Greedy fewest-scenes cover of every cluster cell, by footpoint UNION.

    Scenes are long rotated strips (~70 km) that rarely contain a whole res-4
    hexagon, so coverage is evaluated per point: a cell is covered when its
    centre + 6 boundary vertices ALL lie inside the union of the selected
    footprints (pixel samples are pooled across scenes accordingly). Only FBD
    dual-pol granules (POLARIZATION == 'HH+HV') with a download URL are
    candidates: HH-only FBS scenes cannot give an HV median. Ties on newly
    covered points go to the newest acquisition. Returns (selected, uncovered).
    """
    pool = [g for g in granules if g["pol"] == "HH+HV" and g["url"] and g["polygon"]]
    pool.sort(key=lambda g: g["acq"] or "", reverse=True)
    pts = {c: cell_pts(c) for c in cells}
    uncovered_pts = {c: set(range(len(pts[c]))) for c in cells}
    chosen: list[dict] = []
    while True:
        remaining = sum(len(v) for v in uncovered_pts.values())
        if remaining == 0:
            break
        best, best_gain = None, None
        for g in pool:
            gain = sum(1 for c, idxs in uncovered_pts.items()
                       for i in idxs if _point_in_ring(pts[c][i][0], pts[c][i][1], g["polygon"]))
            if best_gain is None or gain > best_gain:
                best, best_gain = g, gain
        if best is None or best_gain == 0:
            break
        chosen.append(best)
        pool.remove(best)
        for c, idxs in uncovered_pts.items():
            uncovered_pts[c] = {i for i in idxs
                                if not _point_in_ring(pts[c][i][0], pts[c][i][1], best["polygon"])}
    return chosen, sorted(c for c, idxs in uncovered_pts.items() if idxs)


# --------------------------------------------------------------------- fetch


def fetch_scenes(scenes: list[dict]) -> dict[str, Path]:
    """Download selected scenes through p0ingest.snapshots.fetch (MANIFEST provenance).

    ASF datapool is an Earthdata host but missing from snapshots.EARTHDATA_HOSTS;
    the tuple is extended at runtime (no edit of the shared module) so the bearer
    token rides the redirects exactly as for the other DAACs.
    """
    if "asf.alaska.edu" not in snapshots.EARTHDATA_HOSTS:
        snapshots.EARTHDATA_HOSTS = snapshots.EARTHDATA_HOSTS + ("asf.alaska.edu",)
    paths: dict[str, Path] = {}
    for scene in scenes:
        paths[scene["ur"]] = fetch(DATASET, scene["url"])
    return paths


# --------------------------------------------------------------------- scene reading


def _tif_pol(name: str) -> str | None:
    base = Path(name).name.upper()
    for pol in ("HH", "HV"):
        if f"_{pol}" in base or base.endswith(pol):
            return pol
    return None


def scene_files(path: Path) -> list[tuple[str, str | None]]:
    """(rasterio URL, polarization) for the polarization TIFFs inside an RTC zip."""
    path = Path(path)
    if path.suffix.lower() == ".tif":
        return [(str(path), _tif_pol(path.name))]
    with zipfile.ZipFile(path) as z:
        return [(f"/vsizip/{path}/{name}", _tif_pol(name))
                for name in z.namelist() if name.lower().endswith(".tif")]


def to_db(values: np.ndarray, already_db: bool) -> np.ndarray:
    """gamma0 to dB. Linear power: 10*log10 with values <= 0 invalid; dB files pass
    through. Anything outside the physical guard range becomes invalid (NaN)."""
    v = np.asarray(values, dtype="float64").copy()
    finite = np.isfinite(v)
    with np.errstate(invalid="ignore", divide="ignore"):
        if not already_db:
            v = np.where(finite & (v > 0), 10.0 * np.log10(np.where(finite & (v > 0), v, 1.0)), np.nan)
    v[~np.isfinite(v)] = np.nan
    v[(v < DB_RANGE[0]) | (v > DB_RANGE[1])] = np.nan
    return v


def _band_is_db(src) -> tuple[bool, str]:
    parts = list(src.descriptions) + [str(v) for v in (src.tags() or {}).values()]
    handle = " ".join(str(p) for p in parts)
    return "db" in handle.lower(), handle[:200]


def process_scene(path: Path, cells: list[str]) -> dict:
    """Pixel -> hexagon per the declared rule, on the stride-30 subgrid.

    For every 30th raster row and column (one fixed-offset grid), the pixel CENTRE
    is projected raster CRS -> WGS84 per read window (vectorised) and assigned
    with h3.latlng_to_cell(lat, lon, 4); subgrid pixels inside one of the
    cluster's 7 cells pool their dB value into that cell. Returns
    {cell: {'HH': [...], 'HV': [...]}, 'stride_pixels': n, 'band_info': {...}}.
    """
    out = {c: {"HH": [], "HV": []} for c in cells}
    wanted = set(cells)
    lon_min, lat_min, lon_max, lat_max = cluster_bbox(cells)
    stride_pixels = 0
    band_info: dict[str, dict] = {}
    for url, pol in scene_files(path):
        if pol is None:
            continue
        with rasterio.open(url) as src:
            already_db, desc = _band_is_db(src)
            t = src.transform
            if not (t.b == 0 and t.d == 0):
                raise ValueError(f"{Path(url).name}: rotated raster not supported per declared rule")
            xs, ys = warp_transform("EPSG:4326", src.crs,
                                    [lon_min, lon_max, lon_max, lon_min],
                                    [lat_min, lat_min, lat_max, lat_max])
            corners = [src.index(x, y) for x, y in zip(xs, ys)]
            r_lo = max(0, min(r for r, _ in corners))
            r_hi = min(src.height, max(r for r, _ in corners))
            c_lo = max(0, min(c for _, c in corners))
            c_hi = min(src.width, max(c for _, c in corners))
            if r_lo >= r_hi or c_lo >= c_hi:
                continue
            band_info[Path(url).name] = {"pol": pol, "crs": str(src.crs), "already_db": already_db,
                                         "desc": desc, "window": [int(r_lo), int(r_hi), int(c_lo), int(c_hi)]}
            for r0 in range((r_lo // STRIDE) * STRIDE, r_hi, WINDOW):
                for c0 in range((c_lo // STRIDE) * STRIDE, c_hi, WINDOW):
                    win_h = min(WINDOW, r_hi - r0)
                    win_w = min(WINDOW, c_hi - c0)
                    if win_h <= 0 or win_w <= 0:
                        continue
                    band = src.read(1, window=rasterio.windows.Window(
                        c0, r0, win_w, win_h))
                    sub = band[::STRIDE, ::STRIDE]
                    sub_rows = np.arange(r0, r0 + win_h, STRIDE)
                    sub_cols = np.arange(c0, c0 + win_w, STRIDE)
                    grid_r, grid_c = np.meshgrid(sub_rows, sub_cols, indexing="ij")
                    lons, lats = warp_transform(
                        src.crs, "EPSG:4326",
                        (t.c + t.a * (grid_c.astype("float64") + 0.5)).ravel(),
                        (t.f + t.e * (grid_r.astype("float64") + 0.5)).ravel())
                    vals = to_db(sub.ravel(), already_db)
                    stride_pixels += int(sub.size)
                    for lat, lon, val in zip(lats, lons, vals):
                        if val != val:
                            continue
                        cell = h3.latlng_to_cell(lat, lon, RES)
                        if cell in wanted:
                            out[cell][pol].append(float(val))
    return {"cells": out, "stride_pixels": stride_pixels, "band_info": band_info}


# --------------------------------------------------------------------- build


def median_stream(samples: list[float], min_valid: int = MIN_VALID_SAMPLES) -> tuple[float | None, int]:
    """(median or None, count). Below the support minimum the median stays missing."""
    if len(samples) < min_valid:
        return None, len(samples)
    return float(np.median(np.asarray(samples, dtype="float64"))), len(samples)


def build(out_parquet: Path = OUT_PARQUET, out_meta: Path = OUT_META,
          raw_dir: Path = RAW_DIR, selection_path: Path = SELECTION_FILE) -> dict:
    """Aggregate fetched scenes into the regional table (+ meta). Missing stays missing."""
    missing_reason: dict[str, str] = {}
    sites = campaign_sites()
    clusters = site_clusters(sites)
    meta: dict = {
        "generatedAt": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S+00:00"),
        "h3Res": RES,
        "datasetId": DATASET,
        "subsetRule": "six campaign files in data/campaigns/: the site hexagon plus its H3 "
                      "ring-1 neighbours (grid_disk(cell,1), 7 cells per site). FMARS and "
                      "HMP-2015 share one parent cell -> 5 distinct sites -> 35 keys.",
        "pixelToHexRule": "raster pixel CENTRE projected raster CRS -> WGS84 per read window "
                          "with rasterio.warp.transform, then h3.latlng_to_cell(lat, lon, 4)",
        "sampleRule": f"stride-{STRIDE} subgrid of the 12.5 m raster (every {STRIDE}-th row and "
                      f"column = 1/{STRIDE * STRIDE} of pixels); median over that subgrid pooled "
                      f"across selected scenes; valid-subpixel counts refer to this subgrid",
        "statistic": "median of gamma0 [dB] pooled per cell; kept only with >= "
                     f"{MIN_VALID_SAMPLES} valid subgrid pixels, else missing ('{MISSING_THIN}')",
        "proxyLimits": "PALSAR is L-band (1.26 GHz) LINEAR polarization (HH, HV). The targets "
                       "radar_ka_backscatter (Mars, Ka band) and cpr_minirf (Moon, circular "
                       "polarization ratio) are a different frequency band and polarization "
                       "basis; NO conversion was made and none is claimed.",
        "timeSupport": "static composite of single-date ALOS-1 scenes (mission span 2006-03/"
                       "2011-04 per the registry row); scene acquisition dates recorded per row; "
                       "no time series built (owner rule: at most monthly satisfied by design)",
        "sceneSelection": "CMR granules intersecting the cluster bbox, POLARIZATION 'HH+HV' only "
                          "(HH-only FBS cannot give an HV median); greedy fewest-scenes cover where "
                          "a cell counts covered when its centre + 6 boundary vertices all lie "
                          "inside the UNION of selected CMR footprint polygons (scenes are rotated "
                          "strips that rarely contain a whole hexagon, so pixel samples pool across "
                          "scenes); newest acquisition first on ties; selection file in the meta",
        "units": "gamma0 in dB; linear-power pixel values converted as 10*log10(power), "
                 "non-positive and out-of-guard-range values dropped",
        "license": "© NASA [Year], Includes Material © JAXA, METI [Year] (ASF EULA; registry "
                   "row licence.verified true)",
        "inputs": [],
        "blocks": [],
        "sources": sites,
    }
    for row in meta["sources"]:
        row["cells"] = clusters[row["cell"]]["cells"]
    rows: dict[str, dict] = {}
    for parent, info in clusters.items():
        for cell in info["cells"]:
            rows[cell] = {"h3": cell, "parent": parent, "sites": info["sites"],
                          "HH": [], "HV": [], "scenes": [], "acq": []}
    manifest = load_manifest()
    local = {Path(e["localPath"]).name: e for e in manifest["entries"] if e.get("datasetId") == DATASET}
    selection: dict[str, list[dict]] = {}
    if selection_path.exists():
        selection = json.loads(selection_path.read_text(encoding="utf-8"))
    else:
        meta["blocks"].append({
            "code": MISSING_ASF_BLOCK,
            "detail": "No scene-selection file -> raw scenes were never fetched. ASF datapool "
                      "needs a one-time Earthdata app/EULA approval: "
                      "https://urs.earthdata.nasa.gov/approve_app?client_id=BO_n7nTIlMljdvU6kRRB3g "
                      "then cumulus.asf.alaska.edu/s3credentials returns 403 "
                      "'EULA Acceptance Failure' without it. Evidence on issue #96 "
                      "(2026-11-14). No values filled; nothing synthesized."})
    if selection:
        for parent in clusters:  # zones without a selection entry stayed unfetched too
            if parent not in selection:
                for cell in clusters[parent]["cells"]:
                    missing_reason.setdefault(cell, MISSING_ASF_BLOCK)
        for parent, scenes in selection.items():
            for scene in scenes:
                entry = local.get(Path(scene["zip"]).name)
                if entry and entry not in meta["inputs"]:
                    meta["inputs"].append(entry)
            for cell in clusters[parent]["cells"]:
                rows[cell]["scenes"] = [s["ur"] for s in scenes]
                rows[cell]["acq"] = [s["acq"] for s in scenes if s.get("acq")]
            uncovered = set(clusters[parent]["cells"])
            for scene in scenes:
                zp = raw_dir / scene["zip"]
                if not zp.exists():
                    for cell in uncovered:
                        missing_reason[cell] = MISSING_NO_RAW
                    continue
                res = process_scene(zp, clusters[parent]["cells"])
                got = set()
                for cell in clusters[parent]["cells"]:
                    rows[cell]["HH"].extend(res["cells"][cell]["HH"])
                    rows[cell]["HV"].extend(res["cells"][cell]["HV"])
                    if res["cells"][cell]["HH"] or res["cells"][cell]["HV"]:
                        got.add(cell)
                uncovered -= got
                for cell in got:
                    missing_reason.pop(cell, None)
            for cell in sorted(uncovered):
                missing_reason.setdefault(cell, MISSING_NO_SCENE)
    records = []
    for cell in sorted(rows):
        row = rows[cell]
        hh, hh_n = median_stream(row["HH"])
        hv, hv_n = median_stream(row["HV"])
        block_code = MISSING_ASF_BLOCK if meta["blocks"] else MISSING_THIN
        reason = missing_reason.get(cell) or block_code
        nulls = {}
        if hh is None:
            nulls["gamma0_hh_db"] = reason
            nulls["gamma0_hh_valid_pixels"] = reason
        if hv is None:
            nulls["gamma0_hv_db"] = reason
            nulls["gamma0_hv_valid_pixels"] = reason
        records.append({
            "h3": cell,
            "campaigns": row["sites"],
            "scene_urs": row["scenes"],
            "acq_dates": row["acq"],
            "gamma0_hh_db": hh,
            "gamma0_hv_db": hv,
            "gamma0_hh_valid_pixels": None if hh is None else hh_n,
            "gamma0_hv_valid_pixels": None if hv is None else hv_n,
            "missing_reason": json.dumps(nulls, sort_keys=True) if nulls else "",
        })
    table = pa.table({
        "h3": pa.array([r["h3"] for r in records], pa.string()),
        "campaigns": pa.array([r["campaigns"] for r in records], pa.list_(pa.string())),
        "scene_urs": pa.array([r["scene_urs"] for r in records], pa.list_(pa.string())),
        "acq_dates": pa.array([r["acq_dates"] for r in records], pa.list_(pa.string())),
        "gamma0_hh_db": pa.array([r["gamma0_hh_db"] for r in records], pa.float64()),
        "gamma0_hv_db": pa.array([r["gamma0_hv_db"] for r in records], pa.float64()),
        "gamma0_hh_valid_pixels": pa.array([r["gamma0_hh_valid_pixels"] for r in records], pa.int64()),
        "gamma0_hv_valid_pixels": pa.array([r["gamma0_hv_valid_pixels"] for r in records], pa.int64()),
        "missing_reason": pa.array([r["missing_reason"] for r in records], pa.string()),
    })
    out_parquet.parent.mkdir(parents=True, exist_ok=True)
    pq.write_table(table, out_parquet)
    out_meta.write_text(json.dumps(meta, indent=1), encoding="utf-8")
    return {"rows": table.num_rows, "meta": meta}


# --------------------------------------------------------------------- check


def check(out_parquet: Path = OUT_PARQUET, raw_dir: Path = RAW_DIR,
          selection_path: Path = SELECTION_FILE) -> dict:
    """Structural checks + >=5 raw spot checks (recomputed medians vs the table)."""
    problems: list[str] = []
    table = pq.read_table(out_parquet)
    column_names = table.column_names
    expected = ("h3", "campaigns", "scene_urs", "acq_dates", "gamma0_hh_db", "gamma0_hv_db",
                "gamma0_hh_valid_pixels", "gamma0_hv_valid_pixels", "missing_reason")
    if column_names != list(expected):
        problems.append(f"columns {column_names} != {list(expected)}")
        report = {"rows": table.num_rows, "missing_values": None, "problems": problems,
                  "spots": "NOT RUN", "status": "fail"}
        print(json.dumps(report, indent=1))
        return report
    keys = [str(v) for v in table.column("h3").to_pylist()]
    if len(set(keys)) != len(keys):
        problems.append("duplicate h3 keys")
    for key in keys:
        if not (h3.is_valid_cell(key) and h3.get_resolution(key) == RES):
            problems.append(f"{key}: not a valid res-{RES} H3 cell")
    expected_keys: set[str] = {
        c for info in site_clusters(campaign_sites()).values() for c in info["cells"]}
    if set(keys) != expected_keys:
        problems.append(f"keys {len(keys)} != 35 expected subset keys")

    def col(name):
        return table.column(name).to_pylist()

    hh_med, hv_med = col("gamma0_hh_db"), col("gamma0_hv_db")
    hh_n, hv_n = col("gamma0_hh_valid_pixels"), col("gamma0_hv_valid_pixels")
    reasons = col("missing_reason")
    n_missing = 0
    for i, key in enumerate(keys):
        null_cols = [c for c, v in (("gamma0_hh_db", hh_med[i]), ("gamma0_hv_db", hv_med[i]),
                                    ("gamma0_hh_valid_pixels", hh_n[i]), ("gamma0_hv_valid_pixels", hv_n[i]))
                     if v is None]
        try:
            parsed = json.loads(reasons[i]) if reasons[i] else {}
        except json.JSONDecodeError:
            problems.append(f"{key}: missing_reason not JSON: {reasons[i]!r}")
            continue
        if parsed and set(parsed) != set(null_cols):
            problems.append(f"{key}: missing_reason keys {sorted(parsed)} != nulls {null_cols}")
        if (hh_med[i] is None) != (hh_n[i] is None) or (hv_med[i] is None) != (hv_n[i] is None):
            problems.append(f"{key}: median/valid-count null mismatch")
        for name, value in (("HH", hh_med[i]), ("HV", hv_med[i])):
            if value is None:
                n_missing += 1
            elif not (DB_RANGE[0] <= value <= DB_RANGE[1]):
                problems.append(f"{key}: gamma0_{name.lower()}_db {value} outside physical guard")
        for name, count in (("HH", hh_n[i]), ("HV", hv_n[i])):
            if count is not None and count < 1:
                problems.append(f"{key}: gamma0_{name.lower()}_valid_pixels {count} < 1")
    spots = _spot_checks(keys, hh_med, hv_med, raw_dir, selection_path)
    problems.extend(spots["problems"])
    status = "blocked" if not raw_available(selection_path, raw_dir) else ("ok" if not problems else "fail")
    report = {"rows": table.num_rows, "missing_values": n_missing, "problems": problems,
              "spots": spots["summary"], "status": status}
    print(json.dumps(report, indent=1))
    return report


def raw_available(selection_path: Path, raw_dir: Path) -> bool:
    if not selection_path.exists():
        return False
    selection = json.loads(Path(selection_path).read_text(encoding="utf-8"))
    return any((Path(raw_dir) / s["zip"]).exists()
               for scenes in selection.values() for s in scenes)


def _spot_checks(keys: list[str], hh_med, hv_med, raw_dir: Path, selection_path: Path) -> dict:
    """Recompute 5 cells' medians straight from the raw zips and compare exactly."""
    problems: list[str] = []
    if not raw_available(selection_path, raw_dir):
        return {"summary": "NOT RUN (no raw scenes fetched; blocked per meta.blocks)",
                "problems": []}
    selection = json.loads(Path(selection_path).read_text(encoding="utf-8"))
    clusters = site_clusters(campaign_sites())
    with_data = [k for i, k in enumerate(keys) if hh_med[i] is not None or hv_med[i] is not None]
    targets = (with_data or keys)[:5]
    if len(targets) < 5:
        problems.append(f"only {len(targets)} cells available for spot checks, need 5")
    for cell in targets:
        parent = next(p for p, info in clusters.items() if cell in info["cells"])
        pooled = {"HH": [], "HV": []}
        for scene in selection.get(parent, []):
            zp = raw_dir / scene["zip"]
            if not zp.exists():
                continue
            res = process_scene(zp, clusters[parent]["cells"])
            for pol in ("HH", "HV"):
                pooled[pol].extend(res["cells"][cell][pol])
        for pol, table_val in (("HH", hh_med[keys.index(cell)]), ("HV", hv_med[keys.index(cell)])):
            med, _ = median_stream(pooled[pol])
            if (med is None) != (table_val is None):
                problems.append(f"{cell} {pol}: median recompute {med} != table {table_val}")
            elif med is not None and abs(med - table_val) > 1e-9:
                problems.append(f"{cell} {pol}: median recompute {med} != table {table_val}")
    return {"summary": f"{len(targets)} cell x 2-band medians recomputed from raw and compared",
            "problems": problems}


# --------------------------------------------------------------------- query (CMR probe + plan)


def query(save: bool = True) -> dict:
    """Probe CMR per site, pick scenes, write the selection file, print the size plan."""
    clusters = site_clusters(campaign_sites())
    selection: dict[str, list[dict]] = {}
    total_bytes = 0.0
    plan: list[dict] = []
    for parent, info in clusters.items():
        granules = cmr_granules(cluster_bbox(info["cells"]))
        chosen, uncovered = select_scenes(granules, info["cells"])
        entries = [{"ur": g["ur"], "acq": g["acq"], "bytes": g["bytes"], "url": g["url"],
                    "zip": Path(g["url"]).name.split("?")[0] if g["url"] else None}
                   for g in chosen]
        selection[parent] = entries
        parent_bytes = sum(e["bytes"] for e in entries)
        total_bytes += parent_bytes
        plan.append({"parent": parent, "sites": info["sites"], "candidates": len(granules),
                     "dualpol_candidates": sum(1 for g in granules if g["pol"] == "HH+HV"),
                     "chosen": [e["ur"] for e in entries], "bytes": int(parent_bytes),
                     "uncovered": uncovered})
    out = {"plan": plan, "total_bytes": int(total_bytes)}
    print(json.dumps(out, indent=1))
    if save:
        SELECTION_FILE.parent.mkdir(parents=True, exist_ok=True)
        SELECTION_FILE.write_text(json.dumps(selection, indent=1), encoding="utf-8")
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--query", action="store_true", help="CMR probe: candidates, scenes, size plan")
    ap.add_argument("--fetch", action="store_true", help="download selected scenes (MANIFEST provenance)")
    ap.add_argument("--build", action="store_true", help="build the regional parquet + meta")
    ap.add_argument("--check", action="store_true", help="validate the table + raw spot checks")
    args = ap.parse_args(argv)
    if args.query:
        query()
    if args.fetch:
        if not SELECTION_FILE.exists():
            raise SystemExit("no selection file; run --query first")
        selection = json.loads(SELECTION_FILE.read_text(encoding="utf-8"))
        wanted = [s for scenes in selection.values() for s in scenes]
        fetch_scenes(wanted)
    if args.build:
        report = build()
        print(json.dumps({"built": report["rows"],
                          "blocked": [b["code"] for b in report["meta"]["blocks"]]}))
    if args.check:
        report = check()
        return 0 if report["status"] in ("ok", "blocked") else 1
    if not any(vars(args).values()):
        ap.error("nothing to do: pass --query / --fetch / --build / --check")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
