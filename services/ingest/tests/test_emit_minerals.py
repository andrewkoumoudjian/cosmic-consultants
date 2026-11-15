"""Tests for p0ingest.emit_minerals (W35 #94): EMIT L2B minerals -> H3 res-4."""
import json
import tempfile
import unittest
from pathlib import Path

import h3
import netCDF4
import numpy as np

from p0ingest.emit_minerals import (BD_BINS, COLUMNS, FAMILY_ORDER, HistStore,
                                    aggregate_granule, cell_medians,
                                    classify_names, classify_names_from_granule,
                                    fam_bitmask, is_geologic, load_state,
                                    map_cells, ordered_sample, read_granule,
                                    RAW_DIR)


def _make_granule(path: Path, lat: np.ndarray, lon: np.ndarray,
                  names: list[str], groups: dict[int, tuple[np.ndarray, np.ndarray]]
                  ) -> None:
    """Minimal EMITL2BMIN-style netCDF: location group + root group_N vars."""
    with netCDF4.Dataset(path, "w", format="NETCDF4") as ds:
        n = len(lat)
        loc = ds.createGroup("location")
        loc.createDimension("pix", n)
        v = loc.createVariable("lat", "f8", ("pix",))
        v[:] = lat
        v = loc.createVariable("lon", "f8", ("pix",))
        v[:] = lon
        md = ds.createGroup("mineral_metadata")
        md.createDimension("lib", len(names))
        v = md.createVariable("index", "i4", ("lib",))
        v[:] = np.arange(1, len(names) + 1)
        v = md.createVariable("name", str, ("lib",))
        v[:] = np.asarray(names, dtype=object)
        ds.createDimension("pix", n)
        for g, (ids, bds) in groups.items():
            v = ds.createVariable(f"group_{g}_mineral_id", "i4", ("pix",))
            v[:] = ids
            v = ds.createVariable(f"group_{g}_band_depth", "f4", ("pix",))
            v[:] = bds


class NameRules(unittest.TestCase):
    def test_organic_and_manmade_excluded(self):
        self.assertFalse(is_geologic("organic_dry_grasses"))
        self.assertFalse(is_geologic("organic_paint_plastic_flashy"))
        self.assertFalse(is_geologic("cyanide_mineral_x"))
        self.assertFalse(is_geologic("methane-gas_solid"))
        for n in ("montmorillonite", "calcite", "gypsum", "fe2+_olivine_forsterite",
                  "fe3+_hematite", "illite+kaolinite"):
            self.assertTrue(is_geologic(n))

    def test_family_matches(self):
        f = classify_names(["montmorillonite", "chlorite+vermiculite", "kaolinite",
                            "illite", "gypsum", "calcite", "dolomite",
                            "fe2+_olivine_forsterite", "fe3+_hematite",
                            "organic_dry_grasses"])
        self.assertIn("fe_mg_smectite", f["montmorillonite"])
        self.assertIn("hydration", f["montmorillonite"])
        self.assertIn("fe_mg_smectite", f["chlorite+vermiculite"])
        self.assertEqual(f["kaolinite"], {"hydration", "al_oh"})
        self.assertTrue("al_oh" in f["illite"] and "hydration" in f["illite"])
        self.assertIn("sulfate", f["gypsum"])
        self.assertIn("carbonate", f["calcite"])
        self.assertIn("carbonate", f["dolomite"])
        self.assertIn("mafic_bd_1um", f["fe2+_olivine_forsterite"])
        self.assertIn("dust_proxy", f["fe3+_hematite"])

    def test_feldspar_kept_out_of_mafic(self):
        f = classify_names(["fe2+_feldspar_albite", "fe2+_pyroxene"])
        self.assertNotIn("mafic_bd_1um", f.get("fe2+_feldspar_albite", set()))
        self.assertIn("mafic_bd_1um", f["fe2+_pyroxene"])

    def test_unmatched_geologic_name_has_no_family(self):
        # a geologic name outside every rule must simply not appear
        self.assertEqual(classify_names(["organic_paint"]), {})


