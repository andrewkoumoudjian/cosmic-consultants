"""Prepare Mars Odyssey THEMIS IR controlled mosaics for six landing-site ROIs (#104).

The USGS THEMIS day/night IR controlled mosaics (STAC collection
mo_themis_controlled_mosaics, CC0-1.0) are 8-bit QUALITATIVE brightness image
mosaics: values are never labelled as surface temperature (kelvin) or thermal
inertia (TIU). Tables keep the source native simple-cylindrical grid and
coordinates (100 m/pixel), clipped to ~1 deg regional subsets around Jezero,
Gale, Elysium (InSight), Utopia (Zhurong), Meridiani (Opportunity) and Gusev
(Spirit).

Not ingested, on explicit evidence:
- USGS THEMIS global thermal-inertia mosaic (Quantitative-32-Bit): licence
  unresolved (FGDC access/use constraints both "None"; no data.nasa.gov
  record) per the LICENCE-AUDIT-41 precedent (`themis-global-thermal-inertia`
  registry row). The FGDC .cub.docx evidence resource 404s on re-fetch, so no
  evidence bytes are snapshotted; the constraint text is quoted in the
  registry row. Values are not ingested either way.
- MRO Mars Climate Sounder (mcs-mro): PDS Atmospheres holds only per-orbit
  (~4-hour) EDR/DDR granules and no Ls-binned surface climatology, so under
  the at-most-monthly rule MCS is probe-only. Its EDR label and DATASET.CAT
  are snapshotted as evidence.

Direct decoding and declared filtering only. No resampling, no H3, no scoring.
Pixel-to-coordinate rule: the centre of each native 100 m pixel maps to its
simple-cylindrical planetocentric longitude and latitude through the GeoTIFF
affine transform of IAU_2015:49910 (x = A*lon, y = A*lat, lon in -180..180
east, A = 3396190 m). No h3 step applies to Mars tables.
Run: python -m p0ingest.mars_themis fetch|build|check
"""
from __future__ import annotations

import argparse
import json
import math
import re
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import polars as pl
import pyarrow.parquet as pq
import rasterio

from .snapshots import REPO, SNAP, fetch, load_manifest, sha256

OUT = SNAP / "_derived" / "planetary" / "themis-ir-controlled-mosaics"
STAC_ITEMS_URL = ("https://stac.astrogeology.usgs.gov/api/collections/"
                  "mo_themis_controlled_mosaics/items?limit=100")
ASSET_BASE = "https://astrogeo-ard.s3.us-west-2.amazonaws.com/mars/mo/themis/controlled_mosaics/"
MCS_EDR_FMT_URL = "https://atmos.nmsu.edu/PDS/data/MROM_0006/LABEL/MCS_EDR.FMT"
MCS_DATASET_CAT_URL = "https://atmos.nmsu.edu/PDS/data/MROM_0006/CATALOG/DATASET.CAT"
TI_LICENCE_DOCX_URL = ("https://astrogeology.usgs.gov/ckan/dataset/"
                       "3a0624e9-e7d3-41e7-aa50-9a8d080cf3cc/resource/"
                       "6556a9a1-33ba-4347-8e98-3155a78262a3/download/"
                       "themis_ti_mosaic_qual_00n000e_100mpp_cub.docx")
DATASET = "themis-ir-controlled-mosaics"
TES_DERIVED = SNAP / "_derived" / "planetary" / "tes-thermal-inertia-night.parquet"
MARS_A_METRES = 3396190.0  # IAU_2015:49910 equatorial radius, per the product CRS

# Published landing-site coordinates (planetocentric latitude, east longitude):
# Jezero 18.4447N 77.4508E (Perseverance); Gale 4.5895S 137.4417E (Curiosity);
# Elysium 4.502384N 135.623447E (InSight); Utopia 25.066N 109.925E (Zhurong);
# Meridiani 1.9462S 354.4734E (Opportunity); Gusev 14.5684S 175.4726E (Spirit).
SITES = {
    "jezero_perseverance": (18.4447, 77.4508),
    "gale_curiosity": (-4.5895, 137.4417),
    "elysium_insight": (4.502384, 135.623447),
    "utopia_zhurong": (25.066, 109.925),
    "meridiani_opportunity": (-1.9462, 354.4734),
    "gusev_spirit": (-14.5684, 175.4726),
}
ROI_HALF_DEG = 0.5  # ~59 km north-south, ~50 km east-west at these latitudes
PIXEL_METRES = 100.0
NODATA_DN = 0

