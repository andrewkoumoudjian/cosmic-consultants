// #185: funnel warnings follow the resolved priorities, not the URL's must list.
// Synthetic rules only; no observations. Run: npm test
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { requirements, type Dataset, type Rule } from '../src/planner/engine.ts';
import { priorityNotices } from '../src/planner/notices.ts';
import type { PlanRequest } from '../src/plan-url.ts';

// Mirrors the trait map's OP-5LM shape: terrain nice with a band, surfaceMaterial
// with a band and no priority, dust and thermal with no band and no priority.
const rules = [
  { dimension: 'terrain', table: 'L1', earthColumn: 'slope_mean_deg', unit: 'deg', band: { lo: 0, hi: 5 }, origin: 'target', priority: 'nice' },
  { dimension: 'surfaceMaterial', table: 'L1', earthColumn: 'barren_pct', unit: '%', band: { lo: 50, hi: 100 }, origin: 'team' },
  { dimension: 'dustProcess', table: 'L1m', earthColumn: 'dust_aod', unit: 'unitless', band: null, origin: 'target' },
  { dimension: 'thermal', table: 'L1m', earthColumn: 'lst_night_k', unit: 'K', band: null, origin: 'target' },
].map(r => ({ objectiveId: 'OP-5LM', ...r })) as unknown as Rule[];
const data = {
  h3: [], yearly: {}, monthly: {}, rules, manifestHash: '', inputs: [],
  objectives: [{ objectiveId: 'OP-5LM', body: 'mars', title: 'SYNTHETIC', requiredDimensions: ['terrain', 'surfaceMaterial', 'dustProcess', 'thermal'], earthTestableComponent: '', notTestableOnEarth: [] }],
  runtime: { numericPolicy: '', qualityWarnings: [], reasonSets: [{}], yearlyReasons: [], monthlyReasons: [], categories: [], campaigns: [], events: {} },
} as unknown as Dataset;
const link = (extra: Partial<PlanRequest> = {}): PlanRequest =>
  ({ version: 1, body: 'mars', objectiveId: 'OP-5LM', missionType: 'robotic', months: { start: 6, end: 8 }, ...extra });

test('a link with no must= does not claim that nothing filters when trait-map defaults are required', () => {
  const notes = priorityNotices(requirements(data, link()));
  assert.ok(!notes.some(n => n.startsWith('All requirements are preferred')), notes.join(' | '));
  assert.equal(notes.length, 1);
  assert.match(notes[0]!, /Required with no test band: dustProcess, thermal\./);
});

test('all-preferred requests still get the "nothing filters" warning', () => {
  const notes = priorityNotices(requirements(data, link({ nice: ['terrain', 'surfaceMaterial', 'dustProcess', 'thermal'] })));
  assert.deepEqual(notes, ['All requirements are preferred: no trait filters the results.']);
});

test('the start-page defaults (unbanded traits preferred) give no warning', () => {
  const notes = priorityNotices(requirements(data, link({ must: ['surfaceMaterial'], nice: ['terrain', 'dustProcess', 'thermal'] })));
  assert.deepEqual(notes, []);
});

test('a required trait with a band but no Earth column is flagged too', () => {
  const notes = priorityNotices([{ dimension: 'subsurface', priority: 'must', band: { lo: 0, hi: 1 }, earthColumn: null }]);
  assert.match(notes[0]!, /Required with no test band: subsurface\./);
});
