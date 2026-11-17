import { useEffect, useState } from 'react';
import { ensureYearly } from '../../atlas/src/planner/data.ts';
import { requirements, type Dataset } from '../../atlas/src/planner/engine.ts';
import type { PlanRequest } from '../../atlas/src/plan-url.ts';
import { campaignAllocations, loadEngineResults, selectedTarget, targetName, type EngineLoad, type EngineResults, type TargetResult } from './engine-results.ts';
import { DIMENSION_LABEL, MONTHS, coordLabel, fmt, num, type Category } from './model.ts';
import { Button, Card, Select } from './ui.tsx';
import './styles/engine-results.css';

export function useEngineResults(data: Dataset | null): EngineLoad {
  const [load, setLoad] = useState<EngineLoad>({ state: 'loading' });
  useEffect(() => {
    if (!data) return;
    let live = true;
    setLoad({ state: 'loading' });
    loadEngineResults(data).then(results => { if (live) setLoad({ state: 'ready', data: results }); },
      (e: Error) => { if (live) setLoad({ state: 'error', message: e.message }); });
    return () => { live = false; };
  }, [data]);
  return load;
}

export type EngineProps = { engine: EngineLoad; targetId?: string; onTarget: (id: string) => void };
const AXIS_LABEL: Record<string, string> = {
  slope_gap_deg: 'Slope gap', dust_aod_gap: 'Dust gap', wind_speed_gap_ms: 'Wind gap', barren_deficit_pct: 'Bare-ground deficit',
  night_interannual_iqr_k: 'Year-to-year night variation', diurnal_range_gap_k: 'Day/night range gap', thermal_cold_gap_k: 'Cold-temperature gap', permafrost_deficit_pct: 'Permafrost deficit',
};

function TargetPicker({ data, target, body, onTarget }: { data: EngineResults; target: TargetResult; body: 'moon' | 'mars'; onTarget: (id: string) => void }) {
  return <Select label="Planetary target" value={target.targetId} onChange={onTarget}
    options={Object.values(data.targets).filter(t => t.body === body).map(t => ({ value: t.targetId, label: targetName(data, t.targetId) }))} />;
}

function Status({ load }: { load: EngineLoad }) {
  return <p role={load.state === 'error' ? 'alert' : 'status'} className="note">{load.state === 'error' ? load.message : 'Loading verified planetary engine results…'}</p>;
}

export function EngineCandidates({ data, request, engine, targetId, onTarget, onInspect, onCompare, eligible }: EngineProps & {
  data: Dataset; request: PlanRequest; onInspect: (i: number) => void; onCompare: (i: number) => void; eligible: (h3: string) => boolean;
}) {
  const [expanded, setExpanded] = useState(false);
  if (engine.state !== 'ready') return <Status load={engine} />;
  const target = selectedTarget(engine.data, request.body, targetId);
  if (!target) return <p className="note">No published engine scenario for this destination.</p>;
  const all = target.frontierSample;
  return <Card title="Earth analogs for your planetary target" className="engine-results" aside={<TargetPicker data={engine.data} target={target} body={request.body} onTarget={onTarget} />}>
    <p className="t-small text-2">{target.counts.comparable.toLocaleString('en-US')} cells compared across {target.axes.length} traits. {all.length} sampled candidates from Pareto layers 1–{String(target.parameters.maxLayers?.value ?? 'unknown')}; no combined similarity score.</p>
    <p className="t-label muted">Published example with stated team assumptions. Your mission bands below are checked separately.</p>
    <div className="table-wrap"><table className="engine-table"><thead><tr><th>Earth site</th><th>Layer</th>{target.axes.map(a => <th key={a.name} title={`${a.column}; ${a.mode}; target ${a.targetValue ?? 'not applicable'}`}>{AXIS_LABEL[a.name] ?? a.name}<span className="engine-unit">{a.unit}</span></th>)}<th>Your plan</th></tr></thead>
      <tbody>{(expanded ? all : all.slice(0, 5)).map(c => {
        const i = data.h3.indexOf(c.h3), can = i >= 0 && eligible(c.h3), pinned = request.pins?.includes(c.h3) ?? false;
        return <tr key={c.h3}><td><Button className="link mono" disabled={i < 0} onClick={() => onInspect(i)}>{i >= 0 ? coordLabel(data, i) : c.h3}</Button></td><td className="mono">{c.paretoLayer}</td>
          {target.axes.map(a => <td className="mono" key={a.name} title={`Measured ${a.column}: ${c.observations[a.column] ?? 'not recorded'}; target ${a.targetValue ?? 'not applicable'}`}>{num(c.gaps[a.name])}</td>)}
          <td><Button className="btn sm" disabled={!can || (!pinned && (request.pins?.length ?? 0) >= 3)} onClick={() => onCompare(i)}>{pinned ? 'Stop comparing' : can ? 'Compare' : 'Outside mission bands'}</Button></td></tr>;
      })}</tbody></table></div>
    {all.length > 5 && <div><Button className="btn sm" onClick={() => setExpanded(!expanded)}>{expanded ? 'Show fewer candidates' : `Show all ${all.length} engine candidates`}</Button></div>}
    <details className="engine-details"><summary>Target values and scenario assumptions</summary>
      <dl className="engine-facts">{target.axes.map(a => <div key={a.name}><dt>{AXIS_LABEL[a.name] ?? a.name}</dt><dd>{a.targetValue === null ? 'Minimize observed variation' : `${num(a.targetValue)} ${a.unit}`} · {a.mode.replace(/_/g, ' ')}</dd></div>)}</dl>
      {Object.entries(target.parameters).map(([key, p]) => <p className="t-small text-2" key={key}><b>{key}:</b> {JSON.stringify(p.value)}. {p.basis}</p>)}
    </details>
    <EngineEvidence data={data} engine={engine.data} target={target} />
  </Card>;
}

