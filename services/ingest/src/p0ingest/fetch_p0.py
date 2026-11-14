"""Fetch the P0 Earth inputs for 2023 (one full year, V061 / MERRA-2 5.12.4)."""
from __future__ import annotations

import sys
from concurrent.futures import ThreadPoolExecutor, as_completed

from .snapshots import cmr_granule_urls, fetch

YEAR = "2023-01-01T00:00:00Z,2023-12-31T23:59:59Z"
JOBS = [
    ("modis-mod11c3", "C2565788897-LPCLOUD", YEAR, ".hdf"),
    ("modis-mcd12c1", "C2484078896-LPCLOUD", "2023-01-01T00:00:00Z,2023-12-31T23:59:59Z", ".hdf"),
    ("merra2-m2tmnxaer", "C1276812866-GES_DISC", YEAR, ".nc4"),
]


def main() -> int:
    todo = []
    for ds, cid, t, suf in JOBS:
        urls = cmr_granule_urls(cid, t, suf)
        print(f"{ds}: {len(urls)} granules", flush=True)
        todo += [(ds, u) for u in urls]
    errors = 0
    with ThreadPoolExecutor(max_workers=6) as ex:
        futs = {ex.submit(fetch, ds, u): (ds, u) for ds, u in todo}
        for f in as_completed(futs):
            ds, u = futs[f]
            try:
                p = f.result()
                print(f"ok   {ds} {p.name} {p.stat().st_size} B", flush=True)
            except Exception as exc:  # noqa: BLE001
                errors += 1
                print(f"FAIL {ds} {u}: {exc}", flush=True)
    print(f"done, {errors} error(s)", flush=True)
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
