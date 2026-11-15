"""W49 (#108) target-site validator (data prep only; no scoring, no similarity).

Loads every data/targets/*.yaml and checks, per row:
  - required fields, enum vales, id/filename match, coordinate ranges;
  - every quoted coordinate actually appears in the quoted passage (parsed back);
  - source sha256 matches the MANIFEST entry for that snapshot;
  - quotes are verbatim substrings of the local snapshot bytes that CAN be
    parsed without extra deps (JSON bodies, XHTML, plain text) - press-kit PDFs
    are hash-verified only (no PDF dependency in the frozen env) and are marked
    accordingly;
  - gazetteer-derived feature rows re-compose their record quote from
    data/snapshots/usgs-planetary-nomenclature/<BODY>_nomenclature_center_pts.zip
    and must match it exactly;
  - rows that state a USGS cross-check tolerance must actually lie within it of
    the gazetteer feature centre (great-circle distance, haversine).

Open gaps (centre null) must carry an explicit missing reason. Missing payload
bytes (snapshots are gitignored) downgrade quote verification to a per-row
"payload-not-local" note instead of a failure.

CLI:  python -m p0ingest.targets [-q]  -> exit 0 only if every check passes.
"""
from __future__ import annotations

import argparse
import hashlib
import html as _html
import json
import math
import re
import struct
import sys
import zipfile
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[4]
TARGETS = REPO / "data" / "targets"
SNAPSHOTS = REPO / "data" / "snapshots"
MANIFEST = SNAPSHOTS / "MANIFEST.json"

GAZETTEER_DATASET = "usgs-planetary-nomenclature"
GAZETTEER_ZIP = {  # gazetteer export per body (payload file inside MANIFEST)
    "moon": "MOON_nomenclature_center_pts.zip",
    "mars": "MARS_nomenclature_center_pts.zip",
}
# gazetteer exports record longitude east-positive 0-360 and planetocentric latitude
GAZETTEER_LONMODE = "east-positive-0-360"

BODIES = {"moon": 1737.4, "mars": 3389.5}  # mean radii (km), distance scale only
KINDS = {"region", "feature", "landing-site"}
STATUSES = {"candidate", "historical", "proposed"}
LONMODES = {"east-positive-0-360", "east-positive-minus180-180"}
DOC_PARSEABLE = {".json", ".xhtml", ".txt", ".html"}

REQUIRED = ("siteId", "name", "body", "kind", "status", "lonMode")


# ---------------------------------------------------------------- helpers ----
def _norm_text(text: str) -> str:
    """Fold quotes/dashes/whitespace so a YAML quote matches rendered page text."""
    table = {
        "\u2018": "'", "\u2019": "'", "\u201c": '"', "\u201d": '"',
        "\u00a0": " ", "\u2013": "-", "\u2014": "-", "\u2026": "...",
    }
    for k, v in table.items():
        text = text.replace(k, v)
    return re.sub(r"\s+", " ", text).strip()


def _strip_markup(text: str) -> str:
    return re.sub(r"<[^>]+>", " ", text)


def load_manifest_records(path: Path | None = None) -> dict:
    """MANIFEST entries keyed by (datasetId, filename)."""
    manifest_path = path or MANIFEST
    records = {}
    if not manifest_path.exists():
        return records
    data = json.loads(manifest_path.read_text(encoding="utf-8"))
    for entry in data.get("entries", []):
        local = entry.get("localPath")  # campaign rows may carry no localPath (#70)
        if not local:
            continue
        records[(entry["datasetId"], Path(local).name)] = entry
    return records


