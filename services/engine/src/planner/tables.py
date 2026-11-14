"""The engine's view of L1, L1m, L2 and the EONET event list
(DATA-PIPELINE.md section 5). Rows are plain dicts keyed by column name;
`None` is missing and keeps its `missing_reason` (rule 2: missing stays missing).

`Tables.from_parquet(derived_dir)` reads the real files with pyarrow (imported
only there). Tests build `Tables` directly from small synthetic rows.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path

L1_FILE = "cells-r4.parquet"
L1M_FILE = "cells-r4-monthly.parquet"
L2_FILE = "context-r4.parquet"
EVENTS_FILE = "eonet-events-r4.parquet"


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

        def rows(name: str) -> list[dict]:
            path = derived / name
            if not path.exists():
                return []
            inputs.append({"path": f"data/snapshots/_derived/{name}", "sha256": sha256_file(path)})
            return pq.read_table(path).to_pylist()

        inputs: list[dict] = []
        cells = {r["h3"]: r for r in rows(L1_FILE)}
        monthly = {(r["h3"], int(r["month"])): r for r in rows(L1M_FILE)}
        context = {r["h3"]: r for r in rows(L2_FILE)}
        events: dict[str, list[dict]] = {}
        for r in rows(EVENTS_FILE):
            events.setdefault(r["h3"], []).append(r)
        if not cells:
            raise FileNotFoundError(f"{derived / L1_FILE} is required")
        return cls(cells, monthly, context, events, inputs)
