import { AnimatePresence, motion } from 'motion/react';
import { useState } from 'react';
import { LOGISTICS_GLANCE, LOGISTICS_SUMMARY_NOTES, PLAN_PARAMETERS, SEASONAL, SEASONAL_SUMMARY, SITE_DETAIL, type SiteDetail } from '../data/placeholders/logistics.ts';
import type { World } from '../data/catalog.ts';
import { Button, Label, PendingTag, SectionHeader, Swatch, Tile } from '../components/ui.tsx';
import { Footer, StepHeader } from '../components/shell.tsx';
import { seriesColor, sitesInChart, useMission, type Route } from '../state.tsx';
import { usd, usdK } from './shared.tsx';

const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];

function rating(v: number) {
  return v >= 75 ? 'good' : v >= 50 ? 'marginal' : 'poor';
}

export function Logistics({ go }: { go: (r: Route) => void }) {
  const { mission } = useMission();
  const sites = sitesInChart(mission);
  const plan = PLAN_PARAMETERS.sample;
  const glance = LOGISTICS_GLANCE.sample;
  const costed = sites.filter((s) => glance[s.id]);
  const costs = costed.map((s) => glance[s.id].costUsd);
  const lo = costed[costs.indexOf(Math.min(...costs))];
  const hi = costed[costs.indexOf(Math.max(...costs))];
  const maxCost = Math.max(...costs, 1);
  const costRange = costs.length ? `${usdK(Math.min(...costs))} – ${usdK(Math.max(...costs))}` : '–';
  const [tab, setTab] = useState<string | null>(null);
  const active = sites.find((s) => s.id === tab) ?? sites[0];

  return (
    <>
      <StepHeader title="Logistics." sub={`What it takes to get ${plan.people} people and a rover to each site in play, and keep them working for ${plan.fieldDays} days.`} />
      <div className="step-content report">
        <div className="tiles">
          <Tile label="SITES COMPARED" value={sites.length} note={`Same ${plan.people}-person team, ${plan.fieldDays} field days`} pending={PLAN_PARAMETERS} />
          <Tile label="EST. TOTAL COST" value={costRange} note={lo && hi ? `${lo.name} lowest · ${hi.name.split(' ')[0]} highest` : 'No cost samples'} pending={LOGISTICS_GLANCE} />
          <Tile label="HUB TO SITE" value={LOGISTICS_SUMMARY_NOTES.sample.hubToSite} note={LOGISTICS_SUMMARY_NOTES.sample.hubToSiteNote} pending={LOGISTICS_SUMMARY_NOTES} />
          <Tile label="PERMIT LEAD TIME" value={LOGISTICS_SUMMARY_NOTES.sample.permitLead} note={LOGISTICS_SUMMARY_NOTES.sample.permitLeadNote} pending={LOGISTICS_SUMMARY_NOTES} />
        </div>

        <section data-pending={LOGISTICS_GLANCE.id}>
          <SectionHeader title="Logistics at a glance" sub="The same mission plan costed and routed for every site in play." pending={[LOGISTICS_GLANCE]} />
          <div className="grid-table glance" role="table">
            <div className="grid-table__head" role="row">
              {['SITE', 'NEAREST HUB', 'HUB → SITE', 'VEHICLES', 'COMMS', 'PERMITS', 'BEST WINDOW', 'EST. COST'].map((h) => (
                <span key={h} role="columnheader">{h}</span>
              ))}
            </div>
            {sites.map((s) => {
              const g = glance[s.id];
              return (
                <div className="grid-table__row grid-table__row--tall" role="row" key={s.id}>
                  <span role="cell" className="with-swatch t-body">
                    <Swatch color={seriesColor(mission, s.id)} size={8} />
                    {s.name}
                  </span>
                  {g ? (
                    <>
                      <Two a={g.hub} b={g.hubRegion} />
                      <Two a={g.travel} b={g.travelHow} />
                      <Two a={g.vehicles} b={g.vehiclesNote} />
                      <Two a={g.comms} b={g.commsNote} />
                      <Two a={`${g.permitsApproved} of ${g.permitsTotal} approved`} b={g.permitLead} />
                      <Two a={g.bestWindow} b={g.windowNote} />
                      <span role="cell" className="stack cost-cell">
                        <span className="t-body">{usdK(g.costUsd, 1)}</span>
                        <span className="bar">
                          <motion.span className="bar__fill" initial={{ width: 0 }} animate={{ width: `${(g.costUsd / maxCost) * 100}%` }} transition={{ duration: 0.6, ease: [0.22, 1, 0.36, 1] }} />
                        </span>
                      </span>
                    </>
                  ) : (
                    <span role="cell" className="t-small t-muted span-rest">
                      No logistics sample for this site · awaits {LOGISTICS_GLANCE.id}
                    </span>
                  )}
                </div>
              );
            })}
          </div>
        </section>

        <section data-pending={SEASONAL.id}>
          <SectionHeader title="Seasonal planning" sub="Field-testing feasibility by month at each site, scored 0–100 from weather, access, and daylight." pending={[SEASONAL]} />
          <div className="verdict-key t-small t-muted">
            <span><span className="t-control" style={{ color: 'var(--status-good)' }}>✓</span> Good · 75+</span>
            <span><span className="t-control" style={{ color: 'var(--status-warning)' }}>?</span> Marginal · 50–74</span>
            <span><span className="t-control" style={{ color: 'var(--status-critical)' }}>×</span> Poor · under 50</span>
          </div>
          <div className="heatmap" role="table" aria-label="Seasonal feasibility by month">
            <span />
            {MONTHS.map((m) => (
              <span key={m} className="heatmap__month t-small t-muted" role="columnheader">{m}</span>
            ))}
            {sites.map((s, row) => (
              <HeatRow key={s.id} name={s.name} color={seriesColor(mission, s.id)} values={SEASONAL.sample[s.id]} row={row} />
            ))}
            <span className="t-small t-muted heatmap__label">Sites rated good</span>
            {MONTHS.map((m, i) => {
              const good = sites.filter((s) => (SEASONAL.sample[s.id]?.[i] ?? -1) >= 75).length;
              return (
                <span key={m} className={`t-small heatmap__count${good >= Math.ceil(sites.length * 0.8) ? '' : ' t-muted'}`}>
                  {good} / {sites.length}
                </span>
              );
            })}
          </div>
          <p className="t-small heatmap__summary">{SEASONAL_SUMMARY.sample}</p>
        </section>

        <section className="site-detail" data-pending={SITE_DETAIL.id}>
          <div className="overline">
            <span>SITE DETAIL</span>
            <PendingTag p={SITE_DETAIL} />
            <span className="flex" />
            <span>Full plan for one site at a time. Switch tabs to see the others.</span>
          </div>
          <div className="tabs" role="tablist">
            {sites.map((s) => {
              const on = active?.id === s.id;
              return (
                <button key={s.id} type="button" role="tab" aria-selected={on} className={`tab${on ? ' is-on' : ''}`} onClick={() => setTab(s.id)}>
                  {on && <motion.span layoutId="site-tab" className="tab__bg" transition={{ type: 'spring', stiffness: 420, damping: 38 }} />}
                  <Swatch color={seriesColor(mission, s.id)} size={8} />
                  <span>{s.name}</span>
                </button>
              );
            })}
          </div>
          <AnimatePresence mode="wait">
            <motion.div key={active?.id ?? 'none'} initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -4 }} transition={{ duration: 0.2 }}>
              {active && SITE_DETAIL.sample[active.id] ? (
                <Detail d={SITE_DETAIL.sample[active.id]} world={mission.world} people={plan.people} days={plan.fieldDays} />
              ) : (
                <div className="empty-state">
                  <p className="t-category">No field plan for {active?.name ?? 'this site'} yet.</p>
                  <p className="t-small t-muted">The Figma file only draws Mauna Kea's plan. This tab fills in when {SITE_DETAIL.id} has a row for this site.</p>
                </div>
              )}
            </motion.div>
          </AnimatePresence>
        </section>
      </div>
      <Footer onBack={() => go('limitations')} status={`${sites.length} sites · est. ${costRange}`}>
        <Button onClick={() => go('risks')}>Continue →</Button>
      </Footer>
    </>
  );
}

