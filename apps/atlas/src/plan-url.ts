// Plan request <-> URL query (W11b slice 1, #121).
//
// One plan request drives all six steps and lives in the URL, so a plan is a
// shareable link (docs/plan/MISSION-PLANNER.md, UI). This file mirrors
// contracts/plan-request.schema.json v1 (#79): same fields, same URL keys,
// same checks. If #79 changes, this file follows it.
//
// Not in the URL: `version` (always 1) and `successCriteria` (too long; it
// goes in the URL hash with the step 4 checklist, a later slice).
//
// Canonical form, so decode(encode(r)) equals r exactly:
// - `top: null` and a missing `top` both mean "all"; decode leaves it out.
// - `hiStrict: false` and a missing `hiStrict` mean the same; decode leaves it out.
// - Empty `must`/`nice`/`bandEdits`/`pins`/`limits` are left out.
// - List order is kept as given.

export const DIMENSIONS = [
  "terrain", "thermal", "illumination", "dustProcess",
  "waterIce", "surfaceMaterial", "subsurface", "operations",
] as const;
export type Dimension = (typeof DIMENSIONS)[number];

export const BODIES = ["moon", "mars"] as const;
export type Body = (typeof BODIES)[number];

export const MISSION_TYPES = ["robotic", "crewed", "instrument"] as const;
export type MissionType = (typeof MISSION_TYPES)[number];

/** Hard limits, in URL order. max is inclusive; every minimum is 0. */
export const LIMITS = {
  access: { max: Infinity, unit: "min" },
  protected: { max: 100, unit: "%" },
  airport: { max: Infinity, unit: "km" },
  slope: { max: 90, unit: "deg" },
} as const;
export type LimitKey = keyof typeof LIMITS;
const LIMIT_KEYS = Object.keys(LIMITS) as LimitKey[];

export interface MonthRange { start: number; end: number }
export interface BandEdit { dimension: Dimension; lo: number; hi: number; hiStrict?: boolean }
export interface SuccessCriterion { dimension: Dimension; text: string }

export interface PlanRequest {
  version: 1;
  body: Body;
  objectiveId: string;
  category?: string;
  presetCampaignId?: string;
  missionType: MissionType;
  months: MonthRange;
  durationDays?: number;
  teamSize?: number;
  limits?: Partial<Record<LimitKey, number>>;
  must?: Dimension[];
  nice?: Dimension[];
  bandEdits?: BandEdit[];
  sortBy?: Dimension;
  top?: number | null;
  pins?: string[];
  successCriteria?: SuccessCriterion[];
}

export type DecodeResult =
  | { ok: true; plan: PlanRequest; unknownKeys: string[] }
  | { ok: false; errors: string[] };

/** Every URL key, in the order encodePlan writes them. */
export const URL_KEYS = [
  "body", "obj", "cat", "preset", "type", "months", "days", "team",
  "lim", "must", "nice", "band", "sort", "top", "pins",
] as const;

const OBJECTIVE_ID = /^[A-Z]{2,3}-[0-9]+(L|M|LM)?$/;
const SLUG = /^[a-z0-9]+(?:-[a-z0-9]+)*$/;
const H3_R4 = /^84[0-9a-f]{13}$/;
const MAX_PINS = 3;
const INT = /^[0-9]+$/;
const NUM = /^-?(?:[0-9]+(?:\.[0-9]+)?|\.[0-9]+)(?:e[+-]?[0-9]+)?$/i;

const isOneOf = <T extends string>(list: readonly T[], v: unknown): v is T =>
  typeof v === "string" && (list as readonly string[]).includes(v);
// Safe integers only: String() writes those as plain digits (it switches to
// exponent form from 1e21), so encodePlan never writes a link decodePlan rejects.
const isInt = (v: unknown, min: number, max = Infinity): v is number =>
  typeof v === "number" && Number.isSafeInteger(v) && v >= min && v <= max;

