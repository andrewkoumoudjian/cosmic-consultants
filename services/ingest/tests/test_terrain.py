"""Unit tests for Copernicus GLO-30 WBM/EDM masking and boundary-safe slope calculation (#76, #183)."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from p0ingest.terrain import _slope_deg, mask_tile_arrays, _read_tile  # noqa: E402


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

    def test_isolated_land_keeps_elevation_even_when_slope_is_unknown(self):
        from unittest.mock import MagicMock, patch
        from affine import Affine
        z = np.zeros((3, 3)); z[1, 1] = 123
        water = np.ones((3, 3), dtype=np.uint8); water[1, 1] = 0
        datasets = []
        for array in (z, water, np.ones((3, 3), dtype=np.uint8)):
            ds = MagicMock(); ds.__enter__.return_value = ds
            ds.read.return_value = array
            ds.transform = Affine(1, 0, 0, 0, -1, 3); ds.nodata = None
            datasets.append(ds)
        with patch('p0ingest.terrain.rasterio.open', side_effect=datasets), patch('p0ingest.terrain.CMG_STEP', 180):
            record, indices, heights, slopes = _read_tile('test_DEM', np.zeros((2, 2), dtype=int), mask_water=True)
        self.assertEqual(heights.tolist(), [123])
        self.assertTrue(np.isnan(slopes[0]))
        self.assertEqual(record['pixelsWithSlope'], 0)
        self.assertIsNotNone(record['wbmSha256'])
        self.assertEqual(len(indices), 1)

    def test_requested_mask_failure_does_not_fall_back_to_unmasked_tile(self):
        from unittest.mock import MagicMock, patch
        ds = MagicMock(); ds.__enter__.return_value = ds
        ds.read.return_value = np.ones((3, 3)); ds.nodata = None
        with patch('p0ingest.terrain.rasterio.open', side_effect=[ds, OSError('mask missing')]):
            with self.assertRaisesRegex(RuntimeError, 'masking unavailable'):
                _read_tile('test_DEM', np.zeros((2, 2), dtype=int), mask_water=True)


if __name__ == "__main__":
    unittest.main()
