"""#203: readable place labels per H3 res-4 cell (country, first-level region,
nearest populated place), from Natural Earth 1:10m (public domain).

Output: data/snapshots/_derived/place-names-r4.parquet (+ .meta.json), one row
per master cell (cells-r4.parquet key order), with:
  place_country      Natural Earth admin-0 NAME of the polygon containing the cell centre
  place_country_a3   its ADM0_A3 code
  place_admin1       admin-1 `name` of the polygon containing the cell centre
  place_nearest      `name` of the nearest Natural Earth populated place within 50 km
  place_nearest_km   great-circle distance from the cell centre to that place [km]
  missing_reason     JSON: column -> short code, for exactly the null columns

These are LABELS, not traits or measurements. The UI must word them as
"cell centre is in X" (or "X km from Y"), never as an exact site. Natural
Earth draws de facto, cartographic boundaries; they are not legal statements.

Rules (also written into the meta):
  - Containment is tested on the cell centre only (lat/lon from cells-r4),
    with the even-odd rule over every ring of a record, so holes and
    multi-part polygons are handled. Points exactly on a boundary are
    whichever side the ray test puts them; no snapping, no buffering.
  - A centre inside no polygon stays null with a reason (sea, ice shelf, or
    a coastline the 1:10m polygons don't reach). A centre inside more than
    one polygon of the same layer stays null with a reason; it is never
    resolved by picking one.
  - Nearest place: haversine on a sphere of R = 6371.0088 km (mean Earth
    radius); kept only within 50 km, else null with a reason.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq
import shapefile

from .snapshots import REPO, SNAP, sha256

DERIVED = SNAP / "_derived"
DATASET = "natural-earth-10m-cultural"
FILES = {
    "admin0": "ne_10m_admin_0_countries.zip",
    "admin1": "ne_10m_admin_1_states_provinces.zip",
    "places": "ne_10m_populated_places_simple.zip",
}
EARTH_R_KM = 6371.0088
NEAREST_MAX_KM = 50.0
COLUMNS = ["place_country", "place_country_a3", "place_admin1", "place_nearest", "place_nearest_km"]


# ---- geometry -----------------------------------------------------------------
def rings_of(shape) -> list[np.ndarray]:
    """Split a shapefile polygon record into its rings, each an (N, 2) lon/lat array."""
    pts = np.asarray(shape.points, dtype=np.float64)
    starts = list(shape.parts) + [len(pts)]
    return [pts[a:b] for a, b in zip(starts, starts[1:]) if b - a >= 3]


def inside_rings(lon: np.ndarray, lat: np.ndarray, rings: list[np.ndarray], chunk: int = 1024) -> np.ndarray:
    """Even-odd point-in-polygon over all rings of one record (holes and parts included).

    Crossing parity is additive over rings, so each ring is tested on its own,
    only for points inside that ring's bounding box (a point outside a ring's
    box never crosses it an odd number of times). Points and edges are both
    chunked so memory stays bounded for continent-sized polygons.
    """
    inside = np.zeros(lon.shape, dtype=bool)
    if lon.size == 0:
        return inside
    for ring in rings:
        if not np.array_equal(ring[0], ring[-1]):  # close the ring if the file didn't
            ring = np.vstack([ring, ring[:1]])
        rx, ry = ring[:, 0], ring[:, 1]
        sel = np.nonzero((lon >= rx.min()) & (lon <= rx.max()) & (lat >= ry.min()) & (lat <= ry.max()))[0]
        if sel.size == 0:
            continue
        x0, y0, x1, y1 = rx[:-1], ry[:-1], rx[1:], ry[1:]
        for p in range(0, sel.size, chunk):
            idx = sel[p:p + chunk]
            px, py = lon[idx][:, None], lat[idx][:, None]
            odd = np.zeros(idx.size, dtype=bool)
            for s in range(0, x0.size, chunk):
                a0, b0, a1, b1 = x0[s:s + chunk], y0[s:s + chunk], x1[s:s + chunk], y1[s:s + chunk]
                straddle = (b0 > py) != (b1 > py)
                with np.errstate(divide="ignore", invalid="ignore"):
                    xcross = (a1 - a0) * (py - b0) / (b1 - b0) + a0
                odd ^= (np.count_nonzero(straddle & (px < xcross), axis=1) % 2 == 1)
            inside[idx] ^= odd
    return inside


def locate(lon: np.ndarray, lat: np.ndarray, polygons: list[tuple[tuple[float, float, float, float], list[np.ndarray]]]
           ) -> tuple[np.ndarray, np.ndarray]:
    """Index of the containing polygon per point (-1 none) and the number of containing polygons."""
    idx = np.full(lon.shape, -1, dtype=np.int64)
    count = np.zeros(lon.shape, dtype=np.int64)
    for k, (bbox, rings) in enumerate(polygons):
        xmin, ymin, xmax, ymax = bbox
        cand = np.nonzero((lon >= xmin) & (lon <= xmax) & (lat >= ymin) & (lat <= ymax))[0]
        if cand.size == 0:
            continue
        hit = cand[inside_rings(lon[cand], lat[cand], rings)]
        count[hit] += 1
        idx[hit] = np.where(idx[hit] == -1, k, idx[hit])
    return idx, count


def nearest(lat: np.ndarray, lon: np.ndarray, plat: np.ndarray, plon: np.ndarray, chunk: int = 2048
            ) -> tuple[np.ndarray, np.ndarray]:
    """Nearest place index and great-circle distance [km] for every point (haversine)."""
    best_i = np.full(lat.shape, -1, dtype=np.int64)
    best_d = np.full(lat.shape, np.inf)
    if plat.size == 0:
        return best_i, best_d
    p1, l1 = np.radians(plat)[None, :], np.radians(plon)[None, :]
    for s in range(0, lat.size, chunk):
        p0, l0 = np.radians(lat[s:s + chunk])[:, None], np.radians(lon[s:s + chunk])[:, None]
        a = np.sin((p1 - p0) / 2) ** 2 + np.cos(p0) * np.cos(p1) * np.sin((l1 - l0) / 2) ** 2
        d = 2 * EARTH_R_KM * np.arcsin(np.sqrt(np.clip(a, 0.0, 1.0)))
        j = np.argmin(d, axis=1)
        best_i[s:s + chunk] = j
        best_d[s:s + chunk] = d[np.arange(d.shape[0]), j]
    return best_i, best_d


# ---- table --------------------------------------------------------------------
def label_cells(lat: np.ndarray, lon: np.ndarray, admin0: list[dict], admin1: list[dict], places: list[dict]) -> dict:
    """Pure core: arrays in, column lists out. admin*: {'bbox','rings','name',...}; places: {'name','lat','lon'}."""
    n = lat.size
    i0, c0 = locate(lon, lat, [(p["bbox"], p["rings"]) for p in admin0])
    i1, c1 = locate(lon, lat, [(p["bbox"], p["rings"]) for p in admin1])
    pi, pd = nearest(lat, lon, np.array([p["lat"] for p in places], dtype=np.float64),
                     np.array([p["lon"] for p in places], dtype=np.float64))
    out = {c: [None] * n for c in COLUMNS}
    reasons: list[dict] = [{} for _ in range(n)]
    def blank(v) -> bool:
        return v is None or (isinstance(v, str) and (not v.strip() or v.strip() == "-99"))

    for r in range(n):
        if c0[r] == 1:
            for col, field in (("place_country", "name"), ("place_country_a3", "a3")):
                v = admin0[i0[r]].get(field)
                if blank(v):
                    reasons[r][col] = "admin0-polygon-has-no-value"
                else:
                    out[col][r] = v.strip()
        else:
            code = "centre-outside-admin0-polygons" if c0[r] == 0 else "centre-in-several-admin0-polygons"
            reasons[r]["place_country"] = reasons[r]["place_country_a3"] = code
        if c1[r] == 1:
            v = admin1[i1[r]].get("name")
            if blank(v):
                reasons[r]["place_admin1"] = "admin1-polygon-has-no-name"
            else:
                out["place_admin1"][r] = v.strip()
        else:
            reasons[r]["place_admin1"] = "centre-outside-admin1-polygons" if c1[r] == 0 else "centre-in-several-admin1-polygons"
        if pi[r] >= 0 and pd[r] <= NEAREST_MAX_KM and not blank(places[pi[r]]["name"]):
            out["place_nearest"][r] = places[pi[r]]["name"].strip()
            out["place_nearest_km"][r] = round(float(pd[r]), 3)
        else:
            reasons[r]["place_nearest"] = reasons[r]["place_nearest_km"] = "no-populated-place-within-50km"
    out["missing_reason"] = [json.dumps(x, sort_keys=True, separators=(",", ":")) for x in reasons]
    out["__counts"] = {
        "admin0Contained": int((c0 == 1).sum()), "admin0None": int((c0 == 0).sum()), "admin0Several": int((c0 > 1).sum()),
        "admin1Contained": int((c1 == 1).sum()), "admin1None": int((c1 == 0).sum()), "admin1Several": int((c1 > 1).sum()),
        "nearestWithin50km": int(((pi >= 0) & (pd <= NEAREST_MAX_KM)).sum()),
    }
    return out


def _polygons(path: Path, name_field: str, extra: dict[str, str]) -> list[dict]:
    r = shapefile.Reader(str(path), encoding="utf-8")
    out = []
    for sr in r.iterShapeRecords():
        rings = rings_of(sr.shape)
        if not rings:
            continue
        rec = sr.record.as_dict()
        item = {"bbox": tuple(sr.shape.bbox), "rings": rings, "name": (rec.get(name_field) or "").strip() or None}
        item.update({k: rec.get(v) for k, v in extra.items()})
        out.append(item)
    return out


def _places(path: Path) -> list[dict]:
    r = shapefile.Reader(str(path), encoding="utf-8")
    out = []
    for rec in r.iterRecords():
        d = rec.as_dict()
        if d.get("name") and d.get("latitude") is not None and d.get("longitude") is not None:
            out.append({"name": d["name"].strip(), "lat": float(d["latitude"]), "lon": float(d["longitude"])})
    return out


def build(cells_path: Path | None = None, out_dir: Path | None = None) -> dict:
    cells_path = Path(cells_path or DERIVED / "cells-r4.parquet")
    out_dir = Path(out_dir or DERIVED)
    src = {k: SNAP / DATASET / f for k, f in FILES.items()}
    for k, p in src.items():
        if not p.exists():
            raise SystemExit(f"{p} missing: run snapshots.fetch('{DATASET}', ...) first (see the catalog row)")
    cells = pq.read_table(cells_path, columns=["h3", "lat", "lon"])
    lat = cells["lat"].to_numpy().astype(np.float64)
    lon = cells["lon"].to_numpy().astype(np.float64)
    admin0 = _polygons(src["admin0"], "NAME", {"a3": "ADM0_A3"})
    admin1 = _polygons(src["admin1"], "name", {})
    places = _places(src["places"])
    res = label_cells(lat, lon, admin0, admin1, places)
    counts = res.pop("__counts")
    table = pa.table({
        "h3": cells["h3"],
        "place_country": pa.array(res["place_country"], pa.string()),
        "place_country_a3": pa.array(res["place_country_a3"], pa.string()),
        "place_admin1": pa.array(res["place_admin1"], pa.string()),
        "place_nearest": pa.array(res["place_nearest"], pa.string()),
        "place_nearest_km": pa.array(res["place_nearest_km"], pa.float64()),
        "missing_reason": pa.array(res["missing_reason"], pa.string()),
    })
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / "place-names-r4.parquet"
    pq.write_table(table, out, compression="zstd")
    meta = {
        "table": "place-names-r4", "workOrder": 203, "rows": table.num_rows,
        "builtAt": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "cells": {"path": str(cells_path.relative_to(REPO)) if cells_path.is_relative_to(REPO) else str(cells_path),
                  "sha256": sha256(cells_path)},
        "inputs": {k: {"path": str(p.relative_to(REPO)), "sha256": sha256(p)} for k, p in src.items()},
        "license": "public-domain (Natural Earth terms of use, checked 2026-11-15)",
        "counts": {**counts, "admin0Polygons": len(admin0), "admin1Polygons": len(admin1), "places": len(places)},
        "units": {"place_nearest_km": "km"},
        "labelRule": "Labels, not traits: show as 'cell centre is in <admin1>, <country>' and '<km> km from <place>'. Never an exact site.",
        "cleanRules": {
            "ne-centre-in-polygon": "cell centre (cells-r4 lat/lon) tested against every ring of each Natural Earth polygon, even-odd rule; no snapping or buffering",
            "ne-single-polygon-only": "a centre in zero or several polygons of a layer stays null with a reason; never resolved by picking one",
            "ne-nearest-50km": f"haversine on R = {EARTH_R_KM} km; nearest populated place kept only within {NEAREST_MAX_KM:.0f} km",
        },
        "caveats": ["Natural Earth boundaries and names are cartographic (de facto), not legal statements.",
                    "1:10m polygons miss small islands and narrow coasts; those cells are null with a reason."],
        "output": {"path": str(out.relative_to(REPO)) if out.is_relative_to(REPO) else str(out), "sha256": sha256(out)},
    }
    (out_dir / "place-names-r4.meta.json").write_text(json.dumps(meta, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return meta


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    ap.add_argument("--cells", type=Path, default=None, help="master cells parquet with h3, lat, lon (default _derived/cells-r4.parquet)")
    ap.add_argument("--out", type=Path, default=None, help="output folder (default _derived/)")
    args = ap.parse_args(argv)
    meta = build(args.cells, args.out)
    print(json.dumps({"rows": meta["rows"], "counts": meta["counts"], "output": meta["output"]}, indent=1, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
