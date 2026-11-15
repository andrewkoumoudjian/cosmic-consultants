import test from 'node:test';
import assert from 'node:assert/strict';
import { verdict, windowVerdict, paretoLayers } from '../src/planner/engine.ts';

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
