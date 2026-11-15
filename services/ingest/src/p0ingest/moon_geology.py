"""Prepare source-native Moon geology context data (#98).

- unified-geologic-map-moon (USGS 2020 1:5M, CC0): map-unit table + polygon
  geometry (WKB) straight out of the GeoUnits shapefile inside the published
  GIS zip. Coordinates are converted with the exact linear inverse of the
  source Moon2000 equidistant-cylindrical (central meridian 0) projection to
  lon/lat degrees on the source Moon_2000 sphere (radius 1,737,400 m);
  lon in [-180, 180) east-positive. No resampling, no H3, no reprojection
  beyond that closed-form inverse.
- lroc-pits-atlas (LROC Catalog of Lunar Pits v1, March 2021; the catalogue
  ships only as PDF/HTML, never as a file): per-pit fields parsed page by
  page from the PDF, verbatim source strings kept beside parsed numbers.
- robbins-moon-craters + lroc-nac-boulders-watkins: licence unresolved, so
  their values are NOT used; gap reports with probe evidence instead.
Run: python -m p0ingest.moon_geology fetch|build|check
"""
from __future__ import annotations

import argparse
import csv
import io
import json
import re
import struct
import zipfile
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import polars as pl
import pyarrow.parquet as pq
import shapefile
from pypdf import PdfReader

from .snapshots import REPO, SNAP, fetch, load_manifest, sha256

OUT = SNAP / "_derived" / "planetary"

GEO_ZIP = ("unified-geologic-map-moon",
           "https://asc-astropedia.s3.us-west-2.amazonaws.com/Moon/Geology/Unified_Geologic_Map_of_the_Moon_GIS_v2.zip")
PITS_PDF = ("lroc-pits-atlas",
            "https://www.lroc.im-ldi.com/atlases/pits/lroc_pits_atlas.pdf")
ROBBINS_BUNDLE = ("robbins-moon-craters",
                  "https://astrogeology.usgs.gov/ckan/dataset/f89f5478-b69a-486c-b9b5-30d7b0c5ad2b/resource/c4f25cc2-4f8a-4207-a845-5e176da3ac5a/download/lunar_crater_database_robbins_2018")
BOULDER_BUNDLE = ("lroc-nac-boulders-watkins",
                  "https://asc-astropedia.s3.us-west-2.amazonaws.com/Moon/Research/Regolith/lunar_boulder_data_bundle")

GEO_ZIP_MEMBER = "Unified_Geologic_Map_of_the_Moon_GIS/"
GEO_SHP_BASE = GEO_ZIP_MEMBER + "Lunar_GIS/Shapefiles/GeoUnits."
GEO_DOMU_MEMBER = (GEO_ZIP_MEMBER + "Lunar_GIS/Symbol_LayerDefinitions/"
                   "Unified_Geologic_Map_of_the_Moon_DOMU_descriptions.csv")
GEO_PRJ_MEMBER = GEO_ZIP_MEMBER + "Lunar_GIS/Shapefiles/GeoUnits.prj"
GEO_PRJ_IDS = ('PROJCS["Moon2000_EquidistantCylindrical_clon0"',
               'GEOGCS["GCS_Moon_2000"', "1737400.0", '"Standard_Parallel_1",0.0')
MOON_RADIUS_M = 1_737_400.0

PIT_VALUE_COLUMNS = ["lat_deg", "lon_deg_east", "inner_max_diameter_m", "inner_min_diameter_m",
                     "funnel_max_diameter_m", "funnel_min_diameter_m", "depth_m",
                     "long_axis_azimuth_deg"]

# LROC terms of use, https://www.lroc.im-ldi.com/about/terms (fetched 2026-11-14):
# "Data products available through the LROC Data Node of the PDS or through NASA
# PDS interfaces are in the public domain (see list of URLs below)"; the URL list
# includes lroc.im-ldi.com and pds.lroc.im-ldi.com. The pits catalogue table (a
# data table, not an image) is served from lroc.im-ldi.com. Recorded here as the
# licence evidence; final sign-off belongs to the owner (noted in the PR).

