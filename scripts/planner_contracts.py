"""Planner contract checks (W20, #78), called from validate_contracts.py.

Validates, with the cross-file and arithmetic rules JSON Schema cannot express:

1. data/requirements/trait-map.yaml against contracts/trait-map.schema.json:
   objectiveId exists, the trait is one the objective requires, one rule per
   (objective, trait), earthColumn is a real column of its table
   (DATA-PIPELINE.md section 5), lo <= hi, the band is not empty, a precedent
   rule names an existing campaign. Required traits with no rule are printed as
   unknown (never an error: unknown is a legal answer).
2. data/fixtures/example-plan-request.json against plan-request.schema.json:
   the objective exists for the body, must/nice don't overlap, pins are H3
   resolution-4 cells, band edits have lo <= hi.
3. data/fixtures/example-site-plan.json against site-plan.schema.json: one
   verdict row per required trait; each verdict agrees with its value, band and
   gap; bands, priority and origin follow the trait map and the request; L1m
   rows cover exactly the requested months and the window verdict follows the
   proposed rule (miss if any month misses, else unknown if any is unknown,
   else match); funnel class, Pareto layer, season months, test split and
   not-testable list agree with the rest; Shapley shares add up to closeness;
   no key anywhere looks like a score, rating or total.
4. self_test(): broken copies of all three must be rejected.
"""
from __future__ import annotations

import copy
import glob
import json
import re
from pathlib import Path

import h3
import yaml
from jsonschema import Draft202012Validator, FormatChecker
from referencing import Registry, Resource

ROOT = Path(__file__).resolve().parent.parent
TRAIT_MAP = "data/requirements/trait-map.yaml"
PLAN_REQUEST_FIXTURE = "data/fixtures/example-plan-request.json"
SITE_PLAN_FIXTURE = "data/fixtures/example-site-plan.json"
TOL = 1e-9

# Columns per table, from DATA-PIPELINE.md section 5 at 03a040e (checked against
# the names used in services/ingest/src/p0ingest/*.py). A new column needs a
# spec change first, then a line here.
COLUMNS = {
    "L1": {
        "h3", "res", "lat", "lon", "cmg_pixels", "land_pct_mean",
        "lst_day_max_k", "lst_night_min_k", "lst_diurnal_range_mean_k", "lst_months_with_range", "lst_valid_pixels",
        "barren_pct", "snow_ice_pct", "water_pct", "permafrost_pct",
        "dem_pixels", "elev_mean_m", "elev_min_m", "elev_max_m",
        "slope_mean_deg", "slope_frac_lt5", "slope_frac_lt15", "slope_frac_gt30",
        "sun_noon_elev_max_deg", "sun_noon_elev_min_deg", "polar_night", "polar_day", "dust_aod_mean",
    },
    "L1m": {
        "lst_day_k", "lst_night_k", "lst_diurnal_k", "lst_valid_pixels",
        "sun_noon_elev_deg", "daylight_h", "polar_day", "polar_night", "dust_aod",
    },
    "L2": {"access_min_median", "access_min_p10", "protected_pct", "airport_km"},
}
EONET_CATEGORIES = ["wildfires", "volcanoes", "severeStorms", "floods", "landslides", "dustHaze", "earthquakes", "snow", "tempExtremes", "drought"]
L2_PATTERNS = [re.compile(r"^eonet_(%s)_(events|months)$" % "|".join(EONET_CATEGORIES)), re.compile(r"^burned_pct_(0[1-9]|1[0-2])$")]
FORBIDDEN_KEY = re.compile(r"score|suitab|rating|overall|total|weight", re.IGNORECASE)


def _validators() -> dict[str, Draft202012Validator]:
    names = ["trait-map.schema.json", "plan-request.schema.json", "site-plan.schema.json"]
    schemas = {n: json.loads((ROOT / "contracts" / n).read_text(encoding="utf-8")) for n in names}
    registry = Registry().with_resources((s["$id"], Resource.from_contents(s)) for s in schemas.values())
    out = {}
    for n, s in schemas.items():
        Draft202012Validator.check_schema(s)
        out[n] = Draft202012Validator(s, registry=registry, format_checker=FormatChecker())
    return out


