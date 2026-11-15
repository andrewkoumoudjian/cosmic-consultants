import './style.css';
import { setWorkerUrl, type GeoJSONSource } from 'maplibre-gl';
import { cellToBoundary } from 'h3-js';
import { createMap } from '../map';
import { decodePlan, encodePlan, validatePlan, type PlanRequest } from '../plan-url';
import { ensureMonthly, loadDataset, monthlyColumnsForObjective, usedMonthlyColumns } from './data';
import { brief, funnelClass, limitRows, months, requirements, rows, search, type Dataset, type Row, type SearchResult } from './engine';

const element=<T extends HTMLElement>(id:string)=>{const e=document.getElementById(id);if(!e)throw Error(`Missing #${id}`);return e as T;};
function el<K extends keyof HTMLElementTagNameMap>(tag:K,text?:string,cls?:string){const e=document.createElement(tag);if(text!==undefined)e.textContent=text;if(cls)e.className=cls;return e;}
function button(text:string,fn:()=>void){const e=el('button',text);e.type='button';e.addEventListener('click',fn);return e;}
const controls=element('controls'),details=element('details'),results=element('results'),status=element('status');
const monthNames=['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];
let data:Dataset,request:PlanRequest,result:SearchResult,pinned:number[]=[],active:number|null=null,show=20,filter='matches',checklist='';
let map:ReturnType<typeof createMap>|null=null,mapReady=false;
const countFormat=(n:number)=>n.toLocaleString();
const number=(v:number|null|undefined)=>v==null||!Number.isFinite(v)?'unknown':Number(v.toPrecision(6)).toLocaleString(undefined,{maximumFractionDigits:5});
function select<T extends string>(label:string,options:[T,string][],selected:T,onChange:(value:T)=>void){
 const wrap=el('label',label),input=el('select');for(const [v,text]of options){const o=el('option',text);o.value=v;o.selected=v===selected;input.append(o);}input.addEventListener('change',()=>onChange(input.value as T));wrap.append(input);return wrap;
}
function field(label:string,v:number,min:number,max:number,onChange:(n:number)=>void){
 const wrap=el('label',label),input=el('input');input.type='number';input.value=String(v);input.min=String(min);input.max=String(max);input.addEventListener('change',()=>{const n=Number(input.value);if(Number.isFinite(n)&&n>=min&&n<=max){input.setCustomValidity('');onChange(n);}else{input.setCustomValidity(`Enter a value from ${min} to ${max}.`);input.reportValidity();}});wrap.append(input);return wrap;
}
async function setObjective(id:string){
 request.objectiveId=id;delete request.bandEdits;delete request.must;delete request.nice;delete request.pins;pinned=[];active=null;
 const needed=monthlyColumnsForObjective(data,id).filter(c=>!(c in data.monthly));
 if(needed.length){
  status.className='';status.textContent=`Loading monthly trait data for ${id}…`;
  await ensureMonthly(data,needed,p=>{status.textContent=`Loading monthly trait data (${p.loadedFiles}/${p.totalFiles} files · ${(p.loadedBytes/1048576).toFixed(1)} MB)…`;});
  if(request.objectiveId!==id)return;
 }
 defaults();renderControls();run();
}
function defaults(){
 const rs=requirements(data,request);request.must=rs.filter(r=>r.band!==null&&r.earthColumn!==null&&r.priority!=='nice').map(r=>r.dimension);
 request.nice=rs.filter(r=>!request.must!.includes(r.dimension)).map(r=>r.dimension);
 request.sortBy=rs[0]?.dimension;
}
function renderControls(){
 controls.replaceChildren(el('h2','1. Define the mission'),el('p','Choose an objective and an Earth test window. Edit the requirements to fit your experiment.'));
 controls.append(select('Target body',[['moon','Moon'],['mars','Mars']],request.body,b=>{request.body=b;void setObjective(data.objectives.find(o=>o.body===b)!.objectiveId);}));
 controls.append(select('NASA objective',data.objectives.filter(o=>o.body===request.body).map(o=>[o.objectiveId,`${o.objectiveId} · ${o.title}`]),request.objectiveId,id=>{void setObjective(id);}));
 controls.append(select('Planning category',data.runtime.categories.map(c=>[c.categoryId,c.name]),request.category??data.runtime.categories[0]!.categoryId,c=>{request.category=c;renderControls();run();}));
 const cat=data.runtime.categories.find(c=>c.categoryId===request.category);if(cat){const info=el('details');info.append(el('summary','Category scope and available evidence'));info.append(el('p','The category describes your activity. The measured requirements below drive this first release; the full category menu is not yet supported.'));for(const metric of cat.detailedMetricMenuText??[])info.append(el('p',metric));controls.append(info);}
 controls.append(select('Mission type',[['robotic','Robotic'],['crewed','Crewed'],['instrument','Instrument test']],request.missionType,t=>{request.missionType=t;run();}));
 const dates=el('div',undefined,'form-row');
 dates.append(select('First month',monthNames.map((n,i)=>[String(i+1),n]),String(request.months.start),m=>{request.months.start=Number(m);run();}),select('Last month',monthNames.map((n,i)=>[String(i+1),n]),String(request.months.end),m=>{request.months.end=Number(m);run();}));controls.append(dates);
 const trip=el('div',undefined,'form-row');trip.append(field('Days',request.durationDays??14,1,365,n=>{request.durationDays=n;run();}),field('Team size',request.teamSize??6,1,1000,n=>{request.teamSize=n;run();}));controls.append(trip);
 controls.append(el('h3','Test requirements'),el('p','Required traits must match in every selected month. Preferred traits remain visible. Unknown bands start as preferred so you can explore.', 'muted'));
 for(const r of requirements(data,request)){
  const box=el('div',undefined,'metric');box.append(el('strong',`${r.dimension} · ${r.earthColumn??'field evidence needed'}`),el('small',`${r.unit??'no global measurement'} · ${r.table==='L1m'?'monthly':'yearly / site context'}`));
  box.append(select('Priority',[['must','Required'],['nice','Preferred']],r.priority!,p=>{request.must=requirements(data,request).filter(x=>x.dimension===r.dimension?p==='must':x.priority==='must').map(x=>x.dimension);request.nice=requirements(data,request).filter(x=>!request.must!.includes(x.dimension)).map(x=>x.dimension);run();}));
  const bounds=el('div',undefined,'form-row'),lo=el('input'),hi=el('input');lo.type=hi.type='number';lo.step=hi.step='any';lo.value=r.band===null?'':String(r.band.lo);hi.value=r.band===null?'':String(r.band.hi);lo.placeholder='Minimum';hi.placeholder='Maximum';lo.setAttribute('aria-label',`${r.dimension} minimum`);hi.setAttribute('aria-label',`${r.dimension} maximum`);
  const strictWrap=el('label'),strict=el('input');strict.type='checkbox';strict.checked=r.band?.hiStrict??false;strictWrap.append(strict,document.createTextNode(' Exclude the upper boundary'));
  const edit=()=>{if(lo.value===''&&hi.value===''){request.bandEdits=request.bandEdits?.filter(e=>e.dimension!==r.dimension);renderControls();run();return;}
   const l=lo.value===''?NaN:Number(lo.value),h=hi.value===''?NaN:Number(hi.value);if(!Number.isFinite(l)||!Number.isFinite(h)||l>h){hi.setCustomValidity('Enter both bounds, with minimum at or below maximum.');hi.reportValidity();return;}hi.setCustomValidity('');request.bandEdits=[...(request.bandEdits??[]).filter(e=>e.dimension!==r.dimension),{dimension:r.dimension,lo:l,hi:h,...(strict.checked?{hiStrict:true}:{})}];run();};
  lo.addEventListener('change',edit);hi.addEventListener('change',edit);strict.addEventListener('change',edit);bounds.append(lo,hi);box.append(bounds,strictWrap);
  if(r.band===null)box.append(el('small','No accepted band. Enter your own test bounds, or keep this trait unknown.'));
  const why=el('details');why.append(el('summary',`Basis: ${r.origin}`),el('p',r.basis??'No cited basis.'),el('p',r.scaleCaveat??'Source support limits apply.'));box.append(why);controls.append(box);
 }
 const advanced=el('details');advanced.append(el('summary','Access limits and display'));
 for(const [key,label,unit,max]of [['access','Travel time to city','min',50000],['airport','Distance to airport','km',30000],['protected','Protected land','%',100],['slope','Mean slope','deg',90]] as const){
  const wrap=el('label',`${label} (${unit}; blank = no limit)`),input=el('input');input.type='number';input.min='0';input.max=String(max);input.step='any';input.value=request.limits?.[key]===undefined?'':String(request.limits[key]);input.addEventListener('change',()=>{const limits={...request.limits};if(input.value==='')delete limits[key];else{const n=Number(input.value);if(!Number.isFinite(n)||n<0||n>max){input.setCustomValidity('Enter a nonnegative value within the stated range.');input.reportValidity();return;}input.setCustomValidity('');limits[key]=n;}request.limits=limits;run();});wrap.append(input);advanced.append(wrap);
 }
 const rs=requirements(data,request);advanced.append(select('Sort within each Pareto layer',rs.map(r=>[r.dimension,r.dimension]),request.sortBy??rs[0]!.dimension,d=>{request.sortBy=d;run();}),select('Sites to show',[['20','20'],['50','50'],['100','100'],['all','All (paged)']],request.top===undefined||request.top===null?'all':String(request.top),t=>{request.top=t==='all'?null:Number(t);run();}));controls.append(advanced);
}
function run(){
 try{const errors=validatePlan(request);if(errors.length)throw Error(errors.join('; '));const start=performance.now();result=search(data,request);request.pins=pinned.map(i=>data.h3[i]!);history.replaceState(null,'',`${location.pathname}?${encodePlan(request)}${checklist?'#'+encodeURIComponent(JSON.stringify({checklist})):''}`);
  const ms=months(request);status.className='';status.textContent=`Real source data · ${countFormat(data.h3.length)} land cells · ${ms.map(m=>monthNames[m-1]).join(', ')} · conditional results, scientific review partial`;
  status.dataset.computeMs=String(Math.round(performance.now()-start));
  const counter=element('counter');counter.replaceChildren(el('h2','2. Find and compare sites'));const funnel=el('div',undefined,'funnel');for(const [name,n]of [['Land cells',result.counts.land],['Within limits',result.counts.withinLimits],['Required traits match',result.counts.matches],['Need more evidence',result.counts.unknown]] as const){const stat=el('div',undefined,'stat');stat.append(el('strong',countFormat(n)),el('span',name));funnel.append(stat);}counter.append(funnel);
  if(!request.must?.length)counter.append(el('p','All requirements are preferred: no trait filters the results.','warning'));
  show=request.top??20;renderResults();renderDetails();renderMap();element<HTMLButtonElement>('export').disabled=false;element<HTMLButtonElement>('print').disabled=false;
 }catch(e){status.className='error';status.textContent=String(e);}
}
function visibleIndices(){
 if(filter==='matches')return result.indices;
 const code=filter==='unknown'?2:1;return [...result.classes.keys()].filter(i=>result.classes[i]===code);
}
function renderResults(){
 results.replaceChildren();const heading=el('div',undefined,'results-head');heading.append(el('h3','Candidate sites'),select('Show',[['matches','Required traits match'],['unknown','Need more evidence'],['misses','Known misses']],filter,f=>{filter=f;show=request.top??20;renderResults();renderMap();}));results.append(heading);
 const indices=visibleIndices(),limit=request.top??Infinity,page=indices.slice(0,Math.min(show,limit));
 if(!indices.length){const msg=el('div',undefined,'empty');msg.append(el('strong',filter==='matches'?'No sites match every required trait.':'No sites in this group.'),el('p','Review the bands and month window, make an uncertain requirement preferred, or inspect the “Need more evidence” group. Unknown data never counts as a match.'));results.append(msg);}
 else{results.append(el('p',`Showing ${countFormat(page.length)} of ${countFormat(Math.min(indices.length,limit))}. Pareto layers use all displayed requirements with known verdicts. Sites missing preferred evidence are shown separately, without a layer.`,'muted'));
  const table=el('table'),thead=el('thead'),hr=el('tr');for(const text of ['Location','Result / layer','Inspect'])hr.append(el('th',text));thead.append(hr);table.append(thead);const tbody=el('tbody');
  for(const i of page){const tr=el('tr'),loc=el('td');loc.append(el('span',`${number(data.yearly.lat?.[i])}°, ${number(data.yearly.lon?.[i])}°`),el('small',data.h3[i],'muted'));const state=el('td',result.classes[i]===0?(result.layers.has(i)?`Pareto layer ${result.layers.get(i)}`:'Match · preferred evidence incomplete'):result.classes[i]===1?'Known miss':'Unknown');const actions=el('td');actions.append(button('Open',()=>open(i)),button(pinned.includes(i)?'Unpin':'Compare',()=>pin(i)));tr.append(loc,state,actions);tbody.append(tr);}table.append(tbody);results.append(table);
  if(page.length<Math.min(indices.length,limit))results.append(button('Show more',()=>{show+=100;renderResults();renderMap();}));
 }
 if(pinned.length>1){const wrap=el('div',undefined,'comparison');wrap.append(el('h3','Side-by-side comparison'));const table=el('table'),hr=el('tr');hr.append(el('th','Trait'));for(const i of pinned)hr.append(el('th',`${number(data.yearly.lat?.[i])}°, ${number(data.yearly.lon?.[i])}°`));table.append(hr);
  for(const rule of requirements(data,request)){const tr=el('tr');tr.append(el('th',rule.dimension));for(const i of pinned){const r=rows(data,request,i).find(r=>r.dimension===rule.dimension)!;tr.append(el('td',`${r.verdict}${r.gap!==undefined?` · gap ${number(r.gap)} ${r.unit??''}`:''}`));}table.append(tr);}wrap.append(table);results.append(wrap);
 }
}
function open(i:number){active=i;renderDetails();if(map)map.easeTo({center:[data.yearly.lon![i]!,data.yearly.lat![i]!],zoom:4});renderMap();}
function pin(i:number){if(pinned.includes(i))pinned=pinned.filter(j=>j!==i);else{if(pinned.length===3){pinned.shift();status.textContent='The oldest comparison site was replaced.';}pinned.push(i);}active=i;run();}
function detailRow(r:Row){const box=el('div',undefined,`verdict status-${r.verdict}`);box.append(el('strong',`${r.priority==='must'?'Required':'Preferred'} · ${r.dimension}: ${r.verdict.toUpperCase()}`));
 const measure=r.table==='L1m'?`Monthly ${r.earthColumn}`:`${r.earthColumn??'No Earth column'}: ${number(r.value)} ${r.unit??''}`;box.append(el('small',measure));if(r.band)box.append(el('small',`Test band ${r.band.lo} to ${r.band.hi} ${r.unit??''}${r.band.hiStrict?' (upper excluded)':''}`));
 if(r.gap!==undefined)box.append(el('p',`Gap ${number(r.gap)} ${r.unit??''} ${r.side}${r.gap===0?' · on the excluded strict boundary':''}`,'gap'));
 if(r.reason)box.append(el('p',r.reason.text));if(r.perMonth){const list=el('details');list.append(el('summary','Values by selected month'));for(const m of r.perMonth)list.append(el('p',`${monthNames[m.month-1]}: ${number(m.value)} ${r.unit??''} · ${m.verdict}${m.reason?` · ${m.reason.text}`:''}`));box.append(list);}return box;}
function renderDetails(){
 details.replaceChildren(el('h2','3. Gaps and field plan'));
 if(active===null){details.append(el('p','Open a candidate or pin up to three to compare.'));return;}
 const i=active,card=el('div',undefined,'site-card');card.append(el('h3',data.h3[i]),el('p',`${number(data.yearly.lat?.[i])}°, ${number(data.yearly.lon?.[i])}°`,'coordinates'),button(pinned.includes(i)?'Remove from comparison':'Pin to compare',()=>pin(i)));
 for(const r of rows(data,request,i))card.append(detailRow(r));details.append(card);
 const season=el('section');season.append(el('h3','4. Logistics and season'));for(const [col,label,unit]of [['access_min_median','Travel time to city','min'],['airport_km','Nearest paved-runway airport','km'],['protected_pct','Protected-land share','%']])season.append(el('p',`${label}: ${number(data.yearly[col!]?.[i])} ${unit}`));
 for(const r of limitRows(data,request,i))season.append(el('p',`${r.limit}: ${r.outcome}${r.outcome==='unknown'?' — this limit is unverified':''}`));
 const strip=el('div',undefined,'month-strip');for(let m=1;m<=12;m++){const req={...request,months:{start:m,end:m}},cls=funnelClass(rows(data,req,i));strip.append(el('span',`${monthNames[m-1]} · ${cls==='allMatch'?'match':cls==='someMiss'?'miss':'?'}`,`status-${cls==='allMatch'?'match':cls==='someMiss'?'miss':'unknown'}`));}season.append(strip,el('small','The strip checks monthly test requirements. Access, permits and safe field conditions still need verification.','muted'));details.append(season);
 const risk=el('section');risk.append(el('h3','5. Recorded hazards'),el('p','EONET is a curated list. None recorded does not establish safety.'));
 const events=data.runtime.events[data.h3[i]!]??[];risk.append(el('p',`${events.length} nearby event records in the source window.`));const ev=el('details');ev.append(el('summary','Event names and dates'));for(const e of events.slice(0,100))ev.append(el('p',`${String(e.title??e.event_id)} · ${String(e.start_date??'date unknown')}`));risk.append(ev);risk.append(el('p',`Steep ground (>30°): ${number(data.yearly.slope_frac_gt30?.[i])} share.`));details.append(risk);
 const past=el('details');past.append(el('summary','6. Cited past campaigns'));past.append(el('p','Reference records only. Similarity and campaign-time conditions have not been assessed.'));for(const c of data.runtime.campaigns){past.append(el('p',String(c.name??c.campaignId??'Campaign record')));}details.append(past);
 const checks=el('section');checks.append(el('h3','Planning checklist'),el('p','Record equipment, permits, budget, staffing, communications and evacuation needs. These are your notes.'));const text=el('textarea');text.setAttribute('aria-label','Planning checklist');text.value=checklist;text.addEventListener('change',()=>{checklist=text.value;run();});checks.append(text);details.append(checks);
 const limits=el('section',undefined,'breakdowns');limits.append(el('h3','What Earth cannot test'));for(const [k,text]of [['gravity','Reduced lunar or Martian gravity'],['pressureRegime','Lunar vacuum or thin Martian air'],['radiation','Lunar or Martian radiation']])limits.append(el('p',`${k}: ${text}`));details.append(limits);
 const source=el('details',undefined,'sources');source.append(el('summary','Sources, scale caveats and data limits'));for(const w of data.runtime.qualityWarnings)source.append(el('p',w));for(const r of requirements(data,request)){source.append(el('p',`${r.dimension}: ${r.basis??''} ${r.scaleCaveat??''}`));}source.append(el('p',`Build manifest SHA256: ${data.manifestHash}`));const link=el('a','Download source manifest');link.href='./data/planner-v1/source-manifest.json';link.download='source-manifest.json';source.append(link);details.append(source);
}
function renderMap(){
 if(!map||!mapReady||!result)return;
 const indices=[...new Set([...visibleIndices().slice(0,Math.min(show,request.top??200)),...pinned,...(active===null?[]:[active])])];
 const features=indices.map(i=>{const center=data.yearly.lon![i]!,boundary=cellToBoundary(data.h3[i]!,true).map(([lon,lat])=>{while(lon-center>180)lon-=360;while(lon-center< -180)lon+=360;return [lon,lat];});return {type:'Feature' as const,geometry:{type:'Polygon' as const,coordinates:[boundary]},properties:{index:i,cls:result.classes[i],selected:pinned.includes(i)||active===i?1:0}};});
 const source=map.getSource('planner-sites') as GeoJSONSource;source.setData({type:'FeatureCollection',features});
}
function download(){const chosen=pinned.length?pinned:active===null?[]:[active];if(!chosen.length){status.textContent='Open or pin a site before exporting a brief.';return;}const a=el('a');a.href=URL.createObjectURL(new Blob([brief(data,request,chosen,checklist)],{type:'text/markdown'}));a.download='mission-plan.md';a.click();setTimeout(()=>URL.revokeObjectURL(a.href),1000);}
element('export').addEventListener('click',download);element('print').addEventListener('click',()=>window.print());
async function init(){
 try{
  const decoded=location.search?decodePlan(location.search):null;
  if(decoded&&!decoded.ok)throw Error(decoded.errors.join('; '));
  if(decoded?.ok&&decoded.unknownKeys.length)throw Error(`Unknown request fields: ${decoded.unknownKeys.join(', ')}`);
  const initialObjectiveId=decoded?.ok?decoded.plan.objectiveId:'LI-5L';
  data=await loadDataset('./data/planner-v1/',{initialObjectiveId,onProgress:p=>{status.textContent=`Loading and verifying published data (${p.loadedFiles}/${p.totalFiles} files · ${(p.loadedBytes/1048576).toFixed(1)} MB)…`;}});
  request=decoded?.ok?decoded.plan:{version:1,body:'moon',objectiveId:'LI-5L',category:'robotic-mobility-navigation',missionType:'robotic',months:{start:1,end:1},durationDays:14,teamSize:6,top:20};
  if(!decoded)defaults();if(location.hash){try{const hash=JSON.parse(decodeURIComponent(location.hash.slice(1)));if(typeof hash.checklist==='string')checklist=hash.checklist;}catch{throw Error('The saved checklist link is invalid.');}}
  pinned=(request.pins??[]).map(h=>data.h3.indexOf(h));if(pinned.some(i=>i<0))throw Error('A pinned site is outside the published data.');active=pinned[0]??null;
  renderControls();run();
  void ensureMonthly(data,usedMonthlyColumns(data)).catch(()=>{});
  try{setWorkerUrl(new URL('maplibre-gl-worker.mjs',new URL(import.meta.env.BASE_URL,location.href)).href);map=createMap(element('map'));map.on('load',()=>{mapReady=true;map!.addSource('planner-sites',{type:'geojson',data:{type:'FeatureCollection',features:[]}});map!.addLayer({id:'planner-fill',type:'fill',source:'planner-sites',paint:{'fill-color':['match',['get','cls'],0,'#70cba4',1,'#d49b76',2,'#9daabb','#4d6171'],'fill-opacity':0.65}});map!.addLayer({id:'planner-outline',type:'line',source:'planner-sites',paint:{'line-color':'#d1e2e8','line-width':['case',['==',['get','selected'],1],3,0.5]}});map!.on('click','planner-fill',e=>{const n=Number(e.features?.[0]?.properties?.index);if(Number.isInteger(n))open(n);});renderMap();});map.on('error',()=>{element('map').setAttribute('aria-label','Basemap tiles unavailable; the site list remains usable.');});}
  catch{element('map').replaceChildren(el('p','Map unavailable on this device. The site finder and comparison remain usable.'));}
 }catch(e){status.className='error';status.textContent=String(e);status.append(button('Retry',()=>location.reload()));}
}
void init();