GAPS = {
    "robbins-moon-craters": {
        "feature": "crater_density (Moon)",
        "blocker": "license-unresolved",
        "evidence": [
            "Registry row data/catalog/robbins-moon-craters.yaml: license.id unresolved, verified false "
            "(issue #41 audit: citation of Robbins 2019 JGR is not a dataset licence).",
            "2026-11-14 re-probe of the Astropedia page "
            "https://astrogeology.usgs.gov/search/map/moon_crater_database_v1_robbins (HTTP 200, 30423 B): "
            "the page has no 'Use Constraints' section (the geologic-map page has one; theirs says CC0).",
            "2026-11-14: full PDS bundle lunar_crater_database_robbins_2018 (96,227,201 B zip; sha256, fetch "
            "time and licenseVerified=false recorded in MANIFEST.json) downloaded; "
            "lunar_crater_database_README.pdf and lunar_crater_database_archive_description.pdf contain no "
            "licence, rights, redistribution or public-domain statement (only embedded font-copyright text).",
            "PDS Individual_Investigations URL advertised on the Astropedia page, "
            "https://pdsimage2.wr.usgs.gov/Individual_Investigations/moon_lro.kaguya_multi_craterdatabase_robbins_2018/, "
            "returned HTTP 404 on 2026-11-14.",
        ],
        "conclusion": "No product-specific reuse terms found; per the owner rule the crater values are not "
                      "used and no crater table is prepared. Raw bundle retained (Drive) for provenance only.",
    },
    "lroc-nac-boulders-watkins": {
        "feature": "boulder_density_nac (Moon)",
        "blocker": "license-unresolved",
        "evidence": [
            "Registry row data/catalog/lroc-nac-boulders-watkins.yaml: license.id unresolved, verified false "
            "(issue #41).",
            "2026-11-14 re-probe of "
            "https://astrogeology.usgs.gov/search/map/moon_lro_lroc_nac_boulder_database_v1_watkins "
            "(HTTP 200, 18873 B): no 'Use Constraints' section on the page.",
            "2026-11-14: PDS bundle lunar_boulder_data_bundle (185,154,475 B zip; sha256 and fetch time in "
            "MANIFEST.json, licenseVerified=false) downloaded; bundle_XML.xml, the data inventory and "
            "checksums declare PDS identifiers urn:nasa:pds:watkins_lunar_boulder_data:* but no licence, "
            "rights or redistribution statement.",
            "PDS Individual_Investigations URL advertised on the Astropedia page, "
            "https://pdsimage2.wr.usgs.gov/Individual_Investigations/moon_lro_lroc_boulderdata_watkins_2018/, "
            "returned HTTP 404 on 2026-11-14.",
        ],
        "conclusion": "No product-specific reuse terms found; boulder values are not used, no boulder table. "
                      "The work order anticipated this gap (boulder_density_nac is a listed source gap).",
    },
}


def sources():
    yield from (GEO_ZIP, PITS_PDF, ROBBINS_BUNDLE, BOULDER_BUNDLE)


# ---------------------------------------------------------------- geologic map


def geologic_units(zip_path: Path) -> list[dict]:
    """Published Description-of-Map-Units rows, verbatim, keyed by unit code."""
    with zipfile.ZipFile(zip_path) as zf:
        rows = list(csv.DictReader(
            io.TextIOWrapper(zf.open(GEO_DOMU_MEMBER), "utf-8-sig", newline="")))
    needed = ["Unit", "Name", "Description", "Interpretation"]
    if not rows or any(k not in rows[0] for k in needed):
        raise ValueError("DOMU description csv columns changed; review before preparing")
    return [{"unit_code": r["Unit"].strip(), "unit_name": r["Name"].strip(),
             "unit_description": r["Description"].strip(),
             "unit_interpretation": r["Interpretation"].strip()} for r in rows]


def _prj_check(prj: str) -> None:
    missing = [i for i in GEO_PRJ_IDS if i not in prj]
    if missing or 'UNIT["Meter"' not in prj:
        raise ValueError(f"GeoUnits.prj changed (missing {missing}); review before preparing")


def _point_in_ring(pt, ring: np.ndarray) -> bool:
    """Crossing-number test; ring is an (n,2) array in the same plane as pt."""
    x, y = float(pt[0]), float(pt[1])
    inside = False
    x1, y1 = ring[-1]
    for x2, y2 in ring:
        if (y1 > y) != (y2 > y):
            xr = x1 + (y - y1) * (x2 - x1) / (y2 - y1)
            if x < xr:
                inside = not inside
        x1, y1 = x2, y2
    return inside


class _Ring:
    __slots__ = ("pts", "bbox", "area", "bad", "parent")

    def __init__(self, pts: np.ndarray):
        self.pts = pts
        self.bbox = (pts[:, 0].min(), pts[:, 1].min(), pts[:, 0].max(), pts[:, 1].max())
        if len(pts) < 4 or not np.isfinite(pts).all():
            self.area = 0.0
            self.bad = True
        else:
            x, y = pts[:, 0], pts[:, 1]
            self.area = 0.5 * float(np.dot(x, np.roll(y, -1)) - np.dot(y, np.roll(x, -1)))
            self.bad = bool(abs(self.area) <= 1e-6)
        self.parent = -1


