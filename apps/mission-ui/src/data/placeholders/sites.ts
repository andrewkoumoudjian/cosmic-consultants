/**
 * Step 4 (site finder). Nothing here comes from the pipeline yet: the
 * shortlist, per-requirement fit and map layers are engine output
 * (services/engine, L4 per docs/plan/DATA-PIPELINE.md). The samples are the
 * values drawn in Figma frame "04 / Site finder — Moon / Robotic mobility &
 * navigation", kept so the layout can be checked.
 */
import { BLOCKED, PENDING } from '../pending.ts';

export interface Site {
  id: string;
  name: string;
  region: string;
  country: string;
  lat: number;
  lon: number;
}

export const SITE_SHORTLIST = PENDING<Site[]>(
  'engine.L4.shortlist',
  'Pareto-ordered Earth cells for the chosen objective and requirements, from the planner engine (services/engine, #20; L4 wiring #183/#184). Site names need a gazetteer join that no table has yet.',
  [
    { id: 'mauna-kea', name: 'Mauna Kea', region: 'Hawaiʻi, United States', country: 'US', lat: 19.82, lon: -155.47 },
    { id: 'haughton-crater', name: 'Haughton Crater', region: 'Devon Island, Nunavut, Canada', country: 'CA', lat: 75.38, lon: -89.68 },
    { id: 'atacama', name: 'Atacama Desert', region: 'Antofagasta, Chile', country: 'CL', lat: -24.09, lon: -69.93 },
    { id: 'lanzarote', name: 'Lanzarote', region: 'Canary Islands, Spain', country: 'ES', lat: 29.04, lon: -13.63 },
    { id: 'mount-etna', name: 'Mount Etna', region: 'Sicily, Italy', country: 'IT', lat: 37.75, lon: 14.99 },
    { id: 'bockfjorden', name: 'Bockfjorden', region: 'Svalbard, Norway', country: 'NO', lat: 79.42, lon: 13.33 },
    { id: 'meteor-crater', name: 'Meteor Crater', region: 'Arizona, United States', country: 'US', lat: 35.03, lon: -111.02 },
    { id: 'craters-of-the-moon', name: 'Craters of the Moon', region: 'Idaho, United States', country: 'US', lat: 43.42, lon: -113.52 },
    { id: 'rio-tinto', name: 'Río Tinto', region: 'Huelva, Spain', country: 'ES', lat: 37.72, lon: -6.55 },
    { id: 'wadi-rum', name: 'Wadi Rum', region: 'Aqaba, Jordan', country: 'JO', lat: 29.58, lon: 35.42 },
  ],
);

/** The design starts with Wadi Rum removed, so the "removed" state is visible. */
export const INITIAL_REMOVED: Record<string, string> = {
  'wadi-rum': 'sand too fine for traction tests',
};

/**
 * Per-requirement fit, 0–100, one number per (site, metric). They are never
 * combined into one site score. Only the five Figma metrics have samples;
 * any other metric is drawn as "no data" (vertex left out).
 */
export const REQUIREMENT_FIT = PENDING<Record<string, Record<string, number>>>(
  'engine.L4.requirementFitByMetric',
  'Per-requirement fit (0–100) for each shortlisted site from the planner engine. The scoring rule per metric is not frozen in proofs/ yet (ADR-0001).',
  {
    'mauna-kea': { 'slope-100m': 90, 'mean-traverse-slope': 85, 'elevation-relief': 88, albedo: 78, 'sunlit-fraction': 70 },
    'haughton-crater': { 'slope-100m': 80, 'mean-traverse-slope': 80, 'elevation-relief': 70, albedo: 72, 'sunlit-fraction': 92 },
    atacama: { 'slope-100m': 78, 'mean-traverse-slope': 86, 'elevation-relief': 72, albedo: 88, 'sunlit-fraction': 66 },
    lanzarote: { 'slope-100m': 74, 'mean-traverse-slope': 76, 'elevation-relief': 82, albedo: 70, 'sunlit-fraction': 58 },
    'mount-etna': { 'slope-100m': 68, 'mean-traverse-slope': 72, 'elevation-relief': 66, albedo: 70, 'sunlit-fraction': 54 },
  },
);

/** The design's "92%" per site and the legend's "AVG" are single site scores. */
export const SINGLE_MATCH_PERCENT = BLOCKED(
  'siteFinder.singleMatchPercent',
  'The Figma shows one "match %" per site. AGENTS.md rule 4 forbids a single similarity score per site; it needs an owner decision or ADR before it can be shown.',
);
export const AVERAGE_FIT = BLOCKED(
  'siteFinder.averageFitPerSite',
  'The Figma legend shows an "AVG" fit per site, which collapses the per-requirement vector into one number (AGENTS.md rule 4).',
);

export const MAP_LAYERS = {
  elevation: PENDING<null>('map.layer.elevation', 'Elevation tiles for the site map. Not published for this app (apps/atlas uses GIBS for its basemap only).', null),
  thermal: PENDING<null>('map.layer.thermal', 'Land-surface temperature tiles for the site map (lst_* columns exist per cell, but no tile layer is built).', null),
  fullMap: PENDING<null>('map.fullscreen', 'The "open full map" view isn\'t designed in Figma yet.', null),
};
