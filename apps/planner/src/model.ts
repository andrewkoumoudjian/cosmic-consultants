/**
 * View model between the shared engine and the React screens (ADR-0012).
 * Every verdict here comes from apps/atlas/src/planner/engine.ts. This file only
 * picks, labels and groups. No site score is computed anywhere (AGENTS.md rule 4).
 */
import { LIMIT_COLUMNS, funnelClass, limitRows, months, requirements, rows, search, type Dataset, type Row, type SearchResult } from '../../atlas/src/planner/engine.ts';
import type { Dimension, PlanRequest } from '../../atlas/src/plan-url.ts';

export type Body = 'moon' | 'mars';
export type Category = Dataset['runtime']['categories'][number];
export type FunnelClass = ReturnType<typeof funnelClass>;

export const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
/** Figma site-finder series palette, in order, for compared sites. */
/** Compared-site colours: read on the white page and on the night globe, and stay apart from the verdict colours. */
export const SERIES = ['#12b5a5', '#e2479d', '#6fbf3a'];
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
    const known = (r.perMonth ?? []).map(m => m.value).filter((v): v is number => v !== null);
    const detail = r.verdict === 'miss' ? `gap ${num(r.gap)} ${r.unit ?? ''} ${r.side}`.trim()
      : r.verdict === 'unknown' ? r.reason?.text ?? 'unknown'
      : known.length > 1 ? `${num(Math.min(...known))} – ${num(Math.max(...known))} ${r.unit ?? ''}`.trim() // every month, not one picked
      : `${num(shown)} ${r.unit ?? ''}`.trim();
    return { dimension: r.dimension, priority: r.priority!, verdict: r.verdict, glyph: GLYPH[r.verdict], detail, value: shown };
  });
}

/**
 * The one value to plot for a monthly trait: the worst month for a miss, the month closest to a band
 * edge for a match, and nothing for an unknown window (a known month must not stand in for a missing one).
 */
function worstMonthValue(r: Row): number | null {
  if (r.verdict === 'unknown') return null;
  const pm = (r.perMonth ?? []).filter(m => m.value !== null);
  const miss = pm.filter(m => m.verdict === 'miss').sort((a, b) => b.gap! - a.gap!)[0];
  if (miss) return miss.value;
  if (!r.band) return pm[0]?.value ?? null;
  const margin = (v: number) => Math.min(v - r.band!.lo, r.band!.hi - v);
  return pm.map(m => m.value!).sort((a, b) => margin(a) - margin(b))[0] ?? null;
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

/** Most burned area over the window's months. A month with no data is listed, never dropped (AGENTS.md rule 3). */
export function burnedInWindow(data: Dataset, request: PlanRequest, i: number): { max: number | null; missing: string[] } {
  const col = data.monthly.burned_pct;
  if (!col) return { max: null, missing: months(request).map(m => MONTHS[m - 1]!) };
  const known: number[] = [], missing: string[] = [];
  for (const m of months(request)) { const v = col[i * 12 + m - 1]!; if (Number.isFinite(v)) known.push(v); else missing.push(MONTHS[m - 1]!); }
  return { max: known.length ? Math.max(...known) : null, missing };
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

/**
 * Tidy table for JSheets (or any sheet tool): one row per compared site x trait, then one row per site x
 * logistics measure. Values come straight from engine rows(); missing stays empty with a reason (rule 3).
 */
export function sheetCsv(data: Dataset, request: PlanRequest, sites: number[]): string {
  const head = ['site_h3', 'lat', 'lon', 'kind', 'name', 'priority', 'verdict', 'value', 'unit', 'band_lo', 'band_hi', 'gap', 'side', 'reason', 'earth_column', 'manifest_sha256'];
  const cell = (v: unknown) => {
    // 9 significant digits round-trip a float32 exactly, without printing its float64 tail
    const s = v === null || v === undefined ? '' : typeof v === 'number' ? String(Number(v.toPrecision(9))) : String(v);
    return /[",\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
  };
  const out = [head.join(',')];
  for (const i of sites) {
    const { lat, lon } = latLon(data, i);
    const base = [data.h3[i], lat.toFixed(4), lon.toFixed(4)];
    const tail = [data.manifestHash];
    for (const r of rows(data, request, i)) {
      const shown = r.perMonth ? worstMonthValue(r) : r.value;
      out.push([...base, 'trait', r.dimension, r.priority, r.verdict, shown, r.unit, r.band?.lo, r.band?.hi, r.gap, r.side, r.reason?.text, r.earthColumn, ...tail].map(cell).join(','));
    }
    for (const l of limitRows(data, request, i)) out.push([...base, 'limit', l.limit, 'must', l.outcome, l.value, '', '', l.max, '', '', l.value === null ? 'missing in release' : '', LIMIT_COLUMNS[l.limit], ...tail].map(cell).join(','));
    for (const [col, unit] of [['access_min_median', 'min'], ['airport_km', 'km'], ['protected_pct', '%'], ['elev_mean_m', 'm']] as const) {
      const v = data.yearly[col]?.[i], known = v !== undefined && Number.isFinite(v);
      out.push([...base, 'logistics', col, '', '', known ? v : null, unit, '', '', '', '', known ? '' : 'missing in release', col, ...tail].map(cell).join(','));
    }
  }
  return out.join('\n') + '\n';
}

export function download(name: string, text: string, type: string) {
  const url = URL.createObjectURL(new Blob([text], { type }));
  Object.assign(document.createElement('a'), { href: url, download: name }).click();
  URL.revokeObjectURL(url);
}