VALUE_COLUMN = "ir_brightness_dn"
TABLE_COLUMNS = ["site", "quad", "phase", "source_line", "source_sample",
                 "lat_pc_deg", "lon_east_deg", VALUE_COLUMN, "missing_reason"]
MISSING_NO_DATA = json.dumps({VALUE_COLUMN: "no-source-data"})
# Raw spot checks: (site, lat, lon east) - every site, verified in both phases.
SPOT_CHECKS = [
    ("jezero_perseverance", 18.4447, 77.4508),
    ("gale_curiosity", -4.5895, 137.4417),
    ("elysium_insight", 4.502384, 135.623447),
    ("utopia_zhurong", 25.066, 109.925),
    ("meridiani_opportunity", -1.9462, 354.4734),
    ("gusev_spirit", -14.5684, 175.4726),
    ("jezero_perseverance", 18.50, 77.55),
    ("gale_curiosity", -4.70, 137.50),
    ("elysium_insight", 4.60, 135.70),
    ("utopia_zhurong", 25.12, 110.00),
    ("meridiani_opportunity", -2.00, 354.40),
    ("gusev_spirit", -14.65, 175.55),
]


def parse_isis_mapping(path: Path) -> dict:
    """Parse the Mapping group of an ISIS3 quad label into a small dict."""
    text = path.read_text(errors="replace")
    match = re.search(r"Group = Mapping(.*?)End_Group", text, re.S)
    if not match:
        raise ValueError(f"no ISIS Mapping group in {path.name}")
    fields = {}
    for key in ("ProjectionName", "LatitudeType", "LongitudeDirection", "LongitudeDomain",
                "MinimumLatitude", "MaximumLatitude", "MinimumLongitude", "MaximumLongitude",
                "PixelResolution", "Scale"):
        found = re.search(rf"^\s*{key}\s*=\s*([^\n]+)", match.group(1), re.M)
        if found:
            fields[key] = found.group(1).strip()
    for key in ("CenterLongitude", "MinimumLatitude", "MaximumLatitude",
                "MinimumLongitude", "MaximumLongitude", "PixelResolution"):
        if key in fields:
            fields[key] = float(fields[key])
    return fields


def stac_items() -> dict:
    path = fetch(DATASET, STAC_ITEMS_URL, filename="stac-items.json")
    return {f["id"]: f for f in json.loads(path.read_text())["features"]}


def quad_footprints() -> dict:
    """Fetch every quad ISIS label; return {item_id: {mapping, tif, provenance, phase}}."""
    footprints = {}
    for item_id, item in sorted(stac_items().items()):
        label_path = fetch(DATASET, ASSET_BASE + f"{item_id}/{item_id}.isis.lbl")
        mapping = parse_isis_mapping(label_path)
        tifs = [a["href"] for a in item["assets"].values()
                if str(a.get("type", "")).startswith("image/tiff")]
        if len(tifs) != 1:
            raise ValueError(f"expected one tif asset for {item_id}, got {len(tifs)}")
        phase = "night" if item_id.endswith("_nir") else \
            ("day" if item_id.endswith("_dir") else None)
        if phase is None or mapping.get("ProjectionName") != "SimpleCylindrical":
            raise ValueError(f"unexpected quad item {item_id}: phase {phase}, "
                             f"projection {mapping.get('ProjectionName')}")
        footprints[item_id] = {"mapping": mapping, "tif": tifs[0], "phase": phase,
                               "provenance": ASSET_BASE + f"{item_id}/provenance.txt"}
    return footprints


