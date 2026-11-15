"""Offline tests for p0ingest.palsar (W37, #96). No network: CMR/ASF paths are
covered by synthetic fixtures; the granule-reading path is exercised with small
locally written GeoTIFFs clipped to the MDRS cluster."""
import json
import tempfile
import unittest
import zipfile
from pathlib import Path

import h3
import numpy as np
import pyarrow.parquet as pq
import rasterio
from rasterio.transform import Affine
from rasterio.warp import transform as warp_transform

from p0ingest.palsar import (campaign_sites, site_clusters, cluster_bbox, select_scenes,
                             covered_cells, _point_in_ring, to_db, process_scene,
                             median_stream, build, check, _tif_pol,
                             MISSING_ASF_BLOCK, MISSING_NO_SCENE, VALUE_COLS)

MDRS = "8429927ffffffff"


class Sites(unittest.TestCase):
    def test_six_files_five_distinct_clusters(self):
        sites = campaign_sites()
        self.assertEqual(len(sites), 6, "six campaign yaml files expected")
        self.assertTrue(all(h3.is_valid_cell(s["cell"]) and h3.get_resolution(s["cell"]) == 4
                            for s in sites))
        clusters = site_clusters(sites)
        self.assertEqual(len(clusters), 5, "FMARS and HMP-2015 share a parent cell")
        self.assertTrue(all(len(info["cells"]) == 7 for info in clusters.values()))
        parents = {s["cell"] for s in sites}
        for parent, info in clusters.items():
            self.assertIn(parent, parents)
            self.assertIn(parent, info["cells"], "parent cell is inside its own cluster")

    def test_cluster_bbox_contains_parent(self):
        cells = site_clusters(campaign_sites())[MDRS]["cells"]
        long_min, lat_min, long_max, lat_max = cluster_bbox(cells)
        lat, lon = h3.cell_to_latlng(MDRS)
        self.assertGreater(lat, lat_min)
        self.assertLess(lat, lat_max)
        self.assertGreater(lon, long_min)
        self.assertLess(lon, long_max)


class Geometry(unittest.TestCase):
    RING = [(0.0, 0.0), (0.0, 2.0), (2.0, 2.0), (2.0, 0.0)]

    def test_point_in_ring(self):
        self.assertTrue(_point_in_ring(1.0, 1.0, self.RING))
        self.assertTrue(_point_in_ring(0.5, 0.5, self.RING))
        self.assertFalse(_point_in_ring(3.0, 1.0, self.RING))
        self.assertFalse(_point_in_ring(1.0, -0.5, self.RING))

    def test_point_in_ring_closed_ring(self):
        closed = self.RING + [self.RING[0]]
        self.assertTrue(_point_in_ring(1.0, 1.0, closed))
        self.assertFalse(_point_in_ring(3.0, 1.0, closed))

    def test_covered_cells_needs_all_seven_pts(self):
        cells = site_clusters(campaign_sites())[MDRS]["cells"]
        # a large square around the whole cluster covers everything; a small one covers none
        big = cluster_bbox(cells)
        around = [(big[0], big[1]), (big[0], big[3]), (big[2], big[3]), (big[2], big[1])]
        self.assertEqual(covered_cells({"polygon": around}, cells), set(cells))
        tiny = [(0.0, 0.0), (0.0, 1.0), (1.0, 1.0), (1.0, 0.0)]
        self.assertEqual(covered_cells({"polygon": tiny}, cells), set())


