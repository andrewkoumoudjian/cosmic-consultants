"""Runtime interpretation of frozen S7; tests are conformance, not a proof of code.

Physical values must be the published Float32 values. Requirements/bands remain
finite Python/JavaScript numbers. No epsilon or scalar analogy score is used.
"""
from __future__ import annotations
import copy
import math
import re
from .tables import Tables, reason_for
from .request import months_in_window
from .logistics import limits, logistics
from .risks import risks

DIMENSIONS = {'terrain','thermal','illumination','dustProcess','waterIce','surfaceMaterial','subsurface','operations'}

def verdict(value, band):
    if value is not None and not math.isfinite(value):
        raise ValueError('observation must be finite or null')
    if band is not None and (not all(type(band[k]) in (int,float) and math.isfinite(band[k]) for k in ('lo','hi')) or band['lo'] > band['hi']):
        raise ValueError('band must have finite ordered bounds')
    if band is None or value is None:
        return {'verdict':'unknown','reason':{'code':'no-band' if band is None else 'missing','text':'No accepted band.' if band is None else 'Observation is missing.'}}
    if value < band['lo']: return {'verdict':'miss','gap':band['lo']-value,'side':'below'}
    if value > band['hi'] or (band.get('hiStrict',False) and value == band['hi']):
        return {'verdict':'miss','gap':value-band['hi'],'side':'above'}
    return {'verdict':'match'}

def window_verdict(rows):
    missed = [r for r in rows if r['verdict']=='miss']
    if missed:
        worst = max(missed,key=lambda r:r['gap'])
        return {k:worst[k] for k in ('verdict','gap','side')}
    unknown = next((r for r in rows if r['verdict']=='unknown'),None)
    if unknown is not None:return {'verdict':'unknown','reason':unknown['reason']}
    if not rows:return {'verdict':'unknown','reason':{'code':'empty-window','text':'No months selected.'}}
    return {'verdict':'match'}

def requirements(l3, request):
    allowed={'version','body','objectiveId','category','presetCampaignId','missionType','months','durationDays','teamSize','limits','must','nice','bandEdits','sortBy','top','pins','successCriteria'}
    if set(request)-allowed or request.get('version')!=1 or request.get('missionType') not in ('robotic','crewed','instrument'):
        raise ValueError('Invalid plan request fields, version or mission type.')
    for k,v in request.get('limits',{}).items():
        if k not in ('access','airport','protected','slope') or not isinstance(v,(int,float)) or isinstance(v,bool) or not math.isfinite(v) or v<0 or v>{'protected':100,'slope':90}.get(k,math.inf):
            raise ValueError('Invalid operational limit.')
    if request.get('top') is not None and (type(request['top']) is not int or request['top']<1):raise ValueError('top must be a positive integer.')
    objective = next((o for o in l3['objectives'] if (o['objectiveId'],o['body'])==(request.get('objectiveId'),request.get('body'))),None)
    if objective is None:raise ValueError('Objective is unavailable for this body.')
    window=request.get('months',{})
    if any(type(window.get(k)) is not int or not 1<=window[k]<=12 for k in ('start','end')):raise ValueError('Months must be 1–12.')
    must, nice = request.get('must',[]),request.get('nice',[])
    if len(must)!=len(set(must)) or len(nice)!=len(set(nice)) or set(must)&set(nice):raise ValueError('Duplicate or overlapping priorities.')
    if not set(must+nice).issubset(objective['requiredDimensions']):raise ValueError('Priority names an unavailable objective trait.')
    if request.get('sortBy') is not None and request['sortBy'] not in objective['requiredDimensions']:raise ValueError('Sort trait is not in this objective.')
    for field in ('durationDays','teamSize'):
        if field in request and (type(request[field]) is not int or request[field]<1):raise ValueError('Trip days and team size must be positive integers.')
    pins=request.get('pins',[])
    if len(pins)>3 or len(pins)!=len(set(pins)):raise ValueError('Choose up to three different sites.')
    if any(not isinstance(h,str) or not re.fullmatch(r'84[0-9a-f]{13}',h) for h in pins):raise ValueError('Invalid pinned H3 identifier.')
    edits=request.get('bandEdits',[])
    if len({e['dimension'] for e in edits})!=len(edits) or any(e['dimension'] not in objective['requiredDimensions'] for e in edits):raise ValueError('Invalid band edit.')
    rules={r['dimension']:r for r in l3['trait-map']['rules'] if r['objectiveId']==request['objectiveId']}
    out=[]
    for d in objective['requiredDimensions']:
        source=rules.get(d,{'dimension':d,'table':None,'earthColumn':None,'unit':None,'band':None,'origin':'team'})
        r={k:copy.deepcopy(source.get(k)) for k in ('dimension','table','earthColumn','unit','band','origin')}
        r['priority']='must' if d in must else 'nice' if d in nice else source.get('priority','must')
        if r['band'] is not None and source.get('hiStrict'):r['band']['hiStrict']=True
        edit=next((e for e in edits if e['dimension']==d),None)
        if edit is not None:r['band']={k:edit[k] for k in ('lo','hi','hiStrict') if k in edit};r['origin']='user'
        verdict(None,r['band'])  # validate bands even when observations are missing
        criterion=next((c['text'] for c in request.get('successCriteria',[]) if c['dimension']==d),None)
        if criterion:r['successCriterion']=criterion
        out.append(r)
    return objective,out