def lon_segments(center_east: float, half: float) -> list[tuple[float, float]]:
    """ROI longitude segment(s) in 0..360 east-longitude space."""
    low = (center_east - half) % 360.0
    high = (center_east + half) % 360.0
    return [(low, high)] if low < high else [(0.0, high), (low, 360.0)]


def roi_quads(footprints: dict, lat: float, lon_east: float) -> list[str]:
    """Quads whose declared footprint fully covers the whole ROI box.

    Quad labels state longitudes in the -180..180 or 0..360 POSITIVE-EAST
    convention inconsistently (e.g. mc11 -45..0 vs mc12 0..45); normalize to
    0..360 before the coverage test.
    """
    chosen = []
    for item_id, fp in sorted(footprints.items()):
        m = fp["mapping"]
        lo = m.get("MinimumLongitude", 360.0) % 360.0
        hi = m.get("MaximumLongitude", 0.0) % 360.0
        if hi < lo:
            hi += 360.0
        if (m.get("MinimumLatitude", 90.0) > lat - ROI_HALF_DEG + 1e-9
                or m.get("MaximumLatitude", -90.0) < lat + ROI_HALF_DEG - 1e-9):
            continue
        if not all(seg[0] >= lo - 1e-9 and seg[1] <= hi + 1e-9
                   for seg in lon_segments(lon_east, ROI_HALF_DEG)):
            continue
        chosen.append(item_id)
    return chosen


def select_quads() -> dict:
    """{site: {"day": quad, "night": quad}} from the fetched ISIS labels."""
    footprints = quad_footprints()
    sites = {}
    for site, (lat, lon_east) in SITES.items():
        ids = roi_quads(footprints, lat, lon_east % 360.0)
        if not ids:
            raise ValueError(f"no THEMIS controlled-mosaic quad covers the ROI of {site}")
        phases = {"day": None, "night": None}
        for item_id in ids:
            phases[footprints[item_id]["phase"]] = item_id
        if None in phases.values():
            raise ValueError(f"{site}: missing a quad phase, coverage ids {ids}")
        sites[site] = phases
    return {"sites": sites, "footprints": footprints,
            "used": sorted({i for ph in sites.values() for i in ph.values()})}


def sources() -> list[tuple[str, str]]:
    """All raw bytes: STAC items, the used quads' tifs + provenance files, the MCS
    probe evidence and the TI-mosaic licence evidence."""
    out = [(DATASET, STAC_ITEMS_URL),
           ("mcs-mro", MCS_EDR_FMT_URL),
           ("mcs-mro", MCS_DATASET_CAT_URL),
           ("themis-global-thermal-inertia", TI_LICENCE_DOCX_URL)]
    selection = select_quads()
    for item_id in selection["used"]:
        fp = selection["footprints"][item_id]
        out.append((DATASET, fp["tif"]))
        out.append((DATASET, fp["provenance"]))
    return out


# Evidence-only downloads whose absence must not block the run (the host serving
# the TI docx returned HTTP 200 on 2026-11-14 ~17:55 UTC and HTTP 404 on repeat
# probes; the FGDC constraint text is quoted in the catalog row and report).
OPTIONAL_URLS = {MCS_EDR_FMT_URL, MCS_DATASET_CAT_URL, TI_LICENCE_DOCX_URL}


def verify_value_inputs() -> list[dict]:
    """MANIFEST + hash verification for the value-carrying mosaic inputs."""
    entries = {e["localPath"]: e for e in load_manifest()["entries"]}
    selection = select_quads()
    wanted = [(DATASET, STAC_ITEMS_URL, SNAP / DATASET / "stac-items.json")]
    for item_id in sorted({i for s in selection["sites"].values() for i in s.values()}):
        fp = selection["footprints"][item_id]
        wanted.append((DATASET, ASSET_BASE + f"{item_id}/{item_id}.isis.lbl",
                       SNAP / DATASET / f"{item_id}.isis.lbl"))
        wanted.append((DATASET, fp["tif"],
                       SNAP / DATASET / Path(fp["tif"]).name))
    checked = []
    for dataset, url, local in wanted:
        entry = entries.get(str(local.relative_to(REPO)))
        if entry is None or entry["datasetId"] != dataset or not entry["licenseVerified"]:
            raise ValueError(f"missing licensed snapshot: {url}")
        if local.stat().st_size != entry["bytes"] or sha256(local) != entry["sha256"]:
            raise ValueError(f"input hash/size mismatch: {local}")
        checked.append(entry)
    return checked


