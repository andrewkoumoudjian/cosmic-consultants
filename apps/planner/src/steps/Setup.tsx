/** Steps 1 Destination, 2 Category, 3 Requirements. */
import { useState } from 'react';
import { RadioGroup } from '@base-ui/react/radio-group';
import { Radio } from '@base-ui/react/radio';
import { requirements, type Dataset } from '../../../atlas/src/planner/engine.ts';
import { LIMITS, MISSION_TYPES, validatePlan, type Dimension, type LimitKey, type MissionType, type PlanRequest } from '../../../atlas/src/plan-url.ts';
import { COLUMN_LABEL, DIMENSION_LABEL, MONTHS, objectivesFor, pickObjective, withDefaultPriorities, type Body, type Category } from '../model.ts';
import { Page, RadioDot, Select } from '../ui.tsx';
import moonArt from '../assets/moon-illustration.png';
import marsArt from '../assets/mars-illustration.png';

type CategoryMeta = Category & { group?: string };

export function Location({ body, onBody, onNext }: { body: Body; onBody: (b: Body) => void; onNext: () => void }) {
  return (
    <Page title="Moon or Mars?" next={onNext}>
      <RadioGroup value={body} onValueChange={v => onBody(v as Body)} className="worlds" aria-label="Destination">
        {([['moon', 'Moon', moonArt], ['mars', 'Mars', marsArt]] as const).map(([id, name, art]) => (
          <Radio.Root key={id} value={id} className="world" nativeButton>
            <div className="world-art"><img src={art} alt="" width={1254} height={1254} /></div>
            <div className="world-name">{name}<RadioDot checked={body === id} /></div>
          </Radio.Root>
        ))}
      </RadioGroup>
    </Page>
  );
}

export function CategoryStep({ data, body, categoryId, onCategory, onBack, onNext }: {
  data: Dataset; body: Body; categoryId?: string; onCategory: (id: string) => void; onBack: () => void; onNext: () => void;
}) {
  const cats = data.runtime.categories as CategoryMeta[];
  const groups = [...new Set(cats.map(c => c.group ?? 'Other'))];
  return (
    <Page title="What are you testing?" back={onBack} next={onNext} nextDisabled={!categoryId}>
      <RadioGroup value={categoryId ?? ''} onValueChange={v => onCategory(v as string)} aria-label="Category">
        {groups.map(g => (
          <section key={g}>
            <div className="group-name">{g}</div>
            <div className="cats">
              {cats.filter(c => (c.group ?? 'Other') === g).map(c => {
                const { supported } = pickObjective(data, body, c);
                return (
                  <Radio.Root key={c.categoryId} value={c.categoryId} className="cat" nativeButton data-unsupported={supported.length ? undefined : ''}>
                    <RadioDot checked={c.categoryId === categoryId} />
                    <span className="cat-name">{c.name}</span>
                    <span className="traits">{supported.map(d => <span key={d} className="tag">{DIMENSION_LABEL[d]}</span>)}</span>
                  </Radio.Root>
                );
              })}
            </div>
          </section>
        ))}
      </RadioGroup>
    </Page>
  );
}

const PRIORITY = [{ value: 'must', label: 'Required' }, { value: 'nice', label: 'Preferred' }] as const;
const MONTH_OPTIONS = MONTHS.map((m, i) => ({ value: String(i + 1), label: m }));
const TYPE_LABEL: Record<MissionType, string> = { robotic: 'Robotic', crewed: 'Crewed', instrument: 'Instrument' };
const LIMIT_LABEL: Record<LimitKey, string> = { access: 'Travel time, min', protected: 'Protected land, %', airport: 'Airport, km', slope: 'Mean slope, °' };

