"""#202 (partial): logistics facts per H3 res-4 cell from public-domain sources.

Output: data/snapshots/_derived/logistics-facts-r4.parquet (+ .meta.json), one
row per master cell (cells-r4 key order):
  town_nearest       name of the nearest Natural Earth populated place (any distance)
  town_nearest_km    great-circle distance from the cell centre to it [km]
  road_nearest_km    distance from the cell centre to the nearest Natural Earth
                     1:10m road segment [km]; ferries and tracks excluded
  missing_reason     JSON: column -> short code, for exactly the null columns

Scope and honesty (licences checked 2026-11-15, see the catalog rows):
  - Natural Earth is public domain. Its 1:10m roads are a generalized major-road
    network, NOT a paved/unpaved classification and not every road; a large
    distance means "far from a mapped major road", never "no road".
  - Its populated places list towns and cities above a size threshold, so the
    nearest one is a named settlement, not necessarily the nearest village.
  - Hotels, hospitals, power lines and cell towers are NOT built here. Their
    open sources are share-alike (OSM: ODbL; OpenCelliD: CC BY-SA 4.0) and are
    blocked pending the owner's licence decision (issue #202); Gridfinder's
    modelled grid (CC BY 4.0) needs a 724 MB download not yet approved.

Distances: the cell centre (cells-r4 lat/lon) to the nearest road segment on a
local equirectangular projection about the centre (sphere R = 6371.0088 km),
exact point-to-segment within that projection. Segments are indexed in 1-degree
buckets; the search grows ring by ring and stops once no unvisited bucket can
be closer than the best distance found, up to MAX_RING degrees, beyond which
the value is null with a reason. Projection error is well under 1% at the
distances this search accepts.
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq
import shapefile

from .place_names import DATASET, EARTH_R_KM, _places, nearest
from .snapshots import REPO, SNAP, sha256

DERIVED = SNAP / "_derived"
ROADS = "ne_10m_roads.zip"
PLACES = "ne_10m_populated_places_simple.zip"
EXCLUDED_ROAD_TYPES = {"Ferry Route", "Ferry, seasonal", "Track"}
MAX_RING = 5  # degrees; about 550 km in latitude
KM_PER_DEG = EARTH_R_KM * math.pi / 180.0
COLUMNS = ["town_nearest", "town_nearest_km", "road_nearest_km"]


def road_segments(path: Path) -> np.ndarray:
    """(N, 4) lon0, lat0, lon1, lat1 for every road segment kept (ferries and tracks dropped)."""
    r = shapefile.Reader(str(path), encoding="utf-8")
    segs = []
    for sr in r.iterShapeRecords():
        rec = sr.record.as_dict()
        if rec.get("featurecla") == "Ferry" or rec.get("type") in EXCLUDED_ROAD_TYPES:
            continue
        pts = np.asarray(sr.shape.points, dtype=np.float64)
        starts = list(sr.shape.parts) + [len(pts)]
        for a, b in zip(starts, starts[1:]):
            if b - a >= 2:
                p = pts[a:b]
                segs.append(np.c_[p[:-1], p[1:]])
    s = np.vstack(segs) if segs else np.zeros((0, 4))
    return s[np.abs(s[:, 2] - s[:, 0]) <= 180.0]  # drop the few antimeridian-spanning segments


class SegmentIndex:
    """1-degree buckets of segment indices (a segment goes in every bucket its bbox touches)."""

    def __init__(self, segs: np.ndarray):
        self.segs = segs
        buckets: dict[tuple[int, int], list[int]] = {}
        lo_lat = np.floor(np.minimum(segs[:, 1], segs[:, 3])).astype(int)
        hi_lat = np.floor(np.maximum(segs[:, 1], segs[:, 3])).astype(int)
        lo_lon = np.floor(np.minimum(segs[:, 0], segs[:, 2])).astype(int)
        hi_lon = np.floor(np.maximum(segs[:, 0], segs[:, 2])).astype(int)
        for i in range(segs.shape[0]):
            for la in range(lo_lat[i], hi_lat[i] + 1):
                for lo in range(lo_lon[i], hi_lon[i] + 1):
                    buckets.setdefault((la, ((lo + 180) % 360) - 180), []).append(i)
        self.buckets = {k: np.asarray(v, dtype=np.int64) for k, v in buckets.items()}

    def ring(self, la0: int, lo0: int, r: int) -> list[np.ndarray]:
        out = []
        for la in range(la0 - r, la0 + r + 1):
            if la < -90 or la > 89:
                continue
            for lo in range(lo0 - r, lo0 + r + 1):
                if max(abs(la - la0), abs(lo - lo0)) != r:
                    continue
                v = self.buckets.get((la, ((lo + 180) % 360) - 180))
                if v is not None:
                    out.append(v)
        return out


def point_segment_km(lat: float, lon: float, segs: np.ndarray) -> np.ndarray:
    """Distance [km] from one point to each segment, on a local equirectangular projection."""
    c = math.cos(math.radians(lat))
    dx0 = ((segs[:, 0] - lon + 180.0) % 360.0 - 180.0) * c
    dx1 = ((segs[:, 2] - lon + 180.0) % 360.0 - 180.0) * c
    dy0 = segs[:, 1] - lat
    dy1 = segs[:, 3] - lat
    ex, ey = dx1 - dx0, dy1 - dy0
    ll = ex * ex + ey * ey
    with np.errstate(divide="ignore", invalid="ignore"):
        t = np.where(ll > 0, -(dx0 * ex + dy0 * ey) / ll, 0.0)
    t = np.clip(t, 0.0, 1.0)
    px, py = dx0 + t * ex, dy0 + t * ey
    return np.hypot(px, py) * KM_PER_DEG


def nearest_road_km(lat: np.ndarray, lon: np.ndarray, index: SegmentIndex, max_ring: int = MAX_RING) -> np.ndarray:
    out = np.full(lat.shape, np.nan)
    for k in range(lat.size):
        la, lo = float(lat[k]), float(lon[k])
        la0, lo0 = math.floor(la), math.floor(lo)
        best = math.inf
        r = 0
        while r <= max_ring:
            parts = index.ring(la0, lo0, r)
            if parts:
                ids = np.unique(np.concatenate(parts))
                best = min(best, float(point_segment_km(la, lo, index.segs[ids]).min()))
            # every bucket in ring r+1 is at least r degrees away in latitude, or r degrees
            # of longitude at the most poleward latitude of that ring
            cos_edge = math.cos(math.radians(min(89.0, abs(la) + r + 1)))
            if math.isfinite(best) and best <= r * KM_PER_DEG * cos_edge:
                break
            r += 1
        if math.isfinite(best) and best <= max_ring * KM_PER_DEG * math.cos(math.radians(min(89.0, abs(la) + max_ring))):
            out[k] = best
    return out


def build(cells_path: Path | None = None, out_dir: Path | None = None) -> dict:
    cells_path = Path(cells_path or DERIVED / "cells-r4.parquet")
    out_dir = Path(out_dir or DERIVED)
    src = {"roads": SNAP / DATASET / ROADS, "places": SNAP / DATASET / PLACES}
    for p in src.values():
        if not p.exists():
            raise SystemExit(f"{p} missing: fetch it first (catalog row {DATASET}, MANIFEST.json)")
    cells = pq.read_table(cells_path, columns=["h3", "lat", "lon"])
    lat = cells["lat"].to_numpy().astype(np.float64)
    lon = cells["lon"].to_numpy().astype(np.float64)
    places = _places(src["places"])
    pi, pd = nearest(lat, lon, np.array([p["lat"] for p in places]), np.array([p["lon"] for p in places]))
    segs = road_segments(src["roads"])
    road = nearest_road_km(lat, lon, SegmentIndex(segs))
    n = lat.size
    town = [places[i]["name"] if i >= 0 else None for i in pi]
    town_km = [round(float(d), 3) if math.isfinite(d) else None for d in pd]
    road_km = [round(float(d), 3) if math.isfinite(d) else None for d in road]
    reasons = []
    for k in range(n):
        r = {}
        if town[k] is None:
            r["town_nearest"] = r["town_nearest_km"] = "no-populated-places-loaded"
        if road_km[k] is None:
            r["road_nearest_km"] = "no-mapped-road-within-search-radius"
        reasons.append(json.dumps(r, sort_keys=True, separators=(",", ":")))
    table = pa.table({"h3": cells["h3"], "town_nearest": pa.array(town, pa.string()),
                      "town_nearest_km": pa.array(town_km, pa.float64()),
                      "road_nearest_km": pa.array(road_km, pa.float64()),
                      "missing_reason": pa.array(reasons, pa.string())})
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / "logistics-facts-r4.parquet"
    pq.write_table(table, out, compression="zstd")
    road_ok = np.isfinite(road)
    meta = {
        "table": "logistics-facts-r4", "workOrder": 202, "rows": n,
        "builtAt": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "cells": {"path": str(cells_path.relative_to(REPO)) if cells_path.is_relative_to(REPO) else str(cells_path), "sha256": sha256(cells_path)},
        "inputs": {k: {"path": str(p.relative_to(REPO)), "sha256": sha256(p)} for k, p in src.items()},
        "license": "public-domain (Natural Earth terms of use, checked 2026-11-15)",
        "counts": {"roadSegments": int(segs.shape[0]), "places": len(places), "roadWithinSearch": int(road_ok.sum()),
                   "roadMissing": int((~road_ok).sum()),
                   "roadKmMedian": round(float(np.median(road[road_ok])), 3) if road_ok.any() else None,
                   "townKmMedian": round(float(np.median(pd)), 3)},
        "units": {"town_nearest_km": "km", "road_nearest_km": "km"},
        "cleanRules": {
            "ne-roads-major-network": "Natural Earth 1:10m roads, featurecla Road; ferry routes and tracks excluded; a generalized major-road network, not a paved-road map",
            "local-equirectangular-segment-distance": f"cell centre to nearest segment on a local equirectangular projection, R = {EARTH_R_KM} km; search up to {MAX_RING} degrees, else null with a reason",
            "ne-nearest-place-any-distance": "nearest Natural Earth populated place by haversine, no distance cap",
        },
        "notBuilt": {
            "hotel_nearest_km, hospital_nearest_km": "OpenStreetMap (ODbL share-alike): blocked pending owner licence decision (#202, #7)",
            "power_line_nearest_km": "Gridfinder modelled grid (CC BY 4.0, 724 MB): download not approved yet; its OSM-derived lines would also carry ODbL",
            "cell_towers_seen": "OpenCelliD (CC BY-SA 4.0, needs an account token): blocked pending owner licence decision and a person-created token",
        },
        "output": {"path": str(out.relative_to(REPO)) if out.is_relative_to(REPO) else str(out), "sha256": sha256(out)},
    }
    (out_dir / "logistics-facts-r4.meta.json").write_text(json.dumps(meta, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return meta


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    ap.add_argument("--cells", type=Path, default=None)
    ap.add_argument("--out", type=Path, default=None)
    a = ap.parse_args(argv)
    meta = build(a.cells, a.out)
    print(json.dumps({"rows": meta["rows"], "counts": meta["counts"], "output": meta["output"]}, indent=1, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