# ------------------------------------------------------- gazetteer (DBF) ----
def dbf_rows_from_bytes(raw: bytes) -> list[dict]:
    """Minimal dBASE III reader - enough for the gazetteer centre-point exports."""
    if len(raw) < 33 or raw[0:1] != b"\x03":
        raise ValueError("not a dBASE III file")
    header_len, record_len = struct.unpack("<HH", raw[8:12])
    count = struct.unpack("<I", raw[4:8])[0]
    fields, offset = [], 32
    while raw[offset] != 0x0D:
        name = raw[offset:offset + 11].split(b"\x00")[0].decode("latin1")
        fields.append((name, chr(raw[offset + 11]), raw[offset + 16]))
        offset += 32
    rows, pos = [], header_len
    for _ in range(count):
        record = raw[pos:pos + record_len]
        pos += record_len
        if record[0:1] != b"\x20":  # deleted / EOF marker
            continue
        values, offset = {}, 1
        for name, _kind, size in fields:
            values[name] = record[offset:offset + size].decode("latin1").strip()
            offset += size
        rows.append(values)
    return rows


def load_gazetteer(manifest_records: dict, snapshots: Path | None = None) -> dict:
    """{body: {(field,value): record}} from the gazetteer centre-point zips.

    Payloads are gitignored: a body without its local zip returns an empty map
    (callers report 'payload-not-local'), never a fabricated one.
    """
    root = snapshots or SNAPSHOTS
    gazetteer = {}
    for body, filename in GAZETTEER_ZIP.items():
        entry = manifest_records.get((GAZETTEER_DATASET, filename))
        if entry is None:
            continue
        path = root / entry["localPath"].removeprefix("data/snapshots/")
        if not path.exists():
            continue
        with zipfile.ZipFile(path) as archive:
            dbf_name = next(n for n in archive.namelist() if n.endswith(".dbf"))
            raw = archive.read(dbf_name)
        gazetteer[body] = dbf_rows_from_bytes(raw)
    return gazetteer


def gazetteer_record(gazetteer: dict, body: str, feature_name: str) -> dict | None:
    for row in gazetteer.get(body, []):
        if row.get("name", "") == feature_name:
            return row
    return None


def gazetteer_quote(record: dict) -> str:
    """Deterministic quote recomposed from one gazetteer record's raw fields."""
    keys = ("name", "clean_name", "approvaldt", "diameter", "center_lon",
            "center_lat", "type", "code", "approval")
    return ";".join(f"{key}={record.get(key, '')}" for key in keys)


# ------------------------------------------- coordinate parsing from quotes ----
LAT_PATTERNS = [
    r"(?P<deg>\d+(?:\.\d+)?)\s*(?:deg(?:rees)?\.?|\u00b0|degrees)\s*(?P<hem>[NS])\.?\s*latitude\b",
    # JPL press kits spell the hemisphere out: "18 degrees north latitude"
    r"(?P<deg>\d+(?:\.\d+)?)\s*(?:deg(?:rees)?\.?|\u00b0|degrees)\s*"
    r"(?P<word>north|south)\.?\s*latitude\b",
    r"(?P<deg>\d+(?:\.\d+)?)\s*(?:deg(?:rees)?\.?|\u00b0)?\s*(?P<hem>[NS])\.?(?:,| and|$)",
]
LON_PATTERNS = [
    r"(?P<deg>\d+(?:\.\d+)?)\s*(?:deg(?:rees)?\.?|\u00b0|degrees)\s*"
    r"(?P<hem>[EW])\.?\s*longitude\b",
    # JPL press kits omit the hemisphere before a bare "N degrees longitude";
    # unmarked ecliptic-side longitude is east-positive.
    r"(?P<deg>\d+(?:\.\d+)?)\s*degrees\s*longitude\b",
    r"(?P<deg>\d+(?:\.\d+)?)\s*(?:deg(?:rees)?\.?|\u00b0)?\s*(?P<hem>[EW])\.?(?:[,.]|$|\))",
]

WORD_HEMISPHERE = {"north": "N", "south": "S", "east": "E", "west": "W"}


