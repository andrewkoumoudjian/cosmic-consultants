/** Tested runtime interpretation of frozen S7. Source physics is not certified. */
import type { PlanRequest, Dimension } from '../plan-url.ts';
export type Band = {lo:number;hi:number;hiStrict?:boolean};
export type Reason = {code:string;text:string};
export type Result = {verdict:'match'|'miss'|'unknown';gap?:number;side?:'below'|'above';reason?:Reason};
export type Rule = {dimension:Dimension;table:'L1'|'L1m'|'L2'|null;earthColumn:string|null;unit:string|null;band:Band|null;origin:string;priority?:'must'|'nice';hiStrict?:boolean;basis?:string;scaleCaveat?:string;successCriterion?:string};
export type Row = Rule & Result & {value:number|null;perMonth?:({month:number;value:number|null}&Result)[]};
export type Objective = {objectiveId:string;body:'moon'|'mars';title:string;requiredDimensions:Dimension[];earthTestableComponent:string;notTestableOnEarth:{mismatch:string;why:string}[]};
export type Runtime = {numericPolicy:string;qualityWarnings:string[];reasonSets:Record<string,string>[];yearlyReasons:number[];monthlyReasons:number[];categories:{categoryId:string;name:string;traits:Dimension[];detailedMetricMenuText:string[]}[];campaigns:Record<string,unknown>[];events:Record<string,Record<string,unknown>[]>};
export type Dataset = {h3:string[];yearly:Record<string,Float32Array>;monthly:Record<string,Float32Array>;objectives:Objective[];rules:Rule[];runtime:Runtime;manifestHash:string;inputs:{path:string;sha256:string}[]};
export function verdict(value:number|null,band:Band|null):Result {
 if(value!==null&&!Number.isFinite(value))throw Error('Observation must be finite or null.');
 if(band&&(!Number.isFinite(band.lo)||!Number.isFinite(band.hi)||band.lo>band.hi))throw Error('Band must have finite ordered bounds.');
 if(band===null||value===null)return {verdict:'unknown',reason:{code:band===null?'no-band':'missing',text:band===null?'No accepted band.':'Observation is missing.'}};
 if(value<band.lo)return {verdict:'miss',gap:band.lo-value,side:'below'};
 if(value>band.hi||(band.hiStrict&&value===band.hi))return {verdict:'miss',gap:value-band.hi,side:'above'};
 return {verdict:'match'};
}
export function windowVerdict(rows:Result[]):Result {
 const missed=rows.filter(r=>r.verdict==='miss');
 if(missed.length){const worst=missed.reduce((a,b)=>b.gap!>a.gap!?b:a);return {verdict:'miss',gap:worst.gap!,side:worst.side!};}
 const unknown=rows.find(r=>r.verdict==='unknown');
 if(unknown)return {verdict:'unknown',reason:unknown.reason!};
 return rows.length?{verdict:'match'}:{verdict:'unknown',reason:{code:'empty-window',text:'No months selected.'}};
}
export function months(request:PlanRequest):number[]{
 const {start,end}=request.months;
 if(!Number.isInteger(start)||!Number.isInteger(end)||start<1||end>12||end<1||start>12)throw Error('Months must be 1–12.');
 return Array.from({length:(end-start+12)%12+1},(_,i)=>(start-1+i)%12+1);
}
export function requirements(data:Dataset,request:PlanRequest):Rule[]{
 const objective=data.objectives.find(o=>o.objectiveId===request.objectiveId&&o.body===request.body);
 if(!objective)throw Error('Objective is unavailable for this body.');
 return objective.requiredDimensions.map(d=>{
  const source=data.rules.find(r=>(r as Rule&{objectiveId?:string}).objectiveId===request.objectiveId&&r.dimension===d);
  if(!source)throw Error(`No requirement record for ${d}.`);
  const edit=request.bandEdits?.find(e=>e.dimension===d);
  const band=edit?{lo:edit.lo,hi:edit.hi,...(edit.hiStrict?{hiStrict:true}:{})}:source.band?{...source.band,...(source.hiStrict?{hiStrict:true}:{})}:null;
  verdict(null,band);
  return {...source,band,origin:edit?'user':source.origin,priority:request.must?.includes(d)?'must':request.nice?.includes(d)?'nice':source.priority??'must'};
 });
}
export function value(data:Dataset,i:number,rule:Rule,m:number):number|null {
 if(!rule.earthColumn||!rule.table)return null;
 const array=rule.table==='L1m'?data.monthly[rule.earthColumn]:data.yearly[rule.earthColumn];
 const v=array?.[rule.table==='L1m'?i*12+m-1:i];
 if(v===undefined||Number.isNaN(v))return null;
 if(!Number.isFinite(v))throw Error('Nonfinite published observation.');
 return v;
}
/** A banded requirement Earth has no dataset for: not a per-site data gap (#166). */
export const NO_EARTH_COLUMN:Reason={code:'no-earth-column',text:'No Earth dataset for this trait.'};
function observed(data:Dataset,i:number,r:Rule,m:number){
 const v=value(data,i,r,m),result=verdict(v,r.band);
 if(result.verdict==='unknown'&&r.band&&(!r.earthColumn||!r.table)){
  result.reason=NO_EARTH_COLUMN;
 }else if(result.verdict==='unknown'&&r.band){
  const reasonIndex=r.table==='L1m'?data.runtime.monthlyReasons[i*12+m-1]:data.runtime.yearlyReasons[i];
  const reasons=data.runtime.reasonSets[reasonIndex??0]??{};
  const reason=reasons[r.earthColumn??'']??reasons[r.dimension]??'not-in-source';
  result.reason={code:'missing-observation',text:reason};
 }
 return {value:v,...result};
}
export function rows(data:Dataset,request:PlanRequest,i:number):Row[]{
 const ms=months(request);
 return requirements(data,request).map(r=>{
  const base={dimension:r.dimension,table:r.table,earthColumn:r.earthColumn,unit:r.unit,band:r.band,origin:r.origin,priority:r.priority!};
  if(r.table==='L1m'){
   const perMonth=ms.map(m=>({month:m,...observed(data,i,r,m)}));
   return {...base,value:null,perMonth,...windowVerdict(perMonth)};
  }
  return {...base,...observed(data,i,r,ms[0]!)};
 });
}
export function funnelClass(rs:Row[]):'allMatch'|'someMiss'|'noMissSomeUnknown'{
 const must=rs.filter(r=>r.priority==='must');
 return must.some(r=>r.verdict==='miss')?'someMiss':must.some(r=>r.verdict==='unknown')?'noMissSomeUnknown':'allMatch';
}
export const LIMIT_COLUMNS={access:'access_min_median',protected:'protected_pct',airport:'airport_km',slope:'slope_mean_deg'} as const;
export function limitRows(data:Dataset,request:PlanRequest,i:number){
 return (Object.keys(LIMIT_COLUMNS) as (keyof typeof LIMIT_COLUMNS)[]).filter(k=>request.limits?.[k]!==undefined).map(k=>{
  const v=data.yearly[LIMIT_COLUMNS[k]]?.[i],known=v!==undefined&&Number.isFinite(v);
  return {limit:k,max:request.limits![k]!,value:known?v:null,outcome:!known?'unknown':v!<=request.limits![k]!? 'pass':'fail'};
 });
}
/** Exact layers on unique vectors; two varying axes use prefix maximum in O(n log n). */
export function paretoLayers(vectors:number[][]):number[]{
 if(!vectors.length)return [];
 const dimensions=vectors[0]!.map((_,d)=>d).filter(d=>vectors.some(v=>v[d]!==vectors[0]![d]));
 const groups=new Map<string,{v:number[];indices:number[];depth:number}>();
 vectors.forEach((v,i)=>{const key=JSON.stringify(v);const g=groups.get(key);if(g)g.indices.push(i);else groups.set(key,{v,indices:[i],depth:1});});
 const sorted=[...groups.values()].sort((a,b)=>{for(const d of dimensions){if(a.v[d]!==b.v[d])return a.v[d]!-b.v[d]!;}return 0;});
 if(dimensions.length===1)sorted.forEach((g,i)=>g.depth=i+1);
 else if(dimensions.length===2){
  const d=dimensions[1]!,ys=[...new Set(sorted.map(g=>g.v[d]!))].sort((a,b)=>a-b),rank=new Map(ys.map((y,i)=>[y,i+1]));
  const tree=new Int32Array(ys.length+1);
  for(const g of sorted){const y=rank.get(g.v[d]!)!;let best=0;for(let j=y;j>0;j-=j&-j)best=Math.max(best,tree[j]!);g.depth=best+1;for(let j=y;j<tree.length;j+=j&-j)tree[j]=Math.max(tree[j]!,g.depth);}
 }else if(dimensions.length>2){
  sorted.forEach((g,i)=>{for(let j=0;j<i;j++){const h=sorted[j]!;if(h.v.every((x,d)=>x<=g.v[d]!))g.depth=Math.max(g.depth,h.depth+1);}});
 }
 const result=new Array<number>(vectors.length);for(const g of sorted)for(const i of g.indices)result[i]=g.depth;return result;
}
export type SearchResult={counts:{land:number;withinLimits:number;matches:number;misses:number;unknown:number};classes:Uint8Array;indices:number[];layers:Map<number,number>};
export function search(data:Dataset,request:PlanRequest):SearchResult{
 const rules=requirements(data,request),ms=months(request),classes=new Uint8Array(data.h3.length);
 const counts={land:data.h3.length,withinLimits:0,matches:0,misses:0,unknown:0};
 const matched:number[]=[],unranked:number[]=[],vectors:number[][]=[],ranked:number[]=[];
 for(let i=0;i<data.h3.length;i++){
  let excluded=false;
  for(const k of Object.keys(LIMIT_COLUMNS) as (keyof typeof LIMIT_COLUMNS)[]){const cap=request.limits?.[k],v=data.yearly[LIMIT_COLUMNS[k]]?.[i];if(cap!==undefined&&v!==undefined&&Number.isFinite(v)&&v>cap){excluded=true;break;}}
  if(excluded){classes[i]=3;continue;}counts.withinLimits++;
  let mustMiss=false,mustUnknown=false,complete=true;const gaps:number[]=[];
  for(const r of rules){let miss=false,unknown=false,gap=0;
   for(const m of r.table==='L1m'?ms:[ms[0]!]){const v=value(data,i,r,m);if(r.band===null||v===null){unknown=true;continue;}
    const g=v<r.band.lo?r.band.lo-v:v>r.band.hi?v-r.band.hi:0;
    if(g>0||(r.band.hiStrict&&v===r.band.hi)){miss=true;gap=Math.max(gap,g);}}
   const cls=miss?1:unknown?2:0;if(r.priority==='must'){mustMiss ||=cls===1;mustUnknown ||=cls===2;}
   if(cls===2)complete=false;gaps.push(gap);
  }
  if(mustMiss){classes[i]=1;counts.misses++;}else if(mustUnknown){classes[i]=2;counts.unknown++;}else{
   counts.matches++;matched.push(i);if(complete){ranked.push(i);vectors.push(gaps);}else unranked.push(i);
  }
 }
 const depths=paretoLayers(vectors),layers=new Map(ranked.map((i,j)=>[i,depths[j]!]));
 const sortRule=rules.find(r=>r.dimension===request.sortBy);
 const sortGap=(i:number)=>{if(!sortRule||!sortRule.band)return 0;return Math.max(...(sortRule.table==='L1m'?ms:[ms[0]!]).map(m=>{const v=value(data,i,sortRule,m);return v===null?Infinity:Math.max(sortRule.band!.lo-v,v-sortRule.band!.hi,0);}));};
 matched.sort((a,b)=>(layers.get(a)??Infinity)-(layers.get(b)??Infinity)||sortGap(a)-sortGap(b)||a-b);
 return {counts,classes,indices:matched,layers};
}
export function brief(data:Dataset,request:PlanRequest,indices:number[],checklist:string):string{
 const objective=data.objectives.find(o=>o.objectiveId===request.objectiveId&&o.body===request.body)!;
 const lines=['# Mission plan brief',`${request.body.toUpperCase()} / ${objective.objectiveId} — ${objective.title}`,`Months: ${months(request).join(', ')}; team: ${request.teamSize??'not set'}; days: ${request.durationDays??'not set'}`,'','Scientific status: partial. These are conditional screening results, not field certification.',...data.runtime.qualityWarnings.map(w=>'- '+w),''];
 const effectiveRules=requirements(data,request);
 for(const i of indices){
  const siteRows=rows(data,request,i);
  lines.push(`## ${data.h3[i]} (${data.yearly.lat?.[i]}, ${data.yearly.lon?.[i]})`,'',
   '| Requirement | Priority | Origin | Band | Result | Gap / reason |','|---|---|---|---|---|---|');
  // Narrative and monthly lists follow the whole table, so every requirement
  // remains a table row even when an earlier requirement has monthly evidence.
  for(const r of siteRows){
   const band=r.band?`${r.band.lo} to ${r.band.hi} ${r.unit??''}${r.band.hiStrict?' (upper excluded)':''}`:'unknown';
   lines.push(`| ${r.dimension} (${r.earthColumn??'unavailable'}) | ${r.priority} | ${r.origin} | ${band} | ${r.verdict} | ${r.reason?.text??`${r.gap??''} ${r.unit??''}`} |`);
  }
  lines.push('');
  for(const r of siteRows){
   const rule=effectiveRules.find(q=>q.dimension===r.dimension)!;
   lines.push(`### ${r.dimension}: evidence and limits`,'');
   if(r.origin==='user'){
    lines.push('Band origin: user (edited for this plan).',
     `Original source basis (context only; does not justify edited bounds): ${rule.basis??'Not recorded.'}`);
   }else{
    lines.push(`Band origin: ${r.origin}.`,`Basis: ${rule.basis??'Not recorded.'}`);
   }
   if(rule.scaleCaveat)lines.push(`Scale caveat: ${rule.scaleCaveat}`);
   if(r.perMonth){
    lines.push('');
    for(const m of r.perMonth)lines.push(`- Month ${m.month}: ${m.value??'unknown'} ${r.unit??''}; ${m.verdict}${m.reason?': '+m.reason.text:''}`);
   }
   lines.push('');
  }
  lines.push('','Operational limits:',...limitRows(data,request,i).map(r=>`- ${r.limit}: ${r.value??'unknown'} / cap ${r.max}: ${r.outcome}`));
 }
 lines.push('','## Earth cannot reproduce','- gravity: reduced lunar or Martian gravity.','- pressureRegime: lunar vacuum or thin Martian atmosphere.','- radiation: lunar or Martian radiation environment.',...objective.notTestableOnEarth.map(m=>`- ${m.mismatch}: ${m.why}`),'','## Planning checklist (from the scientist)',checklist||'Not checked: equipment, permits, personnel, budget, communications and emergency access.','','Past-campaign closeness: not checked (S8 pending).','EONET is a curated event list. None recorded does not establish safety.','','## Sources',`Build manifest SHA256: ${data.manifestHash}`,...data.inputs.map(i=>`- ${i.path}: ${i.sha256}`));return lines.join('\n')+'\n';
}
