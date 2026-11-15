"""Run a real request against the verified assembly and write JSON/Markdown."""
import argparse
import json
from pathlib import Path
from time import perf_counter
from .assembled import from_assembled
from .publish import load_l3
from .request import parse_query
from .tables import sha256_file
from .workflow import brief, search, site_plan

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('assembled',type=Path)
    parser.add_argument('--query',required=True,help='plan-request URL query, without a URL prefix')
    parser.add_argument('--site',help='inspect one H3 cell, including a miss/unknown')
    parser.add_argument('--out',type=Path,required=True)
    parser.add_argument('--repo',type=Path,default=Path(__file__).resolve().parents[4])
    args=parser.parse_args();start=perf_counter()
    request=parse_query(args.query)
    # An explicit top controls materialized plans; omitted means all, as the contract says.
    tables=from_assembled(args.assembled,args.repo/'data/pipeline/columns.yaml');l3=load_l3(args.repo)
    h=sha256_file(args.assembled/'assembly-report.json')
    if args.site:result={'sites':[site_plan(tables,l3,request,args.site,None,False)]}
    else:result=search(tables,l3,request,None,False)
    for plan in result['sites']:
        plan['provenance']['inputs'].append({'path':'assembly-report.json','sha256':h})
    args.out.mkdir(parents=True,exist_ok=True)
    (args.out/'result.json').write_text(json.dumps(result,indent=2,allow_nan=False)+'\n')
    (args.out/'mission-plan.md').write_text('\n\n'.join(brief(p) for p in result['sites']))
    print(json.dumps({'counts':result.get('counts'),'plans':len(result['sites']),'seconds':round(perf_counter()-start,2),'output':str(args.out)},indent=2))
if __name__=='__main__':main()
