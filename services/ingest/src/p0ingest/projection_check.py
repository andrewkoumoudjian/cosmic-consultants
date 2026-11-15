"""Independent geographic-placement checks for the native planetary products (#74).

The TES DSMAP catalog gives LINE/SAMPLE equations whose signs contradict its own
"pixel (1,1) is the north-west corner" text. Nothing here picks one by assumption:
each candidate pixel-to-coordinate mapping is scored against independent data.

* MOLA MEGDR topography is itself first checked against the USGS/IAU Gazetteer
  (named montes must sit high, named planitiae low) before it is used as reference.
* TES: 4 axis-flip candidates are scored by the correlation of fine-scale
  (high-pass) log thermal inertia with fine-scale MOLA elevation (night map), and
  the day map is checked against the night map under each candidate. A shift scan
  against 16 px/deg MOLA then measures the remaining apparent offset; it is
  reported as an open finding, never applied as a correction.
* Diviner PRP: centre lat/lon/alt are recomputed from the three body-fixed vertex
  coordinates, and named south-polar craters (gazetteer) are tested for cold floors
  relative to their surroundings, against an east/west-mirrored control.

Outputs placement evidence only. No values are changed, resampled into tables or
compared across bodies. Run: python -m p0ingest.projection_check fetch|run
"""
from __future__ import annotations

import argparse
import io
import json
import re
import struct
import sys
import zipfile
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import polars as pl

from .snapshots import SNAP, fetch, load_manifest, sha256

OUT = SNAP / "_derived" / "planetary" / "projection-check.json"
MOLA = "https://pds-geosciences.wustl.edu/mgs/mgs-m-mola-5-megdr-l3-v1/mgsl_300x/"
NAMES = "https://planetarynames.wr.usgs.gov/shapefiles/"
TES_RES = 20  # px/deg, from the TES label MAP_RESOLUTION
MOON_RADIUS_KM = 1737.4

CANDIDATES = {
    # name: (flip_lines, flip_samples) relative to "line 1 = north edge, sample 1 = 180 W"
    "label-text: line1=north, sample1=west(-180)": (False, False),
    "dsmap-equations: line1=south, sample1=east(+180)": (True, True),
    "lat-flip only: line1=south, sample1=west": (True, False),
    "lon-flip only: line1=north, sample1=east": (False, True),
}


def sources():
    for folder, stem in (("meg004/", "megt90n000cb"), ("meg016/", "megt90n000eb")):
        for ext in ("lbl", "img"):
            yield "mola-megdr", MOLA + folder + stem + "." + ext
    for body in ("MOON", "MARS"):
        yield "usgs-planetary-nomenclature", NAMES + body + "_nomenclature_center_pts.zip"


def local(dataset: str, name: str) -> Path:
    """Return a snapshot path after checking its bytes against MANIFEST (rule 3)."""
    path = SNAP / dataset / name
    rel = f"data/snapshots/{dataset}/{name}"
    entry = next((e for e in load_manifest()["entries"] if e.get("localPath") == rel), None)
    if entry is None or not path.exists():
        raise SystemExit(f"missing snapshot {rel}; run fetch")
    if sha256(path) != entry["sha256"]:
        raise SystemExit(f"hash mismatch for {rel}")
    return path


# ---------------------------------------------------------------- readers

def pds3_image(img: Path, lbl: Path, dtype: str = ">i2") -> np.ndarray:
    text = lbl.read_text(errors="replace")
    lines = int(re.search(r"^\s*LINES\s*=\s*(\d+)", text, re.M).group(1))
    samples = int(re.search(r"^\s*LINE_SAMPLES\s*=\s*(\d+)", text, re.M).group(1))
    if "MSB_INTEGER" not in text or img.stat().st_size != lines * samples * 2:
        raise ValueError(f"{img.name}: byte layout differs from label")
    return np.memmap(img, dtype=dtype, mode="r", shape=(lines, samples))


def mola_grid(stem: str) -> tuple[np.ndarray, int]:
    lbl = local("mola-megdr", stem + ".lbl")
    text = lbl.read_text(errors="replace")
    res = int(float(re.search(r"MAP_RESOLUTION\s*=\s*([\d.]+)", text).group(1)))
    west = float(re.search(r"WESTERNMOST_LONGITUDE\s*=\s*([-\d.]+)", text).group(1))
    if west != 0.0 or "POSITIVE_LONGITUDE_DIRECTION = \"EAST\"" not in text:
        raise ValueError("unexpected MOLA longitude convention")
    return np.asarray(pds3_image(local("mola-megdr", stem + ".img"), lbl), dtype=np.float32), res


