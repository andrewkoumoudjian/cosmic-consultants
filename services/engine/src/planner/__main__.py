"""python -m planner publish <derived_dir> <out_dir> [--repo <repo_root>]"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from .publish import load_l3, publish
from .tables import Tables, sha256_file


def main() -> int:
    ap = argparse.ArgumentParser(prog="planner")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("publish", help="write L4 from _derived parquet files + L3 YAML")
    p.add_argument("derived", type=Path)
    p.add_argument("out", type=Path)
    p.add_argument("--repo", type=Path, default=Path(__file__).resolve().parents[4])
    args = ap.parse_args()
    tables = Tables.from_parquet(args.derived)
    l3 = load_l3(args.repo)
    l3_inputs = [{"path": p.relative_to(args.repo).as_posix(), "sha256": sha256_file(p)}
                 for p in sorted((args.repo / "data").glob("objectives/*.yaml"))
                 + sorted((args.repo / "data").glob("campaigns/*.yaml"))
                 + [args.repo / "data/requirements/trait-map.yaml"]]
    manifest = publish(tables, l3, args.out, l3_inputs)
    print(json.dumps({"cells": len(tables.cells), "files": len(manifest["files"]), "manifestSha256": manifest["sha256"]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
