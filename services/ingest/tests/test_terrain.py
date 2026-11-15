"""Unit tests for Copernicus GLO-30 WBM/EDM masking and boundary-safe slope calculation (#76, #183)."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from p0ingest.terrain import _slope_deg, mask_tile_arrays  # noqa: E402


class TerrainMaskingTests(unittest.TestCase):
    def test_masks_water_and_void_and_avoids_ocean_slope_bias(self) -> None:
        # 4x4 elevation patch: columns 0-1 are ocean (0.0 m, WBM=1); columns 2-3 rise steeply (100 m, 200 m, WBM=0).
        z = np.array([
            [0.0, 0.0, 100.0, 200.0],
            [0.0, 0.0, 100.0, 200.0],
            [0.0, 0.0, 100.0, 200.0],
            [0.0, 0.0, 100.0, 200.0],
        ], dtype=np.float64)
        wbm = np.array([
            [1, 1, 0, 0],
            [1, 1, 0, 0],
            [1, 1, 0, 0],
            [1, 1, 0, 0],
        ], dtype=np.uint8)
        edm = np.ones_like(wbm)
        edm[0, 3] = 0  # void pixel

        z_clean, counts = mask_tile_arrays(z, wbm=wbm, edm=edm)
        self.assertEqual(counts, {
            "totalPixels": 16,
            "maskedWaterPixels": 8,
            "maskedVoidPixels": 1,
            "retainedLandPixels": 7,
        })
        self.assertTrue(np.all(np.isnan(z_clean[:, :2])))
        self.assertTrue(np.isnan(z_clean[0, 3]))

        dx = np.full((4, 1), 240.0)
        dy = 240.0
        slope = _slope_deg(z_clean, dx, dy)
        # Ocean & void stay NaN; coastal land pixel (row 1, col 2) computes slope against land neighbor (col 3 = 200 m),
        # NOT 0.0 m ocean! tan(slope) = 100 / 240 -> ~22.62 deg.
        self.assertTrue(np.all(np.isnan(slope[:, :2])))
        self.assertTrue(np.isnan(slope[0, 3]))
        self.assertAlmostEqual(float(slope[1, 2]), float(np.degrees(np.arctan(100.0 / 240.0))), places=5)
        self.assertAlmostEqual(float(slope[1, 3]), float(np.degrees(np.arctan(100.0 / 240.0))), places=5)


if __name__ == "__main__":
    unittest.main()
