import unittest
from unittest.mock import patch
import numpy as np

from p0ingest import albedo, regolith


class Dataset:
    def __init__(self, name): self.name = name
    def attributes(self):
        if self.name == "Albedo_Quality": return {"_FillValue": 255, "valid_range": [0, 254]}
        return {"scale_factor": 0.001, "_FillValue": 32767, "valid_range": [0, 32766]}
    def __getitem__(self, key):
        return {"Albedo_WSA_shortwave": np.array([[100, 200, 32767, 400]], dtype=np.int16),
                "Albedo_BSA_shortwave": np.array([[100, 32767, 300, 400]], dtype=np.int16),
                "Albedo_Quality": np.array([[0, 0, 0, 2]], dtype=np.uint8)}[self.name]


class File:
    def select(self, name): return Dataset(name)
    def attributes(self): return {}
    def end(self): pass


class W26Readers(unittest.TestCase):
    def test_raw_counts_precede_mask_and_fields_keep_own_support(self):
        with patch.object(albedo, "SD", return_value=File()):
            result = albedo._read_granule("synthetic.hdf")
        self.assertEqual(result["n_nonfill_px"], 2)  # paired, before QA and fill mutation
        self.assertEqual(result["n_best_px"], 1)     # paired, after best-QA filtering
        np.testing.assert_allclose(result["wsa"], [[0.1, 0.2, np.nan, np.nan]], equal_nan=True)
        np.testing.assert_allclose(result["bsa"], [[0.1, np.nan, 0.3, np.nan]], equal_nan=True)

    def test_quality_rule_text_matches_independent_masking(self):
        # #76: pixel 1 has white-sky only, pixel 2 black-sky only; both are kept.
        with patch.object(albedo, "SD", return_value=File()):
            result = albedo._read_granule("synthetic.hdf")
        self.assertEqual(result["n_best_wsa_px"], 2)
        self.assertEqual(result["n_best_bsa_px"], 2)
        self.assertEqual(result["n_best_px"], 1)
        self.assertIn("filtered independently", albedo.QUALITY_RULE)
        self.assertNotIn("must be non-fill", albedo.QUALITY_RULE)

    def test_fetch_entrypoint_calls_registered_snapshot_helper(self):
        import contextlib, io
        with patch.object(regolith, "fetch") as fetch, contextlib.redirect_stdout(io.StringIO()):
            regolith.fetch_regolith()
        self.assertEqual(fetch.call_count, 13)
        self.assertEqual({c.args[0] for c in fetch.call_args_list}, {regolith.DATASET})

    def test_monthly_reasons_name_each_missing_field(self):
        reasons = albedo.monthly_reasons(np.array([0.1, np.nan]), np.array([np.nan, 0.2]),
                                        np.array([4, 0]), np.array([1, 4]), np.array([2, 2]))
        import json
        self.assertEqual(json.loads(reasons[0]), {"albedo_bs_sw": "too-few-albedo-pixels"})
        self.assertEqual(json.loads(reasons[1]), {"albedo_ws_sw": "no-best-quality-retrieval"})

    def test_integration_checker_rejects_omitted_reason(self):
        import pyarrow as pa
        from p0ingest.w26_check import reason_mismatches
        table = pa.table({"wsa": [0.1, None], "bsa": [None, 0.2],
                          "missing_reason": ['{}', '{"wsa":"absent"}']})
        self.assertEqual(reason_mismatches(table, ["wsa", "bsa"]), 1)


if __name__ == "__main__": unittest.main()
