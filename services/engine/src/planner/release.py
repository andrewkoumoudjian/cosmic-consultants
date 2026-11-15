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
    tables=from_assembled(assembled,repo/'data/pipeline/columns.yaml')
    l3=load_l3(repo)
    config_files=[*sorted((repo/'data/objectives').glob('*.yaml')),*sorted((repo/'data/campaigns').glob('*.yaml')),
                  repo/'data/requirements/trait-map.yaml',repo/'data/pipeline/test-categories.yaml',repo/'data/pipeline/evidence.yaml',repo/'data/pipeline/columns.yaml']
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
             'events':tables.events,'categories':yaml.safe_load(config_files[-3].read_text())['categories'],
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
    manifest.pop('sha256',None)
    for name,data in supplements.items():
        (out/name).write_bytes(data);manifest['files'][name]=hashlib.sha256(data).hexdigest()
    manifest['numericPolicy']='published-float32-no-epsilon'
    manifest['engine']='planner 0.2.0 workflow132'
    manifest['files']=dict(sorted(manifest['files'].items()))
    manifest['inputs'].extend({'path':str(p.relative_to(repo)),'sha256':sha256_file(p)} for p in [repo/'data/snapshots/MANIFEST.json',repo/'proofs/Analog/Funnel.lean',repo/'proofs/Analog/FunnelProofs.lean',repo/'services/engine/src/planner/workflow.py',repo/'services/engine/src/planner/assembled.py',repo/'services/engine/src/planner/release.py',repo/'apps/atlas/src/planner/engine.ts',repo/'contracts/site-plan.schema.json',repo/'contracts/planner-runtime.schema.json'])
    (out/'build-manifest.json').write_bytes(_json(manifest))
    return {'cells':len(order),'goldenCases':len(cases),'files':len(manifest['files']),'manifestSha256':sha256_file(out/'build-manifest.json')}

def main():
    p=argparse.ArgumentParser();p.add_argument('assembled',type=Path);p.add_argument('out',type=Path)
    p.add_argument('--repo',type=Path,default=Path(__file__).resolve().parents[4]);args=p.parse_args()
    print(json.dumps(release(args.assembled,args.out,args.repo),indent=2))
if __name__=='__main__':main()
