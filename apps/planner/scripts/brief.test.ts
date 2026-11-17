import { test } from 'node:test';
import assert from 'node:assert/strict';
import { brief, type Dataset } from '../../atlas/src/planner/engine.ts';
import type { PlanRequest } from '../../atlas/src/plan-url.ts';
import { plannerBrief, waterCoverWarning, WATER_COVER_GUIDANCE } from '../src/brief.ts';

/** Synthetic export-only fixture; it makes no claim about a real site's water. */
function fixture(water?: number[]): { data: Dataset; request: PlanRequest } {
  const data: Dataset = {
    h3: ['wet-example', 'dry-example', 'missing-example'],
    yearly: { lat: new Float32Array([10, 20, 30]), lon: new Float32Array([40, 50, 60]),
      ...(water ? { water_pct: new Float32Array(water) } : {}) },
    monthly: {}, rules: [],
    objectives: [{ objectiveId: 'LI-5L', body: 'moon', title: 'Synthetic export fixture', requiredDimensions: [], earthTestableComponent: 'Synthetic', notTestableOnEarth: [] }],
    runtime: { numericPolicy: 'published-float32-no-epsilon', qualityWarnings: ['Synthetic source caveat.'], reasonSets: [{}], yearlyReasons: [0, 0, 0], monthlyReasons: [], categories: [], campaigns: [], events: {} },
    manifestHash: 'a'.repeat(64), inputs: [{ path: 'synthetic-input', sha256: 'b'.repeat(64) }],
  };
  return { data, request: { version: 1, body: 'moon', objectiveId: 'LI-5L', missionType: 'robotic', months: { start: 1, end: 1 } } };
}

test('a wet cell retains the screen warning in its saved brief', () => {
  const { data, request } = fixture([95]);
  const text = plannerBrief(data, request, [0], 'Check access.');
  assert.match(text, /Water cover in the cell: 95 %/);
  assert.ok(text.includes(WATER_COVER_GUIDANCE));
  // The old Download brief path loses exactly the evidence this regression checks.
  assert.ok(!brief(data, request, [0], 'Check access.').includes(WATER_COVER_GUIDANCE));
});

test('the screen warning keeps its existing strict boundary and rejects nonfinite values', () => {
  for (const value of [undefined, NaN, Infinity, -Infinity, 0, 25]) assert.equal(waterCoverWarning(value), null);
  assert.equal(waterCoverWarning(25.1), WATER_COVER_GUIDANCE);
});

test('missing water stays explicit instead of becoming a dry cell', () => {
  for (const water of [undefined, [NaN], [Infinity], []]) {
    const { data, request } = fixture(water);
    const text = plannerBrief(data, request, [0], '');
    assert.match(text, /Water cover in the cell: no data/);
    assert.match(text, /Water cover is missing in this release/);
    assert.ok(!text.includes('Surface water cover > 25 %:'));
    assert.doesNotMatch(text, /Water cover in the cell: 0/);
  }
});

test('water context stays with each compared site, not the whole comparison', () => {
  const { data, request } = fixture([95, 0, NaN]);
  const text = plannerBrief(data, request, [0, 1, 2], '');
  const context = text.slice(text.indexOf('## Water-cover context'));
  const wet = context.slice(context.indexOf('### wet-example'), context.indexOf('### dry-example'));
  const dry = context.slice(context.indexOf('### dry-example'), context.indexOf('### missing-example'));
  const missing = context.slice(context.indexOf('### missing-example'));
  assert.ok(wet.includes(WATER_COVER_GUIDANCE));
  assert.match(dry, /Water cover in the cell: 0 %/);
  assert.ok(!dry.includes(WATER_COVER_GUIDANCE));
  assert.match(missing, /Water cover in the cell: no data/);
  assert.ok(!missing.includes('Surface water cover > 25 %:'));
});

test('the export retains the shared engine brief byte for byte, including provenance', () => {
  const { data, request } = fixture([95]);
  const original = brief(data, request, [0], 'A scientist checklist.');
  assert.ok(plannerBrief(data, request, [0], 'A scientist checklist.').startsWith(original));
  assert.equal(plannerBrief(data, request, [], ''), brief(data, request, [], ''));
});
