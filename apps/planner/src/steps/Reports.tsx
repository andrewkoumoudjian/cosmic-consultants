/**
 * Steps 5 Limitations, 6 Logistics, 7 Risks. Only real release data is shown.
 * Anything we hold no data for says "not checked" (AGENTS.md rule 3).
 */
import { useEffect, useState } from 'react';
import { Tabs } from '@base-ui/react/tabs';
import { brief, limitRows, months, requirements, rows, type Dataset, type Objective } from '../../../atlas/src/planner/engine.ts';
import { ensureMonthly } from '../../../atlas/src/planner/data.ts';
import type { PlanRequest } from '../../../atlas/src/plan-url.ts';
import { BREAKDOWNS, CLASS_TEXT, DIMENSION_LABEL, MONTHS, SERIES, bandLabel, burnedInWindow, coordLabel, download, hazardFacts, logisticsFacts, num, seasonStrip, sheetCsv, siteClass, traitCells } from '../model.ts';
import { Page, Verdict } from '../ui.tsx';

function SiteHead({ data, sites }: { data: Dataset; sites: number[] }) {
  return <>{sites.map((i, k) => <th key={i} className="mono"><span className="swatch" style={{ background: SERIES[k] }} />{coordLabel(data, i)}</th>)}</>;
}

function SheetButton({ data, request, sites }: { data: Dataset; request: PlanRequest; sites: number[] }) {
  return (
    <button className="btn btn-line" disabled={!sites.length} title="A tidy CSV: one row per site and trait. Opens in JSheets."
      onClick={() => download(`sites-${request.objectiveId}.csv`, sheetCsv(data, request, sites), 'text/csv')}>Open in JSheets (.csv)</button>
  );
}

const NoSites = () => <p className="warn">No sites compared. Pin up to three in Sites.</p>;

export function Limits({ data, request, sites, objective, onBack, onNext }: {
  data: Dataset; request: PlanRequest; sites: number[]; objective: Objective; onBack: () => void; onNext: () => void;
}) {
  const rules = requirements(data, request);
  const cells = sites.map(i => traitCells(data, request, i));
  const cannot = [...BREAKDOWNS, ...objective.notTestableOnEarth.filter(m => !BREAKDOWNS.some(b => b.mismatch === m.mismatch))];
  const unknowns = sites.flatMap((i, k) => cells[k]!.filter(c => c.verdict === 'unknown').map(c => ({ i, k, c })));
  const caveats = rules.filter(r => r.basis || r.scaleCaveat);
  return (
    <Page title="Limitations" back={onBack} next={onNext} aside={<SheetButton data={data} request={request} sites={sites} />}>
      {!sites.length ? <NoSites /> : <>
        <div className="sheet">
          <table>
            <thead><tr><th>Trait</th><th className="num">Band</th><SiteHead data={data} sites={sites} /></tr></thead>
            <tbody>
              {rules.map(r => (
                <tr key={r.dimension} className={r.priority === 'must' ? 'must' : undefined}>
                  <td>{DIMENSION_LABEL[r.dimension]}{r.priority === 'nice' && <span className="muted"> · preferred</span>}</td>
                  <td className="num muted">{bandLabel(r)}</td>
                  {cells.map((cs, k) => {
                    const c = cs.find(x => x.dimension === r.dimension)!;
                    return <td key={k}><Verdict verdict={c.verdict}><span className="muted mono small">{c.detail}</span></Verdict></td>;
                  })}
                </tr>
              ))}
            </tbody>
            <tfoot><tr><td colSpan={2}>Required traits</td>{sites.map(i => <td key={i}>{CLASS_TEXT[siteClass(data, request, i)]}</td>)}</tr></tfoot>
          </table>
        </div>

        <div className="cols">
          <section>
            <h2 className="h2">Earth can't reproduce</h2>
            <ul className="list">{cannot.map(m => <li key={m.mismatch}><span>{m.mismatch}</span><span className="muted small">{m.why}</span></li>)}</ul>
          </section>
          <section>
            <h2 className="h2">Unknown</h2>
            {unknowns.length === 0 ? <p className="muted">None.</p> : (
              <ul className="list">{unknowns.map(({ i, k, c }) => (
                <li key={`${i}-${c.dimension}`}>
                  <span><span className="swatch" style={{ background: SERIES[k] }} /><span className="mono">{coordLabel(data, i)}</span> · {DIMENSION_LABEL[c.dimension]}</span>
                  <span className="muted small">{c.detail}</span>
                </li>
              ))}</ul>
            )}
            {(caveats.length > 0 || data.runtime.qualityWarnings.length > 0) && (
              <details>
                <summary>Data notes</summary>
                <ul className="list">
                  {caveats.map(r => <li key={r.dimension}><span>{DIMENSION_LABEL[r.dimension]}</span><span className="muted small">{[r.basis, r.scaleCaveat].filter(Boolean).join(' ')}</span></li>)}
                  {data.runtime.qualityWarnings.map(w => <li key={w}><span className="muted small">{w}</span></li>)}
                </ul>
              </details>
            )}
          </section>
        </div>
      </>}
    </Page>
  );
}

