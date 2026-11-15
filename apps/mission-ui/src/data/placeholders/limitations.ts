/**
 * Step 5 (limitation report / "gaps" in MISSION-PLANNER.md). The per-site
 * verdicts and the limitation ratings are engine and review output that
 * doesn't exist yet. Samples come from Figma frame "05 / Limitation report —
 * Moon / Site comparison".
 *
 * In text fields, {metric-id} is replaced by the metric's label. It is bold
 * when the user marked that requirement High or Critical.
 */
import type { World } from '../catalog.ts';
import { PENDING } from '../pending.ts';

export type Verdict = 'supported' | 'uncertain' | 'not-met' | 'not-reproducible';

export const VERDICTS: Record<Verdict, { glyph: string; label: string; color: string }> = {
  supported: { glyph: '✓', label: 'Supported', color: 'var(--status-good)' },
  uncertain: { glyph: '?', label: 'Uncertain', color: 'var(--status-warning)' },
  'not-met': { glyph: '!', label: 'Not met at this site', color: 'var(--status-serious)' },
  'not-reproducible': { glyph: '×', label: 'Not reproducible on Earth', color: 'var(--status-critical)' },
};

type Cell = { verdict: Verdict; value: string };
const c = (verdict: Verdict, value: string): Cell => ({ verdict, value });

export const VERIFICATION = PENDING<Record<string, Record<string, Cell>>>(
  'engine.L4.verificationMatrix',
  'Per-site verdict (match / miss with its gap / unknown) and measured range for each requirement, from the planner engine L4 output. The cell value needs the measured column from columns.yaml per site.',
  {
    'slope-100m': { 'mauna-kea': c('uncertain', '8–22°'), 'haughton-crater': c('supported', '4–12°'), atacama: c('supported', '3–9°'), lanzarote: c('uncertain', '10–25°'), 'mount-etna': c('not-met', '18–30°') },
    'mean-traverse-slope': { 'mauna-kea': c('supported', '6°'), 'haughton-crater': c('supported', '5°'), atacama: c('supported', '4°'), lanzarote: c('supported', '9°'), 'mount-etna': c('not-met', '14°') },
    'elevation-relief': { 'mauna-kea': c('supported', '35 m'), 'haughton-crater': c('not-met', '60 m'), atacama: c('supported', '20 m'), lanzarote: c('supported', '45 m'), 'mount-etna': c('not-met', '80 m') },
    albedo: { 'mauna-kea': c('supported', '0.10–0.14'), 'haughton-crater': c('not-met', '0.18–0.25'), atacama: c('not-met', '0.20–0.30'), lanzarote: c('supported', '0.08–0.12'), 'mount-etna': c('supported', '0.07–0.10') },
    'sunlit-fraction': { 'mauna-kea': c('not-reproducible', '~50%'), 'haughton-crater': c('uncertain', '100% (Jul)'), atacama: c('not-reproducible', '~50%'), lanzarote: c('not-reproducible', '~50%'), 'mount-etna': c('not-reproducible', '~50%') },
  },
);

export type Impact = 'high' | 'moderate' | 'low';

export interface Limitation {
  name: string;
  detail: Record<World, string>;
  impact: Record<string, Impact>;
}

const all = (i: Impact) => ({ 'mauna-kea': i, 'haughton-crater': i, atacama: i, lanzarote: i, 'mount-etna': i });

export const SCIENTIFIC_LIMITATIONS = PENDING<Limitation[]>(
  'gaps.scientificLimitations',
  'Impact rating of each physical limitation per site. Gravity, pressure and radiation are permanent breakdowns (AGENTS.md rule 4); the per-site impact ratings need a reviewed rule, not yet in docs/plan/MISSION-PLANNER.md step 3.',
  [
    { name: 'Gravity', detail: { moon: '1 g everywhere vs 0.17 g on the Moon; wheel loads ~6× lunar.', mars: '1 g everywhere vs 0.38 g on Mars; wheel loads ~2.6× Martian.' }, impact: all('high') },
    { name: 'Vacuum', detail: { moon: '1 atm everywhere; no electrostatic dust, air cooling flatters thermal margins.', mars: '1 atm everywhere vs ~0.006 atm CO₂; convection and dust lofting differ.' }, impact: all('high') },
    { name: 'Regolith mechanics', detail: { moon: 'How closely surface material behaves like lunar regolith under a wheel.', mars: 'How closely surface material behaves like Martian regolith under a wheel.' }, impact: { 'mauna-kea': 'moderate', 'haughton-crater': 'high', atacama: 'moderate', lanzarote: 'low', 'mount-etna': 'moderate' } },
    { name: 'Illumination', detail: { moon: 'Shadow hardness and sun angle compared with the lunar surface.', mars: 'Sun angle and dust-scattered light compared with the Martian surface.' }, impact: { 'mauna-kea': 'moderate', 'haughton-crater': 'low', atacama: 'moderate', lanzarote: 'moderate', 'mount-etna': 'moderate' } },
    { name: 'Thermal range', detail: { moon: 'How far daily temperatures fall short of the lunar swing.', mars: 'How far daily temperatures fall short of the Martian swing.' }, impact: { 'mauna-kea': 'moderate', 'haughton-crater': 'moderate', atacama: 'moderate', lanzarote: 'high', 'mount-etna': 'moderate' } },
    { name: 'Radiation', detail: { moon: 'Not a mobility driver at these test durations.', mars: 'Not a mobility driver at these test durations.' }, impact: all('low') },
  ],
);