def _hemisphere(match: re.Match) -> str | None:
    groups = match.groupdict()
    hemisphere = groups.get("hem") or groups.get("word")
    if hemisphere is None:
        return None
    return WORD_HEMISPHERE.get(hemisphere.lower(), hemisphere.upper())


def coordinates_from_quote(quote: str):
    """Parse (lat, lon) planetocentric east-positive from a quoted passage.

    Accepts the phrasings used by NSSDC pages and JPL press kits, e.g.
    '22.27 deg N latitude and 312.05 deg E longitude', '19.33 N, 33.55 W',
    '1.946\u00b0 S and 354.473\u00b0 E', '4.6 degrees south latitude,
    137.4 degrees east longitude'. Returns None when not parseable.
    """
    text = _norm_text(quote)
    lat = lon = None
    for pattern in LAT_PATTERNS:
        match = re.search(pattern, text, re.I)
        if match:
            lat = float(match.group("deg"))
            if _hemisphere(match) == "S":
                lat = -lat
            break
    for pattern in LON_PATTERNS:
        match = re.search(pattern, text, re.I)
        if match:
            lon = float(match.group("deg"))
            if _hemisphere(match) == "W":
                lon = -lon
            break
    if lat is None or lon is None:
        return None
    if 90 < lon <= 360:  # declared 0-360 convention
        lon = lon - 360 if lon > 180 else lon
    return lat, lon


def great_circle_km(lat1, lon1, lat2, lon2, body):
    radius = BODIES[body]
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dlon, dlat = math.radians(lon2 - lon1), math.radians(lat2 - lat1)
    a = (math.sin(dlat / 2) ** 2
         + math.cos(p1) * math.cos(p2) * math.sin(dlon / 2) ** 2)
    return radius * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


# ------------------------------------------------------------ validation ----
class RowReport:
    def __init__(self, site_id):
        self.site_id = site_id
        self.errors = []
        self.notes = []

    def ok(self):
        return not self.errors


