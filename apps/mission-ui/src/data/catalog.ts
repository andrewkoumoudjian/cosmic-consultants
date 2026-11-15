/**
 * Steps 1–3: destinations, mission categories and their metric menus.
 *
 * Labels and menu order come from the Figma file (frames "02 / Category" and
 * "Picker / …"). Moon and Mars use the same menus there.
 *
 * Pipeline links:
 * - `pipelineCategoryId` is the categoryId in data/pipeline/test-categories.yaml.
 *   That file marks every category `dataSupportStatus: not-established`, so a
 *   link means "same category", not "the data supports this test".
 * - `column` is the workflow-table column in data/pipeline/columns.yaml with
 *   `status: active` that backs the metric. `null` means no published column
 *   backs it yet, and the metric carries a PENDING id instead.
 */
import { PENDING, type Pending } from './pending.ts';

export type World = 'moon' | 'mars';

export const WORLDS: Record<World, { label: string; blurb: string; adjective: string }> = {
  moon: { label: 'Moon', blurb: 'Lunar surface and orbital analogs', adjective: 'Lunar' },
  mars: { label: 'Mars', blurb: 'Martian surface and habitat analogs', adjective: 'Martian' },
};

export type Condition = 'at-least' | 'at-most' | 'equals' | 'greater-than' | 'less-than' | 'matches';
export const CONDITIONS: { id: Condition; label: string }[] = [
  { id: 'at-least', label: 'At least' },
  { id: 'at-most', label: 'At most' },
  { id: 'equals', label: 'Equals' },
  { id: 'greater-than', label: 'Greater than' },
  { id: 'less-than', label: 'Less than' },
  { id: 'matches', label: 'Matches' },
];

export type Priority = 'low' | 'medium' | 'high' | 'critical';
export const PRIORITIES: { id: Priority; label: string }[] = [
  { id: 'low', label: 'Low' },
  { id: 'medium', label: 'Medium' },
  { id: 'high', label: 'High' },
  { id: 'critical', label: 'Critical' },
];

export const MAX_METRICS = 8; // test-categories.yaml selection.maxMetrics

export interface Metric {
  id: string;
  label: string;
  /** Short label for chart axes. */
  short: string;
  unit: string;
  defaultCondition: Condition;
  /** Active column in data/pipeline/columns.yaml, or null. */
  column: string | null;
  /** Set when column is null: what the metric is waiting on. */
  pending?: Pending<null>;
}

function m(
  id: string,
  label: string,
  short: string,
  unit: string,
  defaultCondition: Condition,
  column: string | null,
  awaits?: string,
): Metric {
  return {
    id, label, short, unit, defaultCondition, column,
    pending: column ? undefined : PENDING(`pipeline.metric.${id}`, awaits ?? 'No active column in data/pipeline/columns.yaml backs this metric yet.', null),
  };
}

const DEM_FINE = 'Needs a slope column at this baseline. columns.yaml only has slope_mean_deg and slope fractions from the cell DEM.';
const LITHO = 'GLiM is catalogued (data/catalog/glim-0p5deg.yaml) but has no column in columns.yaml yet.';

