import { AnimatePresence, motion } from 'motion/react';
import { useMemo, useState } from 'react';
import worldDots from '../assets/dot-matrix-world.svg';
import { METRICS } from '../data/catalog.ts';
import { AVERAGE_FIT, MAP_LAYERS, REQUIREMENT_FIT, SINGLE_MATCH_PERCENT, SITE_SHORTLIST, type Site } from '../data/placeholders/sites.ts';
import { BlockedSlot, Button, PendingTag, Swatch } from '../components/ui.tsx';
import { Footer, StepHeader } from '../components/shell.tsx';
import { chartIds, MAX_IN_CHART, seriesColor, sitesInChart, sitesInPlay, useMission, type Route } from '../state.tsx';

export function formatCoord(lat: number, lon: number) {
  return `${Math.abs(lat).toFixed(2)}°${lat >= 0 ? 'N' : 'S'} ${Math.abs(lon).toFixed(2)}°${lon >= 0 ? 'E' : 'W'}`;
}

export function SiteFinder({ go }: { go: (r: Route) => void }) {
  const { mission } = useMission();
  const inPlay = sitesInPlay(mission);
  const [hoverSite, setHoverSite] = useState<string | null>(null);

  return (
    <>
      <StepHeader
        title="Candidate analog sites."
        sub={`Earth sites to compare against your ${mission.requirements.length} mission requirement${mission.requirements.length === 1 ? '' : 's'}. No single score: each requirement is shown on its own. Remove any that clearly won't work, then compare the rest.`}
        sample
      />
      <div className="step-content finder">
        <Candidates hoverSite={hoverSite} onHover={setHoverSite} />
        <div className="finder__analysis">
          <RequirementFit hoverSite={hoverSite} onHover={setHoverSite} />
          <SiteMap hoverSite={hoverSite} onHover={setHoverSite} />
        </div>
      </div>
      <Footer onBack={() => go('metrics')} status={`${inPlay.length} sites in play · ${chartIds(mission).length} in chart`}>
        <Button disabled={chartIds(mission).length === 0} onClick={() => go('limitations')}>
          Compare limitations →
        </Button>
      </Footer>
    </>
  );
}

function Candidates({ hoverSite, onHover }: { hoverSite: string | null; onHover: (id: string | null) => void }) {
  const { mission, dispatch } = useMission();
  const all = SITE_SHORTLIST.sample;
  const removed = Object.keys(mission.removed).length;
  const full = chartIds(mission).length >= MAX_IN_CHART;
  return (
    <section className="candidates" data-pending={SITE_SHORTLIST.id} aria-label="Site candidates">
      <div className="list-header t-small t-muted">
        <span>SITE CANDIDATES</span>
        <PendingTag p={SITE_SHORTLIST} compact />
        <span className="flex" />
        <span>
          {all.length - removed} in play · {removed} removed
        </span>
      </div>
      <div className="divider" />
      <ol className="candidates__list">
        {all.map((s) => {
          const reason = mission.removed[s.id];
          const color = seriesColor(mission, s.id);
          const inChart = !!color;
          return (
            <motion.li
              key={s.id}
              layout="position"
              className={`site-row${reason ? ' is-removed' : ''}${hoverSite === s.id ? ' is-hover' : ''}`}
              onPointerEnter={() => onHover(s.id)}
              onPointerLeave={() => onHover(null)}
            >
              <div className="site-row__content">
                <span className="t-small t-muted site-row__rank" aria-hidden="true" />
                <button
                  type="button"
                  className="site-row__marker"
                  disabled={!!reason || (!inChart && full)}
                  aria-pressed={inChart}
                  aria-label={inChart ? `Remove ${s.name} from chart` : `Add ${s.name} to chart`}
                  title={!inChart && full ? `Chart holds up to ${MAX_IN_CHART} sites` : inChart ? 'In spider chart' : 'Click to compare'}
                  onClick={() => dispatch({ type: 'toggle-chart', id: s.id })}
                >
                  <Swatch color={color} />
                </button>
                <div className="site-row__copy">
                  <div className="site-row__line">
                    <span className="t-control site-row__name">{s.name}</span>
                    <span className="flex" />
                    {reason ? <span className="t-control">—</span> : <BlockedSlot p={SINGLE_MATCH_PERCENT} />}
                    {reason ? (
                      <button type="button" className="site-row__act t-small" onClick={() => dispatch({ type: 'restore-site', id: s.id })}>
                        Restore
                      </button>
                    ) : (
                      <button type="button" className="site-row__act t-small" aria-label={`Remove ${s.name}`} title="Remove this site" onClick={() => dispatch({ type: 'remove-site', id: s.id, reason: 'removed by you' })}>
                        ×
                      </button>
                    )}
                  </div>
                  <div className="site-row__line t-small t-muted">
                    <span>{reason ? `Removed · ${reason}` : s.region}</span>
                    <span className="flex" />
                    {!reason && <span>{formatCoord(s.lat, s.lon)}</span>}
                  </div>
                </div>
              </div>
              <div className="divider" />
            </motion.li>
          );
        })}
      </ol>
      <div className="chart-key t-small t-muted">
        <span className="chart-key__item">
          <Swatch color="var(--chart-series-1)" size={8} />
          In spider chart (max {MAX_IN_CHART})
        </span>
        <span className="chart-key__item">
          <Swatch color={null} size={8} />
          Click to compare · × removes a site
        </span>
      </div>
    </section>
  );
}

