/**
 * Step 4 Sites. Ranking follows the submitted planner (apps/planner/src/steps/Finder.tsx): Pareto layers, kept
 * deliberately plain (rank, coordinates, Compare). Per-trait detail lives in the globe's site card and, bottom right,
 * the top three ranked sites on a per-trait similarity radar (TopThree.tsx). No single site score (AGENTS.md rule 4).
 *
 * Two display rules on top of the engine, both on by default, both shown and switchable:
 * mostly-water cells are hidden, and cells within 300 km of one listed above fold into it.
 */
import { Fragment, lazy, Suspense, useEffect, useMemo, useRef, useState } from 'react';
import { months, type Dataset, type SearchResult } from '../../../atlas/src/planner/engine.ts';
import type { PlanRequest } from '../../../atlas/src/plan-url.ts';
import { CELL_AREA, CLASS_TEXT, DIMENSION_LABEL, FINDER_ORDERS, MAX_COMPARE, MONTHS, SERIES, SITE_LETTER, coordLabel, fmt, objectiveTitle, seasonStrip, siteFacts, sortByColumn, traitCells, type FinderOrder } from '../model.ts';
import { isWet, spread } from '../place.ts';
import { Button, NavFoot, Select, SiteBadge, StepHead, Switch, Verdict } from '../ui.tsx';
import { TopThree } from './TopThree.tsx';
import type { Anchor } from '../Globe.tsx';
import { EngineCandidates, SiteMeasurements, type EngineProps } from '../engine-results-ui.tsx';

const Globe = lazy(() => import('../Globe.tsx'));
type ListFilter = 'matches' | 'unknown' | 'misses';
const CLASS_WHY: (string | undefined)[] = [undefined, 'misses a required trait', 'a required trait is unknown', 'past one of your hard limits'];
const SPREAD_KM = 300;

