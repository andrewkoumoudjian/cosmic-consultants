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
import { burnedInWindow, pickObjective, sheetCsv, siteClass, supportedTraits, traitCells, GLYPH, newRequest } from '../src/model.ts';

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

/** Minimal RFC 4180 reader, enough to check our own export. */
function parseCsv(text: string): string[][] {
  const out: string[][] = []; let row: string[] = [], f = '', q = false;
  for (let k = 0; k < text.length; k++) {
    const ch = text[k]!;
    if (q) { if (ch === '"' && text[k + 1] === '"') { f += '"'; k++; } else if (ch === '"') q = false; else f += ch; }
    else if (ch === '"') q = true;
    else if (ch === ',') { row.push(f); f = ''; }
    else if (ch === '\n') { row.push(f); out.push(row); row = []; f = ''; }
    else f += ch;
  }
  return out;
}

test('JSheets CSV is rectangular and carries the engine verdict for every golden case', () => {
  const cases = json('golden-verdicts.json') as { h3: string; request: Parameters<typeof traitCells>[1]; verdicts: { dimension: string; verdict: string }[] }[];
  for (const c of cases) {
    const i = data.h3.indexOf(c.h3);
    const [head, ...body] = parseCsv(sheetCsv(data, c.request, [i]));
    assert.ok(body.every(r => r.length === head!.length), `${c.h3} row width`);
    const col = (n: string) => head!.indexOf(n);
    const traits = body.filter(r => r[col('kind')] === 'trait');
    assert.deepEqual(traits.map(r => [r[col('name')], r[col('verdict')]]), c.verdicts.map(v => [v.dimension, v.verdict]), c.h3);
    // missing stays empty with a reason, never a filled number (AGENTS.md rule 3)
    for (const r of traits) if (r[col('verdict')] === 'unknown') assert.ok(r[col('reason')] !== '', `${c.h3} unknown has a reason`);
  }
});

test('burned area names a month with no data instead of dropping it (review of #182, finding 5)', () => {
  const i = data.h3.indexOf('84060abffffffff');
  assert.ok(i >= 0);
  const req = { ...newRequest(data, 'moon', data.runtime.categories[0]!), months: { start: 1, end: 3 } };
  const col = data.monthly.burned_pct!;
  assert.deepEqual([0, 1, 2].map(m => Number.isFinite(col[i * 12 + m]!)), [true, true, false], 'release still has Jan, Feb known and Mar missing');
  assert.deepEqual(burnedInWindow(data, req, i), { max: 0, missing: ['Mar'] });
  assert.deepEqual(burnedInWindow(data, { ...req, months: { start: 3, end: 3 } }, i), { max: null, missing: ['Mar'] });
});

test('every CSV row with an empty value says why (re-check of #182, finding 3)', () => {
  const cat = data.runtime.categories.find(c => c.categoryId === 'robotic-mobility-navigation')!;
  const req = { ...newRequest(data, 'moon', cat), limits: { protected: 100, access: 100000, airport: 100000, slope: 90 } };
  const i = data.h3.indexOf('8401b65ffffffff');
  const [head, ...body] = parseCsv(sheetCsv(data, req, [i]));
  const col = (n: string) => head!.indexOf(n);
  const limit = body.find(r => r[col('kind')] === 'limit' && r[col('name')] === 'protected')!;
  assert.deepEqual([limit[col('verdict')], limit[col('value')], limit[col('reason')], limit[col('earth_column')]], ['unknown', '', 'missing in release', 'protected_pct']);
  for (const r of body) if (r[col('value')] === '') assert.notEqual(r[col('reason')], '', `${r[col('kind')]} ${r[col('name')]} has no value and no reason`);
});
