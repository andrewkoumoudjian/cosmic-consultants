import { Fragment } from 'react';
import { METRICS } from '../data/catalog.ts';
import { DATA_UNCERTAINTY, RECOMMENDED_TESTING, SCIENTIFIC_LIMITATIONS, TRADE_OFFS, VERDICTS, VERIFICATION, type Impact, type TradeOff, type Verdict } from '../data/placeholders/limitations.ts';
import { Button, SectionHeader, Tile } from '../components/ui.tsx';
import { Footer, StepHeader } from '../components/shell.tsx';
import { isRequired, sitesInChart, sitesInPlay, useMission, type Route } from '../state.tsx';
import { formatTarget, MetricText, SiteRefs } from './shared.tsx';

const IMPACT: Record<Impact, { glyph: string; label: string; color: string }> = {
  high: { glyph: '▲', label: 'High', color: 'var(--status-critical)' },
  moderate: { glyph: '■', label: 'Moderate', color: 'var(--status-warning)' },
  low: { glyph: '▼', label: 'Low', color: 'var(--status-good)' },
};

export function Limitations({ go }: { go: (r: Route) => void }) {
  const { mission } = useMission();
  const sites = sitesInChart(mission);
  const reqs = mission.requirements;
  const removed = Object.keys(mission.removed).length;
  const v = VERIFICATION.sample;

  const metPerSite = sites.map((s) => reqs.filter((r) => v[r.metric]?.[s.id]?.verdict === 'supported').length);
  const uncertainCells = reqs.reduce((n, r) => n + sites.filter((s) => v[r.metric]?.[s.id]?.verdict === 'uncertain').length, 0);
  const hardest = reqs.filter((r) => sites.some((s) => v[r.metric]?.[s.id]?.verdict === 'not-reproducible'));
  const hardestNote = hardest.length
    ? (() => {
        const r = hardest[0];
        const partial = sites.filter((s) => v[r.metric]?.[s.id] && v[r.metric][s.id].verdict !== 'not-reproducible');
        return `${METRICS[r.metric].label.replace(' (proxy)', '')}${partial.length ? ` · partial at ${partial.map((s) => s.name.split(' ')[0]).join(', ')} only` : ''}`;
      })()
    : 'None among your requirements';

  return (
    <>
      <StepHeader
        title="Limitation report."
        sub={`How well each site in play supports your ${reqs.length} mission requirements, and what no Earth site can reproduce.`}
        sample
      />
      <div className="step-content report">
        <div className="tiles">
          <Tile label="SITES COMPARED" value={sites.length} note={`Top ${sites.length} of ${sitesInPlay(mission).length} in play · ${removed} removed`} />
          <Tile label="REQUIREMENTS MET" value={metPerSite.length ? `${Math.min(...metPerSite)} – ${Math.max(...metPerSite)}` : '–'} note={`of ${reqs.length}, depending on site`} pending={VERIFICATION} />
          <Tile label="NEEDS MORE EVIDENCE" value={uncertainCells} note="cells marked uncertain" pending={VERIFICATION} />
          <Tile label="HARDEST TO REPRODUCE" value={hardest.length} note={hardestNote} pending={VERIFICATION} />
        </div>

        <section data-pending={VERIFICATION.id}>
          <SectionHeader
            title="Requirements verification matrix"
            sub="Each requirement checked at every site, against what that site can physically reproduce."
            pending={[VERIFICATION]}
            right={
              <span className="t-small t-muted">
                <b className="t-text">Bold</b> = required &nbsp;&nbsp; Regular = preferred
              </span>
            }
          />
          <div className="verdict-key t-small t-muted">
            {(Object.keys(VERDICTS) as Verdict[]).map((k) => (
              <span key={k}>
                <span style={{ color: VERDICTS[k].color }} className="t-control">
                  {VERDICTS[k].glyph}
                </span>{' '}
                {VERDICTS[k].label}
              </span>
            ))}
          </div>
          <div className="grid-table matrix" style={{ gridTemplateColumns: `minmax(180px, 230px) minmax(110px, 126px) repeat(${Math.max(sites.length, 1)}, minmax(110px, 1fr))` }} role="table">
            <div className="grid-table__head" role="row">
              <span role="columnheader">REQUIREMENT</span>
              <span role="columnheader">{mission.world === 'moon' ? 'LUNAR' : 'MARTIAN'} TARGET</span>
              {sites.map((s) => (
                <span key={s.id} role="columnheader" className="with-swatch">
                  <SiteRefs sites={[s.id]} upper />
                </span>
              ))}
            </div>
            {reqs.map((r) => (
              <div className="grid-table__row" role="row" key={r.metric}>
                <span role="cell" className={isRequired(r) ? 't-strong' : 't-body'}>
                  {METRICS[r.metric].label.replace(' (proxy)', '')}
                </span>
                <span role="cell" className="t-body t-muted">
                  {formatTarget(r)}
                </span>
                {sites.map((s) => {
                  const cell = v[r.metric]?.[s.id];
                  return (
                    <span role="cell" key={s.id} className="verdict-cell">
                      {cell ? (
                        <>
                          <span className="t-control" style={{ color: VERDICTS[cell.verdict].color }} aria-label={VERDICTS[cell.verdict].label}>
                            {VERDICTS[cell.verdict].glyph}
                          </span>
                          <span className="t-body">{cell.value}</span>
                        </>
                      ) : (
                        <span className="t-small t-muted" title={`No sample for this cell. Awaits ${VERIFICATION.id}.`}>
                          no data
                        </span>
                      )}
                    </span>
                  );
                })}
              </div>
            ))}
            <div className="grid-table__row" role="row">
              <span role="cell" className="t-body">Requirements met</span>
              <span role="cell" />
              {sites.map((s, i) => (
                <span role="cell" key={s.id} className="t-body">
                  {metPerSite[i]} of {reqs.length}
                </span>
              ))}
            </div>
          </div>
        </section>

        <section data-pending={SCIENTIFIC_LIMITATIONS.id}>
          <SectionHeader title="Scientific limitations" sub="Physical and environmental conditions each site cannot reproduce, rated by impact on this mission." pending={[SCIENTIFIC_LIMITATIONS]} />
          <div className="grid-table limits" style={{ gridTemplateColumns: `minmax(220px, 336px) repeat(${Math.max(sites.length, 1)}, minmax(96px, 1fr)) minmax(150px, 200px)` }} role="table">
            <div className="grid-table__head" role="row">
              <span role="columnheader">LIMITATION</span>
              {sites.map((s) => (
                <span key={s.id} role="columnheader" className="with-swatch">
                  <SiteRefs sites={[s.id]} upper />
                </span>
              ))}
              <span role="columnheader">ACROSS SITES</span>
            </div>
            {SCIENTIFIC_LIMITATIONS.sample.map((l) => {
              const ratings = sites.map((s) => l.impact[s.id]);
              return (
                <div className="grid-table__row grid-table__row--tall" role="row" key={l.name}>
                  <span role="cell" className="stack">
                    <span className="t-control">{l.name}</span>
                    <span className="t-small t-muted">{l.detail[mission.world]}</span>
                  </span>
                  {ratings.map((imp, i) => (
                    <span role="cell" key={sites[i].id} className="impact t-small">
                      {imp ? (
                        <>
                          <span style={{ color: IMPACT[imp].color }} aria-hidden>
                            {IMPACT[imp].glyph}
                          </span>
                          {IMPACT[imp].label}
                        </>
                      ) : (
                        <span className="t-muted">no data</span>
                      )}
                    </span>
                  ))}
                  <span role="cell" className="t-small t-muted">
                    {acrossSites(ratings, sites.map((s) => s.name))}
                  </span>
                </div>
              );
            })}
          </div>
        </section>

        <section data-pending={TRADE_OFFS.id}>
          <SectionHeader title="Trade-off analysis" sub="Which limitations can be managed, and which constrain what any of these sites can conclude." pending={[TRADE_OFFS]} />
          <div className="tradeoffs">
            <TradeOffCard kind="managed" items={TRADE_OFFS.sample.managed} />
            <TradeOffCard kind="constraining" items={TRADE_OFFS.sample.constraining} />
          </div>
        </section>

        <div className="two-col evidence">
          <section data-pending={DATA_UNCERTAINTY.id}>
            <SectionHeader title="Data uncertainty & missing evidence" sub="Where each site's data is too coarse, indirect, or absent to support a verdict." pending={[DATA_UNCERTAINTY]} />
            <ul className="evidence-list">
              {DATA_UNCERTAINTY.sample.map((g, i) => (
                <li key={i}>
                  <div className="evidence-list__badge">
                    <span className={`badge badge--${g.kind}`}>{g.kind.toUpperCase()}</span>
                    <span className="t-small t-muted">{g.spread}</span>
                  </div>
                  <div className="stack">
                    <SiteRefs sites={g.sites} />
                    <p className="t-body">
                      <MetricText text={g.text} />
                    </p>
                  </div>
                </li>
              ))}
            </ul>
          </section>
          <section data-pending={RECOMMENDED_TESTING.id}>
            <SectionHeader title="Recommended additional testing" sub="Ordered by how much uncertainty each test removes across the sites in play." pending={[RECOMMENDED_TESTING]} />
            <ol className="tests-list">
              {RECOMMENDED_TESTING.sample.map((t, i) => (
                <li key={i}>
                  <span className="t-small t-muted">{String(i + 1).padStart(2, '0')}</span>
                  <div className="stack">
                    <div className="row">
                      <span className="t-control">{t.title}</span>
                      <span className="flex" />
                      <span className="t-small t-muted nowrap">{t.where}</span>
                    </div>
                    <p className="t-body t-muted">
                      <MetricText text={t.effect} />
                    </p>
                    <SiteRefs sites={t.sites} />
                  </div>
                </li>
              ))}
            </ol>
          </section>
        </div>
      </div>
      <Footer onBack={() => go('sites')} status={`${sites.length} sites compared`}>
        <Button onClick={() => go('logistics')}>Compare logistics →</Button>
      </Footer>
    </>
  );
}

