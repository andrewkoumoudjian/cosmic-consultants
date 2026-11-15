/**
 * Step 7 Risks, per the owner brief (2026-11-15): three pillars (Environmental risks, Personnel safety & human
 * factors, Environmental impact) and "a simple risk matrix (likelihood × severity) alongside a list of identified
 * risks and suggested mitigations". The release has no likelihood data, so nothing lands on the matrix until a
 * person rates it (AGENTS.md rule 3). Each risk shows its measured evidence and a rule-based severity hint whose
 * thresholds are written out; the hint is never applied for you.
 * Ids stay 'environment' / 'medical' / 'ecological' so ratings in links shared before the rename still load.
 */
import { Fragment, useEffect, useState } from 'react';
import { Collapsible } from '@base-ui/react/collapsible';
import { ensureMonthly, ensureYearly } from '../../../atlas/src/planner/data.ts';
import type { Dataset } from '../../../atlas/src/planner/engine.ts';
import type { PlanRequest } from '../../../atlas/src/plan-url.ts';
import { burnedInWindow, fmt, riskAssessment, tempInWindow, type RiskSeverity } from '../model.ts';
import { Button, Card, NavFoot, NeedSites, Select, SiteTabs, SiteTag, StepHead } from '../ui.tsx';

export type Likelihood = 'Unlikely' | 'Possible' | 'Likely';
type Rating = { l?: Likelihood; s?: RiskSeverity };
export type Ratings = Record<string, Rating>;
type RiskId = 'environment' | 'medical' | 'ecological';

const LIK: Likelihood[] = ['Unlikely', 'Possible', 'Likely'];
const SEV: RiskSeverity[] = ['Low', 'Moderate', 'High'];
const PILLARS: { id: RiskId; title: string; short: string; covers: string }[] = [
  { id: 'environment', title: 'Environmental risks', short: 'Environment', covers: 'Extreme weather, natural hazards, wildlife and difficult terrain.' },
  { id: 'medical', title: 'Personnel safety & human factors', short: 'Personnel', covers: 'Risk of injury, distance to emergency services, and how easily the team can be evacuated.' },
  { id: 'ecological', title: 'Environmental impact', short: 'Impact', covers: 'Possible damage to local ecosystems from equipment, sampling or other field work.' },
];

/** Matrix level from severity × likelihood (0–4): 0–1 low, 2 medium, 3–4 high. */
const LEVEL = (s: RiskSeverity, l: Likelihood) => { const n = SEV.indexOf(s) + LIK.indexOf(l); return n <= 1 ? 'low' : n === 2 ? 'medium' : 'high'; };
const LEVEL_WORD = { low: 'Low', medium: 'Medium', high: 'High' } as const;

/** Ratings travel in the link hash as "h3.risk.L.S" items (L/S are first letters, "-" = not rated). */
export function encodeRatings(r: Ratings): string {
  return Object.entries(r).filter(([, v]) => v.l || v.s).map(([k, v]) => `${k}.${v.l?.[0] ?? '-'}.${v.s?.[0] ?? '-'}`).join(',');
}
export function decodeRatings(s: string | null): Ratings {
  const out: Ratings = {};
  for (const item of (s ?? '').split(',')) {
    const [h3, id, l, sv] = item.split('.');
    if (!h3 || !id || !PILLARS.some(c => c.id === id)) continue;
    out[`${h3}.${id}`] = { l: LIK.find(x => x[0] === l), s: SEV.find(x => x[0] === sv) };
  }
  return out;
}

type Item = { id: RiskId; hint: RiskSeverity | null; basis: string[]; mitigation: string; rule: string };

const RULES: Record<RiskId, string> = {
  environment: 'High if any EONET event, ≥ 15 % ground over 30°, ≥ 5 % burned in the window, ground ≥ 45 °C or ≤ −40 °C, or mean wind ≥ 8 m/s. Moderate if ≥ 3 % steep, any burn, ≥ 35 °C or ≤ −20 °C, yearly max dust AOD ≥ 0.3 or wind ≥ 5 m/s. Otherwise Low.',
  medical: 'High if travel to a city ≥ 6 h or an airport ≥ 300 km. Moderate if ≥ 90 min or ≥ 80 km. Otherwise Low.',
  ecological: 'High if ≥ 25 % protected land. Moderate if any. With no protected-land data, High if water cover ≥ 25 %.',
};
const worse = (a: RiskSeverity | null, b: RiskSeverity | null) => (a === null ? b : b === null ? a : SEV.indexOf(a) >= SEV.indexOf(b) ? a : b);