export function Sites({ data, request, result, removed, onRemoved, onPins, order, onOrder, eligible, dropped, onBack, onNext, engine, targetId, onTarget }: EngineProps & {
  data: Dataset; request: PlanRequest; result: SearchResult; removed: string[];
  onRemoved: (r: string[]) => void; onPins: (p: string[]) => void;
  order: FinderOrder; onOrder: (o: FinderOrder) => void; eligible: (h3: string) => boolean; dropped: string[];
  onBack: () => void; onNext: () => void;
}) {
  const pins = request.pins ?? [];
  const [filter, setFilter] = useState<ListFilter>('matches');
  const [hideWet, setHideWet] = useState(true);
  const [spreadOn, setSpreadOn] = useState(true);
  const pageSize = request.top ?? 50;
  const [extra, setExtra] = useState(0);
  useEffect(() => { setExtra(0); }, [filter, order, pageSize, result, hideWet, spreadOn]);

  const removedSet = useMemo(() => new Set(removed), [removed]);
  const byClass = (cls: number) => {
    const out: number[] = [];
    for (let i = 0; i < result.classes.length; i++) if (result.classes[i] === cls && !removedSet.has(data.h3[i]!)) out.push(i);
    return out;
  };
  const matched = useMemo(() => result.indices.filter(i => !removedSet.has(data.h3[i]!)), [result, removedSet, data]);
  const unknownIdx = useMemo(() => byClass(2), [result, removedSet, data]);
  const missIdx = useMemo(() => byClass(1), [result, removedSet, data]);
  const group = filter === 'matches' ? matched : filter === 'unknown' ? unknownIdx : missIdx;
  const dry = useMemo(() => (hideWet ? group.filter(i => !isWet(data, i)) : group), [group, hideWet, data]);
  const ordered = useMemo(() => (order === 'engine' ? dry : sortByColumn(data, dry, order, 1)), [dry, order, data]);
  const kept = useMemo(() => (spreadOn ? spread(data, ordered, SPREAD_KM).kept : ordered), [ordered, spreadOn, data]);
  const shown = useMemo(() => kept.slice(0, pageSize + extra), [kept, pageSize, extra]);
  // Top 3 for the similarity chart: always the in-play ranking with the same switches, whichever group the list shows.
  const top3 = useMemo(() => {
    if (filter === 'matches') return kept.slice(0, 3);
    const d = hideWet ? matched.filter(i => !isWet(data, i)) : matched;
    const o = order === 'engine' ? d : sortByColumn(data, d, order, 1);
    return (spreadOn ? spread(data, o, SPREAD_KM).kept : o).slice(0, 3);
  }, [filter, kept, matched, hideWet, order, spreadOn, data]);
  const pinIdx = pins.map(h => data.h3.indexOf(h)).filter(i => i >= 0);
  const [active, setActive] = useState<number | null>(() => pinIdx[0] ?? null);
  const c = result.counts;
  const hasLayers = useMemo(() => matched.some(i => result.layers.has(i)), [matched, result]);
  const allTie = useMemo(() => hasLayers && new Set(matched.map(i => result.layers.get(i))).size <= 1, [hasLayers, matched, result]);
  const sortedBy = FINDER_ORDERS.find(o => o.value === order)!;
  const objective = data.objectives.find(o => o.objectiveId === request.objectiveId);

  const togglePin = (i: number) => {
    const h = data.h3[i]!;
    if (pins.includes(h)) onPins(pins.filter(p => p !== h));
    else if (pins.length < MAX_COMPARE && eligible(h)) onPins([...pins, h]);
  };
  const remove = (i: number) => {
    const h = data.h3[i]!;
    onRemoved([...removed, h]);
    if (pins.includes(h)) onPins(pins.filter(p => p !== h));
    if (active === i) setActive(null);
  };
  const orderNote = order !== 'engine' ? `Sorted by ${sortedBy.note}, lowest first.`
    : allTie ? 'Every site here ties on the required traits, so Pareto can’t separate them. Sort by a measure to rank.'
    : hasLayers ? null
    : 'No Pareto layers (a trait has no accepted band). Sort by a measure to rank.';

  return (
    <div className="page">
      <StepHead step={4} context={<>
        <span className={`bubble ${request.body}`}>{request.body === 'moon' ? 'Moon' : 'Mars'}</span>
        <span className="bubble">{objective ? objectiveTitle(objective) : request.objectiveId}</span>
        <span className="bubble accent"><span className="mono">{c.matches.toLocaleString('en-US')}</span> of <span className="mono">{c.land.toLocaleString('en-US')}</span> places fit</span>
      </>} />

      {c.matches === 0 && <p className="note warn">No site meets every required trait. Make one Preferred, widen a band, or change the months.</p>}
      {dropped.length > 0 && <p className="note">Left the comparison because they no longer match: <span className="mono">{dropped.join(', ')}</span></p>}

      <EngineCandidates data={data} request={request} engine={engine} targetId={targetId} onTarget={onTarget}
        eligible={eligible} onCompare={togglePin} onInspect={i => { setActive(i); document.querySelector('.globe-card')?.scrollIntoView({ behavior: 'smooth', block: 'center' }); }} />

      <div className="sf-main">
        <section className="card sf-list-card" aria-label="Ranked candidates">
          <div className="sf-controls">
            <Select label="Group" value={filter} onChange={setFilter} options={[
              { value: 'matches', label: `In play · ${matched.length.toLocaleString('en-US')}` },
              { value: 'unknown', label: `Unknown · ${unknownIdx.length.toLocaleString('en-US')}` },
              { value: 'misses', label: `Miss · ${missIdx.length.toLocaleString('en-US')}` },
            ]} />
            <Select label="Order" value={order} onChange={onOrder} options={FINDER_ORDERS.map(o => ({ value: o.value, label: o.label }))} />
            <span className="flex1" />
            <span className="bubble accent">{pins.length}/{MAX_COMPARE} picked</span>
          </div>
          <div className="sf-toggles">
            <Switch on={hideWet} onChange={setHideWet}>Dry land only</Switch>
            <Switch on={spreadOn} onChange={setSpreadOn}>One per {SPREAD_KM} km</Switch>
            <span className="t-label muted">{kept.length.toLocaleString('en-US')} listed of {group.length.toLocaleString('en-US')}</span>
          </div>
          {orderNote && <p className="t-small muted sf-note">{orderNote}</p>}
          <ol className="sf-list">
            {shown.length === 0 && <li className="t-small muted" style={{ padding: 16 }}>Nothing in this group with these switches.</li>}
            {shown.map((i, rank) => {
              const h = data.h3[i]!, at = pins.indexOf(h);
              const canPin = eligible(h) && (at >= 0 || pins.length < MAX_COMPARE);
              const layer = filter === 'matches' && !allTie && hasLayers ? result.layers.get(i) : undefined;
              const sortVal = order === 'engine' ? null : fmt(data.yearly[order]?.[i], sortedBy.unit);
              return (
                <li key={h} className="sf-row" data-active={active === i ? '' : undefined} onClick={() => setActive(i)}>
                  <span className="sf-rank mono">{rank + 1}</span>
                  <span className="sf-coord mono">{coordLabel(data, i)}</span>
                  <span className="sf-side">
                    <span className="t-label muted">{sortVal ? `${sortVal}` : layer !== undefined ? `Layer ${layer}` : ''}</span>
                    {at >= 0
                      ? <Button className="sf-pick on" aria-label={`Stop comparing site ${SITE_LETTER[at]}`} onClick={e => { e.stopPropagation(); togglePin(i); }}><SiteBadge k={at} /></Button>
                      : <Button className="sf-pick" aria-label="Compare this site" disabled={!canPin} title={eligible(h) ? 'Compare' : `Can't compare: ${CLASS_WHY[result.classes[i]!]}`}
                          onClick={e => { e.stopPropagation(); togglePin(i); }}>Compare</Button>}
                    <Button className="sf-x" aria-label={`Remove ${coordLabel(data, i)} from the list`} title="Remove from the list" onClick={e => { e.stopPropagation(); remove(i); }}>×</Button>
                  </span>
                </li>
              );
            })}
          </ol>
          {kept.length > shown.length && (
            <Button className="btn sm" style={{ alignSelf: 'center' }} onClick={() => setExtra(e => e + pageSize)}>
              Show {Math.min(pageSize, kept.length - shown.length)} more
            </Button>
          )}
          {removed.length > 0 && (
            <p className="t-label muted">Removed by you: {removed.map(h => data.h3.indexOf(h)).filter(i => i >= 0).map((i, n) => (
              <Fragment key={data.h3[i]}>{n > 0 && ', '}<Button className="link" onClick={() => onRemoved(removed.filter(h => h !== data.h3[i]))}>{coordLabel(data, i)} ↺</Button></Fragment>
            ))}</p>
          )}
        </section>

        <div className="sf-right">
          <GlobeCard data={data} request={request} result={result} inPlay={shown} pinIdx={pinIdx} pins={pins} active={active}
            onActive={setActive} onPin={togglePin} eligible={eligible} removed={removed} />
          <TopThree data={data} request={request} ranked={top3} />
        </div>
      </div>

      {active !== null && <SiteMeasurements data={data} i={active} engine={engine} />}

      <NavFoot onBack={onBack} onNext={onNext} nextLabel="Limitations" nextDisabled={pinIdx.length === 0}
        hint={pinIdx.length === 0 ? 'Press Compare on up to three sites' : undefined} />
    </div>
  );
}