def _schema_errors(v, doc) -> list[str]:
    return [f"{'/'.join(map(str, e.path)) or '<root>'}: {e.message}" for e in v.iter_errors(doc)]


def _column_known(table: str, column: str) -> bool:
    if column in COLUMNS.get(table, set()):
        return True
    return table == "L2" and any(p.match(column) for p in L2_PATTERNS)


def _campaign_ids() -> set[str]:
    ids = set()
    for p in glob.glob(str(ROOT / "data/campaigns/*.yaml")):
        doc = yaml.safe_load(Path(p).read_text(encoding="utf-8"))
        if isinstance(doc, dict) and doc.get("campaignId"):
            ids.add(doc["campaignId"])
    return ids


def _objectives_by_id(objectives: dict) -> dict[str, dict]:
    """objectives is validate_contracts' {(objectiveId, body): row}."""
    return {oid: row for (oid, _body), row in objectives.items()}


def _months(window: dict) -> list[int]:
    s, e = window["start"], window["end"]
    return list(range(s, e + 1)) if s <= e else list(range(s, 13)) + list(range(1, e + 1))


# ---------- 1. trait map ----------

def check_trait_map(v, doc, objectives: dict, campaigns: set[str], verbose: bool = True) -> list[str]:
    errs = _schema_errors(v, doc)
    if errs:
        return errs
    by_id = _objectives_by_id(objectives)
    seen: set[tuple[str, str]] = set()
    for i, r in enumerate(doc["rules"]):
        at = f"rules/{i} ({r['objectiveId']} {r['dimension']})"
        obj = by_id.get(r["objectiveId"])
        if obj is None:
            errs.append(f"{at}: objectiveId is not a row in data/objectives/")
            continue
        if r["dimension"] not in obj["requiredDimensions"]:
            errs.append(f"{at}: {r['dimension']} is not a required dimension of {r['objectiveId']}")
        key = (r["objectiveId"], r["dimension"])
        if key in seen:
            errs.append(f"{at}: second rule for the same (objective, trait)")
        seen.add(key)
        if r["earthColumn"] is not None and not _column_known(r["table"], r["earthColumn"]):
            errs.append(f"{at}: {r['earthColumn']!r} is not a column of {r['table']} in DATA-PIPELINE.md section 5")
        band = r["band"]
        if band is not None:
            if band["lo"] > band["hi"]:
                errs.append(f"{at}: band lo {band['lo']} > hi {band['hi']}")
            elif r.get("hiStrict") and band["lo"] == band["hi"]:
                errs.append(f"{at}: band is empty (lo == hi with hiStrict)")
        if r["origin"] == "precedent" and r.get("campaignId") not in campaigns:
            errs.append(f"{at}: campaignId {r.get('campaignId')!r} is not in data/campaigns/")
    if verbose and not errs:
        for oid, obj in sorted(by_id.items()):
            rules = {r["dimension"]: r for r in doc["rules"] if r["objectiveId"] == oid}
            parts = []
            for d in obj["requiredDimensions"]:
                r = rules.get(d)
                parts.append(f"{d}=" + ("no rule" if r is None else "no band" if r["band"] is None else f"{r.get('priority', 'must')} band"))
            unknown = [d for d in obj["requiredDimensions"] if d not in rules or rules[d]["band"] is None]
            print(f"     trait map {oid}: {', '.join(parts)}; unknown for {unknown or 'none'}")
    return errs


# ---------- 2. plan request ----------

def _valid_r4(cell: str) -> bool:
    try:
        return h3.is_valid_cell(cell) and h3.get_resolution(cell) == 4
    except Exception:  # noqa: BLE001 - any parse failure means not a valid cell
        return False


