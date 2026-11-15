/**
 * Step 8 Past missions: the Google Doc's "past missions database, like a spreadsheet", from campaigns.json.
 * Every field is quoted from a stored source; a field the sources don't give says "not recorded" (AGENTS.md rule 3).
 * "Your plan at this site" runs the engine on the campaign's own cell, so you can see how a classic site fares.
 */
import { Fragment, useState } from 'react';
import type { Dataset } from '../../../atlas/src/planner/engine.ts';
import type { PlanRequest } from '../../../atlas/src/plan-url.ts';
import { DIMENSION_LABEL, coordLabel, traitCells, siteClass } from '../model.ts';
import { Card, NavFoot, StepHead, Verdict } from '../ui.tsx';

type Q = { quote?: string; sourceRef?: string };
type Campaign = {
  campaignId: string; name: string; agency?: string[]; years?: { first: number; last: number };
  site?: { name?: string; h3r4?: string; lat?: number; lon?: number } & Q;
  objectivesExercised?: ({ objectiveId?: string | null; text: string } & Q)[];
  publishedConstraints?: ({ what: string; value?: number | string; unit?: string } & Q)[];
  outcome?: ({ kind: 'worked' | 'lesson'; text: string } & Q)[];
  nulls?: { field: string; reason: string }[];
  sources?: { ref: string; url?: string; fetchedAt?: string; licenceNote?: string; sha256?: string }[];
};

const NR = <span className="muted" style={{ fontStyle: 'italic' }}>not recorded</span>;
const years = (c: Campaign) => (c.years ? (c.years.first === c.years.last ? String(c.years.first) : `${c.years.first}–${c.years.last}`) : null);

export function PastMissions({ data, request, onBack }: { data: Dataset; request: PlanRequest; sites: number[]; onBack: () => void }) {
  const campaigns = data.runtime.campaigns as Campaign[];
  const [sel, setSel] = useState<string | null>(campaigns[0]?.campaignId ?? null);
  const c = campaigns.find(x => x.campaignId === sel) ?? null;
  const worked = campaigns.reduce((n, x) => n + (x.outcome ?? []).filter(o => o.kind === 'worked').length, 0);
  const lessons = campaigns.reduce((n, x) => n + (x.outcome ?? []).filter(o => o.kind === 'lesson').length, 0);

  return (
    <div className="page">
      <StepHead step={8} />
      <div className="ll-grid">
        <Card title="Past analog missions" aside={<span className="t-label muted">{campaigns.length} missions · {worked} worked · {lessons} lessons</span>}>
          <ul className="ll-list" role="listbox" aria-label="Past analog missions">
            {campaigns.map(x => {
              const w = (x.outcome ?? []).filter(o => o.kind === 'worked').length, l = (x.outcome ?? []).filter(o => o.kind === 'lesson').length;
              return (
                <li key={x.campaignId} role="option" aria-selected={x.campaignId === sel} tabIndex={0} className="ll-row" data-active={x.campaignId === sel ? '' : undefined}
                  onClick={() => setSel(x.campaignId)} onKeyDown={e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); setSel(x.campaignId); } }}>
                  <span className="ll-main"><span className="ll-name">{x.name}</span><span className="t-label muted">{x.site?.name ?? 'Site not recorded'}</span></span>
                  <span className="ll-side"><span className="mono t-small">{years(x) ?? '–'}</span>
                    <span className="t-label">{w > 0 && <span className="g-match">{w} worked</span>}{w > 0 && l > 0 && ' · '}{l > 0 && <span className="g-miss">{l} lesson{l > 1 ? 's' : ''}</span>}</span></span>
                </li>
              );
            })}
          </ul>
        </Card>
        {c && <MissionDetail data={data} request={request} c={c} />}
      </div>
      <NavFoot onBack={onBack} />
    </div>
  );
}

function MissionDetail({ data, request, c }: { data: Dataset; request: PlanRequest; c: Campaign }) {
  const i = c.site?.h3r4 ? data.h3.indexOf(c.site.h3r4) : -1;
  const cls = i >= 0 ? siteClass(data, request, i) : null;
  const refs = new Map((c.sources ?? []).map(s => [s.ref, s]));
  const cite = (q: Q) => q.sourceRef ? <a href={refs.get(q.sourceRef)?.url} target="_blank" rel="noreferrer" title={q.quote}>[{q.sourceRef}]</a> : null;
  return (
    <Card title={c.name} aside={<span className="t-label muted">{[c.agency?.join(', '), years(c)].filter(Boolean).join(' · ')}</span>}>
      <div className="stack" style={{ gap: 16 }}>
        <Section title="Objectives">{c.objectivesExercised?.length ? c.objectivesExercised.map((o, n) => <p key={n} className="t-small text-2">{o.text} {cite(o)}</p>) : NR}</Section>
        <Section title="Conditions">{c.publishedConstraints?.length ? c.publishedConstraints.map((p, n) => <p key={n} className="t-small text-2">{p.what}{p.value !== undefined && <>: <span className="mono">{p.value}{p.unit ? ` ${p.unit}` : ''}</span></>} {cite(p)}</p>) : NR}</Section>
        <Section title="What worked, what to change">{c.outcome?.length ? c.outcome.map((o, n) => <p key={n} className="t-small text-2"><span className={`verdict ${o.kind === 'worked' ? 'match' : 'miss'}`} style={{ marginRight: 6 }}><span className="g">{o.kind === 'worked' ? '●' : '◆'}</span>{o.kind === 'worked' ? 'Worked' : 'Lesson'}</span>{o.text} {cite(o)}</p>) : NR}</Section>
        <Section title={`Your plan at this site${i >= 0 ? ` · ${coordLabel(data, i)}` : ''}`}>
          {i >= 0 && cls ? <div className="chips">{traitCells(data, request, i).map(t => <span key={t.dimension} className="bubble" title={t.detail}><Verdict v={t.verdict}>{DIMENSION_LABEL[t.dimension]}</Verdict></span>)}</div>
            : <p className="t-small muted">No cell to check.</p>}
        </Section>
      </div>
    </Card>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return <Fragment><div className="stack" style={{ gap: 6 }}><span className="t-label text-2" style={{ textTransform: 'uppercase', letterSpacing: '.08em' }}>{title}</span>{children}</div></Fragment>;
}