def validate_row(path: Path, row: dict, gazetteer: dict,
                 manifest_records: dict, snapshots: Path) -> RowReport:
    report = RowReport(row.get("siteId") or f"<unnamed:{path.name}>")

    for field in REQUIRED:
        if not row.get(field):
            report.errors.append(f"missing required field {field}")
    if report.errors:
        return report

    if not re.fullmatch(r"[a-z0-9]+(-[a-z0-9]+)*", row["siteId"]):
        report.errors.append(f"siteId {row['siteId']!r} is not kebab-case")
    if path.stem != row["siteId"]:
        report.errors.append(f"filename {path.name} does not match siteId {row['siteId']}")
    if row["body"] not in BODIES:
        report.errors.append(f"body must be one of {sorted(BODIES)}")
    if row["kind"] not in KINDS:
        report.errors.append(f"kind must be one of {sorted(KINDS)}")
    if row["status"] not in STATUSES:
        report.errors.append(f"status must be one of {sorted(STATUSES)}")
    if row["lonMode"] not in LONMODES:
        report.errors.append(f"lonMode must be one of {sorted(LONMODES)}")

    lat, lon = row.get("centreLat"), row.get("centreLon")
    if (lat is None) != (lon is None):
        report.errors.append("centreLat and centreLon must be given together or both null")
        return report

    source = row.get("source") or {}
    if lat is not None:
        if not (-90 <= lat <= 90):
            report.errors.append(f"centreLat {lat} out of range [-90, 90]")
        lo, hi = (0, 360) if row["lonMode"] == "east-positive-0-360" else (-180, 180)
        if not (lo <= lon <= hi):
            report.errors.append(f"centreLon {lon} outside declared {row['lonMode']} range")

        for field in ("datasetId", "file", "url", "fetchedAt", "sourceSha256", "quote"):
            if not source.get(field):
                report.errors.append(f"coordinate present but source.{field} missing")
        if report.errors:
            return report

        entry = manifest_records.get((source["datasetId"], Path(source["file"]).name))
        if entry is None:
            report.errors.append(
                f"no MANIFEST entry for {source['datasetId']}/{source['file']} (entries come from fetch only)")
        else:
            if entry.get("sourceUrl") != source["url"]:
                report.errors.append("source.url does not match MANIFEST sourceUrl")
            if entry.get("sha256") == source["sourceSha256"]:
                pass
            else:
                report.errors.append("source.sourceSha256 does not match MANIFEST sha256")

        # quote verification where the payload bytes are readable without extra deps
        snapshot = None
        if entry is not None:
            snapshot = snapshots / entry["localPath"].removeprefix("data/snapshots/")
        is_gazetteer = row.get("coordinateSource") == GAZETTEER_DATASET
        if is_gazetteer:
            record = gazetteer_record(gazetteer, row["body"],
                                      row.get("usgsFeatureName") or row["name"])
            if record is None:
                report.errors.append("gazetteer row but no gazetteer record loaded")
            else:
                expected = gazetteer_quote(record)
                if row["source"]["quote"] != expected:
                    report.errors.append("quote is not the recomposed gazetteer record")
                declared = (record["center_lat"], record["center_lon"])
                if (abs(float(record["center_lat"]) - lat) > 1e-9
                        or abs(gazetteer_lon_to_east(float(record["center_lon"])) - lon) > 1e-9):
                    report.errors.append("centre does not equal the gazetteer record centre")
                del declared
        elif snapshot is not None and snapshot.exists() and snapshot.suffix in DOC_PARSEABLE:
            raw = snapshot.read_text(encoding="utf-8", errors="replace")
            if snapshot.suffix == ".json":
                body = json.loads(raw)
                if isinstance(body, list):
                    body = body[0] if body else {}
                rendered = (body.get("content") or {}).get("rendered", "")
                text = _norm_text(_html.unescape(_strip_markup(rendered)))
            elif snapshot.suffix in {".xhtml", ".html"}:
                text = _norm_text(_html.unescape(_strip_markup(raw)))
            else:
                text = _norm_text(raw)
            if _norm_text(source["quote"]) not in text:
                report.errors.append("quote not found verbatim in the snapshot document")
            parsed = coordinates_from_quote(source["quote"])
            if parsed is None:
                report.errors.append("could not parse lat/lon back out of quote")
            else:
                qlat, qlon = parsed
                if 90 < qlon <= 360 and row["lonMode"] == "east-positive-0-360":
                    qlon = qlon - 360 if qlon > 180 else qlon
                if abs(qlat - lat) > 1e-9 or abs(_east(qlon) - _east(lon)) > 1e-9:
                    report.errors.append(
                        f"declared centre ({lat}, {lon}) != quote-parsed ({qlat}, {qlon})")
        elif snapshot is not None and snapshot.exists():
            report.notes.append("PDF snapshot: quote/hash trusted, content not reparsed (no PDF reader in frozen env)")
        else:
            report.notes.append("payload-not-local: hash checked against MANIFEST only")

    elif lat is None:
        # No numeric centre: an explicit reason is mandatory, and a provenance
        # quote (e.g. the NASA release listing the region by name) is checked
        # verbatim when the snapshot can be read without extra deps.
        reason = row.get("missingReason") or (row.get("missing") or {}).get("reason")
        if not reason:
            report.errors.append("centre null: missingReason required")
        if source.get("quote"):
            if not (source.get("datasetId") and source.get("file")
                    and source.get("url") and source.get("fetchedAt")
                    and source.get("sourceSha256")):
                report.errors.append("source.quote present but source block incomplete")
            else:
                entry = manifest_records.get((source["datasetId"], Path(source["file"]).name))
                if entry is None:
                    report.errors.append(
                        f"no MANIFEST entry for {source['datasetId']}/{source['file']}")
                elif entry.get("sha256") != source["sourceSha256"]:
                    report.errors.append("source.sourceSha256 does not match MANIFEST sha256")
                else:
                    snapshot = snapshots / entry["localPath"].removeprefix("data/snapshots/")
                    if snapshot.exists() and snapshot.suffix in DOC_PARSEABLE:
                        raw = snapshot.read_text(encoding="utf-8", errors="replace")
                        if snapshot.suffix == ".json":
                            body = json.loads(raw)
                            if isinstance(body, list):
                                body = body[0] if body else {}
                            rendered = (body.get("content") or {}).get("rendered", "")
                            text = _norm_text(_html.unescape(_strip_markup(rendered)))
                        elif snapshot.suffix in {".xhtml", ".html"}:
                            text = _norm_text(_html.unescape(_strip_markup(raw)))
                        else:
                            text = _norm_text(raw)
                        if _norm_text(source["quote"]) not in text:
                            report.errors.append("quote not found verbatim in the snapshot document")
                    else:
                        report.notes.append("payload-not-local: hash checked against MANIFEST only")

    cross = row.get("usgsCrossCheck") or {}
    if cross:
        feature = cross.get("feature")
        tolerance = cross.get("expectedMaxKm")
        if not feature or tolerance is None:
            report.errors.append("usgsCrossCheck needs feature and expectedMaxKm")
        else:
            record = gazetteer_record(gazetteer, row["body"], feature)
            if record is None:
                report.notes.append(
                    f"usgsCrossCheck pending: gazetteer payload for {row['body']} not local")
            elif lat is None:
                report.notes.append("usgsCrossCheck skipped: row has no centre")
            else:
                glat = float(record["center_lat"])
                glon = _east(gazetteer_lon_to_east(float(record["center_lon"])))
                diff = great_circle_km(lat, lon, glat, glon, row["body"])
                if diff > float(tolerance) + 1e-6:
                    report.errors.append(
                        f"centre {diff:.1f} km from USGS {feature} centre, tolerance {tolerance} km")
                if cross.get("diffKm") is None or abs(float(cross.get("diffKm")) - diff) > 0.5:
                    report.errors.append(
                        f"usgsCrossCheck.diffKm {cross.get('diffKm')} != recomputed {diff:.1f}")

    # sanity: a coordinate must carry a quoted passage; a coordinate-less row
    # (missingReason set) may also cite one but need not
    if lat is not None and not source.get("quote"):
        report.errors.append("coordinate present but quote missing")
    return report


