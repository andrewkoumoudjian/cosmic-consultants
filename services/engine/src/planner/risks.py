"""Step 5 risks (MISSION-PLANNER.md step 5; contract site-plan `risks`).

One row per hazard type, each its own flag. No combined risk score and no
hazard rate: EONET is a curated list whose size changes a lot by year
(DATA-PIPELINE section 4.1, ADR-0006), so a 0 means "none recorded in EONET".
Cold and heat come from our L1m temperatures, not EONET.
"""
from __future__ import annotations

from .request import months_in_window
from .tables import Tables, reason_for

EONET_CATEGORIES = ["wildfires", "volcanoes", "severeStorms", "floods", "landslides",
                    "dustHaze", "earthquakes", "snow", "tempExtremes", "drought"]
EONET_DISCLAIMER = ("EONET is a curated list of notable natural events, not a complete record: "
                    "0 means none recorded in EONET near here, not that none happened.")


def _reason(row, column, trait=None):
    code = reason_for(row, column, trait)
    words = "".join(c if c.isalnum() else " " for c in code.lower()).split()
    return {"code": "-".join(words[:6]) or "missing", "text": f"{column} is missing ({code})."}


def eonet_rows(tables: Tables, h3: str) -> list[dict]:
    ctx = tables.context.get(h3)
    listed = tables.events.get(h3, [])
    rows = []
    for cat in EONET_CATEGORIES:
        column = f"eonet_{cat}_events"
        n = None if ctx is None else ctx.get(column)
        row = {"hazard": cat, "kind": "eonet", "eventsRecorded": n}
        evs = sorted((e for e in listed if e.get("category") == cat), key=lambda e: (e.get("start_date") or "", e.get("event_id") or ""))
        row["events"] = [
            {k: v for k, v in (("eonetId", e["event_id"]), ("title", e.get("title") or e["event_id"]),
                               ("date", (e.get("start_date") or "")[:10]), ("url", e.get("source_url"))) if v}
            for e in evs if e.get("start_date")
        ]
        if n is None:
            row["reason"] = _reason(ctx, column)
        rows.append(row)
    return rows


def burned_row(tables: Tables, h3: str, months: list[int]) -> dict:
    """Mean burned share over the requested months (P1: present only once
    MCD64A1 columns exist in L2). Missing months make the value unknown."""
    ctx = tables.context.get(h3)
    cols = [f"burned_pct_{m:02d}" for m in months]
    values = [None if ctx is None else ctx.get(c) for c in cols]
    row = {"hazard": "burnedArea", "kind": "burnedArea", "unit": "% of hexagon burned, mean over requested months (2015-2024 climatology)"}
    if any(v is None for v in values) or not values:
        row["value"] = None
        missing = next((c for c, v in zip(cols, values) if v is None), cols[0] if cols else "burned_pct")
        row["reason"] = _reason(ctx, missing)
    else:
        row["value"] = sum(values) / len(values)
    return row


def terrain_row(tables: Tables, h3: str) -> dict:
    cell = tables.cells.get(h3)
    value = None if cell is None else cell.get("slope_frac_gt30")
    row = {"hazard": "steepTerrain", "kind": "terrain", "value": value, "unit": "share of ground steeper than 30 deg"}
    if value is None:
        row["reason"] = _reason(cell, "slope_frac_gt30", "terrain")
    return row


def temperature_rows(tables: Tables, h3: str, months: list[int]) -> list[dict]:
    """Coldest night and hottest day among the requested months (L1m)."""
    out = []
    for hazard, column, pick in (("coldestMonth", "lst_night_k", min), ("hottestMonth", "lst_day_k", max)):
        known = [(tables.monthly[(h3, m)][column], m) for m in months
                 if (h3, m) in tables.monthly and tables.monthly[(h3, m)].get(column) is not None]
        row = {"hazard": hazard, "kind": "temperature", "unit": "K"}
        if len(known) < len(months):
            # Rule 2: a window with an unknown month has no known extreme.
            gap = next(m for m in months if (h3, m) not in tables.monthly or tables.monthly[(h3, m)].get(column) is None)
            row.update(month=None, value=None, reason=_reason(tables.monthly.get((h3, gap)), column, "thermal"))
        else:
            value, month = pick(known, key=lambda t: (t[0], t[1]))
            row.update(month=month, value=value)
        out.append(row)
    return out


def risks(tables: Tables, h3: str, request: dict) -> dict:
    months = months_in_window(request["months"])
    return {
        "eonetDisclaimer": EONET_DISCLAIMER,
        "rows": eonet_rows(tables, h3) + [burned_row(tables, h3, months), terrain_row(tables, h3)]
                + temperature_rows(tables, h3, months),
    }