def _shape_rings(shape) -> list[_Ring]:
    pts = np.asarray(shape.points, dtype=np.float64)
    idx = list(shape.parts) + [len(pts)]
    if idx[0] != 0:
        raise ValueError("shapefile parts do not start at point 0")
    return [_Ring(pts[a:b]) for a, b in zip(idx, idx[1:])]


def _contains(outer: _Ring, inner: _Ring) -> bool:
    """bbox containment plus one crossing test on an inner representative point."""
    ob, ib = outer.bbox, inner.bbox
    if not (ob[0] <= ib[0] and ob[1] <= ib[1] and ob[2] >= ib[2] and ob[3] >= ib[3]):
        return False
    return _point_in_ring(inner.pts[0], outer.pts)


def polygon_parts(shape):
    """Split one shapefile record into source-native polygons + diagnostics.

    Ring nesting uses the smallest-containing-ring rule (immediate parent);
    rings at even nesting depth are outers, odd depth are holes - independent
    of ring winding, which the shapefile format does not guarantee.

    Returns ((outer, [holes...]) list, n_vertices, n_rings, n_degenerate),
    polygons as source x/y metres.
    """
    rings = [r for r in _shape_rings(shape) if not r.bad]
    degenerate = len(shape.parts) - len(rings)
    rings.sort(key=lambda r: abs(r.area), reverse=True)  # large rings first
    for i, ring in enumerate(rings):
        parent, parent_area = -1, float("inf")
        for j, cand in enumerate(rings[:i]):  # candidate containers are larger
            if abs(ring.area) < abs(cand.area) and abs(cand.area) < parent_area and _contains(cand, ring):
                parent, parent_area = j, abs(cand.area)
        ring.parent = parent
    depth = []
    for i, ring in enumerate(rings):
        d, j = 0, i
        while rings[j].parent >= 0:
            j, d = rings[j].parent, d + 1
        depth.append(d)
    polys: list[tuple[_Ring, list]] = []
    outer_at = {}
    for i, ring in enumerate(rings):
        if depth[i] % 2 == 0:
            outer_at[i] = len(polys)
            polys.append((ring, []))
    for i, ring in enumerate(rings):
        if depth[i] % 2 == 1:
            j = ring.parent
            while depth[j] % 2 != 0:
                j = rings[j].parent
            polys[outer_at[j]][1].append(ring)
    return polys, int(sum(len(r.pts) for r in rings)), len(rings), degenerate


def meters_to_degrees(pts: np.ndarray) -> np.ndarray:
    """Invert Moon2000 equidistant-cylindrical (clon 0, std parallel 0):
    lon = x/R (rad) in degrees, lat = y/R (rad) in degrees. Exact inverse."""
    return np.rad2deg(pts / MOON_RADIUS_M)


def polygon_wkb_degrees(polygons) -> bytes:
    """WKB (little-endian) for the transformed polygons; Polygon or MultiPolygon.

    Winding normalised to outer CCW / holes CW (OpenGIS simple-features style);
    vertices stay source vertices, only the exact linear inverse projection is
    applied. Source longitudes are consecutive, so no ring crosses the
    antimeridian.
    """
    is_multi = len(polygons) > 1
    polys = []
    for outer, holes in polygons:
        rings = []
        for k, ring in enumerate([outer] + holes):
            flip = (k == 0) == (ring.area > 0)
            a = np.empty((len(ring.pts) + 1, 2), dtype="<f8")
            a[: len(ring.pts)] = ring.pts[::-1] if flip else ring.pts
            a[-1] = a[0]
            rings.append(meters_to_degrees(a))
        wkb = struct.pack("<BII", 1, 3, len(rings))
        for arr in rings:
            wkb += struct.pack("<I", len(arr)) + arr.tobytes()
        polys.append(wkb)
    if is_multi:
        return struct.pack("<BII", 1, 6, len(polys)) + b"".join(polys)
    return polys[0]


def decode_wkb(wkb: bytes) -> tuple[str, list[list[np.ndarray]]]:
    """Minimal WKB reader (little-endian Polygon/MultiPolygon) -> (kind, polygons).

    Each polygon is a list of rings, ring 0 the outer, the rest holes.
    """
    if wkb[0] != 1:
        raise ValueError("only little-endian wkb supported")

    def ring_at(offset: int) -> tuple[np.ndarray, int]:
        (count,) = struct.unpack_from("<I", wkb, offset)
        arr = np.frombuffer(wkb, dtype="<f8", count=count * 2, offset=offset + 4).reshape(count, 2)
        return arr, offset + 4 + count * 16

    def polygon_at(offset: int) -> tuple[list, int]:
        if wkb[offset] != 1:
            raise ValueError("non-little-endian member")
        (kind,) = struct.unpack_from("<I", wkb, offset + 1)
        if kind != 3:
            raise ValueError(f"unsupported member wkb type {kind}")
        (nrings,) = struct.unpack_from("<I", wkb, offset + 5)
        off = offset + 9
        rings = []
        for _ in range(nrings):
            ring, off = ring_at(off)
            rings.append(ring)
        return rings, off

    (gtype,) = struct.unpack_from("<I", wkb, 1)
    if gtype == 3:
        rings, off = polygon_at(0)
        return "Polygon", [rings]
    if gtype == 6:
        (n,) = struct.unpack_from("<I", wkb, 5)
        off = 9
        polys = []
        for _ in range(n):
            rings, off = polygon_at(off)
            polys.append(rings)
        return "MultiPolygon", polys
    raise ValueError(f"unsupported wkb type {gtype}")


