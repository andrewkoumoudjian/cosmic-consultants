/**
 * Steps 05 Limitation report, 06 Logistics, 07 Risks & brief (Figma 77:526, 80:534, 89:544).
 * Only real release data is shown. What we hold no data for says "not checked" (AGENTS.md rule 3).
 */
import { useEffect, useState } from 'react';
import { Tabs } from '@base-ui/react/tabs';
import { brief, limitRows, months, requirements, rows, type Dataset, type Objective } from '../../../atlas/src/planner/engine.ts';
import { ensureMonthly } from '../../../atlas/src/planner/data.ts';
import type { PlanRequest } from '../../../atlas/src/plan-url.ts';
import { BREAKDOWNS, CLASS_TEXT, COLUMN_LABEL, DIMENSION_LABEL, MONTHS, SERIES, bandLabel, coordLabel, hazardFacts, logisticsFacts, monthWindowLabel, num, seasonStrip, siteClass, traitCells } from '../model.ts';
import { Footer, Plate, StepHeader, Verdict } from '../ui.tsx';

type Nav = { reached: number; onStep: (n: number) => void };

function SiteHead({ data, sites }: { data: Dataset; sites: number[] }) {
  return <>{sites.map((i, k) => (
    <th key={i}><span style={{ display: 'inline-flex', gap: 6, alignItems: 'center' }}><span className="swatch" style={{ background: SERIES[k] }} />{coordLabel(data, i)}</span></th>
  ))}</>;
}

function NoSites() {
  return <p className="notice">No site is in the comparison. Go back to the site finder and tick up to three.</p>;
}

export function Limits({ data, request, sites, objective, onBack, onNext, reached, onStep }: Nav & {
  data: Dataset; request: PlanRequest; sites: number[]; objective: Objective; onBack: () => void; onNext: () => void;
}) {
  const rules = requirements(data, request);
  const cells = sites.map(i => traitCells(data, request, i));
  const unknowns = cells.flat().filter(c => c.verdict === 'unknown').length;
  const cannot = [...BREAKDOWNS, ...objective.notTestableOnEarth.filter(m => !BREAKDOWNS.some(b => b.mismatch === m.mismatch))];
  return (
    <>
      <StepHeader title="Limitation report." lede={`What each compared site can and can't stand in for, over ${monthWindowLabel(request)}.`}
        step={5} reached={reached} onStep={onStep} />
      <div className="content">
        {!sites.length ? <NoSites /> : <>
          <div className="cards">
            <div className="card"><span className="fig">Sites compared</span><span className="big">{sites.length}</span><span className="muted t-small">picked in the site finder</span></div>
            <div className="card"><span className="fig">Traits checked</span><span className="big">{rules.length}</span><span className="muted t-small">{rules.filter(r => r.priority === 'must').length} required</span></div>
            <div className="card"><span className="fig">Unknown results</span><span className="big v-unknown">{unknowns}</span><span className="muted t-small">site × trait pairs with no verdict</span></div>
            <div className="card"><span className="fig">Earth can't reproduce</span><span className="big">{cannot.length}</span><span className="muted t-small">the same at every site</span></div>
          </div>

          <section>
            <div className="plate-head"><h2 className="t-section">Requirements verification matrix</h2><span className="muted t-small">bold = required · ✓ match · ✕ miss with gap · ? unknown</span></div>
            <div className="sheet-wrap">
              <table className="sheet">
                <thead><tr><th>Trait</th><th>Target</th><SiteHead data={data} sites={sites} /></tr></thead>
                <tbody>
                  {rules.map(r => (
                    <tr key={r.dimension} className={r.priority === 'must' ? 'must' : undefined}>
                      <td>{DIMENSION_LABEL[r.dimension]}<div className="t-small muted" style={{ fontWeight: 400 }}>{r.earthColumn ? COLUMN_LABEL[r.earthColumn] ?? r.earthColumn : 'no Earth data'}</div></td>
                      <td className="muted">{bandLabel(r)}</td>
                      {cells.map((cs, k) => {
                        const c = cs.find(x => x.dimension === r.dimension)!;
                        return <td key={k}><Verdict verdict={c.verdict} /><div className="t-small muted">{c.detail}</div></td>;
                      })}
                    </tr>
                  ))}
                </tbody>
                <tfoot><tr><td colSpan={2}>Engine result</td>{sites.map(i => <td key={i}>{CLASS_TEXT[siteClass(data, request, i)]}</td>)}</tr></tfoot>
              </table>
            </div>
          </section>

          <div className="two-col">
            <section>
              <div className="plate-head"><h2 className="t-section">What no Earth site can reproduce</h2></div>
              <ul className="plain">
                {cannot.map(m => <li key={m.mismatch}><b style={{ fontWeight: 500 }}>{m.mismatch}</b><div className="muted">{m.why}</div></li>)}
              </ul>
              <p className="t-small muted" style={{ marginTop: 10 }}>These are permanent breakdowns. Plan to cover them in a lab, a chamber or a simulator.</p>
            </section>
            <section>
              <div className="plate-head"><h2 className="t-section">Data uncertainty</h2></div>
              <ul className="plain">
                {sites.flatMap((i, k) => cells[k]!.filter(c => c.verdict === 'unknown').map(c => (
                  <li key={`${i}-${c.dimension}`}>
                    <span className="v v-unknown"><span className="mark unknown" />Unknown</span>{' '}
                    <span className="swatch" style={{ background: SERIES[k] }} /> {coordLabel(data, i)} · <b style={{ fontWeight: 500 }}>{DIMENSION_LABEL[c.dimension]}</b>
                    <div className="muted">{c.detail}</div>
                  </li>
                )))}
                {rules.filter(r => r.basis || r.scaleCaveat).map(r => (
                  <li key={`caveat-${r.dimension}`}><b style={{ fontWeight: 500 }}>{DIMENSION_LABEL[r.dimension]}</b><div className="muted">{[r.basis, r.scaleCaveat].filter(Boolean).join(' ')}</div></li>
                ))}
                {data.runtime.qualityWarnings.map(w => <li key={w} className="muted">{w}</li>)}
              </ul>
            </section>
          </div>
        </>}
      </div>
      <Footer step={5} onBack={onBack} next={onNext} nextLabel="Compare logistics →" note={`${sites.length} sites compared`} />
    </>
  );
}

