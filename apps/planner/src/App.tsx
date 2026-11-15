import { useEffect, useMemo, useState } from 'react';
import { AnimatePresence, motion, useReducedMotion } from 'motion/react';
import { loadDataset, ensureMonthly, monthlyColumnsForObjective, type LoadProgress } from '../../atlas/src/planner/data.ts';
import type { Dataset } from '../../atlas/src/planner/engine.ts';
import { decodePlan, encodePlan, validatePlan, type PlanRequest } from '../../atlas/src/plan-url.ts';
import { coordLabel, newRequest, runSearch, type Body } from './model.ts';
import { TopBar } from './ui.tsx';
import { Location, CategoryStep, Metrics } from './steps/Setup.tsx';
import { Finder } from './steps/Finder.tsx';
import { Limits, Logistics, Risks } from './steps/Reports.tsx';

type Load = { state: 'loading'; progress?: LoadProgress } | { state: 'error'; message: string } | { state: 'ready'; data: Dataset };

/** Reads the shared plan link once at start-up. The step lives in the hash, the plan in the query. */
function fromUrl(): { request: PlanRequest | null; step: number; problems: string[]; notes: string } {
  const hash = new URLSearchParams(location.hash.slice(1));
  const notes = hash.get('notes') ?? ''; // the field-notes checklist travels with the link
  const raw = Number(hash.get('step'));
  const step = Number.isInteger(raw) && raw >= 1 && raw <= 7 ? raw : 1;
  if (!location.search) return { request: null, step: 1, problems: [], notes };
  const decoded = decodePlan(location.search);
  if (!decoded.ok) return { request: null, step: 1, problems: decoded.errors, notes };
  return { request: decoded.plan, step, problems: [], notes };
}

