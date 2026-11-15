"""Publish a verified assembly for the static planner, with source lineage.

Run: PYTHONPATH=services/engine/src services/engine/.venv/bin/python -m planner.release ASSEMBLED OUT
"""
import argparse
import hashlib
import json
from pathlib import Path
import yaml
from .assembled import from_assembled
from .publish import load_l3, publish, _json
from .tables import sha256_file, reasons_of


def release(assembled,out,repo):
    from jsonschema import Draft202012Validator
    scenario_path=repo/'data/pipeline/release-scenarios.yaml'
    schema_path=repo/'contracts/release-scenarios.schema.json'
    scenarios=yaml.safe_load(scenario_path.read_text())
    Draft202012Validator(json.loads(schema_path.read_text())).validate(scenarios)
    tables=from_assembled(assembled,repo/'data/pipeline/columns.yaml')
    l3=load_l3(repo)
    config_files=[*sorted((repo/'data/objectives').glob('*.yaml')),*sorted((repo/'data/campaigns').glob('*.yaml')),
                  repo/'data/requirements/trait-map.yaml',repo/'data/pipeline/test-categories.yaml',repo/'data/pipeline/evidence.yaml',repo/'data/pipeline/columns.yaml']
    config_files.extend([scenario_path,schema_path])
    configs=[{'path':str(p.relative_to(repo)),'sha256':sha256_file(p)} for p in config_files]
    manifest=publish(tables,l3,out,configs)
    report=json.loads((assembled/'assembly-report.json').read_text())
    order=tables.order()
    reason_sets=[{}]; reason_ids={'{}':0}
    def reason_id(row):
        reason=reasons_of(row);key=json.dumps(reason,sort_keys=True)
        if key not in reason_ids:reason_ids[key]=len(reason_sets);reason_sets.append(reason)
        return reason_ids[key]
    yearly_reasons=[reason_id(tables.cells[h]) for h in order]
    monthly_reasons=[reason_id(tables.monthly[(h,m)]) for h in order for m in range(1,13)]
    runtime={'version':1,'numericPolicy':'published-float32-no-epsilon',
             'qualityWarnings':['Scientific acceptance is partial. Requirements and comparisons are conditional on the stated sources, scales and bands.',*report.get('sourceQuality',{}).get('warnings',[])],
             'yearlyReasons':yearly_reasons,'reasonSets':reason_sets,
             'monthlyReasons':monthly_reasons,
             'events':tables.events,'categories':yaml.safe_load((repo/'data/pipeline/test-categories.yaml').read_text())['categories'],
             'campaigns':l3['campaigns'],'sourceManifest':'source-manifest.json'}
    supplements={'planner-runtime.json':_json(runtime),'source-manifest.json':(repo/'data/snapshots/MANIFEST.json').read_bytes(),
                 'column-evidence.json':_json(yaml.safe_load((repo/'data/pipeline/evidence.yaml').read_text())),
                 'assembly-report.json':(assembled/'assembly-report.json').read_bytes()}
    # Store the inputs' own builder metadata for a trace from assembled measurements to raw snapshots.
    input_meta={}
    for name,meta in report['inputs'].items():
        p=assembled.parent/(Path(meta['path']).stem+'.meta.json')
        if p.exists():input_meta[name]=json.loads(p.read_text())
    supplements['source-lineage.json']=_json(input_meta)
    # Golden cases compare the Python reference with the browser on published numbers.
    from .workflow import site_plan
    sample=sorted(set([order[0],order[len(order)//2],order[-1],*list(order[::max(1,len(order)//50)])]))
    cases=[]
    for objective in l3['objectives']:
        for window in ({'start':1,'end':1},{'start':6,'end':8},{'start':11,'end':2}):
            req={'version':1,'body':objective['body'],'objectiveId':objective['objectiveId'],'missionType':'robotic','months':window}
            for h in sample:
                plan=site_plan(tables,l3,req,h,synthetic=False)
                cases.append({'request':req,'h3':h,'verdicts':plan['verdicts'],'funnelClass':plan['funnelClass'],'limits':plan['limits']})
    supplements['golden-verdicts.json']=_json(cases)

    # Expose #168 planetary/earth-feature metadata and #172 S9/S10 Pareto + CVaR outputs when present.
    extra_inputs=[]
    campaign_errors=[]
    for copy_name in ('data-coverage.json','earth-feature-scales.json','planetary-targets.meta.json'):
        p=assembled/copy_name
        if p.exists():
            supplements[copy_name]=_json(json.loads(p.read_text()))
    targets_pq=assembled/'planetary-targets.parquet'
    ef_pq=assembled/'earth-features-r4.parquet'
    if targets_pq.exists() and ef_pq.exists():
        import math as _math
        from .pareto_model import load_assembled_targets,rank_earth_for_target,select_diverse_frontier_candidates
        from .optimizer import build_campaign_problem_from_years,solve_cvar_campaign
        def _clean(v):
            if isinstance(v,float) and not _math.isfinite(v):return None
            if isinstance(v,dict):return {k:_clean(x) for k,x in v.items()}
            if isinstance(v,list):return [_clean(x) for x in v]
            return v
        raw_targets=load_assembled_targets(assembled)
        supplements['planetary-targets.json']=_json(_clean(raw_targets))
        extra_inputs.extend([
            {'path':'data/snapshots/_derived/assembled/planetary-targets.parquet','sha256':sha256_file(targets_pq)},
            {'path':'data/snapshots/_derived/assembled/earth-features-r4.parquet','sha256':sha256_file(ef_pq)},
        ])
        years_pq=assembled.parent/'cells-r4-monthly-years.parquet'
        avail_ids={t['target_id'] for t in raw_targets}
        pareto_bundle={'version':1,'scientificStatus':'partial','scenarioStatus':scenarios['status'],'targets':{}}
        for scenario in scenarios['scenarios']:
            tid=scenario['targetId']
            params={k:v['value'] for k,v in scenario['parameters'].items()}
            if tid not in avail_ids:
                continue
            ranked=rank_earth_for_target(assembled,tid,limits=params['limits'],min_land_pct=params['minLandPct'],max_layers=params['maxLayers'],
                                         passthrough_columns=('access_min_median','land_pct_mean','barren_pct','slope_mean_deg'))
            cands=select_diverse_frontier_candidates(ranked,max_candidates=params['maxCandidates'])
            entry={
                'targetId':tid,'body':ranked['body'],'axes':ranked['axes'],
                'scenarioStatus':scenarios['status'],'parameters':scenario['parameters'],
                'excludedLimits':ranked['excludedLimits'],
                'notTestableOnEarth':ranked['notTestableOnEarth'],'counts':ranked['counts'],
                'frontierSample':[{k:c[k] for k in ('h3','lat','lon','paretoLayer','gaps','observations') if k in c} for c in cands],
            }
            if years_pq.exists() and cands:
                try:
                    prob,excl=build_campaign_problem_from_years(
                        cands,years_pq,month=params['month'],thermal_band_k=tuple(params['thermalBandK']),expected_years=params['years'],
                        alpha=params['alpha'],max_weight_per_site=params['maxWeightPerSite'],coverage_rules=params['coverageRules'],
                    )
                    sol=solve_cvar_campaign(prob,use_screening=True)
                    entry['campaignPlan']={
                        'month':params['month'],'thermalBandK':params['thermalBandK'],'alpha':params['alpha'],
                        'status':'solved',
                        'cvar':sol.cvar,'varT':sol.var_t,'expectedCost':sol.expected_cost,
                        'weights':{k:v for k,v in sol.weights.items() if v>1e-9},
                        'screeningExact':sol.screening_exact,
                        'certified':sol.certificate.certified,
                        'certificationStatus':sol.certificate.certification_status,
                        'certifiedSuboptLe':sol.certificate.certified_subopt_le if sol.certificate.certified else None,
                        'numericalSuboptEstimate':sol.certificate.numerical_subopt_estimate,
                        'excludedCandidates':excl,
                    }
                except Exception as exc:  # noqa: BLE001 - record infeasibility cleanly without failing release
                    entry['campaignPlan']={'status':'error','error':str(exc)}
                    campaign_errors.append({'targetId':tid,'error':str(exc)})
            else:
                entry['campaignPlan']={'status':'not-run','missing_reason':'historical-years-unavailable' if not years_pq.exists() else 'no-frontier-candidates'}
            pareto_bundle['targets'][tid]=entry
        supplements['pareto-targets.json']=_json(_clean(pareto_bundle))
        if years_pq.exists():
            extra_inputs.append({'path':'data/snapshots/_derived/cells-r4-monthly-years.parquet','sha256':sha256_file(years_pq)})

    manifest.pop('sha256',None)
    for name,data in supplements.items():
        (out/name).write_bytes(data);manifest['files'][name]=hashlib.sha256(data).hexdigest()
    manifest['numericPolicy']='published-float32-no-epsilon'
    manifest['engine']='planner 0.2.0 workflow132'
    manifest['files']=dict(sorted(manifest['files'].items()))
    manifest['inputs'].extend(extra_inputs)
    manifest['inputs'].extend({'path':str(p.relative_to(repo)),'sha256':sha256_file(p)} for p in [repo/'data/snapshots/MANIFEST.json',repo/'proofs/Analog/Funnel.lean',repo/'proofs/Analog/FunnelProofs.lean',repo/'proofs/Analog/ParetoLayers.lean',repo/'proofs/Analog/CampaignOpt.lean',repo/'services/engine/src/planner/workflow.py',repo/'services/engine/src/planner/pareto_model.py',repo/'services/engine/src/planner/optimizer.py',repo/'services/engine/src/planner/assembled.py',repo/'services/engine/src/planner/release.py',repo/'apps/atlas/src/planner/engine.ts',repo/'contracts/site-plan.schema.json',repo/'contracts/planner-runtime.schema.json'])
    manifest['inputs']=sorted({i['path']:i for i in manifest['inputs']}.values(),key=lambda i:i['path'])
    (out/'build-manifest.json').write_bytes(_json(manifest))
    return {'cells':len(order),'goldenCases':len(cases),'files':len(manifest['files']),'campaignErrorCount':len(campaign_errors),'campaignErrors':campaign_errors,'manifestSha256':sha256_file(out/'build-manifest.json')}

def main():
    p=argparse.ArgumentParser();p.add_argument('assembled',type=Path);p.add_argument('out',type=Path)
    p.add_argument('--repo',type=Path,default=Path(__file__).resolve().parents[4]);args=p.parse_args()
    print(json.dumps(release(args.assembled,args.out,args.repo),indent=2))
if __name__=='__main__':main()