def quad_path(footprints: dict, quad: str) -> Path:
    return SNAP / DATASET / Path(footprints[quad]["tif"]).name


def pixel_indices(lat: float, lon_east: float, transform, width: int, height: int) -> tuple[int, int]:
    """Native (line, sample) of the pixel whose CENTRE contains (lat, lon)."""
    a, c, f = transform.a, transform.c, transform.f
    lon = ((lon_east + 180.0) % 360.0) - 180.0
    sample = int(round((math.radians(lon) * MARS_A_METRES - c) / a - 0.5))
    line = int(round((f - math.radians(lat) * MARS_A_METRES) / 100.0 - 0.5))
    if not (0 <= sample < width and 0 <= line < height):
        raise ValueError("coordinate outside raster")
    return line, sample


def site_window(ds: rasterio.io.DatasetReader, lat: float, lon_east: float) -> dict:
    """Native pixel window of the ROI box in one quad GeoTIFF.

    The COG CRS is IAU_2015:49910 simple cylindrical: x = A*lon (lon in
    -180..180 east), y = A*lat, A = 3396190 m, 100 m/pixel. Rows grow south,
    columns grow east. clippedEdges counts ROI sides that fall on no-data
    areas of this quad (kept explicit, not filled).
    """
    lon_lo = ((lon_east - ROI_HALF_DEG + 180.0) % 360.0) - 180.0
    lon_hi = ((lon_east + ROI_HALF_DEG + 180.0) % 360.0) - 180.0
    if lon_hi < lon_lo:
        raise ValueError("ROI crosses the -180/180 seam or spans >180 deg")
    inv = ~ds.transform
    (col_a, _), (col_b, _) = inv * (math.radians(lon_lo) * MARS_A_METRES, 0.0), \
        inv * (math.radians(lon_hi) * MARS_A_METRES, 0.0)
    (_, row_a), (_, row_b) = inv * (0.0, math.radians(lat + ROI_HALF_DEG) * MARS_A_METRES), \
        inv * (0.0, math.radians(lat - ROI_HALF_DEG) * MARS_A_METRES)
    col0, col1 = min(col_a, col_b), max(col_a, col_b)
    row0, row1 = min(row_a, row_b), max(row_a, row_b)
    req_c0, req_c1 = math.floor(col0), math.ceil(col1)
    req_r0, req_r1 = math.floor(row0), math.ceil(row1)
    c0, c1 = max(0, req_c0), min(ds.width - 1, req_c1)
    r0, r1 = max(0, req_r0), min(ds.height - 1, req_r1)
    return {"row0": r0, "col0": c0, "rows": r1 - r0 + 1, "cols": c1 - c0 + 1,
            "clippedCols": max(0, (req_c0 - c0) + (req_c1 - c1)),
            "clippedRows": max(0, (req_r0 - r0) + (req_r1 - r1)),
            "fullyInsideQuad": req_c0 >= 0 and req_c1 <= ds.width - 1
            and req_r0 >= 0 and req_r1 <= ds.height - 1}


