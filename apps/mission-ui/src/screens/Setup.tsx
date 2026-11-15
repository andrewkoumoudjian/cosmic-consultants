import { AnimatePresence, motion } from 'motion/react';
import { lazy, Suspense, useEffect, useRef, useState } from 'react';
import { CATEGORIES, categoryByKey, CONDITIONS, MAX_METRICS, METRICS, PRIORITIES, WORLDS, type World } from '../data/catalog.ts';
import { Button, Modal, PendingTag, Radio, SelectField } from '../components/ui.tsx';
import { Footer, StepHeader } from '../components/shell.tsx';
import { useMission, type Requirement, type Route } from '../state.tsx';

// three.js is only needed on step 1, so it loads in its own chunk.
const Planet = lazy(() => import('../three/Planet.tsx').then((m) => ({ default: m.Planet })));

type Nav = { go: (r: Route) => void };

/* ===================== 01 Location ===================== */

export function LocationStep({ go }: Nav) {
  const { mission, dispatch } = useMission();
  const [hover, setHover] = useState<World | null>(null);
  return (
    <>
      <StepHeader title="Begin with a world." sub="Choose the environment your mission is designed for." route="location" onStep={go} canVisit={(r) => r === 'category'} />
      <div className="step-content step-content--location">
        <div className="destinations" role="radiogroup" aria-label="Destination">
          {(Object.keys(WORLDS) as World[]).map((w) => {
            const selected = mission.world === w;
            return (
              <button
                key={w}
                type="button"
                role="radio"
                aria-checked={selected}
                className={`destination${selected ? ' is-selected' : ''}`}
                onClick={() => dispatch({ type: 'world', world: w })}
                onPointerEnter={() => setHover(w)}
                onPointerLeave={() => setHover(null)}
                onFocus={() => setHover(w)}
                onBlur={() => setHover(null)}
              >
                <motion.span className="destination__art" animate={{ opacity: selected ? 1 : 0.72, scale: selected ? 1 : 0.97 }} transition={{ duration: 0.4, ease: [0.22, 1, 0.36, 1] }}>
                  <Suspense fallback={<span className="planet" />}>
                    <Planet world={w} hovered={hover === w} label={`${WORLDS[w].label}, illustrated`} />
                  </Suspense>
                </motion.span>
                <span className="choice">
                  <Radio checked={selected} />
                  <span className="choice__copy">
                    <span className="t-section">{WORLDS[w].label}</span>
                    <span className="t-body">{WORLDS[w].blurb}</span>
                  </span>
                </span>
                <span className="choice__rule">{selected && <motion.span layoutId="destination-rule" className="choice__rule-on" />}</span>
              </button>
            );
          })}
        </div>
        <p className="t-small">You can change your selection before creating the mission.</p>
      </div>
      <Footer status="Step 1 of 3">
        <Button onClick={() => go('category')}>Continue →</Button>
      </Footer>
    </>
  );
}

/* ===================== 02 Mission category ===================== */

export function CategoryStep({ go }: Nav) {
  const { mission, dispatch } = useMission();
  return (
    <>
      <StepHeader title="What will you test?" sub="Choose one mission category. Metrics will follow your selection." route="category" onStep={go} canVisit={(r) => r === 'metrics' && !!mission.category} />
      <div className="step-content">
        <div className="context-row">
          <p className="t-body">{WORLDS[mission.world].label} / Single selection</p>
          <p className="t-body">{mission.category ? 1 : 0} selected</p>
        </div>
        <div className="categories" role="radiogroup" aria-label="Mission category">
          {CATEGORIES.map((c) => {
            const selected = mission.category === c.key;
            return (
              <button key={c.key} type="button" role="radio" aria-checked={selected} className={`category${selected ? ' is-selected' : ''}`} onClick={() => dispatch({ type: 'category', key: c.key })}>
                {selected && <motion.span layoutId="category-bg" className="category__bg" transition={{ type: 'spring', stiffness: 420, damping: 38 }} />}
                <span className="category__content">
                  <Radio checked={selected} />
                  <span className="category__copy">
                    <span className="t-small t-muted">{c.ordinal}</span>
                    <span className="t-category">{c.name}</span>
                    <span className="t-body">{c.description}</span>
                    {c.menu.length === 0 && <span className="t-small t-muted">No supported metrics currently available</span>}
                  </span>
                </span>
                <span className="category__rule">{selected && <motion.span layoutId="category-rule" className="category__rule-on" transition={{ type: 'spring', stiffness: 420, damping: 38 }} />}</span>
              </button>
            );
          })}
        </div>
      </div>
      <Footer onBack={() => go('location')} status="Step 2 of 3">
        <Button disabled={!mission.category} onClick={() => go('metrics')}>Continue →</Button>
      </Footer>
    </>
  );
}

