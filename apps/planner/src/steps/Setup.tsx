/** Steps 01 Location, 02 Mission category, 03 Metrics (Figma frames 33:340, 33:400, 33:521). */
import { useState } from 'react';
import { RadioGroup } from '@base-ui/react/radio-group';
import { Radio } from '@base-ui/react/radio';
import { requirements, type Dataset } from '../../../atlas/src/planner/engine.ts';
import { LIMITS, MISSION_TYPES, validatePlan, type Dimension, type LimitKey, type MissionType, type PlanRequest } from '../../../atlas/src/plan-url.ts';
import { COLUMN_LABEL, DIMENSION_LABEL, MONTHS, bandLabel, objectivesFor, pickObjective, supportedTraits, withDefaultPriorities, type Body, type Category } from '../model.ts';
import { Footer, RadioDot, Select, StepHeader } from '../ui.tsx';
import moonArt from '../assets/moon-illustration.png';
import marsArt from '../assets/mars-illustration.png';

const plural = (n: number, w: string) => `${n} ${w}${n === 1 ? '' : 's'}`;
type Nav = { reached: number; onStep: (n: number) => void };
type CategoryMeta = Category & { group?: string; primaryInputsText?: string; documentSupportLabel?: string };

export function Location({ data, body, onBody, onNext, reached, onStep }: Nav & {
  data: Dataset; body: Body; onBody: (b: Body) => void; onNext: () => void;
}) {
  const worlds = [
    { id: 'moon' as const, name: 'Moon', art: moonArt, note: plural(objectivesFor(data, 'moon').length, 'objective') + ' in this release' },
    { id: 'mars' as const, name: 'Mars', art: marsArt, note: plural(objectivesFor(data, 'mars').length, 'objective') + ' in this release' },
  ];
  return (
    <>
      <StepHeader title="Where are you going?" lede="Choose the world your mission is preparing for. We then look for places on Earth that can stand in for parts of it."
        step={1} reached={reached} onStep={onStep} />
      <div className="content">
        <RadioGroup value={body} onValueChange={v => onBody(v as Body)} className="worlds" aria-label="Destination">
          {worlds.map(w => (
            <Radio.Root key={w.id} value={w.id} className="world" nativeButton>
              <div className="world-art"><img src={w.art} alt="" width={1254} height={1254} /></div>
              <div className="world-label">
                <RadioDot checked={body === w.id} />
                <div className="copy"><span className="t-category">{w.name}</span><span className="muted t-small">{w.note}</span></div>
              </div>
            </Radio.Root>
          ))}
        </RadioGroup>
      </div>
      <Footer step={1} next={onNext} nextLabel="Continue →" note="Step 1 of 3" />
    </>
  );
}

export function CategoryStep({ data, body, categoryId, onCategory, onBack, onNext, reached, onStep }: Nav & {
  data: Dataset; body: Body; categoryId?: string; onCategory: (id: string) => void; onBack: () => void; onNext: () => void;
}) {
  const cats = data.runtime.categories as CategoryMeta[];
  const groups = [...new Set(cats.map(c => c.group ?? 'Other'))];
  return (
    <>
      <StepHeader title="What are you testing?" lede="Pick the kind of test. Each one needs certain traits of the place, like slope or night-time cold."
        step={2} reached={reached} onStep={onStep} />
      <div className="content">
        <div className="selection-context"><span className="fig">Destination</span><span className="t-category">{body === 'moon' ? 'Moon' : 'Mars'}</span></div>
        <RadioGroup value={categoryId ?? ''} onValueChange={v => onCategory(v as string)} aria-label="Mission category">
          <div className="categories">
            {groups.map(g => [
              <div key={`g-${g}`} className="group-label fig">{g}</div>,
              ...cats.filter(c => (c.group ?? 'Other') === g).map(c => {
                const { objectiveId, supported } = pickObjective(data, body, c);
                const checked = c.categoryId === categoryId;
                return (
                  <Radio.Root key={c.categoryId} value={c.categoryId} className="category" nativeButton
                    data-unsupported={supported.length ? undefined : ''}>
                    <RadioDot checked={checked} />
                    <span className="copy">
                      <span className="t-category">{c.name}</span>
                      {c.primaryInputsText && <span className="muted">Needs: {c.primaryInputsText}</span>}
                      <span className="support t-small">
                        {supported.length
                          ? <span>We can check {supported.map(d => DIMENSION_LABEL[d]).join(', ')} · {objectiveId}</span>
                          : <span>No trait we hold data for yet. Results will be all unknown.</span>}
                      </span>
                    </span>
                  </Radio.Root>
                );
              }),
            ])}
          </div>
        </RadioGroup>
      </div>
      <Footer step={2} onBack={onBack} next={onNext} nextLabel="Continue →" nextDisabled={!categoryId} note="Step 2 of 3" />
    </>
  );
}