class Bitmask(unittest.TestCase):
    def test_base_bit_set_only_for_geologic_ids(self):
        names = ["calcite", "organic_dry_grasses"]
        id_by_index = {1: names[0], 2: names[1]}
        name_fams = classify_names(names)
        bm = fam_bitmask(name_fams, [1, 2], id_by_index)
        base = 1 << len(FAMILY_ORDER)
        self.assertTrue(bm[1] & base)
        self.assertFalse(bm[2] & base)
        k = FAMILY_ORDER.index("carbonate")
        self.assertTrue((bm[1] >> k) & 1)


class Cells(unittest.TestCase):
    def test_map_cells_centre_rule(self):
        lat = np.array([28.0, 36.5, np.nan])
        lon = np.array([71.0, -115.0, -115.0])
        got = map_cells(lat, lon)
        want = int(h3.latlng_to_cell(28.0, 71.0, 4), 16)
        want2 = int(h3.latlng_to_cell(36.5, -115.0, 4), 16)
        self.assertEqual(got[0], want)
        self.assertEqual(got[1], want2)
        self.assertEqual(got[2], 0)


class SyntheticGranule(unittest.TestCase):
    def test_aggregate_counts_base_and_families(self):
        # three pixels in one Thar-desert hexagon, one organic (excluded from
        # base), one carbonate, one fe3+ oxide; plus an unknown id
        names = ["calcite", "fe3+_hematite", "organic_dry_grasses"]
        lat = np.array([28.0, 28.0, 28.0, 28.0])
        lon = np.array([71.0, 71.0, 71.0, 71.0])
        ids = np.array([1, 2, 3, 99], dtype="i4")   # 99 not in library -> ignored
        bds = np.array([0.10, 0.02, 0.30, 0.50], dtype="f4")
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "g.nc"
            _make_granule(p, lat, lon, names, {2: (ids, bds)})
            nf = classify_names(names)
            agg = aggregate_granule(p, nf)
            cell = int(h3.latlng_to_cell(28.0, 71.0, 4), 16)
            # organic excluded, unknown id excluded -> base 2
            base = dict(zip(agg["BASE__counts"][0].tolist(),
                            agg["BASE__counts"][1].tolist()))
            self.assertEqual(base.get(cell), 2)
            ck = agg["carbonate__cells"]
            self.assertEqual(ck.tolist(), [cell])
            self.assertTrue(np.isclose(agg["carbonate__bds"][0], 0.10, atol=1e-6))
            dp = agg["dust_proxy__cells"]
            self.assertEqual(dp.tolist(), [cell])
            self.assertTrue(np.isclose(agg["dust_proxy__bds"][0], 0.02, atol=1e-6))

    def test_invalid_pixels_dropped(self):
        names = ["calcite"]
        lat = np.array([np.nan, 28.0])
        lon = np.array([71.0, 71.0])
        ids = np.array([1, 1], dtype="i4")
        bds = np.array([0.1, 0.2], dtype="f4")
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "g.nc"
            _make_granule(p, lat, lon, names, {2: (ids, bds)})
            agg = aggregate_granule(p, classify_names(names))
            cell = int(h3.latlng_to_cell(28.0, 71.0, 4), 16)
            self.assertEqual(agg["carbonate__cells"].tolist(), [cell])
            self.assertEqual(agg["BASE__counts"][1].tolist(), [1])

    def test_bd_guards(self):
        # band depth <= 0 or > MAX_BD(1.0) or NaN must not enter families
        names = ["gypsum", "gypsum", "gypsum", "gypsum"]
        lat = np.full(4, 28.0)
        lon = np.full(4, 71.0)
        ids = np.ones(4, dtype="i4")
        bds = np.array([0.0, 1.5, np.nan, 0.4], dtype="f4")
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "g.nc"
            _make_granule(p, lat, lon, names, {1: (ids, bds)})
            agg = aggregate_granule(p, classify_names(names))
            cell = int(h3.latlng_to_cell(28.0, 71.0, 4), 16)
            self.assertEqual(agg["sulfate__bds"].tolist(), [np.float32(0.4)])
            self.assertEqual(agg["sulfate__cells"].tolist(), [cell])
            # base still counts all four geologic identifications
            self.assertEqual(agg["BASE__counts"][1].tolist(), [4])


