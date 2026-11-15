/**
 * Step 6 (logistics). context-r4 publishes access_min_median, airport_km and
 * protected_pct per cell, but this app doesn't load the release yet, and hubs,
 * vehicles, permits, costs and seasonal ratings have no table at all. Samples
 * come from Figma frame "06 / Logistics — Moon / Site comparison".
 */
import { PENDING } from '../pending.ts';

export const PLAN_PARAMETERS = PENDING<{ people: number; fieldDays: number }>(
  'logistics.planParameters',
  'Team size and field days are not asked anywhere in steps 1–3 yet (no Figma screen, no plan-request field in contracts/).',
  { people: 8, fieldDays: 14 },
);

export interface GlanceRow {
  hub: string; hubRegion: string;
  travel: string; travelHow: string;
  vehicles: string; vehiclesNote: string;
  comms: string; commsNote: string;
  permitsApproved: number; permitsTotal: number; permitLead: string;
  bestWindow: string; windowNote: string;
  costUsd: number;
}

export const LOGISTICS_GLANCE = PENDING<Record<string, GlanceRow>>(
  'logistics.glance',
  'Nearest hub, hub-to-site travel, vehicles, comms, permits, season and cost per site. Travel could come from context-r4.access_min_median / airport_km once the app reads the release; the rest has no source table.',
  {
    'mauna-kea': { hub: 'Hilo (ITO)', hubRegion: 'Hawaiʻi', travel: '1 h 45 min', travelHow: 'Highway + 4×4 track', vehicles: '4×4 trucks', vehiclesNote: '+ rover trailer', comms: 'Starlink', commsNote: 'Iridium backup', permitsApproved: 2, permitsTotal: 5, permitLead: 'Lead time 10–16 wk', bestWindow: 'Jun', windowNote: 'May – Sep', costUsd: 148_580 },
    'haughton-crater': { hub: 'Resolute (YRB)', hubRegion: 'Nunavut', travel: '1.5 h charter', travelHow: 'Twin Otter flight', vehicles: 'ATVs', vehiclesNote: 'airlifted', comms: 'Iridium', commsNote: 'no ground network', permitsApproved: 1, permitsTotal: 4, permitLead: 'Lead time 12–20 wk', bestWindow: 'Jul', windowNote: 'Jul – Aug only', costUsd: 214_000 },
    atacama: { hub: 'Antofagasta (ANF)', hubRegion: 'Chile', travel: '3 h 30 min', travelHow: 'Highway + gravel', vehicles: '4×4 trucks', vehiclesNote: '+ rover trailer', comms: 'Starlink', commsNote: 'Iridium backup', permitsApproved: 3, permitsTotal: 3, permitLead: 'Lead time 6 wk', bestWindow: 'Year-round', windowNote: 'best Apr – Oct', costUsd: 118_000 },
    lanzarote: { hub: 'Arrecife (ACE)', hubRegion: 'Canary Islands', travel: '30 min', travelHow: 'Paved road', vehicles: 'Vans', vehiclesNote: '+ rover trailer', comms: '4G + Starlink', commsNote: 'grid power', permitsApproved: 1, permitsTotal: 3, permitLead: 'National park · 6–12 wk', bestWindow: 'Oct – May', windowNote: 'hot Jul – Aug', costUsd: 92_000 },
    'mount-etna': { hub: 'Catania (CTA)', hubRegion: 'Sicily', travel: '1 h 15 min', travelHow: 'Road + 4×4 track', vehicles: '4×4 trucks', vehiclesNote: '+ rover trailer', comms: '4G + Starlink', commsNote: 'weak above 2,500 m', permitsApproved: 2, permitsTotal: 3, permitLead: 'Lead time 6–10 wk', bestWindow: 'May – Sep', windowNote: 'snow Nov – Apr', costUsd: 104_000 },
  },
);

export const LOGISTICS_SUMMARY_NOTES = PENDING<{ hubToSite: string; hubToSiteNote: string; permitLead: string; permitLeadNote: string }>(
  'logistics.summaryNotes',
  'Summary ranges for travel and permit lead time. Derivable from logistics.glance once that exists.',
  { hubToSite: '30 min – 3.5 h', hubToSiteNote: 'Road everywhere except Haughton (charter flight)', permitLead: '6 – 20 wk', permitLeadNote: 'Longest: Haughton Crater' },
);

export const SEASONAL = PENDING<Record<string, number[]>>(
  'logistics.seasonalFeasibility',
  'Monthly field-testing feasibility 0–100 per site from weather, access and daylight. sites-r4-monthly has lst_*, daylight_h and dust_aod per month, but no feasibility rule combines them yet.',
  {
    'mauna-kea': [30, 35, 45, 65, 80, 90, 85, 80, 85, 70, 45, 30],
    'haughton-crater': [0, 0, 0, 0, 10, 55, 90, 75, 20, 0, 0, 0],
    atacama: [70, 65, 75, 85, 85, 80, 80, 85, 85, 85, 80, 75],
    lanzarote: [80, 80, 85, 85, 80, 70, 60, 60, 70, 80, 85, 80],
    'mount-etna': [30, 30, 40, 60, 80, 85, 85, 80, 85, 70, 45, 30],
  },
);

export const SEASONAL_SUMMARY = PENDING<string>(
  'logistics.seasonalSummary',
  'One-line reading of the seasonal heatmap. Written by hand in Figma; would be generated from logistics.seasonalFeasibility.',
  'Jul – Aug is the only window where four of five sites rate good, and the only time Haughton Crater is reachable. Lanzarote and Atacama stay workable most of the year.',
);