export function CampaignAllocation({ data, request, engine, targetId, onTarget }: EngineProps & { data: Dataset; request: PlanRequest }) {
  if (engine.state !== 'ready') return <Status load={engine} />;
  const target = selectedTarget(engine.data, request.body, targetId);
  if (!target) return null;
  const plan = target.campaignPlan;
  return <Card title="Campaign allocation from the engine" className="engine-results" aside={<TargetPicker data={engine.data} target={target} body={request.body} onTarget={onTarget} />}>
    <p className="t-small text-2">Published scenario for {MONTHS[(plan.month ?? 1) - 1]}; {plan.thermalBandK?.join('–') ?? 'unknown'} K equipment window; worst {num((plan.alpha ?? 0) * 100)}% of historical years. It is not recomputed from your selected sites or edited bands.</p>
    {plan.status === 'solved' ? <>
      <p className={`note${plan.certified ? '' : ' warn'}`}><b>{plan.certified ? 'Certified objective bound' : 'Solved · not certified'}</b>{plan.certified ? `: ${num(plan.certifiedSuboptLe)}` : ` · ${plan.certificationStatus ?? 'certificate unavailable'}`}. Scientific status: partial.</p>
      <div className="table-wrap"><table className="engine-table"><thead><tr><th>Earth site</th><th>Field-day share</th><th>Of your {request.durationDays ?? 'requested'} days</th><th>Month</th></tr></thead><tbody>
        {campaignAllocations(plan, request.durationDays).map(a => { const i = data.h3.indexOf(a.h3); return <tr key={a.key}><td className="mono">{i >= 0 ? coordLabel(data, i) : a.h3}</td><td className="mono">{num(a.weight * 100)}%</td><td className="mono">{a.days === null ? 'not set' : `${num(a.days)} days`}</td><td>{a.month ? MONTHS[a.month - 1] : 'not recorded'}</td></tr>; })}
      </tbody></table></div>
      <p className="t-label muted">Days are a proportional illustration of the published allocation. Campaign risk {num(plan.cvar)} K beyond the equipment window; a field-plan cost, never a site similarity score.</p>
      <details className="engine-details"><summary>Solver evidence and excluded candidates</summary>
        <p className="t-small text-2">Numerical objective-gap estimate: {plan.numericalSuboptEstimate?.toExponential(3) ?? 'not recorded'} (not a certificate). Tail screening: {plan.screeningExact ? 'exact in the solver result' : 'not recorded as exact'}.</p>
        {(plan.excludedCandidates ?? []).map(c => <p className="t-label mono" key={c.h3}>{c.h3}: {c.reason}</p>)}
      </details>
    </> : <p className="note">Campaign {plan.status}: {plan.error ?? plan.missing_reason ?? 'no allocation published'}.</p>}
    <EngineEvidence data={data} engine={engine.data} target={target} />
  </Card>;
}

function EngineEvidence({ data, engine, target }: { data: Dataset; engine: EngineResults; target: TargetResult }) {
  const github = 'https://github.com/andrewkoumoudjian/cosmic-consultants/blob/main/';
  return <details className="engine-details"><summary>Mathematics, data and limits</summary>
    <p className="t-small text-2"><a href={github + 'proofs/Analog/FunnelProofs.lean'} target="_blank" rel="noreferrer">S7: requirement matching</a> · <a href={github + 'proofs/Analog/ParetoLayersProofs.lean'} target="_blank" rel="noreferrer">S9: Pareto ordering</a> · <a href={github + 'proofs/Analog/CampaignOptProofs.lean'} target="_blank" rel="noreferrer">S10: campaign optimization</a>.</p>
    <p className="t-small text-2">Lean proves the stated mathematical rules. Runtime conformance is tested; the proofs do not certify measurements, physical equivalence or this JavaScript build. Past-mission Shapley comparison is not available yet.</p>
    {data.runtime.qualityWarnings.map(w => <p className="t-small text-2" key={w}>{w}</p>)}
    <p className="t-small text-2">Gravity, air pressure and radiation remain permanent differences. Target assumptions: {JSON.stringify(target.notTestableOnEarth)}.</p>
    <p className="t-label mono engine-hash">Manifest SHA256: {engine.manifestHash}<br />Target results SHA256: {engine.files['pareto-targets.json']}</p>
    <p className="t-small"><a href="./data/planner-v1/build-manifest.json" target="_blank" rel="noreferrer">Release manifest</a> · <a href="./data/planner-v1/pareto-targets.json" target="_blank" rel="noreferrer">Engine results</a> · <a href="./data/planner-v1/planetary-targets.json" target="_blank" rel="noreferrer">Planetary measurements</a> · <a href="./data/planner-v1/source-manifest.json" target="_blank" rel="noreferrer">Source provenance</a></p>
  </details>;
}