export function Logistics({ data, request, sites, checklist, onChecklist, onBack, onNext, reached, onStep }: Nav & {
  data: Dataset; request: PlanRequest; sites: number[]; checklist: string; onChecklist: (s: string) => void; onBack: () => void; onNext: () => void;
}) {
  const facts = sites.map(i => logisticsFacts(data, i));
  const range = (col: string) => {
    const v = sites.map(i => data.yearly[col]?.[i]).filter((x): x is number => x !== undefined && Number.isFinite(x));
    return v.length ? `${num(Math.min(...v))} – ${num(Math.max(...v))}` : 'unknown';
  };
  const strips = sites.map(i => seasonStrip(data, request, i));
  return (
    <>
      <StepHeader title="Logistics." lede={`Getting a team of ${request.teamSize ?? '—'} to each site for ${request.durationDays ?? '—'} days. Only what the release measures is shown.`}
        step={6} reached={reached} onStep={onStep} />
      <div className="content">
        {!sites.length ? <NoSites /> : <>
          <div className="cards">
            <div className="card"><span className="fig">Sites compared</span><span className="big">{sites.length}</span><span className="muted t-small">{request.missionType} mission</span></div>
            <div className="card"><span className="fig">Nearest airport</span><span className="big">{range('airport_km')}</span><span className="muted t-small">km, paved runway</span></div>
            <div className="card"><span className="fig">Travel from a city</span><span className="big">{range('access_min_median')}</span><span className="muted t-small">minutes, median over the cell</span></div>
            <div className="card"><span className="fig">Cost and permits</span><span className="big muted">Not checked</span><span className="muted t-small">we hold no data for these</span></div>
          </div>

          <section>
            <div className="plate-head"><h2 className="t-section">Logistics at a glance</h2></div>
            <div className="sheet-wrap">
              <table className="sheet">
                <thead><tr><th>Measure</th><SiteHead data={data} sites={sites} /></tr></thead>
                <tbody>
                  {facts[0]!.map((f, r) => (
                    <tr key={f.label}><td>{f.label}</td>{facts.map((fs, k) => <td key={k} className="num">{fs[r]!.value === 'unknown' ? <span className="v-unknown">unknown</span> : `${fs[r]!.value} ${fs[r]!.unit}`}</td>)}</tr>
                  ))}
                  {sites.length > 0 && limitRows(data, request, sites[0]!).map((l, r) => (
                    <tr key={l.limit}><td>Limit: {l.limit} ≤ {l.max}</td>{sites.map(i => {
                      const row = limitRows(data, request, i)[r]!;
                      return <td key={i} className={`num ${row.outcome === 'fail' ? 'v-miss' : row.outcome === 'unknown' ? 'v-unknown' : 'v-match'}`}>{row.outcome}</td>;
                    })}</tr>
                  ))}
                  <tr><td>Vehicles, comms, habitat, permits</td>{sites.map(i => <td key={i} className="muted">not checked</td>)}</tr>
                </tbody>
              </table>
            </div>
          </section>

          <section>
            <div className="plate-head"><h2 className="t-section">Seasonal planning</h2>
              <span className="t-small" style={{ display: 'flex', gap: 14, flexWrap: 'wrap' }}>
                <span className="v v-match"><span className="mark match" />no required miss</span>
                <span className="v v-unknown"><span className="mark unknown" />required trait unknown</span>
                <span className="v v-miss"><span className="mark miss" />required trait missed</span>
              </span></div>
            <p className="muted" style={{ marginBottom: 12 }}>The engine's result for each site if the field window were that single month. Your window: {monthWindowLabel(request)}.</p>
            <div className="season" role="table" aria-label="Result per month">
              <span />{MONTHS.map(m => <span key={m} className="t-small muted" style={{ textAlign: 'center' }}>{m}</span>)}
              {sites.map((i, k) => [
                <span key={`l${i}`} className="t-small" style={{ display: 'flex', gap: 6, alignItems: 'center' }}><span className="swatch" style={{ background: SERIES[k] }} />{coordLabel(data, i)}</span>,
                ...strips[k]!.map((cls, m) => <span key={`${i}-${m}`} className={`cell ${cls}`} title={`${MONTHS[m]}: ${CLASS_TEXT[cls]}`}>{cls === 'allMatch' ? '✓' : cls === 'someMiss' ? '✕' : '?'}</span>),
              ])}
              <span className="t-small muted">Sites with no required miss</span>
              {MONTHS.map((m, j) => <span key={m} className="t-small" style={{ textAlign: 'center' }}>{strips.filter(s => s[j] === 'allMatch').length} / {sites.length}</span>)}
            </div>
          </section>

          <section>
            <div className="plate-head"><h2 className="t-section">Planning checklist</h2><span className="muted t-small">goes into the brief</span></div>
            <p className="muted" style={{ marginBottom: 10 }}>Write down equipment, permits, people, budget, comms and emergency access. We can't check these for you.</p>
            <textarea className="field" value={checklist} onChange={e => onChecklist(e.target.value)} placeholder={'Equipment:\nPermits:\nPeople:\nBudget:\nComms:\nEmergency access:'} />
          </section>
        </>}
      </div>
      <Footer step={6} onBack={onBack} next={onNext} nextLabel="Review risks →" note={`${sites.length} sites compared`} />
    </>
  );
}