def build_geologic() -> dict:
    entry = _manifest_entry(GEO_ZIP[1])
    zip_path = REPO / entry["localPath"]
    if sha256(zip_path) != entry["sha256"]:
        raise ValueError("geologic map zip hash mismatch")
    _prj_check(zipfile.ZipFile(zip_path).open(GEO_PRJ_MEMBER).read().decode("ascii"))
    with zipfile.ZipFile(zip_path) as zf:
        reader = shapefile.Reader(shp=zf.open(GEO_SHP_BASE + "shp"),
                                  shx=zf.open(GEO_SHP_BASE + "shx"),
                                  dbf=zf.open(GEO_SHP_BASE + "dbf"))
        if reader.shapeTypeName != "POLYGON":
            raise ValueError(f"GeoUnits shape type changed: {reader.shapeTypeName}")
        field_names = [f[0] for f in reader.fields[1:]]
        if field_names != ["FIRST_Unit", "FIRST_Un_1", "FIRST_Un_2", "Shape_Leng", "Shape_Area", "AREA_GEO"]:
            raise ValueError(f"GeoUnits dbf fields changed: {field_names}")
        units = geologic_units(zip_path)
        unit_names = {u["unit_code"]: u["unit_name"] for u in units}
        rows = {"source_record": [], "unit_code": [], "unit_name": [], "unit_era": [],
                "unit_material": [], "shape_leng": [], "shape_area": [], "area_geo": [],
                "polygon_type": [], "n_rings": [], "n_vertices": [],
                "lon_min": [], "lon_max": [], "lat_min": [], "lat_max": [], "geometry": [],
                "missing_reason": []}
        diagnostics = {"degenerate_rings": 0, "holes": 0, "codes_without_domu": {}, "vertices": 0}
        for source_record, (rec, shape) in enumerate(zip(reader.iterRecords(), reader.iterShapes())):
            polys, n_vertices, n_rings, n_degenerate = polygon_parts(shape)
            diagnostics["degenerate_rings"] += n_degenerate
            diagnostics["holes"] += sum(len(holes) for _, holes in polys)
            diagnostics["vertices"] += n_vertices
            if not polys:
                raise ValueError(f"GeoUnits record {source_record} yielded no polygon")
            name = unit_names.get(rec[0])
            reason = None
            if name is None:
                reason = {"unit_name": f"no-DOMU-row-for-source-code-{rec[0]}"}
                diagnostics["codes_without_domu"][rec[0]] = diagnostics["codes_without_domu"].get(rec[0], 0) + 1
            rows["missing_reason"].append(json.dumps(reason, sort_keys=True) if reason else None)
            lons, lats = [], []
            for outer, holes in polys:
                for ring in [outer] + holes:
                    d = meters_to_degrees(ring.pts)
                    lons += [float(d[:, 0].min()), float(d[:, 0].max())]
                    lats += [float(d[:, 1].min()), float(d[:, 1].max())]
            rows["source_record"].append(source_record)
            rows["unit_code"].append(rec[0])
            rows["unit_name"].append(name)
            rows["unit_era"].append(rec[1])
            rows["unit_material"].append(rec[2])
            rows["shape_leng"].append(rec[3])
            rows["shape_area"].append(rec[4])
            rows["area_geo"].append(rec[5])
            rows["polygon_type"].append("MultiPolygon" if len(polys) > 1 else "Polygon")
            rows["n_rings"].append(n_rings)
            rows["n_vertices"].append(n_vertices)
            rows["lon_min"].append(min(lons))
            rows["lon_max"].append(max(lons))
            rows["lat_min"].append(min(lats))
            rows["lat_max"].append(max(lats))
            rows["geometry"].append(polygon_wkb_degrees(polys))
        out_dir = OUT / "unified-geologic-map-moon"
        out_dir.mkdir(parents=True, exist_ok=True)
        geom_meta = _write_parquet(out_dir / "geo-units-polygons.parquet", rows)
        unit_rows = {"unit_code": [u["unit_code"] for u in units],
                     "unit_name": [u["unit_name"] for u in units],
                     "unit_description": [u["unit_description"] for u in units],
                     "unit_interpretation": [u["unit_interpretation"] for u in units]}
        units_meta = _write_parquet(out_dir / "map-units-domu.parquet", unit_rows)
        return {"datasetId": GEO_ZIP[0], "sourceUrl": GEO_ZIP[1],
                "licence": {"id": entry["license"], "verified": entry["licenseVerified"],
                            "pageText": "Use Constraints: CC0, but please cite authors (Astropedia page)"},
                "rows": len(rows["source_record"]),
                "units": len(units),
                "diagnostics": diagnostics,
                "geometryOutput": geom_meta,
                "unitsOutput": units_meta,
                "crs": {"source": 'PROJCS["Moon2000_EquidistantCylindrical_clon0" on GCS_Moon_2000, IAU '
                                  "Moon_2000 sphere r=1737400 m, unit metre",
                        "output": "lon [-180,180) east-positive, lat degrees, GCS_Moon_2000 (sphere)",
                        "inverse": "lon_deg = rad2deg(x / 1737400.0), lat_deg = rad2deg(y / 1737400.0); exact linear inverse of x = R*lon_rad, y = R*lat_rad"},
                "ringClassification": "immediate-smallest-container nesting; even depth outer, odd depth hole",
                "windingNote": "shapefile ring windings are normalised on WKB write; vertices untouched",
                "domuMismatch": "source polygon code Iohs has no DOMU row; DOMU lists Ios as "
                                "'Imbrian Orientale Hevelius Formation, Secondary Crater Facies'; recorded, not fixed"}


