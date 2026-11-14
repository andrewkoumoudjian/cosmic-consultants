"""`uv run python -m p0ingest restore` pulls missing payloads from the mounted Drive mirror."""
import json
import sys

from .snapshots import restore_all

if __name__ == "__main__" and sys.argv[1:] == ["restore"]:
    print(json.dumps(restore_all(), indent=1))
else:
    print("usage: python -m p0ingest restore   (other steps: p0ingest.fetch_p0, .terrain, .process, .inventory)")
