import assert from 'node:assert/strict';
import { test } from 'node:test';
import { readFile } from 'node:fs/promises';
import { createHash } from 'node:crypto';
import { loadEngineResults, selectedTarget, campaignAllocations, engineBrief } from '../src/engine-results.ts';

const base = new URL('../../atlas/public/data/planner-v1/', import.meta.url);
const manifestBytes = await readFile(new URL('build-manifest.json', base));
const hash = createHash('sha256').update(manifestBytes).digest('hex');
const get: typeof fetch = async url => new Response(await readFile(new URL(String(url).replace('/release/', ''), base)));
const engine = await loadEngineResults({ manifestHash: hash }, '/release/', get);

test('loads hash-verified real target results and preserves uncertified solver state', () => {
  assert.equal(Object.keys(engine.targets).length, 4);
  for (const t of Object.values(engine.targets)) {
    assert.equal(t.frontierSample.length, 20);
    assert.equal(t.campaignPlan.status, 'solved');
    assert.equal(t.campaignPlan.certified, false);
    assert.equal(t.campaignPlan.certifiedSuboptLe, null);
    assert.ok(t.axes.some(a => a.name.includes('thermal') || a.name.includes('night')));
  }
});
test('target selection cannot leak a Mars target into a Moon plan', () => {
  assert.equal(selectedTarget(engine, 'moon', 'mars-landing-curiosity')?.body, 'moon');
  assert.equal(selectedTarget(engine, 'mars', 'mars-landing-perseverance')?.targetId, 'mars-landing-perseverance');
});
test('allocation conversion preserves solver shares and distinguishes illustration from a rerun', () => {
  const t = selectedTarget(engine, 'moon')!;
  const allocations = campaignAllocations(t.campaignPlan, 14);
  assert.ok(Math.abs(allocations.reduce((s, a) => s + a.days!, 0) - 14) < 1e-8);
  const exported = engineBrief(engine, t, 14);
  assert.match(exported, /not recomputed from edited mission bands/);
  assert.match(exported, /not certified/);
  assert.match(exported, /Certified objective-gap bound: not available/);
  assert.match(exported, new RegExp(hash));
  assert.match(exported, /thermal_cold_gap_k/);
});
test('a changed manifest is rejected before any engine file is consumed', async () => {
  await assert.rejects(loadEngineResults({ manifestHash: '0'.repeat(64) }, '/release/', get), /engine release changed/);
});
test('a tampered frontier is rejected by its published hash', async () => {
  const altered: typeof fetch = async url => String(url).endsWith('pareto-targets.json') ? new Response('{}') : get(url);
  await assert.rejects(loadEngineResults({ manifestHash: hash }, '/release/', altered), /verification failed/);
});
test('an unavailable engine file is explicit rather than a silent fallback', async () => {
  const missing: typeof fetch = async url => String(url).endsWith('planetary-targets.json') ? new Response('missing', { status: 404 }) : get(url);
  await assert.rejects(loadEngineResults({ manifestHash: hash }, '/release/', missing), /Engine results unavailable/);
});