/* ===================== 03 Metrics ===================== */

function isNumber(s: string) {
  return s.trim() !== '' && Number.isFinite(Number(s.replace(',', '.')));
}

export function targetIsSet(r: Requirement) {
  return r.condition === 'matches' ? r.target.trim() !== '' : isNumber(r.target);
}

export function MetricsStep({ go }: Nav) {
  const { mission, dispatch } = useMission();
  const cat = categoryByKey(mission.category);
  const [picker, setPicker] = useState(false);
  const [menuFor, setMenuFor] = useState<string | null>(null);

  useEffect(() => {
    if (!cat) go('category');
  }, [cat, go]);
  if (!cat) return null;

  const reqs = mission.requirements;
  const ready = reqs.length > 0 && reqs.every(targetIsSet);

  return (
    <>
      <StepHeader title="Define your metrics." sub={`Choose up to ${MAX_METRICS} metrics for your selected category.`} route="metrics" onStep={go} />
      <div className="step-content">
        <div className="mission-context">
          <h2 className="t-section">
            {WORLDS[mission.world].label} / {cat.name}
          </h2>
          <span className="mission-context__right">
            {cat.pending && <PendingTag p={cat.pending} />}
            <a className="link t-body" href="#/category">Change</a>
          </span>
        </div>
        <div className="testing-includes">
          <p className="t-control">Testing includes</p>
          <p className="t-small">{cat.description}</p>
        </div>
        <div className="requirements-heading">
          <h2 className="t-section">Mission requirements</h2>
          <p className="t-body">
            {reqs.length} / {MAX_METRICS} selected
          </p>
        </div>

        <div className="req-table" role="table" aria-label="Mission requirements">
          <div className="req-table__head t-small" role="row">
            <span role="columnheader">METRIC</span>
            <span role="columnheader">CONDITION</span>
            <span role="columnheader">TARGET VALUE</span>
            <span role="columnheader">PRIORITY</span>
            <span role="columnheader">ACTION</span>
          </div>
          {cat.menu.length === 0 && <p className="req-table__empty t-small t-muted">No supported metrics currently available for this category.</p>}
          <AnimatePresence initial={false}>
            {reqs.map((r) => {
              const metric = METRICS[r.metric];
              return (
                <motion.div
                  key={r.metric}
                  className="req-row"
                  role="row"
                  layout
                  initial={{ opacity: 0, height: 0 }}
                  animate={{ opacity: 1, height: 65 }}
                  exit={{ opacity: 0, height: 0 }}
                  transition={{ duration: 0.22, ease: [0.22, 1, 0.36, 1] }}
                >
                  <div className="req-row__metric" role="cell">
                    <span className="t-body">{metric.label}</span>
                    {metric.column ? (
                      <span className="t-small t-muted req-row__col" title="Active column in data/pipeline/columns.yaml">
                        {metric.column}
                      </span>
                    ) : (
                      metric.pending && <PendingTag p={metric.pending} label="no column" />
                    )}
                  </div>
                  <div role="cell" className="req-row__cell">
                    <SelectField
                      ariaLabel={`Condition for ${metric.label}`}
                      title="Condition"
                      value={r.condition}
                      options={CONDITIONS}
                      onChange={(condition) => dispatch({ type: 'requirement', metric: r.metric, patch: { condition } })}
                    />
                  </div>
                  <div role="cell" className="req-row__target">
                    <input
                      className="field field--input"
                      inputMode={r.condition === 'matches' ? 'text' : 'decimal'}
                      placeholder={r.condition === 'matches' ? 'Set class' : 'Set value'}
                      aria-label={`Target value for ${metric.label}`}
                      value={r.target}
                      aria-invalid={r.target !== '' && !targetIsSet(r)}
                      onChange={(e) => dispatch({ type: 'requirement', metric: r.metric, patch: { target: e.target.value } })}
                    />
                    <span className="t-body">{r.condition === 'matches' ? '' : metric.unit}</span>
                  </div>
                  <div role="cell" className="req-row__cell">
                    <SelectField
                      ariaLabel={`Priority for ${metric.label}`}
                      title="Priority"
                      value={r.priority}
                      options={PRIORITIES}
                      onChange={(priority) => dispatch({ type: 'requirement', metric: r.metric, patch: { priority } })}
                    />
                  </div>
                  <div role="cell" className="req-row__action">
                    <RowMenu open={menuFor === r.metric} onOpen={(o) => setMenuFor(o ? r.metric : null)} onRemove={() => dispatch({ type: 'drop', metric: r.metric })} label={metric.label} />
                  </div>
                </motion.div>
              );
            })}
          </AnimatePresence>
        </div>
        {cat.menu.length > 0 && (
          <Button variant="secondary" wide onClick={() => setPicker(true)}>
            + Choose metrics
          </Button>
        )}
        <p className="t-small t-muted hint">{ready ? 'All targets set.' : reqs.length ? 'Set target values to continue.' : 'Choose at least one metric to continue.'}</p>
      </div>
      <Footer onBack={() => go('category')} status="Step 3 of 3">
        <Button disabled={!ready} onClick={() => go('sites')}>Create mission</Button>
      </Footer>
      <MetricPicker open={picker} onClose={() => setPicker(false)} />
    </>
  );
}

