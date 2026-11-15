"""W15 (#23): run each cited campaign's own site through the request frozen in
data/calibration/campaign-expectations.yaml, then compare trait by trait.

No new verdict logic lives here. Verdicts come from `workflow.site_plan` and
`workflow.search` (frozen S7 semantics). This module only lines up "expected"
next to "observed". Disagreements are kept and reported, never dropped. The
expectations file is read only, never rewritten.

No site score (AGENTS.md rule 4): the only counts are how many trait
expectations held. That tallies our predictions, it does not rate a site.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from pathlib import Path
from time import perf_counter

from .workflow import search, site_plan

# Grid-wide checks need one request per objective. Months 1-12 and crewed are
# stated here, not hidden: for OP-5LM the only monthly traits have no band, so
# the month window cannot change a verdict.
GRID_REQUEST = {"version": 1, "missionType": "crewed", "months": {"start": 1, "end": 12}}
BODY = {"OP-5LM": "mars", "SE-3LM": "moon", "LI-5L": "moon"}


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build_request(campaign: dict, variant: dict) -> dict:
    req = {"version": 1, "presetCampaignId": campaign["campaignId"], **campaign["request"]}
    req.update(variant.get(req["objectiveId"], {}))
    return req


def compare_trait(dimension: str, expected: dict | None, row: dict) -> dict:
    out = {"dimension": dimension, "priority": row["priority"], "observed": row["verdict"]}
    if row["verdict"] == "miss":
        out["gap"] = row["gap"]
        out["side"] = row["side"]
    if row["verdict"] == "unknown":
        out["reason"] = row["reason"]["code"]
    if row.get("value") is not None:
        out["value"] = row["value"]
    if "perMonth" in row:
        out["perMonth"] = [{k: m[k] for k in ("month", "value", "verdict") if k in m} for m in row["perMonth"]]
    if expected is None:
        out.update(expected=None, agrees=None, note="no expectation was frozen for this trait")
        return out
    out["expected"] = expected["verdict"]
    out["confidence"] = expected.get("confidence")
    agrees = expected["verdict"] == row["verdict"]
    if agrees and "reason" in expected:
        agrees = out.get("reason") == expected["reason"]
    out["agrees"] = agrees
    return out


def run_campaign(tables, l3, exp: dict, campaign: dict, campaign_record: dict) -> dict:
    cid = campaign["campaignId"]
    if not campaign.get("run", False):
        return {"campaignId": cid, "run": False, "reason": campaign["reason"]}
    h3 = campaign_record["site"]["h3r4"]
    result = {"campaignId": cid, "run": True, "site": {"h3": h3, "name": campaign_record["site"]["name"]},
              "mappingBasis": campaign["mappingBasis"], "monthsBasis": campaign["monthsBasis"], "variants": {}}
    if h3 not in tables.cells:
        result["outcome"] = "site-outside-grid"
        return result
    for name, variant in exp["variants"].items():
        request = build_request(campaign, variant)
        plan = site_plan(tables, l3, request, h3, None, False)
        traits = [compare_trait(r["dimension"], campaign["expected"].get(r["dimension"]), r) for r in plan["verdicts"]]
        expected_funnel = campaign.get("expectedFunnel", {}).get(name)
        result["variants"][name] = {
            "request": request,
            "traits": traits,
            "funnel": {"expected": expected_funnel, "observed": plan["funnelClass"],
                       "agrees": None if expected_funnel is None else expected_funnel == plan["funnelClass"]},
        }
    return result


def run_grid(tables, l3, exp: dict, item: dict) -> dict:
    oid = item["objectiveId"]
    request = {**GRID_REQUEST, "body": BODY[oid], "objectiveId": oid}
    request.update(exp["variants"][item["variant"]].get(oid, {}))
    res = search(tables, l3, request, None, False)
    observed = {"matches": res["counts"]["matches"],
                "paretoLayered": sum(1 for s in res["sites"] if s.get("paretoLayer") is not None)}
    checks = {}
    for key, want in item["expected"].items():
        if key == "matchesAtLeast":
            checks[key] = {"expected": want, "observed": observed["matches"], "agrees": observed["matches"] >= want}
        else:
            checks[key] = {"expected": want, "observed": observed[key], "agrees": observed[key] == want}
    return {"objectiveId": oid, "variant": item["variant"], "request": request, "counts": res["counts"], "checks": checks}


def tally(campaigns: list[dict], grid: list[dict]) -> dict:
    """How many frozen expectations held. Counts predictions, not site quality."""
    t = {"traitExpectations": 0, "traitAgree": 0, "funnelExpectations": 0, "funnelAgree": 0,
         "gridExpectations": 0, "gridAgree": 0, "campaignsRun": 0, "campaignsNotRun": 0}
    for c in campaigns:
        if not c["run"]:
            t["campaignsNotRun"] += 1
            continue
        t["campaignsRun"] += 1
        for v in c["variants"].values():
            for tr in v["traits"]:
                if tr["agrees"] is not None:
                    t["traitExpectations"] += 1
                    t["traitAgree"] += bool(tr["agrees"])
            if v["funnel"]["agrees"] is not None:
                t["funnelExpectations"] += 1
                t["funnelAgree"] += bool(v["funnel"]["agrees"])
    for g in grid:
        for ch in g["checks"].values():
            t["gridExpectations"] += 1
            t["gridAgree"] += bool(ch["agrees"])
    return t


def run(tables, l3, expectations_path: Path, campaigns_dir: Path) -> dict:
    import yaml
    exp = yaml.safe_load(expectations_path.read_text())
    if exp.get("status") != "frozen":
        raise ValueError("Expectations must be frozen before a calibration run.")
    campaigns = []
    for c in exp["campaigns"]:
        record = yaml.safe_load((campaigns_dir / f"{c['campaignId']}.yaml").read_text())
        campaigns.append(run_campaign(tables, l3, exp, c, record))
    grid = [run_grid(tables, l3, exp, g) for g in exp.get("grid", [])]
    return {"version": 1, "issue": 23, "expectationsSha256": _sha(expectations_path),
            "campaigns": campaigns, "grid": grid, "tally": tally(campaigns, grid),
            "inputs": list(tables.inputs)}


def _fmt(tr: dict) -> str:
    if tr["observed"] == "miss":
        return f"miss (gap {tr['gap']:.3g} {tr['side']})"
    if tr["observed"] == "unknown":
        return f"unknown ({tr['reason']})"
    return "match"


def markdown(result: dict) -> str:
    lines = ["# W15 calibration results (#23)", "",
             f"Expectations sha256 `{result['expectationsSha256']}`, frozen at commit "
             f"`{result.get('expectationsCommit', 'unrecorded')}` before this run.", ""]
    t = result["tally"]
    lines += [f"Trait expectations held: {t['traitAgree']} of {t['traitExpectations']}. "
              f"Funnel expectations held: {t['funnelAgree']} of {t['funnelExpectations']}. "
              f"Grid expectations held: {t['gridAgree']} of {t['gridExpectations']}. "
              f"Campaigns run: {t['campaignsRun']}; not run: {t['campaignsNotRun']}.", "",
              "This counts our predictions. It is not a site score.", ""]
    lines += ["| Campaign | Variant | Trait | Priority | Expected | Observed | Value | Holds? |", "|---|---|---|---|---|---|---|---|"]
    for c in result["campaigns"]:
        if not c["run"]:
            continue
        if c.get("outcome"):
            lines.append(f"| {c['campaignId']} | — | — | — | — | {c['outcome']} | — | — |")
            continue
        for vname, v in c["variants"].items():
            for tr in v["traits"]:
                value = "" if tr.get("value") is None else f"{tr['value']:.4g}"
                holds = "—" if tr["agrees"] is None else ("yes" if tr["agrees"] else "**no**")
                lines.append(f"| {c['campaignId']} | {vname} | {tr['dimension']} | {tr['priority']} | "
                             f"{tr['expected']} | {_fmt(tr)} | {value} | {holds} |")
            f = v["funnel"]
            lines.append(f"| {c['campaignId']} | {vname} | *funnel* | — | {f['expected']} | {f['observed']} | | "
                         f"{'yes' if f['agrees'] else '**no**'} |")
    lines += ["", "## Grid-wide", "", "| Objective | Variant | Check | Expected | Observed | Holds? |", "|---|---|---|---|---|---|"]
    for g in result["grid"]:
        for key, ch in g["checks"].items():
            lines.append(f"| {g['objectiveId']} | {g['variant']} | {key} | {ch['expected']} | {ch['observed']} | "
                         f"{'yes' if ch['agrees'] else '**no**'} |")
    lines += ["", "## Not run", ""]
    lines += [f"- {c['campaignId']}: {c['reason']}" for c in result["campaigns"] if not c["run"]]
    lines += ["", "## Inputs", ""] + [f"- `{i['path']}` sha256 `{i['sha256']}`" for i in result["inputs"]]
    return "\n".join(lines) + "\n"


def main(argv=None):
    from .assembled import from_assembled
    from .publish import load_l3
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("assembled", type=Path)
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--repo", type=Path, default=Path(__file__).resolve().parents[4])
    a = p.parse_args(argv)
    start = perf_counter()
    exp_path = a.repo / "data/calibration/campaign-expectations.yaml"
    tables = from_assembled(a.assembled, a.repo / "data/pipeline/columns.yaml")
    result = run(tables, load_l3(a.repo), exp_path, a.repo / "data/campaigns")
    commit = subprocess.run(["git", "-C", str(a.repo), "log", "-1", "--format=%H", "--", str(exp_path)],
                            capture_output=True, text=True).stdout.strip()
    result["expectationsCommit"] = commit or None
    report = a.assembled / "assembly-report.json"
    result["inputs"].append({"path": "assembly-report.json (as read)", "sha256": _sha(report)})
    a.out.mkdir(parents=True, exist_ok=True)
    (a.out / "calibration-results.json").write_text(json.dumps(result, indent=2, allow_nan=False) + "\n")
    (a.out / "CALIBRATION-RESULTS.md").write_text(markdown(result))
    print(json.dumps({"tally": result["tally"], "seconds": round(perf_counter() - start, 2), "out": str(a.out)}, indent=2))


if __name__ == "__main__":
    main()
