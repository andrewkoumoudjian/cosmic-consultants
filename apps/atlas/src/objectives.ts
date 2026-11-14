/**
 * Objectives shown in the picker.
 *
 * The rateable rows come straight from data/objectives/*.yaml (contracts lane),
 * copied into src/data/objectives.json by `npm run sync:objectives`.
 *
 * The greyed rows are objectives we do NOT rate. They come from
 * docs/research/07-spaceapps-rules-and-m2m-objectives.md §2.1 ("Not
 * Earth-testable at all as a primary objective"). They are listed so the map
 * is honest about what Earth cannot rehearse (AGENTS.md rule 4, ADR-0002 D1).
 */

import type { ObjectiveRow } from "./types";
import objectiveData from "./data/objectives.json";

export const OBJECTIVES = objectiveData as unknown as ObjectiveRow[];

export const OBJECTIVE_BY_ID = new Map(OBJECTIVES.map((row) => [row.objectiveId, row]));

export interface NotRateableObjective {
  objectiveId: string;
  title: string;
  reason: string;
}

/** Objectives with no Earth-testable component, so they get no level at all. */
export const NOT_RATEABLE: NotRateableObjective[] = [
  {
    objectiveId: "HBS-1",
    title: "Biological effects of the space environment",
    reason: "Earth cannot stand in for the space environment, so there is nothing to rate.",
  },
  {
    objectiveId: "AS-6",
    title: "Partial-gravity human effects",
    reason: "Suit and body behaviour change with gravity, and Earth gravity is not the target.",
  },
  {
    objectiveId: "OP-6",
    title: "Partial-gravity operations",
    reason: "The main content is how crew move and work in low gravity, which Earth cannot rehearse.",
  },
  {
    objectiveId: "PPS-1",
    title: "Radio-quiet far-side operations",
    reason: "The point of the objective is the radio quiet behind the Moon, which Earth cannot reproduce.",
  },
  {
    objectiveId: "HS-3",
    title: "Heliophysics",
    reason: "Space weather on the Sun is not reproducible in a field on Earth.",
  },
];

/** The P0 objectives of the hackathon window (ADR-0003 D4). */
export const P0_OBJECTIVE_IDS = ["OP-5LM", "SE-3LM", "LI-5L"];
