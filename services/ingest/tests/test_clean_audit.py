import unittest
import numpy as np
import polars as pl
from p0ingest.clean_audit import mask_counts, output_counts


class CleaningEvidence(unittest.TestCase):
    def test_counts_keep_input_and_output_grains_separate(self):
        counts = mask_counts(np.array([0, 7499, 7500, 65535]), lambda x: x < 7500)
        self.assertEqual(counts, {"inputValues": 4, "maskedInputValues": 2, "retainedInputValues": 2})
        result = output_counts(pl.DataFrame({"x": [None, 150.0]}), ["x"])
        self.assertEqual(result["columns"]["x"]["nullOutputRows"], 1)
        self.assertIsNone(result["maskedInputValues"])
        self.assertNotEqual(result["maskedInputValues"], result["columns"]["x"]["nullOutputRows"])


if __name__ == "__main__":
    unittest.main()