def check_plan_request(v, doc, objectives: dict) -> list[str]:
    errs = _schema_errors(v, doc)
    if errs:
        return errs
    obj = objectives.get((doc["objectiveId"], doc["body"]))
    if obj is None:
        return [f"objective {doc['objectiveId']} has no row for body {doc['body']}"]
    required = set(obj["requiredDimensions"])
    overlap = set(doc.get("must", [])) & set(doc.get("nice", []))
    if overlap:
        errs.append(f"must and nice overlap: {sorted(overlap)}")
    for field in ("must", "nice"):
        extra = set(doc.get(field, [])) - required
        if extra:
            errs.append(f"{field}: {sorted(extra)} not required by {doc['objectiveId']}")
    if "sortBy" in doc and doc["sortBy"] not in required:
        errs.append(f"sortBy {doc['sortBy']} is not required by {doc['objectiveId']}")
    for cell in doc.get("pins", []):
        if not _valid_r4(cell):
            errs.append(f"pin {cell} is not a valid H3 resolution-4 cell")
    seen = set()
    for e in doc.get("bandEdits", []):
        if e["lo"] > e["hi"]:
            errs.append(f"bandEdits {e['dimension']}: lo > hi")
        if e["dimension"] in seen:
            errs.append(f"bandEdits {e['dimension']}: edited twice")
        seen.add(e["dimension"])
    return errs


# ---------- 3. site plan ----------

def _forbidden_keys(node, path="") -> list[str]:
    out = []
    if isinstance(node, dict):
        for k, val in node.items():
            if FORBIDDEN_KEY.search(k):
                out.append(f"{path}/{k}: key looks like a score/rating/total/weight (AGENTS.md rule 4)")
            out += _forbidden_keys(val, f"{path}/{k}")
    elif isinstance(node, list):
        for i, val in enumerate(node):
            out += _forbidden_keys(val, f"{path}/{i}")
    return out


def _expected(value, band, hi_strict):
    """(verdict, gap, side) the frozen-to-be S7 rule gives for one value."""
    if value is None or band is None:
        return "unknown", None, None
    lo, hi = band["lo"], band["hi"]
    if value < lo:
        return "miss", lo - value, "below"
    if value > hi or (hi_strict and value == hi):
        return "miss", value - hi, "above"
    return "match", None, None


def _check_one(at, got, value, band, hi_strict) -> list[str]:
    verdict, gap, side = _expected(value, band, hi_strict)
    errs = []
    if got["verdict"] != verdict:
        errs.append(f"{at}: verdict {got['verdict']} but value {value} and band {band} give {verdict}")
    elif verdict == "miss":
        if side != got.get("side"):
            errs.append(f"{at}: side {got.get('side')} but the value is {side} the band")
        # An excluded strict boundary has exactly zero geometric distance.
        if abs(got["gap"] - gap) > TOL * max(1.0, abs(gap)):
            errs.append(f"{at}: gap {got['gap']} but the distance outside the band is {gap}")
    return errs