function Two({ a, b }: { a: string; b: string }) {
  return (
    <span role="cell" className="stack">
      <span className="t-body">{a}</span>
      <span className="t-small t-muted">{b}</span>
    </span>
  );
}

function HeatRow({ name, color, values, row }: { name: string; color: string | null; values?: number[]; row: number }) {
  return (
    <>
      <span className="with-swatch t-body heatmap__label" role="rowheader">
        <Swatch color={color} size={8} />
        {name}
      </span>
      {MONTHS.map((m, i) => {
        const v = values?.[i];
        return v == null ? (
          <span key={m} className="heatmap__cell heatmap__cell--none t-small t-muted">–</span>
        ) : (
          <motion.span
            key={m}
            className={`heatmap__cell heatmap__cell--${rating(v)} t-small`}
            initial={{ opacity: 0, scale: 0.85 }}
            animate={{ opacity: 1, scale: 1 }}
            transition={{ delay: 0.015 * (row * 12 + i), duration: 0.25 }}
            title={`${name}, ${m}: ${v} (${rating(v)})`}
          >
            {v}
          </motion.span>
        );
      })}
    </>
  );
}

const LATENCY: { id: 'live' | World; label: string; injector: string }[] = [
  { id: 'live', label: 'Live', injector: 'Latency injector · off' },
  { id: 'moon', label: 'Moon · 2.6 s round trip', injector: 'Latency injector · +1.28 s each way (Earth-Moon light time)' },
  { id: 'mars', label: 'Mars · 6–44 min', injector: 'Latency injector · +3–22 min each way (Earth-Mars light time)' },
];

