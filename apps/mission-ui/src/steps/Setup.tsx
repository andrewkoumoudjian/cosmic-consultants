/** Steps 1 Destination, 2 Test, 3 Requirements. Logic follows apps/planner/src/steps/Setup.tsx. */
import { useEffect, useState } from 'react';
import { requirements, type Dataset } from '../../../atlas/src/planner/engine.ts';
import { LIMITS, MISSION_TYPES, validatePlan, type Dimension, type LimitKey, type MissionType, type PlanRequest } from '../../../atlas/src/plan-url.ts';
import { RadioGroup } from '@base-ui/react/radio-group';
import { Radio } from '@base-ui/react/radio';
import { Input } from '@base-ui/react/input';
import { Toggle } from '@base-ui/react/toggle';
import { COLUMN_LABEL, DIMENSION_LABEL, MONTHS, objectiveTitle, objectivesFor, pickObjective, unitLabel, updateBandEdit, withDefaultPriorities, type Body, type Category } from '../model.ts';
import { Button, Card, NavFoot, NumInput, Seg, Select, StepHead } from '../ui.tsx';
import { Planet } from '../three/Planet.tsx';
import { CategoryCoverage } from '../engine-results-ui.tsx';

const WORLD = {
  moon: { name: 'Moon', gravity: '0.17 g', air: 'No air (vacuum)', note: 'Polar terrain, low sun, cold traps and sharp regolith.' },
  mars: { name: 'Mars', gravity: '0.38 g', air: 'Thin CO₂ air', note: 'Dust, cold deserts, ancient water and ground ice.' },
} as const;

export function Destination({ data, body, onBody, onNext }: { data: Dataset; body: Body; onBody: (b: Body) => void; onNext: () => void }) {
  const [hover, setHover] = useState<Body | null>(null);
  return (
    <div className="page">
      <header className="hero">
        <h1 className="hero-title">Analog Atlas</h1>
        <p className="hero-sub">Find the places on Earth that best stand in for the Moon and Mars.</p>
      </header>
      <RadioGroup className="worlds" aria-label="Destination" value={body} onValueChange={v => onBody(v as Body)}>
        {(['moon', 'mars'] as const).map(id => {
          const w = WORLD[id];
          const objs = objectivesFor(data, id);
          return (
            <Radio.Root key={id} value={id} className="world" data-world={id} render={<div />}
              onMouseEnter={() => setHover(id)} onMouseLeave={() => setHover(null)}>
              <div className="world-art"><Planet world={id} hovered={hover === id} label={`${w.name}, illustrative`} /></div>
              <div className="world-name">{w.name}<span className="radio"><Radio.Indicator className="radio-dot" /></span></div>
              <p className="text-2">{w.note}</p>
              <div className="chips">
                <span className={`bubble ${id}`}>Gravity {w.gravity}</span>
                <span className={`bubble ${id}`}>{w.air}</span>
                <span className="bubble">{objs.length} NASA objective{objs.length === 1 ? '' : 's'}</span>
              </div>
            </Radio.Root>
          );
        })}
      </RadioGroup>
      <NavFoot onNext={onNext} hint={`Planning for the ${WORLD[body].name}`} />
    </div>
  );
}

type CategoryMeta = Category & { group?: string };

export function CategoryStep({ data, body, categoryId, onCategory, onBack, onNext }: {
  data: Dataset; body: Body; categoryId?: string; onCategory: (id: string) => void; onBack: () => void; onNext: () => void;
}) {
  const cats = data.runtime.categories as CategoryMeta[];
  const groups = [...new Set(cats.map(c => c.group ?? 'Other'))];
  return (
    <div className="page">
      <StepHead step={2} context={<span className={`bubble ${body}`}>{WORLD[body].name}</span>} />
      <RadioGroup className="cat-board" aria-label="Test category" value={categoryId ?? null} onValueChange={v => onCategory(v as string)}>
        {groups.map(g => (
          <section key={g} className="cat-group">
            <h2>{g}</h2>
            {cats.filter(c => (c.group ?? 'Other') === g).map(c => {
              const { objectiveId, supported } = pickObjective(data, body, c);
              const obj = data.objectives.find(o => o.objectiveId === objectiveId);
              return (
                <Radio.Root key={c.categoryId} value={c.categoryId} className="cat" disabled={!supported.length} render={<div />}
                  title={supported.length && obj ? `Tests ${objectiveTitle(obj)} (${objectiveId})` : 'No Earth data for its traits yet'}>
                  <span className="cat-name">{c.name}<span className="radio"><Radio.Indicator className="radio-dot" /></span></span>
                  <span className="cat-traits">{supported.length ? supported.map(d => DIMENSION_LABEL[d]).join(' · ') : 'No Earth data yet'}</span>
                </Radio.Root>
              );
            })}
          </section>
        ))}
      </RadioGroup>
      <NavFoot onBack={onBack} onNext={onNext} nextDisabled={!categoryId} hint={categoryId ? undefined : 'Pick one test to continue'} />
    </div>
  );
}

