/** Funnel warnings computed from the resolved requirements, not from the URL (#185). */
import type { Rule } from './engine.ts';

/**
 * A share link may name no `must`/`nice` traits; the engine then uses the trait
 * map's priority (default required). So warnings must read the resolved rules.
 */
export function priorityNotices(rules: Pick<Rule, 'dimension' | 'priority' | 'band' | 'earthColumn'>[]): string[] {
  const notes: string[] = [];
  const required = rules.filter(r => r.priority === 'must');
  if (!required.length) notes.push('All requirements are preferred: no trait filters the results.');
  const blind = required.filter(r => r.band === null || !r.earthColumn).map(r => r.dimension);
  if (blind.length) {
    notes.push(`Required with no test band: ${blind.join(', ')}. No site can match these yet, so every site stays “need more evidence”. Enter bounds, or make them preferred.`);
  }
  return notes;
}
