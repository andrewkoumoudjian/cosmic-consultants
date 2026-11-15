// Workflow acceptance cases C02–C11 (docs/qa/WORKFLOW-ACCEPTANCE.md, #136),
// run against the browser planner engine with synthetic inputs (#165).
//
// Every value below is INVENTED test input, not an observation or a site
// claim. A pass here is a synthetic engine pass only: it does not satisfy the
// real-data release cases (R01–R05) or the UI cases (C01, C12–C15).
// Run: npm test
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { Ajv2020 } from 'ajv/dist/2020.js';
import addFormats from 'ajv-formats';
import {
  rows, funnelClass, limitRows, search, paretoLayers, months,
  type Dataset, type Rule, type Objective, type Row,
} from '../src/planner/engine.ts';
import { decodePlan, encodePlan, type PlanRequest, type Dimension } from '../src/plan-url.ts';

const OBJ = 'SYN-1';
type Cell = number | null;

/** Synthetic dataset. Yearly columns: one value per site. Monthly columns: one 12-value array per site. */
function dataset(o: {
  dims: Dimension[];
  rules: Partial<Rule>[];
  yearly?: Record<string, Cell[]>;
  monthly?: Record<string, Cell[][]>;
  reasonSets?: Record<string, string>[];
  yearlyReasons?: number[];
  monthlyReasons?: number[];
}): Dataset {
  const n = Object.values(o.yearly ?? {})[0]?.length ?? Object.values(o.monthly ?? {})[0]?.length ?? 0;
  const f32 = (xs: Cell[]) => Float32Array.from(xs, (x) => (x === null ? NaN : x));
  const objective: Objective = {
    objectiveId: OBJ, body: 'mars', title: 'Synthetic acceptance objective', requiredDimensions: o.dims,
    earthTestableComponent: 'synthetic', notTestableOnEarth: [{ mismatch: 'gravity', why: 'synthetic' }],
  };
  return {
    h3: Array.from({ length: n }, (_, i) => `syn-${String.fromCharCode(65 + i)}`),
    yearly: Object.fromEntries(Object.entries(o.yearly ?? {}).map(([k, v]) => [k, f32(v)])),
    monthly: Object.fromEntries(Object.entries(o.monthly ?? {}).map(([k, v]) => [k, f32(v.flat())])),
    objectives: [objective],
    rules: o.rules.map((r) => ({ objectiveId: OBJ, table: 'L1', unit: null, origin: 'team', ...r }) as Rule),
    runtime: {
      numericPolicy: 'synthetic', qualityWarnings: [], reasonSets: o.reasonSets ?? [{}],
      yearlyReasons: o.yearlyReasons ?? new Array(n).fill(0), monthlyReasons: o.monthlyReasons ?? new Array(n * 12).fill(0),
      categories: [], campaigns: [], events: {},
    },
    manifestHash: 'synthetic', inputs: [],
  };
}
const request = (extra: Partial<PlanRequest> = {}): PlanRequest =>
  ({ version: 1, body: 'mars', objectiveId: OBJ, missionType: 'robotic', months: { start: 6, end: 8 }, ...extra });
/** 12 monthly values, null except the given months. */
const year = (byMonth: Record<number, Cell>): Cell[] => Array.from({ length: 12 }, (_, m) => byMonth[m + 1] ?? null);
const ids = (d: Dataset, idx: number[]) => idx.map((i) => d.h3[i]!).sort();

const terrain: Partial<Rule> = { dimension: 'terrain', earthColumn: 'slope_mean_deg', unit: 'deg', band: { lo: 0, hi: 5 } };
const thermal: Partial<Rule> = { dimension: 'thermal', table: 'L1m', earthColumn: 'lst_night_k', unit: 'K', band: { lo: 0, hi: 10 } };

