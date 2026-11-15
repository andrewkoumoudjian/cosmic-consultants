/**
 * Step 7 (risks). The register is a design sample from Figma frame
 * "07 / Risks — Moon / Site comparison". context-r4 has EONET hazard event
 * counts per cell (eonet_*_events) and burned_pct monthly, but no table turns
 * them into scored, mitigated risks. The matrix, exposure table and summary
 * tiles are computed from this register in the UI, so they follow it.
 *
 * Likelihood and severity are qualitative (low / medium / high), and the band
 * comes from where a risk sits on a 3×3 grid. There are no 1–5 digits and no
 * likelihood × severity product: nothing published supports those numbers yet,
 * so the UI doesn't invent them (same call as apps/planner's risk matrix).
 */
import { PENDING } from '../pending.ts';

export type Level = 'low' | 'medium' | 'high';

export type RiskCategory = 'medical' | 'environmental' | 'technical' | 'ecological';

export const RISK_CATEGORIES: { id: RiskCategory; label: string; short: string }[] = [
  { id: 'medical', label: 'MEDICAL & EVACUATION', short: 'MEDICAL' },
  { id: 'environmental', label: 'ENVIRONMENTAL HAZARDS', short: 'ENVIRONMENTAL' },
  { id: 'technical', label: 'TECHNICAL FAILURE', short: 'TECHNICAL' },
  { id: 'ecological', label: 'ECOLOGICAL IMPACT', short: 'ECOLOGICAL' },
];

export interface Risk {
  id: string;
  category: RiskCategory;
  name: string;
  detail: string;
  likelihood: Level;
  severity: Level;
  sites: string[] | 'all';
  mitigation: string;
}

export const RISK_REGISTER = PENDING<Risk[]>(
  'risks.register',
  'Scored risk register per site with mitigations. Hazard inputs exist per cell (context-r4.eonet_*_events, burned_pct), but no risk table, likelihood/severity rule or mitigation catalogue exists yet (MISSION-PLANNER.md step 5).',
  [
    { id: 'R1', category: 'medical', name: 'Acute mountain sickness', detail: 'Working at 3,000–4,200 m without enough acclimatization.', likelihood: 'high', severity: 'medium', sites: ['mauna-kea', 'mount-etna'], mitigation: 'Stage the ascent with a night at mid-altitude, carry pulse oximeters and oxygen, and descend at the first symptoms.' },
    { id: 'R2', category: 'medical', name: 'Delayed medical evacuation', detail: 'Medevac depends on charter aircraft and can stall for days in bad weather.', likelihood: 'low', severity: 'high', sites: ['haughton-crater'], mitigation: 'Bring a wilderness first responder, arrange medevac in advance, and hold extra medical supplies for 72 h.' },
    { id: 'R3', category: 'medical', name: 'Injury on uneven terrain', detail: 'Sprains and falls on loose scree and sharp lava.', likelihood: 'medium', severity: 'medium', sites: 'all', mitigation: 'Require boots and gloves, use a buddy system, and mark walking routes around the test corridor.' },
    { id: 'R4', category: 'environmental', name: 'Volcanic activity', detail: 'Eruptions, ash, or gas can close the test area with little warning.', likelihood: 'medium', severity: 'high', sites: ['mount-etna'], mitigation: 'Monitor INGV volcano alerts daily, stay outside exclusion zones, and keep a rehearsed evacuation route.' },
    { id: 'R5', category: 'environmental', name: 'Polar bear encounter', detail: 'Bears range across Devon Island in summer.', likelihood: 'low', severity: 'high', sites: ['haughton-crater'], mitigation: 'Assign a trained bear monitor, carry deterrents, and keep camp perimeter alarms on overnight.' },
    { id: 'R6', category: 'environmental', name: 'Extreme heat and UV', detail: 'High sun and heat cause exhaustion and overheat electronics.', likelihood: 'high', severity: 'low', sites: ['atacama', 'lanzarote'], mitigation: 'Shift work to early morning, set up shade and water points, and log rover temperatures.' },
    { id: 'R7', category: 'environmental', name: 'Storm or road closure', detail: 'Snow or high wind closes access roads, even in the summer window.', likelihood: 'low', severity: 'high', sites: ['mauna-kea', 'mount-etna'], mitigation: 'Make daily weather go/no-go calls and keep 2 days of reserve supplies on site.' },
    { id: 'R8', category: 'technical', name: 'Rover drivetrain failure', detail: 'Wheel, motor, or gearbox failure ends traverse testing.', likelihood: 'medium', severity: 'high', sites: 'all', mitigation: 'Pack a spares kit with swappable wheel modules, and inspect the drivetrain every morning.' },
    { id: 'R9', category: 'technical', name: 'Comms outage', detail: 'Loss of the satellite link cuts the mission-control loop.', likelihood: 'medium', severity: 'medium', sites: ['haughton-crater'], mitigation: 'Run two independent links, keep scheduled check-ins, and log all data locally.' },
    { id: 'R10', category: 'technical', name: 'Power failure', detail: 'Generator or battery fault stops charging and camp systems.', likelihood: 'low', severity: 'medium', sites: 'all', mitigation: 'Keep a second generator or battery buffer, and do daily load checks.' },
    { id: 'R11', category: 'ecological', name: 'Damage to protected or sacred ground', detail: 'Driving off approved corridors harms fragile surfaces and culturally significant sites.', likelihood: 'medium', severity: 'high', sites: ['mauna-kea', 'lanzarote'], mitigation: 'Stay on approved corridors, bring a cultural or park monitor, and never drive off route.' },
    { id: 'R12', category: 'ecological', name: 'Fuel or fluid spill', detail: 'Diesel or hydraulic fluid contaminates soil.', likelihood: 'low', severity: 'high', sites: 'all', mitigation: 'Use spill kits and drip trays, and refuel only on lined pads.' },
    { id: 'R13', category: 'ecological', name: 'Invasive species transfer', detail: 'Seeds and insects travel in on gear and tyres.', likelihood: 'low', severity: 'medium', sites: ['haughton-crater', 'mauna-kea'], mitigation: 'Clean and inspect all gear, boots, and tyres before arrival.' },
  ],
);

export const LEVELS: Level[] = ['low', 'medium', 'high'];
export const LIKELIHOOD_LABELS: Record<Level, string> = { low: 'Unlikely', medium: 'Possible', high: 'Likely' };
export const SEVERITY_LABELS: Record<Level, string> = { low: 'Minor', medium: 'Moderate', high: 'Severe' };

export type RiskBand = 'high' | 'medium' | 'low';
const STEP: Record<Level, number> = { low: 0, medium: 1, high: 2 };
/** Band of a 3×3 grid cell: the top-right corner is high, the diagonal is medium, the bottom-left is low. */
export function band(likelihood: Level, severity: Level): RiskBand {
  const sum = STEP[likelihood] + STEP[severity];
  return sum >= 3 ? 'high' : sum === 2 ? 'medium' : 'low';
}
export const riskBand = (r: Risk): RiskBand => band(r.likelihood, r.severity);
/** For sorting only (never shown): higher band first, then severity, then likelihood. */
export const riskOrder = (r: Risk): number => STEP[riskBand(r)] * 9 + STEP[r.severity] * 3 + STEP[r.likelihood];

export const NEXT_STEP = PENDING<null>(
  'design.step.pastMissions',
  'MISSION-PLANNER.md step 6 (past analog missions) comes after risks, but the Figma file has no screen for it yet.',
  null,
);