export function App() {
  const [load, setLoad] = useState<Load>({ state: 'loading' });
  const initial = useMemo(fromUrl, []);
  const [body, setBody] = useState<Body>(initial.request?.body ?? 'moon');
  const [categoryId, setCategoryId] = useState<string | undefined>(initial.request?.category);
  const [request, setRequest] = useState<PlanRequest | null>(initial.request);
  const [step, setStep] = useState(initial.request ? initial.step : 1);
  const [reached, setReached] = useState(initial.request ? (initial.request.pins?.length ? 7 : 4) : 1);
  const [removed, setRemoved] = useState<string[]>([]);
  const [checklist, setChecklist] = useState(initial.notes);
  const [dropped, setDropped] = useState<string[]>([]);
  const [monthlyFor, setMonthlyFor] = useState<string | null>(null);
  const [blocked, setBlocked] = useState(false);
  const reduce = useReducedMotion();

  useEffect(() => {
    loadDataset('./data/planner-v1/', {
      initialObjectiveId: initial.request?.objectiveId,
      onProgress: progress => setLoad({ state: 'loading', progress }),
    }).then(data => setLoad({ state: 'ready', data }), (e: Error) => setLoad({ state: 'error', message: e.message }));
  }, [initial]);

  const data = load.state === 'ready' ? load.data : null;

  // Monthly columns load on demand for the chosen objective, with the same hash checks.
  useEffect(() => {
    if (!data || !request) return;
    let live = true;
    const id = request.objectiveId;
    ensureMonthly(data, monthlyColumnsForObjective(data, id)).then(() => { if (live) setMonthlyFor(id); },
      (e: Error) => setLoad({ state: 'error', message: e.message }));
    return () => { live = false; };
  }, [data, request?.objectiveId]);

  // Keep the URL a shareable plan link.
  useEffect(() => {
    if (!request || validatePlan(request).length) return;
    const hash = new URLSearchParams({ step: String(step) });
    if (checklist) hash.set('notes', checklist);
    history.replaceState(null, '', `?${encodePlan(request)}#${hash}`);
  }, [request, step, checklist]);

  const ready = !!data && !!request && monthlyFor === request.objectiveId;
  const result = useMemo(() => (ready ? runSearch(data!, request!) : null), [ready, data, request]);

  // Only sites still in play can be compared: no required miss or unknown, inside the limits, not removed.
  const eligible = (h: string) => {
    const i = data!.h3.indexOf(h);
    return i >= 0 && result!.classes[i] === 0 && !removed.includes(h);
  };
  useEffect(() => {
    if (!data || !request || !result) return;
    // Nothing is picked for the user: tied cells come in release order, so "the first three" would be arbitrary.
    // A compared cell that stops matching after an edit leaves the comparison, and the site list says which.
    const pins = request.pins ?? [];
    const kept = pins.filter(eligible);
    if (kept.length === pins.length) return;
    setDropped(pins.filter(h => !kept.includes(h)).map(h => { const i = data.h3.indexOf(h); return i >= 0 ? coordLabel(data, i) : h; }));
    setRequest({ ...request, pins: kept.length ? kept : undefined });
  }, [result, removed]);

  if (load.state === 'loading') {
    const p = load.progress;
    const pct = p ? Math.round((p.loadedFiles / Math.max(p.totalFiles, 1)) * 100) : 0;
    return (
      <main className="loading" aria-busy="true">
        <div className="track" role="progressbar" aria-label="Verifying data" aria-valuenow={pct} aria-valuemin={0} aria-valuemax={100}><i style={{ width: `${pct}%` }} /></div>
        <span className="muted small">Verifying data</span>
      </main>
    );
  }
  if (load.state === 'error') return <main className="loading"><p className="warn" style={{ maxWidth: 520 }}>{load.message}</p></main>;

  const d = load.data;
  const category = d.runtime.categories.find(c => c.categoryId === categoryId);
  const go = (n: number) => { if (blocked && n > 3) return; setStep(n); setReached(r => Math.max(r, n)); window.scrollTo({ top: 0 }); };
  const objective = request ? d.objectives.find(o => o.objectiveId === request.objectiveId) : undefined;
  const pinIdx = result ? (request?.pins ?? []).filter(eligible).map(h => d.h3.indexOf(h)) : [];

  const chooseCategory = (id: string) => {
    setCategoryId(id);
    setRequest(newRequest(d, body, d.runtime.categories.find(x => x.categoryId === id)!));
    setRemoved([]); setDropped([]);
    setReached(3);
  };
  const chooseBody = (b: Body) => {
    if (b === body) return;
    setBody(b); setCategoryId(undefined); setRequest(null); setRemoved([]); setDropped([]); setReached(1);
    history.replaceState(null, '', location.pathname); // the old plan must not come back on refresh
  };

  let screen;
  if (step === 1) screen = <Location body={body} onBody={chooseBody} onNext={() => go(2)} />;
  else if (step === 2) screen = <CategoryStep data={d} body={body} categoryId={categoryId} onCategory={chooseCategory} onBack={() => go(1)} onNext={() => go(3)} />;
  else if (!request || !category) screen = <MissingPlan onRestart={() => go(1)} />;
  else if (step === 3) screen = <Metrics data={d} category={category} request={request} onRequest={r => { setRequest(r); setReached(3); }} onBlocked={setBlocked} onBack={() => go(2)} onNext={() => go(4)} />;
  else if (!result) screen = <main className="loading"><span className="muted small">Loading monthly data</span></main>;
  else if (step === 4) screen = <Finder data={d} request={request} result={result} removed={removed} onRemoved={setRemoved} onPins={p => { setDropped([]); setRequest({ ...request, pins: p.length ? p : undefined }); }} eligible={eligible} dropped={dropped} onBack={() => go(3)} onNext={() => go(5)} />;
  else if (step === 5) screen = <Limits data={d} request={request} sites={pinIdx} objective={objective!} onBack={() => go(4)} onNext={() => go(6)} />;
  else if (step === 6) screen = <Logistics data={d} request={request} sites={pinIdx} checklist={checklist} onChecklist={setChecklist} onBack={() => go(5)} onNext={() => go(7)} />;
  else screen = <Risks data={d} request={request} sites={pinIdx} checklist={checklist} onBack={() => go(6)} />;

  return (
    <>
      <TopBar step={step} reached={blocked ? Math.min(reached, 3) : reached} onStep={go} action={request && <CopyLink />} />
      {initial.problems.length > 0 && step === 1 && <p className="warn" style={{ padding: '16px 40px 0' }}>This plan link couldn't be read: {initial.problems.join('; ')}.</p>}
      <AnimatePresence mode="wait" initial={false}>
        <motion.main key={step} initial={reduce ? false : { opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }}
          exit={reduce ? undefined : { opacity: 0 }} transition={{ duration: 0.2, ease: [0.22, 1, 0.36, 1] }}>
          {screen}
        </motion.main>
      </AnimatePresence>
    </>
  );
}

function CopyLink() {
  const [done, setDone] = useState(false);
  return (
    <button className="btn btn-line" onClick={() => navigator.clipboard?.writeText(location.href).then(() => { setDone(true); setTimeout(() => setDone(false), 1500); })}>
      {done ? 'Copied' : 'Copy link'}
    </button>
  );
}

function MissingPlan({ onRestart }: { onRestart: () => void }) {
  return (
    <div className="page"><button className="btn btn-primary" onClick={onRestart} style={{ alignSelf: 'flex-start' }}>Start a plan →</button></div>
  );
}
