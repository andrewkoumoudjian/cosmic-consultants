import { motion } from 'motion/react';
import { Fragment, useState } from 'react';
import { band, LEVELS, LIKELIHOOD_LABELS, NEXT_STEP, RISK_CATEGORIES, RISK_REGISTER, riskBand, riskOrder, SEVERITY_LABELS, type Risk, type RiskBand } from '../data/placeholders/risks.ts';
import { Button, SectionHeader, Swatch, Tile } from '../components/ui.tsx';
import { Footer, StepHeader } from '../components/shell.tsx';
import { seriesColor, sitesInChart, useMission, type Route } from '../state.tsx';
import { SiteRefs } from './shared.tsx';

const BAND: Record<RiskBand, { glyph: string; label: string; color: string }> = {
  high: { glyph: '▲', label: 'High', color: 'var(--status-critical)' },
  medium: { glyph: '■', label: 'Medium', color: 'var(--status-warning)' },
  low: { glyph: '▼', label: 'Low', color: 'var(--status-good)' },
};

const applies = (r: Risk, siteId: string) => r.sites === 'all' || r.sites.includes(siteId);

export function Risks({ go }: { go: (r: Route) => void }) {
  const { mission } = useMission();
  const sites = sitesInChart(mission);
  const [hover, setHover] = useState<string | null>(null);
  const risks = RISK_REGISTER.sample.filter((r) => sites.some((s) => applies(r, s.id)));
  const high = risks.filter((r) => riskBand(r) === 'high');
  const medium = risks.filter((r) => riskBand(r) === 'medium');
  const low = risks.filter((r) => riskBand(r) === 'low');
  const cats = new Set(risks.map((r) => r.category)).size;
  const sharedHigh = high.filter((r) => sites.every((s) => applies(r, s.id)));

  return (
    <>
      <StepHeader title="Risks." sub="What could go wrong at each site in play, how likely and how serious it is, and how to reduce it." sample />
      <div className="step-content report">
        <div className="tiles">
          <Tile label="RISKS IDENTIFIED" value={risks.length} note={`Across ${cats} categories and ${sites.length} sites`} pending={RISK_REGISTER} />
          <Tile label="HIGH" icon={<span style={{ color: BAND.high.color }}>▲ </span>} value={high.length} note="Likely and severe · mitigate before go" pending={RISK_REGISTER} />
          <Tile label="MEDIUM" icon={<span style={{ color: BAND.medium.color }}>■ </span>} value={medium.length} note="On the diagonal · monitor in the field" pending={RISK_REGISTER} />
          <Tile label="LOW" icon={<span style={{ color: BAND.low.color }}>▼ </span>} value={low.length} note="Unlikely or minor · note and accept" pending={RISK_REGISTER} />
        </div>

        <div className="two-col risks-top" data-pending={RISK_REGISTER.id}>
          <section>
            <SectionHeader title="Risk matrix" sub="Likelihood against severity, each low / medium / high. Each tag is a risk from the register below." pending={[RISK_REGISTER]} />
            <div className="rmatrix" role="table" aria-label="Risk matrix, likelihood by severity">
              {[...LEVELS].reverse().map((l) => (
                <Fragment key={l}>
                  <span className="rmatrix__ylab t-small t-muted" role="rowheader">
                    {LIKELIHOOD_LABELS[l]}
                  </span>
                  {LEVELS.map((s) => {
                    const here = risks.filter((r) => r.likelihood === l && r.severity === s);
                    return (
                      <span key={s} role="cell" className={`rmatrix__cell rmatrix__cell--${band(l, s)}`}>
                        <span className="rmatrix__tags">
                          {here.map((r) => (
                            <button
                              key={r.id}
                              type="button"
                              className={`rtag t-small${hover === r.id ? ' is-hover' : ''}`}
                              onPointerEnter={() => setHover(r.id)}
                              onPointerLeave={() => setHover(null)}
                              onFocus={() => setHover(r.id)}
                              onBlur={() => setHover(null)}
                              onClick={() => document.getElementById(`risk-${r.id}`)?.scrollIntoView({ behavior: 'smooth', block: 'center' })}
                              title={r.name}
                            >
                              {r.id}
                            </button>
                          ))}
                        </span>
                      </span>
                    );
                  })}
                </Fragment>
              ))}
              <span />
              {LEVELS.map((s) => (
                <span key={s} className="rmatrix__xlab t-small t-muted">
                  {SEVERITY_LABELS[s]}
                </span>
              ))}
            </div>
            <p className="t-small t-muted rmatrix__axes">↑ LIKELIHOOD &nbsp;&nbsp;&nbsp; SEVERITY →</p>
            <p className="t-small t-muted rmatrix__key">
              {(['high', 'medium', 'low'] as RiskBand[]).map((b) => (
                <span key={b}>
                  <span style={{ color: BAND[b].color }}>{BAND[b].glyph}</span> {BAND[b].label}
                </span>
              ))}
            </p>
          </section>

          <section>
            <SectionHeader title="Exposure by site" sub="Worst risk band each site carries in every category." />
            <div className="grid-table exposure" role="table">
              <div className="grid-table__head" role="row">
                <span role="columnheader">SITE</span>
                {RISK_CATEGORIES.map((c) => (
                  <span key={c.id} role="columnheader">{c.short}</span>
                ))}
                <span role="columnheader">HIGH RISKS</span>
              </div>
              {sites.map((s) => {
                const mine = risks.filter((r) => applies(r, s.id));
                return (
                  <div className="grid-table__row" role="row" key={s.id}>
                    <span role="cell" className="with-swatch t-body">
                      <Swatch color={seriesColor(mission, s.id)} size={8} />
                      {s.name}
                    </span>
                    {RISK_CATEGORIES.map((c) => {
                      const worst = mine.filter((r) => r.category === c.id).sort((a, b) => riskOrder(b) - riskOrder(a))[0];
                      return worst ? (
                        <span
                          role="cell"
                          key={c.id}
                          className={`exposure__cell exposure__cell--${riskBand(worst)}${hover === worst.id ? ' is-hover' : ''}`}
                          onPointerEnter={() => setHover(worst.id)}
                          onPointerLeave={() => setHover(null)}
                        >
                          <span className="t-control" style={{ color: BAND[riskBand(worst)].color }}>{BAND[riskBand(worst)].glyph}</span> <span className="t-small t-muted">{worst.id}</span>
                        </span>
                      ) : (
                        <span role="cell" key={c.id} className="exposure__cell t-small t-muted">–</span>
                      );
                    })}
                    <span role="cell" className="t-body">
                      <span style={{ color: BAND.high.color }} className="t-small">▲</span> {mine.filter((r) => riskBand(r) === 'high').length}
                    </span>
                  </div>
                );
              })}
            </div>
            <p className="t-small t-muted exposure__note">
              {sharedHigh.length > 0 && `${sharedHigh.map((r) => `${r.name} (${r.id})`).join(', ')} ${sharedHigh.length === 1 ? 'is the one high risk' : 'are the high risks'} shared by every site. `}
            </p>
          </section>
        </div>

        <section data-pending={RISK_REGISTER.id}>
          <SectionHeader title="Risk register & mitigations" sub="Every identified risk, where it applies, and what reduces it. Likelihood and severity are low / medium / high." pending={[RISK_REGISTER]} />
          <div className="register" role="table">
            <div className="register__head grid-table__head" role="row">
              {['ID', 'RISK', 'LIKELIHOOD', 'SEVERITY', 'BAND', 'SITES', 'MITIGATION'].map((h) => (
                <span key={h} role="columnheader">{h}</span>
              ))}
            </div>
            {RISK_CATEGORIES.map((c) => {
              const group = risks.filter((r) => r.category === c.id);
              if (!group.length) return null;
              return (
                <Fragment key={c.id}>
                  <div className="register__group t-small" role="row">
                    <span>{c.label}</span> <span className="t-muted">· {group.length} risks</span>
                  </div>
                  {group.map((r, i) => {
                    const b = riskBand(r);
                    return (
                      <motion.div
                        id={`risk-${r.id}`}
                        key={r.id}
                        role="row"
                        className={`register__row${hover === r.id ? ' is-hover' : ''}`}
                        onPointerEnter={() => setHover(r.id)}
                        onPointerLeave={() => setHover(null)}
                        initial={{ opacity: 0, y: 6 }}
                        whileInView={{ opacity: 1, y: 0 }}
                        viewport={{ once: true, margin: '-40px' }}
                        transition={{ duration: 0.3, delay: i * 0.03 }}
                      >
                        <span role="cell" className="t-body">{r.id}</span>
                        <span role="cell" className="stack">
                          <span className="t-body">{r.name}</span>
                          <span className="t-small t-muted">{r.detail}</span>
                        </span>
                        <span role="cell" className="t-body">{LIKELIHOOD_LABELS[r.likelihood]}</span>
                        <span role="cell" className="t-body">{SEVERITY_LABELS[r.severity]}</span>
                        <span role="cell" className="t-body nowrap">
                          <span className="t-small" style={{ color: BAND[b].color }}>{BAND[b].glyph}</span> {BAND[b].label}
                        </span>
                        <span role="cell">
                          <SiteRefs sites={r.sites === 'all' ? 'all' : r.sites.filter((id) => sites.some((s) => s.id === id))} />
                        </span>
                        <span role="cell" className="t-body">{r.mitigation}</span>
                      </motion.div>
                    );
                  })}
                </Fragment>
              );
            })}
          </div>
        </section>
      </div>
      <Footer onBack={() => go('logistics')} status={`${risks.length} risks · ${high.length} high`}>
        <span data-pending-id={NEXT_STEP.id} title={`PENDING ${NEXT_STEP.id}\n${NEXT_STEP.awaits}`}>
          <Button disabled>Continue →</Button>
        </span>
      </Footer>
    </>
  );
}
