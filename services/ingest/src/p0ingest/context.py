"""Build the L2 context table from licensed snapshots and the frozen L1 cell list."""
from __future__ import annotations

import csv
import json
import math
import time
import zipfile
from datetime import datetime, timezone
from pathlib import Path

import h3
import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq
import rasterio
from rasterio.features import rasterize
from rasterio.windows import Window

from .grid import DERIVED
from .snapshots import REPO, SNAP, catalog_row, fetch, sha256, load_manifest

ACCESS_URL = ("https://data.malariaatlas.org/geoserver/ows?service=CSW&version=2.0.1&request=DirectDownload&"
              "ResourceId=Explorer:2015_accessibility_to_cities_v1.0")
AIRPORTS_URL = "https://davidmegginson.github.io/ourairports-data/airports.csv"
RUNWAYS_URL = "https://davidmegginson.github.io/ourairports-data/runways.csv"
EONET_URL = ("https://eonet.gsfc.nasa.gov/api/v3/events?status=all&start=2015-01-01&end=2024-12-31"
             "&limit=100000")
EONET_RADIUS_KM = 50.0
EONET_CATEGORIES = ("wildfires", "volcanoes", "severeStorms", "floods", "landslides", "dustHaze",
                    "earthquakes", "snow", "tempExtremes", "drought")
SPOTS = {
    "Death Valley": (36.24, -116.82),
    "Haughton crater (Devon Island)": (75.37, -89.68),
    "Atacama": (-23.86, -69.19),
    "McMurdo Dry Valleys": (-77.5, 161.0),
    "Mauna Loa": (19.475, -155.608),
}
EARTH_KM = 6371.0088
PAVED_SURFACES = {"ASP", "CON", "ASPHALT", "CONCRETE", "BITUMINOUS", "PAVED", "ASPH", "CONC"}


def _find_l1() -> Path:
    candidates = [DERIVED / "cells-r4.parquet",
                  Path("/home/drew/cosmic-consultants/data/snapshots/_derived/cells-r4.parquet")]
    for path in candidates:
        if path.is_file():
            return path
    raise FileNotFoundError("cells-r4.parquet not found locally; restore it from the Drive mirror first")


def _download_inputs() -> dict[str, Path]:
    # Read licence status before calling the snapshot helper. Unresolved or restricted
    # sources are intentionally not fetched or used in the output table.
    access = catalog_row("travel-time-to-cities-2015")
    airports = catalog_row("ourairports")
    if not access.get("license", {}).get("verified") or access["license"].get("id") != "cc-by-3.0":
        raise RuntimeError("travel-time source licence is not verified as CC BY 3.0")
    if not airports.get("license", {}).get("verified") or airports["license"].get("id") != "public-domain":
        raise RuntimeError("OurAirports licence is not verified as public domain")
    return {
        "access": fetch("travel-time-to-cities-2015", ACCESS_URL, "2015_accessibility_to_cities_v1.0.zip"),
        "airports": fetch("ourairports", AIRPORTS_URL, "airports.csv"),
        "runways": fetch("ourairports", RUNWAYS_URL, "runways.csv"),
        "eonet": fetch("eonet-v3-events", EONET_URL, "events-2015-2024.json"),
    }


def _access_tif(path: Path) -> str:
    with zipfile.ZipFile(path) as zf:
        names = [n for n in zf.namelist() if n.lower().endswith((".tif", ".tiff"))]
    if not names:
        raise RuntimeError(f"no GeoTIFF in travel-time archive {path}")
    return f"/vsizip/{path.resolve()}/{names[0]}"