const PRIORITY = [{ value: 'must', label: 'Required' }, { value: 'nice', label: 'Preferred' }] as const;
const MONTH_OPTIONS = MONTHS.map((m, i) => ({ value: String(i + 1), label: m }));
const TYPE_LABEL: Record<MissionType, string> = { robotic: 'Robotic', crewed: 'Crewed', instrument: 'Instrument test' };
const LIMIT_LABEL: Record<LimitKey, string> = { access: 'Max travel time from a city', protected: 'Max protected land', airport: 'Max distance to an airport', slope: 'Max mean slope' };

export function Metrics({ data, category, request, onRequest, onBack, onNext, reached, onStep }: Nav & {
  data: Dataset; category: Category; request: PlanRequest; onRequest: (r: PlanRequest) => void; onBack: () => void; onNext: () => void;
}) {
  const rules = requirements(data, request);
  const errors = validatePlan(request);
  const supported = supportedTraits(data, request.objectiveId, category);
  const objective = data.objectives.find(o => o.objectiveId === request.objectiveId)!;
  const [drafts, setDrafts] = useState<Record<string, { lo: string; hi: string }>>({});

  const setPriority = (d: Dimension, p: 'must' | 'nice') => {
    const must = (request.must ?? []).filter(x => x !== d), nice = (request.nice ?? []).filter(x => x !== d);
    onRequest({ ...request, must: p === 'must' ? [...must, d] : must, nice: p === 'nice' ? [...nice, d] : nice });
  };
  const setBand = (d: Dimension, lo: string, hi: string) => {
    setDrafts(x => ({ ...x, [d]: { lo, hi } }));
    const l = Number(lo), h = Number(hi);
    if (lo.trim() === '' || hi.trim() === '' || !Number.isFinite(l) || !Number.isFinite(h) || l > h) return;
    const edits = (request.bandEdits ?? []).filter(e => e.dimension !== d);
    onRequest({ ...request, bandEdits: [...edits, { dimension: d, lo: l, hi: h }] });
  };
  const resetBand = (d: Dimension) => {
    setDrafts(x => { const y = { ...x }; delete y[d]; return y; });
    onRequest({ ...request, bandEdits: (request.bandEdits ?? []).filter(e => e.dimension !== d) });
  };
  const setLimit = (k: LimitKey, v: string) => {
    const limits = { ...(request.limits ?? {}) };
    if (v.trim() === '') delete limits[k]; else limits[k] = Number(v);
    onRequest({ ...request, limits: Object.keys(limits).length ? limits : undefined });
  };
  const int = (v: string) => (v.trim() === '' ? undefined : Number(v));

  return (
    <>
      <StepHeader title="Define your metrics." lede="These are the conditions a site must meet. We start from the frozen test bands; you can change them."
        step={3} reached={reached} onStep={onStep} />
      <div className="content">
        <div className="plate-head" style={{ marginBottom: 0 }}>
          <div>
            <div className="fig">{request.body === 'moon' ? 'Moon' : 'Mars'} / {category.name}</div>
            <h2 className="t-section" style={{ marginTop: 4 }}>{objective.title}</h2>
            <p className="muted" style={{ marginTop: 6, maxWidth: 760 }}>{objective.earthTestableComponent}</p>
          </div>
          <Select label="Objective" width={220} value={request.objectiveId}
            options={objectivesFor(data, request.body).map(o => ({ value: o.objectiveId, label: o.objectiveId }))}
            onChange={id => onRequest(withDefaultPriorities(data, { ...request, objectiveId: id }))} />
        </div>
        {supported.length === 0 && (
          <p className="notice">This objective can't test any trait this category needs with our data. Every site will come back unknown for those traits.</p>
        )}

        <section>
          <div className="plate-head"><h2 className="t-section">Mission requirements</h2><span className="muted">{rules.length} traits · bold = required</span></div>
          <div className="sheet-wrap">
            <table className="sheet">
              <thead><tr><th>Trait</th><th>Earth measure</th><th>Condition</th><th>Accepted band</th><th>Priority</th><th /></tr></thead>
              <tbody>
                {rules.map(r => {
                  const draft = drafts[r.dimension];
                  const lo = draft?.lo ?? (r.band ? String(r.band.lo) : ''), hi = draft?.hi ?? (r.band ? String(r.band.hi) : '');
                  const bad = !!draft && (draft.lo === '' || draft.hi === '' || !Number.isFinite(Number(draft.lo)) || !Number.isFinite(Number(draft.hi)) || Number(draft.lo) > Number(draft.hi));
                  const edited = request.bandEdits?.some(e => e.dimension === r.dimension);
                  return (
                    <tr key={r.dimension} className={r.priority === 'must' ? 'must' : undefined}>
                      <td>{DIMENSION_LABEL[r.dimension] ?? r.dimension}</td>
                      <td className={r.earthColumn ? undefined : 'muted'}>
                        {r.earthColumn ? <>{COLUMN_LABEL[r.earthColumn] ?? r.earthColumn}{r.table === 'L1m' ? ', monthly' : ''}</> : 'No Earth data yet'}
                      </td>
                      <td className="muted">{r.earthColumn ? 'Between' : '—'}</td>
                      <td>
                        {r.earthColumn ? (
                          <div className="pair">
                            <input className="field num" inputMode="decimal" aria-label={`${r.dimension} lower bound`} value={lo} placeholder="min" aria-invalid={bad || undefined}
                              onChange={e => setBand(r.dimension, e.target.value, hi)} />
                            <span className="muted">–</span>
                            <input className="field num" inputMode="decimal" aria-label={`${r.dimension} upper bound`} value={hi} placeholder="max" aria-invalid={bad || undefined}
                              onChange={e => setBand(r.dimension, lo, e.target.value)} />
                            <span className="muted">{r.unit ?? ''}</span>
                          </div>
                        ) : <span className="muted">{bandLabel(r)}</span>}
                        {!r.band && r.earthColumn && !draft && <div className="t-small v-unknown" style={{ marginTop: 4 }}>No frozen band. Sites stay unknown until you set one.</div>}
                        {bad && <div className="t-small v-miss" style={{ marginTop: 4 }}>Enter two numbers, low then high.</div>}
                      </td>
                      <td>
                        <Select label={`${r.dimension} priority`} width={130} value={r.priority ?? 'must'} options={[...PRIORITY]}
                          onChange={p => setPriority(r.dimension, p)} />
                      </td>
                      <td>{edited && <button className="link t-small" onClick={() => resetBand(r.dimension)}>Reset band</button>}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </section>

        <section>
          <div className="plate-head"><h2 className="t-section">Field window and team</h2></div>
          <div className="controls">
            <label className="control"><span className="fig">From</span>
              <Select label="First month" value={String(request.months.start)} options={MONTH_OPTIONS} width={110}
                onChange={m => onRequest({ ...request, months: { ...request.months, start: Number(m) } })} /></label>
            <label className="control"><span className="fig">To</span>
              <Select label="Last month" value={String(request.months.end)} options={MONTH_OPTIONS} width={110}
                onChange={m => onRequest({ ...request, months: { ...request.months, end: Number(m) } })} /></label>
            <label className="control"><span className="fig">Mission type</span>
              <Select label="Mission type" value={request.missionType} width={170}
                options={MISSION_TYPES.map(t => ({ value: t, label: TYPE_LABEL[t] }))} onChange={t => onRequest({ ...request, missionType: t })} /></label>
            <label className="control"><span className="fig">Days</span>
              <input className="field" type="number" min={1} value={request.durationDays ?? ''} onChange={e => onRequest({ ...request, durationDays: int(e.target.value) })} /></label>
            <label className="control"><span className="fig">Team</span>
              <input className="field" type="number" min={1} value={request.teamSize ?? ''} onChange={e => onRequest({ ...request, teamSize: int(e.target.value) })} /></label>
            <label className="control"><span className="fig">Sites listed</span>
              <Select label="Sites listed" value={String(request.top ?? 50)} width={100}
                options={['25', '50', '100'].map(v => ({ value: v, label: v }))} onChange={v => onRequest({ ...request, top: Number(v) })} /></label>
          </div>
        </section>

        <section>
          <div className="plate-head"><h2 className="t-section">Hard limits <span className="muted t-small">optional</span></h2>
            <span className="muted">Sites past a limit are left out. A site with no data for a limit stays in.</span></div>
          <div className="controls">
            {(Object.keys(LIMITS) as LimitKey[]).map(k => (
              <label key={k} className="control"><span className="fig">{LIMIT_LABEL[k]} ({LIMITS[k].unit})</span>
                <input className="field" type="number" min={0} max={Number.isFinite(LIMITS[k].max) ? LIMITS[k].max : undefined} placeholder="none"
                  value={request.limits?.[k] ?? ''} onChange={e => setLimit(k, e.target.value)} /></label>
            ))}
          </div>
        </section>
        {errors.length > 0 && <p className="notice error">{errors.join('. ')}.</p>}
      </div>
      <Footer step={3} onBack={onBack} next={onNext} nextLabel="Find sites →" nextDisabled={errors.length > 0} note="Step 3 of 3" />
    </>
  );
}
