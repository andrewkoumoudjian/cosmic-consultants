import { AnimatePresence, motion } from 'motion/react';
import { useEffect, useId, useRef, useState, type ReactNode } from 'react';
import radioEmpty from '../assets/radio-empty.svg';
import radioSelected from '../assets/radio-selected.svg';
import { describe, type Placeholder } from '../data/pending.ts';

/* ---------- Mission / Button (Figma 32:40) ---------- */

type ButtonVariant = 'primary' | 'secondary' | 'ghost';

export function Button({
  variant = 'primary', disabled, onClick, children, wide, title, type = 'button',
}: {
  variant?: ButtonVariant; disabled?: boolean; onClick?: () => void; children: ReactNode; wide?: boolean; title?: string; type?: 'button' | 'submit';
}) {
  return (
    <button
      type={type}
      className={`btn btn--${variant}${wide ? ' btn--wide' : ''}`}
      disabled={disabled}
      onClick={onClick}
      title={title}
    >
      {children}
    </button>
  );
}

/* ---------- Mission / Radio (Figma 32:49) ---------- */

export function Radio({ checked }: { checked: boolean }) {
  return (
    <span className="radio" aria-hidden>
      <img src={radioEmpty} width={24} height={24} alt="" />
      <AnimatePresence>
        {checked && (
          <motion.img
            key="on"
            src={radioSelected}
            width={24}
            height={24}
            alt=""
            initial={{ scale: 0.4, opacity: 0 }}
            animate={{ scale: 1, opacity: 1 }}
            exit={{ scale: 0.4, opacity: 0 }}
            transition={{ type: 'spring', stiffness: 500, damping: 30 }}
          />
        )}
      </AnimatePresence>
    </span>
  );
}

/* ---------- Placeholders ---------- */

/** Small chip naming the placeholder that feeds a section. */
export function PendingTag({ p, label, compact }: { p: Placeholder; label?: string; compact?: boolean }) {
  return (
    <span className={`pending-tag pending-tag--${p.kind}`} data-pending-id={p.id} title={describe(p)} tabIndex={0} aria-label={`${p.kind === 'pending' ? 'Placeholder' : 'Blocked'}: ${p.id}`}>
      {compact ? '◌' : (label ?? (p.kind === 'pending' ? 'placeholder' : 'blocked')) + ' ·'} {p.id}
    </span>
  );
}

/** Empty slot where the design shows a value the project rules don't allow. */
export function BlockedSlot({ p, width = 34 }: { p: Placeholder; width?: number }) {
  return (
    <span className="blocked-slot" style={{ width }} data-pending-id={p.id} title={describe(p)} aria-label={`Blocked: ${p.id}`}>
      —
    </span>
  );
}

/* ---------- Layout bits ---------- */

export function Tile({ label, value, note, icon, pending }: { label: ReactNode; value: ReactNode; note: ReactNode; icon?: ReactNode; pending?: Placeholder }) {
  return (
    <div className="tile" data-pending={pending?.id}>
      <p className="t-small t-muted tile__label">
        {icon}
        {label}
      </p>
      <p className="t-section">{value}</p>
      <p className="t-small t-muted">{note}</p>
    </div>
  );
}

export function SectionHeader({ title, sub, right, pending }: { title: string; sub: ReactNode; right?: ReactNode; pending?: Placeholder[] }) {
  return (
    <header className="section-header">
      <div>
        <h2 className="t-section">{title}</h2>
        <p className="t-small t-muted section-header__sub">
          <span>{sub}</span>
          {pending?.map((p) => <PendingTag key={p.id} p={p} />)}
        </p>
      </div>
      {right && <div className="section-header__right">{right}</div>}
    </header>
  );
}

export function Label({ children, right }: { children: ReactNode; right?: ReactNode }) {
  return (
    <div className="overline">
      <span>{children}</span>
      {right}
    </div>
  );
}

/* ---------- Select field + menu (Figma "Field / …", "Condition / menu", "Priority / menu") ---------- */

export function SelectField<T extends string>({
  value, options, title, onChange, width = 154, ariaLabel,
}: {
  value: T; options: { id: T; label: string }[]; title: string; onChange: (v: T) => void; width?: number; ariaLabel: string;
}) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  const listId = useId();

  useEffect(() => {
    if (!open) return;
    const close = (e: MouseEvent | KeyboardEvent) => {
      if (e instanceof KeyboardEvent ? e.key === 'Escape' : !ref.current?.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener('mousedown', close);
    document.addEventListener('keydown', close);
    return () => {
      document.removeEventListener('mousedown', close);
      document.removeEventListener('keydown', close);
    };
  }, [open]);

  const current = options.find((o) => o.id === value);
  return (
    <div className="select" ref={ref} style={{ width }}>
      <button
        type="button"
        className="field field--button"
        aria-haspopup="listbox"
        aria-expanded={open}
        aria-controls={listId}
        aria-label={`${ariaLabel}: ${current?.label}`}
        onClick={() => setOpen((o) => !o)}
      >
        <span>{current?.label}</span>
        <span className="t-small field__chev" aria-hidden>⌄</span>
      </button>
      <AnimatePresence>
        {open && (
          <motion.div
            className="menu"
            id={listId}
            role="listbox"
            aria-label={title}
            initial={{ opacity: 0, y: -4 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -4 }}
            transition={{ duration: 0.14 }}
          >
            <p className="t-small t-muted">{title}</p>
            {options.map((o) => (
              <button
                key={o.id}
                type="button"
                role="option"
                aria-selected={o.id === value}
                className={`menu__item${o.id === value ? ' is-current' : ''}`}
                onClick={() => {
                  onChange(o.id);
                  setOpen(false);
                }}
              >
                {o.label}
              </button>
            ))}
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

/* ---------- Modal ---------- */

export function Modal({ open, onClose, children, label, width }: { open: boolean; onClose: () => void; children: ReactNode; label: string; width: number }) {
  const panel = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!open) return;
    const prev = document.activeElement as HTMLElement | null;
    const t = setTimeout(() => panel.current?.querySelector<HTMLElement>('button, input')?.focus(), 30);
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && onClose();
    document.addEventListener('keydown', onKey);
    return () => {
      clearTimeout(t);
      document.removeEventListener('keydown', onKey);
      prev?.focus?.();
    };
  }, [open, onClose]);
  return (
    <AnimatePresence>
      {open && (
        <motion.div
          className="modal"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          transition={{ duration: 0.18 }}
          onMouseDown={(e) => e.target === e.currentTarget && onClose()}
        >
          <motion.div
            ref={panel}
            className="modal__panel"
            role="dialog"
            aria-modal="true"
            aria-label={label}
            style={{ width }}
            initial={{ opacity: 0, y: 12, scale: 0.985 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: 8, scale: 0.99 }}
            transition={{ type: 'spring', stiffness: 380, damping: 32 }}
          >
            {children}
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}

/* ---------- Site swatch ---------- */

export function Swatch({ color, size = 10 }: { color: string | null; size?: number }) {
  return color ? (
    <span className="swatch" style={{ width: size, height: size, background: color }} aria-hidden />
  ) : (
    <span className="swatch swatch--outline" style={{ width: size, height: size }} aria-hidden />
  );
}