def _cell_shapes(hexes: list[str]):
    """Yield H3 polygons in lon/lat order, splitting dateline cells by shifted copies."""
    shapes = []
    for idx, cell in enumerate(hexes):
        center_lat, center_lon = h3.cell_to_latlng(cell)
        ring = []
        for lat, lon in h3.cell_to_boundary(cell):
            lon = center_lon + ((lon - center_lon + 180.0) % 360.0 - 180.0)
            ring.append((lon, lat))
        ring.append(ring[0])
        xs = [p[0] for p in ring]
        shifts = (0, 360) if min(xs) < -180 else ((0, -360) if max(xs) > 180 else (0,))
        min_lat, max_lat = min(p[1] for p in ring), max(p[1] for p in ring)
        for shift in shifts:
            coords = [(x + shift, y) for x, y in ring]
            shapes.append(({"type": "Polygon", "coordinates": [coords]}, idx, min_lat, max_lat))
    return shapes


def _access_stats(path: Path, hexes: list[str]) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    n = len(hexes)
    med = np.full(n, np.nan, dtype=np.float64)
    p10 = np.full(n, np.nan, dtype=np.float64)
    null_rows = np.ones(n, dtype=bool)
    groups: dict[int, list[np.ndarray]] = {}
    uri = _access_tif(path)
    shapes = _cell_shapes(hexes)
    with rasterio.open(uri) as src:
        if src.crs is None or src.crs.to_epsg() != 4326:
            raise RuntimeError(f"expected EPSG:4326 travel raster, got {src.crs}")
        # Work in bounded stripes. The full global raster is never decompressed into memory.
        stripe = 256
        for row in range(0, src.height, stripe):
            height = min(stripe, src.height - row)
            window = Window(0, row, src.width, height)
            transform = src.window_transform(window)
            stripe_top = transform.f
            stripe_bottom = transform.f + transform.e * height
            candidates = ((geom, idx) for geom, idx, lo, hi in shapes
                          if hi >= stripe_bottom and lo <= stripe_top)
            ids = rasterize(candidates, out_shape=(height, src.width), transform=transform,
                            fill=-1, dtype="int32", all_touched=False)
            values = src.read(1, window=window, masked=False)
            good = ids >= 0
            if src.nodata is not None:
                good &= values != src.nodata
            good &= np.isfinite(values)
            valid_ids = ids[good]
            valid_values = values[good]
            if valid_ids.size:
                order = np.argsort(valid_ids)
                sorted_ids = valid_ids[order]
                sorted_values = valid_values[order]
                starts = np.r_[0, np.flatnonzero(sorted_ids[1:] != sorted_ids[:-1]) + 1,
                               len(sorted_ids)]
                for a, b in zip(starts[:-1], starts[1:]):
                    groups.setdefault(int(sorted_ids[a]), []).append(sorted_values[a:b].copy())
    for idx, chunks in groups.items():
        vals = np.concatenate(chunks)
        # The source's raster unit is minutes. Keep exact within-cell quantiles.
        med[idx] = float(np.median(vals))
        p10[idx] = float(np.percentile(vals, 10))
        null_rows[idx] = False
    return med, p10, null_rows


