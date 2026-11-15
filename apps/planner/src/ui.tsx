/** Shared pieces: one top bar, a page frame, a footer, verdict marks and a Base UI select. */
import type { ReactNode } from 'react';
import { Select as BaseSelect } from '@base-ui/react/select';
import type { Row } from '../../atlas/src/planner/engine.ts';

export function Mark({ verdict }: { verdict: Row['verdict'] }) {
  return <span className={`mark ${verdict}`} aria-hidden="true" />;
}

export function Verdict({ verdict, children }: { verdict: Row['verdict']; children?: ReactNode }) {
  const word = verdict === 'match' ? 'Match' : verdict === 'miss' ? 'Miss' : 'Unknown';
  return (
    <span className={`v v-${verdict}`}>
      <Mark verdict={verdict} /><span className="sr">{word}</span>{children}
    </span>
  );
}

export function RadioDot({ checked }: { checked: boolean }) {
  return <span className="radio" data-checked={checked ? '' : undefined} aria-hidden="true" />;
}

export type Option<T extends string> = { value: T; label: string };

export function Select<T extends string>({ value, options, onChange, label, width }: {
  value: T; options: Option<T>[]; onChange: (v: T) => void; label: string; width?: number;
}) {
  return (
    <BaseSelect.Root items={options} value={value} onValueChange={v => { if (v !== null) onChange(v as T); }}>
      <BaseSelect.Trigger className="select" aria-label={label} style={width ? { minWidth: width } : undefined}>
        <BaseSelect.Value />
        <BaseSelect.Icon aria-hidden="true">⌄</BaseSelect.Icon>
      </BaseSelect.Trigger>
      <BaseSelect.Portal>
        <BaseSelect.Positioner sideOffset={4} alignItemWithTrigger={false}>
          <BaseSelect.Popup className="popup">
            <BaseSelect.List>
              {options.map(o => (
                <BaseSelect.Item key={o.value} value={o.value} className="item">
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

export const STEPS = ['Destination', 'Category', 'Requirements', 'Sites', 'Limitations', 'Logistics', 'Risks'] as const;

export function TopBar({ step, reached, onStep, action }: { step: number; reached: number; onStep: (n: number) => void; action?: ReactNode }) {
  return (
    <header className="bar">
      <span className="brand">cosmic / consultants</span>
      <nav className="steps" aria-label="Steps">
        {STEPS.map((s, k) => (
          <button key={s} onClick={() => onStep(k + 1)} disabled={k + 1 > reached} aria-current={k + 1 === step ? 'step' : undefined}>
            <span className="n">{k + 1}</span>{s}
          </button>
        ))}
      </nav>
      {action}
    </header>
  );
}

export function Page({ title, aside, children, back, next, nextLabel = 'Continue', nextDisabled }: {
  title: ReactNode; aside?: ReactNode; children: ReactNode;
  back?: () => void; next?: () => void; nextLabel?: string; nextDisabled?: boolean;
}) {
  return (
    <div className="page">
      <div className="page-head"><h1 className="title">{title}</h1>{aside}</div>
      <div className="content">{children}</div>
      <div className="footer">
        {back ? <button className="btn btn-ghost" onClick={back}>← Back</button> : <span />}
        {next && <button className="btn btn-primary" onClick={next} disabled={nextDisabled}>{nextLabel} →</button>}
      </div>
    </div>
  );
}
