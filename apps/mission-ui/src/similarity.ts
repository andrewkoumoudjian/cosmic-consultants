/**
 * Per-trait closeness to the user's band, 0–100, for the "Top 3 Sites — Scientific Similarity" chart (owner, 2026-11-15).
 *
 * One number per trait, never combined across traits (AGENTS.md rule 4: the per-dimension vector, no site score).
 *   - inside the band            → 100
 *   - outside it, by the engine's gap g → 100 × (1 − g / S), where S is the farthest any cell in the release sits from
 *     that band on that trait (so 0 = as far off as anywhere on Earth). Each trait uses its own unit and its own S.
 *   - no band, or no observation → unavailable (null). Never 0 (rule 3: missing stays missing).
 * This is a display transform of the engine's verdict and gap; it does not change matching or ranking.
 */
import { LIMIT_COLUMNS, limitRows, rows, type Dataset, type Row } from '../../atlas/src/planner/engine.ts';
import type { PlanRequest } from '../../atlas/src/plan-url.ts';
import { columnBounds, spiderValue } from './model.ts';

export type Closeness = {
  dimension: Row['dimension']; unit: string | null; priority: Row['priority'];
  score: number | null;          // 0–100, or null when unavailable
  measured: number | null;       // the value the verdict used (worst month for monthly traits)
  why?: string;                  // why it is unavailable
};

export function closeness(data: Dataset, request: PlanRequest, i: number): Closeness[] {
  return rows(data, request, i).map(r => {
    const base = { dimension: r.dimension, unit: r.unit, priority: r.priority, measured: spiderValue(r).value };
    if (!r.band) return { ...base, score: null, why: r.earthColumn ? 'no accepted band' : 'no Earth data for this trait' };
    if (r.verdict === 'unknown') return { ...base, score: null, why: r.reason?.text ?? 'no data' };
    if (r.verdict === 'match') return { ...base, score: 100 };
    const b = r.earthColumn ? columnBounds(data, r.earthColumn, r.table) : null;
    const far = b ? Math.max(r.band.lo - b.min, b.max - r.band.hi) : 0;
    if (!(far > 0) || r.gap === undefined) return { ...base, score: null, why: 'no Earth range to scale against' };
    return { ...base, score: Math.max(0, Math.min(100, 100 * (1 - r.gap / far))) };
  });
}

/**
 * Hard limits the user set in step 3, as extra spokes (owner, 2026-11-15: the Moon has at most two traits with Earth
 * data, so without these the radar can never draw). Same rule as a trait whose band is [0, limit]: 100 within the
 * limit; past it, the score falls with the overshoot, reaching 0 at the largest value anywhere on Earth. No limit set:
 * no spoke. No data: unavailable, never 0.
 */
const LIMIT_AXIS = {
  access: { label: 'Travel to a city', unit: 'min' }, airport: { label: 'Airport distance', unit: 'km' },
  slope: { label: 'Mean slope', unit: 'deg' }, protected: { label: 'Protected land', unit: '%' },
} as const;

export type Axis = { dimension: Row['dimension']; band: { lo: number; hi: number; hiStrict: boolean } | null; unit: string | null; priority: Row['priority'] };

export function limitAxes(request: PlanRequest): Axis[] {
  return (Object.keys(LIMIT_COLUMNS) as (keyof typeof LIMIT_COLUMNS)[]).filter(k => request.limits?.[k] !== undefined)
    .map(k => ({ dimension: LIMIT_AXIS[k].label as Row['dimension'], band: { lo: 0, hi: request.limits![k]!, hiStrict: false }, unit: LIMIT_AXIS[k].unit, priority: 'must' as Row['priority'] }));
}

export function limitCloseness(data: Dataset, request: PlanRequest, i: number): Closeness[] {
  return limitRows(data, request, i).map(l => {
    const base = { dimension: LIMIT_AXIS[l.limit].label as Row['dimension'], unit: LIMIT_AXIS[l.limit].unit, priority: 'must' as Row['priority'], measured: l.value };
    if (l.value === null) return { ...base, score: null, why: 'no data' };
    if (l.outcome === 'pass') return { ...base, score: 100 };
    const b = columnBounds(data, LIMIT_COLUMNS[l.limit], 'L1');
    const far = b ? b.max - l.max : 0;
    if (!(far > 0)) return { ...base, score: null, why: 'no Earth range to scale against' };
    return { ...base, score: Math.max(0, Math.min(100, 100 * (1 - (l.value - l.max) / far))) };
  });
}