def read_site_pixels(ds: rasterio.io.DatasetReader, quad: str, phase: str, site: str,
                     lat: float, lon_east: float) -> tuple[pl.DataFrame, dict]:
    """Native-grid pixel table for one site ROI from an open quad COG."""
    win = site_window(ds, lat, lon_east)
    if win["rows"] < 1 or win["cols"] < 1:
        raise ValueError(f"{site}/{quad}: empty ROI window")
    data = ds.read(1, window=rasterio.windows.Window(win["col0"], win["row0"],
                                                     win["cols"], win["rows"]))
    height, width = data.shape
    lines = np.repeat(np.arange(win["row0"], win["row0"] + height, dtype=np.int64), width)
    samples = np.tile(np.arange(win["col0"], win["col0"] + width, dtype=np.int64), height)
    lon_deg = [(math.degrees((ds.transform.c + ds.transform.a * (s + 0.5)) / MARS_A_METRES)
                + 360.0) % 360.0 for s in samples.tolist()]
    lat_deg = [math.degrees((ds.transform.f - PIXEL_METRES * (l + 0.5)) / MARS_A_METRES)
               for l in lines.tolist()]
    flat = data.ravel()
    valid = (flat != NODATA_DN).tolist()
    frame = pl.DataFrame({
        "site": pl.Series([site] * flat.size, dtype=pl.String),
        "quad": pl.Series([quad] * flat.size, dtype=pl.String),
        "phase": pl.Series([phase] * flat.size, dtype=pl.String),
        "source_line": pl.Series(lines, dtype=pl.Int64),
        "source_sample": pl.Series(samples, dtype=pl.Int64),
        "lat_pc_deg": pl.Series(lat_deg, dtype=pl.Float64),
        "lon_east_deg": pl.Series(lon_deg, dtype=pl.Float64),
        VALUE_COLUMN: pl.Series([int(v) if ok else None
                                 for v, ok in zip(flat.tolist(), valid)], dtype=pl.UInt8),
        "missing_reason": [None if ok else MISSING_NO_DATA for ok in valid],
    })
    return frame, win


def pixel_stats(frame: pl.DataFrame) -> dict:
    nodes = frame.group_by(pl.col(VALUE_COLUMN).is_null().alias("null")).len()
    nodata = int(nodes.filter(pl.col("null"))["len"][0]) \
        if nodes.filter(pl.col("null")).height else 0
    values = frame.filter(pl.col(VALUE_COLUMN).is_not_null())[VALUE_COLUMN]
    return {"pixels": frame.height, "nodataPixels": nodata,
            "dnMin": int(values.min()), "dnMax": int(values.max()),
            "dnMean": round(float(values.mean()), 3)}


def tes_diagnostic(night: pl.DataFrame) -> dict:
    """Diagnostic-only cross-check: THEMIS night brightness vs TES thermal inertia.

    THEMIS night DN is averaged into nominal TES 20 px/deg cells (0.05 deg,
    nominal equations lat = 90 - (line+0.5)*0.05, and both possible longitude
    conventions because the TES DSMAP sign is under review: positions carry
    ~0.3-0.5 deg uncertainty per PR #87). Spearman rho per site. Nothing is
    adjusted and no number here is a feature.
    """
    if not TES_DERIVED.exists():
        return {"status": "skipped",
                "reason": f"{TES_DERIVED.name} not present locally (copy from ccdrive first)"}
    tes = pl.read_parquet(TES_DERIVED, columns=["source_line", "source_sample",
                                                "thermal_inertia"])
    tes = tes.filter(pl.col("thermal_inertia").is_not_null())
    out = {"status": "ok",
           "method": "THEMIS night DN averaged into nominal TES 0.05 deg cells; "
                     "Spearman rho; diagnostic only, TES positions uncertain (PR #87)",
           "sites": {}}
    for site, (lat0, lon0) in sorted(SITES.items()):
        sub = night.filter((pl.col("site") == site) & pl.col(VALUE_COLUMN).is_not_null())
        if sub.height == 0:
            out["sites"][site] = {"note": "no THEMIS night data"}
            continue
        cells = (sub.with_columns(((90.0 - pl.col("lat_pc_deg")) / 0.05 - 0.5)
                                  .floor().cast(pl.Int64).alias("line_i")))
        result = {"themisPixels": cells.height}
        # TES sample direction is the review item (PR #87): nominal east vs flipped
        tes_cells_east = tes.select(pl.col("source_line").alias("line_i"),
                                    pl.col("source_sample").alias("col_i"),
                                    "thermal_inertia")
        tes_cells_west = tes.select(pl.col("source_line").alias("line_i"),
                                    (7199 - pl.col("source_sample")).alias("col_i"),
                                    "thermal_inertia")
        for convention, lon_expr, tes_cells in (
                ("east_0_360", pl.col("lon_east_deg") / 0.05 - 0.5, tes_cells_east),
                ("west_0_360", (360.0 - pl.col("lon_east_deg")) / 0.05 - 0.5, tes_cells_west)):
            grouped = (cells.with_columns(lon_expr.floor().cast(pl.Int64).alias("col_i"))
                       .group_by(["line_i", "col_i"])
                       .agg(pl.col(VALUE_COLUMN).mean().alias("dn_mean")))
            merged = grouped.join(tes_cells, on=["line_i", "col_i"], how="inner")
            if merged.height < 30:
                result[convention] = {"note": f"only {merged.height} TES cells overlap"}
                continue
            ranked = merged.with_columns(pl.col("dn_mean").rank().alias("rd"),
                                         pl.col("thermal_inertia").rank().alias("rt"))
            rho = ranked.select(pl.corr("rd", "rt")).item()
            result[convention] = {"tesCells": int(merged.height),
                                  "spearmanNightDnVsTesTi": round(float(rho), 4)}
        out["sites"][site] = result
    return out


