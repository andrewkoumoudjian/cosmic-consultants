import test from 'node:test';
import assert from 'node:assert/strict';
import { verdict, windowVerdict, paretoLayers, brief, type Dataset, type Rule } from '../src/planner/engine.ts';
import type { PlanRequest } from '../src/plan-url.ts';

test('strict boundary is a zero-gap miss; missing and empty windows stay unknown',()=>{
 assert.deepEqual(verdict(10,{lo:0,hi:10,hiStrict:true}),{verdict:'miss',gap:0,side:'above'});
 assert.deepEqual(verdict(10,{lo:0,hi:10}),{verdict:'match'});
 assert.equal(windowVerdict([]).verdict,'unknown');
 assert.equal(windowVerdict([{verdict:'match'},{verdict:'unknown',reason:{code:'missing',text:'cloud'}}]).verdict,'unknown');
 assert.throws(()=>verdict(Infinity,{lo:0,hi:10}));
});
test('Pareto layers retain identities on ties and tradeoffs',()=>{
 assert.deepEqual(paretoLayers([[0,2],[1,1],[2,0],[2,2],[0,2]]),[1,1,1,2,1]);
 assert.deepEqual(paretoLayers([[],[],[]]),[1,1,1]);
});
test('optimized layering agrees with independent exhaustive reference',()=>{
 const vectors=Array.from({length:150},(_,i)=>[(i*17)%23,(i*31)%19]);
 const pending=new Set(vectors.map((_,i)=>i)),levels=new Array<number>(vectors.length);let layer=1;
 while(pending.size){
  const front=[...pending].filter(i=>![...pending].some(j=>vectors[j]!.every((v,k)=>v<=vectors[i]![k]!)&&vectors[j]!.some((v,k)=>v<vectors[i]![k]!)));
  for(const i of front){levels[i]=layer;pending.delete(i);}layer++;
 }
 assert.deepEqual(paretoLayers(vectors),levels);
});

function exportFixture(): { data: Dataset; request: PlanRequest } {
 const rules: (Rule & { objectiveId: string })[] = [
  {objectiveId:'OP-5LM',dimension:'terrain',table:'L1',earthColumn:'slope_mean_deg',unit:'deg',band:{lo:0,hi:5},origin:'target',priority:'must',basis:'SYNTHETIC target slope band: 0 to 5 deg.',scaleCaveat:'SYNTHETIC cell-scale support.'},
  {objectiveId:'OP-5LM',dimension:'thermal',table:'L1m',earthColumn:'lst_night_k',unit:'K',band:{lo:270,hi:300},origin:'team',priority:'must',basis:'SYNTHETIC thermal rationale.'},
  {objectiveId:'OP-5LM',dimension:'surfaceMaterial',table:'L1',earthColumn:'barren_pct',unit:'%',band:{lo:50,hi:100},origin:'team',priority:'must',basis:'SYNTHETIC barren-share rationale.'},
 ];
 const data: Dataset = {
  h3:['842a107ffffffff'],
  yearly:{lat:new Float32Array([10]),lon:new Float32Array([20]),slope_mean_deg:new Float32Array([3]),barren_pct:new Float32Array([80])},
  monthly:{lst_night_k:new Float32Array(12).fill(285)},
  objectives:[{objectiveId:'OP-5LM',body:'mars',title:'SYNTHETIC export example',requiredDimensions:['terrain','thermal','surfaceMaterial'],earthTestableComponent:'Synthetic fixture',notTestableOnEarth:[]}],
  rules,
  runtime:{numericPolicy:'published-float32-no-epsilon',qualityWarnings:[],reasonSets:[{}],yearlyReasons:[0],monthlyReasons:new Array(12).fill(0),categories:[],campaigns:[],events:{}},
  manifestHash:'0'.repeat(64),inputs:[],
 };
 return {data,request:{version:1,body:'mars',objectiveId:'OP-5LM',missionType:'robotic',months:{start:1,end:1}}};
}