export function Metrics({ data, request, onRequest, onBack, onNext }: {
  data: Dataset; category: Category; request: PlanRequest; onRequest: (r: PlanRequest) => void; onBack: () => void; onNext: () => void;
}) {
  const rules = requirements(data, request);
  const errors = validatePlan(request);
  const [drafts, setDrafts] = useState<Record<string, { lo: string; hi: string }>>({});

  const setPriority = (d: Dimension, p: 'must' | 'nice') => {
    const must = (request.must ?? []).filter(x => x !== d), nice = (request.nice ?? []).filter(x => x !== d);
    onRequest({ ...request, must: p === 'must' ? [...must, d] : must, nice: p === 'nice' ? [...nice, d] : nice });
  };
  const setBand = (d: Dimension, lo: string, hi: string) => {
    setDrafts(x => ({ ...x, [d]: { lo, hi } }));
    const l = Number(lo), h = Number(hi);
    if (lo.trim() === '' || hi.trim() === '' || !Number.isFinite(l) || !Number.isFinite(h) || l > h) return;
    onRequest({ ...request, bandEdits: [...(request.bandEdits ?? []).filter(e => e.dimension !== d), { dimension: d, lo: l, hi: h }] });
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
    <Page title="Requirements" back={onBack} next={onNext} nextLabel="Find sites" nextDisabled={errors.length > 0}
      aside={<Select label="Objective" width={300} value={request.objectiveId}
        options={objectivesFor(data, request.body).map(o => ({ value: o.objectiveId, label: `${o.objectiveId} · ${o.title}` }))}
        onChange={id => onRequest(withDefaultPriorities(data, { ...request, objectiveId: id }))} />}>
      <div className="sheet">
        <table>
          <thead><tr><th>Trait</th><th>Measured on Earth as</th><th className="num">Band</th><th>Priority</th></tr></thead>
          <tbody>
            {rules.map(r => {
              const draft = drafts[r.dimension];
              const lo = draft?.lo ?? (r.band ? String(r.band.lo) : ''), hi = draft?.hi ?? (r.band ? String(r.band.hi) : '');
              const bad = !!draft && (draft.lo === '' || draft.hi === '' || !Number.isFinite(Number(draft.lo)) || !Number.isFinite(Number(draft.hi)) || Number(draft.lo) > Number(draft.hi));
              const edited = request.bandEdits?.some(e => e.dimension === r.dimension);
              return (
                <tr key={r.dimension} className={r.priority === 'must' ? 'must' : undefined}>
                  <td>{DIMENSION_LABEL[r.dimension] ?? r.dimension}</td>
                  <td className={r.earthColumn ? undefined : 'muted'}>{r.earthColumn ? `${COLUMN_LABEL[r.earthColumn] ?? r.earthColumn}${r.table === 'L1m' ? ', monthly' : ''}` : 'No Earth data'}</td>
                  <td className="num">
                    {r.earthColumn ? (
                      <div className="band" style={{ justifyContent: 'flex-end' }}>
                        {edited && <button className="icon-btn small" onClick={() => resetBand(r.dimension)} title="Back to the frozen band">reset</button>}
                        <input className="field" inputMode="decimal" aria-label={`${r.dimension} low`} value={lo} placeholder="low" aria-invalid={bad || undefined} onChange={e => setBand(r.dimension, e.target.value, hi)} />
                        <span className="muted">–</span>
                        <input className="field" inputMode="decimal" aria-label={`${r.dimension} high`} value={hi} placeholder="high" aria-invalid={bad || undefined} onChange={e => setBand(r.dimension, lo, e.target.value)} />
                        <span className="muted" style={{ width: 40, textAlign: 'left' }}>{r.unit ?? ''}</span>
                      </div>
                    ) : <span className="muted">—</span>}
                  </td>
                  <td><Select label={`${r.dimension} priority`} width={130} value={r.priority ?? 'must'} options={[...PRIORITY]} onChange={p => setPriority(r.dimension, p)} /></td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      <section>
        <h2 className="h2">Field window</h2>
        <div className="row">
          <label className="control">From<Select label="First month" value={String(request.months.start)} options={MONTH_OPTIONS} width={104}
            onChange={m => onRequest({ ...request, months: { ...request.months, start: Number(m) } })} /></label>
          <label className="control">To<Select label="Last month" value={String(request.months.end)} options={MONTH_OPTIONS} width={104}
            onChange={m => onRequest({ ...request, months: { ...request.months, end: Number(m) } })} /></label>
          <label className="control">Mission<Select label="Mission type" value={request.missionType} width={140}
            options={MISSION_TYPES.map(t => ({ value: t, label: TYPE_LABEL[t] }))} onChange={t => onRequest({ ...request, missionType: t })} /></label>
          <label className="control">Days<input className="field" type="number" min={1} value={request.durationDays ?? ''} onChange={e => onRequest({ ...request, durationDays: int(e.target.value) })} /></label>
          <label className="control">Team<input className="field" type="number" min={1} value={request.teamSize ?? ''} onChange={e => onRequest({ ...request, teamSize: int(e.target.value) })} /></label>
          <label className="control">Show<Select label="Sites shown" value={String(request.top ?? 50)} width={90}
            options={['25', '50', '100'].map(v => ({ value: v, label: v }))} onChange={v => onRequest({ ...request, top: Number(v) })} /></label>
        </div>
      </section>

      <section>
        <h2 className="h2">Limits</h2>
        <div className="row">
          {(Object.keys(LIMITS) as LimitKey[]).map(k => (
            <label key={k} className="control">{LIMIT_LABEL[k]}
              <input className="field" type="number" min={0} max={Number.isFinite(LIMITS[k].max) ? LIMITS[k].max : undefined} placeholder="none"
                value={request.limits?.[k] ?? ''} onChange={e => setLimit(k, e.target.value)} /></label>
          ))}
        </div>
      </section>
      {errors.length > 0 && <p className="warn">{errors.join('. ')}.</p>}
    </Page>
  );
}