test('C02: must terrain [0,5] on 5 / 6 / null gives match / miss gap 1 above / unknown with reason', () => {
  const d = dataset({
    dims: ['terrain'], rules: [terrain], yearly: { slope_mean_deg: [5, 6, null] },
    reasonSets: [{}, { slope_mean_deg: 'synthetic: no DEM tile' }], yearlyReasons: [0, 0, 1],
  });
  const req = request({ must: ['terrain'] });
  const [a, b, c] = [0, 1, 2].map((i) => rows(d, req, i)[0]!) as [Row, Row, Row];
  assert.equal(a.verdict, 'match'); assert.equal(a.value, 5); assert.equal(a.gap, undefined);
  assert.deepEqual([b.verdict, b.gap, b.side, b.unit], ['miss', 1, 'above', 'deg']);
  assert.equal(c.verdict, 'unknown'); assert.equal(c.value, null, 'null is not zero');
  assert.equal(c.reason?.text, 'synthetic: no DEM tile');
  assert.deepEqual([0, 1, 2].map((i) => funnelClass(rows(d, req, i))), ['allMatch', 'someMiss', 'noMissSomeUnknown']);
  const s = search(d, req);
  assert.deepEqual(s.counts, { land: 3, withinLimits: 3, matches: 1, misses: 1, unknown: 1 });
  assert.deepEqual(ids(d, s.indices), ['syn-A'], 'unknown is never counted as a match');
});

test('C03: [0,5) via hiStrict turns 5 into a zero-gap miss that validates against site-plan.schema.json', () => {
  const d = dataset({ dims: ['terrain'], rules: [terrain], yearly: { slope_mean_deg: [5] } });
  assert.equal(rows(d, request({ must: ['terrain'] }), 0)[0]!.verdict, 'match');
  const req = request({ must: ['terrain'], bandEdits: [{ dimension: 'terrain', lo: 0, hi: 5, hiStrict: true }] });
  const row = rows(d, req, 0)[0]!;
  assert.deepEqual([row.verdict, row.gap, row.side, row.origin], ['miss', 0, 'above', 'user']);
  assert.equal(funnelClass([row]), 'someMiss');
  assert.equal(search(d, req).counts.misses, 1, 'the funnel agrees with the row');
  const ajv = new Ajv2020({ strict: false });
  addFormats.default ? addFormats.default(ajv) : (addFormats as unknown as (a: Ajv2020) => void)(ajv);
  const contract = (f: string) => JSON.parse(readFileSync(resolve(import.meta.dirname, '../../../contracts', f), 'utf8'));
  ajv.addSchema(contract('plan-request.schema.json')).addSchema(contract('site-plan.schema.json'));
  const validate = ajv.compile({ $ref: 'https://cosmic-consultants.dev/contracts/site-plan.schema.json#/$defs/verdictRow' });
  assert.ok(validate(row), JSON.stringify(validate.errors));
  const { gap: _gap, ...noGap } = row;
  assert.equal(validate(noGap), false, 'the validator really checks: a miss without its gap is rejected');
});

test('C04: known value with a null band, and a rule with no Earth column, stay unknown with an applicable reason', () => {
  const d = dataset({
    dims: ['terrain', 'subsurface'],
    rules: [{ ...terrain, band: null }, { dimension: 'subsurface', table: null, earthColumn: null, unit: null, band: null }],
    yearly: { slope_mean_deg: [3] },
  });
  const [noBand, noColumn] = rows(d, request({ must: ['terrain', 'subsurface'] }), 0);
  assert.equal(noBand!.verdict, 'unknown'); assert.equal(noBand!.value, 3); assert.equal(noBand!.band, null);
  assert.equal(noBand!.reason?.code, 'no-band');
  assert.equal(noColumn!.verdict, 'unknown'); assert.equal(noColumn!.value, null);
  // Today's only column-less rule (SE-3LM subsurface) also has no band, so it reads "No accepted band."; see C04b.
  assert.equal(noColumn!.reason?.code, 'no-band');
  assert.equal(noColumn!.gap, undefined); assert.equal(noBand!.gap, undefined);
  assert.equal(funnelClass([noBand!, noColumn!]), 'noMissSomeUnknown');
});

test('C04b: an Earth-unavailable rule that still has a band is explained as a missing column, not a missing observation', { todo: 'fails on main: tracked in #166' }, () => {
  const d = dataset({
    dims: ['subsurface'],
    rules: [{ dimension: 'subsurface', table: null, earthColumn: null, unit: 'm', band: { lo: 0, hi: 1 } }],
    yearly: { slope_mean_deg: [3] },
  });
  const row = rows(d, request({ must: ['subsurface'] }), 0)[0]!;
  assert.equal(row.verdict, 'unknown');
  assert.equal(row.reason?.code, 'no-earth-column');
});