/** Weather exposure from measured wind and dust, folded into Environmental risks ("extreme weather"). */
function weather(data: Dataset, i: number): { hint: RiskSeverity | null; basis: string[] } {
  const y = (c: string) => { const v = data.yearly[c]?.[i]; return v !== undefined && Number.isFinite(v) ? v : null; };
  const dust = y('dust_aod_max'), wind = y('wind_speed_mean');
  const hint = dust === null && wind === null ? null : wind !== null && wind >= 8 ? 'High' : (dust !== null && dust >= 0.3) || (wind !== null && wind >= 5) ? 'Moderate' : 'Low';
  return { hint, basis: [`Wind speed, yearly mean: ${wind === null ? 'no data' : `${wind.toFixed(1)} m/s`}`, `Dust aerosol optical depth, yearly max: ${fmt(dust, 'unitless') ?? 'no data'}`, 'Wildlife: no data in this release'] };
}

export function Risks({ data, request, sites, ratings, onRatings, onSites, onBack, onNext }: {
  data: Dataset; request: PlanRequest; sites: number[]; ratings: Ratings; onRatings: (r: Ratings) => void; onSites: () => void; onBack: () => void; onNext: () => void;
}) {
  const [k, setK] = useState(0);
  const [state, setState] = useState<'loading' | 'ready' | 'missing'>('loading');
  const [flash, setFlash] = useState<RiskId | null>(null);
  useEffect(() => {
    let live = true;
    Promise.all([ensureMonthly(data, ['burned_pct', 'lst_day_k', 'lst_night_k']), ensureYearly(data, ['wind_speed_mean', 'dust_aod_max'])]).then(
      () => { if (live) setState('ready'); }, () => { if (live) setState('missing'); });
    return () => { live = false; };
  }, [data]);
  const kk = Math.min(k, Math.max(sites.length - 1, 0));
  const i = sites[kk];

  const head = <StepHead step={7} context={sites.length > 1 ? <SiteTabs data={data} sites={sites} value={kk} onChange={setK} />
    : sites.length === 1 ? <span className="bubble"><SiteTag data={data} i={sites[0]!} k={0} /></span> : undefined} />;
  const pillars = (
    <section className="pillars" aria-label="Risk pillars">
      <div className="pillar-row">
        {PILLARS.map(p => (
          <Collapsible.Root key={p.id} className="pillar">
            <Collapsible.Trigger className="pillar-trigger">
              <span>{p.title}</span><Caret />
            </Collapsible.Trigger>
            <Collapsible.Panel className="pillar-panel"><p>{p.covers}</p></Collapsible.Panel>
          </Collapsible.Root>
        ))}
      </div>
    </section>
  );
  if (i === undefined) return <div className="page">{head}{pillars}<NeedSites onSites={onSites} /><NavFoot onBack={onBack} onNext={onNext} nextLabel="Lessons learned" /></div>;

  const h3 = data.h3[i]!;
  const fire = state === 'ready' ? burnedInWindow(data, request, i) : null;
  const temp = state === 'ready' ? tempInWindow(data, request, i) : null;
  const base = riskAssessment(data, request, i, fire, temp);
  const fromBase = (id: RiskId): Item => {
    const r = base.find(x => x.id === id)!;
    return { id, hint: r.evidence === 'missing' ? null : r.severity, basis: r.basis.split(' · '), mitigation: r.mitigation, rule: RULES[id] };
  };
  const env = fromBase('environment'), w = weather(data, i);
  const items: Item[] = [
    { ...env, hint: worse(env.hint, w.hint), basis: [...env.basis, ...w.basis],
      mitigation: env.mitigation },
    fromBase('medical'),
    fromBase('ecological'),
  ];
  const key = (id: RiskId) => `${h3}.${id}`;
  const rating = (id: RiskId): Rating => ratings[key(id)] ?? {};
  const setRating = (id: RiskId, patch: Rating) => onRatings({ ...ratings, [key(id)]: { ...rating(id), ...patch } });
  const placed = items.filter(it => rating(it.id).l && rating(it.id).s);
  const jump = (id: RiskId) => { setFlash(id); document.getElementById(`risk-${id}`)?.scrollIntoView({ behavior: 'smooth', block: 'center' }); setTimeout(() => setFlash(null), 1400); };

  return (
    <div className="page">
      {head}
      {pillars}
      <div className="grid-2 risks-main">
        <Card title="Likelihood × severity" aside={<span className="t-label muted">{placed.length} of {items.length} rated</span>}>
            <div className="matrix" role="table" aria-label="Risk matrix, severity by likelihood">
              <span className="ax corner">Severity</span>
              {LIK.map(l => <span key={l} className="ax x">{l}</span>)}
              {[...SEV].reverse().map(s => (
                <Fragment key={s}>
                  <span className="ax" role="rowheader">{s}</span>
                  {LIK.map(l => {
                    const here = placed.filter(it => rating(it.id).l === l && rating(it.id).s === s);
                    const lv = LEVEL(s, l);
                    return (
                      <div key={l} className="mcell" data-level={lv} role="cell"
                        aria-label={`${s} severity, ${l}, ${LEVEL_WORD[lv]} risk: ${here.map(h => PILLARS.find(x => x.id === h.id)!.title).join(', ') || 'none'}`}>
                        <span className="mlevel">{LEVEL_WORD[lv]}</span>
                        {here.map(h => <Button key={h.id} className="mchip" onClick={() => jump(h.id)}>{PILLARS.find(x => x.id === h.id)!.short}</Button>)}
                      </div>
                    );
                  })}
                </Fragment>
              ))}
            </div>
            <div className="mlegend">
              <span><i data-level="low" />Low</span><span><i data-level="medium" />Medium</span><span><i data-level="high" />High</span>
            </div>
          </Card>

        <Card title="Risks and mitigations">
          <ul className="items">
            {items.map(it => {
              const p = PILLARS.find(x => x.id === it.id)!;
              const r = rating(it.id);
              const lv = r.l && r.s ? LEVEL(r.s, r.l) : null;
              return (
                <li key={it.id} id={`risk-${it.id}`} className={`item risk${flash === it.id ? ' flash' : ''}`}>
                  <div className="spread" style={{ flexWrap: 'nowrap' }}>
                    <h3 className="t-card">{p.title}</h3>
                    {lv && <span className="level-tag" data-level={lv}>{LEVEL_WORD[lv]} risk</span>}
                  </div>
                  <div className="risk-controls">
                    <Select label={`${p.title} likelihood`} value={r.l ?? 'unset'} onChange={v => setRating(it.id, { l: v === 'unset' ? undefined : (v as Likelihood) })}
                      options={[{ value: 'unset', label: 'Likelihood' }, ...LIK.map(l => ({ value: l, label: l }))]} />
                    <span className="muted">×</span>
                    <Select label={`${p.title} severity`} value={r.s ?? 'unset'} onChange={v => setRating(it.id, { s: v === 'unset' ? undefined : (v as RiskSeverity) })}
                      options={[{ value: 'unset', label: 'Severity' }, ...SEV.map(s => ({ value: s, label: s }))]} />
                    {it.hint && <span className="t-label muted" title={it.rule}>Data suggests <b className={`sev ${it.hint}`}>{it.hint}</b></span>}
                  </div>
                  <p className="t-small text-2">{it.mitigation}</p>
                  <Collapsible.Root className="evidence">
                    <Collapsible.Trigger className="evidence-trigger"><Caret />Evidence{state === 'loading' && ' · loading'}</Collapsible.Trigger>
                    <Collapsible.Panel className="pillar-panel">
                      <ul className="stack" style={{ gap: 4, paddingTop: 8 }}>{it.basis.map(b => <li key={b} className="mono t-label text-2">{b}</li>)}</ul>
                      <p className="t-label muted" style={{ marginTop: 8 }}>Hint rule: {it.rule} Team thresholds, not a published standard.</p>
                    </Collapsible.Panel>
                  </Collapsible.Root>
                </li>
              );
            })}
          </ul>
        </Card>
      </div>

      <NavFoot onBack={onBack} onNext={onNext} nextLabel="Lessons learned" />
    </div>
  );
}

const Caret = () => <svg className="caret" width="10" height="10" viewBox="0 0 10 10" aria-hidden><path d="M3.5 2 6.5 5 3.5 8" fill="none" stroke="currentColor" strokeWidth="1.5" /></svg>;