test('brief keeps all requirement rows together before monthly evidence',()=>{
 const {data,request}=exportFixture(),text=brief(data,request,[0],'');
 const lines=text.slice(text.indexOf('| Requirement |')).split('\n');
 const table=[];
 for(const line of lines){if(!line.startsWith('|'))break;table.push(line);}
 assert.equal(table.length,5,'header, delimiter and exactly three requirement rows');
 assert.match(table[2]!,/^\| terrain /);
 assert.match(table[3]!,/^\| thermal /);
 assert.match(table[4]!,/^\| surfaceMaterial /);
 assert.ok(text.indexOf('- Month 1:')>text.indexOf('| surfaceMaterial '));
 assert.ok(text.indexOf('SYNTHETIC target slope band:')>text.indexOf('| surfaceMaterial '));
});

test('brief distinguishes a user-edited band from its original source basis',()=>{
 const {data,request}=exportFixture();request.bandEdits=[{dimension:'terrain',lo:0,hi:20}];
 const text=brief(data,request,[0],'');
 assert.match(text,/\| terrain .*\| user \| 0 to 20 deg \|/);
 assert.match(text,/Band origin: user \(edited for this plan\)\./);
 assert.match(text,/Original source basis \(context only; does not justify edited bounds\): SYNTHETIC target slope band: 0 to 5 deg\./);
 assert.match(text,/Scale caveat: SYNTHETIC cell-scale support\./);
});

test('Pareto layers ignore unbanded nice rules while leaving sites missing banded observations unranked', async () => {
 const { search } = await import('../src/planner/engine.ts');
 const d: Dataset = {
  h3: ['842a107ffffffff', '842a103ffffffff', '842a101ffffffff'],
  yearly: {
   lat: new Float32Array([10, 11, 12]),
   lon: new Float32Array([20, 21, 22]),
   barren_pct: new Float32Array([80, 90, 85]),
   slope_mean_deg: new Float32Array([3, 6, NaN]),
  },
  monthly: {},
  objectives: [{
   objectiveId: 'OP-5LM', body: 'mars', title: 'SYNTHETIC',
   requiredDimensions: ['terrain', 'surfaceMaterial', 'thermal'],
   earthTestableComponent: 'Synthetic', notTestableOnEarth: [],
  }],
  rules: [
   { objectiveId: 'OP-5LM', dimension: 'surfaceMaterial', table: 'L1', earthColumn: 'barren_pct', unit: '%', band: { lo: 50, hi: 100 }, origin: 'team', priority: 'must' } as Rule & { objectiveId: string },
   { objectiveId: 'OP-5LM', dimension: 'terrain', table: 'L1', earthColumn: 'slope_mean_deg', unit: 'deg', band: { lo: 0, hi: 5 }, origin: 'target', priority: 'nice' } as Rule & { objectiveId: string },
   { objectiveId: 'OP-5LM', dimension: 'thermal', table: 'L1m', earthColumn: 'lst_night_k', unit: 'K', band: null, origin: 'target', priority: 'nice' } as Rule & { objectiveId: string },
  ],
  runtime: { numericPolicy: 'published-float32-no-epsilon', qualityWarnings: [], reasonSets: [{}], yearlyReasons: [0, 0, 0], monthlyReasons: new Array(36).fill(0), categories: [], campaigns: [], events: {} },
  manifestHash: '0'.repeat(64), inputs: [],
 };
 const req: PlanRequest = { version: 1, body: 'mars', objectiveId: 'OP-5LM', missionType: 'robotic', months: { start: 1, end: 1 }, must: ['surfaceMaterial'], nice: ['terrain', 'thermal'] };
 const res = search(d, req);
 assert.equal(res.counts.matches, 3);
 assert.equal(res.layers.get(0), 1, 'terrain match beats terrain miss');
 assert.equal(res.layers.get(1), 2, 'terrain miss gets layer 2 instead of undefined');
 assert.equal(res.layers.has(2), false, 'missing observation on banded nice rule stays unranked');
});
