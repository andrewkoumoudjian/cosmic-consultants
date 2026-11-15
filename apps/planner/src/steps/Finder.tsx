/** Step 4 Sites. Per-trait results only: no percentage, no average (AGENTS.md rule 4). */
import { lazy, Suspense, useMemo, useState } from 'react';
import { requirements, type Dataset, type SearchResult } from '../../../atlas/src/planner/engine.ts';
import type { PlanRequest } from '../../../atlas/src/plan-url.ts';
import { DIMENSION_LABEL, MAX_COMPARE, SERIES, coordLabel, num, traitCells } from '../model.ts';
import { Mark, Page, Verdict } from '../ui.tsx';

const Globe = lazy(() => import('../Globe.tsx'));

export function Finder({ data, request, result, removed, onRemoved, onPins, eligible, onBack, onNext }: {
  data: Dataset; request: PlanRequest; result: SearchResult; removed: string[];
  onRemoved: (r: string[]) => void; onPins: (p: string[]) => void;
  /** Still in play: the engine's class 0 and not removed. Only these can be compared. */
  eligible: (h3: string) => boolean; onBack: () => void; onNext: () => void;
}) {
  const pins = request.pins ?? [];
  const inPlay = useMemo(() => result.indices.filter(i => !removed.includes(data.h3[i]!)).slice(0, request.top ?? 50), [result, removed, request.top, data]);
  const pinIdx = pins.map(h => data.h3.indexOf(h)).filter(i => i >= 0);
  const [active, setActive] = useState<number | null>(() => pinIdx[0] ?? inPlay[0] ?? null);
  const c = result.counts;

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
      </div>}>
      {c.matches === 0 && <p className="warn">No site meets every required trait. Make one Preferred, widen a band, or change months.</p>}
      <div className="finder">
        <div className="sites" role="list" aria-label="Sites">
          {inPlay.map((i, rank) => {
            const h = data.h3[i]!, at = pins.indexOf(h);
            return (
              <div key={h} role="listitem" className="site" data-active={active === i ? '' : undefined} onClick={() => setActive(i)} title={h}>
                <span className="rank">{rank + 1}</span>
                <button className="pin" aria-pressed={at >= 0} aria-label={at >= 0 ? 'Stop comparing' : 'Compare'}
                  disabled={at < 0 && pins.length >= MAX_COMPARE} style={at >= 0 ? { background: SERIES[at] } : undefined}
                  onClick={e => { e.stopPropagation(); togglePin(i); }} />
                <span>
                  <span className="mono">{coordLabel(data, i)}</span>
                  <span className="glyphs small">
                    {traitCells(data, request, i).map(t => <Verdict key={t.dimension} verdict={t.verdict}><span className="muted">{DIMENSION_LABEL[t.dimension]}</span></Verdict>)}
                  </span>
                </span>
                <button className="icon-btn" aria-label={`Remove ${h}`} onClick={e => { e.stopPropagation(); remove(i); }}>×</button>
              </div>
            );
          })}
          {removed.map(h => data.h3.indexOf(h)).filter(i => i >= 0).map(i => (
            <div key={data.h3[i]} className="removed small">
              <s className="mono">{coordLabel(data, i)}</s>
              <button className="icon-btn small" onClick={() => onRemoved(removed.filter(h => h !== data.h3[i]))}>restore</button>
            </div>
          ))}
        </div>

        <div className="content" style={{ gap: 48 }}>
          <div className="globe">
            <Suspense fallback={null}>
              <Globe data={data} classes={result.classes} inPlay={inPlay} pins={pinIdx} active={active} onPick={setActive} />
            </Suspense>
            <div className="globe-legend">
              <span><Mark verdict="match" />match</span><span><Mark verdict="unknown" />unknown</span>
            </div>
            {active !== null && <CellCard data={data} request={request} i={active} pinned={pins.includes(data.h3[active]!)}
              canPin={pins.length < MAX_COMPARE && eligible(data.h3[active]!)}
              why={removed.includes(data.h3[active]!) ? 'Removed' : CLASS_WHY[result.classes[active]!]} onPin={() => togglePin(active)} />}
          </div>
          {pinIdx.length > 0 && <Compare data={data} request={request} sites={pinIdx} />}
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
        <span key={t.dimension} className="small" style={{ display: 'flex', justifyContent: 'space-between', gap: 16 }}>
          <Verdict verdict={t.verdict}>{DIMENSION_LABEL[t.dimension]}</Verdict><span className="muted mono">{t.detail}</span>
        </span>
      ))}
      {(pinned || canPin) ? <button className="btn btn-line small" onClick={onPin}>{pinned ? 'Stop comparing' : 'Compare'}</button>
        : why && <span className="muted small">{why}</span>}
    </div>
  );
}

/** One strip per banded trait: the accepted band and each compared site's value. */
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
          const label = <span>{DIMENSION_LABEL[r.dimension]} <span className="muted small">{r.unit}</span></span>;
          if (!r.band) return [<span key={`l${r.dimension}`}>{label}</span>, <span key={`s${r.dimension}`} className="v-unknown small">no band</span>];
          const known = vals.map(v => v.value).filter((v): v is number => v !== null);
          let lo = Math.min(r.band.lo, ...known), hi = Math.max(r.band.hi, ...known);
          if (lo === hi) { lo -= 1; hi += 1; }
          const pad = (hi - lo) * 0.06; lo -= pad; hi += pad;
          const at = (v: number) => `${((v - lo) / (hi - lo)) * 100}%`;
          return [
            <span key={`l${r.dimension}`}>{label}</span>,
            <div key={`s${r.dimension}`}>
              <div className="strip" style={{ height: 8 + vals.length * 8 }}>
                <span className="b" style={{ left: at(r.band.lo), width: `calc(${at(r.band.hi)} - ${at(r.band.lo)})` }} />
                {vals.map((v, k) => v.value === null
                  ? <span key={k} className="q v-unknown small" style={{ left: 0, top: k * 8 - 2 }}>?</span>
                  : <span key={k} className="m" title={`${num(v.value)} ${r.unit ?? ''}`}
                      style={{ left: at(v.value), top: 3 + k * 8, background: SERIES[k], clipPath: v.verdict === 'miss' ? 'polygon(50% 0,100% 50%,50% 100%,0 50%)' : undefined }} />)}
              </div>
              <div className="scale"><span>{num(lo)}</span><span>{num(r.band.lo)} – {num(r.band.hi)}</span><span>{num(hi)}</span></div>
            </div>,
          ];
        })}
      </div>
    </section>
  );
}