def build() -> dict:
    checked = verify_value_inputs()
    selection = select_quads()
    footprints, quads = selection["footprints"], selection["sites"]
    OUT.mkdir(parents=True, exist_ok=True)
    report = {
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "inputs": checked,
        "runtimeStatus": "executed",
        "scientificStatus": "partial",
        "scope": "source-native 8-bit IR brightness on the native simple-cylindrical "
                 "grid over six landing-site ROIs; no resampling, no temperature or "
                 "TIU values, no scoring",
        "pixelToCoordinateRule": "pixel centre -> IAU_2015:49910 simple-cylindrical "
                                 "lon/lat through the GeoTIFF affine transform "
                                 "(x = 3396190 m * lon, y = 3396190 m * lat, "
                                 "100 m/pixel); no h3 step for Mars",
        "sites": {s: {"lat_pc_deg": lat, "lon_east_deg": lon, "quads": quads[s],
                      "roiHalfDeg": ROI_HALF_DEG, "windows": {}}
                  for s, (lat, lon) in SITES.items()},
        "gaps": {
            "ti": "The USGS THEMIS quantitative global thermal-inertia mosaic "
                  "(~100 m/px, 32-bit, e.g. THEMIS_TI_Mosaic_Quant_00N060E_100mpp.cub, "
                  "2.53 GB/sheet) was NOT ingested: licence unresolved. The FGDC "
                  "metadata inside the USGS sheet docx declares accconst=None and "
                  "useconst=None; no data.nasa.gov record exists for the product "
                  "(package_search 'themis thermal inertia' count 26, none match, "
                  "probed 2026-11-14); ckan.astrogeology.usgs.gov and "
                  "api.astrogeology.usgs.gov fail connections (HTTP 000). Per the "
                  "LICENCE-AUDIT-41 precedent (mars-geologic-map-sim3292), that is "
                  "not an explicit licence grant, so values were not used. The "
                  "FGDC .cub.docx evidence resource returned HTTP 404 on every "
                  "re-fetch of 2026-11-14 after one successful direct fetch "
                  "whose bytes did not persist, so no evidence file is "
                  "snapshotted; the constraint text is quoted in the registry "
                  "row. ti stays with TES (tes-mgs, 20 px/deg, prepared in #75) "
                  "at ~3 km/px.",
            "tsurf_max/tsurf_min/tsurf_range": "The THEMIS day/night controlled "
                  "mosaics are qualitative 8-bit brightness (USGS product "
                  "description: 'qualitative (8-bit) ... image mosaic'), never "
                  "kelvin, so they are kept as DN and not labelled temperature. "
                  "The MRO Mars Climate Sounder archive (mcs-mro, PDS Atmospheres) "
                  "holds only per-orbit ~4-hour EDR/DDR granules (2227 volumes, "
                  "e.g. DATA/2007/200702/20070201/2007020100_EDR.TAB) and no "
                  "Ls-binned static surface climatology, so under the "
                  "at-most-monthly rule MCS is probe-only; its EDR label and "
                  "DATASET.CAT are snapshotted as evidence. InSight 1.5 m air "
                  "temperature (INSIGHT-2017) stays the in-situ reference.",
        },
        "outputs": {},
    }
    tables = {}
    for phase in ("day", "night"):
        frames = []
        for site, (lat, lon_east) in sorted(SITES.items()):
            quad = quads[site][phase]
            with rasterio.open(fetch(DATASET, footprints[quad]["tif"])) as ds:
                if "49910" not in str(ds.crs):
                    raise ValueError(f"{quad}: unexpected CRS {ds.crs}")
                if ds.nodata != NODATA_DN or abs(abs(ds.transform.a) - PIXEL_METRES) > 1e-6:
                    raise ValueError(f"{quad}: unexpected nodata/pixel size "
                                     f"({ds.nodata}, {ds.transform.a})")
                frame, win = read_site_pixels(ds, quad, phase, site, lat, lon_east)
            report["sites"][site]["windows"][phase] = win
            frames.append(frame)
        table = pl.concat(frames, rechunk=True).sort(["site", "quad",
                                                      "source_line", "source_sample"])
        path = OUT / f"themis-ir-{phase}-rois.parquet"
        pq.write_table(table.to_arrow(), path, compression="zstd")
        tables[phase] = table
        report["outputs"][path.name] = {
            "rows": table.height, "bytes": path.stat().st_size, "sha256": sha256(path),
            "columns": TABLE_COLUMNS,
            "unit": "8-bit DN (qualitative IR brightness; NOT kelvin, NOT TIU)",
            "resolution": "100 m/pixel, native IAU_2015:49910 simple-cylindrical grid",
            "siteStats": {site: pixel_stats(frame)
                          for site, frame in zip(sorted(SITES), frames)},
        }
    report["crossCheck"] = tes_diagnostic(tables["night"])
    (OUT / "preparation-report.json").write_text(json.dumps(report, indent=2) + "\n")
    return report


