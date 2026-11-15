/** Shared building blocks. Every interactive control is a Base UI part, styled in app.css. */
import type { ReactNode } from 'react';
import { Select as BaseSelect } from '@base-ui/react/select';
import { ToggleGroup } from '@base-ui/react/toggle-group';
import { Toggle } from '@base-ui/react/toggle';
import { Tabs } from '@base-ui/react/tabs';
import { Switch as BaseSwitch } from '@base-ui/react/switch';
import { NumberField } from '@base-ui/react/number-field';
import { Button } from '@base-ui/react/button';
export { Button };
import type { Row } from '../../atlas/src/planner/engine.ts';
import { SITE_LETTER, coordLabel } from './model.ts';
import type { Dataset } from '../../atlas/src/planner/engine.ts';

export type StepId = 'destination' | 'category' | 'requirements' | 'sites' | 'limitations' | 'logistics' | 'risks' | 'missions';

/** One short title per step. No eyebrows or subtitles: the title and the content say what the step is for. */
export const STEPS: { id: StepId; label: string; title: string }[] = [
  { id: 'destination', label: 'Destination', title: 'Analog Atlas' },
  { id: 'category', label: 'Objectives', title: 'Defining mission objectives' },
  { id: 'requirements', label: 'Requirements', title: 'Requirements' },
  { id: 'sites', label: 'Sites', title: 'Sites' },
  { id: 'limitations', label: 'Limitations', title: 'Limitations' },
  { id: 'logistics', label: 'Logistics', title: 'Logistics' },
  { id: 'risks', label: 'Risks', title: 'Risk assessment' },
  { id: 'missions', label: 'Lessons learned', title: 'Lessons learned' },
];

export function StepHead({ step, context, title }: { step: number; context?: ReactNode; title?: ReactNode }) {
  const s = STEPS[step - 1]!;
  return (
    <header className="step-head">
      <h1 className="t-page">{title ?? s.title}</h1>
      {context && <div className="context">{context}</div>}
    </header>
  );
}

export function Card({ title, aside, tone, className, children, id }: {
  title?: ReactNode; aside?: ReactNode; tone?: 'accent' | 'mars' | 'moon'; className?: string; children?: ReactNode; id?: string;
}) {
  return (
    <section className={`card${className ? ` ${className}` : ''}`} data-tone={tone} id={id}>
      {(title || aside) && (
        <div className="card-head">
          {title && <h2 className="card-title">{title}</h2>}
          {aside}
        </div>
      )}
      {children}
    </section>
  );
}

export const GLYPH: Record<Row['verdict'], string> = { match: '●', miss: '◆', unknown: '○' };
export const WORD: Record<Row['verdict'], string> = { match: 'Match', miss: 'Miss', unknown: 'Unknown' };

/** A verdict is always glyph + word + colour. `children` replaces the word (e.g. a trait name). */
export function Verdict({ v, children, detail }: { v: Row['verdict']; children?: ReactNode; detail?: ReactNode }) {
  return (
    <span className={`verdict ${v}`} title={WORD[v]}>
      <span className={`g g-${v}`} aria-hidden>{GLYPH[v]}</span>
      {children ?? WORD[v]}
      {children && <span className="sr-only"> ({WORD[v]})</span>}
      {detail && <span className="d">{detail}</span>}
    </span>
  );
}

export function VerdictLegend() {
  return (
    <div className="legend" aria-label="Legend">
      <span><span className="g-match" aria-hidden>●</span>Match</span>
      <span><span className="g-miss" aria-hidden>◆</span>Miss</span>
      <span><span className="g-unknown" aria-hidden>○</span>Unknown</span>
    </div>
  );
}

export function SiteBadge({ k }: { k: number }) {
  return <span className="site-badge" data-k={k} aria-label={`Site ${SITE_LETTER[k]}`}>{SITE_LETTER[k]}</span>;
}

export function SiteTag({ data, i, k }: { data: Dataset; i: number; k: number }) {
  return <span className="site-tag"><SiteBadge k={k} />{coordLabel(data, i)}</span>;
}

/** Single choice from a few options: Base UI ToggleGroup. Pressing the pressed one keeps it. */
export function Seg<T extends string>({ value, options, onChange, label }: { value: T; options: { value: T; label: ReactNode; disabled?: boolean }[]; onChange: (v: T) => void; label: string }) {
  return (
    <ToggleGroup className="seg" aria-label={label} value={[value]} onValueChange={v => { const next = v[0] as T | undefined; if (next !== undefined) onChange(next); }}>
      {options.map(o => <Toggle key={o.value} value={o.value} disabled={o.disabled} className="seg-item">{o.label}</Toggle>)}
    </ToggleGroup>
  );
}

