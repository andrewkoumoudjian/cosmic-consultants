"""Plan request <-> share-link URL (MISSION-PLANNER.md "UI", contract
contracts/plan-request.schema.json).

One request drives all six steps and lives in the URL, so a plan is a link:

    ?body=mars&obj=OP-5LM&type=robotic&months=6-8&days=14&team=6
     &lim=access:240,protected:0&must=terrain,surfaceMaterial&sort=terrain
     &top=20&pins=<h3>,<h3>

`to_query(r)` writes keys in one fixed order, and `parse_query(to_query(r)) == r`
for every request the contract accepts without `successCriteria` (those are
too long for a URL and live in the hash with the checklist). The UI test
"the URL round-trips the request exactly" is this function pair.
"""
from __future__ import annotations

from urllib.parse import parse_qsl, quote, urlencode

ORDER = ["body", "obj", "cat", "preset", "type", "months", "days", "team", "lim", "must", "nice", "band", "sort", "top", "pins"]
LIMIT_KEYS = ["access", "protected", "airport", "slope"]
SAFE = ",:.<-"


def _num(text: str) -> int | float:
    """Integers stay ints (240), anything else is a float (0.5). repr()
    round-trips floats exactly, so the pair is lossless."""
    try:
        return int(text)
    except ValueError:
        value = float(text)
        if value != value or value in (float("inf"), float("-inf")):
            raise ValueError(f"not a finite number: {text!r}")
        return value


def _fmt(value: int | float) -> str:
    return str(value) if isinstance(value, int) and not isinstance(value, bool) else repr(float(value))


def to_query(r: dict) -> str:
    """Request dict -> query string (no leading '?')."""
    if r.get("version") != 1:
        raise ValueError("only plan-request version 1 is supported")
    if "successCriteria" in r:
        raise ValueError("successCriteria are not URL fields; keep them in the hash with the checklist")
    out: dict[str, str] = {
        "body": r["body"],
        "obj": r["objectiveId"],
        "type": r["missionType"],
        "months": f"{r['months']['start']}-{r['months']['end']}",
    }
    if "category" in r:
        out["cat"] = r["category"]
    if "presetCampaignId" in r:
        out["preset"] = r["presetCampaignId"]
    if "durationDays" in r:
        out["days"] = _fmt(r["durationDays"])
    if "teamSize" in r:
        out["team"] = _fmt(r["teamSize"])
    if "limits" in r:
        out["lim"] = ",".join(f"{k}:{_fmt(r['limits'][k])}" for k in LIMIT_KEYS if k in r["limits"])
    for key in ("must", "nice"):
        if key in r:
            out[key] = ",".join(r[key])
    if "bandEdits" in r:
        out["band"] = ",".join(
            f"{e['dimension']}:{_fmt(e['lo'])}..{_fmt(e['hi'])}" + ("<" if e.get("hiStrict") else "")
            for e in r["bandEdits"]
        )
    if "sortBy" in r:
        out["sort"] = r["sortBy"]
    if "top" in r:
        out["top"] = "all" if r["top"] is None else _fmt(r["top"])
    if "pins" in r:
        out["pins"] = ",".join(r["pins"])
    return urlencode([(k, out[k]) for k in ORDER if k in out], safe=SAFE, quote_via=quote)


def _list(text: str) -> list[str]:
    return [] if text == "" else text.split(",")


def parse_query(query: str) -> dict:
    """Query string (with or without '?') -> request dict. Unknown or repeated
    keys are errors, so a hand-edited link can't silently drop a constraint."""
    pairs = parse_qsl(query.lstrip("?"), keep_blank_values=True, strict_parsing=bool(query.lstrip("?")))
    q: dict[str, str] = {}
    for k, v in pairs:
        if k not in ORDER:
            raise ValueError(f"unknown URL key {k!r}")
        if k in q:
            raise ValueError(f"URL key {k!r} given twice")
        q[k] = v
    for k in ("body", "obj", "type", "months"):
        if k not in q:
            raise ValueError(f"missing URL key {k!r}")
    start, _, end = q["months"].partition("-")
    r: dict = {
        "version": 1,
        "body": q["body"],
        "objectiveId": q["obj"],
        "missionType": q["type"],
        "months": {"start": int(start), "end": int(end)},
    }
    if "cat" in q:
        r["category"] = q["cat"]
    if "preset" in q:
        r["presetCampaignId"] = q["preset"]
    if "days" in q:
        r["durationDays"] = int(q["days"])
    if "team" in q:
        r["teamSize"] = int(q["team"])
    if "lim" in q:
        limits = {}
        for item in _list(q["lim"]):
            key, _, value = item.partition(":")
            if key not in LIMIT_KEYS or key in limits:
                raise ValueError(f"bad or repeated limit {key!r}")
            limits[key] = _num(value)
        r["limits"] = limits
    for key, field in (("must", "must"), ("nice", "nice")):
        if key in q:
            r[field] = _list(q[key])
    # The writer emits keys in ORDER, so field order in r matches to_query's input
    # convention only up to dict ordering; equality of dicts ignores order anyway.
    if "band" in q:
        edits = []
        for item in _list(q["band"]):
            dim, _, rng = item.partition(":")
            strict = rng.endswith("<")
            lo, sep, hi = rng.rstrip("<").partition("..")
            if not sep:
                raise ValueError(f"band edit {item!r} needs lo..hi")
            e = {"dimension": dim, "lo": _num(lo), "hi": _num(hi)}
            if strict:
                e["hiStrict"] = True
            edits.append(e)
        r["bandEdits"] = edits
    if "sort" in q:
        r["sortBy"] = q["sort"]
    if "top" in q:
        r["top"] = None if q["top"] == "all" else int(q["top"])
    if "pins" in q:
        r["pins"] = _list(q["pins"])
    return r


def months_in_window(window: dict) -> list[int]:
    """Requested months, inclusive, wrapping over the new year (11-2 = 11,12,1,2)."""
    s, e = window["start"], window["end"]
    return list(range(s, e + 1)) if s <= e else list(range(s, 13)) + list(range(1, e + 1))
