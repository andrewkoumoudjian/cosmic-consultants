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
  { mismatch: 'gravity', label: 'Gravity', why: 'Earth has 1 g. The Moon has 0.17 g and Mars 0.38 g.' },
  { mismatch: 'pressureRegime', label: 'Air pressure', why: 'Earth has 1 atm of air. The Moon has vacuum; Mars has thin CO2.' },
  { mismatch: 'radiation', label: 'Radiation', why: "Earth's magnetic field and air block radiation the Moon and Mars receive." },
];

/** Plain names and units for the hard limits (engine LIMIT_COLUMNS keys). */
export const LIMIT_TEXT = {
  access: { label: 'Travel to a city', unit: 'min' }, protected: { label: 'Protected land', unit: '%' },
  airport: { label: 'Airport distance', unit: 'km' }, slope: { label: 'Mean slope', unit: 'deg' },
} as const;

/** H3 resolution 4, the release's cell size (h3-js getHexagonAreaAvg(4) = 1,770 km², edge 22.6 km). */
export const CELL_AREA = '≈1,770 km² cell';

/** Objective titles carry an editor's note ("— shortened by us"); show the title alone. */
export function objectiveTitle(o: { title: string }): string {
  return o.title.replace(/\s+—\s+shortened by us$/, '');
}

/** Rule notes start with an internal envelope tag ("moon-south-pole-v0 terrain: …") and say "deg". Show plain text. */
export function cleanNote(text: string | null | undefined): string {
  if (!text || text === 'None') return '';
  const t = text.replace(/^[a-z0-9-]+-v\d+\s+\w+:\s*/, '').replace(/(\d)\s?deg\b/g, '$1°');
  return t.charAt(0).toUpperCase() + t.slice(1);
}

// ---- numbers at the precision a 1,770 km² cell can carry; missing stays null (rule 3) ----------
const finiteNum = (v: number | null | undefined): v is number => v !== null && v !== undefined && Number.isFinite(v);
const noNegZero = (v: number) => (Object.is(v, -0) ? 0 : v);
const fixed = (v: number, d: number) => noNegZero(Number(v.toFixed(d))).toLocaleString('en-US', { minimumFractionDigits: d, maximumFractionDigits: d });
/** Unit shown to people: ° not "deg", nothing for unitless. */
export function unitLabel(unit: string | null | undefined): string {
  return unit === 'deg' ? '°' : unit === 'unitless' || unit === 'flag' || unit === '0/1' || !unit ? '' : ` ${unit === '0-1' ? '%' : unit}`;
}
export function fmt(v: number | null | undefined, unit: string | null | undefined): string | null {
  if (!finiteNum(v)) return null;
  switch (unit) {
    case 'deg': return `${fixed(v, Math.abs(v) < 10 ? 1 : 0)}°`;
    case '%': return `${fixed(v, 0)} %`;
    case '0-1': return `${fixed(v * 100, 0)} %`;
    case 'K': return `${fixed(v - 273.15, 0)} °C`;
    case 'm': return `${noNegZero(Math.round(v / 10) * 10).toLocaleString('en-US')} m`;
    case 'km': return `${fixed(v, 0)} km`;
    case 'min': return v < 60 ? `${fixed(v, 0)} min` : `${fixed(v / 60, v < 600 ? 1 : 0)} h`;
    case 'flag': case '0/1': return v >= 0.5 ? 'yes' : 'no';
    case 'unitless': return fixed(v, 2);
    default: return Number(v.toPrecision(3)).toLocaleString('en-US');
  }
}

/** A few measured facts for one cell, for the globe's cell card. */
export function siteFacts(data: Dataset, i: number): { label: string; value: string | null }[] {
  const y = (c: string) => data.yearly[c]?.[i];
  const lo = fmt(y('elev_min_m'), 'm'), hi = fmt(y('elev_max_m'), 'm');
  return [
    { label: 'Elevation', value: lo && hi ? `${lo.replace(' m', '')}–${hi}` : null },
    { label: 'To a city', value: fmt(y('access_min_median'), 'min') },
    { label: 'To an airport', value: fmt(y('airport_km'), 'km') },
  ];
}