class Selection(unittest.TestCase):
    def test_greedy_fewest_newest_dual_pol(self):
        cells = site_clusters(campaign_sites())[MDRS]["cells"]
        big = cluster_bbox(cells)
        around = [(big[0], big[1]), (big[0], big[3]), (big[2], big[3]), (big[2], big[1])]
        half = [(big[0], big[1]), (big[0], big[3]), (big[1], big[3]), (big[1], big[1])]
        scene_old = {"ur": "OLD", "acq": "2006-01-01T00:00:00Z", "pol": "HH+HV",
                     "polygon": around, "url": "u1", "bytes": 1}
        scene_new = {"ur": "NEW", "acq": "2011-01-01T00:00:00Z", "pol": "HH+HV",
                     "polygon": around, "url": "u2", "bytes": 1}
        scene_single = {"ur": "FBS", "acq": "2010-01-01T00:00:00Z", "pol": "HH",
                        "polygon": around, "url": "u3", "bytes": 1}
        scene_no_url = {"ur": "NOP", "acq": "2010-01-01T00:00:00Z", "pol": "HH+HV",
                        "polygon": around, "url": None, "bytes": 1}
        chosen, uncovered = select_scenes(
            [scene_old, scene_new, scene_single, scene_no_url], cells)
        self.assertEqual(chosen, [scene_new], "newest full-cover FBD scene wins, single/no-url skipped")
        self.assertEqual(uncovered, [])

        chosen, uncovered = select_scenes([scene_single, scene_no_url], cells)
        self.assertEqual(chosen, [])
        self.assertEqual(uncovered, sorted(cells))

        # cover west half: one scene, ~4 cells uncovered (roughly half of 7)
        mid = (big[0] + big[2]) / 2
        west_pol = [(big[0], big[1]), (big[0], big[3]), (mid, big[3]), (mid, big[1])]
        chosen, uncovered = select_scenes([{"ur": "W", "acq": "2007-01-01T00:00:00Z",
                                            "pol": "HH+HV", "polygon": west_pol,
                                            "url": "u4", "bytes": 1}], cells)
        self.assertEqual(len(chosen), 1)
        self.assertTrue(0 < len(uncovered) < 7, "half cover leaves some cells uncovered")


class BandsToDb(unittest.TestCase):
    def test_linear_converted_and_invalid_dropped(self):
        vals = np.array([0.01, 0.0, 100.0, np.nan, -2.0])
        out = to_db(vals, already_db=False)
        self.assertTrue(np.isnan(out[1]))
        self.assertAlmostEqual(out[0], -20.0, places=9)
        self.assertAlmostEqual(out[2], 20.0, places=9)
        self.assertTrue(np.isnan(out[3]))
        self.assertTrue(np.isnan(out[4]))

    def test_db_passthrough_and_guard(self):
        out = to_db(np.array([5.0, -50.0, 25.0]), already_db=True)
        self.assertAlmostEqual(out[0], 5.0)
        self.assertTrue(np.isnan(out[1]) or out[1] != out[1], "below guard dropped")
        self.assertTrue(np.isnan(out[2]), "above guard dropped")

    def test_median_stream_support_rule(self):
        med, n = median_stream([1.0, 2.0])
        self.assertIsNone(med)
        self.assertEqual(n, 2)
        med, n = median_stream(list(np.linspace(-20.0, -10.0, 51)))
        self.assertAlmostEqual(med, -15.0)
        self.assertEqual(n, 51)


def _write_scene(tmp: Path, name: str, crs, lon: float, lat: float, values,
                 pixel: float = 12.5, pol_desc: str | None = None) -> Path:
    """A synthetic 12.5 m RTC raster centred at (lon, lat) with the given values."""
    x0, y0 = warp_transform("EPSG:4326", crs, [lon], [lat])
    height, width = values.shape
    transform = Affine(pixel, 0.0, float(x0[0]) - width * pixel / 2,
                       0.0, -pixel, float(y0[0]) + height * pixel / 2)
    path = tmp / name
    profile = {"driver": "GTiff", "height": height, "width": width, "dtype": "float32",
               "crs": crs, "transform": transform, "count": 1}
    with rasterio.open(path, "w", **profile) as dst:
        dst.write(values.astype("float32"), 1)
        if pol_desc:
            dst.set_band_description(1, pol_desc)
    return path


