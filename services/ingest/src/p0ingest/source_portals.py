"""Probe the owner's additional source list, preserving failures as evidence.

Records reachability only; does not claim data acquisition or licence approval.
Run: python -m p0ingest.source_portals
"""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import hashlib
import json

import requests
import yaml

from .snapshots import REPO, SNAP, sha256, UA


def probe(resource):
    result = {"id": resource["id"], "url": resource["url"],
              "probedAt": datetime.now(timezone.utc).isoformat()}
    try:
        response = requests.get(resource["url"], headers=UA, timeout=(10, 30))
        result.update({"httpStatus": response.status_code, "resolvedUrl": response.url,
                       "bytes": len(response.content), "sha256": hashlib.sha256(response.content).hexdigest(),
                       "contentType": response.headers.get("Content-Type"),
                       "runtimeStatus": "reachable" if response.ok else "http-error",
                       "meaning": "HTTP reachability only; no product or licence acceptance"})
    except requests.RequestException as error:
        result.update({"runtimeStatus": "probe-error", "error": str(error)})
    return result


def main():
    path = REPO / "data/sources/agency-portals.yaml"
    resources = yaml.safe_load(path.read_text())["resources"]
    if len({r["id"] for r in resources}) != len(resources):
        raise ValueError("duplicate source resource")
    for resource in resources:
        for dataset in resource["existingDatasetIds"]:
            if not (REPO / f"data/catalog/{dataset}.yaml").is_file():
                raise ValueError(f"missing existing catalog row: {dataset}")
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(probe, resources))
    date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    out = SNAP / "source-portal-probes" / date
    out.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%H%M%S%f")
    (out / f"probe-{stamp}.json").write_text(json.dumps({"inventorySha256": sha256(path), "results": results}, indent=2) + "\n")
    for result in results:
        print(result["id"], result["runtimeStatus"], result.get("httpStatus", result.get("error")))


if __name__ == "__main__":
    main()