/* ---------- Spider chart ---------- */

const CX = 250;
const CY = 182;
const R = 128;

function polar(i: number, n: number, r: number) {
  const a = -Math.PI / 2 + (i * 2 * Math.PI) / n;
  return { x: CX + r * Math.cos(a), y: CY + r * Math.sin(a), a };
}

function RequirementFit({ hoverSite, onHover }: { hoverSite: string | null; onHover: (id: string | null) => void }) {
  const { mission } = useMission();
  const chart = sitesInChart(mission);
  const inPlay = sitesInPlay(mission).length;
  const axes = mission.requirements.map((r) => METRICS[r.metric]);
  const n = axes.length;
  const fit = REQUIREMENT_FIT.sample;

  const shapes = useMemo(
    () =>
      chart.map((s) => {
        const pts = axes
          .map((m, i) => {
            const v = fit[s.id]?.[m.id];
            return v == null ? null : polar(i, n, (v / 100) * R);
          })
          .filter((p): p is NonNullable<typeof p> => !!p);
        return { site: s, color: seriesColor(mission, s.id)!, pts, points: pts.map((p) => `${p.x.toFixed(1)},${p.y.toFixed(1)}`).join(' '), count: pts.length };
      }),
    [chart, axes, n, fit, mission],
  );
  const missingAxes = axes.filter((m) => !chart.some((s) => fit[s.id]?.[m.id] != null));

  return (
    <section className="card fit" data-pending={REQUIREMENT_FIT.id} aria-label="Requirement fit">
      <div className="card__header t-small t-muted">
        <span>REQUIREMENT FIT</span>
        <PendingTag p={REQUIREMENT_FIT} compact />
        <span className="flex" />
        <span>
          Comparing {chart.length} of {inPlay} · sample 0–100 each, rule not frozen
        </span>
      </div>
      <div className="fit__body">
        <svg className="spider" viewBox="-20 0 540 400" role="img" aria-label="Spider chart of per-requirement fit for the compared sites">
          {n >= 3 ? (
            <>
              {[0.25, 0.5, 0.75, 1].map((k) => (
                <polygon key={k} className="spider__ring" points={axes.map((_, i) => polar(i, n, R * k)).map((p) => `${p.x},${p.y}`).join(' ')} />
              ))}
              {axes.map((_, i) => {
                const p = polar(i, n, R);
                return <line key={i} className="spider__spoke" x1={CX} y1={CY} x2={p.x} y2={p.y} />;
              })}
              {[25, 50, 75].map((v) => (
                <text key={v} className="spider__tick" x={CX + 5} y={CY - (v / 100) * R + 4}>
                  {v}
                </text>
              ))}
              {shapes.map((sh, i) => {
                const dim = hoverSite && hoverSite !== sh.site.id;
                return (
                  <motion.polygon
                    key={sh.site.id}
                    points={sh.points}
                    fill={sh.color}
                    stroke={sh.color}
                    className="spider__shape"
                    style={{ transformOrigin: `${CX}px ${CY}px` }}
                    initial={{ scale: 0, opacity: 0 }}
                    animate={{ scale: 1, opacity: dim ? 0.12 : 1 }}
                    transition={{ scale: { type: 'spring', stiffness: 160, damping: 22, delay: i * 0.05 }, opacity: { duration: 0.18 } }}
                    onPointerEnter={() => onHover(sh.site.id)}
                    onPointerLeave={() => onHover(null)}
                  />
                );
              })}
              {shapes.map((sh) =>
                sh.pts.map((pt, k) => (
                  <motion.circle
                    key={`${sh.site.id}-${k}`}
                    cx={pt.x}
                    cy={pt.y}
                    r={2.5}
                    fill={sh.color}
                    initial={{ opacity: 0 }}
                    animate={{ opacity: hoverSite && hoverSite !== sh.site.id ? 0.12 : 1 }}
                    transition={{ duration: 0.2 }}
                  />
                )),
              )}
              {axes.map((m, i) => {
                const p = polar(i, n, R + 18);
                const cos = Math.cos(p.a);
                const anchor = Math.abs(cos) < 0.2 ? 'middle' : cos > 0 ? 'start' : 'end';
                const dy = Math.sin(p.a) > 0.3 ? 14 : Math.sin(p.a) < -0.3 ? -6 : 4;
                const missing = missingAxes.includes(m);
                return (
                  <text key={m.id} className={`spider__axis${missing ? ' is-missing' : ''}`} x={p.x} y={p.y + dy} textAnchor={anchor}>
                    {m.short}
                    {missing && <title>No fit sample for this requirement yet ({REQUIREMENT_FIT.id})</title>}
                  </text>
                );
              })}
              {shapes.every((sh) => sh.count < 3) && (
                <text className="spider__empty" x={CX} y={CY + 4} textAnchor="middle">
                  {missingAxes.length === n ? 'No fit samples for these requirements yet' : 'Too few fit samples to draw shapes'}
                </text>
              )}
            </>
          ) : (
            <text className="spider__axis" x={250} y={190} textAnchor="middle">
              A spider chart needs at least 3 requirements.
            </text>
          )}
        </svg>
        <div className="legend">
          <div className="legend__head t-small t-muted">
            <span>IN CHART</span>
            <span className="flex" />
            <span>AVG</span>
          </div>
          <AnimatePresence initial={false}>
            {chart.map((s) => (
              <motion.div
                key={s.id}
                className={`legend__row${hoverSite === s.id ? ' is-hover' : ''}`}
                onPointerEnter={() => onHover(s.id)}
                onPointerLeave={() => onHover(null)}
                initial={{ opacity: 0, x: 8 }}
                animate={{ opacity: 1, x: 0 }}
                exit={{ opacity: 0, x: 8 }}
              >
                <Swatch color={seriesColor(mission, s.id)} />
                <span className="t-body legend__name">{s.name}</span>
                <BlockedSlot p={AVERAGE_FIT} width={24} />
              </motion.div>
            ))}
          </AnimatePresence>
          <p className="t-small t-muted legend__note">Hover a shape to isolate it. Toggle sites in the list to compare up to {MAX_IN_CHART}.</p>
        </div>
      </div>
    </section>
  );
}

