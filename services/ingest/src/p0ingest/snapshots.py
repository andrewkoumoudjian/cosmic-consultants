"""Download + hash + manifest. Payloads stay in data/snapshots/<datasetId>/ (gitignored);
data/snapshots/MANIFEST.json (tracked) records URL, fetch time, sha256, bytes and licence."""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
import shutil
import threading
import time
from pathlib import Path

import requests
import yaml

REPO = Path(__file__).resolve().parents[4]
SNAP = REPO / "data" / "snapshots"
MANIFEST = SNAP / "MANIFEST.json"
CATALOG = REPO / "data" / "catalog"
TOKEN_FILE = Path.home() / ".config" / "cosmic-consultants" / "earthdata-token"
EARTHDATA_HOSTS = ("earthdatacloud.nasa.gov", "gesdisc.eosdis.nasa.gov", "gesdisc.earthdata.nasa.gov",
                   "urs.earthdata.nasa.gov", "nsidc.org", "earthdata.nasa.gov")
# Shared Drive mirror (read-only rclone mount, see scripts/drive_mount.sh). If a
# payload is missing locally but the mirror has it with the manifest's sha256,
# we copy it instead of downloading again.
DRIVE_FOLDER_URL = "https://drive.google.com/drive/folders/1W4s6X4HTHmF7Xvd8eb1x3FlO-osP07V_"
MIRROR = Path(os.environ.get("CC_DRIVE_MOUNT", str(Path.home() / "mnt" / "cosmic-drive"))) / "snapshots"
_LOCK = threading.Lock()  # fetch() runs in threads; manifest writes must not race
UA = {"User-Agent": "cosmic-consultants-p0ingest/0.1 (NASA Space Apps 2026)"}


def catalog_row(dataset_id: str) -> dict:
    path = CATALOG / f"{dataset_id}.yaml"
    if not path.exists():
        raise SystemExit(f"{dataset_id}: no registry row in data/catalog/ (rule: no substitutes without one)")
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def _session() -> requests.Session:
    s = requests.Session()
    s.headers.update(UA)
    return s


class _AuthSession(requests.Session):
    """Keep the bearer token across Earthdata redirects, drop it anywhere else."""

    def __init__(self, token: str | None):
        super().__init__()
        self.headers.update(UA)
        self._token = token

    def rebuild_auth(self, prepared, response):
        host = requests.utils.urlparse(prepared.url).hostname or ""
        if self._token and any(host.endswith(h) for h in EARTHDATA_HOSTS):
            prepared.headers["Authorization"] = f"Bearer {self._token}"
        else:
            prepared.headers.pop("Authorization", None)


def _token() -> str | None:
    return TOKEN_FILE.read_text().strip() if TOKEN_FILE.exists() else None


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def load_manifest() -> dict:
    if MANIFEST.exists():
        return json.loads(MANIFEST.read_text(encoding="utf-8"))
    return {"description": "Hashed dataset snapshots used by W6 ingest. Payload bytes are local (gitignored); "
                           "this file is the provenance record (AGENTS.md rule 3).", "entries": []}


def save_manifest(m: dict) -> None:
    m["entries"].sort(key=lambda e: (e["datasetId"], e["localPath"]))
    tmp = MANIFEST.with_suffix(".tmp")
    tmp.write_text(json.dumps(m, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    os.replace(tmp, MANIFEST)


def fetch(dataset_id: str, url: str, filename: str | None = None, retries: int = 4) -> Path:
    """Download url into data/snapshots/<dataset_id>/ once; record it in MANIFEST.json."""
    row = catalog_row(dataset_id)
    dest_dir = SNAP / dataset_id
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / (filename or url.rsplit("/", 1)[-1].split("?")[0])
    rel = str(dest.relative_to(REPO))
    m = load_manifest()
    known = next((e for e in m["entries"] if e["localPath"] == rel), None)
    if dest.exists() and known:
        return dest
    if known and restore_from_mirror(known):
        return dest
    host = requests.utils.urlparse(url).hostname or ""
    token = _token() if any(host.endswith(h) for h in EARTHDATA_HOSTS) else None
    sess = _AuthSession(token)
    if token:
        sess.headers["Authorization"] = f"Bearer {token}"
    last = None
    for attempt in range(retries):
        try:
            with sess.get(url, stream=True, timeout=(30, 300), allow_redirects=True) as r:
                r.raise_for_status()
                ctype = r.headers.get("Content-Type", "")
                if "text/html" in ctype:
                    raise RuntimeError(f"got HTML instead of data (login page?) from {r.url}")
                part = dest.with_suffix(dest.suffix + ".part")
                with part.open("wb") as f:
                    for chunk in r.iter_content(1 << 20):
                        f.write(chunk)
                os.replace(part, dest)
            break
        except Exception as exc:  # noqa: BLE001 - retried, then re-raised
            last = exc
            time.sleep(2 ** attempt)
    else:
        raise RuntimeError(f"{dataset_id}: failed to fetch {url}: {last}")
    with _LOCK:
        m = load_manifest()
        m["entries"] = [e for e in m["entries"] if e["localPath"] != rel]
        m["entries"].append({
            "datasetId": dataset_id,
            "sourceUrl": url,
            "fetchedAt": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "sha256": sha256(dest),
            "bytes": dest.stat().st_size,
            "license": (row.get("license") or {}).get("id"),
            "licenseVerified": bool((row.get("license") or {}).get("verified")),
            "localPath": rel,
        })
        save_manifest(m)
    return dest


def restore_from_mirror(entry: dict) -> bool:
    """Copy one manifest entry from the Drive mirror if its sha256 matches."""
    src = MIRROR / Path(entry["localPath"]).relative_to("data/snapshots")
    if not src.exists():
        return False
    dest = REPO / entry["localPath"]
    dest.parent.mkdir(parents=True, exist_ok=True)
    part = dest.with_suffix(dest.suffix + ".part")
    shutil.copyfile(src, part)
    if sha256(part) != entry["sha256"]:
        part.unlink()
        raise RuntimeError(f"mirror copy of {entry['localPath']} does not match MANIFEST sha256")
    os.replace(part, dest)
    return True


def restore_all() -> dict:
    """Pull every manifest payload that's missing locally from the mirror."""
    got, missing = [], []
    for e in load_manifest()["entries"]:
        if (REPO / e["localPath"]).exists():
            continue
        (got if restore_from_mirror(e) else missing).append(e["localPath"])
    return {"restored": got, "notOnMirror": missing}


def cmr_granule_urls(concept_id: str, temporal: str, suffix: str, page_size: int = 200) -> list[str]:
    """Data URLs (https, ending in suffix) for a CMR collection over a temporal range."""
    r = _session().get("https://cmr.earthdata.nasa.gov/search/granules.json",
                       params={"collection_concept_id": concept_id, "temporal": temporal,
                               "page_size": page_size, "sort_key": "start_date"}, timeout=60)
    r.raise_for_status()
    urls = []
    for e in r.json()["feed"]["entry"]:
        hrefs = [l["href"] for l in e.get("links", []) if l["href"].startswith("https") and l["href"].endswith(suffix)]
        if hrefs:
            urls.append(hrefs[0])
    return urls
