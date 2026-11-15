// Round-trip and rejection tests for src/plan-url.ts (#121). Run: npm test
import { test } from "node:test";
import assert from "node:assert/strict";
import {
  DIMENSIONS, LIMITS, decodePlan, encodePlan, validatePlan,
  type Dimension, type LimitKey, type PlanRequest,
} from "../src/plan-url.ts";

const PIN_A = "842a107ffffffff";
const PIN_B = "8428309ffffffff";

const decodeOk = (q: string): PlanRequest => {
  const r = decodePlan(q);
  if (!r.ok) assert.fail(`expected ok for ${q}: ${r.errors.join("; ")}`);
  return r.plan;
};
const decodeErrors = (q: string): string[] => {
  const r = decodePlan(q);
  if (r.ok) assert.fail(`expected errors for ${q}`);
  return r.errors;
};

test("the MISSION-PLANNER.md example URL decodes and re-encodes to the same string", () => {
  const q = `body=mars&obj=OP-5LM&type=robotic&months=6-8&days=14&team=6&lim=access:240,protected:0`
    + `&must=terrain,surfaceMaterial&sort=terrain&top=20&pins=${PIN_A},${PIN_B}`;
  const plan = decodeOk(`?${q}`);
  assert.deepEqual(plan, {
    version: 1, body: "mars", objectiveId: "OP-5LM", missionType: "robotic",
    months: { start: 6, end: 8 }, durationDays: 14, teamSize: 6,
    limits: { access: 240, protected: 0 }, must: ["terrain", "surfaceMaterial"],
    sortBy: "terrain", top: 20, pins: [PIN_A, PIN_B],
  });
  assert.equal(encodePlan(plan), q);
});

test("a request with only the required fields round-trips", () => {
  const plan: PlanRequest = { version: 1, body: "moon", objectiveId: "LI-5L", missionType: "crewed", months: { start: 1, end: 1 } };
  assert.equal(encodePlan(plan), "body=moon&obj=LI-5L&type=crewed&months=1-1");
  assert.deepEqual(decodeOk(encodePlan(plan)), plan);
});

test("every URL field at once round-trips, including wrapped months, negative and strict bands", () => {
  const plan: PlanRequest = {
    version: 1, body: "moon", objectiveId: "SE-3LM", category: "thermal-vacuum", presetCampaignId: "haughton-2023",
    missionType: "instrument", months: { start: 11, end: 2 }, durationDays: 30, teamSize: 1,
    limits: { access: 12.5, protected: 100, airport: 0, slope: 90 },
    must: ["thermal", "waterIce"], nice: ["dustProcess"],
    bandEdits: [{ dimension: "thermal", lo: -40.25, hi: 10, hiStrict: true }, { dimension: "terrain", lo: 0, hi: 1e21 }],
    sortBy: "thermal", top: 1, pins: [PIN_B, PIN_A, "84be8d9ffffffff"],
  };
  const q = encodePlan(plan);
  assert.match(q, /band=thermal:-40\.25\.\.10%3C,terrain:0\.\.1e%2B21/);
  assert.deepEqual(decodeOk(q), plan);
  // Also through a full URL, the way the browser will hand it over.
  assert.deepEqual(decodeOk(new URL(`https://example.test/atlas/?${q}`).search), plan);
});

test("2,000 random valid requests round-trip exactly", () => {
  let seed = 121;
  const rnd = () => ((seed = (seed * 1103515245 + 12345) % 2 ** 31) / 2 ** 31);
  const pick = <T,>(xs: readonly T[]) => xs[Math.floor(rnd() * xs.length)]!;
  const subset = (xs: readonly Dimension[]) => xs.filter(() => rnd() < 0.3);
  const maybe = () => rnd() < 0.5;
  for (let i = 0; i < 2000; i++) {
    const plan: PlanRequest = {
      version: 1, body: pick(["moon", "mars"] as const),
      objectiveId: pick(["OP-5LM", "LI-5L", "SE-3LM", "AS-12", "LIG-1M"]),
      missionType: pick(["robotic", "crewed", "instrument"] as const),
      months: { start: 1 + Math.floor(rnd() * 12), end: 1 + Math.floor(rnd() * 12) },
    };
    if (maybe()) plan.category = pick(["terrain-traverse", "ice", "a1"]);
    if (maybe()) plan.durationDays = 1 + Math.floor(rnd() * 400);
    if (maybe()) plan.teamSize = 1 + Math.floor(rnd() * 50);
    if (maybe()) {
      const limits: Partial<Record<LimitKey, number>> = {};
      for (const k of Object.keys(LIMITS) as LimitKey[]) if (maybe()) limits[k] = Math.round(rnd() * Math.min(LIMITS[k].max, 900) * 100) / 100;
      if (Object.keys(limits).length) plan.limits = limits;
    }
    const must = subset(DIMENSIONS);
    const nice = subset(DIMENSIONS.filter((d) => !must.includes(d)));
    if (must.length) plan.must = must;
    if (nice.length) plan.nice = nice;
    const bands = subset(DIMENSIONS).map((dimension) => {
      const lo = (rnd() - 0.5) * 1000;
      const b = { dimension, lo, hi: lo + rnd() * 500 } as { dimension: Dimension; lo: number; hi: number; hiStrict?: boolean };
      if (maybe()) b.hiStrict = true;
      return b;
    });
    if (bands.length) plan.bandEdits = bands;
    if (maybe()) plan.sortBy = pick(DIMENSIONS);
    if (maybe()) plan.top = 1 + Math.floor(rnd() * 100);
    const pins = [PIN_A, PIN_B, "84be8d9ffffffff"].filter(() => maybe());
    if (pins.length) plan.pins = pins;
    assert.deepEqual(validatePlan(plan), [], `case ${i} should be valid`);
    assert.deepEqual(decodeOk(encodePlan(plan)), plan, `case ${i}`);
  }
});