export const METRICS: Record<string, Metric> = Object.fromEntries(
  [
    m('slope-regional-2-5km', 'Regional slope over 2–5 km', 'Regional slope', '°', 'at-most', null, DEM_FINE),
    m('slope-local-200-500m', 'Local slope over 200–500 m', 'Local slope', '°', 'at-most', null, DEM_FINE),
    m('slope-100m', 'Slope over 100 m', 'Slope (100 m)', '°', 'at-most', null, DEM_FINE),
    m('slope-fine-20-40m', 'Fine-scale slope over 20–40 m where resolution permits', 'Fine slope', '°', 'at-most', null, DEM_FINE),
    m('slope-5m', 'Slope over 5 m where high-resolution coverage exists', 'Slope (5 m)', '°', 'at-most', null, DEM_FINE),
    m('eva-slope-2km', 'EVA terrain slope over 2 km', 'EVA slope', '°', 'at-most', null, DEM_FINE),
    m('mean-traverse-slope', 'Mean traverse slope', 'Traverse slope', '°', 'at-most', 'slope_mean_deg'),
    m('roughness-matched', 'Terrain roughness at matched spatial scales', 'Roughness', '', 'at-most', null, 'No roughness column in columns.yaml.'),
    m('roughness', 'Terrain roughness', 'Roughness', '', 'at-most', null, 'No roughness column in columns.yaml.'),
    m('elevation-relief', 'Local elevation relief', 'Elevation relief', 'm', 'at-most', 'elev_max_m − elev_min_m'),
    m('albedo', 'Surface albedo', 'Surface albedo', '', 'equals', 'albedo_ws_sw_mean'),
    m('min-solar-elevation', 'Minimum solar elevation', 'Min. sun elevation', '°', 'at-least', 'sun_noon_elev_min_deg'),
    m('sunlit-fraction', 'Sunlit time fraction (proxy)', 'Sunlit fraction', '%', 'at-least', null, 'No sunlit-fraction column. daylight_h (monthly) exists, but no agreed proxy rule turns it into this metric.'),
    m('lithology', 'Lithology class (proxy)', 'Lithology', '', 'matches', null, LITHO),
    m('resource-lithology', 'Resource-relevant lithology class (proxy)', 'Resource lithology', '', 'matches', null, LITHO),
    m('tir-emissivity', 'Thermal-infrared emissivity band shape (proxy)', 'TIR emissivity', '', 'matches', null, 'ASTER GED is catalogued (aster-ged-ag100.yaml) but has no column in columns.yaml yet.'),
    m('spectral-depths', 'Selected-mineral spectral feature depths (proxy)', 'Band depths', '', 'at-least', 'emit_min_*_bd_med'),
    m('hydrated', 'Hydrated-mineral indicators (proxy)', 'Hydrated minerals', '', 'at-least', 'emit_min_hydration_share'),
    m('fe-mg-clay', 'Iron- and magnesium-bearing clay indicators (proxy)', 'Fe/Mg clays', '', 'at-least', 'emit_min_fe_mg_smectite_share'),
    m('al-oh', 'Aluminum-hydroxyl mineral indicators (proxy)', 'Al-OH minerals', '', 'at-least', 'emit_min_al_oh_share'),
    m('clay', 'Clay-mineral indicators (proxy)', 'Clay minerals', '', 'at-least', null, 'Needs a rule combining emit_min_fe_mg_smectite_* and emit_min_al_oh_* into one clay indicator.'),
    m('sulfate', 'Gypsum and sulfate indicators (proxy)', 'Sulfates', '', 'at-least', 'emit_min_sulfate_share'),
    m('carbonate', 'Carbonate indicators (proxy)', 'Carbonates', '', 'at-least', 'emit_min_carbonate_share'),
    m('permafrost', 'Permafrost probability (proxy)', 'Permafrost', '%', 'at-least', 'permafrost_pct'),
    m('ground-ice', 'Mapped ground-ice content class (proxy; pending source clearance)', 'Ground ice', '', 'matches', null, 'NSIDC GGD318 is catalogued but its licence/source clearance is still pending.'),
    m('soil-moisture', 'Near-surface soil moisture (Earth context)', 'Soil moisture', 'm³/m³', 'at-most', null, 'SMAP SPL3SMP_E is catalogued (smap-spl3smp-e.yaml) but has no column in columns.yaml yet.'),
    m('lst-min', 'Observed minimum surface temperature', 'Min. surface temp.', '°C', 'at-most', 'lst_night_min_k'),
    m('lst-max', 'Observed maximum surface temperature', 'Max. surface temp.', '°C', 'at-most', 'lst_day_max_k'),
    m('lst-diurnal', 'Day–night surface-temperature difference', 'Day–night ΔT', '°C', 'at-least', 'lst_diurnal_range_mean_k'),
    m('shadow-fraction', 'Topographic shadow fraction (proxy)', 'Shadow fraction', '%', 'at-least', null, 'No horizon/shadow model in the pipeline yet.'),
    m('dist-shaded', 'Distance to topographically shaded terrain (proxy)', 'Distance to shade', 'km', 'at-most', null, 'No horizon/shadow model in the pipeline yet.'),
    m('horizon', 'Terrain horizon obstruction (proxy)', 'Horizon', '°', 'at-most', null, 'No horizon/shadow model in the pipeline yet.'),
    m('dust-aod', 'Annual mean dust optical depth', 'Dust AOD', '', 'at-least', 'dust_aod_mean'),
    m('dust-exceedance', 'Dust optical-depth exceedance frequency (proxy)', 'Dust exceedance', '%', 'at-least', null, 'Needs an exceedance threshold rule over dust_aod (monthly).'),
    m('bare-ground', 'Bare-ground fraction as a dust-source indicator (proxy)', 'Bare ground', '%', 'at-least', 'barren_pct'),
    m('dust-minerals', 'Dust-source mineral indicators (proxy)', 'Dust minerals', '', 'at-least', 'emit_min_dust_proxy_share'),
    m('wind', 'Horizontal wind speed at available reference heights (Earth context)', 'Wind speed', 'm/s', 'at-least', 'wind_speed_mean'),
    m('thermal-inertia', 'Apparent thermal inertia (proxy)', 'Thermal inertia', 'TIU', 'equals', null, 'No thermal-inertia column; would need albedo + diurnal LST rule.'),
  ].map((x) => [x.id, x]),
);

export interface Category {
  key: string;
  ordinal: string;
  name: string;
  description: string;
  /** categoryId in data/pipeline/test-categories.yaml, or null if none matches. */
  pipelineCategoryId: string | null;
  /** Picker order (Figma "Picker / …" frame). */
  menu: string[];
  /** What the Figma "03 / Metrics" frame shows as already chosen. */
  defaults: { metric: string; condition?: Condition; priority?: Priority }[];
  pending?: Pending<null>;
}

