/** Step 4 Sites. Per-trait results only: no percentage, no average (AGENTS.md rule 4). */
import { lazy, Suspense, useEffect, useMemo, useState } from 'react';
import { requirements, type Dataset, type SearchResult } from '../../../atlas/src/planner/engine.ts';
import type { PlanRequest } from '../../../atlas/src/plan-url.ts';
import { CELL_AREA, DIMENSION_LABEL, MAX_COMPARE, SERIES, coordLabel, fmt, siteFacts, sortByColumn, traitCells } from '../model.ts';
import { Mark, Page, Select, Verdict } from '../ui.tsx';

const Globe = lazy(() => import('../Globe.tsx'));

type ListFilter = 'matches' | 'unknown' | 'misses';

/** List orders. "engine" is the engine's own order; the rest sort by one measured column. */
const ORDERS = [
  { value: 'engine', label: 'Pareto order', unit: '', note: '' },
  { value: 'slope_mean_deg', label: 'Flattest first', unit: 'deg', note: 'mean slope' },
  { value: 'access_min_median', label: 'Closest to a city', unit: 'min', note: 'to a city' },
  { value: 'airport_km', label: 'Closest airport', unit: 'km', note: 'to an airport' },
  { value: 'elev_mean_m', label: 'Lowest first', unit: 'm', note: 'mean elevation' },
] as const;
type Order = (typeof ORDERS)[number]['value'];

