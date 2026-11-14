"""H3 grid + the 0.05 deg MODIS CMG pixel -> H3 cell map (cached, gitignored)."""
from __future__ import annotations

import glob
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import h3
import numpy as np
from pyhdf.SD import SD, SDC

from .snapshots import SNAP

RES = 4
CMG_N, CMG_M, CMG_STEP = 3600, 7200, 0.05
DERIVED = SNAP / "_derived"


def cmg_lat(i):  # pixel-center latitude of row i
    return 90.0 - CMG_STEP / 2 - i * CMG_STEP


def cmg_lon(j):
    return -180.0 + CMG_STEP / 2 + j * CMG_STEP


def land_percent() -> np.ndarray:
    """Percent_land_in_grid from the first MOD11C3 granule (same CMG grid for all months)."""
    f = sorted(glob.glob(str(SNAP / "modis-mod11c3" / "*.hdf")))[0]
    return SD(f, SDC.READ).select("Percent_land_in_grid")[:].astype(np.uint8)


def _row_cells(args):
    i, cols, res = args
    lat = cmg_lat(i)
    return i, np.array([int(h3.latlng_to_cell(lat, cmg_lon(j), res), 16) for j in cols], dtype=np.uint64)


def cmg_cell_map(res: int = RES) -> tuple[np.ndarray, np.ndarray]:
    """Return (cell id per CMG pixel as uint64, 0 = not land) and the land-percent array."""
    DERIVED.mkdir(parents=True, exist_ok=True)
    cache = DERIVED / f"cmg_h3r{res}.npy"
    landp = land_percent()
    if cache.exists():
        return np.load(cache), landp
    out = np.zeros((CMG_N, CMG_M), dtype=np.uint64)
    jobs = [(i, np.nonzero(landp[i] > 0)[0], res) for i in range(CMG_N)]
    jobs = [j for j in jobs if len(j[1])]
    with ProcessPoolExecutor() as ex:
        for i, cells in ex.map(_row_cells, jobs, chunksize=16):
            cols = np.nonzero(landp[i] > 0)[0]
            out[i, cols] = cells
    np.save(cache, out)
    return out, landp


def group_index(cellmap: np.ndarray):
    """Flat pixel indices sorted by cell, plus unique cells and group boundaries."""
    flat = cellmap.ravel()
    land = np.nonzero(flat)[0]
    order = land[np.argsort(flat[land], kind="stable")]
    cells, starts = np.unique(flat[order], return_index=True)
    return order, cells, starts


def cell_center(cell: int) -> tuple[float, float]:
    return h3.cell_to_latlng(format(int(cell), "x"))