export function Risks({ data, request, sites, checklist, onBack, reached, onStep }: Nav & {
  data: Dataset; request: PlanRequest; sites: number[]; checklist: string; onBack: () => void;
}) {
  const [burned, setBurned] = useState<'loading' | 'ready' | 'missing'>('loading');
  useEffect(() => {
    let live = true;
    ensureMonthly(data, ['burned_pct']).then(() => { if (live) setBurned(data.monthly.burned_pct ? 'ready' : 'missing'); }, () => { if (live) setBurned('missing'); });
    return () => { live = false; };
  }, [data]);
  const pinned = sites.map(i => data.h3[i]!);
  const campaigns = data.runtime.campaigns as { campaignId: string; name: string; agency?: string[]; years?: { first: number; last: number }; site?: { name?: string; h3r4?: string } }[];

  const download = () => {
    const text = brief(data, request, sites, checklist);
    const url = URL.createObjectURL(new Blob([text], { type: 'text/markdown' }));
    const a = Object.assign(document.createElement('a'), { href: url, download: `mission-brief-${request.objectiveId}.md` });
    a.click();
    URL.revokeObjectURL(url);
  };

  return (
    <>
      <StepHeader title="Risks & brief." lede="Hazards recorded near each site, past campaigns in our sources, and a brief you can hand to the team."
        step={7} reached={reached} onStep={onStep} />
      <div className="content">
        {!sites.length ? <NoSites /> : <>
          <Tabs.Root defaultValue={String(sites[0])}>
            <Tabs.List className="tabs" aria-label="Compared sites">
              {sites.map((i, k) => (
                <Tabs.Tab key={i} value={String(i)}><span className="swatch" style={{ background: SERIES[k], marginRight: 6 }} />{coordLabel(data, i)}</Tabs.Tab>
              ))}
            </Tabs.List>
            {sites.map(i => <Tabs.Panel key={i} value={String(i)} style={{ marginTop: 20 }}><SiteRisks data={data} request={request} i={i} burned={burned} /></Tabs.Panel>)}
          </Tabs.Root>

          <section>
            <div className="plate-head"><h2 className="t-section">Past campaigns in our sources</h2><span className="muted t-small">closeness to past campaigns: not checked yet (S8 pending)</span></div>
            <div className="sheet-wrap">
              <table className="sheet">
                <thead><tr><th>Campaign</th><th>Where</th><th>Years</th><th>Agency</th><th>In a compared cell</th></tr></thead>
                <tbody>
                  {campaigns.map(c => (
                    <tr key={c.campaignId}>
                      <td>{c.name}</td><td className="muted">{c.site?.name ?? 'unknown'}</td>
                      <td>{c.years ? (c.years.first === c.years.last ? c.years.first : `${c.years.first}–${c.years.last}`) : 'unknown'}</td>
                      <td>{c.agency?.join(', ') ?? 'unknown'}</td>
                      <td>{c.site?.h3r4 && pinned.includes(c.site.h3r4) ? <span className="v-match">yes</span> : <span className="muted">no</span>}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>

          <Plate fig="FIG. 07 — Mission brief" title="Take the plan with you"
            aside={<span className="muted t-small">Markdown with every verdict, band, reason and source hash</span>}>
            <p className="muted" style={{ marginBottom: 14 }}>The brief lists each compared site's results, the limits, what Earth can't reproduce, your checklist and the SHA-256 of every input file.</p>
            <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap' }} className="no-print">
              <button className="btn btn-primary" onClick={download}>Download brief (.md)</button>
              <button className="btn btn-secondary" onClick={() => window.print()}>Print this page</button>
            </div>
          </Plate>
        </>}
      </div>
      <Footer step={7} onBack={onBack} nextLabel="" note="Step 7 of 7 · plan complete" />
    </>
  );
}

function SiteRisks({ data, request, i, burned }: { data: Dataset; request: PlanRequest; i: number; burned: 'loading' | 'ready' | 'missing' }) {
  const { events, byCategory, steep } = hazardFacts(data, i);
  const hot = data.yearly.lst_day_max_k?.[i], cold = data.yearly.lst_night_min_k?.[i];
  const fire = burned === 'ready' ? months(request).map(m => data.monthly.burned_pct![i * 12 + m - 1]!) : [];
  const fireKnown = fire.filter(v => Number.isFinite(v));
  const unknownTraits = rows(data, request, i).filter(r => r.verdict === 'unknown').length;
  return (
    <div className="two-col">
      <section>
        <div className="fig" style={{ marginBottom: 8 }}>Natural events on record (NASA EONET)</div>
        {events.length === 0
          ? <p className="muted">None recorded in this cell. EONET is a curated list, so none recorded doesn't mean safe.</p>
          : <ul className="plain">
              {[...byCategory].map(([cat, list]) => (
                <li key={cat}>
                  <b style={{ fontWeight: 500 }}>{cat}</b> <span className="muted">· {list.length} event{list.length > 1 ? 's' : ''}</span>
                  <div className="t-small">{list.slice(0, 4).map(e => (
                    <div key={String(e.event_id)}><span className="muted">{String(e.start_date ?? '')}</span>{' '}
                      {e.source_url ? <a href={String(e.source_url)} target="_blank" rel="noreferrer">{String(e.title)}</a> : String(e.title)}</div>
                  ))}{list.length > 4 && <div className="muted">and {list.length - 4} more</div>}</div>
                </li>
              ))}
            </ul>}
      </section>
      <section>
        <div className="fig" style={{ marginBottom: 8 }}>Site conditions</div>
        <div className="kv"><span className="muted">Ground steeper than 30°</span><span>{steep === null || !Number.isFinite(steep) ? <span className="v-unknown">unknown</span> : `${num(steep * 100)} % of the cell`}</span></div>
        <div className="kv"><span className="muted">Hottest daytime surface (year)</span><span>{hot !== undefined && Number.isFinite(hot) ? `${num(hot)} K (${num(hot - 273.15)} °C)` : <span className="v-unknown">unknown</span>}</span></div>
        <div className="kv"><span className="muted">Coldest night surface (year)</span><span>{cold !== undefined && Number.isFinite(cold) ? `${num(cold)} K (${num(cold - 273.15)} °C)` : <span className="v-unknown">unknown</span>}</span></div>
        <div className="kv"><span className="muted">Most burned area in your window</span><span>{burned === 'loading' ? 'loading…' : fireKnown.length ? `${num(Math.max(...fireKnown))} %` : <span className="v-unknown">unknown</span>}</span></div>
        <div className="kv"><span className="muted">Traits with no verdict</span><span className={unknownTraits ? 'v-unknown' : undefined}>{unknownTraits}</span></div>
        <div className="kv"><span className="muted">Field safety, rescue, weather on the day</span><span className="muted">not checked</span></div>
      </section>
    </div>
  );
}