def check_site_plan(v, vreq, doc, objectives: dict, trait_map: dict, campaigns: set[str]) -> list[str]:
    errs = _schema_errors(v, doc)
    errs += _forbidden_keys(doc)
    if errs:
        return errs
    req = doc["request"]
    errs += [f"request: {m}" for m in check_plan_request(vreq, req, objectives)]
    if (doc["objective"]["objectiveId"], doc["objective"]["body"]) != (req["objectiveId"], req["body"]):
        errs.append("objective differs from the request's objective/body")
    obj = objectives.get((req["objectiveId"], req["body"]))
    if obj is None:
        return errs
    site = doc["site"]
    if not _valid_r4(site["h3"]):
        errs.append(f"site.h3 {site['h3']} is not a valid H3 resolution-4 cell")
    elif h3.latlng_to_cell(site["lat"], site["lon"], 4) != site["h3"]:
        errs.append("site lat/lon is not inside site.h3")

    required = obj["requiredDimensions"]
    rows = {}
    for r in doc["verdicts"]:
        if r["dimension"] in rows:
            errs.append(f"verdicts: {r['dimension']} appears twice")
        rows[r["dimension"]] = r
    missing = [d for d in required if d not in rows]
    extra = [d for d in rows if d not in required]
    if missing:
        errs.append(f"verdicts: required traits missing: {missing}")
    if extra:
        errs.append(f"verdicts: traits not required by the objective: {extra}")

    rules = {r["dimension"]: r for r in trait_map["rules"] if r["objectiveId"] == req["objectiveId"]}
    edits = {e["dimension"]: e for e in req.get("bandEdits", [])}
    window = _months(req["months"])
    for d, r in rows.items():
        at = f"verdicts/{d}"
        rule = rules.get(d)
        if d in edits:
            e = edits[d]
            band, hi_strict, origin = {"lo": e["lo"], "hi": e["hi"]}, bool(e.get("hiStrict")), "user"
        elif rule is not None:
            band, hi_strict, origin = rule["band"], bool(rule.get("hiStrict")), rule["origin"]
        else:
            band, hi_strict, origin = None, False, r["origin"]
        if rule is not None and (r["table"], r["earthColumn"]) != (rule["table"], rule["earthColumn"]):
            errs.append(f"{at}: column {r['table']}.{r['earthColumn']} differs from the trait map's {rule['table']}.{rule['earthColumn']}")
        if rule is not None and r.get("unit") != rule.get("unit"):
            errs.append(f"{at}: unit {r.get('unit')!r} differs from the trait map's {rule.get('unit')!r}")
        got_band = None if r["band"] is None else {"lo": r["band"]["lo"], "hi": r["band"]["hi"]}
        if got_band != band or bool((r["band"] or {}).get("hiStrict")) != (hi_strict and band is not None):
            errs.append(f"{at}: band {r['band']} differs from the trait map / request band {band} (hiStrict {hi_strict})")
        if r["origin"] != origin:
            errs.append(f"{at}: origin {r['origin']} but expected {origin}")
        priority = "must" if d in req.get("must", []) else "nice" if d in req.get("nice", []) else (rule or {}).get("priority", "must")
        if r["priority"] != priority:
            errs.append(f"{at}: priority {r['priority']} but the trait map and request give {priority}")
        if r["table"] == "L1m":
            months = [m["month"] for m in r["perMonth"]]
            if sorted(months) != sorted(window) or len(set(months)) != len(months):
                errs.append(f"{at}: perMonth covers {months}, the request asks for {window}")
            for m in r["perMonth"]:
                errs += _check_one(f"{at}/month {m['month']}", m, m["value"], band, hi_strict)
            verdicts = [m["verdict"] for m in r["perMonth"]]
            window_verdict = "miss" if "miss" in verdicts else "unknown" if "unknown" in verdicts else "match"
            if r["verdict"] != window_verdict:
                errs.append(f"{at}: window verdict {r['verdict']} but the months give {window_verdict}")
            elif window_verdict == "miss":
                worst = max((m for m in r["perMonth"] if m["verdict"] == "miss"), key=lambda m: m["gap"])
                if abs(r["gap"] - worst["gap"]) > TOL * max(1.0, worst["gap"]) or r["side"] != worst["side"]:
                    errs.append(f"{at}: window gap/side must be the largest monthly gap ({worst['gap']} {worst['side']})")
        else:
            errs += _check_one(at, r, r["value"], band, hi_strict)

    must = [r for r in rows.values() if r["priority"] == "must"]
    cls = "someMiss" if any(r["verdict"] == "miss" for r in must) else "noMissSomeUnknown" if any(r["verdict"] == "unknown" for r in must) else "allMatch"
    if doc["funnelClass"] != cls:
        errs.append(f"funnelClass {doc['funnelClass']} but the must rows give {cls}")

    req_limits = req.get("limits", {})
    seen_limits: set[str] = set()
    for lim in doc.get("limits", []):
        name = lim["limit"]
        if name in seen_limits:
            errs.append(f"limits/{name}: appears twice")
        seen_limits.add(name)
        if name in req_limits and lim["max"] != req_limits[name]:
            errs.append(f"limits/{name}: max {lim['max']} differs from request limit {req_limits[name]}")
        want = "unknown" if lim["value"] is None else "pass" if lim["value"] <= lim["max"] else "fail"
        if lim["outcome"] != want:
            errs.append(f"limits/{name}: outcome {lim['outcome']} but value {lim['value']} vs max {lim['max']} gives {want}")
    asked = set(req_limits)
    if asked != seen_limits:
        errs.append(f"limits: request asks for {sorted(asked)}, plan reports {sorted(seen_limits)}")
    if doc.get("paretoLayer") is not None and (cls == "someMiss" or any(l["outcome"] == "fail" for l in doc.get("limits", []))):
        errs.append("paretoLayer set for a site a must miss or a failed limit filters out")

    want_nte = sorted((n["mismatch"], n["why"]) for n in obj["notTestableOnEarth"])
    if sorted((n["mismatch"], n["why"]) for n in doc["notTestableOnEarth"]) != want_nte:
        errs.append("notTestableOnEarth differs from the objective row in data/objectives/")

    season = doc.get("season")
    if season:
        months = [m["month"] for m in season["months"]]
        if sorted(months) != list(range(1, 13)):
            errs.append(f"season.months must hold months 1-12 once each, got {months}")
        want = sorted(m["month"] for m in season["months"] if m["mustTraitsMatch"] is True and m["reachable"] is True)
        if sorted(season["fieldSeasonMonths"]) != want:
            errs.append(f"season.fieldSeasonMonths {season['fieldSeasonMonths']} but the strip gives {want}")
        static_must = [r for r in must if r["table"] != "L1m"]
        static_miss = any(r["verdict"] == "miss" for r in static_must)
        static_unknown = any(r["verdict"] == "unknown" for r in static_must)
        window_set = set(window)
        for m in season["months"]:
            mo = m["month"]
            got_mtm = m["mustTraitsMatch"]
            if mo in window_set:
                m_verdicts = [
                    r["verdict"] if r["table"] != "L1m"
                    else next((pm["verdict"] for pm in r["perMonth"] if pm["month"] == mo), "unknown")
                    for r in must
                ]
                want_mtm = False if "miss" in m_verdicts else None if "unknown" in m_verdicts else True
                if got_mtm is not want_mtm:
                    errs.append(f"season.months/{mo}: mustTraitsMatch is {got_mtm} but must verdicts give {want_mtm}")
            else:
                if static_miss and got_mtm is not False:
                    errs.append(f"season.months/{mo}: mustTraitsMatch is {got_mtm} but a static must trait misses")
                elif static_unknown and got_mtm is True:
                    errs.append(f"season.months/{mo}: mustTraitsMatch is True but a static must trait is unknown")

    split = (doc.get("logistics") or {}).get("testSplit")
    if split:
        for key, verdict in (("matchesHere", "match"), ("missesHere", "miss"), ("unknownHere", "unknown")):
            want = sorted(d for d, r in rows.items() if r["verdict"] == verdict)
            if sorted(split[key]) != want:
                errs.append(f"logistics.testSplit.{key} {split[key]} but the verdicts give {want}")
        if sorted(split["cannotTestOnEarth"]) != sorted(n["mismatch"] for n in obj["notTestableOnEarth"]):
            errs.append("logistics.testSplit.cannotTestOnEarth differs from notTestableOnEarth")

    for row in (doc.get("risks") or {}).get("rows", []):
        if row["kind"] != "eonet" and ("eventsRecorded" in row or "events" in row):
            errs.append(f"risks/{row['hazard']}: events belong to EONET rows only")
        if row["kind"] == "eonet":
            if row["hazard"] not in EONET_CATEGORIES:
                errs.append(f"risks/{row['hazard']}: not an EONET category")
            n, events = row.get("eventsRecorded"), row.get("events", [])
            if n is not None and len(events) > n:
                errs.append(f"risks/{row['hazard']}: {len(events)} events listed but eventsRecorded is {n}")

    for p in doc.get("precedents", []):
        at = f"precedents/{p['campaignId']}"
        if p["campaignId"] not in campaigns:
            errs.append(f"{at}: not a campaign in data/campaigns/")
        if p["closeness"] is None:
            if p["shapley"]:
                errs.append(f"{at}: Shapley shares given without a closeness")
            if not p.get("missingTraits"):
                errs.append(f"{at}: closeness is null but missingTraits does not say which trait is missing")
            continue
        dims = [s["dimension"] for s in p["shapley"]]
        if sorted(dims) != sorted(p["traitSet"]) or len(set(dims)) != len(dims):
            errs.append(f"{at}: Shapley dimensions {dims} must be the trait set {p['traitSet']}, once each")
        total = sum(s["share"] for s in p["shapley"])
        if abs(total - p["closeness"]) > TOL * max(1.0, abs(p["closeness"])):
            errs.append(f"{at}: Shapley shares add up to {total}, closeness is {p['closeness']}")
        if p.get("missingTraits"):
            errs.append(f"{at}: ranked with a closeness while missingTraits is not empty")
    return errs