# ------------------------------------------------------------------- pits


_NUM = r"[><]?\d+(?:\.\d+)?"
_NA = r"N/?A"
_VAL = r"(N/?A|[><]?\d+(?:\.\d+)?)"


def _value(raw: str | None) -> tuple[float | None, str | None]:
    if raw is None or re.fullmatch(_NA, raw):
        return None, raw
    num = float(raw.lstrip("><"))
    return num, raw


def parse_pit_page(text: str, page_number: int) -> dict | None:
    if "Latitude" not in text:
        return None
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    name = lines[0]
    cls = next((ln for ln in lines[1:4] if re.match(r"^[A-Z][^:]{0,80}: ", ln)), None)
    if not name or not cls:
        raise ValueError(f"pits pdf page {page_number}: missing name or class line")
    lat = re.search(r"Latitude\s+([\d.]+)\s*°\s*([NS])", text)
    lon = re.search(r"Longitude\s+([\d.]+)\s*°\s*([EW])", text)
    if not lat or not lon or lon.group(2) != "E":
        raise ValueError(f"pits pdf page {page_number}: unreadable coordinates")
    inner = re.search(r"Inner pit\s+diameter\s+" + _VAL + r"\s*m(?:\s*×\s*" + _VAL + r"\s*m)?", text)
    funnel = re.search(r"Funnel\s+diameter\s+" + _VAL + r"\s*m(?:\s*×\s*" + _VAL + r"\s*m)?", text)
    azimuth = re.search(r"Long axis\s+azimuth\s+" + _VAL + r"\s*°", text)
    depth = re.search(r"Depth\s+" + _VAL + r"\s*m\s+Funnel", text)
    row = {"pit_name": name, "pit_class_host": cls, "page_number": page_number,
           "lat_source": f"{lat.group(1)}°{lat.group(2)}", "lon_source": f"{lon.group(1)}°{lon.group(2)}",
           "lat_deg": float(lat.group(1)) * (-1 if lat.group(2) == "S" else 1),
           "lon_deg_east": float(lon.group(1))}
    parsed = {"inner_max_diameter_m": _value(inner.group(1) if inner else None),
              "inner_min_diameter_m": _value(inner.group(2) if inner else None),
              "funnel_max_diameter_m": _value(funnel.group(1) if funnel else None),
              "funnel_min_diameter_m": _value(funnel.group(2) if funnel else None),
              "long_axis_azimuth_deg": _value(azimuth.group(1) if azimuth else None),
              "depth_m": _value(depth.group(1) if depth else None)}
    missing = {}
    for col, (num, src) in parsed.items():
        row[col] = num
        row[col + "_source"] = src
        if num is None:
            missing[col] = "absent-or-N/A-on-source-page"
    row["missing_reason"] = json.dumps(missing, sort_keys=True) if missing else None
    return row


