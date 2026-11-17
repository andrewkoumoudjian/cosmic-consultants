/**
 * Analog Atlas: eight steps over the shared planner engine and the planner-v1 release.
 * The plan lives in the URL (query = plan, hash = step, list order, notes, risk ratings), so a link shares it.
 * Plan state handling follows apps/planner/src/App.tsx, the submitted planner.
 */
import { useEffect, useMemo, useState } from 'react';
import { AnimatePresence, motion, MotionConfig, useReducedMotion } from 'motion/react';
import { loadDataset, ensureMonthly, monthlyColumnsForObjective, type LoadProgress } from '../../atlas/src/planner/data.ts';
import { brief, type Dataset } from '../../atlas/src/planner/engine.ts';
import { decodePlan, encodePlan, validatePlan, type PlanRequest } from '../../atlas/src/plan-url.ts';
import { coordLabel, download, newRequest, normalizeOrder, runSearch, sheetCsv, type Body, type FinderOrder } from './model.ts';
import { Button, STEPS } from './ui.tsx';
import { Destination, CategoryStep, Requirements } from './steps/Setup.tsx';
import { Sites } from './steps/Sites.tsx';
import { Limitations } from './steps/Limitations.tsx';
import { Logistics } from './steps/Logistics.tsx';
import { Risks, decodeRatings, encodeRatings, type Ratings } from './steps/Risks.tsx';
import { PastMissions } from './steps/Missions.tsx';
import { useEngineResults } from './engine-results-ui.tsx';
import { engineBrief, selectedTarget } from './engine-results.ts';

type Load = { state: 'loading'; progress?: LoadProgress } | { state: 'error'; message: string } | { state: 'ready'; data: Dataset };
const LAST = STEPS.length;

function fromUrl() {
  const hash = new URLSearchParams(location.hash.slice(1));
  const targetId = hash.get('target') ?? undefined;
  const notes = hash.get('notes') ?? '';
  const order = normalizeOrder(hash.get('order'));
  const ratings = decodeRatings(hash.get('risk'));
  const raw = Number(hash.get('step'));
  const step = Number.isInteger(raw) && raw >= 1 && raw <= LAST ? raw : 1;
  if (!location.search) return { request: null as PlanRequest | null, step: 1, problems: [] as string[], notes, order: 'engine' as FinderOrder, ratings, targetId };
  const decoded = decodePlan(location.search);
  if (!decoded.ok) return { request: null, step: 1, problems: decoded.errors, notes, order, ratings, targetId };
  return { request: decoded.plan, step, problems: [], notes, order, ratings, targetId };
}