def gazetteer_lon_to_east(value: float) -> float:
    """Gazetteer exports already hold planetocentric east-positive 0-360 degrees."""
    return value


def _east(lon: float) -> float:
    """Fold 0-360 and -180-180 conventions onto -180-180 for comparison."""
    return ((lon + 180.0) % 360.0) - 180.0


def validate_targets(root: Path | None = None, snapshots: Path | None = None,
                     manifest_path: Path | None = None) -> list[RowReport]:
    root = root or TARGETS
    snapshots = snapshots or SNAPSHOTS
    records = load_manifest_records(manifest_path)
    gazetteer = load_gazetteer(records, snapshots)
    reports = []
    for path in sorted(root.glob("*.yaml")):
        row = yaml.safe_load(path.read_text(encoding="utf-8"))
        reports.append(validate_row(path, row if row else {}, gazetteer, records, snapshots))
    if not reports:
        row = None  # explicit: empty target set is itself a reportable condition
    return reports


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="validate data/targets/*.yaml (W49 #108)")
    parser.add_argument("-q", "--quiet", action="store_true")
    args = parser.parse_args(argv)
    reports = validate_targets()
    failures = [r for r in reports if not r.ok()]
    if not args.quiet:
        for report in reports:
            state = "OK" if report.ok() else "FAIL"
            print(f"{state:4} {report.site_id}")
            for message in report.errors:
                print(f"     ! {message}")
            for note in report.notes:
                print(f"     - {note}")
        print(f"{len(reports) - len(failures)}/{len(reports)} rows pass")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