function Detail({ d, world, people, days }: { d: SiteDetail; world: World; people: number; days: number }) {
  const [latency, setLatency] = useState<'live' | World>(world);
  const vehiclesTotal = d.vehicles.reduce((a, v) => a + v.costUsd, 0);
  const massTotal = d.payload.reduce((a, p) => a + p.massKg, 0);
  const subtotal = d.costs.reduce((a, c) => a + c.usd, 0);
  const contingency = Math.round((subtotal * d.contingencyPct) / 100);
  const injector = LATENCY.find((l) => l.id === latency)!.injector;

  return (
    <div className="detail">
      {/* Transport & cargo */}
      <div className="two-col">
        <div>
          <SectionHeader title="Transport & cargo" sub="Moving people and heavy payloads from the nearest hub to the field site." />
          <Label>ROUTE · HUB TO SITE</Label>
          <ol className="route">
            {d.route.stops.map((stop, i) => (
              <li key={stop.name}>
                <div className="route__stop">
                  <span className={`route__dot${stop.field ? ' is-field' : ''}`} aria-hidden />
                  <div className="stack flex">
                    <span className="t-body">{stop.name}</span>
                    <span className="t-small t-muted">{stop.note}</span>
                  </div>
                  <span className="t-small t-muted">{stop.altitude}</span>
                </div>
                {d.route.legs[i] && <p className="route__leg t-small">{d.route.legs[i]}</p>}
              </li>
            ))}
          </ol>
          <Label>OFF-ROAD VEHICLE RENTALS</Label>
          <table className="table">
            <thead>
              <tr>
                <th>VEHICLE</th>
                <th className="num">QTY</th>
                <th className="num">DAYS</th>
                <th className="num">COST</th>
              </tr>
            </thead>
            <tbody>
              {d.vehicles.map((v) => (
                <tr key={v.name}>
                  <td>{v.name}</td>
                  <td className="num">{v.qty}</td>
                  <td className="num">{v.days}</td>
                  <td className="num">{usd(v.costUsd)}</td>
                </tr>
              ))}
              <tr>
                <td>Total</td>
                <td />
                <td />
                <td className="num">{usd(vehiclesTotal)}</td>
              </tr>
            </tbody>
          </table>
        </div>
        <div className="detail__right">
          <Label>PAYLOAD DIMENSIONS</Label>
          <table className="table">
            <thead>
              <tr>
                <th>ITEM</th>
                <th className="num">L × W × H</th>
                <th className="num">MASS</th>
              </tr>
            </thead>
            <tbody>
              {d.payload.map((p) => (
                <tr key={p.item}>
                  <td>{p.item}</td>
                  <td className="num">{p.dims}</td>
                  <td className="num">{p.massKg} kg</td>
                </tr>
              ))}
              <tr>
                <td>Total</td>
                <td />
                <td className="num">{massTotal} kg</td>
              </tr>
            </tbody>
          </table>
          <div className="card cold-chain">
            <div className="row">
              <span className="t-small t-muted">COLD-CHAIN SHIPPING · SAMPLES</span>
              <span className="flex" />
              <span className="t-body">{d.coldChain.temperature}</span>
            </div>
            <ul className="dash-list t-body">
              {d.coldChain.lines.map((l) => (
                <li key={l}>{l}</li>
              ))}
            </ul>
          </div>
        </div>
      </div>

      {/* Habitat + comms */}
      <div className="two-col">
        <div>
          <SectionHeader title="Habitat & life support" sub={`Planned daily burn rate for ${people} people, plus waste and power.`} />
          <Label>DAILY BURN RATE</Label>
          <div className="burn">
            {d.burn.map((b) => (
              <div className="card burn__card" key={b.label}>
                <p className="t-small t-muted">{b.label}</p>
                <p>
                  <span className="t-section">{b.perDay}</span> <span className="t-small t-muted">{b.unit}</span>
                </p>
                <p className="t-small">
                  {b.perDay * days} {b.unit.split(' / ')[0]} over {days} days
                </p>
                <span className="bar">
                  <motion.span className="bar__fill" initial={{ width: 0 }} animate={{ width: `${(b.stockDays / days) * 100}%` }} transition={{ duration: 0.6 }} />
                </span>
                <p className="t-small t-muted">{b.stockDays} days of stock on site</p>
              </div>
            ))}
          </div>
          <p className="t-small t-muted">{d.resupplyNote}</p>
          <div className="burn burn--two">
            <div className="card">
              <p className="t-small t-muted">WASTE · PACK IN, PACK OUT</p>
              <ul className="dash-list t-small">
                {d.waste.map((w) => <li key={w}>{w}</li>)}
              </ul>
            </div>
            <div className="card">
              <p className="t-small t-muted">POWER SETUP</p>
              <ul className="dash-list t-small">
                {d.power.map((w) => <li key={w}>{w}</li>)}
              </ul>
            </div>
          </div>
        </div>
        <div>
          <SectionHeader title="Comms architecture" sub="Local network, satellite uplinks, and simulated mission-control latency." />
          <Label>NETWORK PATH</Label>
          <div className="netpath">
            <div className="netnode netnode--accent">
              <div className="stack">
                <span className="t-body">Mission control (simulated)</span>
                <span className="t-small t-muted">Remote ops team follows a flight-style timeline</span>
              </div>
            </div>
            <AnimatePresence mode="wait">
              <motion.p key={injector} className="netlink t-small" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} transition={{ duration: 0.15 }}>
                {injector}
              </motion.p>
            </AnimatePresence>
            <div className="netpath__pair">
              {d.network.uplinks.map((u) => (
                <div className="netnode" key={u.name}>
                  <div className="stack">
                    <span className="t-body">{u.name}</span>
                    <span className="t-small t-muted">{u.role}</span>
                  </div>
                  <span className="t-small">{u.rate}</span>
                </div>
              ))}
            </div>
            <p className="netlink t-small">{d.network.links[0]}</p>
            <div className="netnode">
              <div className="stack">
                <span className="t-body">{d.network.camp.name}</span>
                <span className="t-small t-muted">{d.network.camp.detail}</span>
              </div>
              <span className="t-small">{d.network.camp.size}</span>
            </div>
            <p className="netlink t-small">{d.network.links[1]}</p>
            <div className="netnode">
              <div className="stack">
                <span className="t-body">{d.network.field.name}</span>
                <span className="t-small t-muted">{d.network.field.detail}</span>
              </div>
              <span className="t-small">{d.network.field.rate}</span>
            </div>
          </div>
          <div className="row latency">
            <span className="t-small t-muted">SIMULATED LATENCY</span>
            <span className="flex" />
            <div className="segmented" role="radiogroup" aria-label="Simulated latency">
              {LATENCY.map((l) => (
                <button key={l.id} type="button" role="radio" aria-checked={latency === l.id} className={latency === l.id ? 'is-on' : ''} onClick={() => setLatency(l.id)}>
                  {l.label}
                </button>
              ))}
            </div>
          </div>
        </div>
      </div>

      {/* Permits + cost */}
      <div className="two-col">
        <div>
          <SectionHeader title="Permits & administration" sub="The approvals pipeline, and what the whole mission is expected to cost." />
          <Label>PERMIT PIPELINE</Label>
          <ul className="permits">
            {d.permits.map((p) => (
              <li key={p.name}>
                <span className={`t-small permit-status permit-status--${p.status}`}>
                  <span aria-hidden>{p.status === 'approved' ? '✓' : p.status === 'in-review' ? '?' : '○'}</span> {p.status === 'approved' ? 'Approved' : p.status === 'in-review' ? 'In review' : 'To file'}
                </span>
                <span className="stack flex">
                  <span className="t-body">{p.name}</span>
                  <span className="t-small t-muted">{p.authority}</span>
                </span>
                <span className="stack right">
                  <span className="t-small">{p.date}</span>
                  <span className="t-small t-muted">{p.lead}</span>
                </span>
              </li>
            ))}
          </ul>
        </div>
        <div className="cost">
          <div className="section-header section-header--spacer" aria-hidden />
          <Label>ESTIMATED TOTAL MISSION COST</Label>
          <ul className="cost__list">
            {d.costs.map((c) => (
              <li key={c.label}>
                <div className="row">
                  <span className="t-body">{c.label}</span>
                  <span className="flex" />
                  <span className="t-body">{usd(c.usd)}</span>
                </div>
                <span className="bar bar--thin">
                  <motion.span className="bar__fill" initial={{ width: 0 }} animate={{ width: `${(c.usd / subtotal) * 100}%` }} transition={{ duration: 0.7, ease: [0.22, 1, 0.36, 1] }} />
                </span>
              </li>
            ))}
          </ul>
          <div className="row t-small t-muted cost__sub">
            <span>Subtotal</span>
            <span className="flex" />
            <span>{usd(subtotal)}</span>
          </div>
          <div className="row t-small t-muted cost__sub">
            <span>Contingency ({d.contingencyPct}%)</span>
            <span className="flex" />
            <span>{usd(contingency)}</span>
          </div>
          <div className="row cost__total">
            <span className="t-body">Estimated total</span>
            <span className="flex" />
            <span className="t-section">{usd(subtotal + contingency)}</span>
          </div>
        </div>
      </div>
    </div>
  );
}
