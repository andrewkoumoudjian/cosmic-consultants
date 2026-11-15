/**
 * "Top 3 Sites — Scientific Similarity" (owner spec, 2026-11-15): the first three rows of the ranked list as shown,
 * one overlapping polygon each, one spoke per trait the user set in step 3, values from similarity.ts (0–100 per trait,
 * 100 = inside the band). Missing values are listed as unavailable and never drawn as 0. With fewer than three traits a
 * radar is not valid, so it shows one bar per site per trait instead.
 */
import { useMemo, useState, type ReactNode } from 'react';
import { Collapsible } from '@base-ui/react/collapsible';
import type { Dataset } from '../../../atlas/src/planner/engine.ts';
import type { PlanRequest } from '../../../atlas/src/plan-url.ts';
import { DIMENSION_LABEL, bandLabel, coordLabel, fmt } from '../model.ts';
import { requirements } from '../../../atlas/src/planner/engine.ts';
import { closeness, limitAxes, limitCloseness, type Closeness } from '../similarity.ts';

const COLOR = ['#2dd4bf', '#fbbf24', '#a78bfa'];
const DASH = ['', '6 4', '2 3'];
type Tip = { x: number; y: number; body: ReactNode } | null;

const measuredText = (c: Closeness) => (c.measured === null ? 'no data' : fmt(c.measured, c.unit ?? 'unitless') ?? String(c.measured));
const scoreText = (c: Closeness) => (c.score === null ? 'unavailable' : String(Math.round(c.score)));

export function TopThree({ data, request, ranked }: { data: Dataset; request: PlanRequest; ranked: number[] }) {
  const top = ranked.slice(0, 3);
  const rules = [...requirements(data, request), ...limitAxes(request)] as ReturnType<typeof requirements>;
  const scores = useMemo(() => top.map(i => [...closeness(data, request, i), ...limitCloseness(data, request, i)]), [data, request, top.join(',')]);
  const [tip, setTip] = useState<Tip>(null);
  const names = top.map(i => coordLabel(data, i));
  const missing = scores.flatMap((cs, k) => cs.filter(c => c.score === null).map(c => ({ k, c })));

  return (
    <section className="card top3" aria-label="Top 3 Sites — Scientific Similarity">
      <div className="card-head">
        <div>
          <h2 className="card-title">Top 3 Sites — Scientific Similarity</h2>
          <p className="t-small muted" style={{ marginTop: 2 }}>Comparison against your mission requirements</p>
        </div>
      </div>
      {top.length === 0 ? <p className="t-small muted">No ranked sites with these settings.</p> : <>
        <ol className="top3-legend">
          {top.map((i, k) => (
            <li key={i}><Swatch k={k} /><span className="strong">#{k + 1}</span> <span className="mono">{names[k]}</span></li>
          ))}
        </ol>
        <div className="top3-plot" onMouseLeave={() => setTip(null)}>
          {rules.length >= 3
            ? <Radar scores={scores} names={names} rules={rules} onTip={setTip} />
            : <><Bars scores={scores} names={names} rules={rules} />
              <p className="t-label muted">A radar needs 3 or more spokes. Set a hard limit in Requirements to add one.</p></>}
          {tip && <div className="chart-tip" style={{ left: tip.x, top: tip.y }} role="status">{tip.body}</div>}
        </div>
        {missing.length > 0 && (
          <p className="t-label muted">Not plotted, no score: {[...new Map(missing.map(({ c }) => [`${c.dimension}|${c.why}`, c])).values()].map(c => {
            const who = missing.filter(m => m.c.dimension === c.dimension && m.c.why === c.why).map(m => `#${m.k + 1}`);
            return `${DIMENSION_LABEL[c.dimension] ?? c.dimension} (${c.why}${who.length === top.length ? '' : `, ${who.join(' ')}`})`;
          }).join(' · ')}</p>
        )}
        <Collapsible.Root>
          <Collapsible.Trigger className="evidence-trigger"><Caret />How the score works</Collapsible.Trigger>
          <Collapsible.Panel className="pillar-panel">
            <p className="t-label text-2" style={{ paddingTop: 8 }}>
              Each trait is scored on its own, in its own units. 100 means the site is inside your band. Outside it, the score
              drops with the gap, reaching 0 at the farthest any place on Earth sits from that band. Missing data is shown as
              unavailable, never as 0. Scores are never added up into one number per site.
            </p>
          </Collapsible.Panel>
        </Collapsible.Root>
      </>}
    </section>
  );
}