def dbf_records(raw: bytes, wanted: list[str]) -> list[dict]:
    """Minimal dBASE III reader (the gazetteer ships a .dbf attribute table)."""
    count, header_len, record_len = struct.unpack("<IHH", raw[4:12])
    fields, pos = [], 32
    while raw[pos] != 0x0D:
        name = raw[pos:pos + 11].split(b"\0")[0].decode()
        fields.append((name, chr(raw[pos + 11]), raw[pos + 16]))
        pos += 32
    out = []
    for i in range(count):
        rec = raw[header_len + i * record_len: header_len + (i + 1) * record_len]
        if rec[:1] == b"*":
            continue
        row, off = {}, 1
        for name, kind, length in fields:
            value = rec[off:off + length].decode("utf-8", "replace").strip()
            off += length
            if name in wanted:
                row[name] = float(value) if kind in "NF" and value else (value or None)
        out.append(row)
    return out


def gazetteer(body: str) -> list[dict]:
    path = local("usgs-planetary-nomenclature", f"{body}_nomenclature_center_pts.zip")
    with zipfile.ZipFile(path) as z:
        name = next(n for n in z.namelist() if n.endswith(".dbf"))
        raw = z.read(name)
    fields = []
    pos = 32
    while raw[pos] != 0x0D:
        fields.append(raw[pos:pos + 11].split(b"\0")[0].decode())
        pos += 32
    need = {"name": _pick(fields, ["clean_name", "name"]), "lat": _pick(fields, ["center_lat"]),
            "lon": _pick(fields, ["center_lon"]), "diameter": _pick(fields, ["diameter"]),
            "type": _pick(fields, ["type"]), "status": _pick(fields, ["approval"])}
    rows = dbf_records(raw, [v for v in need.values() if v])
    return [{k: r.get(v) for k, v in need.items() if v} for r in rows]


def _pick(fields: list[str], options: list[str]) -> str | None:
    lower = {f.lower(): f for f in fields}
    return next((lower[o] for o in options if o in lower), None)


# ---------------------------------------------------------------- numerics

def box_mean(a: np.ndarray, k: int) -> np.ndarray:
    """NaN-aware k x k box mean (longitude wraps, latitude clamps)."""
    valid = np.isfinite(a)
    filled = np.where(valid, a, 0.0).astype(np.float64)
    pad = k // 2
    def blur(x):
        x = np.concatenate([x[:, -pad:], x, x[:, :pad]], axis=1)
        x = np.pad(x, ((pad, pad), (0, 0)), mode="edge")
        c = np.cumsum(np.cumsum(np.pad(x, ((1, 0), (1, 0))), axis=0), axis=1)
        return c[k:, k:] - c[:-k, k:] - c[k:, :-k] + c[:-k, :-k]
    total, n = blur(filled), blur(valid.astype(np.float64))
    with np.errstate(invalid="ignore", divide="ignore"):
        return np.where(n > 0, total / n, np.nan)


def highpass(a: np.ndarray, k: int) -> np.ndarray:
    return a - box_mean(a, k)


def corr(a: np.ndarray, b: np.ndarray, keep: np.ndarray) -> tuple[float, int]:
    ok = keep & np.isfinite(a) & np.isfinite(b)
    n = int(ok.sum())
    if n < 1000:
        return float("nan"), n
    return float(np.corrcoef(a[ok], b[ok])[0, 1]), n


def block_nanmean(a: np.ndarray, f: int) -> np.ndarray:
    h, w = a.shape[0] // f, a.shape[1] // f
    v = a[:h * f, :w * f].reshape(h, f, w, f)
    with np.errstate(invalid="ignore"):
        return np.nanmean(np.nanmean(v, axis=3), axis=1) if np.isfinite(v).any() else v.mean(axis=(1, 3))


def tes_log_ti(kind: str) -> np.ndarray:
    from .planetary import read_tes_image
    v = read_tes_image(local("tes-mgs", f"global_ti_{kind}_2007.img"), local("tes-mgs", f"global_ti_{kind}_2007.lbl"))
    m = read_tes_image(local("tes-mgs", f"global_ti_msk_{kind}_2007.img"), local("tes-mgs", f"global_ti_msk_{kind}_2007.lbl"))
    v = np.asarray(v, dtype=np.float32)
    keep = (np.asarray(m) == 1) & (v >= 5) & (v <= 5000)  # same rule as planetary.clean_tes
    return np.where(keep, np.log10(np.where(keep, v, 1)), np.nan).astype(np.float32)