export interface SiteDetail {
  route: { stops: { name: string; note: string; altitude: string; field?: boolean }[]; legs: string[] };
  vehicles: { name: string; qty: number; days: number; costUsd: number }[];
  payload: { item: string; dims: string; massKg: number }[];
  coldChain: { temperature: string; lines: string[] };
  burn: { label: string; perDay: number; unit: string; stockDays: number }[];
  resupplyNote: string;
  waste: string[];
  power: string[];
  network: { uplinks: { name: string; role: string; rate: string }[]; camp: { name: string; detail: string; size: string }; field: { name: string; detail: string; rate: string }; links: string[] };
  permits: { status: 'approved' | 'in-review' | 'to-file'; name: string; authority: string; date: string; lead: string }[];
  costs: { label: string; usd: number }[];
  contingencyPct: number;
}

/** Only Mauna Kea has a full plan in Figma; other tabs show an empty state. */
export const SITE_DETAIL = PENDING<Record<string, SiteDetail>>(
  'logistics.siteDetail',
  'Full field plan for one site: route, vehicles, payload, life support, comms, permits and cost. No pipeline table or engine step produces this yet; Figma only draws Mauna Kea.',
  {
    'mauna-kea': {
      route: {
        stops: [
          { name: 'Hilo International Airport (ITO)', note: 'Crew arrival, vehicle pickup, cargo receiving', altitude: 'Hub · sea level' },
          { name: 'Hale Pōhaku', note: 'Required acclimatization stop, at least 30 min', altitude: '2,800 m' },
          { name: 'Field site', note: 'Base camp and test corridor', altitude: '~4,000 m', field: true },
        ],
        legs: ['55 km · 1 h 10 min · Daniel K. Inouye Hwy (Route 200)', '13 km · 35 min · 4×4 only, unpaved'],
      },
      vehicles: [
        { name: '4×4 crew truck, 5 seats', qty: 2, days: 14, costUsd: 4200 },
        { name: 'Flatbed + rover trailer', qty: 1, days: 14, costUsd: 2900 },
        { name: 'Cargo van, Hilo supply runs', qty: 1, days: 6, costUsd: 780 },
      ],
      payload: [
        { item: 'Rover chassis', dims: '1.60 × 1.10 × 0.90 m', massKg: 340 },
        { item: 'Instrument crates ×6', dims: '0.80 × 0.60 × 0.50 m', massKg: 270 },
        { item: 'Diesel generator', dims: '1.20 × 0.80 × 0.90 m', massKg: 210 },
        { item: 'Solar array kit', dims: '2.00 × 1.00 × 0.30 m', massKg: 60 },
        { item: 'Comms & camp kit', dims: '–', massKg: 90 },
      ],
      coldChain: {
        temperature: '−20 °C',
        lines: [
          'Dry-ice shippers (2 × 25 L), restocked from Hilo every 3 days',
          'Overnight air freight Hilo → lab, 48 h door to door',
          'Temperature logger and chain-of-custody form on every shipper',
        ],
      },
      burn: [
        { label: 'FOOD', perDay: 16, unit: 'kg / day', stockDays: 5 },
        { label: 'POTABLE WATER', perDay: 32, unit: 'L / day', stockDays: 4 },
        { label: 'GENERATOR FUEL', perDay: 18, unit: 'L diesel / day', stockDays: 6 },
      ],
      resupplyNote: 'Resupply run to Hilo every 4 days keeps at least 2 days of reserve on site.',
      waste: ['All solid waste packed out daily to Hilo', '3 × 120 L sealed bins per day', 'Greywater collected, nothing discharged on site', 'Portable toilets, serviced twice weekly'],
      power: ['5 kW diesel generator (primary)', '2 kW solar array + 10 kWh battery', 'Avg. camp load 3.1 kW · peak 4.6 kW', 'Rover charging overnight, 6 h'],
      network: {
        uplinks: [
          { name: 'Starlink', role: 'Primary uplink', rate: '≈150 Mbps' },
          { name: 'Iridium Certus', role: 'Backup · voice + telemetry', rate: '≤704 kbps' },
        ],
        camp: { name: 'Base camp network', detail: 'Wi-Fi 6 mesh · local data server · GPS time server', size: '4 nodes' },
        field: { name: 'Rover & field team', detail: 'Rover telemetry, video, and handheld radios', rate: '2 Mbps' },
        links: ['Ethernet into camp router, automatic failover', '900 MHz radio link · up to 2 km line of sight'],
      },
      permits: [
        { status: 'approved', name: 'Maunakea access & research approval', authority: 'Maunakea Stewardship Oversight Authority', date: 'Apr 18', lead: 'Lead time 8–12 wk' },
        { status: 'approved', name: 'Cultural consultation', authority: 'Native Hawaiian cultural practitioners', date: 'Apr 2', lead: 'Lead time Ongoing' },
        { status: 'in-review', name: 'Conservation District Use Permit', authority: 'Hawaiʻi DLNR, Office of Conservation', date: 'Filed Mar 10', lead: 'Lead time 10–16 wk' },
        { status: 'in-review', name: 'Drone flight clearance', authority: 'FAA Part 107 + airspace authorization', date: 'Filed Apr 22', lead: 'Lead time 2–6 wk' },
        { status: 'to-file', name: 'Land-use & facility agreement', authority: 'University of Hawaiʻi, Hale Pōhaku', date: 'Due May 1', lead: 'Lead time 4 wk' },
      ],
      costs: [
        { label: 'Personnel (8 people × 14 days)', usd: 96_000 },
        { label: 'Transport & vehicles', usd: 12_400 },
        { label: 'Habitat & life support', usd: 9_800 },
        { label: 'Shipping & cold chain', usd: 5_700 },
        { label: 'Comms & data', usd: 3_200 },
        { label: 'Permits & fees', usd: 2_100 },
      ],
      contingencyPct: 15,
    },
  },
);
