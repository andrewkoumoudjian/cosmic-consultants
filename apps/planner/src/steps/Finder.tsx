/** Step 04 Site finder (Figma 65:526). Per-trait results only: no percentage, no average (AGENTS.md rule 4). */
import { lazy, Suspense, useMemo, useState } from 'react';
import { requirements, type Dataset, type SearchResult } from '../../../atlas/src/planner/engine.ts';
import type { PlanRequest } from '../../../atlas/src/plan-url.ts';
import { CLASS_TEXT, DIMENSION_LABEL, MAX_COMPARE, SERIES, coordLabel, latLon, num, siteClass, traitCells } from '../model.ts';
import { Footer, Plate, StepHeader, Verdict } from '../ui.tsx';

const Globe = lazy(() => import('../Globe.tsx'));
type Nav = { reached: number; onStep: (n: number) => void };

export function Finder({ data, request, result, removed, onRemoved, onPins, onBack, onNext, reached, onStep }: Nav & {
  data: Dataset; request: PlanRequest; result: SearchResult; removed: string[];
  onRemoved: (r: string[]) => void; onPins: (p: string[]) => void; onBack: () => void; onNext: () => void;
}) {
  const pins = request.pins ?? [];
  const top = request.top ?? 50;
  const inPlay = useMemo(() => result.indices.filter(i => !removed.includes(data.h3[i]!)).slice(0, top), [result, removed, top, data]);
  const removedIdx = removed.map(h => data.h3.indexOf(h)).filter(i => i >= 0);
  const [active, setActive] = useState<number | null>(() => (pins[0] ? data.h3.indexOf(pins[0]) : inPlay[0] ?? null));
  const [note, setNote] = useState('');
  const pinIdx = pins.map(h => data.h3.indexOf(h)).filter(i => i >= 0);
  const c = result.counts;

  const togglePin = (i: number) => {
    const h = data.h3[i]!;
    if (pins.includes(h)) { onPins(pins.filter(p => p !== h)); setNote(''); return; }
    if (pins.length >= MAX_COMPARE) { setNote(`You can compare up to ${MAX_COMPARE} sites. Unpin one first.`); return; }
    onPins([...pins, h]); setNote('');
  };
  const remove = (i: number) => {
    const h = data.h3[i]!;
    onRemoved([...removed, h]);
    if (pins.includes(h)) onPins(pins.filter(p => p !== h));
  };
  const lats = inPlay.map(i => latLon(data, i).lat);

  return (
    <>
      <StepHeader title="Analog sites on Earth." lede={<>Every land cell checked against your {requirements(data, request).length} traits. The list keeps sites with no required miss, in the engine's order: best trade-offs first (Pareto layer), then the smallest gap on {DIMENSION_LABEL[request.sortBy ?? ''] ?? 'the sort trait'}.</>}
        step={4} reached={reached} onStep={onStep} />
      <div className="content">
        <div className="cards">
          <div className="card"><span className="fig">Land cells</span><span className="big">{c.land.toLocaleString('en-US')}</span><span className="muted t-small">H3 resolution 4</span></div>
          <div className="card"><span className="fig">Within your limits</span><span className="big">{c.withinLimits.toLocaleString('en-US')}</span><span className="muted t-small">{(c.land - c.withinLimits).toLocaleString('en-US')} left out</span></div>
          <div className="card"><span className="fig">No required miss</span><span className="big v-match">{c.matches.toLocaleString('en-US')}</span><span className="muted t-small">listed below</span></div>
          <div className="card"><span className="fig">Miss · unknown</span><span className="big">{c.misses.toLocaleString('en-US')} · <span className="v-unknown">{c.unknown.toLocaleString('en-US')}</span></span><span className="muted t-small">a required trait missed · not known</span></div>
        </div>
        {c.matches === 0 && (
          <p className="notice">No cell meets every required trait for this window. Try making one trait Preferred in step 3, widening a band, or choosing other months. The map still shows where each cell missed.</p>
        )}

        <div className="finder">
          <div className="finder-side">
            <div>
              <div className="plate-head" style={{ marginBottom: 8 }}>
                <span className="fig">Site candidates</span>
                <span className="muted t-small">{inPlay.length} shown · {removed.length} removed</span>
              </div>
              <div className="site-list" role="list">
                {inPlay.map((i, rank) => {
                  const h = data.h3[i]!, pinAt = pins.indexOf(h), layer = result.layers.get(i);
                  return (
                    <div key={h} role="listitem" className="site" data-active={active === i ? '' : undefined} onClick={() => setActive(i)}>
                      <span className="muted">{String(rank + 1).padStart(2, '0')}</span>
                      <button className="compare-box" data-on={pinAt >= 0 ? '' : undefined} aria-pressed={pinAt >= 0}
                        aria-label={pinAt >= 0 ? 'Remove from comparison' : 'Add to comparison'}
                        style={pinAt >= 0 ? { background: SERIES[pinAt] } : undefined}
                        onClick={e => { e.stopPropagation(); togglePin(i); }} />
                      <span style={{ minWidth: 0 }}>
                        <span style={{ display: 'flex', justifyContent: 'space-between', gap: 8 }}>
                          <b style={{ fontWeight: 500 }}>{coordLabel(data, i)}</b>
                          <button className="btn-ghost link t-small" style={{ textDecoration: 'none', color: 'var(--ink-faint)' }}
                            aria-label={`Remove ${h}`} onClick={e => { e.stopPropagation(); remove(i); }}>remove ×</button>
                        </span>
                        <span className="muted t-small">{h} · {layer ? `Pareto layer ${layer}` : 'not ranked: has an unknown trait'}</span>
                        <span className="chips">
                          {traitCells(data, request, i).map(t => (
                            <span key={t.dimension} className="t-small" title={t.detail}>
                              <Verdict verdict={t.verdict}><span className={t.priority === 'must' ? undefined : 'muted'}>{DIMENSION_LABEL[t.dimension]}</span></Verdict>
                            </span>
                          ))}
                        </span>
                      </span>
                    </div>
                  );
                })}
                {removedIdx.map(i => (
                  <div key={data.h3[i]} role="listitem" className="site" style={{ opacity: 0.6 }}>
                    <span className="muted">—</span><span />
                    <span style={{ display: 'flex', justifyContent: 'space-between' }}>
                      <s>{coordLabel(data, i)}</s>
                      <button className="link t-small" onClick={() => onRemoved(removed.filter(h => h !== data.h3[i]))}>Restore</button>
                    </span>
                  </div>
                ))}
              </div>
              <p className="t-small muted" style={{ marginTop: 10 }}>■ in comparison (max {MAX_COMPARE}) · □ click to compare · remove × takes a site out of play</p>
              {note && <p className="t-small v-miss" role="status">{note}</p>}
            </div>
          </div>

          <div className="finder-side">
            <Plate fig="FIG. 04 — Requirement fit" title={null}
              aside={<span className="muted t-small">Comparing {pinIdx.length} of {inPlay.length} · each trait on its own scale</span>}>
              <FitStrips data={data} request={request} sites={pinIdx} />
            </Plate>

            <Plate fig="FIG. 05 — Site map" aside={<span className="muted t-small">Drag to turn · click a dot to open it</span>}>
              <div className="map-row">
                <div>
                  <div className="globe-wrap">
                    <Suspense fallback={<div className="loading" style={{ minHeight: 0, height: '100%' }}><span className="muted">Drawing 91,800 cells…</span></div>}>
                      <Globe data={data} classes={result.classes} inPlay={inPlay} pins={pinIdx} active={active}
                        onPick={i => { setActive(i); }} />
                    </Suspense>
                  </div>
                  <div className="globe-legend t-small">
                    <span><span className="mark match" />no required miss</span>
                    <span><span className="mark unknown" />required trait unknown</span>
                    <span><span className="swatch" style={{ background: '#b8b3c4' }} />required trait missed</span>
                    <span><span className="swatch" style={{ background: '#ddd5c3' }} />outside your limits</span>
                  </div>
                </div>
                <div>
                  <div className="fig">Coverage</div>
                  <div className="t-section" style={{ margin: '6px 0 10px' }}>{inPlay.length} sites in play</div>
                  <div className="kv"><span className="muted">Latitude range</span><span>{lats.length ? `${num(Math.min(...lats))}° to ${num(Math.max(...lats))}°` : '—'}</span></div>
                  <div className="kv"><span className="muted">Pareto layer 1</span><span>{inPlay.filter(i => result.layers.get(i) === 1).length}</span></div>
                  <div className="kv"><span className="muted">Not ranked (unknowns)</span><span>{inPlay.filter(i => !result.layers.has(i)).length}</span></div>
                  <div className="kv"><span className="muted">Removed</span><span>{removed.length}</span></div>
                  {active !== null && <ActiveSite data={data} request={request} i={active} pinned={pins.includes(data.h3[active]!)} onPin={() => togglePin(active)} />}
                </div>
              </div>
            </Plate>
          </div>
        </div>
      </div>
      <Footer step={4} onBack={onBack} next={onNext} nextLabel="Compare limitations →" nextDisabled={pinIdx.length === 0}
        note={`${inPlay.length} sites in play · ${pinIdx.length} compared`} />
    </>
  );
}

function ActiveSite({ data, request, i, pinned, onPin }: { data: Dataset; request: PlanRequest; i: number; pinned: boolean; onPin: () => void }) {
  const cells = traitCells(data, request, i);
  return (
    <div style={{ marginTop: 18 }}>
      <div className="fig">Open cell</div>
      <div style={{ margin: '4px 0 2px', fontWeight: 500 }}>{coordLabel(data, i)}</div>
      <div className="t-small muted">{data.h3[i]}</div>
      <ul className="plain t-small" style={{ marginTop: 8 }}>
        {cells.map(t => <li key={t.dimension}><Verdict verdict={t.verdict}>{DIMENSION_LABEL[t.dimension]}</Verdict><div className="muted">{t.detail}</div></li>)}
      </ul>
      <button className="btn btn-secondary" style={{ marginTop: 10, width: '100%' }} onClick={onPin}>{pinned ? 'Remove from comparison' : 'Add to comparison'}</button>
    </div>
  );
}

/** One strip per banded trait: the accepted band, and a mark for each compared site. */
function FitStrips({ data, request, sites }: { data: Dataset; request: PlanRequest; sites: number[] }) {
  if (!sites.length) return <p className="muted">Tick up to {MAX_COMPARE} sites in the list to compare them here.</p>;
  const rules = requirements(data, request);
  const cellsBySite = sites.map(i => traitCells(data, request, i));
  return (
    <div className="fit">
      <div style={{ display: 'flex', gap: 16, flexWrap: 'wrap' }}>
        {sites.map((i, k) => (
          <span key={i} className="t-small" style={{ display: 'inline-flex', gap: 6, alignItems: 'center' }}>
            <span className="swatch" style={{ background: SERIES[k] }} />{coordLabel(data, i)}
            <span className="muted">· {CLASS_TEXT[siteClass(data, request, i)]}</span>
          </span>
        ))}
      </div>
      {rules.map(r => {
        const values = cellsBySite.map(cs => cs.find(c => c.dimension === r.dimension)!);
        if (!r.band) {
          return (
            <div key={r.dimension} className="fit-row">
              <span>{DIMENSION_LABEL[r.dimension]}<div className="t-small muted">{r.priority === 'must' ? 'Required' : 'Preferred'}</div></span>
              <span className="t-small v-unknown">No accepted band, so this trait is unknown at every site.</span>
            </div>
          );
        }
        const known = values.map(v => v.value).filter((v): v is number => v !== null);
        let lo = Math.min(r.band.lo, ...known), hi = Math.max(r.band.hi, ...known);
        if (lo === hi) { lo -= 1; hi += 1; }
        const pad = (hi - lo) * 0.08; lo -= pad; hi += pad;
        const at = (v: number) => `${((v - lo) / (hi - lo)) * 100}%`;
        return (
          <div key={r.dimension} className="fit-row">
            <span>{DIMENSION_LABEL[r.dimension]}<div className="t-small muted">{r.priority === 'must' ? 'Required' : 'Preferred'} · {r.unit}</div></span>
            <div>
              <div className="strip" aria-label={`${r.dimension}: band ${r.band.lo} to ${r.band.hi} ${r.unit ?? ''}`}>
                <span className="band" style={{ left: at(r.band.lo), width: `calc(${at(r.band.hi)} - ${at(r.band.lo)})` }} />
                {values.map((v, k) => v.value === null
                  ? <span key={k} className="off v-unknown" style={{ left: `${2 + k * 4}%` }} title="unknown">?</span>
                  : <span key={k} className="mark-at" title={`${num(v.value)} ${r.unit ?? ''}: ${v.verdict}`}
                      style={{ left: at(v.value), background: SERIES[k], clipPath: v.verdict === 'miss' ? 'polygon(50% 0, 100% 50%, 50% 100%, 0 50%)' : undefined }} />)}
              </div>
              <div className="strip-scale"><span>{num(lo)}</span><span>band {num(r.band.lo)}–{num(r.band.hi)}</span><span>{num(hi)}</span></div>
            </div>
          </div>
        );
      })}
      <p className="t-small muted">Monthly traits show the worst month in your window. A diamond marks a miss.</p>
    </div>
  );
}