# ---------- runner + self-test ----------

def _load_all():
    vals = _validators()
    trait_map = yaml.safe_load((ROOT / TRAIT_MAP).read_text(encoding="utf-8"))
    req = json.loads((ROOT / PLAN_REQUEST_FIXTURE).read_text(encoding="utf-8"))
    plan = json.loads((ROOT / SITE_PLAN_FIXTURE).read_text(encoding="utf-8"))
    return vals, trait_map, req, plan


def run(objectives: dict) -> list[str]:
    vals, trait_map, req, plan = _load_all()
    campaigns = _campaign_ids()
    errs = []
    e = check_trait_map(vals["trait-map.schema.json"], trait_map, objectives, campaigns)
    print(f"{'OK  ' if not e else 'FAIL'} trait map {TRAIT_MAP} ({len(trait_map.get('rules', []))} rules)")
    errs += [f"{TRAIT_MAP}: {m}" for m in e]
    e = check_plan_request(vals["plan-request.schema.json"], req, objectives)
    print(f"{'OK  ' if not e else 'FAIL'} plan request {PLAN_REQUEST_FIXTURE}")
    errs += [f"{PLAN_REQUEST_FIXTURE}: {m}" for m in e]
    e = check_site_plan(vals["site-plan.schema.json"], vals["plan-request.schema.json"], plan, objectives, trait_map, campaigns)
    print(f"{'OK  ' if not e else 'FAIL'} site plan {SITE_PLAN_FIXTURE} (funnel {plan.get('funnelClass')}, SYNTHETIC)")
    errs += [f"{SITE_PLAN_FIXTURE}: {m}" for m in e]
    return errs