export const CATEGORIES: Category[] = [
  {
    key: 'robotic-mobility', ordinal: '01', name: 'Robotic mobility & navigation',
    description: 'Autonomous navigation, obstacle avoidance, wheel-soil traction, traversability, robotic mapping.',
    pipelineCategoryId: 'robotic-mobility-navigation',
    menu: ['slope-regional-2-5km', 'slope-local-200-500m', 'slope-100m', 'slope-fine-20-40m', 'slope-5m', 'eva-slope-2km', 'mean-traverse-slope', 'roughness-matched', 'elevation-relief', 'albedo', 'min-solar-elevation', 'sunlit-fraction'],
    defaults: [
      { metric: 'slope-100m', condition: 'at-most', priority: 'high' },
      { metric: 'mean-traverse-slope', condition: 'at-most', priority: 'high' },
      { metric: 'elevation-relief', condition: 'at-most', priority: 'medium' },
      { metric: 'albedo', condition: 'equals', priority: 'medium' },
      { metric: 'sunlit-fraction', condition: 'at-least', priority: 'high' },
    ],
  },
  {
    key: 'geological-sampling', ordinal: '02', name: 'Geological exploration & sampling',
    description: 'Rock identification, drilling, coring, geological mapping, sample collection.',
    pipelineCategoryId: 'geological-exploration-sampling',
    menu: ['lithology', 'albedo', 'tir-emissivity', 'hydrated', 'fe-mg-clay', 'al-oh', 'sulfate', 'carbonate'],
    defaults: ['lithology', 'albedo', 'tir-emissivity', 'hydrated', 'fe-mg-clay'].map((metric) => ({ metric })),
  },
  {
    key: 'resource-isru', ordinal: '03', name: 'Resource prospecting / ISRU',
    description: 'Water-ice detection, regolith characterization, excavation, resource extraction.',
    pipelineCategoryId: 'resource-prospecting-isru',
    menu: ['permafrost', 'ground-ice', 'soil-moisture', 'lst-min', 'lst-max', 'lst-diurnal', 'shadow-fraction', 'dist-shaded', 'resource-lithology'],
    defaults: ['permafrost', 'soil-moisture', 'lst-min', 'lst-max'].map((metric) => ({ metric })),
  },
  {
    key: 'human-habitation', ordinal: '04', name: 'Human habitation & operations',
    description: 'EVA procedures, habitat construction, equipment deployment, crew traverses.',
    pipelineCategoryId: 'human-habitation-operations',
    menu: ['slope-100m', 'eva-slope-2km', 'mean-traverse-slope', 'roughness', 'elevation-relief', 'lst-min', 'lst-max', 'lst-diurnal', 'sunlit-fraction', 'min-solar-elevation', 'horizon'],
    defaults: ['slope-100m', 'eva-slope-2km', 'mean-traverse-slope', 'roughness', 'elevation-relief'].map((metric) => ({ metric })),
  },
  {
    key: 'instrument-testing', ordinal: '05', name: 'Instrument & sensor testing',
    description: 'Spectroscopy, ground-penetrating radar, imaging, seismic instruments.',
    pipelineCategoryId: 'instrument-sensor-testing',
    menu: ['albedo', 'tir-emissivity', 'spectral-depths', 'hydrated', 'clay', 'sulfate', 'carbonate', 'roughness', 'lst-min', 'lst-max', 'lst-diurnal', 'min-solar-elevation'],
    defaults: ['albedo', 'tir-emissivity', 'spectral-depths', 'hydrated', 'clay'].map((metric) => ({ metric })),
  },
  {
    key: 'environmental-hazards', ordinal: '06', name: 'Environmental hazards & resilience',
    description: 'Dust exposure, thermal cycling, erosion, surface material behavior.',
    pipelineCategoryId: null,
    pending: PENDING('pipeline.category.environmental-hazards', 'No matching categoryId in data/pipeline/test-categories.yaml (closest: dust-aeolian-processes, thermal-management).', null),
    menu: ['lst-min', 'lst-max', 'lst-diurnal', 'dust-aod', 'dust-exceedance', 'bare-ground', 'dust-minerals', 'wind', 'thermal-inertia'],
    defaults: ['lst-min', 'lst-max', 'lst-diurnal', 'dust-aod', 'dust-exceedance'].map((metric) => ({ metric })),
  },
  {
    key: 'subsurface', ordinal: '07', name: 'Subsurface exploration',
    description: 'Cave mapping, lava-tube exploration, subsurface navigation, drilling.',
    pipelineCategoryId: 'subsurface-exploration',
    menu: [],
    defaults: [],
  },
  {
    key: 'astrobiology', ordinal: '08', name: 'Astrobiology & habitability',
    description: 'Biosignature detection, extremophile studies, habitability assessment, contamination control.',
    pipelineCategoryId: 'astrobiology-habitability',
    menu: ['soil-moisture', 'permafrost', 'lst-min', 'lst-max', 'lst-diurnal', 'hydrated', 'fe-mg-clay', 'al-oh', 'sulfate', 'carbonate', 'lithology'],
    defaults: ['soil-moisture', 'permafrost', 'lst-min', 'lst-max', 'lst-diurnal'].map((metric) => ({ metric })),
  },
];

export function categoryByKey(key: string | null): Category | undefined {
  return CATEGORIES.find((c) => c.key === key);
}