/** On/off with its label: Base UI Switch. */
export function Switch({ on, onChange, children }: { on: boolean; onChange: (v: boolean) => void; children: ReactNode }) {
  return (
    <label className="switch-label">
      <BaseSwitch.Root className="switch" checked={on} onCheckedChange={c => onChange(c)}>
        <BaseSwitch.Thumb className="switch-thumb" />
      </BaseSwitch.Root>
      {children}
    </label>
  );
}

/** Base UI Select with the current value shown. */
export function Select<T extends string>({ value, options, onChange, label }: { value: T; options: { value: T; label: string }[]; onChange: (v: T) => void; label: string }) {
  return (
    <BaseSelect.Root items={options} value={value} onValueChange={v => { if (v !== null) onChange(v as T); }}>
      <BaseSelect.Trigger className="select" aria-label={label}>
        <BaseSelect.Value className="select-value" />
        <BaseSelect.Icon className="select-icon"><Chevron /></BaseSelect.Icon>
      </BaseSelect.Trigger>
      <BaseSelect.Portal>
        <BaseSelect.Positioner className="select-positioner" sideOffset={6} alignItemWithTrigger={false}>
          <BaseSelect.Popup className="select-popup">
            <BaseSelect.List className="select-list">
              {options.map(o => (
                <BaseSelect.Item key={o.value} value={o.value} className="select-item">
                  <BaseSelect.ItemIndicator className="select-check"><Check /></BaseSelect.ItemIndicator>
                  <BaseSelect.ItemText className="select-text">{o.label}</BaseSelect.ItemText>
                </BaseSelect.Item>
              ))}
            </BaseSelect.List>
          </BaseSelect.Popup>
        </BaseSelect.Positioner>
      </BaseSelect.Portal>
    </BaseSelect.Root>
  );
}

/** A number box: Base UI NumberField. Empty means "not set". */
export function NumInput({ value, onChange, label, min, max, placeholder, width }: {
  value: number | undefined; onChange: (v: number | undefined) => void; label: string; min?: number; max?: number; placeholder?: string; width?: number;
}) {
  return (
    <NumberField.Root className="num-field" value={value ?? null} min={min} max={max} onValueChange={v => onChange(v ?? undefined)}>
      <NumberField.Group className="num-group" style={width ? { width } : undefined}>
        <NumberField.Decrement className="num-step" aria-label={`Lower ${label}`}>−</NumberField.Decrement>
        <NumberField.Input className="num-input" aria-label={label} placeholder={placeholder} />
        <NumberField.Increment className="num-step" aria-label={`Raise ${label}`}>+</NumberField.Increment>
      </NumberField.Group>
    </NumberField.Root>
  );
}

const Chevron = () => <svg width="10" height="10" viewBox="0 0 10 10" aria-hidden><path d="M2 3.5 5 6.5 8 3.5" fill="none" stroke="currentColor" strokeWidth="1.5" /></svg>;
const Check = () => <svg width="10" height="10" viewBox="0 0 10 10" aria-hidden><path d="M1.5 5.2 4 7.5 8.5 2.5" fill="none" stroke="currentColor" strokeWidth="1.6" /></svg>;

/** Switch between the compared sites: Base UI Tabs with its sliding indicator. */
export function SiteTabs({ data, sites, value, onChange }: { data: Dataset; sites: number[]; value: number; onChange: (k: number) => void }) {
  return (
    <Tabs.Root value={value} onValueChange={v => onChange(Number(v))}>
      <Tabs.List className="tabs" aria-label="Compared sites">
        {sites.map((i, k) => <Tabs.Tab key={i} value={k} className="tab"><SiteBadge k={k} />{coordLabel(data, i)}</Tabs.Tab>)}
        <Tabs.Indicator className="tab-indicator" />
      </Tabs.List>
    </Tabs.Root>
  );
}

/** A measured value, or an explicit "no data" (rule 3: missing stays missing). */
export function Val({ text }: { text: string | null | undefined }) {
  return text ? <>{text}</> : <span className="muted" style={{ fontStyle: 'italic', fontFamily: 'var(--font-sans)' }}>no data</span>;
}

export function NavFoot({ onBack, onNext, nextLabel = 'Continue', nextDisabled, hint }: { onBack?: () => void; onNext?: () => void; nextLabel?: string; nextDisabled?: boolean; hint?: ReactNode }) {
  return (
    <div className="nav-foot">
      <Button className="btn ghost" onClick={onBack} disabled={!onBack}>← Back</Button>
      <span className="row">
        {hint && <span className="t-small muted">{hint}</span>}
        {onNext && <Button className="btn primary" onClick={onNext} disabled={nextDisabled}>{nextLabel} →</Button>}
      </span>
    </div>
  );
}

export function NeedSites({ onSites }: { onSites: () => void }) {
  return (
    <Card title="No sites picked yet">
      <p className="text-2">Pick up to three sites in step 4.</p>
      <div><Button className="btn primary" onClick={onSites}>Pick sites →</Button></div>
    </Card>
  );
}