test('C05: monthly must thermal [0,10]: 5/null/11 miss (gap 1), 5/null/6 unknown, 5/6/7 match; months kept', () => {
  const d = dataset({
    dims: ['thermal'], rules: [thermal],
    monthly: { lst_night_k: [year({ 6: 5, 7: null, 8: 11 }), year({ 6: 5, 7: null, 8: 6 }), year({ 6: 5, 7: 6, 8: 7 })] },
  });
  const req = request({ must: ['thermal'] });
  const r = [0, 1, 2].map((i) => rows(d, req, i)[0]!);
  assert.deepEqual(r.map((x) => x.verdict), ['miss', 'unknown', 'match']);
  assert.deepEqual([r[0]!.gap, r[0]!.side], [1, 'above']);
  for (const x of r) { assert.deepEqual(x.perMonth!.map((m) => m.month), [6, 7, 8]); assert.equal(x.value, null); }
  assert.deepEqual(r[0]!.perMonth!.map((m) => m.verdict), ['match', 'unknown', 'miss']);
  assert.deepEqual(search(d, req).counts, { land: 3, withinLimits: 3, matches: 1, misses: 1, unknown: 1 });
});

test('C06: months 11-2 wrap the year and use January, not June; 6-8 uses June only of the two', () => {
  const d = dataset({ dims: ['thermal'], rules: [thermal], monthly: { lst_night_k: [year({ 11: 1, 12: 1, 1: 50, 2: 1, 6: 60, 7: 1, 8: 1 })] } });
  const winter = request({ must: ['thermal'], months: { start: 11, end: 2 } });
  assert.deepEqual(months(winter), [11, 12, 1, 2]);
  const w = rows(d, winter, 0)[0]!;
  assert.deepEqual(w.perMonth!.map((m) => [m.month, m.verdict]), [[11, 'match'], [12, 'match'], [1, 'miss'], [2, 'match']]);
  assert.equal(w.gap, 40);
  const summer = rows(d, request({ must: ['thermal'] }), 0)[0]!;
  assert.deepEqual(summer.perMonth!.map((m) => [m.month, m.verdict]), [[6, 'miss'], [7, 'match'], [8, 'match']]);
  assert.equal(summer.gap, 50, 'gap is June\'s own, not an annual value');
});

test('C07: access cap 240 on 240 / 241 / null is pass / fail / unknown; only the known fail is filtered', () => {
  const d = dataset({ dims: ['terrain'], rules: [terrain], yearly: { slope_mean_deg: [1, 1, 1], access_min_median: [240, 241, null] } });
  const req = request({ must: ['terrain'], limits: { access: 240 } });
  assert.deepEqual([0, 1, 2].map((i) => limitRows(d, req, i)[0]!.outcome), ['pass', 'fail', 'unknown']);
  assert.equal(limitRows(d, req, 2)[0]!.value, null);
  const s = search(d, req);
  assert.equal(s.counts.withinLimits, 2);
  assert.deepEqual(ids(d, s.indices), ['syn-A', 'syn-C'], 'unknown access is kept, not filtered');
});

test('C08: moving an out-of-band terrain rule from must to nice keeps the miss visible but stops it disqualifying', () => {
  const d = dataset({
    dims: ['terrain', 'thermal'], rules: [terrain, thermal],
    yearly: { slope_mean_deg: [9] }, monthly: { lst_night_k: [year({ 6: 5, 7: 5, 8: 5 })] },
  });
  const must = request({ must: ['terrain', 'thermal'] }), nice = request({ must: ['thermal'], nice: ['terrain'] });
  const before = rows(d, must, 0), after = rows(d, nice, 0);
  assert.deepEqual([before[0]!.priority, before[0]!.verdict, before[0]!.gap], ['must', 'miss', 4]);
  assert.deepEqual([after[0]!.priority, after[0]!.verdict, after[0]!.gap], ['nice', 'miss', 4]);
  assert.equal(funnelClass(before), 'someMiss'); assert.equal(funnelClass(after), 'allMatch');
  assert.equal(search(d, must).counts.matches, 0); assert.equal(search(d, nice).counts.matches, 1);
});

