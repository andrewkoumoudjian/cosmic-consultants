/**
 * Step 5 Limitations (owner round 2): "Scientific limitations" and "Trade-off analysis" side by side, then one chart,
 * "Which limitations matter most for this mission?". Nothing else.
 *
 * Every level comes from a written rule, never a hand-set number (AGENTS.md rules 2–4):
 *   High      the objective itself names it as not testable on Earth, or a required trait misses at every pick
 *   Moderate  a permanent breakdown (gravity, air pressure, radiation) the objective does not name, or a trait that
 *             misses or has no data at some picks
 *   Low       a trait that matches at every pick
 * Traits with no accepted band can't be checked, so they are listed as such and kept off the chart.
 * The bar length only encodes the level (three fixed widths). It is not a score.
 */
import { requirements, type Dataset, type Objective } from '../../../atlas/src/planner/engine.ts';
import type { PlanRequest } from '../../../atlas/src/plan-url.ts';
import { BREAKDOWNS, DIMENSION_LABEL, objectiveTitle, traitCells } from '../model.ts';
import { NavFoot, NeedSites, StepHead } from '../ui.tsx';

type Level = 'High' | 'Moderate' | 'Low';
type Limit = { key: string; label: string; level: Level; why: string; earth: boolean };
const ORDER: Level[] = ['High', 'Moderate', 'Low'];
const WIDTH: Record<Level, number> = { High: 92, Moderate: 60, Low: 28 };
const nameOf = (m: string) => BREAKDOWNS.find(b => b.mismatch === m)?.label ?? m.replace(/([a-z])([A-Z])/g, '$1 $2').replace(/^./, ch => ch.toUpperCase());

function limitationsFor(data: Dataset, request: PlanRequest, sites: number[], objective: Objective) {
  const named = new Set(objective.notTestableOnEarth.map(m => m.mismatch));
  const out: Limit[] = [
    ...objective.notTestableOnEarth.map(m => ({ key: m.mismatch, label: nameOf(m.mismatch), level: 'High' as Level, why: m.why, earth: true })),
    ...BREAKDOWNS.filter(b => !named.has(b.mismatch)).map(b => ({ key: b.mismatch, label: b.label, level: 'Moderate' as Level, why: b.why, earth: true })),
  ];
  const unchecked: string[] = [];
  const noBand = new Set(requirements(data, request).filter(r => !r.band).map(r => r.dimension as string));
  const cells = sites.map(i => traitCells(data, request, i));
  for (const d of [...new Set(cells.flat().map(c => c.dimension))]) {
    const label = DIMENSION_LABEL[d] ?? d;
    if (noBand.has(d)) { unchecked.push(label); continue; }
    const cs = cells.map(x => x.find(c => c.dimension === d)!).filter(Boolean);
    const misses = cs.filter(c => c.verdict === 'miss').length, unknown = cs.filter(c => c.verdict === 'unknown').length;
    if (misses === cs.length && cs[0]?.priority === 'must') out.push({ key: d, label, level: 'High', why: 'Misses your band at every pick', earth: false });
    else if (misses + unknown > 0) out.push({ key: d, label, level: 'Moderate', why: misses ? `Misses at ${misses} of ${cs.length} picks` : `No data at ${unknown} of ${cs.length} picks`, earth: false });
    else out.push({ key: d, label, level: 'Low', why: 'Matches at every pick', earth: false });
  }
  return { limits: out.sort((a, b) => ORDER.indexOf(a.level) - ORDER.indexOf(b.level)), unchecked };
}

export function Limitations({ data, request, sites, objective, onSites, onBack, onNext }: {
  data: Dataset; request: PlanRequest; sites: number[]; objective: Objective; onSites: () => void; onBack: () => void; onNext: () => void;
}) {
  const { limits, unchecked } = sites.length ? limitationsFor(data, request, sites, objective) : { limits: [], unchecked: [] };
  const cannot = limits.filter(l => l.earth);
  const constrain = limits.filter(l => l.level !== 'Low');
  const manage = limits.filter(l => l.level === 'Low');

  return (
    <div className="page">
      <StepHead step={5} />
      {!sites.length ? <NeedSites onSites={onSites} /> : <>
        <div className="lim-pair">
          <section className="card">
            <div><h2 className="card-title">Scientific limitations</h2><p className="t-small muted lim-def">What no Earth site can reproduce.</p></div>
            <ul className="lim-list">
              {cannot.map(l => <li key={l.key}><span className="lim-dot" data-level={l.level} /><span><b>{l.label}</b><span className="muted"> · {l.why}</span></span></li>)}
            </ul>
          </section>
          <section className="card">
            <div><h2 className="card-title">Trade-off analysis</h2><p className="t-small muted lim-def">What you can manage, and what limits your conclusions.</p></div>
            <div className="lim-group"><span className="t-label muted">Limits conclusions</span>
              <div className="chips">{constrain.map(l => <span key={l.key} className="lim-chip" data-level={l.level}>{l.label}</span>)}</div></div>
            <div className="lim-group"><span className="t-label muted">Manageable</span>
              <div className="chips">{manage.length ? manage.map(l => <span key={l.key} className="lim-chip" data-level="Low">{l.label}</span>) : <span className="t-small muted">Nothing matches at every pick</span>}</div></div>
            {unchecked.length > 0 && <div className="lim-group"><span className="t-label muted">Can't check (no accepted band)</span>
              <div className="chips">{unchecked.map(u => <span key={u} className="lim-chip">{u}</span>)}</div></div>}
          </section>
        </div>

        <section className="card" aria-label="Which limitations matter most for this mission?">
          <div>
            <h2 className="card-title">Which limitations matter most for this mission?</h2>
            <p className="t-label muted" style={{ marginTop: 4 }}>{objectiveTitle(objective)} · {sites.length} picked site{sites.length > 1 ? 's' : ''}</p>
          </div>
          <ul className="lim-bars">
            {limits.map(l => (
              <li key={l.key} title={l.why}>
                <span className="lim-name">{l.label}</span>
                <span className="lim-track"><span className="lim-fill" data-level={l.level} style={{ width: `${WIDTH[l.level]}%` }} /></span>
                <span className="lim-level" data-level={l.level}>{l.level}</span>
              </li>
            ))}
          </ul>
        </section>
      </>}
      <NavFoot onBack={onBack} onNext={onNext} nextLabel="Logistics" />
    </div>
  );
}