export function Finder({ data, request, result, removed, onRemoved, onPins, eligible, dropped, onBack, onNext }: {
  data: Dataset; request: PlanRequest; result: SearchResult; removed: string[];
  onRemoved: (r: string[]) => void; onPins: (p: string[]) => void;
  /** Still in play: the engine's class 0 and not removed. Only these can be compared. */
  eligible: (h3: string) => boolean;
  /** Compared sites that left the comparison after an edit, as coordinates. */
  dropped: string[];
  onBack: () => void; onNext: () => void;
}) {
  const pins = request.pins ?? [];
  const [filter, setFilter] = useState<ListFilter>('matches');
  const [order, setOrder] = useState<Order>('engine');
  const pageSize = request.top ?? 50;
  const [extra, setExtra] = useState(0);
  useEffect(() => { setExtra(0); }, [filter, order, pageSize, result]);

  const removedSet = useMemo(() => new Set(removed), [removed]);
  const matched = useMemo(() => result.indices.filter(i => !removedSet.has(data.h3[i]!)), [result, removedSet, data]);
  const unknownIdx = useMemo(() => {
    const out: number[] = [];
    for (let i = 0; i < result.classes.length; i++) if (result.classes[i] === 2 && !removedSet.has(data.h3[i]!)) out.push(i);
    return out;
  }, [result, removedSet, data]);
  const missIdx = useMemo(() => {
    const out: number[] = [];
    for (let i = 0; i < result.classes.length; i++) if (result.classes[i] === 1 && !removedSet.has(data.h3[i]!)) out.push(i);
    return out;
  }, [result, removedSet, data]);

  const baseList = filter === 'matches' ? matched : filter === 'unknown' ? unknownIdx : missIdx;
  const sorted = useMemo(() => (order === 'engine' ? baseList : sortByColumn(data, baseList, order, 1)), [baseList, order, data]);
  const inPlay = useMemo(() => sorted.slice(0, pageSize + extra), [sorted, pageSize, extra]);
  const globeInPlay = useMemo(() => inPlay.slice(0, 200), [inPlay]);
  const pinIdx = pins.map(h => data.h3.indexOf(h)).filter(i => i >= 0);
  const [active, setActive] = useState<number | null>(() => pinIdx[0] ?? null);
  const c = result.counts;
  // When every match sits on the same Pareto layer with the same gap, the engine order is just release order.
  const allTie = useMemo(() => new Set(matched.map(i => result.layers.get(i))).size <= 1, [matched, result]);

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

  return (
    <Page title={<>{c.matches.toLocaleString('en-US')} sites <span className="of">of {c.land.toLocaleString('en-US')}</span></>}
      back={onBack} next={onNext} nextLabel="Compare" nextDisabled={pinIdx.length === 0}
      aside={<div className="legend">
        <span><Mark verdict="miss" />{c.misses.toLocaleString('en-US')} miss</span>
        <span><Mark verdict="unknown" />{c.unknown.toLocaleString('en-US')} unknown</span>
        {c.land > c.withinLimits && <span>{(c.land - c.withinLimits).toLocaleString('en-US')} past limits</span>}
        <span>one site = one {CELL_AREA}</span>
      </div>}>
      {c.matches === 0 && <p className="warn">No site meets every required trait. Make one Preferred, widen a band, or change months.</p>}
      {dropped.length > 0 && <p className="note small">Left the comparison because they no longer match: <span className="mono">{dropped.join(', ')}</span></p>}
      <div className="finder">
        <div>
          <div className="list-head">
            <Select label="Show group" value={filter} options={[
              { value: 'matches', label: `Matches (${matched.length.toLocaleString('en-US')})` },
              { value: 'unknown', label: `Unknown (${unknownIdx.length.toLocaleString('en-US')})` },
              { value: 'misses', label: `Misses (${missIdx.length.toLocaleString('en-US')})` },
            ]} onChange={setFilter} width={170} />
            <Select label="Order" value={order} options={ORDERS.map(o => ({ value: o.value, label: o.label }))} onChange={setOrder} width={165} />
          </div>
          <div className="list-meta small muted">
            <span>Showing {inPlay.length.toLocaleString('en-US')} of {sorted.length.toLocaleString('en-US')}</span>
            <span>{pins.length}/{MAX_COMPARE} picked</span>
          </div>
          {filter === 'matches' && order === 'engine' && allTie && matched.length > 1 &&
            <p className="muted small tie">All {matched.length.toLocaleString('en-US')} tie on the required traits, so this order is arbitrary. Sort by a measure, or pick on the globe.</p>}
          <div className="sites" role="list" aria-label="Sites">
            {sorted.length === 0 && filter !== 'matches' &&
              <p className="muted small" style={{ padding: '14px 6px' }}>{filter === 'unknown' ? 'No cells with unknown required traits.' : 'No cells missed a required trait.'}</p>}
            {inPlay.map(i => {
              const h = data.h3[i]!, at = pins.indexOf(h);
              const sortedBy = ORDERS.find(o => o.value === order)!;
              const sortVal = order === 'engine' ? null : fmt(data.yearly[order]?.[i], sortedBy.unit);
              const canPinRow = eligible(h) && (at >= 0 || pins.length < MAX_COMPARE);
              const layer = filter === 'matches' && !allTie ? result.layers.get(i) : undefined;
              return (
                <div key={h} role="listitem" className="site" data-active={active === i ? '' : undefined} onClick={() => setActive(i)}>
                  <button className="pin" aria-pressed={at >= 0} aria-label={at >= 0 ? 'Stop comparing' : 'Compare'}
                    disabled={!canPinRow} title={eligible(h) ? undefined : CLASS_WHY[result.classes[i]!]}
                    style={at >= 0 ? { background: SERIES[at] } : undefined}
                    onClick={e => { e.stopPropagation(); togglePin(i); }} />
                  <span className="site-body">
                    <span className="site-line">
                      <span className="mono">{coordLabel(data, i)}</span>
                      {order !== 'engine' ? <span className="sort-val">{sortVal ?? 'no data'} <span className="faint">{sortedBy.note}</span></span>
                        : layer !== undefined && <span className="faint small">Layer {layer}</span>}
                    </span>
                    <span className="site-traits small">
                      {traitCells(data, request, i).map(t => (
                        <Verdict key={t.dimension} verdict={t.verdict}>{DIMENSION_LABEL[t.dimension]}<span className="tv">{t.short}</span></Verdict>
                      ))}
                    </span>
                  </span>
                  <button className="icon-btn" aria-label={`Remove ${coordLabel(data, i)}`} onClick={e => { e.stopPropagation(); remove(i); }}>×</button>
                </div>
              );
            })}
            {removed.map(h => data.h3.indexOf(h)).filter(i => i >= 0).map(i => (
              <div key={data.h3[i]} className="removed small">
                <s className="mono">{coordLabel(data, i)}</s>
                <button className="icon-btn small" onClick={() => onRemoved(removed.filter(h => h !== data.h3[i]))}>restore</button>
              </div>
            ))}
            {sorted.length > inPlay.length && (
              <div className="more-rows">
                <button className="btn btn-line small" onClick={() => setExtra(e => e + pageSize)}>
                  Show {Math.min(pageSize, sorted.length - inPlay.length)} more ({(sorted.length - inPlay.length).toLocaleString('en-US')} left)
                </button>
              </div>
            )}
          </div>
        </div>

        <div className="content" style={{ gap: 48 }}>
          <div className="globe">
            <Suspense fallback={null}>
              <Globe data={data} classes={result.classes} inPlay={globeInPlay} pins={pinIdx} active={active} onPick={setActive} />
            </Suspense>
            <div className="globe-legend">
              <span><Mark verdict="match" />match</span><span><Mark verdict="unknown" />unknown</span><span><Mark verdict="miss" />miss</span>
            </div>
            {active !== null && <CellCard data={data} request={request} i={active} pinned={pins.includes(data.h3[active]!)}
              canPin={pins.length < MAX_COMPARE && eligible(data.h3[active]!)}
              why={removed.includes(data.h3[active]!) ? 'Removed' : CLASS_WHY[result.classes[active]!]} onPin={() => togglePin(active)} />}
          </div>
          {pinIdx.length > 0
            ? <Compare data={data} request={request} sites={pinIdx} />
            : <p className="muted small">Pick up to three sites from the list or the globe to compare them.</p>}
        </div>
      </div>
    </Page>
  );
}

