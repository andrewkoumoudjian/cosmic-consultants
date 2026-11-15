"""The engine's view of L1, L1m, L2 and the EONET event list
(DATA-PIPELINE.md section 5). Rows are plain dicts keyed by column name;
`None` is missing and keeps its `missing_reason` (rule 2: missing stays missing).

`Tables.from_parquet(derived_dir)` reads the assembled tables (stage A, #69/#127)
under `<derived_dir>/assembled/` with pyarrow (imported only there):
`sites-r4` holds L1 and L2 in one row per hexagon, `sites-r4-monthly` is L1m and
`hazard-events` the EONET list. Their `missing_reason` is keyed by column. The
per-source files (`cells-r4*`, `context-r4`) are not read: they lack dust and
carry trait-keyed reasons, so the L4 would show null dust and `not-in-source`.
Tests build `Tables` directly from small synthetic rows.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path

SITES_FILE = "assembled/sites-r4.parquet"            # L1 + L2, one row per hexagon
MONTHLY_FILE = "assembled/sites-r4-monthly.parquet"  # L1m, one row per (hexagon, month)
EVENTS_FILE = "assembled/hazard-events.parquet"      # EONET named events per hexagon


def input_paths(derived: Path) -> dict[str, Path]:
    """The three assembled files under `derived`. Sites and monthly are required;
    the event list is optional (no events means none listed, never zero rows invented)."""
    paths = {"sites": derived / SITES_FILE, "monthly": derived / MONTHLY_FILE, "events": derived / EVENTS_FILE}
    missing = [p for k, p in paths.items() if k != "events" and not p.exists()]
    if missing:
        raise FileNotFoundError(
            f"{', '.join(str(p) for p in missing)} not found. Build them with "
            "`python -m p0ingest.assemble` (services/ingest) or copy snapshots/_derived/assembled/ from Drive.")
    return paths


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def reasons_of(row: dict | None) -> dict[str, str]:
    """Parse a row's `missing_reason` JSON text (trait or column -> code)."""
    if not row or not row.get("missing_reason"):
        return {}
    try:
        value = json.loads(row["missing_reason"])
    except (TypeError, ValueError):
        return {"*": str(row["missing_reason"])}
    return value if isinstance(value, dict) else {"*": str(value)}


def reason_for(row: dict | None, column: str, trait: str | None = None) -> str:
    """Best reason code for a null `column`: exact column, then a `prefix_*`
    wildcard key, then the trait, then a generic code. Never invents a value."""
    reasons = reasons_of(row)
    if column in reasons:
        return reasons[column]
    for key, code in reasons.items():
        if key.endswith("*") and column.startswith(key[:-1]):
            return code
    if trait and trait in reasons:
        return reasons[trait]
    return "not-in-source" if row is not None else "no-row-for-hexagon"


@dataclass
class Tables:
    cells: dict[str, dict]                                   # L1: h3 -> row
    monthly: dict[tuple[str, int], dict] = field(default_factory=dict)  # L1m: (h3, month) -> row
    context: dict[str, dict] = field(default_factory=dict)  # L2: h3 -> row
    events: dict[str, list[dict]] = field(default_factory=dict)  # h3 -> EONET event rows
    inputs: list[dict] = field(default_factory=list)        # [{path, sha256}] of files read

    def order(self) -> list[str]:
        """Hexagon order for every published array: sorted h3 ids, so builds
        are deterministic whatever order the parquet rows came in."""
        return sorted(self.cells)

    @classmethod
    def from_parquet(cls, derived: Path) -> "Tables":
        import pyarrow.parquet as pq  # only needed for real data

        paths = input_paths(derived)
        inputs: list[dict] = []

        def rows(key: str) -> list[dict]:
            path = paths[key]
            if not path.exists():
                return []
            inputs.append({"path": f"data/snapshots/_derived/{path.relative_to(derived).as_posix()}",
                           "sha256": sha256_file(path)})
            return pq.read_table(path).to_pylist()

        cells = {r["h3"]: r for r in rows("sites")}
        monthly = {(r["h3"], int(r["month"])): r for r in rows("monthly")}
        events: dict[str, list[dict]] = {}
        for r in rows("events"):
            events.setdefault(r["h3"], []).append(r)
        if not cells:
            raise ValueError(f"{paths['sites']} has no rows")
        # sites-r4 carries the L2 columns too, so step 4/5 read the same row.
        return cls(cells, monthly, cells, events, inputs)