const GROUPS = {
  surface: { label: 'Surface & vegetation', columns: ['albedo_ws_sw_mean', 'albedo_bs_sw_mean', 'vcf_percent_nonvegetated_pct_mean', 'vcf_percent_tree_cover_pct_mean'] },
  minerals: { label: 'Minerals', columns: ['emit_min_al_oh_share', 'emit_min_carbonate_share', 'emit_min_dust_proxy_share', 'emit_min_fe_mg_smectite_share', 'emit_min_hydration_share', 'emit_min_mafic_bd_1um_share', 'emit_min_sulfate_share', 'emit_n_observed'] },
  subsurface: { label: 'Subsurface', columns: ['regolith_thick_m', 'soil_thick_m', 'sediment_thick_m', 'avg_soil_sed_thick_m', 'hillslope_frac_mean'] },
  weather: { label: 'Wind & dust', columns: ['wind_speed_mean', 'dust_aod_max'] },
  all: { label: 'All published measurements', columns: [] },
} as const;
type Group = keyof typeof GROUPS;
const COLUMN_NAMES: Record<string, string> = {
  albedo_ws_sw_mean: 'White-sky shortwave albedo', albedo_bs_sw_mean: 'Black-sky shortwave albedo', vcf_percent_nonvegetated_pct_mean: 'Non-vegetated cover', vcf_percent_tree_cover_pct_mean: 'Tree cover',
  regolith_thick_m: 'Regolith thickness', soil_thick_m: 'Soil thickness', sediment_thick_m: 'Sediment thickness', avg_soil_sed_thick_m: 'Mean soil and sediment thickness', hillslope_frac_mean: 'Hillslope fraction', wind_speed_mean: 'Mean wind speed', dust_aod_max: 'Maximum dust AOD', emit_n_observed: 'EMIT observations',
};

export function SiteMeasurements({ data, i, engine }: { data: Dataset; i: number; engine: EngineLoad }) {
  const [group, setGroup] = useState<Group>('surface');
  const [loaded, setLoaded] = useState<string>('');
  const [error, setError] = useState('');
  const columns: string[] = engine.state === 'ready' ? (group === 'all' ? Object.keys(engine.data.yearly.columns) : GROUPS[group].columns.filter(c => c in engine.data.yearly.columns)) : [];
  const key = columns.join(',');
  useEffect(() => {
    if (!key) return;
    let live = true;
    setError('');
    Promise.all(key.split(',').map(column => ensureYearly(data, [column]))).then(() => { if (live) setLoaded(key); }, (e: Error) => { if (live) setError(e.message); });
    return () => { live = false; };
  }, [data, key]);
  if (engine.state !== 'ready') return null;
  return <Card title={`Published measurements · ${coordLabel(data, i)}`} className="engine-results" aside={<Select label="Measurement group" value={group} onChange={setGroup} options={Object.entries(GROUPS).map(([value, g]) => ({ value: value as Group, label: g.label }))} />}>
    {error ? <p role="alert" className="note warn">{error}</p> : loaded !== key ? <p role="status">Loading verified measurements…</p> : <div className="table-wrap"><table className="engine-table"><thead><tr><th>Measurement</th><th>Observed value</th><th>Published column</th></tr></thead><tbody>{columns.map(c => {
      const v = data.yearly[c]?.[i], unit = engine.data.yearly.columns[c];
      const reasonIndex = data.runtime.yearlyReasons[i] ?? 0;
      const reason = data.runtime.reasonSets[reasonIndex]?.[c];
      return <tr key={c}><td>{COLUMN_NAMES[c] ?? c.replace('emit_min_', 'EMIT ').replace(/_/g, ' ')}</td><td className="mono">{fmt(v, unit) ?? `Unknown — ${reason ?? 'not recorded for this cell'}`}</td><td className="t-label mono">{c}</td></tr>;
    })}</tbody></table></div>}
    <p className="t-label muted">Observed Earth context, not an accepted cross-body match. Missing values stay unknown. Each array is checked against the release hash before display.</p>
  </Card>;
}

export function CategoryCoverage({ data, category, request }: { data: Dataset; category: Category; request: PlanRequest }) {
  const rules = requirements(data, request);
  const missing = category.traits.filter(d => !rules.some(r => r.dimension === d && r.earthColumn && r.band));
  if (!missing.length) return null;
  return <p className="note warn" role="status">{category.name}: no supported band for {missing.map(d => DIMENSION_LABEL[d] ?? d).join(', ')} in this objective. These traits do not qualify sites. Planetary target comparisons and measured Earth context are available in Sites.</p>;
}