export function App() {
  const [load, setLoad] = useState<Load>({ state: 'loading' });
  const initial = useMemo(fromUrl, []);
  const [body, setBody] = useState<Body>(initial.request?.body ?? 'moon');
  const [categoryId, setCategoryId] = useState<string | undefined>(initial.request?.category);
  const [request, setRequest] = useState<PlanRequest | null>(initial.request);
  const [step, setStep] = useState(initial.request ? initial.step : 1);
  const [reached, setReached] = useState(initial.request ? (initial.request.pins?.length ? LAST : 4) : 1);
  const [removed, setRemoved] = useState<string[]>([]);
  const [checklist] = useState(initial.notes);
  const [order, setOrder] = useState<FinderOrder>(initial.request ? initial.order : 'engine');
  const [ratings, setRatings] = useState<Ratings>(initial.ratings);
  const [targetId, setTargetId] = useState<string | undefined>(initial.targetId);
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
  const engine = useEngineResults(data);

  useEffect(() => {
    if (!data || !request) return;
    let live = true;
    const id = request.objectiveId;
    ensureMonthly(data, monthlyColumnsForObjective(data, id)).then(() => { if (live) setMonthlyFor(id); },
      (e: Error) => setLoad({ state: 'error', message: e.message }));
    return () => { live = false; };
  }, [data, request?.objectiveId]);

  useEffect(() => {
    if (!request || validatePlan(request).length) return;
    const hash = new URLSearchParams({ step: String(step) });
    if (order !== 'engine') hash.set('order', order);
    if (checklist) hash.set('notes', checklist);
    const r = encodeRatings(ratings);
    if (r) hash.set('risk', r);
    if (targetId) hash.set('target', targetId);
    history.replaceState(null, '', `?${encodePlan(request)}#${hash}`);
  }, [request, step, order, checklist, ratings, targetId]);

  useEffect(() => { document.title = `${STEPS[step - 1]!.label} · Analog Atlas`; }, [step]);

  const ready = !!data && !!request && monthlyFor === request.objectiveId;
  const result = useMemo(() => (ready ? runSearch(data!, request!) : null), [ready, data, request]);

  const eligible = (h: string) => {
    const i = data!.h3.indexOf(h);
    return i >= 0 && result!.classes[i] === 0 && !removed.includes(h);
  };
  useEffect(() => {
    if (!data || !request || !result) return;
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
        <span className="brand"><span className="brand-mark" aria-hidden /><span className="brand-name">Analog Atlas</span></span>
        <div className="track" role="progressbar" aria-label="Checking data hashes" aria-valuenow={pct} aria-valuemin={0} aria-valuemax={100}><i style={{ width: `${pct}%` }} /></div>
        <span className="t-small muted">Checking every data file against its published hash</span>
      </main>
    );
  }
  if (load.state === 'error') return <main className="loading"><p className="note warn" style={{ maxWidth: 520 }}>{load.message}</p></main>;

  const d = load.data;
  const category = d.runtime.categories.find(c => c.categoryId === categoryId);
  const go = (n: number) => { if (blocked && n > 3) return; setStep(n); setReached(r => Math.max(r, n)); window.scrollTo({ top: 0 }); };
  const objective = request ? d.objectives.find(o => o.objectiveId === request.objectiveId) : undefined;
  const pinIdx = result ? (request?.pins ?? []).filter(eligible).map(h => d.h3.indexOf(h)) : [];

  const chooseCategory = (id: string) => {
    setCategoryId(id);
    setRequest(newRequest(d, body, d.runtime.categories.find(x => x.categoryId === id)!));
    setRemoved([]); setDropped([]); setOrder('engine'); setRatings({});
    setReached(3);
  };
  const chooseBody = (b: Body) => {
    if (b === body) return;
    setBody(b); setCategoryId(undefined); setRequest(null); setRemoved([]); setDropped([]); setOrder('engine'); setRatings({}); setReached(1);
    setTargetId(undefined);
    history.replaceState(null, '', location.pathname);
  };
  const changeOrder = (next: FinderOrder) => {
    setOrder(next);
    if (request && next === 'slope_mean_deg' && request.sortBy !== 'terrain') setRequest({ ...request, sortBy: 'terrain' });
  };

  const common = request && objective && result ? { data: d, request, sites: pinIdx, objective, result, engine, targetId, onTarget: setTargetId } : null;
  const target = engine.state === 'ready' && request ? selectedTarget(engine.data, request.body, targetId) : undefined;
  let screen;
  if (step === 1) screen = <Destination data={d} body={body} onBody={chooseBody} onNext={() => go(2)} />;
  else if (step === 2) screen = <CategoryStep data={d} body={body} categoryId={categoryId} onCategory={chooseCategory} onBack={() => go(1)} onNext={() => go(3)} />;
  else if (!request || !category) screen = <div className="page"><Button className="btn primary" style={{ alignSelf: 'flex-start' }} onClick={() => go(1)}>Start a plan →</Button></div>;
  else if (step === 3) screen = <Requirements data={d} category={category} request={request} onRequest={r => { setRequest(r); setReached(3); }} onBlocked={setBlocked} onBack={() => go(2)} onNext={() => go(4)} />;
  else if (!common) screen = <main className="loading"><span className="t-small muted">Loading monthly data</span></main>;
  else if (step === 4) screen = <Sites {...common} removed={removed} onRemoved={setRemoved} onPins={p => { setDropped([]); setRequest({ ...request, pins: p.length ? p : undefined }); }} order={order} onOrder={changeOrder} eligible={eligible} dropped={dropped} onBack={() => go(3)} onNext={() => go(5)} />;
  else if (step === 5) screen = <Limitations {...common} onSites={() => go(4)} onBack={() => go(4)} onNext={() => go(6)} />;
  else if (step === 6) screen = <Logistics {...common} onSites={() => go(4)} onBack={() => go(5)} onNext={() => go(7)} />;
  else if (step === 7) screen = <Risks {...common} ratings={ratings} onRatings={setRatings} onSites={() => go(4)} onBack={() => go(6)} onNext={() => go(8)} />;
  else screen = <PastMissions {...common} onBack={() => go(7)} />;

  const maxReach = blocked ? Math.min(reached, 3) : reached;
  return (
    <MotionConfig reducedMotion="user">
      <div className="shell">
        <header className="topbar">
          <div className="topbar-in">
            <a className="brand" href={location.pathname} aria-label="Analog Atlas, start over" style={{ color: 'inherit', textDecoration: 'none' }}>
              <span className="brand-mark" aria-hidden /><span className="brand-name">Analog Atlas</span>
            </a>
            <nav className="steps" aria-label="Steps">
              {STEPS.map((s, k) => {
                const n = k + 1;
                return (
                  <Button key={s.id} className="step" onClick={() => go(n)} disabled={n > maxReach && n !== step}
                    aria-current={n === step ? 'step' : undefined} data-done={n < step && n <= maxReach ? '' : undefined}>
                    <span className="n">{n < step && n <= maxReach ? '✓' : n}</span>{s.label}
                  </Button>
                );
              })}
            </nav>
            <div className="top-actions">
              {request && <CopyLink />}
              {request && pinIdx.length > 0 && (
                <>
                  <Button className="btn sm" title="A tidy CSV: one row per site and trait, with the data manifest hash"
                    onClick={() => download(`analog-atlas-${request.objectiveId}.csv`, sheetCsv(d, request, pinIdx), 'text/csv')}>CSV</Button>
                  <Button className="btn sm primary" title="The plan, verdicts and checklist as a Markdown brief"
                    onClick={() => download(`analog-atlas-brief-${request.objectiveId}.md`, brief(d, request, pinIdx, checklist) + (engine.state === 'ready' && target ? engineBrief(engine.data, target, request.durationDays) : '\nPlanetary engine results unavailable.\n'), 'text/markdown')}>Brief</Button>
                </>
              )}
            </div>
          </div>
        </header>
        {initial.problems.length > 0 && step === 1 && <div className="page" style={{ paddingBottom: 0 }}><p className="note warn">This plan link couldn't be read: {initial.problems.join('; ')}.</p></div>}
        <AnimatePresence mode="wait" initial={false}>
          <motion.main key={step} initial={reduce ? false : { opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }}
            exit={reduce ? undefined : { opacity: 0 }} transition={{ duration: 0.2, ease: [0.22, 1, 0.36, 1] }}>
            {screen}
          </motion.main>
        </AnimatePresence>
        <footer className="foot">
          <div className="foot-in">
            <span>Release <span className="mono">planner-v1</span> · scientific status: partial · {d.h3.length.toLocaleString('en-US')} land cells (H3 res 4, ≈1,770 km² each) · manifest <span className="mono">{d.manifestHash.slice(0, 8)}</span></span>
            <span>Earth data: Copernicus DEM, NASA MODIS, MERRA-2, ESA CCI Permafrost, travel time (Weiss et al. 2018), OurAirports, NASA EONET</span>
          </div>
        </footer>
      </div>
    </MotionConfig>
  );
}

function CopyLink() {
  const [done, setDone] = useState(false);
  return (
    <Button className="btn sm ghost" onClick={() => navigator.clipboard?.writeText(location.href).then(() => { setDone(true); setTimeout(() => setDone(false), 1500); })}>
      {done ? 'Copied' : 'Copy link'}
    </Button>
  );
}