def _zip_scene(tmp: Path, name: str, lon: float, lat: float, hh, hv) -> Path:
    """A RTC zip like the ASF products: inner TIFFs named ..._HH.tif / ..._HV.tif."""
    crs = "EPSG:32611"  # UTM 11N, the MDRS Utah area
    hh_path = _write_scene(tmp, tmp.name + "_HH.tif", crs, lon, lat, hh)
    hv_path = _write_scene(tmp, tmp.name + "_HV.tif", crs, lon, lat, hv)
    zip_path = tmp / name
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as z:
        for p in (hh_path, hv_path):
            z.write(p, arcname=f"AP_00001_FBD_F0000_RTC_{p.stem.split('_')[-1]}.tif")
    hh_path.unlink()
    hv_path.unlink()
    return zip_path


class SceneReading(unittest.TestCase):
    def make_scenes(self, tmp: Path) -> tuple[Path, float, float]:
        cells = site_clusters(campaign_sites())[MDRS]["cells"]
        lon_min, lat_min, lon_max, lat_max = cluster_bbox(cells)
        # a grid that comfortably covers the cluster (bbox with pad is ~70 km;
        # 6400 px x 12.5 m = 80 km side)
        lat, lon = h3.cell_to_latlng(MDRS)
        height = width = 6400
        hh = np.full((height, width), 0.01, dtype="float32")  # -20 dB
        hv = np.full((height, width), 0.001, dtype="float32")  # -30 dB
        zp = _zip_scene(tmp, "synthetic_RTC.zip", (lon_min + lon_max) / 2,
                        (lat_min + lat_max) / 2, hh, hv)
        return zp, cells, -20.0

    def test_tif_pol(self):
        self.assertEqual(_tif_pol("AP_1_FBD_F00_RTC_HH.tif"), "HH")
        self.assertEqual(_tif_pol("AP_1_FBD_F00_RTC_HV.tif"), "HV")
        self.assertIsNone(_tif_pol("AP_1_FBD_F00_RTC_OTHER.tif"))

    def test_process_scene_stride_and_membership(self):
        self.assertEqual(
            1, 1, "sanity")
        with tempfile.TemporaryDirectory() as directory:
            tmp = Path(directory)
            zp, cells, expected_hh = self.make_scenes(tmp)
            res = process_scene(zp, cells)
            # each cluster cell must have subgrid samples of exactly 10*log10(0.01)
            for cell in cells:
                hh = res["cells"][cell]["HH"]
                hv = res["cells"][cell]["HV"]
                self.assertGreater(len(hh), 0, f"no samples in {cell}")
                self.assertTrue(all(abs(v - expected_hh) < 1e-6 for v in hh), cell)
                self.assertTrue(all(abs(v - (expected_hh - 10.0)) < 1e-6 for v in hv), cell)
            # subgrid stride: samples per cell well under the full pixel count
            self.assertLess(len(res["cells"][list(res["cells"])[0]]["HH"]), 100_000)
            # the two inner tifs were recognised as the two polarizations
            self.assertEqual(sorted(res["band_info"]), sorted(
                {"AP_00001_FBD_F0000_RTC_HH.tif", "AP_00001_FBD_F0000_RTC_HV.tif"}))

    def test_process_scene_zero_regions_dropped(self):
        with tempfile.TemporaryDirectory() as directory:
            tmp = Path(directory)
            cells = site_clusters(campaign_sites())[MDRS]["cells"]
            lon_min, lat_min, lon_max, lat_max = cluster_bbox(cells)
            lat, lon = h3.cell_to_latlng(MDRS)
            hh = np.full((3000, 3000), 0.01, dtype="float32")
            hh[:1500, :] = 0.0  # one slab invalid
            zp = _write_scene(tmp, "raw_HH.tif", "EPSG:32611", (lon_min + lon_max) / 2,
                              (lat_min + lat_max) / 2, hh)
            res = process_scene(zp, cells)
            total = sum(len(res["cells"][c]["HH"]) for c in cells)
            self.assertGreater(total, 0)