type Rules = ReturnType<typeof requirements>;

function Radar({ scores, names, rules, onTip }: { scores: Closeness[][]; names: string[]; rules: Rules; onTip: (t: Tip) => void }) {
  const W = 520, H = 440, cx = W / 2, cy = H / 2 + 6, R = 150;
  const n = rules.length;
  const ang = (d: number) => -Math.PI / 2 + (2 * Math.PI * d) / n;
  const pt = (d: number, v: number): [number, number] => [cx + Math.cos(ang(d)) * R * v / 100, cy + Math.sin(ang(d)) * R * v / 100];
  const show = (e: React.MouseEvent | React.FocusEvent, body: ReactNode) => {
    const host = (e.currentTarget as Element).closest('.top3-plot')!.getBoundingClientRect();
    const r = (e.currentTarget as Element).getBoundingClientRect();
    onTip({ x: r.left - host.left + r.width / 2, y: r.top - host.top, body });
  };
  const siteTip = (k: number, c: Closeness) => (
    <><b>#{k + 1} {names[k]}</b><span>{DIMENSION_LABEL[c.dimension] ?? c.dimension}</span>
      <span>Similarity: <b className="mono">{scoreText(c)}</b></span><span>Measured: <span className="mono">{measuredText(c)}</span></span></>
  );
  const axisTip = (d: number) => (
    <><b>{DIMENSION_LABEL[rules[d]!.dimension] ?? rules[d]!.dimension}</b><span className="mono muted">Band {bandLabel(rules[d]!)}</span>
      {scores.map((cs, k) => <span key={k}><Swatch k={k} /> #{k + 1}: <b className="mono">{scoreText(cs[d]!)}</b> · <span className="mono">{measuredText(cs[d]!)}</span></span>)}</>
  );

  return (
    <svg className="radar-svg" viewBox={`0 0 ${W} ${H}`} role="img"
      aria-label={`Similarity, 0 to 100 per trait, for the top ${scores.length} sites: ${scores.map((cs, k) => `#${k + 1} ${names[k]}: ${cs.map(c => `${DIMENSION_LABEL[c.dimension]} ${scoreText(c)}`).join(', ')}`).join('; ')}`}>
      {[20, 40, 60, 80, 100].map(v => (
        <polygon key={v} points={rules.map((_, d) => pt(d, v).join(',')).join(' ')} fill="none" stroke={v === 100 ? '#3a3e47' : '#272a31'} strokeWidth={1} />
      ))}
      {rules.map((_, d) => { const [x, y] = pt(d, 100); return <line key={d} x1={cx} y1={cy} x2={x} y2={y} stroke="#272a31" />; })}
      {[50, 100].map(v => <text key={v} x={cx + 4} y={pt(0, v)[1] + 12} className="radar-sub">{v}</text>)}

      {scores.map((cs, k) => {
        // Draw and shade only between neighbouring spokes that both have a score; missing data leaves a gap, never a 0.
        const segs: string[] = [], wedges: string[] = [];
        cs.forEach((c, d) => {
          const nx = cs[(d + 1) % n]!;
          if (c.score !== null && nx.score !== null) {
            segs.push(`M${pt(d, c.score).join(',')}L${pt((d + 1) % n, nx.score).join(',')}`);
            wedges.push(`M${cx},${cy}L${pt(d, c.score).join(',')}L${pt((d + 1) % n, nx.score).join(',')}Z`);
          }
        });
        return (
          <g key={k}>
            <path d={wedges.join('')} fill={COLOR[k]} fillOpacity={0.16} stroke="none" />
            <path d={segs.join('')} fill="none" stroke={COLOR[k]} strokeWidth={1.75} strokeDasharray={DASH[k]} strokeLinejoin="round" />
            {cs.map((c, d) => c.score !== null && (
              <g key={d}>
                <Marker k={k} x={pt(d, c.score)[0]} y={pt(d, c.score)[1]} />
                <circle cx={pt(d, c.score)[0]} cy={pt(d, c.score)[1]} r={9} fill="#000" fillOpacity={0} tabIndex={0} className="hit"
                  aria-label={`#${k + 1} ${names[k]}, ${DIMENSION_LABEL[c.dimension]}: ${scoreText(c)}, measured ${measuredText(c)}`}
                  onMouseEnter={e => show(e, siteTip(k, c))} onFocus={e => show(e, siteTip(k, c))} onBlur={() => onTip(null)} />
              </g>
            ))}
          </g>
        );
      })}

      {rules.map((r, d) => {
        const [lx, ly] = pt(d, 122);
        const cos = Math.cos(ang(d));
        const anchor = cos > 0.3 ? 'start' : cos < -0.3 ? 'end' : 'middle';
        return (
          <g key={r.dimension} tabIndex={0} className="hit" onMouseEnter={e => show(e, axisTip(d))} onFocus={e => show(e, axisTip(d))} onBlur={() => onTip(null)}>
            <text x={lx} y={ly} textAnchor={anchor} dominantBaseline="central" className="radar-lbl" style={{ fontWeight: r.priority === 'must' ? 700 : 400 }}>{DIMENSION_LABEL[r.dimension] ?? r.dimension}</text>
            <text x={lx} y={ly + 15} textAnchor={anchor} dominantBaseline="central" className="radar-sub">{r.band ? bandLabel(r) : 'no band'}</text>
          </g>
        );
      })}
    </svg>
  );
}

/** Fewer than three traits: a radar would be a line or a point, so show one bar per site per trait. */
function Bars({ scores, names, rules }: { scores: Closeness[][]; names: string[]; rules: Rules }) {
  return (
    <div className="stack" style={{ gap: 18 }}>
      {rules.map((r, d) => (
        <div key={r.dimension} className="stack" style={{ gap: 8 }}>
          <span className="spread t-small"><span className={r.priority === 'must' ? 'strong' : undefined}>{DIMENSION_LABEL[r.dimension] ?? r.dimension}</span><span className="mono muted">Band {bandLabel(r)}</span></span>
          {scores.map((cs, k) => {
            const c = cs[d]!;
            return (
              <div key={k} className="sbar" title={`#${k + 1} ${names[k]} · ${DIMENSION_LABEL[c.dimension]} · similarity ${scoreText(c)} · measured ${measuredText(c)}`}>
                <span className="sbar-who"><Swatch k={k} />#{k + 1}</span>
                <span className="sbar-track">
                  {c.score !== null ? <span className="sbar-fill" style={{ width: `${c.score}%`, background: COLOR[k] }} /> : <span className="sbar-na">unavailable</span>}
                </span>
                <span className="sbar-val mono">{scoreText(c)}</span>
                <span className="sbar-meas mono muted">{measuredText(c)}</span>
              </div>
            );
          })}
        </div>
      ))}
      <div className="sbar-scale mono"><span>0</span><span>50</span><span>100 = inside band</span></div>
    </div>
  );
}

function Marker({ k, x, y }: { k: number; x: number; y: number }) {
  if (k === 0) return <circle cx={x} cy={y} r={3.5} fill={COLOR[0]} />;
  if (k === 1) return <rect x={x - 3.5} y={y - 3.5} width={7} height={7} fill={COLOR[1]} />;
  return <path d={`M${x},${y - 4.5}L${x + 4.5},${y + 3.5}L${x - 4.5},${y + 3.5}Z`} fill={COLOR[2]} />;
}

function Swatch({ k }: { k: number }) {
  return <svg width="22" height="10" viewBox="0 0 22 10" aria-hidden className="swatch"><line x1="1" y1="5" x2="21" y2="5" stroke={COLOR[k]} strokeWidth="2" strokeDasharray={DASH[k]} /><Marker k={k} x={11} y={5} /></svg>;
}

const Caret = () => <svg className="caret" width="10" height="10" viewBox="0 0 10 10" aria-hidden><path d="M3.5 2 6.5 5 3.5 8" fill="none" stroke="currentColor" strokeWidth="1.5" /></svg>;
