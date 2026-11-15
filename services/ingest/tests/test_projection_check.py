import struct
import unittest

import numpy as np

from p0ingest import projection_check as pc


def dbf(fields, rows):
    """Build a tiny dBASE III table: fields = [(name, kind, length)], rows = [dict]."""
    header_len = 32 + 32 * len(fields) + 1
    record_len = 1 + sum(f[2] for f in fields)
    out = bytearray(struct.pack("<BBBBIHH20x", 3, 126, 1, 1, len(rows), header_len, record_len))
    for name, kind, length in fields:
        out += name.encode().ljust(11, b"\0") + kind.encode() + b"\0" * 4 + bytes([length, 0]) + b"\0" * 14
    out += b"\r"
    for row in rows:
        out += b" " + b"".join(str(row.get(n, "")).encode().ljust(length)[:length] for n, _, length in fields)
    return bytes(out + b"\x1a")


class ProjectionCheckTests(unittest.TestCase):
    def test_bilinear_hits_pixel_centres_and_wraps(self):
        z = np.arange(4 * 8, dtype=float).reshape(4, 8)
        res = 8 / 360  # 8 columns span 360 deg
        lat = np.array([90 - 0.5 / res, 90 - 1.5 / res])
        lon = np.array([0.5 / res, 7.5 / res])
        got = pc.bilinear(z, res, lat, lon)
        np.testing.assert_allclose(got, [z[0, 0], z[1, 7]])
        # halfway across the 0/360 seam averages the last and first columns
        seam = pc.bilinear(z, res, np.array([90 - 0.5 / res]), np.array([0.0]))
        self.assertAlmostEqual(float(seam[0]), (z[0, 7] + z[0, 0]) / 2)

    def test_orient_flips_axes_only_when_asked(self):
        a = np.arange(6).reshape(2, 3)
        np.testing.assert_array_equal(pc.orient(a, (False, False)), a)
        np.testing.assert_array_equal(pc.orient(a, (True, True)), a[::-1, ::-1])
        np.testing.assert_array_equal(pc.orient(a, (True, False)), a[::-1])

    def test_box_mean_ignores_nan_and_wraps_longitude(self):
        a = np.ones((5, 6))
        a[2, 0] = np.nan
        a[2, 5] = 4.0
        m = pc.box_mean(a, 3)
        self.assertTrue(np.isfinite(m).all())
        # (2,0) neighbourhood wraps to column 5: 7 ones + one 4.0 over 8 valid cells
        self.assertAlmostEqual(m[2, 0], (7 + 4) / 8)

    def test_highpass_correlation_detects_flip(self):
        rng = np.random.default_rng(0)
        z = rng.normal(size=(40, 80))
        t = z + 0.5 * rng.normal(size=z.shape)
        keep = np.ones(z.shape, bool)
        same = pc.corr(pc.highpass(t, 5), pc.highpass(z, 5), keep)[0]
        flipped = pc.corr(pc.highpass(t[::-1, ::-1].copy(), 5), pc.highpass(z, 5), keep)[0]
        self.assertGreater(same, 0.7)
        self.assertLess(abs(flipped), 0.1)

    def test_dbf_reader_parses_numbers_and_text(self):
        raw = dbf([("clean_name", "C", 20), ("center_lat", "N", 10), ("center_lon", "N", 10)],
                  [{"clean_name": "Olympus Mons", "center_lat": "18.65", "center_lon": "-133.8"},
                   {"clean_name": "Hellas", "center_lat": "-42.4", "center_lon": ""}])
        rows = pc.dbf_records(raw, ["clean_name", "center_lat", "center_lon"])
        self.assertEqual(rows[0], {"clean_name": "Olympus Mons", "center_lat": 18.65, "center_lon": -133.8})
        self.assertIsNone(rows[1]["center_lon"])


if __name__ == "__main__":
    unittest.main()
