"""Step 4 logistics and the request's hard limits (MISSION-PLANNER.md step 4;
contract site-plan `logistics` and `limits`).

No verdicts here: these are L2 values in physical units, plain-words notes
written from them, and the scientist's checklist prompts. A limit outcome is
`pass`/`fail` only for a known value; an unknown value is `unknown` and never
removes a site (S7i, proposed in #80).
"""
from __future__ import annotations

from .tables import Tables, reason_for

# limit key -> (table, column, unit) ; same mapping as plan-request.schema.json
LIMIT_COLUMNS = {
    "access": ("L2", "access_min_median", "min"),
    "protected": ("L2", "protected_pct", "%"),
    "airport": ("L2", "airport_km", "km"),
    "slope": ("L1", "slope_mean_deg", "deg"),
}
MEASURED = {
    "accessMinMedian": ("access_min_median", "min"),
    "accessMinP10": ("access_min_p10", "min"),
    "airportKm": ("airport_km", "km"),
    "protectedPct": ("protected_pct", "%"),
}


def _measured(row: dict | None, column: str, unit: str) -> dict:
    value = None if row is None else row.get(column)
    out = {"value": value, "unit": unit}
    if value is None:
        code = reason_for(row, column)
        out["reason"] = {"code": _code(code), "text": f"{column} is missing for this hexagon ({code})."}
    return out


def _code(text: str) -> str:
    """Reason text -> contract reason code (lowercase words joined by '-')."""
    words = "".join(c if c.isalnum() else " " for c in text.lower()).split()
    return "-".join(words[:6]) or "missing"


def limits(tables: Tables, h3: str, request: dict) -> list[dict]:
    out = []
    for key in ("access", "protected", "airport", "slope"):
        if key not in request.get("limits", {}):
            continue
        table, column, unit = LIMIT_COLUMNS[key]
        row = tables.context.get(h3) if table == "L2" else tables.cells.get(h3)
        value = None if row is None else row.get(column)
        cap = request["limits"][key]
        item = {"limit": key, "max": cap, "value": value, "unit": unit,
                "outcome": "unknown" if value is None else "pass" if value <= cap else "fail"}
        if value is None:
            code = reason_for(row, column)
            item["reason"] = {"code": _code(code), "text": f"{column} is unknown here ({code}), so this limit can't be checked."}
        out.append(item)
    return out


def _hours(minutes: float) -> str:
    return f"{minutes / 60:.1f} h" if minutes >= 90 else f"{minutes:.0f} min"


def notes(m: dict) -> list[str]:
    """Plain-words notes, only from known numbers. Unknowns are said as unknown."""
    parts = []
    a = m["accessMinMedian"]["value"]
    parts.append(f"About {_hours(a)} from the nearest city" if a is not None else "Travel time to a city is unknown")
    k = m["airportKm"]["value"]
    parts.append(f"nearest paved-runway airport {k:.0f} km away" if k is not None else "nearest airport distance unknown")
    p = m["protectedPct"]["value"]
    parts.append(f"protected land on {p:.0f}% of the hexagon" if p is not None else "protected-land share unknown")
    return [", ".join(parts) + "."]


def checklist(m: dict, request: dict) -> list[dict]:
    """Planning fields no worldwide dataset fills. Prompts come from what we
    know; answers are the scientist's, so they start empty."""
    p = m["protectedPct"]["value"]
    if p is None:
        permit = "Protected-land share is unknown here: check protected areas and permits before planning."
    elif p > 0:
        permit = f"Protected land covers {p:.0f}% of the hexagon: a permit is likely needed."
    else:
        permit = "No protected land recorded in the hexagon: still check national and local permits."
    a, k = m["accessMinMedian"]["value"], m["airportKm"]["value"]
    cost = "Cost band proxy (not a budget): " + (
        f"about {_hours(a)} from a city" if a is not None else "travel time unknown") + (
        f", airport {k:.0f} km away." if k is not None else ", airport distance unknown.")
    days, team = request.get("durationDays"), request.get("teamSize")
    crew = f"{team} people for {days} days" if days and team else "team size and length not set"
    return [
        {"item": "permits", "prompt": permit, "answer": None, "from": "scientist"},
        {"item": "costs", "prompt": cost, "answer": None, "from": "scientist"},
        {"item": "personnel", "prompt": f"Planned: {crew}. Who is on site, with what training?", "answer": None, "from": "scientist"},
        {"item": "equipment", "prompt": "Which instruments, vehicles and spares go in the field?", "answer": None, "from": "scientist"},
        {"item": "infrastructure", "prompt": "Lodging, power, communications and medical access near the site?", "answer": None, "from": "scientist"},
    ]


def logistics(tables: Tables, h3: str, request: dict) -> dict:
    row = tables.context.get(h3)
    m = {name: _measured(row, column, unit) for name, (column, unit) in MEASURED.items()}
    return {**m, "notes": notes(m), "checklist": checklist(m, request)}