export interface TradeOff { name: string; scope: string; text: string; affects: string[] }

export const TRADE_OFFS = PENDING<{ managed: TradeOff[]; constraining: TradeOff[] }>(
  'gaps.tradeOffs',
  'Which limitations can be managed and which constrain conclusions. Needs the gaps step output plus a reviewed mitigation catalogue (none in data/ yet).',
  {
    managed: [
      { name: 'Gravity', scope: 'All sites', text: 'Use a reduced-mass rover or a gravity-offload rig for traction and sinkage runs.', affects: ['mean-traverse-slope', 'slope-100m'] },
      { name: 'Illumination', scope: 'Least effort at Haughton', text: "Run night trials with low-angle artificial lighting; Haughton's low summer sun needs the least correction.", affects: ['albedo'] },
      { name: 'Regolith mechanics', scope: 'Most effort at Haughton', text: 'Calibrate wheel-soil models against LHS-1 simulant; Lanzarote needs the smallest correction.', affects: ['mean-traverse-slope', 'elevation-relief'] },
    ],
    constraining: [
      { name: 'Vacuum', scope: 'All sites', text: "Dust adhesion and thermal behaviour can't be claimed from field data at any site; report them as untested.", affects: ['albedo'] },
      { name: 'Day-night cycle', scope: 'Partial at Haughton', text: 'Only Haughton in July comes close to continuous sunlight; elsewhere power cycling can only be simulated.', affects: ['sunlit-fraction'] },
      { name: 'Thermal range', scope: 'All sites', text: 'No site reaches lunar extremes; Lanzarote is the mildest. Verify thermal limits in a chamber.', affects: ['sunlit-fraction'] },
    ],
  },
);

export interface EvidenceGap { kind: 'uncertain' | 'missing'; spread: string; sites: string[] | 'all'; text: string }

export const DATA_UNCERTAINTY = PENDING<EvidenceGap[]>(
  'gaps.dataUncertainty',
  'Where a verdict rests on coarse, indirect or missing data. Needs per-cell support/coverage diagnostics joined to verdicts (diagnostic columns exist in columns.yaml, the join does not).',
  [
    { kind: 'uncertain', spread: '±4°', sites: ['mauna-kea'], text: '{slope-100m} comes from a 10 m DEM that smooths out short slopes.' },
    { kind: 'uncertain', spread: '±5°', sites: ['lanzarote'], text: '{slope-100m} comes from a 25 m national DEM.' },
    { kind: 'uncertain', spread: '–', sites: ['haughton-crater'], text: '{sunlit-fraction} is verified for July only, at sun heights of 10–35°.' },
    { kind: 'missing', spread: '–', sites: ['atacama', 'mount-etna'], text: 'No in-situ traction data for {mean-traverse-slope}.' },
    { kind: 'missing', spread: '–', sites: 'all', text: "No dust-adhesion data under vacuum for any site's surface material." },
  ],
);

export interface TestRec { title: string; where: string; effect: string; sites: string[] | 'all' }

export const RECOMMENDED_TESTING = PENDING<TestRec[]>(
  'gaps.recommendedTesting',
  'Follow-up tests ordered by how much uncertainty each removes. Needs a test catalogue and an ordering rule; neither exists in data/ yet.',
  [
    { title: 'Fly 0.5 m LiDAR surveys of the traverse corridors', where: 'Field · 1 wk each', effect: 'Resolves {slope-100m}', sites: ['mauna-kea', 'lanzarote'] },
    { title: 'Bevameter and shear-vane tests on surface material', where: 'Field · 2 wk', effect: 'Resolves traction data for {mean-traverse-slope}', sites: ['atacama', 'mount-etna'] },
    { title: 'Reduced-gravity rig for wheel sinkage', where: 'Lab · 3 wk', effect: 'Offsets gravity for {mean-traverse-slope}, {slope-100m}', sites: 'all' },
    { title: 'Field spectrometer albedo transects', where: 'Field · 3 days each', effect: 'Resolves {albedo}', sites: ['haughton-crater', 'atacama'] },
    { title: 'Thermal-vacuum cycling with LHS-1 simulant', where: 'Lab · 4 wk', effect: 'Covers {sunlit-fraction} and vacuum effects', sites: 'all' },
  ],
);