/** Checks a request against the plan-request rules. Empty list = valid. */
export function validatePlan(p: PlanRequest): string[] {
  const e: string[] = [];
  if (p.version !== 1) e.push("version must be 1");
  if (!isOneOf(BODIES, p.body)) e.push(`body must be one of ${BODIES.join(", ")}`);
  if (typeof p.objectiveId !== "string" || !OBJECTIVE_ID.test(p.objectiveId))
    e.push(`obj "${p.objectiveId}" is not an objective id like OP-5LM`);
  if (p.category !== undefined && !SLUG.test(p.category)) e.push(`cat "${p.category}" is not a lowercase-dash id`);
  if (p.presetCampaignId !== undefined && !SLUG.test(p.presetCampaignId))
    e.push(`preset "${p.presetCampaignId}" is not a lowercase-dash id`);
  if (!isOneOf(MISSION_TYPES, p.missionType)) e.push(`type must be one of ${MISSION_TYPES.join(", ")}`);
  if (!p.months || !isInt(p.months.start, 1, 12) || !isInt(p.months.end, 1, 12))
    e.push("months must be two whole months 1-12, like 6-8 (11-2 wraps over the new year)");
  if (p.durationDays !== undefined && !isInt(p.durationDays, 1)) e.push("days must be a whole number >= 1");
  if (p.teamSize !== undefined && !isInt(p.teamSize, 1)) e.push("team must be a whole number >= 1");
  for (const [k, v] of Object.entries(p.limits ?? {})) {
    if (!isOneOf(LIMIT_KEYS, k)) { e.push(`lim: unknown limit "${k}" (known: ${LIMIT_KEYS.join(", ")})`); continue; }
    if (typeof v !== "number" || !Number.isFinite(v) || v < 0 || v > LIMITS[k].max)
      e.push(`lim: ${k} must be a number from 0 to ${LIMITS[k].max} ${LIMITS[k].unit}`);
  }
  for (const key of ["must", "nice"] as const) {
    const list = p[key] ?? [];
    for (const d of list) if (!isOneOf(DIMENSIONS, d)) e.push(`${key}: unknown trait "${d}"`);
    if (new Set(list).size !== list.length) e.push(`${key}: a trait is listed twice`);
  }
  const both = (p.must ?? []).filter((d) => (p.nice ?? []).includes(d));
  if (both.length) e.push(`must and nice both list ${both.join(", ")}`);
  const seen = new Set<string>();
  for (const b of p.bandEdits ?? []) {
    if (!isOneOf(DIMENSIONS, b.dimension)) { e.push(`band: unknown trait "${b.dimension}"`); continue; }
    if (seen.has(b.dimension)) e.push(`band: ${b.dimension} has two bands`);
    seen.add(b.dimension);
    if (!Number.isFinite(b.lo) || !Number.isFinite(b.hi)) e.push(`band: ${b.dimension} needs two numbers`);
    else if (b.lo > b.hi) e.push(`band: ${b.dimension} has lo ${b.lo} above hi ${b.hi}, so nothing can match`);
  }
  if (p.sortBy !== undefined && !isOneOf(DIMENSIONS, p.sortBy)) e.push(`sort: unknown trait "${p.sortBy}"`);
  if (p.top !== undefined && p.top !== null && !isInt(p.top, 1)) e.push("top must be a whole number >= 1");
  const pins = p.pins ?? [];
  if (pins.length > MAX_PINS) e.push(`pins: at most ${MAX_PINS} (got ${pins.length})`);
  if (new Set(pins).size !== pins.length) e.push("pins: a hexagon is pinned twice");
  for (const h of pins) if (!H3_R4.test(h)) e.push(`pins: "${h}" is not an H3 resolution-4 id`);
  return e;
}

// Keep ':' and ',' readable (both are legal in a query); escape the rest,
// including '+', which URLSearchParams would read back as a space.
const esc = (s: string) => encodeURIComponent(s).replace(/%3A/g, ":").replace(/%2C/g, ",");

/** Request -> query string without the leading "?". Throws on an invalid request. */
export function encodePlan(p: PlanRequest): string {
  const errors = validatePlan(p);
  if (errors.length) throw new Error(`invalid plan request: ${errors.join("; ")}`);
  const kv: [string, string][] = [["body", p.body], ["obj", p.objectiveId]];
  if (p.category !== undefined) kv.push(["cat", p.category]);
  if (p.presetCampaignId !== undefined) kv.push(["preset", p.presetCampaignId]);
  kv.push(["type", p.missionType], ["months", `${p.months.start}-${p.months.end}`]);
  if (p.durationDays !== undefined) kv.push(["days", String(p.durationDays)]);
  if (p.teamSize !== undefined) kv.push(["team", String(p.teamSize)]);
  const lim = LIMIT_KEYS.filter((k) => p.limits?.[k] !== undefined).map((k) => `${k}:${p.limits![k]}`);
  if (lim.length) kv.push(["lim", lim.join(",")]);
  if (p.must?.length) kv.push(["must", p.must.join(",")]);
  if (p.nice?.length) kv.push(["nice", p.nice.join(",")]);
  if (p.bandEdits?.length)
    kv.push(["band", p.bandEdits.map((b) => `${b.dimension}:${b.lo}..${b.hi}${b.hiStrict ? "<" : ""}`).join(",")]);
  if (p.sortBy !== undefined) kv.push(["sort", p.sortBy]);
  if (p.top !== undefined && p.top !== null) kv.push(["top", String(p.top)]);
  if (p.pins?.length) kv.push(["pins", p.pins.join(",")]);
  return kv.map(([k, v]) => `${k}=${esc(v)}`).join("&");
}