function GlobeCard({ data, request, result, inPlay, pinIdx, pins, active, onActive, onPin, eligible, removed }: {
  data: Dataset; request: PlanRequest; result: SearchResult; inPlay: number[]; pinIdx: number[]; pins: string[];
  active: number | null; onActive: (i: number | null) => void; onPin: (i: number) => void; eligible: (h: string) => boolean; removed: string[];
}) {
  const [anchor, setAnchor] = useState<Anchor>(null);
  const box = useRef<HTMLDivElement>(null);
  const card = useRef<HTMLDivElement>(null);
  const [target, setTarget] = useState<{ x: number; y: number } | null>(null);
  useEffect(() => {
    const b = box.current?.getBoundingClientRect(), r = card.current?.getBoundingClientRect();
    if (!b || !r || !anchor) { setTarget(null); return; }
    // Attach to the card edge nearest the cell.
    const x = anchor.x < r.left - b.left ? r.left - b.left : anchor.x > r.right - b.left ? r.right - b.left : anchor.x;
    const y = anchor.y < r.top - b.top ? r.top - b.top : r.bottom - b.top;
    setTarget(x === anchor.x ? { x, y } : { x, y: Math.min(Math.max(anchor.y, r.top - b.top + 24), r.bottom - b.top - 24) });
  }, [anchor, active]);
  const k = active === null ? -1 : pinIdx.indexOf(active);
  const color = k >= 0 ? SERIES[k]! : '#eceef2';
  return (
    <section className="card globe-card" ref={box} aria-label="Globe of candidate sites">
      <div className="globe-host">
        <Suspense fallback={<div className="loading" style={{ minHeight: 400 }}><span className="t-small muted">Loading the globe…</span></div>}>
          <Globe data={data} classes={result.classes} inPlay={inPlay} pins={pinIdx} active={active} onPick={onActive} onAnchor={setAnchor} />
        </Suspense>
      </div>
      <div className="globe-legend">
        <span><i style={{ background: '#b4b9ff' }} />Fits</span>
        <span><i style={{ background: '#7d8aa3' }} />Unknown</span>
        <span><i style={{ background: '#2a3170' }} />Miss</span>
        <span><i style={{ background: '#fff' }} />Listed</span>
      </div>
      {active !== null && anchor && target && (
        <svg className="leader" aria-hidden>
          <circle cx={anchor.x} cy={anchor.y} r={7} fill="none" stroke={color} strokeWidth={2} />
          <line x1={anchor.x} y1={anchor.y} x2={target.x} y2={target.y} stroke={color} strokeWidth={1.5} />
          <circle cx={target.x} cy={target.y} r={3} fill={color} />
        </svg>
      )}
      {active === null && <p className="globe-hint t-label">Click a cell or a row to open its card.</p>}
      {active !== null && (
        <div className="pinned" ref={card} role="dialog" aria-label={`Site card ${coordLabel(data, active)}`}>
          <PinnedCard data={data} request={request} i={active} k={k} canPin={pins.length < MAX_COMPARE && eligible(data.h3[active]!)}
            why={removed.includes(data.h3[active]!) ? 'removed by you' : CLASS_WHY[result.classes[active]!]}
            onPin={() => onPin(active)} onClose={() => onActive(null)} />
        </div>
      )}
    </section>
  );
}

