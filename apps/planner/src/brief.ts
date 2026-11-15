import { brief, type Dataset } from '../../atlas/src/planner/engine.ts';
import type { PlanRequest } from '../../atlas/src/plan-url.ts';
import { coordLabel, fmt } from './model.ts';

export const WATER_COVER_GUIDANCE = 'Confirm dry-land staging coordinates outside lakes, wetlands, or coastal waters before deployment.';

/** The existing Limitations warning rule, shared by the screen and export. */
export function waterCoverWarning(value: number | undefined): string | null {
  return value !== undefined && Number.isFinite(value) && value > 25 ? WATER_COVER_GUIDANCE : null;
}

/** Keep report context alongside the shared engine's requirements and sources. */
export function plannerBrief(data: Dataset, request: PlanRequest, sites: number[], checklist: string): string {
  const original = brief(data, request, sites, checklist);
  if (!sites.length) return original;
  const context = ['', '## Water-cover context from the planner reports',
    'Cell-wide water cover does not establish a dry or usable staging location.', ''];
  for (const i of sites) {
    const water = data.yearly.water_pct?.[i];
    context.push(`### ${data.h3[i]} (${coordLabel(data, i)})`, '', `Water cover in the cell: ${fmt(water, '%') ?? 'no data'}.`);
    const warning = waterCoverWarning(water);
    if (warning) context.push(`Surface water cover > 25 %: ${warning}`);
    if (water === undefined || !Number.isFinite(water)) context.push('Water cover is missing in this release; verify dry-land staging before deployment.');
    context.push('');
  }
  return original + context.join('\n');
}