def _rows(tables,request,h3,r):
    months=months_in_window(request['months'])
    def one(m):
        source=tables.monthly.get((h3,m)) if r['table']=='L1m' else tables.context.get(h3) if r['table']=='L2' else tables.cells.get(h3)
        value=None if source is None or r['earthColumn'] is None else source.get(r['earthColumn'])
        result={'value':value,**verdict(value,r['band'])}
        if result['verdict']=='unknown' and r['band'] is not None:
            result['reason']={'code':'missing-observation','text':reason_for(source,r['earthColumn'] or '',r['dimension'])}
        return result
    if r['table']=='L1m':
        rows=[{'month':m,**one(m)} for m in months]
        return {'value':None,'perMonth':rows,**window_verdict(rows)}
    return one(months[0])

def site_plan(tables,l3,request,h3,manifest_hash=None,synthetic=True):
    objective,rules=requirements(l3,request)
    if h3 not in tables.cells:raise ValueError('Site is outside the published land grid.')
    rows=[{**r,**_rows(tables,request,h3,r)} for r in rules]
    must=[r for r in rows if r['priority']=='must']
    cls='someMiss' if any(r['verdict']=='miss' for r in must) else 'noMissSomeUnknown' if any(r['verdict']=='unknown' for r in must) else 'allMatch'
    cell=tables.cells[h3]
    return {'version':1,'request':request,'site':{'h3':h3,'lat':cell['lat'],'lon':cell['lon']},
            'objective':{'objectiveId':objective['objectiveId'],'body':objective['body']},'verdicts':rows,'funnelClass':cls,
            'limits':limits(tables,h3,request),'notTestableOnEarth':objective['notTestableOnEarth'],
            'logistics':logistics(tables,h3,request),'risks':risks(tables,h3,request),
            'provenance':{'synthetic':synthetic,'engine':'planner workflow 0.2','buildManifestSha256':manifest_hash,'inputs':tables.inputs}}

def pareto_layers(vectors):
    """Exact layers with stable identity for ties; two varying axes use prefix maxima."""
    unique=sorted(set(vectors))
    if not unique:return []
    dims=[d for d in range(len(unique[0])) if any(v[d]!=unique[0][d] for v in unique)]
    levels={}
    if len(dims)==0:levels={v:1 for v in unique}
    elif len(dims)==1:levels={v:i+1 for i,v in enumerate(unique)}
    elif len(dims)==2:
        d=dims[1];ys=sorted({v[d] for v in unique});ranks={y:i+1 for i,y in enumerate(ys)};tree=[0]*(len(ys)+1)
        for v in unique:
            y=ranks[v[d]];j=y;best=0
            while j>0:best=max(best,tree[j]);j-=j&-j
            levels[v]=best+1;j=y
            while j<len(tree):tree[j]=max(tree[j],best+1);j+=j&-j
    else:
        for v in unique:
            levels[v]=1+max((depth for w,depth in levels.items() if all(a<=b for a,b in zip(w,v)) and w!=v),default=0)
    return [levels[v] for v in vectors]

def search(tables,l3,request,manifest_hash=None,synthetic=True):
    _,rules=requirements(l3,request)
    counts={'land':len(tables.cells),'withinLimits':0,'matches':0,'misses':0,'unknown':0}
    matches=[];comparable=[];vectors=[]
    for h in tables.order():
        if any(l['outcome']=='fail' for l in limits(tables,h,request)):continue
        counts['withinLimits']+=1
        rs=[{**r,**_rows(tables,request,h,r)} for r in rules]
        must=[r for r in rs if r['priority']=='must']
        if any(r['verdict']=='miss' for r in must):counts['misses']+=1;continue
        if any(r['verdict']=='unknown' for r in must):counts['unknown']+=1;continue
        counts['matches']+=1
        vector=tuple(r.get('gap',0) for r in rs)
        sort_gap=next((r.get('gap',0) if r['verdict']!='unknown' else math.inf for r in rs if r['dimension']==request.get('sortBy')),0)
        matches.append((h,sort_gap))
        if all(r['verdict']!='unknown' for r in rs):comparable.append(h);vectors.append(vector)
    layers=dict(zip(comparable,pareto_layers(vectors)))
    matches.sort(key=lambda item:(layers.get(item[0],math.inf),item[1],item[0]))
    top=request.get('top');chosen=matches if top is None else matches[:top]
    sites=[]
    for h,_ in chosen:
        p=site_plan(tables,l3,request,h,manifest_hash,synthetic)
        p['paretoLayer']=layers.get(h)
        sites.append(p)
    return {'counts':counts,'sites':sites}

def brief(plan):
    lines=['# Mission plan brief',f"{plan['objective']['body'].title()} / {plan['objective']['objectiveId']}",
           'SYNTHETIC example' if plan['provenance']['synthetic'] else 'Real source data; scientific status: partial',
           f"Site: {plan['site']['h3']} ({plan['site']['lat']}, {plan['site']['lon']})",
           f"Months: {plan['request']['months']['start']}–{plan['request']['months']['end']}",'','| Requirement | Priority | Result | Gap / reason |','|---|---|---|---|']
    for r in plan['verdicts']:
        detail=r.get('reason',{}).get('text',str(r.get('gap',''))+' '+str(r.get('unit') or ''))
        lines.append(f"| {r['dimension']} | {r['priority']} | {r['verdict']} | {detail} |")
    lines+=['','Earth cannot reproduce:']+[f"- {m['mismatch']}: {m['why']}" for m in plan['notTestableOnEarth']]
    lines+=['','Logistics:']+['- '+n for n in plan.get('logistics',{}).get('notes',[])]
    lines+=['','Past-campaign closeness: not checked (S8 pending).','Permits, equipment, budget and approvals: not checked.','',plan.get('risks',{}).get('eonetDisclaimer',''),'','Sources:']
    lines += [f"- {i['path']} — sha256 {i['sha256']}" for i in plan['provenance']['inputs']]
    return '\n'.join(lines)+'\n'