function acrossSites(ratings: (Impact | undefined)[], names: string[]): string {
  const known = ratings.map((r, i) => ({ r, name: names[i] })).filter((x): x is { r: Impact; name: string } => !!x.r);
  if (!known.length) return 'No data';
  if (known.every((x) => x.r === known[0].r)) return 'Same at every site';
  const rank: Record<Impact, number> = { low: 0, moderate: 1, high: 2 };
  const min = Math.min(...known.map((x) => rank[x.r]));
  const max = Math.max(...known.map((x) => rank[x.r]));
  const lows = known.filter((x) => rank[x.r] === min);
  const highs = known.filter((x) => rank[x.r] === max);
  if (lows.length === 1) return `Differs · ${lows[0].name.split(' ')[0]} closest`;
  if (highs.length === 1) return `Differs · ${highs[0].name.split(' ')[0]} furthest`;
  return 'Differs by site';
}

function TradeOffCard({ kind, items }: { kind: 'managed' | 'constraining'; items: TradeOff[] }) {
  const { mission } = useMission();
  return (
    <div className="card tradeoff">
      <div className="card__header t-small">
        <span className="t-control" style={{ color: kind === 'managed' ? 'var(--status-good)' : 'var(--status-critical)' }} aria-hidden>
          {kind === 'managed' ? '✓' : '×'}
        </span>
        <span>{kind === 'managed' ? 'CAN BE MANAGED' : 'CONSTRAINS CONCLUSIONS'}</span>
        <span className="flex" />
        <span className="t-muted">{items.length} limitations</span>
      </div>
      {items.map((t) => (
        <Fragment key={t.name}>
          <div className="divider" />
          <div className="tradeoff__item">
            <div className="row">
              <span className="t-control">{t.name}</span>
              <span className="flex" />
              <span className="t-small t-muted">{t.scope}</span>
            </div>
            <p className="t-small t-muted">{t.text.replace('lunar', mission.world === 'moon' ? 'lunar' : 'Martian')}</p>
            <p className="t-small">
              Affects:{' '}
              {t.affects.map((id, i) => (
                <Fragment key={id}>
                  {i > 0 && ', '}
                  <MetricText text={`{${id}}`} />
                </Fragment>
              ))}
            </p>
          </div>
        </Fragment>
      ))}
    </div>
  );
}