export function Logistics({ data, request, sites, checklist, onChecklist, onBack, onNext }: {
  data: Dataset; request: PlanRequest; sites: number[]; checklist: string; onChecklist: (s: string) => void; onBack: () => void; onNext: () => void;
}) {
  const facts = sites.map(i => logisticsFacts(data, i));
  const strips = sites.map(i => seasonStrip(data, request, i));
  const inWindow = new Set(months(request));
  return (
    <Page title="Logistics" back={onBack} next={onNext} aside={<SheetButton data={data} request={request} sites={sites} />}>
      {!sites.length ? <NoSites /> : <>
        <div className="sheet">
          <table>
            <thead><tr><th>Measure</th><SiteHead data={data} sites={sites} /></tr></thead>
            <tbody>
              {facts[0]!.map((f, r) => (
                <tr key={f.label}><td>{f.label}</td>{facts.map((fs, k) => (
                  <td key={k} className="num">{fs[r]!.value === 'unknown' ? <span className="v-unknown">unknown</span> : <>{fs[r]!.value} <span className="muted">{fs[r]!.unit}</span></>}</td>
                ))}</tr>
              ))}
              {limitRows(data, request, sites[0]!).map((l, r) => (
                <tr key={l.limit}><td>Limit · {l.limit} ≤ {l.max}</td>{sites.map(i => {
                  const row = limitRows(data, request, i)[r]!;
                  return <td key={i} className={`num ${row.outcome === 'fail' ? 'v-miss' : row.outcome === 'unknown' ? 'v-unknown' : 'v-match'}`}>{row.outcome}</td>;
                })}</tr>
              ))}
              <tr><td>Cost, permits, vehicles, comms</td>{sites.map(i => <td key={i} className="num muted">not checked</td>)}</tr>
            </tbody>
          </table>
        </div>

        <section>
          <h2 className="h2">By month</h2>
          <div className="season" role="table" aria-label="Required traits per month">
            <span />{MONTHS.map((m, j) => <span key={m} className="mo" data-in={inWindow.has(j + 1) ? '' : undefined}>{m}</span>)}
            {sites.map((i, k) => [
              <span key={`l${i}`} className="mono small"><span className="swatch" style={{ background: SERIES[k] }} />{coordLabel(data, i)}</span>,
              ...strips[k]!.map((cls, m) => <span key={`${i}-${m}`} className={`c ${cls}`} title={`${MONTHS[m]}: ${CLASS_TEXT[cls]}`}>{cls === 'allMatch' ? '●' : cls === 'someMiss' ? '◆' : '○'}</span>),
            ])}
          </div>
        </section>

        <section>
          <h2 className="h2">Checklist</h2>
          <textarea className="field" value={checklist} onChange={e => onChecklist(e.target.value)} placeholder={'Equipment\nPermits\nPeople\nBudget\nComms\nEmergency access'} />
        </section>
      </>}
    </Page>
  );
}

type Campaign = { campaignId: string; name: string; agency?: string[]; years?: { first: number; last: number }; site?: { name?: string; h3r4?: string } };

