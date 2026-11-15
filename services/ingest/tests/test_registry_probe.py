"""Tests for scripts/registry_probe.py Google Drive links and INDEX.md generation."""
import importlib.util
import pathlib
import unittest

REPO = pathlib.Path(__file__).resolve().parents[3]


def load_registry_probe():
    spec = importlib.util.spec_from_file_location("registry_probe", REPO / "scripts" / "registry_probe.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class RegistryProbeIndex(unittest.TestCase):
    def test_drive_cell_combines_raw_and_available_derived_links(self):
        rp = load_registry_probe()
        dl = {
            "rawFolders": {"modis-myd11c3": {"url": "https://drive.google.com/drive/folders/RAW1"}},
            "derivedItems": {
                "aqua-lst-r4-monthly.parquet": {"isDir": False, "url": "https://drive.google.com/file/d/DRV1/view"},
            },
            "datasetDerived": {"modis-myd11c3": ["aqua-lst-r4-monthly.parquet", "missing.parquet"]},
        }
        cell = rp.drive_cell("modis-myd11c3", dl)
        self.assertEqual(
            cell,
            "[raw](https://drive.google.com/drive/folders/RAW1), "
            "[aqua-lst-r4-monthly.parquet](https://drive.google.com/file/d/DRV1/view)",
        )
        self.assertEqual(rp.drive_cell("unmirrored-id", dl), "—")

    def test_index_md_includes_mirror_banner_and_drive_column(self):
        rp = load_registry_probe()
        dl = {
            "folders": {
                "snapshots": {"url": "https://drive.google.com/drive/folders/ROOT"},
                "_derived": {"url": "https://drive.google.com/drive/folders/DER"},
                "_derived/assembled": {"url": "https://drive.google.com/drive/folders/ASM"},
            },
            "rawFolders": {"alpha": {"url": "https://drive.google.com/drive/folders/A1"}},
            "derivedItems": {},
            "datasetDerived": {},
        }
        rows = {
            "alpha": {
                "datasetId": "alpha",
                "bodies": ["earth"],
                "dimensions": ["thermal"],
                "source": {"archive": "NASA"},
                "status": "candidate",
                "license": {"id": "cc0"},
            }
        }
        entries = [{"datasetId": "alpha", "summary": "HTTP 200", "license": {"verified": True}}]
        md = rp.index_md(entries, rows, "2026-11-14", drive_links=dl)
        self.assertIn("Google Drive mirror: [snapshots/](https://drive.google.com/drive/folders/ROOT)", md)
        self.assertIn("| datasetId | body | dimensions | archive | status | license | lic. verified | drive | probe |", md)
        self.assertIn("| [raw](https://drive.google.com/drive/folders/A1) | HTTP 200 |", md)

    def test_catalog_index_tracks_every_catalog_yaml_and_drive_links(self):
        rp = load_registry_probe()
        paths = sorted(p for p in (REPO / "data" / "catalog").glob("*.yaml") if p.name != "dataset.template.yaml")
        idx = (REPO / "data" / "catalog" / "INDEX.md").read_text(encoding="utf-8")
        self.assertIn("Google Drive mirror:", idx)
        for p in paths:
            self.assertIn(f"[{p.stem}]({p.stem}.yaml)", idx)
        self.assertTrue(rp.DRIVE_LINKS.exists())


if __name__ == "__main__":
    unittest.main()
