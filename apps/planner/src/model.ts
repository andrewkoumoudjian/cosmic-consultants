/**
 * View model between the shared engine and the React screens (ADR-0012).
 * Every verdict here comes from apps/atlas/src/planner/engine.ts. This file only
 * picks, labels and groups. No site score is computed anywhere (AGENTS.md rule 4).
 */
import { funnelClass, limitRows, months, requirements, rows, search, type Dataset, type Row, type SearchResult } from '../../atlas/src/planner/engine.ts';
import type { Dimension, PlanRequest } from '../../atlas/src/plan-url.ts';

export type Body = 'moon' | 'mars';
export type Category = Dataset['runtime']['categories'][number];
export type FunnelClass = ReturnType<typeof funnelClass>;

export const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
/** Figma site-finder series palette, in order, for compared sites. */
export const SERIES = ['#3987e5', '#d95926', '#199e70'];
export const MAX_COMPARE = 3; // the plan-request contract allows at most three pins

export const DIMENSION_LABEL: Record<string, string> = {
  terrain: 'Terrain', thermal: 'Thermal', illumination: 'Illumination', dustProcess: 'Dust process',
  waterIce: 'Water ice', surfaceMaterial: 'Surface material', subsurface: 'Subsurface', operations: 'Operations',
};
export const COLUMN_LABEL: Record<string, string> = {
  slope_mean_deg: 'Mean slope', barren_pct: 'Barren ground share', sun_noon_elev_deg: 'Noon sun elevation',
  permafrost_pct: 'Permafrost share', polar_night: 'Polar night', lst_night_k: 'Night land-surface temperature',
  dust_aod: 'Dust aerosol optical depth',
};
export const BREAKDOWNS = [
  { mismatch: 'gravity', why: 'Earth has 1 g. The Moon has 0.17 g and Mars 0.38 g.' },
  { mismatch: 'pressureRegime', why: 'Earth has 1 atm of air. The Moon has vacuum; Mars has thin CO2.' },
  { mismatch: 'radiation', why: "Earth's magnetic field and air block radiation the Moon and Mars receive." },
];

export function objectivesFor(data: Dataset, body: Body) {
  return data.objectives.filter(o => o.body === body);
}

/** Traits a category needs that an objective of this body can actually test: a band and an Earth column. */
export function supportedTraits(data: Dataset, objectiveId: string, category: Category): Dimension[] {
  const objective = data.objectives.find(o => o.objectiveId === objectiveId);
  if (!objective) return [];
  return objective.requiredDimensions.filter(d => category.traits.includes(d) && data.rules.some(r =>
    (r as typeof r & { objectiveId?: string }).objectiveId === objectiveId && r.dimension === d && r.band !== null && r.earthColumn !== null));
}

/** The body's objective sharing the most testable traits with the category; ties keep data order. */
export function pickObjective(data: Dataset, body: Body, category: Category): { objectiveId: string; supported: Dimension[] } {
  let best = { objectiveId: objectivesFor(data, body)[0]!.objectiveId, supported: [] as Dimension[] };
  for (const o of objectivesFor(data, body)) {
    const supported = supportedTraits(data, o.objectiveId, category);
    if (supported.length > best.supported.length) best = { objectiveId: o.objectiveId, supported };
  }
  return best;
}

/** Same defaults as the atlas planner: banded traits with a column are required, the rest preferred. */
export function withDefaultPriorities(data: Dataset, request: PlanRequest): PlanRequest {
  const base = { ...request };
  delete base.must; delete base.nice; delete base.bandEdits; delete base.pins;
  const rs = requirements(data, base);
  const must = rs.filter(r => r.band !== null && r.earthColumn !== null && r.priority !== 'nice').map(r => r.dimension);
  return { ...base, must, nice: rs.filter(r => !must.includes(r.dimension)).map(r => r.dimension), sortBy: rs[0]?.dimension };
}

export function newRequest(data: Dataset, body: Body, category: Category): PlanRequest {
  const { objectiveId } = pickObjective(data, body, category);
  return withDefaultPriorities(data, {
    version: 1, body, objectiveId, category: category.categoryId, missionType: 'robotic',
    months: { start: 1, end: 1 }, durationDays: 14, teamSize: 6, top: 50,
  });
}

export function latLon(data: Dataset, i: number): { lat: number; lon: number } {
  return { lat: data.yearly.lat![i]!, lon: data.yearly.lon![i]! };
}