def build_pits() -> dict:
    entry = _manifest_entry(PITS_PDF[1])
    pdf_path = REPO / entry["localPath"]
    if sha256(pdf_path) != entry["sha256"]:
        raise ValueError("pits pdf hash mismatch")
    reader = PdfReader(pdf_path)
    rows = {"pit_name": [], "pit_class_host": [], "page_number": [], "lat_deg": [], "lon_deg_east": [],
            "lat_source": [], "lon_source": []}
    for col in PIT_VALUE_COLUMNS[2:]:
        rows[col] = []
        rows[col + "_source"] = []
    rows["missing_reason"] = []
    skipped = []
    for i, page in enumerate(reader.pages):
        text = page.extract_text() or ""
        if i <= 2:
            continue  # title + two method pages
        if "Latitude" not in text:
            skipped.append(i)
            continue
        row = parse_pit_page(text, i + 1)
        if row is None:
            raise ValueError(f"pits pdf page {i + 1}: pit page did not parse")
        for col in rows:
            rows[col].append(row[col])
    out_dir = OUT / "lroc-pits-atlas"
    out_dir.mkdir(parents=True, exist_ok=True)
    meta = _write_parquet(out_dir / "pits.parquet", rows)
    return {"datasetId": PITS_PDF[0], "sourceUrl": PITS_PDF[1],
            "licence": {"id": entry["license"], "verified": entry["licenseVerified"], "see": "module + catalog note"},
            "rows": len(rows["pit_name"]), "skippedPages": skipped,
            "output": meta,
            "coordinates": "lat N positive; lon_deg_east 0-360 east-positive exactly as printed (°N/°S, °E kept verbatim)",
            "sourceEdition": "Catalog of Lunar Pits, Version 1 - March 2021 (R.V. Wagner, M.S. Robinson, LROC team)"}


# ------------------------------------------------------------------- shared


def _manifest_entry(url: str) -> dict:
    e = next((e for e in load_manifest()["entries"] if e["sourceUrl"] == url), None)
    if e is None:
        raise ValueError(f"missing snapshot: {url}")
    return e


def _write_parquet(path: Path, rows: dict) -> dict:
    frame = pl.DataFrame(rows)
    if frame.height == 0:
        raise ValueError(f"{path.name}: zero rows")
    table = frame.to_arrow()
    pq.write_table(table, path, compression="zstd")
    return {"path": str(path.relative_to(REPO)), "rows": frame.height,
            "sha256": sha256(path), "bytes": path.stat().st_size,
            "columns": frame.columns,
            "missingReasonDistribution": {json.dumps(list(k), sort_keys=True) if k else "valid": v
                                          for k, v in _reason_counts(frame).items()}}


def _reason_counts(frame: pl.DataFrame) -> dict:
    if "missing_reason" not in frame.columns:
        return {}
    counts: dict = {}
    for r in frame["missing_reason"]:
        if not r:
            continue
        key = tuple(sorted(json.loads(r).items()))
        counts[key] = counts.get(key, 0) + 1
    return counts


def build() -> dict:
    report = {"generatedAt": datetime.now(timezone.utc).isoformat(),
              "runtimeStatus": "executed", "scientificStatus": "executed-unreviewed",
              "scope": "source-native Moon geology preparation; no scoring, no analogy, no H3 resampling",
              "outputs": {}, "gapReports": {}}
    report["outputs"]["unified-geologic-map-moon"] = build_geologic()
    report["outputs"]["lroc-pits-atlas"] = build_pits()
    for dataset, gap in GAPS.items():
        out_dir = OUT / dataset
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "gap-report.json").write_text(json.dumps(gap, indent=2) + "\n")
        report["gapReports"][dataset] = {"path": str((out_dir / "gap-report.json").relative_to(REPO)),
                                         "blocker": gap["blocker"], "feature": gap["feature"]}
    (OUT / "moon-geology-preparation-report.json").write_text(json.dumps(report, indent=2) + "\n")
    return report


def _check_reasons_match(frame: pl.DataFrame, value_cols: list[str]) -> None:
    for row in frame.iter_rows(named=True):
        null_cols = {c for c in value_cols if row[c] is None}
        keys = set(json.loads(row["missing_reason"])) if row["missing_reason"] else set()
        if null_cols != keys:
            raise ValueError(f"missing_reason mismatch for {row}: nulls {null_cols} vs keys {keys}")


# Known-raw spot checks (hand-read from the source document on 2026-11-14).
PIT_SPOT_CHECKS = [
    ("Compton Pit", 56.2247, 106.1955, 110.0, 92.0, 230.0, 140.0, 35.0, 140.0),
    ("Lacus Mortis Pit", 44.9608, 25.6119, 165.0, 110.0, 280.0, 210.0, 60.0, 110.0),
    ("Marius Hills Pit", 14.0917, 303.2299, 55.0, 49.0, 92.0, 79.0, 40.0, 65.0),
    ("West Marius Hills Pit", 13.5507, 301.8267, 50.0, 47.0, 95.0, 70.0, 16.0, 55.0),
    ("Central Mare Fecunditatis Pit", -0.9182, 48.6595, 122.0, 100.0, 198.0, 162.0, 42.0, 155.0),
]