/** Query string (with or without "?") or URLSearchParams -> request, or every error found. */
export function decodePlan(query: string | URLSearchParams): DecodeResult {
  const params = typeof query === "string" ? new URLSearchParams(query.replace(/^\?/, "")) : query;
  const errors: string[] = [];
  const unknownKeys: string[] = [];
  const raw = new Map<string, string>();
  for (const [k, v] of params) {
    if (!isOneOf(URL_KEYS, k)) { if (!unknownKeys.includes(k)) unknownKeys.push(k); continue; }
    if (raw.has(k)) errors.push(`${k} appears more than once`);
    raw.set(k, v);
  }
  const int = (key: string, s: string) => {
    if (!INT.test(s)) { errors.push(`${key} "${s}" is not a whole number`); return NaN; }
    return Number(s);
  };
  const num = (key: string, s: string) => {
    if (!NUM.test(s)) { errors.push(`${key}: "${s}" is not a number`); return NaN; }
    return Number(s);
  };
  const list = (s: string) => (s === "" ? [] : s.split(","));

  for (const key of ["body", "obj", "type", "months"]) if (!raw.has(key)) errors.push(`${key} is missing`);
  let months: MonthRange = { start: NaN, end: NaN };
  const m = /^([0-9]{1,2})-([0-9]{1,2})$/.exec(raw.get("months") ?? "");
  if (m) months = { start: Number(m[1]), end: Number(m[2]) };
  // Fields go in in schema order, so the result deep-equals a hand-written request.
  const out = { version: 1, body: raw.get("body") ?? "", objectiveId: raw.get("obj") ?? "" } as PlanRequest;
  const cat = raw.get("cat"); if (cat !== undefined) out.category = cat;
  const preset = raw.get("preset"); if (preset !== undefined) out.presetCampaignId = preset;
  out.missionType = (raw.get("type") ?? "") as MissionType;
  out.months = months;
  const days = raw.get("days"); if (days !== undefined) out.durationDays = int("days", days);
  const team = raw.get("team"); if (team !== undefined) out.teamSize = int("team", team);
  const lim = raw.get("lim");
  if (lim !== undefined) {
    const limits: Record<string, number> = {};
    for (const pair of list(lim)) {
      const i = pair.indexOf(":");
      if (i < 0) { errors.push(`lim: "${pair}" should look like access:240`); continue; }
      const k = pair.slice(0, i);
      if (k in limits) errors.push(`lim: ${k} appears more than once`);
      limits[k] = num(`lim ${k}`, pair.slice(i + 1));
    }
    out.limits = limits;
  }
  const must = raw.get("must"); if (must !== undefined) out.must = list(must) as Dimension[];
  const nice = raw.get("nice"); if (nice !== undefined) out.nice = list(nice) as Dimension[];
  const band = raw.get("band");
  if (band !== undefined) {
    out.bandEdits = [];
    for (const item of list(band)) {
      const m = /^([A-Za-z]+):(.+?)\.\.(.+?)(<)?$/.exec(item);
      if (!m) { errors.push(`band: "${item}" should look like terrain:0..10 (add < for a strict top)`); continue; }
      const b: BandEdit = { dimension: m[1] as Dimension, lo: num(`band ${m[1]}`, m[2]!), hi: num(`band ${m[1]}`, m[3]!) };
      if (m[4]) b.hiStrict = true;
      out.bandEdits.push(b);
    }
  }
  const sort = raw.get("sort"); if (sort !== undefined) out.sortBy = sort as Dimension;
  const top = raw.get("top"); if (top !== undefined) out.top = int("top", top);
  const pins = raw.get("pins"); if (pins !== undefined) out.pins = list(pins);

  // Report every problem once: skip rule errors for a field that already failed to parse.
  const field = (msg: string) => msg.split(/[\s:]/, 1)[0]!;
  const failed = new Set(errors.map(field));
  errors.push(...validatePlan(out).filter((msg) => !failed.has(field(msg))));
  return errors.length ? { ok: false, errors } : { ok: true, plan: out, unknownKeys };
}