def raw_pixel(path: Path, line: int, sample: int) -> int:
    with rasterio.open(path) as ds:
        return int(ds.read(1, window=rasterio.windows.Window(sample, line, 1, 1))[0, 0])


def run_spot_checks(footprints: dict, tables: dict[str, pl.DataFrame]) -> list[dict]:
    """Compare table pixels with raw COG values at the same native coordinates."""
    results = []
    for phase in ("day", "night"):
        table = tables[phase]
        for site, lat, lon in SPOT_CHECKS:
            quad = table.filter(pl.col("site") == site)["quad"][0]
            path = quad_path(footprints, quad)
            with rasterio.open(path) as ds:
                line, sample = pixel_indices(lat, lon, ds.transform, ds.width, ds.height)
            raw = raw_pixel(path, line, sample)
            row = table.filter((pl.col("site") == site) & (pl.col("quad") == quad)
                               & (pl.col("source_line") == line)
                               & (pl.col("source_sample") == sample))
            if row.height != 1:
                raise ValueError(f"spot check: no exact table row for {site}/{phase} "
                                 f"@({lat},{lon}) line={line} sample={sample}")
            dn = row[VALUE_COLUMN][0]
            if row["missing_reason"][0] is None:
                ok = dn is not None and raw == dn and raw != NODATA_DN
            else:
                ok = raw == NODATA_DN and dn is None
            if not ok:
                raise ValueError(f"spot check mismatch {site}/{phase} @({lat},{lon}) "
                                 f"line={line} sample={sample}: table={dn} raw={raw}")
            results.append({"site": site, "phase": phase, "line": line,
                            "sample": sample, "raw": raw, "table": dn, "match": True})
    return results