# Geologic-map known sites: (label, lon_deg in [-180,180), lat_deg, expected substring)
GEO_SPOT_CHECKS = [
    ("Apollo 11 landing site (Mare Tranquillitatis)", 23.4731, 0.6739, "Mare"),
    ("Apollo 15 landing site (Palus Putredinis)", 3.6338, 26.1324, "Mare"),
    ("Tycho crater centre", -11.36, -43.31, "Cc"),
    ("Aristarchus crater centre", -47.49, 23.73, "Cc"),
    ("Mare Imbrium centre", -15.6, 32.8, "Mare"),
]


def check() -> None:
    reps = json.loads((OUT / "moon-geology-preparation-report.json").read_text())
    for dataset in ("unified-geologic-map-moon", "lroc-pits-atlas", "robbins-moon-craters",
                    "lroc-nac-boulders-watkins"):
        entry = _manifest_entry(_url_of(dataset))
        path = REPO / entry["localPath"]
        if sha256(path) != entry["sha256"] or path.stat().st_size != entry["bytes"]:
            raise ValueError(f"raw snapshot hash/size mismatch: {dataset}")

    # pits: keys, ranges, missing reasons, 5 raw spot checks
    pits_path = OUT / "lroc-pits-atlas" / "pits.parquet"
    meta = reps["outputs"]["lroc-pits-atlas"]["output"]
    if sha256(pits_path) != meta["sha256"]:
        raise ValueError("pits parquet hash mismatch")
    pits = pl.read_parquet(pits_path)
    value_cols = PIT_VALUE_COLUMNS
    if pits.select(pl.col("pit_name").n_unique()).item() != pits.height:
        raise ValueError("duplicate pit_name")
    if pits.filter(pl.col("lat_deg").abs() > 90).height or pits.filter(
            (pl.col("lon_deg_east") < 0) | (pl.col("lon_deg_east") > 360)).height:
        raise ValueError("pit coordinates out of range")
    for col in ("inner_max_diameter_m", "inner_min_diameter_m", "funnel_max_diameter_m",
                "funnel_min_diameter_m", "depth_m"):
        bad = pits.filter((pl.col(col) <= 0).fill_null(False)).height
        if bad:
            raise ValueError(f"physical range violation in {col}")
        bad = pits.filter((pl.col(col) > 5000).fill_null(False)).height
        if bad:
            raise ValueError(f"unphysical {col} value")
    az = pits.filter((pl.col("long_axis_azimuth_deg") < 0) | (pl.col("long_axis_azimuth_deg") > 360))
    if az.height:
        raise ValueError("long_axis_azimuth_deg outside [0, 360]")
    _check_reasons_match(pits, value_cols)
    by_name = {row["pit_name"]: row for row in pits.iter_rows(named=True)}
    for name, lat, lon, imax, imin, fmax, fmin, depth, az in PIT_SPOT_CHECKS:
        row = by_name.get(name)
        if row is None:
            raise ValueError(f"spot-check pit {name} not in table")
        want = {"lat_deg": lat, "lon_deg_east": lon, "inner_max_diameter_m": imax,
                "inner_min_diameter_m": imin, "funnel_max_diameter_m": fmax,
                "funnel_min_diameter_m": fmin, "depth_m": depth, "long_axis_azimuth_deg": az}
        for col, expected in want.items():
            got = row[col]
            if got is None or abs(got - expected) > 1e-9:
                raise ValueError(f"pit spot check failed: {name} {col}: table {got} vs raw {expected}")
    print(f"PASS lroc-pits-atlas/pits.parquet: {pits.height} pits; keys, ranges, reasons, 5 raw spot checks", flush=True)

    # geologic map: hashes, units, geometry roundtrip vs raw, 5 site spot checks
    geo_path = OUT / "unified-geologic-map-moon" / "geo-units-polygons.parquet"
    gmeta = reps["outputs"]["unified-geologic-map-moon"]
    pol = pl.read_parquet(geo_path)
    units = pl.read_parquet(OUT / "unified-geologic-map-moon" / "map-units-domu.parquet")
    entry = _manifest_entry(GEO_ZIP[1])
    zip_path = REPO / entry["localPath"]
    if sha256(geo_path) != reps["outputs"]["unified-geologic-map-moon"]["geometryOutput"]["sha256"]:
        raise ValueError("geo-units parquet hash mismatch")
    with zipfile.ZipFile(zip_path) as zf:
        reader = shapefile.Reader(shp=zf.open(GEO_SHP_BASE + "shp"),
                                  shx=zf.open(GEO_SHP_BASE + "shx"),
                                  dbf=zf.open(GEO_SHP_BASE + "dbf"))
        raw_shapes = list(reader.iterShapes())
        raw_records = list(reader.iterRecords())
    if pol.height != len(raw_records) or units.height != reps["outputs"]["unified-geologic-map-moon"]["units"]:
        raise ValueError("row count mismatch vs raw")
    unit_map = dict(zip(units["unit_code"].to_list(), units["unit_name"].to_list()))
    for source_record in (0, 999, 2_500, 6_000, len(raw_records) - 1):  # 5 raw spot checks
        raw_polys, n_vertices, n_rings, _ = polygon_parts(raw_shapes[source_record])
        row = pol.row(source_record, named=True)
        kind, polys = decode_wkb(row["geometry"])
        # WKB rings are closed: one repeated vertex per ring
        wkb_rings = [r for p in polys for r in p]
        wkb_vertices = sum(r.shape[0] for r in wkb_rings)
        if kind != row["polygon_type"] or wkb_vertices != n_vertices + len(wkb_rings):
            raise ValueError(f"wkb mismatch at record {source_record}")
        rec = raw_records[source_record]
        for col, got in (("unit_code", rec[0]), ("unit_era", rec[1]), ("unit_material", rec[2]),
                         ("shape_leng", rec[3]), ("shape_area", rec[4]), ("area_geo", rec[5])):
            if row[col] != got:
                raise ValueError(f"attribute mismatch at record {source_record}: {col}")
        # decoded rings are exactly the raw rings transformed to degrees
        # (any ring may appear reversed from the winding normalisation)
        raw_rings = [meters_to_degrees(np.asarray(np.vstack((ring.pts, ring.pts[:1])), dtype=np.float64))
                     for p2 in raw_polys for ring in [p2[0]] + p2[1]]
        dec_rings = [r for p2 in polys for r in p2]
        if len(raw_rings) != len(dec_rings):
            raise ValueError(f"ring count mismatch at record {source_record}")
        for got, want in zip(dec_rings, raw_rings):
            if not (np.allclose(got, want, rtol=0, atol=1e-12) or np.allclose(got, want[::-1], rtol=0, atol=1e-12)):
                raise ValueError(f"geometry mismatch at record {source_record}")
        if row["unit_code"] != "Iohs" and unit_map.get(row["unit_code"]) != row["unit_name"]:
            raise ValueError(f"unit name join broken at record {source_record}")
    # 5 known-site checks: site inside polygons of expected material
    hits = 0
    for label, lon, lat, want in GEO_SPOT_CHECKS:
        best = None
        area = float("inf")
        for source_record in range(pol.height):
            row = pol.row(source_record, named=True)
            if not (row["lon_min"] <= lon <= row["lon_max"] and row["lat_min"] <= lat <= row["lat_max"]):
                continue
            kind, polys = decode_wkb(row["geometry"])
            for rings in polys:
                if _point_in_ring((lon, lat), rings[0]) and not any(
                        _point_in_ring((lon, lat), h) for h in rings[1:]):
                    a = row["area_geo"]
                    if a < area:
                        best, area = row, a
                    break
        if best is None:
            raise ValueError(f"site {label} resolved to no unit")
        if not any(want in s for s in (best["unit_code"], best["unit_material"], best["unit_name"] or "", best["unit_era"] or "")):
            raise ValueError(
                f"site spot check failed: {label} -> {best['unit_code']}/{best['unit_material']}, expected {want}")
        hits += 1
    _check_reasons_match(pol, ["unit_name"])
    print(f"PASS unified-geologic-map-moon: {pol.height} polygons, {units.height} units; "
          f"raw roundtrip + {hits} site spot checks", flush=True)
    for dataset, gr in reps["gapReports"].items():
        print(f"GAP {dataset}: {gr['blocker']} -> {gr['path']}", flush=True)


def _url_of(dataset: str) -> str:
    return dict(sources())[dataset]


def _contains_point_decoded(pt, wkb: bytes) -> bool:
    kind, polys = decode_wkb(wkb)
    for rings in polys:
        if _point_in_ring(pt, rings[0]) and not any(_point_in_ring(pt, h) for h in rings[1:]):
            return True
    return False


def main() -> None:
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument("action", choices=["fetch", "build", "check"])
    action = parser.parse_args().action
    if action == "fetch":
        for dataset, url in sources():
            print(fetch(dataset, url), flush=True)
    elif action == "build":
        report = build()
        for name, out in report["outputs"].items():
            print(name, out["rows"], json.dumps(out if name != "unified-geologic-map-moon"
                                                else {k: out[k] for k in ("units", "diagnostics")}),
                  flush=True)
        for name, gap in report["gapReports"].items():
            print(f"GAP {name}: {gap['blocker']}", flush=True)
    else:
        check()


if __name__ == "__main__":
    main()
