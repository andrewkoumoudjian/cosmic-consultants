#!/usr/bin/env node
/**
 * Copy the objective rows from the contracts lane into the atlas.
 *
 * Source of truth: data/objectives/*.yaml (W10, #15), which validate against
 * contracts/objective.schema.json. The atlas is a static site, so it needs the
 * rows as JSON at build time. This script regenerates apps/atlas/src/data/objectives.json.
 *
 * Usage: node scripts/sync-objectives.mjs   (npm run sync:objectives)
 */
import { readdirSync, readFileSync, writeFileSync, mkdirSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import yaml from "js-yaml";

const here = dirname(fileURLToPath(import.meta.url));
const repoRoot = resolve(here, "..", "..", "..");
const sourceDir = join(repoRoot, "data", "objectives");
const outFile = join(here, "..", "src", "data", "objectives.json");

const rows = readdirSync(sourceDir)
  .filter((name) => name.endsWith(".yaml"))
  .sort()
  .map((name) => {
    const doc = yaml.load(readFileSync(join(sourceDir, name), "utf8"));
    if (!doc || !doc.objectiveId) {
      throw new Error(`${name}: no objectiveId`);
    }
    return doc;
  });

rows.sort((a, b) => (a.objectiveId < b.objectiveId ? -1 : a.objectiveId > b.objectiveId ? 1 : 0));

mkdirSync(dirname(outFile), { recursive: true });
writeFileSync(outFile, `${JSON.stringify(rows, null, 2)}\n`, "utf8");

console.log(`wrote ${outFile}`);
console.log(`objectives: ${rows.map((r) => `${r.objectiveId} (${r.body})`).join(", ")}`);