def self_test(objectives: dict) -> list[str]:
    vals, tm, req, plan = _load_all()
    campaigns = _campaign_ids()
    vt, vr, vs = vals["trait-map.schema.json"], vals["plan-request.schema.json"], vals["site-plan.schema.json"]
    cases = []

    def tmc(name, f):
        c = copy.deepcopy(tm); f(c); cases.append((f"trait map: {name}", lambda c=c: check_trait_map(vt, c, objectives, campaigns, verbose=False)))

    def rqc(name, f):
        c = copy.deepcopy(req); f(c); cases.append((f"plan request: {name}", lambda c=c: check_plan_request(vr, c, objectives)))

    def spc(name, f):
        c = copy.deepcopy(plan); f(c); cases.append((f"site plan: {name}", lambda c=c: check_site_plan(vs, vr, c, objectives, tm, campaigns)))

    def rule(c, oid, dim):
        return next(r for r in c["rules"] if r["objectiveId"] == oid and r["dimension"] == dim)

    def row(c, dim):
        return next(r for r in c["verdicts"] if r["dimension"] == dim)

    tmc("rule without basis", lambda c: rule(c, "OP-5LM", "terrain").pop("basis"))
    tmc("band lo above hi", lambda c: rule(c, "OP-5LM", "terrain").update(band={"lo": 9, "hi": 5}))
    tmc("earthColumn not in the spec", lambda c: rule(c, "OP-5LM", "terrain").update(earthColumn="slope_max_deg"))
    tmc("L1m column in an L1 rule", lambda c: rule(c, "OP-5LM", "terrain").update(earthColumn="lst_night_k"))
    tmc("two rules for one pair", lambda c: c["rules"].append(copy.deepcopy(rule(c, "OP-5LM", "terrain"))))
    tmc("precedent rule without campaignId", lambda c: rule(c, "OP-5LM", "terrain").update(origin="precedent"))
    tmc("objective not in data/objectives", lambda c: rule(c, "OP-5LM", "terrain").update(objectiveId="OP-99LM"))
    tmc("trait the objective does not require", lambda c: rule(c, "LI-5L", "terrain").update(dimension="waterIce"))
    tmc("band with no Earth column", lambda c: rule(c, "SE-3LM", "subsurface").update(band={"lo": 0, "hi": 1}))
    tmc("origin user stored in the file", lambda c: rule(c, "OP-5LM", "terrain").update(origin="user"))
    tmc("empty band (lo == hi, hiStrict)", lambda c: rule(c, "LI-5L", "terrain").update(band={"lo": 10, "hi": 10}))

    rqc("four pins", lambda c: c.update(pins=c["pins"] + list(h3.grid_ring(c["pins"][0], 1))[:2]))
    rqc("must and nice overlap", lambda c: c.update(nice=["terrain"]))
    rqc("pin at resolution 5", lambda c: c["pins"].__setitem__(0, h3.cell_to_children(c["pins"][0], 5)[0]))
    rqc("month 13", lambda c: c["months"].update(end=13))
    rqc("weights field", lambda c: c.update(weights={"terrain": 0.7}))
    rqc("objective for the wrong body", lambda c: c.update(body="moon"))

    spc("score field on the plan", lambda c: c.update(score=0.82))
    spc("score hidden in a verdict row", lambda c: row(c, "terrain").update(matchScore=0.4))
    spc("Shapley shares do not add up", lambda c: c["precedents"][0]["shapley"][0].update(share=0.5))
    spc("miss without a gap", lambda c: row(c, "terrain").pop("gap"))
    spc("wrong gap", lambda c: row(c, "terrain").update(gap=2.0))
    spc("match with value outside the band", lambda c: (row(c, "surfaceMaterial").update(value=30.0)))
    spc("unknown value counted as match", lambda c: row(c, "surfaceMaterial").update(value=None))
    spc("required trait row missing", lambda c: c["verdicts"].pop())
    spc("wrong funnel class", lambda c: c.update(funnelClass="allMatch"))
    spc("field season not from the strip", lambda c: c["season"].update(fieldSeasonMonths=[7]))
    spc("perMonth months differ from the request", lambda c: row(c, "thermal")["perMonth"].pop())
    spc("notTestableOnEarth differs from the objective", lambda c: c["notTestableOnEarth"].pop())
    spc("priority ignores the request's must", lambda c: row(c, "terrain").update(priority="nice"))
    spc("band differs from the trait map", lambda c: row(c, "terrain").update(band={"lo": 0, "hi": 8}))
    spc("precedent not in data/campaigns", lambda c: c["precedents"][0].update(campaignId="no-such-campaign"))
    spc("Pareto layer on a filtered site", lambda c: c.update(paretoLayer=1))
    spc("test split disagrees with verdicts", lambda c: c["logistics"]["testSplit"].update(matchesHere=["terrain", "surfaceMaterial"]))
    spc("limit outcome disagrees with its value", lambda c: c["limits"][0].update(outcome="fail"))
    spc("site lat/lon outside its hexagon", lambda c: c["site"].update(lat=10.0))
    spc("verdict unit differs from the trait map", lambda c: row(c, "terrain").update(unit="m"))
    spc("limit max differs from the request", lambda c: c["limits"][0].update(max=100))
    spc("season mustTraitsMatch ignores a must miss", lambda c: c["season"]["months"][0].update(mustTraitsMatch=True, reachable=False))

    errs = []
    for name, run_case in cases:
        found = run_case()
        print(f"{'OK  ' if found else 'FAIL'} self-test rejects: {name}" + (f"  [{found[0]}]" if found else ""))
        if not found:
            errs.append(f"self-test: broken copy was accepted: {name}")
    return errs
