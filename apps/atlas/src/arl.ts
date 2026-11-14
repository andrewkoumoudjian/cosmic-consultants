/**
 * The ARL ladder (ADR-0002 D2) and how it is drawn.
 *
 * The recompute function below is the same rule as the frozen Lean statement
 * in proofs/Analog/Readiness.lean (gate arl+1 is the first gate that does not
 * pass; gates 1-4 must pass for EVERY required dimension of the objective).
 * It is used to re-check the mock data, never to invent a level: the level in
 * the data is the one shown.
 */

import type { Dimension, GateOutcome, Readiness } from "./types";

export const DIMENSION_GATES = [
  "observed",
  "withinTolerance",
  "corroborated",
  "fieldCharacterized",
] as const;

export const SITE_GATES = ["operable", "campaignProven"] as const;

export const ALL_GATES = [...DIMENSION_GATES, ...SITE_GATES] as const;

export type GateName = (typeof ALL_GATES)[number];

export const GATE_LABEL: Record<GateName, string> = {
  observed: "1. Observed",
  withinTolerance: "2. Within tolerance",
  corroborated: "3. Corroborated",
  fieldCharacterized: "4. Field characterized",
  operable: "5. Operable",
  campaignProven: "6. Campaign proven",
};

export const GATE_PLAIN: Record<GateName, string> = {
  observed: "Observed",
  withinTolerance: "Within tolerance",
  corroborated: "Corroborated",
  fieldCharacterized: "Field characterized",
  operable: "Operable",
  campaignProven: "Campaign proven",
};

export const ARL_NAME: Record<number, string> = {
  0: "Not yet observed",
  1: "Characterizable",
  2: "Envelope match",
  3: "Corroborated",
  4: "Field characterized",
  5: "Operable",
  6: "Campaign proven",
};

/**
 * Ordinal colour ramp for ARL 0..6. Lightness rises with the level, so the
 * ramp reads as ordered and stays readable for red/green colour blindness.
 * The colour of a marker says "how far up the ladder for THIS objective", it
 * is not a similarity score.
 */
export const ARL_COLOUR: Record<number, string> = {
  0: "#440154",
  1: "#3f518b",
  2: "#2c728e",
  3: "#21918c",
  4: "#28ae80",
  5: "#5ec962",
  6: "#addc30",
};

/** Grey for a site with no readiness entry for the selected objective. */
export const NOT_RATED_COLOUR = "#9aa0a6";

export const OUTCOME_LABEL = {
  pass: "pass",
  fail: "fail",
  unknown: "unknown",
} as const;

/** Recompute the level of one readiness entry from its gate outcomes. */
export function recomputeArl(readiness: Readiness, requiredDimensions: Dimension[]): number {
  const rows = new Map(readiness.gates.perDimension.map((row) => [row.dimension, row]));
  let level = 0;
  for (let k = 1; k <= 6; k += 1) {
    const gateName = ALL_GATES[k - 1]!;
    let passes: boolean;
    if ((DIMENSION_GATES as readonly string[]).includes(gateName)) {
      passes =
        requiredDimensions.length > 0 &&
        requiredDimensions.every((dimension) => {
          const row = rows.get(dimension);
          const outcome = row ? (row[gateName as (typeof DIMENSION_GATES)[number]] as GateOutcome) : undefined;
          return outcome?.outcome === "pass";
        });
    } else {
      const outcome = readiness.gates.site[gateName as (typeof SITE_GATES)[number]];
      passes = outcome?.outcome === "pass";
    }
    if (!passes) break;
    level = k;
  }
  return level;
}

/** True when the site is an "opportunity" cell: ARL 3 and gate 4 not passed yet. */
export function isOpportunity(readiness: Readiness): boolean {
  return readiness.arl === 3 && readiness.limitingGate === "fieldCharacterized";
}
