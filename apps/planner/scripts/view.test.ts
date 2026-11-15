/**
 * The planner view layer reads the same engine results as the frozen golden cases (ADR-0012).
 * Needs the published release at ../atlas/public/data/planner-v1 (see README, "Run the planner on real data").
 */
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { readFileSync, readdirSync } from 'node:fs';
import { resolve } from 'node:path';
import type { Dataset, Objective, Rule, Runtime } from '../../atlas/src/planner/engine.ts';
import { pickObjective, siteClass, supportedTraits, traitCells, GLYPH, newRequest } from '../src/model.ts';

const base = resolve(import.meta.dirname, process.env.PLANNER_RELEASE ?? '../../atlas/public/data/planner-v1');
const json = (name: string) => JSON.parse(readFileSync(resolve(base, name), 'utf8'));
const bytes = (name: string) => { const b = readFileSync(resolve(base, name)); return b.buffer.slice(b.byteOffset, b.byteOffset + b.byteLength); };

function load(): Dataset {
  const manifest = json('build-manifest.json');
  for (const [name, hash] of Object.entries(manifest.files)) {
    assert.equal(createHash('sha256').update(readFileSync(resolve(base, name))).digest('hex'), hash, `${name} hash`);
  }
  const meta = json('cells.json'), raw = bytes('cells.bin');
  const yearly: Record<string, Float32Array> = {}, monthly: Record<string, Float32Array> = {};
  for (const c of meta.columns) yearly[c.name] = new Float32Array(raw, c.offset, c.length);
  for (const c of Object.keys(json('monthly/monthly.json').columns)) monthly[c] = new Float32Array(bytes(`monthly/${c}.bin`));
  return {
    h3: meta.h3, yearly, monthly, objectives: json('objectives.json') as Objective[], rules: json('trait-map.json').rules as Rule[],
    runtime: json('planner-runtime.json') as Runtime, manifestHash: '', inputs: manifest.inputs,
  };
}

const data = load();

test('trait cells and site class match every golden case', () => {
  const cases = json('golden-verdicts.json') as { h3: string; request: Parameters<typeof traitCells>[1]; verdicts: { dimension: string; verdict: 'match' | 'miss' | 'unknown'; priority: string }[]; funnelClass: string }[];
  assert.ok(cases.length > 0);
  for (const c of cases) {
    const i = data.h3.indexOf(c.h3);
    const cells = traitCells(data, c.request, i);
    assert.deepEqual(cells.map(x => [x.dimension, x.verdict, x.priority]), c.verdicts.map(v => [v.dimension, v.verdict, v.priority]), c.h3);
    assert.ok(cells.every(x => x.glyph === GLYPH[x.verdict]));
    assert.equal(siteClass(data, c.request, i), c.funnelClass);
  }
  console.log(`view layer agrees with ${cases.length} golden cases`);
});

test('each category gets an objective of the chosen body, testing only traits it needs', () => {
  for (const body of ['moon', 'mars'] as const) {
    for (const cat of data.runtime.categories) {
      const { objectiveId, supported } = pickObjective(data, body, cat);
      assert.equal(data.objectives.find(o => o.objectiveId === objectiveId)?.body, body);
      assert.deepEqual(supported, supportedTraits(data, objectiveId, cat));
      assert.ok(supported.every(d => cat.traits.includes(d)));
      const request = newRequest(data, body, cat);
      assert.equal(request.objectiveId, objectiveId);
      assert.equal(request.category, cat.categoryId);
    }
  }
});

test('no single site score anywhere in the view code (AGENTS.md rule 4)', () => {
  const dir = resolve(import.meta.dirname, '../src');
  const files = readdirSync(dir, { recursive: true }).map((f: string | Buffer) => String(f)).filter(f => /\.(ts|tsx)$/.test(f));
  assert.ok(files.length > 5);
  for (const f of files) {
    const code = readFileSync(resolve(dir, f), 'utf8').replace(/\/\*[\s\S]*?\*\/|\/\/.*$/gm, '');
    assert.doesNotMatch(code, /score|percent(age)?Match|matchPct|average/i, f);
  }
  const sample = traitCells(data, newRequest(data, 'mars', data.runtime.categories[0]!), 0);
  assert.doesNotMatch(JSON.stringify(sample), /score/i);
});