def _read_airports(airports_path: Path, runways_path: Path) -> tuple[np.ndarray, np.ndarray]:
    paved_ids: set[str] = set()
    with runways_path.open(encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            surface = (row.get("surface") or "").strip().upper()
            paved = surface in PAVED_SURFACES or surface.startswith(("ASPH", "CONC", "BITUMINOUS"))
            if (paved and row.get("closed", "0").strip() != "1"
                    and (row.get("airport_ident") or "").strip()):
                paved_ids.add(row["airport_ident"].strip())
    lats, lons = [], []
    with airports_path.open(encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            if row.get("ident") not in paved_ids or row.get("type") not in {
                    "small_airport", "medium_airport", "large_airport"}:
                continue
            try:
                lat, lon = float(row["latitude_deg"]), float(row["longitude_deg"])
            except (TypeError, ValueError, KeyError):
                continue
            if math.isfinite(lat) and math.isfinite(lon):
                lats.append(lat); lons.append(lon)
    if not lats:
        raise RuntimeError("no airport with a paved runway and coordinates found")
    return np.asarray(lats), np.asarray(lons)


def _unit_xyz(lat: np.ndarray, lon: np.ndarray) -> np.ndarray:
    la, lo = np.radians(lat), np.radians(lon)
    c = np.cos(la)
    return np.column_stack((c * np.cos(lo), c * np.sin(lo), np.sin(la)))


def _nearest_airport_km(lat: np.ndarray, lon: np.ndarray, airport_lat: np.ndarray,
                        airport_lon: np.ndarray) -> np.ndarray:
    cells_xyz, airport_xyz = _unit_xyz(lat, lon), _unit_xyz(airport_lat, airport_lon)
    try:
        from scipy.spatial import cKDTree
        chord, _ = cKDTree(airport_xyz).query(cells_xyz, k=1, workers=-1)
    except ImportError:
        # Keep bounded memory if scipy is not available in the minimal ingest environment.
        chord = np.empty(len(lat), dtype=np.float64)
        for start in range(0, len(lat), 256):
            dots = cells_xyz[start:start + 256] @ airport_xyz.T
            chord[start:start + len(dots)] = np.sqrt(np.maximum(0.0, 2.0 - 2.0 * dots.max(axis=1)))
    return 2.0 * EARTH_KM * np.arcsin(np.minimum(1.0, chord / 2.0))


def _eonet_points(geometry: list[dict]) -> list[tuple[float, float]]:
    """(lat, lon) of every geometry of an event. Points as given; polygons by the
    mean of their outer-ring vertices (EONET polygons are small event outlines)."""
    pts = []
    for g in geometry:
        c = g.get("coordinates")
        if g.get("type") == "Point" and c:
            pts.append((float(c[1]), float(c[0])))
        elif g.get("type") == "Polygon" and c and c[0]:
            ring = c[0][:-1] if len(c[0]) > 1 and c[0][0] == c[0][-1] else c[0]
            pts.append((float(np.mean([v[1] for v in ring])), float(np.mean([v[0] for v in ring]))))
    return pts


def _eonet(path: Path, hexes: list[str], lat: np.ndarray, lon: np.ndarray):
    """Per cell and category: count of EONET events with any geometry within
    EONET_RADIUS_KM of the cell centre (an r4 cell, edge ~22 km, lies inside that
    circle), and the 0/1 string of the calendar months those events started in.
    Also returns one row per (cell, event) so the planner can name the events."""
    events = json.loads(path.read_text(encoding="utf-8"))["events"]
    index = {cell: i for i, cell in enumerate(hexes)}
    n = len(lat)
    counts = {c: np.zeros(n, dtype=np.int32) for c in EONET_CATEGORIES}
    months = {c: np.zeros((n, 12), dtype=bool) for c in EONET_CATEGORIES}
    links: dict[str, list] = {k: [] for k in ("cell", "event_id", "category", "title", "start_date", "source_url")}
    stats = {"events": len(events), "eventsKeptCategory": 0, "eventsNoGeometry": 0, "eventsNearLand": 0}
    for ev in events:
        cats = [c["id"] for c in ev.get("categories", []) if c["id"] in EONET_CATEGORIES]
        if not cats:
            continue
        stats["eventsKeptCategory"] += 1
        pts = _eonet_points(ev.get("geometry", []))
        dates = sorted(g["date"] for g in ev.get("geometry", []) if g.get("date"))
        if not pts or not dates:
            stats["eventsNoGeometry"] += 1
            continue
        hit = set()
        for plat, plon in pts:
            # r4 cell centres are ~40 km apart, so k=3 rings reach past 50 km.
            for cand in h3.grid_disk(h3.latlng_to_cell(plat, plon, 4), 3):
                i = index.get(cand)
                if i is not None and i not in hit and _haversine_km(plat, plon, lat[i], lon[i]) <= EONET_RADIUS_KM:
                    hit.add(i)
        if not hit:
            continue
        stats["eventsNearLand"] += 1
        idx = np.fromiter(sorted(hit), dtype=np.int64)
        start = dates[0][:10]
        mo = int(start[5:7]) - 1
        src = next((s.get("url") for s in ev.get("sources", []) if s.get("url")), None)
        for c in cats:
            counts[c][idx] += 1
            months[c][idx, mo] = True
            for i in idx:
                links["cell"].append(int(i)); links["event_id"].append(ev["id"]); links["category"].append(c)
                links["title"].append(ev.get("title")); links["start_date"].append(start); links["source_url"].append(src)
    month_str = {c: ["".join("1" if b else "0" for b in row) for row in months[c]] for c in EONET_CATEGORIES}
    return counts, month_str, links, stats


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = p2 - p1
    dl = math.radians((lon2 - lon1 + 180.0) % 360.0 - 180.0)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * EARTH_KM * math.asin(math.sqrt(min(1.0, a)))


def build() -> dict:
    started = time.time()
    DERIVED.mkdir(parents=True, exist_ok=True)
    l1_path = _find_l1()
    l1_hash = sha256(l1_path)
    base = pq.read_table(l1_path, columns=["h3"])
    hexes = base.column("h3").to_pylist()
    if len(hexes) != 91800:
        raise RuntimeError(f"expected 91,800 L1 land cells, got {len(hexes)}")
    centers = [h3.cell_to_latlng(cell) for cell in hexes]
    lat = np.fromiter((p[0] for p in centers), dtype=np.float64, count=len(hexes))
    lon = np.fromiter((p[1] for p in centers), dtype=np.float64, count=len(hexes))

    # Read the source rows before any source is fetched.
    eonet_license = catalog_row("eonet-v3-events")["license"]
    wdpa_license = catalog_row("wdpa-protected-areas")["license"]
    if eonet_license.get("id") != "nasa-esds-open-data-eonet-disclaimer" or not eonet_license.get("verified"):
        raise RuntimeError("EONET licence row is not the owner-approved terms (ADR-0006); review first")
    if wdpa_license.get("id") != "wdpa-terms-noncommercial":
        raise RuntimeError("WDPA licence status changed; review before using this module")

    files = _download_inputs()
    manifest = load_manifest()["entries"]
    inputs = {"cells-r4": {"localPath": "data/snapshots/_derived/cells-r4.parquet",
                           "sha256": l1_hash}}
    for name, path in files.items():
        entry = next(e for e in manifest if e["localPath"] == str(path.relative_to(REPO)))
        inputs[name] = {"localPath": entry["localPath"], "sha256": entry["sha256"]}

    access_median, access_p10, access_missing = _access_stats(files["access"], hexes)
    apt_lat, apt_lon = _read_airports(files["airports"], files["runways"])
    airport_km = _nearest_airport_km(lat, lon, apt_lat, apt_lon)
    eo_counts, eo_months, eo_links, eo_stats = _eonet(files["eonet"], hexes, lat, lon)

    n = len(hexes)
    output: dict[str, pa.Array] = {
        "h3": pa.array(hexes),
        "access_min_median": pa.array(access_median, from_pandas=True),
        "access_min_p10": pa.array(access_p10, from_pandas=True),
        "airport_km": pa.array(airport_km, from_pandas=True),
        "protected_pct": pa.nulls(n, pa.float64()),
    }
    for category in EONET_CATEGORIES:
        output[f"eonet_{category}_events"] = pa.array(eo_counts[category], type=pa.int32())
        output[f"eonet_{category}_months"] = pa.array(eo_months[category], type=pa.string())

    missing_rows = []
    for i in range(n):
        missing = {"protected_pct": "licence-restricted"}
        if access_missing[i]:
            missing["access_min_median"] = "no-access-pixels"
            missing["access_min_p10"] = "no-access-pixels"
        missing_rows.append(json.dumps(missing, sort_keys=True, separators=(",", ":")))
    output["missing_reason"] = pa.array(missing_rows, type=pa.string())
    table = pa.table(output)

    out_path = DERIVED / "context-r4.parquet"
    meta_path = DERIVED / "context-r4.meta.json"
    metadata = {
        "generatedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "h3Res": 4, "cells": n,
        "inputs": inputs,
        "licences": {
            "travel-time-to-cities-2015": "CC BY 3.0; MAP live policy checked 2026-11-14",
            "ourairports": "Public Domain; live source page checked 2026-11-14 (site TLS certificate expired; fetched with curl -k)",
            "wdpa-protected-areas": "restricted; no data fetched or used",
            "eonet-v3-events": "NASA ESDS full and open data policy plus the EONET disclaimer (visualization and general information only; extents approximate); owner-approved 2026-11-14, ADR-0006",
        },
        "computed": {
            "access_min_median": "median of valid 2015 travel-time raster pixel values whose pixel centres fall inside each H3 r4 polygon; units minutes",
            "access_min_p10": "10th percentile of the same valid raster pixels; units minutes",
            "airport_km": "great-circle distance from H3 cell centre to nearest small/medium/large OurAirports airport having at least one non-closed runway with asphalt, concrete or bituminous surface code; Earth radius 6371.0088 km. Ice, snow and gravel runways are excluded, so Antarctic cells read far (McMurdo ~3490 km)",
            "protected_pct": "withheld because Protected Planet terms restrict redistribution of derived material",
            "eonet_<category>_events": f"EONET v3 events 2015-2024 of that category with any geometry within {EONET_RADIUS_KM:.0f} km of the H3 cell centre (polygons by mean vertex); count of events, not a rate: EONET is a curated list whose size varies by year",
            "eonet_<category>_months": "12-character 0/1 string, January first: calendar months in which those events started (first geometry date, UTC); all zeros means none recorded in EONET",
            "eonet-events-r4": "one row per (cell, event, category) behind the counts, with title, start date and first source URL, so the planner can name the events",
        },
        "missing": {
            "protected_pct": "licence-restricted for every cell",
            "access_min_*": "no-access-pixels outside raster coverage or where source pixels are nodata",
        },
    }
    table = table.replace_schema_metadata({"cosmic-consultants": json.dumps(metadata, sort_keys=True)})
    pq.write_table(table, out_path, compression="zstd")
    ev_path = DERIVED / "eonet-events-r4.parquet"
    ev_table = pa.table({
        "h3": pa.array([hexes[i] for i in eo_links["cell"]], type=pa.string()),
        **{k: pa.array(v, type=pa.string()) for k, v in eo_links.items() if k != "cell"},
    })
    pq.write_table(ev_table, ev_path, compression="zstd")
    metadata["eonetEvents"] = {"path": str(ev_path.relative_to(REPO)), "sha256": sha256(ev_path),
                               "rows": ev_table.num_rows, **eo_stats}
    metadata.update({
        "path": str(out_path.relative_to(REPO)),
        "sha256": sha256(out_path),
        "bytes": out_path.stat().st_size,
        "runtime_s": round(time.time() - started, 1),
        "nullRate": {name: round(table[name].null_count / n, 6) for name in table.column_names},
        "rowCount": table.num_rows,
        "airportCountUsed": len(apt_lat),
    })
    meta_path.write_text(json.dumps(metadata, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return metadata


if __name__ == "__main__":
    result = build()
    print(json.dumps({k: result[k] for k in ("path", "rowCount", "sha256", "bytes", "runtime_s",
                                               "nullRate", "inputs", "airportCountUsed", "eonetEvents")}, indent=2))
    table = pq.read_table(DERIVED / "context-r4.parquet")
    ix = {h: i for i, h in enumerate(table["h3"].to_pylist())}
    for name, (spot_lat, spot_lon) in SPOTS.items():
        cell = h3.latlng_to_cell(spot_lat, spot_lon, 4)
        row = ix.get(cell)
        if row is None:
            nearest = min(range(len(table)), key=lambda j: _haversine_km(spot_lat, spot_lon, *h3.cell_to_latlng(table["h3"][j].as_py())))
            row = nearest; cell = table["h3"][row].as_py()
        clat, clon = h3.cell_to_latlng(cell)
        print(json.dumps({"spot": name, "lat": clat, "lon": clon, "h3": cell,
                          **{c: table[c][row].as_py() for c in table.column_names if c != "missing_reason"},
                          "missing_reason": table["missing_reason"][row].as_py()}, sort_keys=True))