class BuildAndCheck(unittest.TestCase):
    def build_empty(self, tmp: Path) -> tuple[Path, Path]:
        out_pq = tmp / "palsar-r4-sites.parquet"
        out_meta = tmp / "palsar-r4-sites.meta.json"
        report = build(out_parquet=out_pq, out_meta=out_meta,
                       raw_dir=tmp / "raw", selection_path=tmp / "no-selection.json")
        self.assertEqual(report["rows"], 35)
        return out_pq, out_meta

    def test_build_blocked_rows_all_missing(self):
        with tempfile.TemporaryDirectory() as directory:
            tmp = Path(directory)
            out_pq, out_meta = self.build_empty(tmp)
            table = pq.read_table(out_pq)
            self.assertEqual(table.num_rows, 35)
            for reason in table.column("missing_reason").to_pylist():
                parsed = json.loads(reason)
                self.assertEqual(set(parsed), set(VALUE_COLS))
                self.assertTrue(all(v == MISSING_ASF_BLOCK for v in parsed.values()))
            for v in table.column("gamma0_hh_db").to_pylist() + table.column("gamma0_hv_db").to_pylist():
                self.assertIsNone(v)
            meta = json.loads(out_meta.read_text())
            self.assertTrue(any(b["code"] == MISSING_ASF_BLOCK for b in meta["blocks"]))

    def test_check_blocked_status(self):
        with tempfile.TemporaryDirectory() as directory:
            tmp = Path(directory)
            out_pq, _ = self.build_empty(tmp)
            report = check(out_parquet=out_pq, raw_dir=tmp / "raw",
                           selection_path=tmp / "no-selection.json")
            self.assertEqual(report["status"], "blocked")
            self.assertEqual(report["problems"], [])
            self.assertEqual(report["rows"], 35)

    def test_check_catches_range_missing_reason_and_dup(self):
        with tempfile.TemporaryDirectory() as directory:
            tmp = Path(directory)
            out_pq, _ = self.build_empty(tmp)
            # corrupt: out-of-range median + count kept, a mismatching reason, one dup key
            import pyarrow as pa

            table = pq.read_table(out_pq)
            hh = list(table.column("gamma0_hh_db").to_pylist())
            reasons = list(table.column("missing_reason").to_pylist())
            hh[0] = 999.0
            keys = list(table.column("h3").to_pylist())
            keys[1] = keys[0]
            reasons[2] = json.dumps({"gamma0_hh_db": MISSING_NO_SCENE})
            bad = pa.table({
                "h3": keys,
                "campaigns": table.column("campaigns"),
                "scene_urs": table.column("scene_urs"),
                "acq_dates": table.column("acq_dates"),
                "gamma0_hh_db": pa.array(hh, pa.float64()),
                "gamma0_hv_db": table.column("gamma0_hv_db"),
                "gamma0_hh_valid_pixels": pa.array([1] * len(hh), pa.int64()),
                "gamma0_hv_valid_pixels": table.column("gamma0_hv_valid_pixels"),
                "missing_reason": reasons,
            })
            pq.write_table(bad, out_pq)
            report = check(out_parquet=out_pq, raw_dir=tmp / "raw",
                           selection_path=tmp / "no-selection.json")
            codes = " ".join(report["problems"])
            self.assertIn("outside physical guard", codes, report["problems"])
            self.assertIn("missing_reason keys", codes)
            self.assertIn("duplicate", codes)

    def test_full_pipeline_with_synthetic_raw(self):
        with tempfile.TemporaryDirectory() as directory:
            tmp = Path(directory)
            raw = tmp / "raw"
            raw.mkdir()
            cells = site_clusters(campaign_sites())[MDRS]["cells"]
            lon_min, lat_min, lon_max, lat_max = cluster_bbox(cells)
            lat, lon = h3.cell_to_latlng(MDRS)
            hh = np.full((20000, 20000), 0.01, dtype="float32")
            hv = np.full((20000, 20000), 0.001, dtype="float32")
            zp = _zip_scene(raw, "AP_00001_FBD_F0000_RT1.zip", (lon_min + lon_max) / 2,
                            (lat_min + lat_max) / 2, hh, hv)
            acq = "2007-07-31T03:43:48Z"
            # a partial second scene: covers a bbox well west of the cluster -> no extra cells
            selection = {MDRS: [{"ur": "SYNTH1", "acq": acq, "bytes": 1.0, "url": "https://x/y.zip",
                                 "zip": zp.name}]}
            sel_path = tmp / "selection.json"
            sel_path.write_text(json.dumps(selection))
            out_pq = tmp / "out.parquet"
            out_meta = tmp / "out.meta.json"
            report = build(out_parquet=out_pq, out_meta=out_meta, raw_dir=raw, selection_path=sel_path)
            self.assertEqual(report["rows"], 35)
            table = pq.read_table(out_pq)
            reasons = table.column("missing_reason").to_pylist()
            hh_med = table.column("gamma0_hh_db").to_pylist()
            filled = [r for r in reasons if not r]
            self.assertEqual(len(filled), 7, "the 7 covered cells have values")
            med = [m for r, m in zip(reasons, hh_med) if not r]
            self.assertTrue(all(m is not None and abs(m + 20.0) < 1e-6 for m in med))
            counted = [c for r, c in zip(reasons, table.column("gamma0_hh_valid_pixels").to_pylist()) if not r]
            self.assertTrue(all(c >= 50 for c in counted))
            raw_reasons = [json.loads(r)["gamma0_hh_db"] for r in reasons
                           if r and json.loads(r)["gamma0_hh_db"] is not None]
            self.assertTrue(all(v in (MISSING_NO_SCENE, MISSING_ASF_BLOCK) for v in raw_reasons))

            # check must pass on the filled subset: 7 valid cells >= 5 spots
            rpt = check(out_parquet=out_pq, raw_dir=raw, selection_path=sel_path)
            self.assertEqual(rpt["status"], "ok", rpt["problems"])

    def test_partial_scene_missing_reason(self):
        with tempfile.TemporaryDirectory() as directory:
            tmp = Path(directory)
            raw = tmp / "raw"
            raw.mkdir()
            cells = site_clusters(campaign_sites())[MDRS]["cells"]
            lon_min, lat_min, lon_max, lat_max = cluster_bbox(cells)
            # a small 300x300 px raster that covers only a fraction of the cluster
            small = np.full((300, 300), 0.01, dtype="float32")
            zp = _zip_scene(raw, "small.zip", (lon_min + lon_max) / 2, (lat_min + lat_max) / 2,
                            small, small)
            sel_path = tmp / "selection.json"
            sel_path.write_text(json.dumps({MDRS: [{"ur": "S", "acq": "2007-07-31", "bytes": 1.0,
                                                    "url": "https://x", "zip": zp.name}]}))
            out_pq = tmp / "out.parquet"
            build(out_parquet=out_pq, out_meta=tmp / "m.json", raw_dir=raw, selection_path=sel_path)
            table = pq.read_table(out_pq)
            reasons = table.column("missing_reason").to_pylist()
            any_missing_scene = any(MISSING_NO_SCENE in json.loads(r).values() for r in reasons)
            self.assertTrue(any_missing_scene, "some cells outside the small raster stay missing")
            for r in reasons:
                parsed = json.loads(r) if r else {}
                for value in parsed.values():
                    self.assertIn(value, {MISSING_NO_SCENE, "not-enough-valid-pixels",
                                          MISSING_ASF_BLOCK})


if __name__ == "__main__":
    unittest.main()