/** Sort cells by one release column. Missing values go last; ties keep the engine's order. */
export function sortByColumn(data: Dataset, indices: number[], column: string, dir: 1 | -1): number[] {
  const v = data.yearly[column];
  const key = (i: number) => { const x = v?.[i]; return x === undefined || !Number.isFinite(x) ? null : x; };
  return indices.map((i, k) => ({ i, k, x: key(i) })).sort((a, b) =>
    a.x === null ? (b.x === null ? a.k - b.k : 1) : b.x === null ? -1 : (a.x - b.x) * dir || a.k - b.k).map(e => e.i);
}

/** Great-circle km between two points (mean Earth radius 6,371 km). */
export function kmBetween(a: { lat: number; lon: number }, b: { lat: number; lon: number }): number {
  const r = Math.PI / 180, dLat = (b.lat - a.lat) * r, dLon = (b.lon - a.lon) * r;
  const h = Math.sin(dLat / 2) ** 2 + Math.cos(a.lat * r) * Math.cos(b.lat * r) * Math.sin(dLon / 2) ** 2;
  return 2 * 6371 * Math.asin(Math.min(1, Math.sqrt(h)));
}

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
  // one decimal (≈11 km): finer would claim a precision a 22 km cell doesn't have
  return `${Math.abs(lat).toFixed(1)}°${lat >= 0 ? 'N' : 'S'} ${Math.abs(lon).toFixed(1)}°${lon >= 0 ? 'E' : 'W'}`;
}

export function num(v: number | null | undefined, digits = 3): string {
  if (v === null || v === undefined || !Number.isFinite(v)) return 'unknown';
  return Number(v.toPrecision(digits)).toLocaleString('en-US', { maximumFractionDigits: 4 });
}

export function bandLabel(r: Pick<Row, 'band' | 'unit'>): string {
  if (!r.band) return 'No accepted band';
  return `${num(r.band.lo, 6)} ≤ x ${r.band.hiStrict ? '<' : '≤'} ${num(r.band.hi, 6)}${unitLabel(r.unit)}`;
}

/** `detail` is the full sentence for the cell card; `short` fits a site-list row. */
export type TraitCell = { dimension: Dimension; priority: 'must' | 'nice'; verdict: Row['verdict']; glyph: string; detail: string; short: string; value: number | null; unit: string | null };

/** One site's per-trait results, straight from engine rows(). */
export function traitCells(data: Dataset, request: PlanRequest, i: number): TraitCell[] {
  return rows(data, request, i).map(r => {
    const shown = r.perMonth ? worstMonthValue(r) : r.value;
    const known = (r.perMonth ?? []).map(m => m.value).filter((v): v is number => v !== null);
    const detail = r.verdict === 'miss' ? `${fmt(r.gap, r.unit) ?? num(r.gap)} ${r.side === 'above' ? 'above' : 'below'} the band`
      : r.verdict === 'unknown' ? r.reason?.text ?? 'unknown'
      : known.length > 1 ? `${fmt(Math.min(...known), r.unit)} – ${fmt(Math.max(...known), r.unit)} over the window` // every month, not one picked
      : fmt(shown, r.unit) ?? num(shown);
    const lo = known.length ? fmt(Math.min(...known), r.unit) : null, hi = known.length ? fmt(Math.max(...known), r.unit) : null;
    const short = r.verdict === 'miss' ? `${fmt(r.gap, r.unit) ?? num(r.gap)} ${r.side === 'above' ? 'over' : 'under'}`
      : r.verdict === 'unknown' ? 'no data'
      : known.length > 1 && lo !== hi ? `${lo} – ${hi}` : fmt(shown, r.unit) ?? num(shown);
    return { dimension: r.dimension, priority: r.priority!, verdict: r.verdict, glyph: GLYPH[r.verdict], detail, short, value: shown, unit: r.unit ?? null };
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
  const lo = fmt(y('elev_min_m'), 'm'), hi = fmt(y('elev_max_m'), 'm');
  return [
    { label: 'Travel to the nearest city, median', value: fmt(y('access_min_median'), 'min') },
    { label: 'Travel, fastest 10 % of the cell', value: fmt(y('access_min_p10'), 'min') },
    { label: 'Nearest paved-runway airport', value: fmt(y('airport_km'), 'km') },
    { label: 'Protected land in the cell', value: fmt(y('protected_pct'), '%') },
    { label: 'Elevation, lowest to highest', value: lo && hi ? `${lo.replace(' m', '')}–${hi}` : null },
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
