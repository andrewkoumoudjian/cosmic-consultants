/** Consume the engine's existing release; no new scores, bands or solver runs. */
import { digest } from '../../atlas/src/planner/data.ts';
import type { Dataset } from '../../atlas/src/planner/engine.ts';

export type Axis = { name: string; column: string; unit: string; mode: string; targetValue: number | null };
export type Candidate = { h3: string; lat: number; lon: number; paretoLayer: number; gaps: Record<string, number>; observations: Record<string, number | null> };
export type Campaign = {
  status: string; error?: string; missing_reason?: string; month?: number; alpha?: number;
  thermalBandK?: number[]; weights?: Record<string, number>; cvar?: number; expectedCost?: number;
  certified?: boolean; certificationStatus?: string; certifiedSuboptLe?: number | null;
  numericalSuboptEstimate?: number; screeningExact?: boolean;
  excludedCandidates?: { h3: string; reason: string }[];
};
export type TargetResult = {
  targetId: string; body: 'moon' | 'mars'; axes: Axis[]; frontierSample: Candidate[];
  counts: Record<string, number>; campaignPlan: Campaign; scenarioStatus: string;
  parameters: Record<string, { value: unknown; origin: string; basis: string }>;
  notTestableOnEarth: unknown;
};
export type EngineResults = {
  targets: Record<string, TargetResult>; planetary: Record<string, unknown>[];
  yearly: { columns: Record<string, string>; nullReasons?: Record<string, Record<string, number>> };
  manifestHash: string; files: Record<string, string>;
};
export type EngineLoad = { state: 'loading' } | { state: 'error'; message: string } | { state: 'ready'; data: EngineResults };

export async function loadEngineResults(data: Pick<Dataset, 'manifestHash'>, base = './data/planner-v1/', get: typeof fetch = fetch): Promise<EngineResults> {
  const response = await get(base + 'build-manifest.json');
  if (!response.ok) throw Error('Engine release manifest is unavailable.');
  const bytes = await response.arrayBuffer();
  if (await digest(bytes) !== data.manifestHash) throw Error('The engine release changed. Reload to use one consistent release.');
  const manifest = JSON.parse(new TextDecoder().decode(bytes)) as { files: Record<string, string> };
  const read = async (name: string) => {
    if (!manifest.files[name]) throw Error(`No published hash for ${name}.`);
    const r = await get(base + name);
    if (!r.ok) throw Error(`Engine results unavailable: ${name}.`);
    const b = await r.arrayBuffer();
    if (await digest(b) !== manifest.files[name]) throw Error(`Engine data verification failed: ${name}.`);
    return JSON.parse(new TextDecoder().decode(b));
  };
  const [bundle, planetary, yearly] = await Promise.all([read('pareto-targets.json'), read('planetary-targets.json'), read('yearly/yearly.json')]);
  if (bundle.version !== 1 || !bundle.targets || !Array.isArray(planetary) || !yearly.columns) throw Error('Unsupported engine results format.');
  for (const [id, t] of Object.entries(bundle.targets) as [string, TargetResult][]) {
    if (t.targetId !== id || !['moon', 'mars'].includes(t.body) || !Array.isArray(t.axes) || !Array.isArray(t.frontierSample) || !t.campaignPlan) throw Error('Incomplete engine target results.');
    const seen = new Set<string>();
    for (const c of t.frontierSample) {
      if (seen.has(c.h3) || !Number.isInteger(c.paretoLayer) || c.paretoLayer < 1 || !t.axes.every(a => Number.isFinite(c.gaps[a.name]) && c.gaps[a.name]! >= 0)) throw Error('Invalid engine frontier sample.');
      seen.add(c.h3);
    }
    const plan = t.campaignPlan;
    if (plan.status === 'solved') {
      const weights = Object.values(plan.weights ?? {});
      if (!weights.length || weights.some(w => !Number.isFinite(w) || w < 0) || Math.abs(weights.reduce((a, b) => a + b, 0) - 1) > 1e-6) throw Error('Invalid campaign allocation.');
      if (plan.certified && (plan.certifiedSuboptLe === null || !Number.isFinite(plan.certifiedSuboptLe) || plan.certifiedSuboptLe! < 0)) throw Error('Missing certified campaign bound.');
    }
  }
  return { targets: bundle.targets, planetary, yearly, manifestHash: data.manifestHash, files: manifest.files };
}

export function selectedTarget(engine: EngineResults, body: 'moon' | 'mars', id?: string): TargetResult | undefined {
  if (id && engine.targets[id]?.body === body) return engine.targets[id];
  const preferred = body === 'moon' ? 'moon-feature-shackleton' : 'mars-landing-curiosity';
  return (engine.targets[preferred]?.body === body ? engine.targets[preferred] : undefined) ?? Object.values(engine.targets).find(t => t.body === body);
}

export function targetName(engine: EngineResults, id: string): string {
  const row = engine.planetary.find(p => p.target_id === id);
  return typeof row?.name === 'string' ? row.name : id.replace(/^(moon|mars)-(feature|landing)-/, '').replace(/-/g, ' ');
}

export function campaignAllocations(plan: Campaign, durationDays?: number) {
  return Object.entries(plan.weights ?? {}).map(([key, weight]) => {
    const [h3, suffix] = key.split(':m');
    return { key, h3: h3!, month: suffix === undefined ? plan.month : Number(suffix), weight, days: durationDays === undefined ? null : weight * durationDays };
  }).sort((a, b) => b.weight - a.weight || a.key.localeCompare(b.key));
}

export function engineBrief(engine: EngineResults, target: TargetResult, days?: number): string {
  const plan = target.campaignPlan;
  return ['\n## Planetary target and campaign engine', `Target: ${targetName(engine, target.targetId)} (${target.targetId}).`,
    'Published scenario, not recomputed from edited mission bands or selected pins. Scientific status: partial.',
    `Pareto sample: ${target.frontierSample.length} candidates; ${target.counts.comparable} comparable cells.`,
    ...Object.entries(target.parameters).map(([k, p]) => `- ${k}: ${JSON.stringify(p.value)} (${p.origin}). ${p.basis}`),
    '', '| Cell | Pareto layer | Per-trait gaps |', '|---|---|---|',
    ...target.frontierSample.map(c => `| ${c.h3} | ${c.paretoLayer} | ${target.axes.map(a => `${a.name}: ${c.gaps[a.name]} ${a.unit}`).join('; ')} |`),
    '', `Campaign status: ${plan.status}.`, `Certification: ${plan.certified === true ? 'certified' : 'not certified'} (${plan.certificationStatus ?? 'not available'}).`,
    `Certified objective-gap bound: ${plan.certified ? plan.certifiedSuboptLe : 'not available'}.`,
    `Numerical estimate (not a certificate): ${plan.numericalSuboptEstimate ?? 'not available'}.`,
    ...campaignAllocations(plan, days).map(a => `- ${a.h3}, month ${a.month}: ${a.weight} of field days${a.days === null ? '' : ` (${a.days} of ${days} requested days; proportional illustration only)`}.`),
    ...(plan.excludedCandidates ?? []).map(c => `- Excluded ${c.h3}: ${c.reason}.`),
    '', `Engine manifest SHA256: ${engine.manifestHash}`, `pareto-targets.json SHA256: ${engine.files['pareto-targets.json']}`,
    'Methods: https://github.com/andrewkoumoudjian/cosmic-consultants/tree/main/proofs/Analog',
    'S7: per-trait verdict logic. S9: Pareto layers. S10: campaign optimization and conditional certificates. These proofs do not certify measurements or the browser implementation.', ''].join('\n');
}