/* ---------- Site map ---------- */

// Equirectangular, cropped to 84°N … ~60°S, as drawn in Figma ("Dot-matrix world", 440 × 176).
const MAP_W = 440;
const MAP_H = 176;
function project(s: Site) {
  return { x: ((s.lon + 180) / 360) * MAP_W, y: 102.67 - 1.2223 * s.lat };
}

type Layer = 'dots' | 'elevation' | 'thermal';

function SiteMap({ hoverSite, onHover }: { hoverSite: string | null; onHover: (id: string | null) => void }) {
  const { mission, dispatch } = useMission();
  const [layer, setLayer] = useState<Layer>('dots');
  const [zoom, setZoom] = useState(1);
  const inPlay = sitesInPlay(mission);
  const removed = Object.keys(mission.removed);
  const lats = inPlay.map((s) => s.lat);
  const fmtLat = (v: number) => `${Math.round(Math.abs(v))}°${v >= 0 ? 'N' : 'S'}`;
  const layerPending = layer === 'dots' ? null : MAP_LAYERS[layer];

  // Zoom around the centre of the sites in play.
  const pts = inPlay.map(project);
  const cx = pts.length ? pts.reduce((a, p) => a + p.x, 0) / pts.length : MAP_W / 2;
  const cy = pts.length ? pts.reduce((a, p) => a + p.y, 0) / pts.length : MAP_H / 2;

  return (
    <section className="card sitemap" aria-label="Site map">
      <div className="card__header t-small t-muted">
        <span>SITE MAP</span>
        <span className="flex" />
        <div className="segmented" role="tablist" aria-label="Map layer">
          {(['dots', 'elevation', 'thermal'] as Layer[]).map((l) => (
            <button key={l} type="button" role="tab" aria-selected={layer === l} className={layer === l ? 'is-on' : ''} onClick={() => setLayer(l)}>
              {l[0].toUpperCase() + l.slice(1)}
            </button>
          ))}
        </div>
      </div>
      <div className="sitemap__row">
        <div className="sitemap__viewport">
          <motion.div
            className="sitemap__canvas"
            animate={{ scale: zoom }}
            transition={{ type: 'spring', stiffness: 200, damping: 28 }}
            style={{ transformOrigin: `${(cx / MAP_W) * 100}% ${(cy / MAP_H) * 100}%` }}
          >
            <img src={worldDots} width={MAP_W} height={MAP_H} alt="" className="sitemap__world" />
            {SITE_SHORTLIST.sample.map((s) => {
              const p = project(s);
              const color = seriesColor(mission, s.id);
              const isRemoved = s.id in mission.removed;
              return (
                <button
                  key={s.id}
                  type="button"
                  className={`pin${color ? ' pin--chart' : ''}${isRemoved ? ' pin--removed' : ''}${hoverSite === s.id ? ' is-hover' : ''}`}
                  style={{ left: `${(p.x / MAP_W) * 100}%`, top: `${(p.y / MAP_H) * 100}%`, ['--pin' as string]: color ?? 'var(--mission-muted)', ['--zoom' as string]: zoom }}
                  aria-label={`${s.name}${color ? ', in chart' : ''}${isRemoved ? ', removed' : ''}`}
                  disabled={isRemoved}
                  onClick={() => dispatch({ type: 'toggle-chart', id: s.id })}
                  onPointerEnter={() => onHover(s.id)}
                  onPointerLeave={() => onHover(null)}
                >
                  <span className="pin__label t-small">{s.name}</span>
                </button>
              );
            })}
          </motion.div>
          {layerPending && (
            <div className="sitemap__overlay">
              <PendingTag p={layerPending} />
            </div>
          )}
          <div className="zoom">
            <button type="button" aria-label="Zoom in" onClick={() => setZoom((z) => Math.min(4, z * 1.5))}>
              +
            </button>
            <button type="button" aria-label="Zoom out" onClick={() => setZoom((z) => Math.max(1, z / 1.5))}>
              −
            </button>
            <button type="button" aria-label="Open full map" title={`PENDING ${MAP_LAYERS.fullMap.id}\n${MAP_LAYERS.fullMap.awaits}`} data-pending-id={MAP_LAYERS.fullMap.id} disabled>
              ⤢
            </button>
          </div>
        </div>
        <dl className="coverage">
          <dt className="t-small t-muted">COVERAGE</dt>
          <dd className="t-category">{inPlay.length} sites in play</dd>
          <div className="kv">
            <dt className="t-small t-muted">Countries</dt>
            <dd className="t-small">{new Set(inPlay.map((s) => s.country)).size}</dd>
          </div>
          <div className="kv">
            <dt className="t-small t-muted">Latitude range</dt>
            <dd className="t-small">{lats.length ? `${fmtLat(Math.min(...lats))} – ${fmtLat(Math.max(...lats))}` : '–'}</dd>
          </div>
          <div className="kv">
            <dt className="t-small t-muted">Match range</dt>
            <dd className="t-small">
              <BlockedSlot p={SINGLE_MATCH_PERCENT} width={60} />
            </dd>
          </div>
          <div className="kv">
            <dt className="t-small t-muted">Removed</dt>
            <dd className="t-small">{removed.length ? `${removed.length} · ${removed.map((id) => SITE_SHORTLIST.sample.find((s) => s.id === id)?.name).join(', ')}` : '0'}</dd>
          </div>
        </dl>
      </div>
    </section>
  );
}