def orient(a: np.ndarray, flips: tuple[bool, bool]) -> np.ndarray:
    """Return a north-up, west(-180)-left view of a TES array under a candidate mapping."""
    if flips[0]:
        a = a[::-1, :]
    if flips[1]:
        a = a[:, ::-1]
    return a


def mola_to_pm180(z: np.ndarray) -> np.ndarray:
    """MOLA columns start at 0 E; roll so they start at 180 W like the TES label text."""
    return np.roll(z, z.shape[1] // 2, axis=1)


def bilinear(z: np.ndarray, res: int, lat: np.ndarray, lon: np.ndarray) -> np.ndarray:
    """Sample a north-up 0..360E MOLA grid with pixel centres at (90-(r+.5)/res, (c+.5)/res)."""
    fr = (90.0 - lat) * res - 0.5
    fc = np.mod(lon, 360.0) * res - 0.5
    r0 = np.clip(np.floor(fr).astype(np.int64), 0, z.shape[0] - 2)
    c0 = np.floor(fc).astype(np.int64)
    dr, dc = np.clip(fr - r0, 0, 1), fc - c0
    c0 %= z.shape[1]
    c1 = (c0 + 1) % z.shape[1]
    return ((1 - dr) * (1 - dc) * z[r0, c0] + (1 - dr) * dc * z[r0, c1]
            + dr * (1 - dc) * z[r0 + 1, c0] + dr * dc * z[r0 + 1, c1])


# ---------------------------------------------------------------- checks

def mola_reference(z4: np.ndarray, res: int, mars: list[dict]) -> dict:
    """MOLA orientation from named features: montes high, planitiae low, only for the true mapping."""
    def classify(t):
        t = (t or "").lower()
        return "high" if t.startswith("mons") or t.startswith("montes") or t == "tholus" else \
               "low" if t.startswith("planitia") else None
    feats = [f for f in mars if classify(f.get("type")) and f.get("lat") is not None and f.get("lon") is not None
             and (f.get("diameter") or 0) >= 100]
    lat = np.array([f["lat"] for f in feats])
    lon = np.array([f["lon"] for f in feats]) % 360
    high = np.array([classify(f["type"]) == "high" for f in feats])
    results = {}
    for name, (fl, fs) in CANDIDATES.items():
        zz = z4[::-1] if fl else z4
        zz = zz[:, ::-1] if fs else zz
        e = bilinear(zz.astype(np.float64), res, lat, lon)
        results[name] = {"meanHighFeatures_m": float(e[high].mean()), "meanLowFeatures_m": float(e[~high].mean()),
                         "fractionHighAboveAllLowMedian": float((e[high] > np.median(e[~high])).mean())}
    named = {}
    for target in ("Olympus Mons", "Hellas Planitia", "Arsia Mons", "Elysium Mons"):
        f = next((x for x in mars if x.get("name") == target), None)
        if f:
            named[target] = {"lat": f["lat"], "lon": f["lon"],
                             "mola_m": float(bilinear(z4.astype(np.float64), res, np.array([f["lat"]]), np.array([f["lon"]]))[0])}
    return {"features": {"high": int(high.sum()), "low": int((~high).sum()),
                         "filter": "gazetteer type Mons/Montes/Tholus vs Planitia, diameter >= 100 km"},
            "candidates": results, "namedFeatures": named}


def tes_orientation(z4: np.ndarray, kinds=("day", "night")) -> dict:
    zref = mola_to_pm180(z4)  # north-up, -180..180
    lat4 = 90 - (np.arange(zref.shape[0]) + 0.5) / 4
    keep = np.abs(lat4)[:, None] < 60
    keep = np.broadcast_to(keep, zref.shape)
    zhp = highpass(zref.astype(np.float64), 9)
    out = {}
    for kind in kinds:
        ti = tes_log_ti(kind)
        per = {}
        for name, flips in CANDIDATES.items():
            t4 = block_nanmean(orient(ti, flips), TES_RES // 4)
            r, n = corr(highpass(t4, 9), zhp, keep)
            per[name] = {"highpassPearsonR": r, "pixels": n}
        ranked = sorted(per, key=lambda k: -abs(per[k]["highpassPearsonR"]))
        out[kind] = {"candidates": per, "best": ranked[0],
                     "bestOverRunnerUpAbsR": abs(per[ranked[0]]["highpassPearsonR"]) / max(abs(per[ranked[1]]["highpassPearsonR"]), 1e-9)}
    return out


def tes_day_vs_night() -> dict:
    """Day and night maps share one label; the day map should agree with night only under one mapping."""
    rows = slice(600, 3000)
    night = highpass(tes_log_ti("night")[rows].astype(np.float64), 15)
    day = tes_log_ti("day")
    per = {}
    for name, flips in CANDIDATES.items():
        r, n = corr(highpass(orient(day, flips)[rows].astype(np.float64), 15), night, np.ones(night.shape, bool))
        per[name] = {"highpassPearsonR": r, "pixels": n}
    ranked = sorted(per, key=lambda k: -abs(per[k]["highpassPearsonR"]))
    return {"candidates": per, "best": ranked[0],
            "bestOverRunnerUpAbsR": abs(per[ranked[0]]["highpassPearsonR"]) / max(abs(per[ranked[1]]["highpassPearsonR"]), 1e-9)}


def tes_offset_scan(z16: np.ndarray, flips: tuple[bool, bool], kind: str, k: int = 45,
                    shifts=tuple(range(-12, 13))) -> dict:
    """High-pass correlation vs whole-pixel shift of the 16 px/deg MOLA sample point.

    The peak is an apparent offset, not a registration fix: thermal inertia also
    responds to slope aspect, and TES (IAU 1991) and MOLA use different Mars
    coordinate frames. Both shift the peak; neither is corrected here."""
    ti = orient(tes_log_ti(kind), flips)
    rows = slice(600, 3000)
    t = highpass(ti[rows].astype(np.float64), k)
    keep = np.ones(t.shape, bool)
    i, j = np.arange(rows.start, rows.stop), np.arange(ti.shape[1])
    lat0, lon0 = 90 - (i + 0.5) / TES_RES, -180 + (j + 0.5) / TES_RES
    def score(dlat, dlon):
        lat = (lat0 + dlat / TES_RES)[:, None] * np.ones((1, len(j)))
        lon = np.ones((len(i), 1)) * (lon0 + dlon / TES_RES)[None, :]
        return corr(t, highpass(bilinear(z16, 16, lat, lon), k), keep)[0]
    lat_curve = {s: score(s, 0) for s in shifts}
    lon_curve = {s: score(0, s) for s in shifts}
    def peak(curve):
        return max(curve, key=lambda s: abs(curve[s]))
    ew = highpass(np.gradient(bilinear(z16, 16, lat0[:, None] * np.ones((1, len(j))), np.ones((len(i), 1)) * lon0[None, :]), axis=1), k)
    return {"product": kind, "highpassBoxPx": k,
            "convention": "positive shift = MOLA sampled north/east of the label-text pixel centre, in TES pixels (0.05 deg)",
            "latShiftCurve": {str(s): v for s, v in lat_curve.items()},
            "lonShiftCurve": {str(s): v for s, v in lon_curve.items()},
            "latPeakShiftPx": peak(lat_curve), "lonPeakShiftPx": peak(lon_curve),
            "peakAtScanEdge": {"lat": abs(peak(lat_curve)) == max(shifts), "lon": abs(peak(lon_curve)) == max(shifts)},
            "corrWithEastWestSlope": corr(t, ew, keep)[0]}


def diviner_checks(moon: list[dict]) -> dict:
    from .planetary import read_character_label, character_batches
    tab, xml = local("diviner-l4", "dlre_prp_south.tab"), local("diviner-l4", "dlre_prp_south.xml")
    spec = read_character_label(xml)
    cols = ["tri1_x", "tri1_y", "tri1_z", "tri2_x", "tri2_y", "tri2_z", "tri3_x", "tri3_y", "tri3_z",
            "tri_clon", "tri_clat", "tri_calt", "temp_max"]
    frame = pl.concat([b.select(cols) for b in character_batches(tab, spec, 500_000)])
    x = (frame["tri1_x"] + frame["tri2_x"] + frame["tri3_x"]).to_numpy() / 3
    y = (frame["tri1_y"] + frame["tri2_y"] + frame["tri3_y"]).to_numpy() / 3
    z = (frame["tri1_z"] + frame["tri2_z"] + frame["tri3_z"]).to_numpy() / 3
    r = np.sqrt(x * x + y * y + z * z)
    lon = np.degrees(np.arctan2(y, x))
    lat = np.degrees(np.arcsin(z / r))
    clon, clat, calt = (frame[c].to_numpy() for c in ("tri_clon", "tri_clat", "tri_calt"))
    dlon = np.abs((lon - clon + 180) % 360 - 180) * np.cos(np.radians(clat))
    geometry = {"rows": int(len(frame)), "latRange": [float(clat.min()), float(clat.max())],
                "lonRange": [float(clon.min()), float(clon.max())],
                "maxAbsLatDiff_deg": float(np.abs(lat - clat).max()),
                "p99AbsLatDiff_deg": float(np.quantile(np.abs(lat - clat), 0.99)),
                "maxAbsLonDiffTimesCosLat_deg": float(dlon.max()),
                "medianRadiusMinusAlt_km": float(np.median(r - calt)),
                "note": "centre recomputed as the mean of three body-fixed vertices; radius - altitude should equal the reference sphere"}
    # crater floor test in polar stereographic km (south pole), vs an east/west mirrored control
    def xy(la, lo):
        rho = 2 * MOON_RADIUS_KM * np.tan(np.radians(90 + la) / 2)
        return rho * np.cos(np.radians(lo)), rho * np.sin(np.radians(lo))
    px, py = xy(clat, clon)
    tmax = frame["temp_max"].to_numpy()
    cell = 5.0
    keys = np.floor(px / cell).astype(np.int64) * 100003 + np.floor(py / cell).astype(np.int64)
    order = np.argsort(keys)
    skeys = keys[order]
    def near(cx, cy, rad):
        idx = []
        for gx in range(int(np.floor((cx - rad) / cell)), int(np.floor((cx + rad) / cell)) + 1):
            for gy in range(int(np.floor((cy - rad) / cell)), int(np.floor((cy + rad) / cell)) + 1):
                k = gx * 100003 + gy
                lo_, hi_ = np.searchsorted(skeys, k), np.searchsorted(skeys, k, side="right")
                idx.append(order[lo_:hi_])
        idx = np.concatenate(idx) if idx else np.array([], int)
        d = np.hypot(px[idx] - cx, py[idx] - cy)
        return idx, d
    craters = [f for f in moon if (f.get("type") or "").lower().startswith("crater") and f.get("lat") is not None
               and f["lat"] <= clat.max() - 0.5 and 10 <= (f.get("diameter") or 0) <= 150]
    def floor_colder(la, lo, diam):
        cx, cy = xy(np.array([la]), np.array([lo]))
        rad = diam / 2
        idx, d = near(cx[0], cy[0], 2.5 * rad)
        inner, ring = tmax[idx[d <= 0.3 * rad]], tmax[idx[(d >= 1.5 * rad) & (d <= 2.5 * rad)]]
        if len(inner) < 5 or len(ring) < 20:
            return None
        return float(np.median(inner) - np.median(ring))
    true_d, mirror_d, used = [], [], []
    for c in craters:
        a = floor_colder(c["lat"], c["lon"], c["diameter"])
        b = floor_colder(c["lat"], -c["lon"], c["diameter"])
        if a is None or b is None:
            continue
        true_d.append(a); mirror_d.append(b); used.append(c["name"])
    true_d, mirror_d = np.array(true_d), np.array(mirror_d)
    craters_out = {"craters": len(used), "filter": "gazetteer craters 10-150 km inside PRP coverage",
                   "fractionFloorColderTrue": float((true_d < 0).mean()) if len(used) else None,
                   "fractionFloorColderMirroredLon": float((mirror_d < 0).mean()) if len(used) else None,
                   "medianFloorMinusRingTrue_K": float(np.median(true_d)) if len(used) else None,
                   "medianFloorMinusRingMirroredLon_K": float(np.median(mirror_d)) if len(used) else None,
                   "examples": dict(list(zip(used, [round(v, 1) for v in true_d]))[:12])}
    return {"geometry": geometry, "craterFloors": craters_out}


def run() -> int:
    checks = []
    def check(name, ok, detail=""):
        checks.append({"check": name, "pass": bool(ok), "detail": detail})
        print(("PASS  " if ok else "FAIL  ") + name + (f" | {detail}" if detail else ""), flush=True)
    mars, moon = gazetteer("MARS"), gazetteer("MOON")
    z4, r4 = mola_grid("megt90n000cb")
    z16, r16 = mola_grid("megt90n000eb")
    ref = mola_reference(z4, r4, mars)
    std = ref["candidates"]["label-text: line1=north, sample1=west(-180)"]
    others = [v for k, v in ref["candidates"].items() if not k.startswith("label-text")]
    gap = std["meanHighFeatures_m"] - std["meanLowFeatures_m"]
    check("MOLA standard orientation puts named montes above planitiae", gap > 5000 and all(
        gap > 2 * (o["meanHighFeatures_m"] - o["meanLowFeatures_m"]) for o in others), f"high-low={gap:.0f} m")
    tes = tes_orientation(z4, kinds=("night", "day"))
    night = tes["night"]
    check("TES night: one mapping clearly best vs MOLA", night["bestOverRunnerUpAbsR"] >= 3,
          f"best={night['best']}, r={night['candidates'][night['best']]['highpassPearsonR']:.3f}, ratio={night['bestOverRunnerUpAbsR']:.1f}")
    check("TES night best mapping is the label text, not the DSMAP equations", night["best"].startswith("label-text"), night["best"])
    dn = tes_day_vs_night()
    check("TES day agrees with night only under the same mapping", dn["best"].startswith("label-text") and dn["bestOverRunnerUpAbsR"] >= 3,
          f"best={dn['best']}, r={dn['candidates'][dn['best']]['highpassPearsonR']:.3f}, ratio={dn['bestOverRunnerUpAbsR']:.1f}")
    flips = CANDIDATES[night["best"]]
    offsets = {kind: tes_offset_scan(z16.astype(np.float64), flips, kind) for kind in ("night", "day")}
    findings = [{"finding": "TES apparent offset vs MOLA (unresolved, not corrected)",
                 "night": {"latPx": offsets["night"]["latPeakShiftPx"], "lonPx": offsets["night"]["lonPeakShiftPx"]},
                 "day": {"latPx": offsets["day"]["latPeakShiftPx"], "lonPx": offsets["day"]["lonPeakShiftPx"]},
                 "peakAtScanEdge": {kind: offsets[kind]["peakAtScanEdge"] for kind in offsets},
                 "meaning": "a peak at the scan edge is not an estimate (weak day-map signal); day and night peaks differ, so this is not one grid misregistration; slope-aspect response and the IAU 1991 (TES) vs MOLA frame difference both shift it. Treat TES placement as uncertain by up to the larger peak (in 0.05 deg pixels) until a cited frame transform is applied."}]
    for kind, o in offsets.items():
        print(f"INFO  TES {kind} apparent offset: lat {o['latPeakShiftPx']:+d} px, lon {o['lonPeakShiftPx']:+d} px, corr with E-W slope {o['corrWithEastWestSlope']:.3f}")
    div = diviner_checks(moon)
    g = div["geometry"]
    check("Diviner centre lat recomputed from vertices", g["maxAbsLatDiff_deg"] < 0.01, f"max {g['maxAbsLatDiff_deg']:.2e} deg")
    check("Diviner centre lon recomputed from vertices", g["maxAbsLonDiffTimesCosLat_deg"] < 0.01, f"max {g['maxAbsLonDiffTimesCosLat_deg']:.2e} deg")
    cf = div["craterFloors"]
    check("Diviner named crater floors colder than rims, beating mirrored control",
          cf["craters"] >= 10 and cf["fractionFloorColderTrue"] >= 0.7 and
          cf["fractionFloorColderTrue"] - cf["fractionFloorColderMirroredLon"] >= 0.2,
          f"n={cf['craters']}, true={cf['fractionFloorColderTrue']:.2f}, mirrored={cf['fractionFloorColderMirroredLon']:.2f}")
    inputs = {e["localPath"]: e["sha256"] for e in load_manifest()["entries"]
              if e.get("datasetId") in ("mola-megdr", "usgs-planetary-nomenclature", "tes-mgs", "diviner-l4")}
    report = {"generatedAt": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
              "module": "p0ingest.projection_check", "moduleSha256": sha256(Path(__file__)),
              "inputs": inputs, "molaReference": ref, "tesOrientation": tes, "tesDayVsNight": dn, "tesOffsetScan": offsets,
              "openFindings": findings, "diviner": div,
              "checks": checks, "allPass": all(c["pass"] for c in checks),
              "scope": "placement evidence only; no physical value changed, no target association made"}
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(report, indent=2) + "\n")
    print("ALL PASS" if report["allPass"] else "SOME CHECKS FAILED")
    return 0 if report["allPass"] else 1


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["fetch", "run"])
    args = ap.parse_args()
    if args.cmd == "fetch":
        for dataset, url in sources():
            print(fetch(dataset, url))
        return
    sys.exit(run())


if __name__ == "__main__":
    main()