test("top: null and hiStrict: false encode the same as leaving them out", () => {
  const base: PlanRequest = { version: 1, body: "mars", objectiveId: "OP-5LM", missionType: "robotic", months: { start: 6, end: 8 } };
  assert.equal(encodePlan({ ...base, top: null }), encodePlan(base));
  const strictOff = encodePlan({ ...base, bandEdits: [{ dimension: "terrain", lo: 0, hi: 5, hiStrict: false }] });
  assert.equal(strictOff, encodePlan({ ...base, bandEdits: [{ dimension: "terrain", lo: 0, hi: 5 }] }));
});

test("unknown keys are ignored and reported, not treated as errors", () => {
  const r = decodePlan("body=mars&obj=OP-5LM&type=robotic&months=6-8&utm_source=mail&utm_source=x");
  assert.ok(r.ok);
  assert.deepEqual(r.unknownKeys, ["utm_source"]);
});

const OK = "body=mars&obj=OP-5LM&type=robotic&months=6-8";
const rejects: [string, string, RegExp][] = [
  ["missing body", "obj=OP-5LM&type=robotic&months=6-8", /^body is missing$/],
  ["missing months", "body=mars&obj=OP-5LM&type=robotic", /^months is missing$/],
  ["unknown body", "body=venus&obj=OP-5LM&type=robotic&months=6-8", /body must be one of/],
  ["bad objective id", "body=mars&obj=op5&type=robotic&months=6-8", /not an objective id/],
  ["bad mission type", "body=mars&obj=OP-5LM&type=rover&months=6-8", /type must be one of/],
  ["month 13", "body=mars&obj=OP-5LM&type=robotic&months=13-2", /months must be/],
  ["month 0", "body=mars&obj=OP-5LM&type=robotic&months=0-2", /months must be/],
  ["months not a range", "body=mars&obj=OP-5LM&type=robotic&months=june", /months must be/],
  ["duplicate key", `${OK}&body=moon`, /body appears more than once/],
  ["days 0", `${OK}&days=0`, /days must be a whole number >= 1/],
  ["days not a number", `${OK}&days=two`, /days "two" is not a whole number/],
  ["team decimal", `${OK}&team=2.5`, /team "2.5" is not a whole number/],
  ["unknown limit", `${OK}&lim=noise:3`, /unknown limit "noise"/],
  ["protected over 100", `${OK}&lim=protected:101`, /protected must be a number from 0 to 100/],
  ["negative access", `${OK}&lim=access:-1`, /access must be a number from 0/],
  ["hex number", `${OK}&lim=access:0x10`, /"0x10" is not a number/],
  ["limit without value", `${OK}&lim=access`, /should look like access:240/],
  ["unknown trait", `${OK}&must=gravity`, /must: unknown trait "gravity"/],
  ["must/nice overlap", `${OK}&must=terrain&nice=terrain`, /must and nice both list terrain/],
  ["trait twice", `${OK}&must=terrain,terrain`, /listed twice/],
  ["band lo above hi", `${OK}&band=terrain:10..0`, /lo 10 above hi 0/],
  ["band twice", `${OK}&band=terrain:0..1,terrain:0..2`, /terrain has two bands/],
  ["band shape", `${OK}&band=terrain:0-10`, /should look like terrain:0\.\.10/],
  ["top 0", `${OK}&top=0`, /top must be a whole number >= 1/],
  ["4 pins", `${OK}&pins=${PIN_A},${PIN_B},84be8d9ffffffff,8429a1dffffffff`, /at most 3 \(got 4\)/],
  ["resolution-5 pin", `${OK}&pins=85283473fffffff`, /not an H3 resolution-4 id/],
  ["pin twice", `${OK}&pins=${PIN_A},${PIN_A}`, /pinned twice/],
];
for (const [name, q, want] of rejects) {
  test(`rejects: ${name}`, () => {
    const errors = decodeErrors(q);
    assert.ok(errors.some((e) => want.test(e)), `got: ${errors.join(" | ")}`);
  });
}

test("a URL with several problems reports each one once", () => {
  const errors = decodeErrors("obj=OP-5LM&type=robotic&months=6-8&days=x&pins=nope");
  assert.deepEqual(errors, ["body is missing", 'days "x" is not a whole number', 'pins: "nope" is not an H3 resolution-4 id']);
});

test("huge whole numbers are rejected up front, so encode never writes a link decode refuses (review on #122)", () => {
  const base: PlanRequest = { version: 1, body: "mars", objectiveId: "OP-5LM", missionType: "robotic", months: { start: 6, end: 8 } };
  for (const key of ["durationDays", "teamSize", "top"] as const) {
    assert.ok(validatePlan({ ...base, [key]: 1e21 }).length > 0, `${key}: 1e21 must be invalid`);
    assert.throws(() => encodePlan({ ...base, [key]: 1e21 }), /whole number/);
    const big = { ...base, [key]: Number.MAX_SAFE_INTEGER };
    assert.deepEqual(decodeOk(encodePlan(big)), big, `${key}: largest safe integer round-trips`);
  }
});

test("encodePlan refuses an invalid request instead of writing a bad link", () => {
  const bad = { version: 1, body: "mars", objectiveId: "OP-5LM", missionType: "robotic", months: { start: 6, end: 8 }, pins: [PIN_A, PIN_A] } as PlanRequest;
  assert.throws(() => encodePlan(bad), /pinned twice/);
});
