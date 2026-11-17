import gzip
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import numpy as np
import polars as pl
import yaml

from p0ingest.clean_audit import mask_counts, output_counts
from p0ingest.source_qa import (
    audit_terrain_ledger,
    decode_mod11c3_qc,
    load_verified_mod11c3_receipt,
    mod11c3_policy_masks,
    verify_catalog_licenses,
)


class CleaningEvidence(unittest.TestCase):
    def test_counts_keep_input_and_output_grains_separate(self):
        counts = mask_counts(np.array([0, 7499, 7500, 65535]), lambda x: x < 7500)
        self.assertEqual(counts, {"inputValues": 4, "maskedInputValues": 2, "retainedInputValues": 2})
        result = output_counts(pl.DataFrame({"x": [None, 150.0]}), ["x"])
        self.assertEqual(result["columns"]["x"]["nullOutputRows"], 1)
        self.assertIsNone(result["maskedInputValues"])
        self.assertNotEqual(result["maskedInputValues"], result["columns"]["x"]["nullOutputRows"])


class SourceQaUnitTests(unittest.TestCase):
    def test_qa_policy_yaml_and_catalog_licenses_verify(self):
        repo = Path(__file__).resolve().parents[3]
        policy = yaml.safe_load((repo / "data" / "pipeline" / "qa-policy.yaml").read_text(encoding="utf-8"))
        self.assertEqual(policy["workOrder"], 76)
        self.assertEqual(policy["status"], "proposed")
        self.assertTrue(policy["accountingRules"]["preserveHistoricalArtifactsUntilFreeze"])
        self.assertTrue(policy["accountingRules"]["neverFabricateUnavailableFilterCounts"])
        lics = verify_catalog_licenses(list(policy["licenses"].keys()), catalog_dir=repo / "data" / "catalog")
        for dsid, info in lics.items():
            self.assertTrue(info["verified"])
            self.assertEqual(info["licenseId"], policy["licenses"][dsid]["licenseId"])

    def test_verify_catalog_licenses_rejects_restricted_or_unverified(self):
        with tempfile.TemporaryDirectory() as tmp:
            cat = Path(tmp)
            (cat / "bad.yaml").write_text("license:\n  id: restricted\n  verified: true\n", encoding="utf-8")
            (cat / "unv.yaml").write_text("license:\n  id: cc0\n  verified: false\n", encoding="utf-8")
            with self.assertRaises(PermissionError):
                verify_catalog_licenses(["bad"], catalog_dir=cat)
            with self.assertRaises(PermissionError):
                verify_catalog_licenses(["unv"], catalog_dir=cat)

    def test_mod11c3_qc_decode_and_policy_masks(self):
        # Construct 5 pixels:
        # 0: raw=0,    qc=0b11_00_00_11 (mand=3 not produced) -> always masked
        # 1: raw=15000,qc=0b00_00_00_00 (mand=0, err=0 <=1K) -> passes all
        # 2: raw=15000,qc=0b01_00_00_01 (mand=1, err=1 <=2K) -> fails P3/P4, passes P0/P1/P2
        # 3: raw=15000,qc=0b10_00_00_01 (mand=1, err=2 <=3K) -> fails P2/P3/P4, passes P0/P1
        # 4: raw=15000,qc=0b11_00_00_01 (mand=1, err=3 >3K)  -> fails P1/P2/P3/P4, passes P0
        lst = np.array([0, 15000, 15000, 15000, 15000], dtype=np.uint16)
        qc = np.array([0b11000011, 0b00000000, 0b01000001, 0b10000001, 0b11000001], dtype=np.uint8)
        dec = decode_mod11c3_qc(qc)
        self.assertEqual(dec["mand_qa"].tolist(), [3, 0, 1, 1, 1])
        self.assertEqual(dec["lst_err"].tolist(), [3, 0, 1, 2, 3])
        masks = mod11c3_policy_masks(lst, qc)
        self.assertEqual(masks["P0-baseline"].tolist(), [False, True, True, True, True])
        self.assertEqual(masks["P1-err-le-3k"].tolist(), [False, True, True, True, False])
        self.assertEqual(masks["P2-err-le-2k"].tolist(), [False, True, True, False, False])
        self.assertEqual(masks["P3-mand-qa-00-only"].tolist(), [False, True, False, False, False])
        self.assertEqual(masks["P4-err-le-1k"].tolist(), [False, True, False, False, False])

    def test_terrain_ledger_audit_never_fabricates_missing_mask_counts(self):
        with tempfile.TemporaryDirectory() as tmp:
            tdir = Path(tmp)
            tlist = tdir / "tileList.txt"
            tlist.write_text("tile_A\ntile_B\n", encoding="utf-8")
            ledger = tdir / "terrain-r4-ledger.jsonl.gz"
            with gzip.open(ledger, "wt", encoding="utf-8") as f:
                f.write(json.dumps({"tile": "tile_A", "shape": [450, 450], "arraySha256": "a" * 64}) + "\n")
                f.write(json.dumps({"tile": "tile_B", "shape": [450, 450], "arraySha256": "b" * 64}) + "\n")
            res = audit_terrain_ledger(tlist, ledger)
            self.assertEqual(res["expectedTiles"], 2)
            self.assertEqual(res["ledgerTiles"], 2)
            self.assertEqual(res["missingTiles"], 0)
            self.assertEqual(res["errorTiles"], 0)
            self.assertFalse(res["waterMasked"])
            self.assertEqual(res["appliedNodataFilterCount"], 0)
            self.assertIsNone(res["invalidInputValues"])
            self.assertIsNone(res["maskedWaterPixels"])

    def test_mod11c3_receipt_verification_rejects_mismatched_manifest(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            snap = root / "data" / "snapshots" / "modis-mod11c3"
            snap.mkdir(parents=True)
            f = snap / "MOD11C3.A2023001.hdf"
            f.write_bytes(b"test-granule")
            import hashlib
            digest = hashlib.sha256(b"test-granule").hexdigest()
            manifest = [{"datasetId": "modis-mod11c3", "localPath": "data/snapshots/modis-mod11c3/MOD11C3.A2023001.hdf", "sha256": digest}]
            receipt = root / "receipt.json"
            receipt.write_text(json.dumps({"granules": [{"localPath": manifest[0]["localPath"], "sha256": digest}]}), encoding="utf-8")
            self.assertIsNotNone(load_verified_mod11c3_receipt(receipt, manifest, repo_root=root))
            manifest_bad = [{"datasetId": "modis-mod11c3", "localPath": manifest[0]["localPath"], "sha256": "0" * 64}]
            self.assertIsNone(load_verified_mod11c3_receipt(receipt, manifest_bad, repo_root=root))

    def test_committed_qa_receipts_preserve_honest_accounting_and_match_policy(self):
        repo = Path(__file__).resolve().parents[3]
        qa_dir = repo / "docs" / "qa" / "source-qa-76"
        modis = json.loads((qa_dir / "mod11c3-qa-replay.json").read_text(encoding="utf-8"))
        self.assertEqual(modis["granuleCount"], 120)
        self.assertEqual(modis["granuleCount2023"], 12)
        for side in ("Day", "Night"):
            self.assertEqual(modis["sides"][side]["anomalies"]["rawGe7500WithBadMandQa"], 0)
            self.assertEqual(modis["sides"][side]["anomalies"]["rawLt7500WithGoodMandQa"], 0)

        dem = json.loads((qa_dir / "dem-wbm-probe.json").read_text(encoding="utf-8"))
        self.assertEqual(len(dem["tiles"]), 7)
        hist = dem["historicalLedgerAudit"]
        self.assertEqual(hist["expectedTiles"], 26450)
        self.assertEqual(hist["ledgerTiles"], 26450)
        self.assertFalse(hist["waterMasked"])
        self.assertEqual(hist["appliedNodataFilterCount"], 0)
        self.assertIsNone(hist["invalidInputValues"])

        cr = json.loads((qa_dir / "cleaning-report-76.json").read_text(encoding="utf-8"))
        self.assertFalse(cr["completeInputFilterAccounting"])
        self.assertIsNone(cr["rules"]["dem-unmasked-source"]["invalidInputValues"])
        self.assertEqual(cr["rules"]["esa-cci-fill-255"]["maskedInputValues"], 262261805)
        self.assertEqual(cr["rules"]["raster-nodata"]["maskedInputValues"], 530356617)
        self.assertEqual(cr["rules"]["myd11c3-fill"]["maskedInputValues"], None)


if __name__ == "__main__":
    unittest.main()
