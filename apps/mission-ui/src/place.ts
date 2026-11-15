/**
 * Plain descriptions of a cell until real place names land (#203). Every word comes from the cell's own
 * release values (latitude, land cover, elevation); nothing is looked up or guessed.
 */
import type { Dataset } from '../../atlas/src/planner/engine.ts';
import { fmt, kmBetween, latLon } from './model.ts';

const val = (data: Dataset, col: string, i: number) => { const v = data.yearly[col]?.[i]; return v !== undefined && Number.isFinite(v) ? v : null; };

export function zone(lat: number): string {
  const a = Math.abs(lat), n = lat >= 0;
  return a >= 66.5 ? (n ? 'Arctic' : 'Antarctic') : a >= 55 ? (n ? 'Subarctic' : 'Subantarctic') : a >= 35 ? 'Mid-latitude' : a >= 23.5 ? 'Subtropical' : 'Tropical';
}

/** e.g. "Arctic · bare ground · 420 m". */
export function describe(data: Dataset, i: number): string {
  const { lat } = latLon(data, i);
  const barren = val(data, 'barren_pct', i), ice = val(data, 'snow_ice_pct', i), water = val(data, 'water_pct', i), pf = val(data, 'permafrost_pct', i);
  const cover = ice !== null && ice >= 50 ? 'ice' : water !== null && water >= 50 ? 'mostly water' : barren !== null && barren >= 50 ? 'bare ground'
    : pf !== null && pf >= 50 ? 'permafrost' : water !== null && water >= 25 ? 'lakes and wetland' : barren === null ? 'land cover unknown' : 'vegetated';
  const elev = val(data, 'elev_mean_m', i);
  return [zone(lat), cover, fmt(elev, 'm')].filter(Boolean).join(' · ');
}

export function isWet(data: Dataset, i: number): boolean {
  const w = val(data, 'water_pct', i);
  return w !== null && w >= 50;
}

/**
 * Keep the list's order, but show one cell per area: a cell within `km` of one already shown is folded into it.
 * A display rule only. The engine's classes, counts and layers are unchanged, and the folded count is shown.
 */
export function spread(data: Dataset, list: number[], km: number): { kept: number[]; folded: Map<number, number> } {
  const kept: number[] = [], pts: { lat: number; lon: number }[] = [], folded = new Map<number, number>();
  const deg = km / 111;
  for (const i of list) {
    const p = latLon(data, i);
    let host = -1;
    for (let k = 0; k < pts.length; k++) {
      const q = pts[k]!;
      if (Math.abs(q.lat - p.lat) > deg) continue;
      if (kmBetween(p, q) < km) { host = k; break; }
    }
    if (host < 0) { kept.push(i); pts.push(p); folded.set(i, 0); }
    else folded.set(kept[host]!, (folded.get(kept[host]!) ?? 0) + 1);
  }
  return { kept, folded };
}