function RowMenu({ open, onOpen, onRemove, label }: { open: boolean; onOpen: (o: boolean) => void; onRemove: () => void; label: string }) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!open) return;
    const close = (e: MouseEvent | KeyboardEvent) => {
      if (e instanceof KeyboardEvent ? e.key === 'Escape' : !ref.current?.contains(e.target as Node)) onOpen(false);
    };
    document.addEventListener('mousedown', close);
    document.addEventListener('keydown', close);
    return () => {
      document.removeEventListener('mousedown', close);
      document.removeEventListener('keydown', close);
    };
  }, [open, onOpen]);
  return (
    <div className="row-menu" ref={ref}>
      <button type="button" className="row-menu__trigger t-control" aria-label={`Actions for ${label}`} aria-expanded={open} onClick={() => onOpen(!open)}>
        ⋯
      </button>
      <AnimatePresence>
        {open && (
          <motion.div className="menu menu--right" initial={{ opacity: 0, y: -4 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -4 }} transition={{ duration: 0.14 }}>
            <p className="t-small t-muted">Action</p>
            <button type="button" className="menu__item" onClick={onRemove}>
              Remove metric
            </button>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

function MetricPicker({ open, onClose }: { open: boolean; onClose: () => void }) {
  const { mission, dispatch } = useMission();
  const cat = categoryByKey(mission.category);
  const [chosen, setChosen] = useState<string[]>([]);
  useEffect(() => {
    if (open) setChosen(mission.requirements.map((r) => r.metric));
  }, [open, mission.requirements]);
  if (!cat) return null;
  const full = chosen.length >= MAX_METRICS;
  const done = () => {
    dispatch({ type: 'metrics', ids: cat.menu.filter((id) => chosen.includes(id)) });
    onClose();
  };
  return (
    <Modal open={open} onClose={onClose} label="Choose metrics" width={820}>
      <div className="picker">
        <div className="picker__head">
          <h2 className="t-section">Choose metrics</h2>
          <Button onClick={done}>Done</Button>
        </div>
        <p className="t-body">{cat.name}</p>
        <p className="t-small t-accent">
          {chosen.length} / {MAX_METRICS} selected
        </p>
        <div className="divider" />
        <div className="picker__list">
          {cat.menu.map((id) => {
            const on = chosen.includes(id);
            const metric = METRICS[id];
            return (
              <button
                key={id}
                type="button"
                role="checkbox"
                aria-checked={on}
                className="picker__row"
                disabled={!on && full}
                onClick={() => setChosen((c) => (on ? c.filter((x) => x !== id) : [...c, id]))}
              >
                <span className="checkbox" aria-hidden>
                  <AnimatePresence>
                    {on && (
                      <motion.span initial={{ scale: 0.3, opacity: 0 }} animate={{ scale: 1, opacity: 1 }} exit={{ scale: 0.3, opacity: 0 }} transition={{ duration: 0.14 }}>
                        ✓
                      </motion.span>
                    )}
                  </AnimatePresence>
                </span>
                <span className="t-small picker__label">{metric.label}</span>
                {!metric.column && <span className="t-small picker__nocol" title={metric.pending?.awaits}>no pipeline column yet</span>}
              </button>
            );
          })}
        </div>
        <p className="t-small t-muted">Up to {MAX_METRICS} metrics. Source and resolution qualifiers remain part of each metric.</p>
      </div>
    </Modal>
  );
}
