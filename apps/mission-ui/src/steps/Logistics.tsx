/**
 * Step 6 Logistics (owner round 2): four flashcards side by side, then one 12-month feasibility bar in four colours.
 * Every value is the release's own; a missing value says "no data" (AGENTS.md rule 3).
 *
 * Month colour, in this order (first that applies):
 *   red     a required trait misses that month
 *   orange  a required trait has no data that month
 *   yellow  the traits fit, but ground temperature is ≥ 35 °C by day or ≤ −20 °C by night (the same thresholds as the
 *           Risk step), or temperature was not measured that month
 *   green   the traits fit and the temperature is inside those limits
 */
import { useEffect, useState } from 'react';
import { ensureMonthly } from '../../../atlas/src/planner/data.ts';
import { months, type Dataset } from '../../../atlas/src/planner/engine.ts';
import type { PlanRequest } from '../../../atlas/src/plan-url.ts';
import { MONTHS, elevRange, fmt, seasonStrip } from '../model.ts';
import { NavFoot, NeedSites, SiteTabs, SiteTag, StepHead } from '../ui.tsx';
import { CampaignAllocation, type EngineProps } from '../engine-results-ui.tsx';

type Go = 'go' | 'caution' | 'gap' | 'nogo';
const GO_TEXT: Record<Go, string> = { go: 'Go', caution: 'Caution', gap: 'Data gap', nogo: 'No-go' };
const GO_WHY: Record<Go, string> = {
  go: 'Required traits fit and ground temperature is workable',
  caution: 'Required traits fit, but ground temperature is extreme or not measured',
  gap: 'A required trait has no data',
  nogo: 'A required trait misses your band',
};
const GO_COLOR: Record<Go, string> = { go: '#22c55e', caution: '#eab308', gap: '#f97316', nogo: '#ef4444' };
const HOT_K = 308.15, COLD_K = 253.15;

function feasibility(data: Dataset, request: PlanRequest, i: number): { go: Go; note: string }[] {
  const strip = seasonStrip(data, request, i);
  const day = data.monthly.lst_day_k, night = data.monthly.lst_night_k;
  return strip.map((c, m) => {
    if (c === 'someMiss') return { go: 'nogo', note: GO_WHY.nogo };
    if (c === 'noMissSomeUnknown') return { go: 'gap', note: GO_WHY.gap };
    const d = day?.[i * 12 + m], n = night?.[i * 12 + m];
    const dk = d !== undefined && Number.isFinite(d) ? d : null, nk = n !== undefined && Number.isFinite(n) ? n : null;
    const temps = `day ${fmt(dk, 'K') ?? 'no data'}, night ${fmt(nk, 'K') ?? 'no data'}`;
    if (dk === null || nk === null || dk >= HOT_K || nk <= COLD_K) return { go: 'caution', note: `${GO_WHY.caution} (${temps})` };
    return { go: 'go', note: `${GO_WHY.go} (${temps})` };
  });
}

function Flash({ label, value, caption, lines }: { label: string; value: string | null; caption: string; lines: [string, string | null][] }) {
  return (
    <section className="flash">
      <h2 className="flash-label">{label}</h2>
      <p className={`flash-value${value ? '' : ' none'}`}>{value ?? 'no data'}</p>
      <p className="flash-caption">{caption}</p>
      <dl className="flash-lines">
        {lines.map(([k, v]) => <div key={k}><dt>{k}</dt><dd className={v ? undefined : 'none'}>{v ?? 'no data'}</dd></div>)}
      </dl>
    </section>
  );
}

export function Logistics({ data, request, sites, onSites, onBack, onNext, engine, targetId, onTarget }: EngineProps & {
  data: Dataset; request: PlanRequest; sites: number[]; onSites: () => void; onBack: () => void; onNext: () => void;
}) {
  const [k, setK] = useState(0);
  const [temps, setTemps] = useState<'loading' | 'ready' | 'missing'>('loading');
  useEffect(() => {
    let live = true;
    ensureMonthly(data, ['lst_day_k', 'lst_night_k']).then(() => { if (live) setTemps('ready'); }, () => { if (live) setTemps('missing'); });
    return () => { live = false; };
  }, [data]);
  const kk = Math.min(k, Math.max(sites.length - 1, 0));
  const i = sites[kk];
  const y = (c: string) => (i === undefined ? undefined : data.yearly[c]?.[i]);
  const inWin = new Set(months(request));
  const go = i !== undefined && temps !== 'loading' ? feasibility(data, request, i) : null;

  return (
    <div className="page">
      <StepHead step={6} context={sites.length > 1 ? <SiteTabs data={data} sites={sites} value={kk} onChange={setK} />
        : sites.length === 1 ? <span className="bubble"><SiteTag data={data} i={sites[0]!} k={0} /></span> : undefined} />
      {i === undefined ? <NeedSites onSites={onSites} /> : <>
        <div className="flash-row">
          <Flash label="Access" value={fmt(y('access_min_median'), 'min')} caption="Median travel to a city" lines={[['Nearest airport', fmt(y('airport_km'), 'km')]]} />
          <Flash label="Terrain" value={fmt(y('slope_mean_deg'), 'deg')} caption="Mean slope" lines={[['Elevation', elevRange(y('elev_min_m'), y('elev_max_m'))]]} />
          <Flash label="Surface" value={fmt(y('barren_pct'), '%')} caption="Bare ground" lines={[['Water', fmt(y('water_pct'), '%')], ['Snow and ice', fmt(y('snow_ice_pct'), '%')]]} />
          <Flash label="Permits" value={fmt(y('protected_pct'), '%')} caption="Protected land" lines={[['Towns, roads, cell signal', null]]} />
        </div>

        <section className="card season-card" aria-label="Seasonal feasibility">
          <h2 className="card-title">Seasonal feasibility</h2>
          {temps === 'loading' ? <p className="t-small muted">Loading monthly data…</p> : <>
            <div className="go-bar" role="img"
              aria-label={go!.map((g, m) => `${MONTHS[m]} ${GO_TEXT[g.go]}`).join('; ')}>
              {go!.map((g, m) => <span key={m} style={{ background: GO_COLOR[g.go] }} title={`${MONTHS[m]}: ${GO_TEXT[g.go]}. ${g.note}.`} />)}
            </div>
            <div className="go-months">{MONTHS.map((m, j) => <span key={m} data-in={inWin.has(j + 1) ? '' : undefined}>{m}</span>)}</div>
            <div className="go-legend">
              {(Object.keys(GO_TEXT) as Go[]).map(g => <span key={g} title={GO_WHY[g]}><i style={{ background: GO_COLOR[g] }} />{GO_TEXT[g]}</span>)}
            </div>
          </>}
        </section>
      </>}
      <CampaignAllocation data={data} request={request} engine={engine} targetId={targetId} onTarget={onTarget} />
      <NavFoot onBack={onBack} onNext={onNext} nextLabel="Risk assessment" />
    </div>
  );
}