function PinnedCard({ data, request, i, k, canPin, why, onPin, onClose }: {
  data: Dataset; request: PlanRequest; i: number; k: number; canPin: boolean; why?: string; onPin: () => void; onClose: () => void;
}) {
  const strip = useMemo(() => seasonStrip(data, request, i), [data, request, i]);
  const inWin = new Set(months(request));
  return (
    <>
      <div className="spread" style={{ flexWrap: 'nowrap', alignItems: 'flex-start' }}>
        <span className="row" style={{ flexWrap: 'nowrap', alignItems: 'flex-start' }}>
          {k >= 0 && <SiteBadge k={k} />}
          <span className="stack" style={{ gap: 2 }}>
            <span className="strong mono">{coordLabel(data, i)}</span>
            <span className="t-label muted">{CELL_AREA}</span>
          </span>
        </span>
        <Button className="sf-x" aria-label="Close site card" onClick={onClose}>×</Button>
      </div>
      <div className="stack" style={{ gap: 6 }}>
        {traitCells(data, request, i).map(t => (
          <span key={t.dimension} className="verdict-line">
            <Verdict v={t.verdict}>{t.priority === 'must' ? <b>{DIMENSION_LABEL[t.dimension]}</b> : DIMENSION_LABEL[t.dimension]}</Verdict>
            <span className="why">{t.detail}</span>
          </span>
        ))}
      </div>
      <dl className="kv">
        {siteFacts(data, i).map(f => <Fragment key={f.label}><dt>{f.label}</dt><dd className={f.value ? undefined : 'none'}>{f.value ?? 'no data'}</dd></Fragment>)}
      </dl>
      <div className="stack" style={{ gap: 5 }}>
        <span className="t-label text-2">Required traits by month</span>
        <div className="season-labels">{MONTHS.map((m, j) => <span key={m} data-in={inWin.has(j + 1) ? '' : undefined}>{m[0]}</span>)}</div>
        <div className="season" role="img" aria-label={`By month: ${strip.map((s, j) => `${MONTHS[j]} ${CLASS_TEXT[s]}`).join('; ')}`}>
          {strip.map((s, j) => <span key={j} className={s} data-in={inWin.has(j + 1) ? '' : undefined} title={`${MONTHS[j]}: ${CLASS_TEXT[s]}`}>{s === 'allMatch' ? '●' : s === 'someMiss' ? '◆' : '○'}</span>)}
        </div>
      </div>
      {(k >= 0 || canPin) ? <Button className={`btn sm${k >= 0 ? '' : ' primary'}`} onClick={onPin}>{k >= 0 ? 'Stop comparing' : 'Compare this site'}</Button>
        : why && <span className="t-small muted">Can't compare: {why}.</span>}
    </>
  );
}
