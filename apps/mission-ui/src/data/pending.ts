/**
 * Traceable placeholders.
 *
 * Anything this UI shows that the data pipeline doesn't publish yet is created
 * with PENDING(id, awaits, sample). The id names the value; `awaits` says
 * which table, column or work order will supply it. The sample is the value
 * drawn in the Figma file, kept only so the layout can be checked. It isn't
 * data, and the UI marks every section that renders one.
 *
 * BLOCKED(id, reason) is for values the design shows but the project rules
 * don't allow yet (e.g. a single similarity score per site, AGENTS.md rule 4).
 * They render as an empty slot with the reason on hover.
 *
 * Find them all:  npm run pending   (or grep -rn "PENDING(\|BLOCKED(" src)
 */

export interface Pending<T> {
  readonly kind: 'pending';
  readonly id: string;
  readonly awaits: string;
  readonly sample: T;
}

export interface Blocked {
  readonly kind: 'blocked';
  readonly id: string;
  readonly reason: string;
}

export type Placeholder = Pending<unknown> | Blocked;

const registry = new Map<string, Placeholder>();

function register<P extends Placeholder>(p: P): P {
  if (registry.has(p.id)) throw new Error(`Duplicate placeholder id: ${p.id}`);
  registry.set(p.id, p);
  return p;
}

export function PENDING<T>(id: string, awaits: string, sample: T): Pending<T> {
  return register({ kind: 'pending', id, awaits, sample });
}

export function BLOCKED(id: string, reason: string): Blocked {
  return register({ kind: 'blocked', id, reason });
}

export function allPlaceholders(): Placeholder[] {
  return [...registry.values()];
}

export function describe(p: Placeholder): string {
  return p.kind === 'pending'
    ? `PENDING ${p.id}\nDesign sample, not pipeline data.\nAwaits: ${p.awaits}`
    : `BLOCKED ${p.id}\n${p.reason}`;
}
