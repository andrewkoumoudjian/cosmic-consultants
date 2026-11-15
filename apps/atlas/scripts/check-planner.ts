/** Independent Python golden parity and full-domain real request checks. */
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { createHash } from 'node:crypto';
import assert from 'node:assert/strict';
import { rows, funnelClass, search, limitRows, brief, type Dataset, type Runtime, type Objective, type Rule } from '../src/planner/engine.ts';
import type { PlanRequest } from '../src/plan-url.ts';
const base=resolve(process.argv[2]??'public/data/planner-v1');
const json=(name:string)=>JSON.parse(readFileSync(resolve(base,name),'utf8'));
const bytes=(name:string)=>{const b=readFileSync(resolve(base,name));return b.buffer.slice(b.byteOffset,b.byteOffset+b.byteLength);};
const manifest=json('build-manifest.json');
for(const [name,hash]of Object.entries(manifest.files))assert.equal(createHash('sha256').update(readFileSync(resolve(base,name))).digest('hex'),hash,`${name} hash`);
const meta=json('cells.json'),raw=bytes('cells.bin');const yearly:Record<string,Float32Array>={},monthly:Record<string,Float32Array>={};
for(const c of meta.columns)yearly[c.name]=new Float32Array(raw,c.offset,c.length);
for(const c of Object.keys(json('monthly/monthly.json').columns))monthly[c]=new Float32Array(bytes(`monthly/${c}.bin`));
const data:Dataset={h3:meta.h3,yearly,monthly,objectives:json('objectives.json') as Objective[],rules:json('trait-map.json').rules as Rule[],runtime:json('planner-runtime.json') as Runtime,manifestHash:createHash('sha256').update(readFileSync(resolve(base,'build-manifest.json'))).digest('hex'),inputs:manifest.inputs};
let count=0;
for(const c of json('golden-verdicts.json')){
 const i=data.h3.indexOf(c.h3),actual=rows(data,c.request,i);
 assert.deepEqual(actual,c.verdicts,`${c.h3} / ${c.request.objectiveId} / ${JSON.stringify(c.request.months)}`);
 assert.equal(funnelClass(actual),c.funnelClass);
 assert.deepEqual(limitRows(data,c.request,i).map(({limit,max,value,outcome})=>({limit,max,value,outcome})),c.limits.map(({limit,max,value,outcome}:{limit:string;max:number;value:number|null;outcome:string})=>({limit,max,value,outcome})));
 count++;
}
console.log(`PASS ${count} Python/browser golden cases; all artifact SHA256 values match.`);
for(const [body,objectiveId,must,nice]of [['moon','LI-5L',['terrain','illumination'],[]],['mars','OP-5LM',['surfaceMaterial'],['terrain','thermal','dustProcess']]] as const){
 const request:PlanRequest={version:1,body,objectiveId,missionType:'robotic',months:{start:1,end:1},must:[...must],nice:[...nice],top:20};
 const start=performance.now(),result=search(data,request);
 assert.equal(result.counts.land,91800);assert.ok(result.counts.matches>0);
 assert.equal(result.counts.withinLimits,result.counts.matches+result.counts.misses+result.counts.unknown);
 const chosen=result.indices.slice(0,3);const text=brief(data,request,chosen,'Equipment and permits: not checked.');
 assert.ok(text.includes('pressureRegime'));assert.ok(text.includes(data.manifestHash));assert.ok(chosen.every(i=>text.includes(data.h3[i]!)));
 console.log(`PASS ${body}: ${JSON.stringify(result.counts)}, ${chosen.length} sites compared/exported, ${Math.round(performance.now()-start)} ms`);
}