class HistMedian(unittest.TestCase):
    def test_median_close_to_true_and_count_exact(self):
        rng = np.random.default_rng(7)
        for trial in range(5):
            bds = rng.uniform(0.001, 0.999, size=501)
            cells = np.full(501, 123 + trial, dtype=np.uint64)
            st = HistStore()
            st.add_pairs("carbonate", cells, bds.astype(np.float32))
            got = cell_medians(st.hists["carbonate"])
            count, med = got[123 + trial]
            self.assertEqual(count, 501)
            self.assertAlmostEqual(med, float(np.median(bds)), delta=0.0015)

    def test_median_split_bins(self):
        st = HistStore()
        cells = np.array([5, 5, 5], dtype=np.uint64)
        bds = np.array([0.001, 0.003, 0.009], dtype=np.float32)
        st.add_pairs("sulfate", cells, bds)
        count, med = cell_medians(st.hists["sulfate"])[5]
        self.assertEqual(count, 3)
        self.assertAlmostEqual(med, 0.003, delta=0.0015)

    def test_flush_merge_roundtrip(self):
        rng = np.random.default_rng(11)
        c1 = np.array([10, 11], dtype=np.uint64)
        b1 = rng.uniform(0.01, 0.5, 200).astype(np.float32)
        c2 = np.array([11, 12, 10], dtype=np.uint64)
        b2 = rng.uniform(0.01, 0.5, 300).astype(np.float32)
        st = HistStore()
        st.add_pairs("hydration", np.concatenate([c1, c2]),
                     np.concatenate([b1, b2]))
        st.add_base(np.array([[10, 11], [7, 9]], dtype=np.uint64))
        h_before = {c: h.copy() for c, h in st.hists["hydration"].items()}
        base_before = dict(st.base)
        with tempfile.TemporaryDirectory() as d:
            cp = Path(d) / "cp-00001.npz"
            st.flush(cp)
            self.assertEqual(st.hists, {})  # flush hands the state off
            st2 = HistStore()
            st2.merge([cp])
        for c, h in h_before.items():
            self.assertTrue(np.array_equal(st2.hists["hydration"][c], h))
        self.assertEqual(st2.base, base_before)


class SampleOrder(unittest.TestCase):
    def test_deterministic_and_spread(self):
        gs = [{"id": f"EMIT_L2B_MIN_002_2022{i:02d}0{j}T000000_S", "url": "u"}
              for i in range(1, 13) for j in range(1, 3)]
        a = [g["id"] for g in ordered_sample(gs)]
        b = [g["id"] for g in ordered_sample(list(reversed(gs)))]
        self.assertEqual(a, b)
        self.assertNotEqual(a, [g["id"] for g in gs])  # genuinely reordered


class Columns(unittest.TestCase):
    def test_column_layout(self):
        self.assertEqual(len(COLUMNS), 1 + 1 + 7 * 3 + 1)
        for f in FAMILY_ORDER:
            for s in ("share", "bd_med", "px"):
                self.assertIn(f"emit_min_{f}_{s}", COLUMNS)
        self.assertEqual(FAMILY_ORDER,
                         ["hydration", "fe_mg_smectite", "al_oh", "sulfate",
                          "carbonate", "mafic_bd_1um", "dust_proxy"])


class StateShape(unittest.TestCase):
    def test_defaults_are_resumable(self):
        from p0ingest.emit_minerals import load_state
        st = load_state()
        self.assertIn("processed", st)
        self.assertIn("bytes", st)
        self.assertIn("failed", st)


@unittest.skipUnless(any(RAW_DIR.glob("*.nc")),
                     "no EMIT L2B MIN raw granules kept on disk")
class PilotRaw(unittest.TestCase):
    def test_read_granule_structure(self):
        p = sorted(RAW_DIR.glob("*.nc"))[0]
        id_by_index, lat, lon, gvars = read_granule(p)
        self.assertTrue(len(id_by_index) >= 300)
        self.assertTrue(set(gvars) & {1, 2})
        for g, (ids, bds) in gvars.items():
            self.assertEqual(len(ids), len(lat))
            self.assertEqual(len(bds), len(lat))

    def test_real_library_classification(self):
        p = sorted(RAW_DIR.glob("*.nc"))[0]
        nf = classify_names_from_granule(p)
        joined = {n: sorted(v) for n, v in nf.items()}
        self.assertTrue(any("hydration" in v for v in joined.values()))
        self.assertTrue(any("mafic_bd_1um" in v for v in joined.values()))
        self.assertTrue(all(n for v in joined.values() for n in v))


if __name__ == "__main__":
    unittest.main()