export function coordLabel(data: Dataset, i: number): string {
  const { lat, lon } = latLon(data, i);
  return `${Math.abs(lat).toFixed(2)}°${lat >= 0 ? 'N' : 'S'} ${Math.abs(lon).toFixed(2)}°${lon >= 0 ? 'E' : 'W'}`;
}

export function num(v: number | null | undefined, digits = 3): string {
  if (v === null || v === undefined || !Number.isFinite(v)) return 'unknown';
  return Number(v.toPrecision(digits)).toLocaleString('en-US', { maximumFractionDigits: 4 });
}

export function bandLabel(r: Pick<Row, 'band' | 'unit'>): string {
  if (!r.band) return 'No accepted band';
  return `${num(r.band.lo, 6)} – ${num(r.band.hi, 6)}${r.band.hiStrict ? ' (upper excluded)' : ''}${r.unit ? ' ' + r.unit : ''}`;
}

export type TraitCell = { dimension: Dimension; priority: 'must' | 'nice'; verdict: Row['verdict']; glyph: string; detail: string; value: number | null };

/** One site's per-trait results, straight from engine rows(). */
export function traitCells(data: Dataset, request: PlanRequest, i: number): TraitCell[] {
  return rows(data, request, i).map(r => {
    const shown = r.perMonth ? worstMonthValue(r) : r.value;
    const detail = r.verdict === 'miss' ? `gap ${num(r.gap)} ${r.unit ?? ''} ${r.side}`.trim()
      : r.verdict === 'unknown' ? r.reason?.text ?? 'unknown' : `${num(shown)} ${r.unit ?? ''}`.trim();
    return { dimension: r.dimension, priority: r.priority!, verdict: r.verdict, glyph: GLYPH[r.verdict], detail, value: shown };
  });
}

function worstMonthValue(r: Row): number | null {
  const pm = r.perMonth ?? [];
  const miss = pm.filter(m => m.verdict === 'miss').sort((a, b) => b.gap! - a.gap!)[0];
  return (miss ?? pm.find(m => m.value !== null) ?? pm[0])?.value ?? null;
}

export const GLYPH: Record<Row['verdict'], string> = { match: '✓', miss: '✕', unknown: '?' };
export const CLASS_TEXT: Record<FunnelClass, string> = {
  allMatch: 'All required traits match',
  noMissSomeUnknown: 'No misses; some required traits unknown',
  someMiss: 'Misses a required trait',
};

/** Funnel class per calendar month, for the season strip. */
export function seasonStrip(data: Dataset, request: PlanRequest, i: number): FunnelClass[] {
  return MONTHS.map((_, m) => funnelClass(rows(data, { ...request, months: { start: m + 1, end: m + 1 } }, i)));
}

/** The engine's funnel class for one site over the whole window. */
export function siteClass(data: Dataset, request: PlanRequest, i: number): FunnelClass {
  return funnelClass(rows(data, request, i));
}

export function runSearch(data: Dataset, request: PlanRequest): SearchResult {
  return search(data, request);
}

export function siteLimits(data: Dataset, request: PlanRequest, i: number) {
  return limitRows(data, request, i);
}

export function monthWindowLabel(request: PlanRequest): string {
  return months(request).map(m => MONTHS[m - 1]).join(', ');
}

export function logisticsFacts(data: Dataset, i: number) {
  const y = (c: string) => data.yearly[c]?.[i];
  return [
    { label: 'Travel time to nearest city (median)', value: num(y('access_min_median')), unit: 'min' },
    { label: 'Travel time, fastest 10%', value: num(y('access_min_p10')), unit: 'min' },
    { label: 'Nearest paved-runway airport', value: num(y('airport_km')), unit: 'km' },
    { label: 'Protected land in the cell', value: num(y('protected_pct')), unit: '%' },
    { label: 'Mean elevation', value: num(y('elev_mean_m'), 4), unit: 'm' },
  ];
}

export function hazardFacts(data: Dataset, i: number) {
  const events = data.runtime.events[data.h3[i]!] ?? [];
  const byCategory = new Map<string, Record<string, unknown>[]>();
  for (const e of events) {
    const k = String(e.category ?? 'other');
    byCategory.set(k, [...(byCategory.get(k) ?? []), e]);
  }
  return { events, byCategory, steep: data.yearly.slope_frac_gt30?.[i] ?? null };
}