export function Risks({ data, request, sites, checklist, onBack }: {
  data: Dataset; request: PlanRequest; sites: number[]; checklist: string; onBack: () => void;
}) {
  const [burned, setBurned] = useState<'loading' | 'ready' | 'missing'>('loading');
  useEffect(() => {
    let live = true;
    ensureMonthly(data, ['burned_pct']).then(() => { if (live) setBurned(data.monthly.burned_pct ? 'ready' : 'missing'); }, () => { if (live) setBurned('missing'); });
    return () => { live = false; };
  }, [data]);
  const pinned = sites.map(i => data.h3[i]!);
  const campaigns = data.runtime.campaigns as Campaign[];

  return (
    <Page title="Risks" back={onBack} aside={
      <div className="row no-print">
        <SheetButton data={data} request={request} sites={sites} />
        <button className="btn btn-line" onClick={() => window.print()}>Print</button>
        <button className="btn btn-primary" disabled={!sites.length}
          onClick={() => download(`mission-brief-${request.objectiveId}.md`, brief(data, request, sites, checklist), 'text/markdown')}>Download brief</button>
      </div>}>
      {!sites.length ? <NoSites /> : <>
        <Tabs.Root defaultValue={String(sites[0])}>
          <Tabs.List className="tabs" aria-label="Compared sites">
            {sites.map((i, k) => <Tabs.Tab key={i} value={String(i)} className="mono"><span className="swatch" style={{ background: SERIES[k] }} />{coordLabel(data, i)}</Tabs.Tab>)}
          </Tabs.List>
          {sites.map(i => <Tabs.Panel key={i} value={String(i)}><SiteRisks data={data} request={request} i={i} burned={burned} /></Tabs.Panel>)}
        </Tabs.Root>

        <section>
          <h2 className="h2">Past campaigns</h2>
          <div className="sheet">
            <table>
              <thead><tr><th>Campaign</th><th>Where</th><th className="num">Years</th><th>Agency</th><th>In a compared cell</th></tr></thead>
              <tbody>
                {campaigns.map(c => (
                  <tr key={c.campaignId}>
                    <td>{c.name}</td><td className="muted">{c.site?.name ?? 'unknown'}</td>
                    <td className="num">{c.years ? (c.years.first === c.years.last ? c.years.first : `${c.years.first}–${c.years.last}`) : 'unknown'}</td>
                    <td>{c.agency?.join(', ') ?? 'unknown'}</td>
                    <td>{c.site?.h3r4 && pinned.includes(c.site.h3r4) ? <span className="v-match">yes</span> : <span className="muted">no</span>}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      </>}
    </Page>
  );
}

const unknown = <span className="v-unknown">unknown</span>;
const finite = (v: number | undefined | null): v is number => v !== undefined && v !== null && Number.isFinite(v);

function SiteRisks({ data, request, i, burned }: { data: Dataset; request: PlanRequest; i: number; burned: 'loading' | 'ready' | 'missing' }) {
  const { events, byCategory, steep } = hazardFacts(data, i);
  const hot = data.yearly.lst_day_max_k?.[i], cold = data.yearly.lst_night_min_k?.[i];
  const fire = burned === 'ready' ? burnedInWindow(data, request, i) : null;
  const unknownTraits = rows(data, request, i).filter(r => r.verdict === 'unknown').length;
  return (
    <div className="cols">
      <section>
        <h2 className="h2">Conditions</h2>
        <div className="kv"><span className="muted">Ground over 30°</span><span className="mono">{finite(steep) ? `${num(steep * 100)} %` : unknown}</span></div>
        <div className="kv"><span className="muted">Hottest day surface</span><span className="mono">{finite(hot) ? `${num(hot - 273.15)} °C` : unknown}</span></div>
        <div className="kv"><span className="muted">Coldest night surface</span><span className="mono">{finite(cold) ? `${num(cold - 273.15)} °C` : unknown}</span></div>
        <div className="kv"><span className="muted">Most burned in window</span><span className="mono">{burned === 'loading' ? '…' : !fire || fire.max === null ? unknown
          : <>{num(fire.max)} %{fire.missing.length > 0 && <span className="v-unknown small"> · no data for {fire.missing.join(', ')}</span>}</>}</span></div>
        <div className="kv"><span className="muted">Traits unknown</span><span className={`mono${unknownTraits ? ' v-unknown' : ''}`}>{unknownTraits}</span></div>
        <div className="kv"><span className="muted">Rescue, weather on the day</span><span className="muted">not checked</span></div>
      </section>
      <section>
        <h2 className="h2">Events on record <span className="muted small">NASA EONET</span></h2>
        {events.length === 0
          ? <p className="muted">None recorded. EONET is curated, so this does not mean safe.</p>
          : <ul className="list">
              {[...byCategory].map(([cat, list]) => (
                <li key={cat}>
                  <span>{cat} <span className="muted">· {list.length}</span></span>
                  {list.slice(0, 4).map(e => (
                    <span key={String(e.event_id)} className="small">
                      <span className="muted mono">{String(e.start_date ?? '').slice(0, 10)}</span>{' '}
                      {e.source_url ? <a href={String(e.source_url)} target="_blank" rel="noreferrer">{String(e.title)}</a> : String(e.title)}
                    </span>
                  ))}
                  {list.length > 4 && <span className="muted small">+{list.length - 4} more</span>}
                </li>
              ))}
            </ul>}
      </section>
    </div>
  );
}