test('C09: tightening [0,5] to [0,4], then adding a must rule, only ever shrinks the surviving set', () => {
  const slopes = [0, 1, 2, 3, 3.5, 4, 4.5, 5, 5.5, null];
  const nights = slopes.map((_, i) => year({ 6: i % 3 === 0 ? 20 : 5, 7: 5, 8: i === 4 ? null : 5 }));
  const d = dataset({ dims: ['terrain', 'thermal'], rules: [terrain, thermal], yearly: { slope_mean_deg: slopes }, monthly: { lst_night_k: nights } });
  const s1 = new Set(ids(d, search(d, request({ must: ['terrain'], nice: ['thermal'] })).indices));
  const s2 = new Set(ids(d, search(d, request({ must: ['terrain'], nice: ['thermal'], bandEdits: [{ dimension: 'terrain', lo: 0, hi: 4 }] })).indices));
  const s3 = new Set(ids(d, search(d, request({ must: ['terrain', 'thermal'], bandEdits: [{ dimension: 'terrain', lo: 0, hi: 4 }] })).indices));
  for (const x of s2) assert.ok(s1.has(x), `${x} appeared after tightening`);
  for (const x of s3) assert.ok(s2.has(x), `${x} appeared after adding a must rule`);
  assert.deepEqual([...s1], ['syn-A', 'syn-B', 'syn-C', 'syn-D', 'syn-E', 'syn-F', 'syn-G', 'syn-H']);
  assert.deepEqual([...s2], ['syn-A', 'syn-B', 'syn-C', 'syn-D', 'syn-E', 'syn-F']);
  assert.deepEqual([...s3], ['syn-B', 'syn-C', 'syn-F'], 'A/D miss thermal in June; E has an unknown August');
});

test('C10: gap vectors (1,3) / (3,1) / (4,4): A and B are layer 1, C is later; no gap sum decides', () => {
  assert.deepEqual(paretoLayers([[1, 3], [3, 1], [4, 4]]), [1, 1, 2]);
  // Through the full search, with both rules nice so all three are eligible; D fails a must rule and stays filtered.
  const crater: Partial<Rule> = { dimension: 'surfaceMaterial', earthColumn: 'barren_pct', unit: '%', band: { lo: 0, hi: 0 } };
  const ops: Partial<Rule> = { dimension: 'operations', earthColumn: 'airport_km', unit: 'km', band: { lo: 0, hi: 0 } };
  const d = dataset({
    dims: ['terrain', 'surfaceMaterial', 'operations'], rules: [terrain, crater, ops],
    yearly: { slope_mean_deg: [1, 1, 1, 9], barren_pct: [1, 3, 4, 0], airport_km: [3, 1, 4, 0] },
  });
  const s = search(d, request({ must: ['terrain'], nice: ['surfaceMaterial', 'operations'] }));
  assert.deepEqual([0, 1, 2].map((i) => s.layers.get(i)), [1, 1, 2]);
  assert.equal(s.layers.has(3), false, 'a must-miss site is filtered, not ranked');
  assert.deepEqual(s.indices.slice(2), [2]);
  // A sum of gaps would rank (2,2) ahead of both (1,3) and (3,1); Pareto keeps all three on layer 1.
  assert.deepEqual(paretoLayers([[1, 3], [3, 1], [2, 2]]), [1, 1, 1]);
});

test('C11: must/strict band/wrapping months/top survive the URL; duplicate body and month 13 are rejected', () => {
  const q = '?body=mars&obj=OP-5LM&type=robotic&months=11-2&must=terrain&band=terrain:0..5%3C&top=20';
  const r = decodePlan(q);
  assert.ok(r.ok, r.ok ? '' : r.errors.join('; '));
  if (!r.ok) return;
  assert.deepEqual(r.plan.months, { start: 11, end: 2 });
  assert.deepEqual(r.plan.must, ['terrain']);
  assert.deepEqual(r.plan.bandEdits, [{ dimension: 'terrain', lo: 0, hi: 5, hiStrict: true }]);
  assert.equal(r.plan.top, 20);
  const again = decodePlan('?' + encodePlan(r.plan));
  assert.ok(again.ok); if (again.ok) assert.deepEqual(again.plan, r.plan);
  for (const bad of ['?body=mars&body=moon&obj=OP-5LM&type=robotic&months=6-8', '?body=mars&obj=OP-5LM&type=robotic&months=13-2']) {
    const x = decodePlan(bad);
    assert.equal(x.ok, false, `${bad} must not decode to defaults`);
  }
});