def check() -> None:
    verify_value_inputs()
    report = json.loads((OUT / "preparation-report.json").read_text())
    for name, meta in report["outputs"].items():
        path = OUT / name
        if sha256(path) != meta["sha256"] or path.stat().st_size != meta["bytes"]:
            raise ValueError(f"output hash/size mismatch: {name}")
        if pq.ParquetFile(path).metadata.num_rows != meta["rows"]:
            raise ValueError(f"output row count mismatch: {name}")
    selection = select_quads()
    footprints = selection["footprints"]
    tables = {}
    for phase in ("day", "night"):
        name = f"themis-ir-{phase}-rois.parquet"
        path = OUT / name
        table = pl.read_parquet(path)
        if table.columns != TABLE_COLUMNS:
            raise ValueError(f"{name}: columns changed: {table.columns}")
        dupes = (table.height
                 - table.select(pl.struct(["site", "phase", "source_line",
                                           "source_sample"]).n_unique()).item())
        if dupes:
            raise ValueError(f"{name}: {dupes} duplicate keys")
        nulls = table.filter(pl.col(VALUE_COLUMN).is_null())
        valid = table.filter(pl.col(VALUE_COLUMN).is_not_null())
        if valid.filter(pl.col("missing_reason").is_not_null()).height:
            raise ValueError(f"{name}: missing_reason present on valid pixels")
        if nulls.filter(pl.col("missing_reason") != MISSING_NO_DATA).height:
            raise ValueError(f"{name}: missing_reason does not match the null column")
        if valid.filter(pl.col(VALUE_COLUMN).is_between(NODATA_DN, 255).not_()).height:
            raise ValueError(f"{name}: DN outside the 8-bit range")
        if table.filter((pl.col("lat_pc_deg").abs() > 90.0)
                        | (pl.col("lon_east_deg").ge(360.0))
                        | (pl.col("lon_east_deg").lt(0.0))).height:
            raise ValueError(f"{name}: coordinates outside physical range")
        tables[phase] = table
    results = run_spot_checks(footprints, tables)
    if len(results) < len(SITES):  # >= 5 spot checks required
        raise ValueError("too few spot checks executed")
    cross = report.get("crossCheck") or {}
    if cross.get("status") == "ok":
        for site, info in cross["sites"].items():
            for convention in ("east_0_360", "west_0_360"):
                rho = (info.get(convention) or {}).get("spearmanNightDnVsTesTi")
                if rho is not None and not -1.0 <= rho <= 1.0:
                    raise ValueError(f"cross-check rho out of range: {site}/{convention}")
    for phase in ("day", "night"):
        print(f"PASS themis-ir-{phase}-rois.parquet: "
              f"{report['outputs'][f'themis-ir-{phase}-rois.parquet']['rows']:,} rows; "
              f"hash, size, keys, ranges, missing reasons")
    print(f"PASS spot checks: {len(results)} raw-vs-table comparisons "
          f"({len(results) // 2} sites x day/night)")


_TRANSIENT = ("Errno -3", "Temporary failure", "NameResolutionError",
              "ConnectionError", "connection reset", "timed out")


def fetch_with_retry(dataset: str, url: str, attempts: int = 6):
    """Retry transient DNS/network failures with backoff before giving up."""
    delay = 20.0
    for i in range(1, attempts + 1):
        try:
            return fetch(dataset, url)
        except Exception as e:
            if i == attempts or not any(t in str(e) for t in _TRANSIENT):
                raise
            print(f"transient error ({e}); retry {i}/{attempts - 1} in {delay:.0f}s",
                  flush=True)
            time.sleep(delay)
            delay = min(delay * 2, 120.0)


def main():
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument("action", choices=["fetch", "build", "check"])
    action = parser.parse_args().action
    if action == "fetch":
        for dataset, url in sources():
            optional = url in OPTIONAL_URLS
            try:
                print(fetch_with_retry(dataset, url), flush=True)
            except Exception as e:
                if optional:
                    print(f"SKIPPED optional evidence ({dataset}) {url}: {e}", flush=True)
                else:
                    raise
    elif action == "build":
        report = build()
        for name, meta in report["outputs"].items():
            print(name, meta["rows"], meta["sha256"], flush=True)
    else:
        check()


if __name__ == "__main__":
    main()
