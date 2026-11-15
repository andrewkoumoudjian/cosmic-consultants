/** Shared pieces: Base UI wrappers, verdict marks, and the Figma shell (sidebar, header, progress, footer). */
import type { ReactNode } from 'react';
import { Select as BaseSelect } from '@base-ui/react/select';
import type { Row } from '../../atlas/src/planner/engine.ts';
import { GLYPH } from './model.ts';

export function Mark({ verdict }: { verdict: Row['verdict'] }) {
  return <span className={`mark ${verdict}`} aria-hidden="true" />;
}

export function Verdict({ verdict, children }: { verdict: Row['verdict']; children?: ReactNode }) {
  const word = verdict === 'match' ? 'Match' : verdict === 'miss' ? 'Miss' : 'Unknown';
  return (
    <span className={`v v-${verdict}`}>
      <Mark verdict={verdict} />
      <span aria-label={word}>{GLYPH[verdict]}</span>
      {children}
    </span>
  );
}

/** The Figma radio, as a mask so it takes the current ink colour. */
export function RadioDot({ checked }: { checked: boolean }) {
  return <span className="radio" data-checked={checked ? '' : undefined} aria-hidden="true" />;
}

export type Option<T extends string> = { value: T; label: string };

export function Select<T extends string>({ value, options, onChange, label, width }: {
  value: T; options: Option<T>[]; onChange: (v: T) => void; label: string; width?: number;
}) {
  return (
    <BaseSelect.Root items={options} value={value} onValueChange={v => { if (v !== null) onChange(v as T); }}>
      <BaseSelect.Trigger className="select-trigger" aria-label={label} style={width ? { minWidth: width } : undefined}>
        <BaseSelect.Value />
        <BaseSelect.Icon aria-hidden="true">⌄</BaseSelect.Icon>
      </BaseSelect.Trigger>
      <BaseSelect.Portal>
        <BaseSelect.Positioner sideOffset={4} alignItemWithTrigger={false}>
          <BaseSelect.Popup className="select-popup">
            <BaseSelect.List>
              {options.map(o => (
                <BaseSelect.Item key={o.value} value={o.value} className="select-item">
                  <BaseSelect.ItemIndicator>✓</BaseSelect.ItemIndicator>
                  <BaseSelect.ItemText>{o.label}</BaseSelect.ItemText>
                </BaseSelect.Item>
              ))}
            </BaseSelect.List>
          </BaseSelect.Popup>
        </BaseSelect.Positioner>
      </BaseSelect.Portal>
    </BaseSelect.Root>
  );
}

export const STEPS = [
  { n: 1, label: 'Location' },
  { n: 2, label: 'Mission category' },
  { n: 3, label: 'Metrics' },
  { n: 4, label: 'Site finder' },
  { n: 5, label: 'Limitation report' },
  { n: 6, label: 'Logistics' },
  { n: 7, label: 'Risks & brief' },
] as const;

export function Sidebar({ step, reached, onStep, manifestHash }: {
  step: number; reached: number; onStep: (n: number) => void; manifestHash: string;
}) {
  return (
    <aside className="sidebar">
      <div className="brand">cosmic /<br />consultants</div>
      <nav className="nav" aria-label="Plan steps">
        {STEPS.map(s => (
          <button key={s.n} onClick={() => onStep(s.n)} disabled={s.n > reached} aria-current={s.n === step ? 'step' : undefined}>
            <span>{String(s.n).padStart(2, '0')}</span><span>{s.label}</span>
          </button>
        ))}
      </nav>
      <div className="colophon t-small faint">
        Release sha256<br /><span title={manifestHash}>{manifestHash.slice(0, 16)}…</span>
      </div>
    </aside>
  );
}

export function Header({ crumbs, action }: { crumbs: string[]; action?: ReactNode }) {
  return (
    <div className="header">
      <div className="crumbs">
        {crumbs.map((c, i) => <span key={i}>{i > 0 && ' / '}{i === crumbs.length - 1 ? <b>{c}</b> : c}</span>)}
      </div>
      {action}
    </div>
  );
}

/** Step title + progress. Steps 1–3 use the Figma three-column progress; 4–7 a four-column one. */
export function StepHeader({ title, lede, step, reached, onStep }: {
  title: string; lede: ReactNode; step: number; reached: number; onStep: (n: number) => void;
}) {
  const group = step <= 3 ? STEPS.slice(0, 3) : STEPS.slice(3);
  return (
    <div className="step-header">
      <h1 className="t-title">{title}</h1>
      <p className="muted">{lede}</p>
      <div className={`progress${group.length > 3 ? ' long' : ''}`}>
        {group.map(s => (
          <button key={s.n} onClick={() => onStep(s.n)} disabled={s.n > reached}
            aria-current={s.n === step ? 'step' : undefined} className={s.n < step ? 'done' : undefined}>
            {s.n < step ? '✓ ' : ''}{String(s.n).padStart(2, '0')} {s.label}
          </button>
        ))}
      </div>
    </div>
  );
}

export function Footer({ step, onBack, next, nextLabel, nextDisabled, note }: {
  step: number; onBack?: () => void; next?: () => void; nextLabel: string; nextDisabled?: boolean; note?: ReactNode;
}) {
  return (
    <div className="footer">
      {onBack ? <button className="btn btn-ghost" onClick={onBack}>← Back</button> : <span />}
      <span className="spacer" />
      <span className="muted">{note ?? `Step ${step} of 7`}</span>
      {next && <button className="btn btn-primary" onClick={next} disabled={nextDisabled}>{nextLabel}</button>}
    </div>
  );
}

export function Plate({ fig, title, aside, children, className }: {
  fig: string; title?: ReactNode; aside?: ReactNode; children: ReactNode; className?: string;
}) {
  return (
    <section className={`plate${className ? ' ' + className : ''}`}>
      <div className="plate-head">
        <div><div className="fig">{fig}</div>{title && <h2 className="t-section" style={{ marginTop: 4 }}>{title}</h2>}</div>
        {aside}
      </div>
      {children}
    </section>
  );
}