/** Why a site can't be compared, by the engine's search class (0 is in play). */
const CLASS_WHY: (string | undefined)[] = [undefined, 'Misses a required trait', 'A required trait is unknown', 'Past a limit'];

function CellCard({ data, request, i, pinned, canPin, why, onPin }: { data: Dataset; request: PlanRequest; i: number; pinned: boolean; canPin: boolean; why?: string; onPin: () => void }) {
  return (
    <div className="cell-card">
      <span className="mono">{coordLabel(data, i)}</span>
      {traitCells(data, request, i).map(t => (
        <span key={t.dimension} className="small card-row">
          <Verdict verdict={t.verdict}>{DIMENSION_LABEL[t.dimension]}</Verdict><span className="muted mono">{t.detail}</span>
        </span>
      ))}
      {siteFacts(data, i).map(f => (
        <span key={f.label} className="small card-row"><span className="muted">{f.label}</span><span className="muted mono">{f.value ?? 'no data'}</span></span>
      ))}
      {(pinned || canPin) ? <button className="btn btn-line small" onClick={onPin}>{pinned ? 'Stop comparing' : 'Compare'}</button>
        : why && <span className="muted small">{why}</span>}
    </div>
  );
}

/** One strip per banded trait: the accepted band, then one lane per compared site with its value. */
function Compare({ data, request, sites }: { data: Dataset; request: PlanRequest; sites: number[] }) {
  const cells = sites.map(i => traitCells(data, request, i));
  return (
    <section>
      <div className="compare-head">
        {sites.map((i, k) => <span key={i} className="mono"><span className="swatch" style={{ background: SERIES[k] }} />{coordLabel(data, i)}</span>)}
      </div>
      <div className="fit">
        {requirements(data, request).map(r => {
          const vals = cells.map(cs => cs.find(x => x.dimension === r.dimension)!);
          const label = <span>{DIMENSION_LABEL[r.dimension]}</span>;
          if (!r.band) return [<span key={`l${r.dimension}`}>{label}</span>, <span key={`s${r.dimension}`} className="v-unknown small">no accepted band</span>];
          const known = vals.map(v => v.value).filter((v): v is number => v !== null);
          let lo = Math.min(r.band.lo, ...known), hi = Math.max(r.band.hi, ...known);
          if (lo === hi) { lo -= 1; hi += 1; }
          const pad = (hi - lo) * 0.06;
          // a scale of slopes or shares shouldn't run below zero
          const floor = r.band.lo >= 0 && known.every(v => v >= 0) ? 0 : -Infinity;
          lo = Math.max(floor, lo - pad); hi += pad;
          const pos = (v: number) => ((v - lo) / (hi - lo)) * 100;
          const f = (v: number) => fmt(v, r.unit) ?? String(v);
          // band edges and scale ends are set numbers, so 10 reads "10°", not "10.0°"
          const fe = (v: number) => (Number.isInteger(v) && r.unit === 'deg' ? `${v}°` : f(v));
          return [
            <span key={`l${r.dimension}`}>{label}</span>,
            <div key={`s${r.dimension}`}>
              <div className="strip" style={{ height: vals.length * 18 + 4 }}>
                <span className="b" style={{ left: `${pos(r.band.lo)}%`, width: `${pos(r.band.hi) - pos(r.band.lo)}%` }} />
                {vals.map((v, k) => {
                  const top = 2 + k * 18;
                  if (v.value === null) return <span key={k} className="lane-val v-unknown" style={{ left: 0, top }}>no data</span>;
                  const x = pos(v.value), right = x > 75;
                  return [
                    <span key={`m${k}`} className="m" style={{ left: `${x}%`, top: top + 4, background: SERIES[k], clipPath: v.verdict === 'miss' ? 'polygon(50% 0,100% 50%,50% 100%,0 50%)' : undefined }} />,
                    <span key={`t${k}`} className="lane-val" style={right ? { right: `${100 - x}%`, top, marginRight: 9 } : { left: `${x}%`, top, marginLeft: 9 }}>
                      {f(v.value)}{v.verdict === 'miss' ? ' · miss' : ''}
                    </span>,
                  ];
                })}
              </div>
              <div className="scale"><span>{fe(Math.round(lo * 10) / 10)}</span><span>band {fe(r.band.lo)} {r.band.hiStrict ? '≤ x <' : '–'} {fe(r.band.hi)}</span><span>{fe(Math.round(hi * 10) / 10)}</span></div>
            </div>,
          ];
        })}
      </div>
    </section>
  );
}