const MONTH_OPTIONS = MONTHS.map((m, i) => ({ value: String(i + 1), label: m }));
const TYPE_LABEL: Record<MissionType, string> = { robotic: 'Robotic', crewed: 'Crewed', instrument: 'Instrument' };
const LIMIT_LABEL: Record<LimitKey, { label: string; unit: string }> = {
  access: { label: 'Travel to a city', unit: 'min' }, protected: { label: 'Protected land', unit: '%' },
  airport: { label: 'Distance to an airport', unit: 'km' }, slope: { label: 'Mean slope', unit: '°' },
};

type Draft = { lo: string; hi: string; hiStrict: boolean };
const badDraft = (d: Pick<Draft, 'lo' | 'hi'>) => d.lo.trim() === '' || d.hi.trim() === '' || !Number.isFinite(Number(d.lo)) || !Number.isFinite(Number(d.hi)) || Number(d.lo) > Number(d.hi);

export function Requirements({ data, category, request, onRequest, onBlocked, onBack, onNext }: {
  data: Dataset; category: Category; request: PlanRequest; onRequest: (r: PlanRequest) => void;
  onBlocked: (blocked: boolean) => void; onBack: () => void; onNext: () => void;
}) {
  const rules = requirements(data, request);
  const errors = validatePlan(request);
  const [draftState, setDraftState] = useState<{ objectiveId: string; byDim: Record<string, Draft> }>({ objectiveId: request.objectiveId, byDim: {} });
  const drafts = draftState.objectiveId === request.objectiveId ? draftState.byDim : {};
  const setDrafts = (f: (x: Record<string, Draft>) => Record<string, Draft>) => setDraftState({ objectiveId: request.objectiveId, byDim: f(drafts) });
  const blocked = rules.some(r => drafts[r.dimension] && badDraft(drafts[r.dimension]!));
  useEffect(() => { setDraftState({ objectiveId: request.objectiveId, byDim: {} }); }, [request.objectiveId]);
  useEffect(() => { onBlocked(blocked); }, [blocked]);
  useEffect(() => () => onBlocked(false), []);

  const setPriority = (d: Dimension, p: 'must' | 'nice') => {
    const must = (request.must ?? []).filter(x => x !== d), nice = (request.nice ?? []).filter(x => x !== d);
    onRequest({ ...request, must: p === 'must' ? [...must, d] : must, nice: p === 'nice' ? [...nice, d] : nice });
  };
  const setBand = (d: Dimension, lo: string, hi: string, hiStrict?: boolean) => {
    const strict = hiStrict ?? drafts[d]?.hiStrict ?? rules.find(r => r.dimension === d)?.band?.hiStrict ?? false;
    setDrafts(x => ({ ...x, [d]: { lo, hi, hiStrict: strict } }));
    if (badDraft({ lo, hi })) return;
    onRequest(updateBandEdit(request, d, Number(lo), Number(hi), strict));
  };
  const resetBand = (d: Dimension) => {
    setDrafts(x => { const y = { ...x }; delete y[d]; return y; });
    onRequest({ ...request, bandEdits: (request.bandEdits ?? []).filter(e => e.dimension !== d) });
  };
  const setLimit = (k: LimitKey, v: number | undefined) => {
    const limits = { ...(request.limits ?? {}) };
    if (v === undefined) delete limits[k]; else limits[k] = v;
    onRequest({ ...request, limits: Object.keys(limits).length ? limits : undefined });
  };

  const monthSel = (which: 'start' | 'end') => (
    <Select label={which === 'start' ? 'First month' : 'Last month'} value={String(request.months[which])} options={MONTH_OPTIONS}
      onChange={m => onRequest({ ...request, months: { ...request.months, [which]: Number(m) } })} />
  );

  return (
    <div className="page">
      <StepHead step={3} context={<>
        <span className={`bubble ${request.body}`}>{WORLD[request.body].name}</span>
        <span className="bubble">{category.name}</span>
      </>} />

      <CategoryCoverage data={data} category={category} request={request} />
      <div className="req-grid">
        <Card title="Traits" aside={
          <Select label="Objective" value={request.objectiveId} onChange={id => onRequest(withDefaultPriorities(data, { ...request, objectiveId: id }))}
            options={objectivesFor(data, request.body).map(o => ({ value: o.objectiveId, label: objectiveTitle(o) }))} />}>
          <div className="table-wrap">
            <table className="req-table">
              <thead><tr><th>Trait</th><th>Low</th><th className="c">Range</th><th>High</th><th>Unit</th><th>Priority</th></tr></thead>
              <tbody>
                {rules.map(r => {
                  const draft = drafts[r.dimension];
                  const lo = draft?.lo ?? (r.band ? String(r.band.lo) : ''), hi = draft?.hi ?? (r.band ? String(r.band.hi) : '');
                  const strict = draft?.hiStrict ?? r.band?.hiStrict ?? false;
                  const bad = !!draft && badDraft(draft);
                  const edited = request.bandEdits?.some(e => e.dimension === r.dimension);
                  const name = DIMENSION_LABEL[r.dimension] ?? r.dimension;
                  const measure = r.earthColumn ? `${COLUMN_LABEL[r.earthColumn] ?? r.earthColumn}${r.table === 'L1m' ? ', by month' : ''}` : 'No Earth data yet';
                  return (
                    <tr key={r.dimension} className={r.priority === 'must' ? 'req' : 'pref'}>
                      <td title={measure}>
                        <span className="req-name">{name}</span>
                        {(edited || draft) && <Button className="link req-reset" onClick={() => resetBand(r.dimension)} title="Back to the published band">reset</Button>}
                      </td>
                      {r.earthColumn ? <>
                        <td><Input className="input" inputMode="decimal" aria-label={`${name} low`} value={lo} placeholder="low" aria-invalid={bad || undefined} onValueChange={v => setBand(r.dimension, v, hi)} /></td>
                        <td className="c"><Toggle className="op" disabled={lo.trim() === '' && hi.trim() === ''} pressed={strict}
                          aria-label={`${name}: ${strict ? 'upper value excluded' : 'upper value included'}`} title="Include or exclude the upper value"
                          onPressedChange={p => setBand(r.dimension, lo, hi, p)}>≤ x {strict ? '<' : '≤'}</Toggle></td>
                        <td><Input className="input" inputMode="decimal" aria-label={`${name} high`} value={hi} placeholder="high" aria-invalid={bad || undefined} onValueChange={v => setBand(r.dimension, lo, v)} /></td>
                        <td className="mono muted">{unitLabel(r.unit).trim() || '–'}</td>
                      </> : <td colSpan={4} className="muted">No Earth data yet</td>}
                      <td><Seg label={`${name} priority`} value={r.priority ?? 'must'} onChange={p => setPriority(r.dimension, p)}
                        options={[{ value: 'must', label: 'Required' }, { value: 'nice', label: 'Preferred' }]} /></td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
          {blocked && <p className="note warn">Each band needs a low and a high number, with low ≤ high.</p>}
        </Card>

        <div className="req-pair">
          <Card title="Hard limits">
            <div className="table-wrap">
              <table className="req-table">
                <thead><tr><th>Limit</th><th>Maximum</th><th>Unit</th></tr></thead>
                <tbody>
                  {(Object.keys(LIMITS) as LimitKey[]).map(k => (
                    <tr key={k}>
                      <td>{LIMIT_LABEL[k].label}</td>
                      <td><NumInput label={LIMIT_LABEL[k].label} min={0} max={Number.isFinite(LIMITS[k].max) ? LIMITS[k].max : undefined} placeholder="none"
                        value={request.limits?.[k]} onChange={v => setLimit(k, v)} /></td>
                      <td className="mono muted">{LIMIT_LABEL[k].unit}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Card>
          <Card title="Field plan">
            <div className="table-wrap">
              <table className="req-table">
                <thead><tr><th>Setting</th><th>Value</th><th>Unit</th></tr></thead>
                <tbody>
                  <tr><td>Field window</td><td><span className="row" style={{ flexWrap: 'nowrap', gap: 6 }}>{monthSel('start')}<span className="muted">to</span>{monthSel('end')}</span></td><td className="mono muted">month</td></tr>
                  <tr><td>Mission type</td><td><Select label="Mission type" value={request.missionType} options={MISSION_TYPES.map(t => ({ value: t, label: TYPE_LABEL[t] }))} onChange={t => onRequest({ ...request, missionType: t })} /></td><td /></tr>
                  <tr><td>Duration</td><td><NumInput label="Days" min={1} value={request.durationDays} onChange={v => onRequest({ ...request, durationDays: v })} /></td><td className="mono muted">days</td></tr>
                  <tr><td>Team size</td><td><NumInput label="Team size" min={1} value={request.teamSize} onChange={v => onRequest({ ...request, teamSize: v })} /></td><td className="mono muted">people</td></tr>
                  <tr><td>Sites per page</td><td><Select label="Sites per page" value={String(request.top ?? 50)} options={['25', '50', '100'].map(v => ({ value: v, label: v }))} onChange={v => onRequest({ ...request, top: Number(v) })} /></td><td /></tr>
                </tbody>
              </table>
            </div>
          </Card>
        </div>
      </div>

      {errors.length > 0 && <p className="note warn">{errors.join('. ')}.</p>}
      <NavFoot onBack={onBack} onNext={onNext} nextLabel="Find sites" nextDisabled={errors.length > 0 || blocked} />
    </div>
  );
}
