#!/usr/bin/env node
/**
 * Check the atlas mock data (W11, issue #21).
 *
 * What it checks:
 *   1. every file in apps/atlas/mock/sites/ validates against
 *      contracts/site.schema.json (the contract is the single source of truth),
 *   2. every readiness entry has the ARL that its gates give, using the rule
 *      frozen in proofs/Analog/Readiness.lean: the level is the largest k <= 6
 *      whose gates 1..k all pass, and gates 1-4 must pass for EVERY required
 *      dimension of the objective,
 *   3. the limiting gate and limiting dimension are right,
 *   4. the per-dimension gate rows are exactly the objective's required
 *      dimensions,
 *   5. nothing in the mock data carries a single similarity score or a
 *      cross-objective total (AGENTS.md rule 4),
 *   6. every mock site says SYNTHETIC in its name,
 *   7. the objective rows copied into src/data/objectives.json still match
 *      data/objectives/*.yaml.
 *
 * Usage: node scripts/check-mock.mjs   (npm run check:mock)
 * Exit code 0 only if everything passes.
 */
import { readdirSync, readFileSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import Ajv2020 from "ajv/dist/2020.js";
import addFormats from "ajv-formats";
import yaml from "js-yaml";

const here = dirname(fileURLToPath(import.meta.url));
const atlasRoot = resolve(here, "..");
const repoRoot = resolve(atlasRoot, "..", "..");
const sitesDir = join(atlasRoot, "mock", "sites");

const DIMENSION_GATES = ["observed", "withinTolerance", "corroborated", "fieldCharacterized"];
const SITE_GATES = ["operable", "campaignProven"];
const ALL_GATES = [...DIMENSION_GATES, ...SITE_GATES];

const errors = [];
const fail = (message) => {
  errors.push(message);
  console.log(`FAIL ${message}`);
};
const ok = (message) => console.log(`OK   ${message}`);

function readJson(path) {
  return JSON.parse(readFileSync(path, "utf8"));
}

// --- contract --------------------------------------------------------------
const schema = readJson(join(repoRoot, "contracts", "site.schema.json"));
const ajv = new Ajv2020({ allErrors: true, strict: false });
addFormats(ajv);
const validateSite = ajv.compile(schema);

// --- objectives (contracts lane is the source of truth) ---------------------
const objectiveDir = join(repoRoot, "data", "objectives");
const objectives = new Map();
for (const name of readdirSync(objectiveDir).filter((n) => n.endsWith(".yaml")).sort()) {
  const doc = yaml.load(readFileSync(join(objectiveDir, name), "utf8"));
  objectives.set(`${doc.objectiveId}/${doc.body}`, doc);
}
console.log(`objectives loaded from data/objectives: ${[...objectives.keys()].join(", ")}`);

// --- the copied objective rows must still match ----------------------------
const copied = readJson(join(atlasRoot, "src", "data", "objectives.json"));
if (copied.length !== objectives.size) {
  fail(`src/data/objectives.json has ${copied.length} rows, data/objectives has ${objectives.size}`);
}
for (const row of copied) {
  const source = objectives.get(`${row.objectiveId}/${row.body}`);
  if (!source) {
    fail(`src/data/objectives.json has an objective with no row in data/objectives: ${row.objectiveId}`);
    continue;
  }
  if (JSON.stringify(row) !== JSON.stringify(source)) {
    fail(`src/data/objectives.json is stale for ${row.objectiveId} - run: npm run sync:objectives`);
  }
}
if (!errors.length) ok("objective rows in src/data/objectives.json match data/objectives/*.yaml");

// --- ARL rule (mirrors proofs/Analog/Readiness.lean) -----------------------
function gatePasses(entry, required, k) {
  const gate = ALL_GATES[k - 1];
  if (DIMENSION_GATES.includes(gate)) {
    const rows = new Map(entry.gates.perDimension.map((row) => [row.dimension, row]));
    return (
      required.length > 0 &&
      required.every((dimension) => rows.get(dimension)?.[gate]?.outcome === "pass")
    );
  }
  return entry.gates.site[gate]?.outcome === "pass";
}

function recomputeArl(entry, required) {
  let level = 0;
  for (let k = 1; k <= 6; k += 1) {
    if (!gatePasses(entry, required, k)) break;
    level = k;
  }
  return level;
}

// --- rule 4: no single similarity score, no cross-objective total ----------
const FORBIDDEN_KEY = /(similarity|score|overallreadiness|overall_readiness|composite|aggregate|ranking|index)$/i;
function scanForForbiddenKeys(node, path) {
  if (Array.isArray(node)) {
    node.forEach((item, i) => scanForForbiddenKeys(item, `${path}[${i}]`));
    return;
  }
  if (node && typeof node === "object") {
    for (const [key, value] of Object.entries(node)) {
      if (FORBIDDEN_KEY.test(key)) {
        fail(`${path}.${key} looks like a single similarity score or a cross-objective total (rule 4)`);
      }
      scanForForbiddenKeys(value, `${path}.${key}`);
    }
  }
}

// --- every mock site -------------------------------------------------------
const siteFiles = readdirSync(sitesDir).filter((name) => name.endsWith(".json")).sort();
if (siteFiles.length === 0) fail("no mock site files found");

let rated = 0;
let levels = new Map();

for (const file of siteFiles) {
  const rel = `apps/atlas/mock/sites/${file}`;
  const site = readJson(join(sitesDir, file));

  if (!validateSite(site)) {
    for (const error of validateSite.errors ?? []) {
      fail(`${rel}: ${error.instancePath || "<root>"} ${error.message}`);
    }
    continue;
  }

  if (!String(site.name ?? "").includes("SYNTHETIC")) {
    fail(`${rel}: the site name must say SYNTHETIC`);
  }
  if (!file.startsWith("synthetic-")) {
    fail(`${rel}: the file name must start with "synthetic-"`);
  }

  scanForForbiddenKeys(site, rel);

  for (const entry of site.readiness ?? []) {
    rated += 1;
    const objective = objectives.get(`${entry.objectiveId}/${entry.body}`);
    if (!objective) {
      fail(`${rel}: no objective row for ${entry.objectiveId}/${entry.body}`);
      continue;
    }
    const required = objective.requiredDimensions;
    const rows = entry.gates.perDimension.map((row) => row.dimension);
    if (
      rows.length !== required.length ||
      !required.every((dimension) => rows.includes(dimension))
    ) {
      fail(`${rel} ${entry.objectiveId}: gate rows ${rows.join(",")} must be exactly ${required.join(",")}`);
      continue;
    }
    const level = recomputeArl(entry, required);
    if (entry.arl !== level) {
      fail(`${rel} ${entry.objectiveId}: arl says ${entry.arl} but the gates give ${level}`);
    }
    const wantGate = level === 6 ? null : ALL_GATES[level];
    if (entry.limitingGate !== wantGate) {
      fail(`${rel} ${entry.objectiveId}: limitingGate should be ${wantGate}, got ${entry.limitingGate}`);
    }
    if (wantGate && DIMENSION_GATES.includes(wantGate)) {
      const failing = entry.gates.perDimension
        .filter((row) => row[wantGate].outcome !== "pass")
        .map((row) => row.dimension);
      if (!failing.includes(entry.limitingDimension)) {
        fail(
          `${rel} ${entry.objectiveId}: limitingDimension should be one of ${failing.join(",")}, got ${entry.limitingDimension}`,
        );
      }
    } else if (entry.limitingDimension !== null) {
      fail(`${rel} ${entry.objectiveId}: limitingDimension must be null here`);
    }
    levels.set(entry.arl, (levels.get(entry.arl) ?? 0) + 1);
  }
}

ok(`${siteFiles.length} mock site files validate against contracts/site.schema.json`);
ok(`${rated} readiness entries re-compute to the ARL their gates give`);
const spread = [...levels.entries()].sort((a, b) => a[0] - b[0]).map(([level, n]) => `${level}x${n}`).join(", ");
console.log(`     levels present in the mock: ${spread}`);

for (const error of errors) console.log(`ERROR ${error}`);
console.log(errors.length === 0 ? "mock data OK" : `${errors.length} error(s)`);
process.exit(errors.length === 0 ? 0 : 1);
