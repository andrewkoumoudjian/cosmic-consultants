import { motion } from 'motion/react';
import { useEffect, useState, type ReactNode } from 'react';
import { allPlaceholders } from '../data/pending.ts';
import type { Route } from '../state.tsx';

/* ---------- Mission / Sidebar (Figma 32:50) ---------- */

export function Sidebar({ route, highlight, onHighlight }: { route: Route; highlight: boolean; onHighlight: (v: boolean) => void }) {
  const [onPage, setOnPage] = useState(0);
  useEffect(() => {
    const count = () => setOnPage(new Set([...document.querySelectorAll('[data-pending-id]')].map((n) => n.getAttribute('data-pending-id'))).size);
    count();
    const obs = new MutationObserver(count);
    obs.observe(document.querySelector('main') ?? document.body, { subtree: true, childList: true });
    return () => obs.disconnect();
  }, [route]);

  return (
    <aside className="sidebar">
      <p className="t-brand sidebar__brand">
        cosmic /{' '}
        <br />
        consultants
      </p>
      <nav className="sidebar__nav" aria-label="Workspace">
        <span className="sidebar__link" aria-disabled title="Not in the Figma file yet">Overview</span>
        <span className="sidebar__link" aria-disabled title="Not in the Figma file yet">Mission archive</span>
        <a className="sidebar__link is-active" href="#/location" aria-current="page">
          <span className="sidebar__dot" aria-hidden />
          Define mission
        </a>
      </nav>
      <div className="sidebar__pending">
        <p className="t-small t-muted">
          <span className="pending-dot" aria-hidden /> PLACEHOLDERS
        </p>
        <p className="t-small t-muted">
          {onPage} on this page
          <br />
          {allPlaceholders().length} in the app
        </p>
        <label className="toggle t-small">
          <input type="checkbox" checked={highlight} onChange={(e) => onHighlight(e.target.checked)} />
          <span>Highlight placeholders</span>
        </label>
      </div>
    </aside>
  );
}

export function Header({ crumbs, action }: { crumbs: string; action: ReactNode }) {
  return (
    <>
      <div className="header">
        <p className="t-body">{crumbs}</p>
        {action}
      </div>
      <div className="divider" />
    </>
  );
}

const STEPS: { route: Route; label: string }[] = [
  { route: 'location', label: '01 Location' },
  { route: 'category', label: '02 Mission category' },
  { route: 'metrics', label: '03 Metrics' },
];

export function StepHeader({ title, sub, route, onStep, canVisit, sample }: { title: string; sub: ReactNode; route?: Route; onStep?: (r: Route) => void; canVisit?: (r: Route) => boolean; sample?: boolean }) {
  const current = STEPS.findIndex((s) => s.route === route);
  return (
    <div className={`step-header${route ? '' : ' step-header--report'}`}>
      <h1 className="t-title">{title}</h1>
      <p className="t-body">{sub}</p>
      {sample && (
        <p className="sample-banner t-small" role="note">
          <b>Design preview, sample data.</b> The sites and numbers on this screen are sample values from the Figma file, not engine output. Real results wait on the planner engine (#20, #183). Turn on &ldquo;Highlight placeholders&rdquo; to see each one.
        </p>
      )}
      {route && (
        <ol className="progress" aria-label="Steps">
          {STEPS.map((s, i) => {
            const done = i < current;
            const active = i === current;
            const reachable = done || (canVisit?.(s.route) ?? false);
            return (
              <li key={s.route} className={`progress__step${active ? ' is-active' : ''}`}>
                <button
                  type="button"
                  className="progress__label"
                  disabled={active || !reachable}
                  aria-current={active ? 'step' : undefined}
                  onClick={() => onStep?.(s.route)}
                >
                  {done ? '✓ ' : ''}
                  {s.label}
                </button>
                <span className="progress__rule" />
                {active && <motion.span layoutId="progress-accent" className="progress__accent" transition={{ type: 'spring', stiffness: 300, damping: 32 }} />}
              </li>
            );
          })}
        </ol>
      )}
    </div>
  );
}

export function Footer({ onBack, status, children }: { onBack?: () => void; status: ReactNode; children: ReactNode }) {
  return (
    <>
      <div className="divider" />
      <footer className="footer">
        <button type="button" className="btn btn--ghost btn--back" onClick={onBack} disabled={!onBack}>
          ← Back
        </button>
        <span className="flex" />
        <p className="t-body">{status}</p>
        {children}
      </footer>
    </>
  );
}
