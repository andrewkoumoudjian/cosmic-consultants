import { Fragment } from 'react';
import { CONDITIONS, METRICS } from '../data/catalog.ts';
import { SITE_SHORTLIST } from '../data/placeholders/sites.ts';
import { Swatch } from '../components/ui.tsx';
import { chartIds, isRequired, seriesColor, useMission, type Requirement } from '../state.tsx';

/** Replaces {metric-id} with the metric label, bold when the requirement is High/Critical. */
export function MetricText({ text }: { text: string }) {
  const { mission } = useMission();
  const parts = text.split(/(\{[a-z0-9-]+\})/g);
  return (
    <>
      {parts.map((part, i) => {
        const m = /^\{([a-z0-9-]+)\}$/.exec(part);
        if (!m) return <Fragment key={i}>{part}</Fragment>;
        const metric = METRICS[m[1]];
        const label = metric ? metric.label.replace(' (proxy)', '') : m[1];
        const req = mission.requirements.find((r) => r.metric === m[1]);
        return isRequired(req) ? (
          <b key={i} className="t-strong">
            {label}
          </b>
        ) : (
          <Fragment key={i}>{label}</Fragment>
        );
      })}
    </>
  );
}

/** Coloured swatches + names for a set of sites. */
export function SiteRefs({ sites, upper }: { sites: string[] | 'all'; upper?: boolean }) {
  const { mission } = useMission();
  if (sites === 'all') {
    return (
      <span className="site-refs t-small">
        <span className="site-refs__swatches">
          {chartIds(mission).map((id) => (
            <Swatch key={id} color={seriesColor(mission, id)} size={8} />
          ))}
        </span>
        <span>All sites</span>
      </span>
    );
  }
  return (
    <span className="site-refs t-small">
      {sites.map((id) => {
        const s = SITE_SHORTLIST.sample.find((x) => x.id === id);
        return (
          <span key={id} className="site-ref">
            <Swatch color={seriesColor(mission, id)} size={8} />
            {upper ? s?.name.toUpperCase() : s?.name}
          </span>
        );
      })}
    </span>
  );
}

export function formatTarget(r: Requirement): string {
  if (!r.target.trim()) return '–';
  const cond = CONDITIONS.find((c) => c.id === r.condition)?.label ?? '';
  if (r.condition === 'matches') return `${cond} ${r.target}`;
  const unit = METRICS[r.metric]?.unit ?? '';
  const tight = unit === '' || unit.startsWith('°') || unit === '%';
  return `${cond} ${r.target}${tight ? unit : ` ${unit}`}`;
}

export function usd(n: number): string {
  return `$${Math.round(n).toLocaleString('en-US')}`;
}

export function usdK(n: number, digits = 0): string {
  const k = n / 1000;
  return `$${digits ? (Math.round(k * 10) / 10).toString() : Math.round(k)}k`;
}
