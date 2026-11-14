/**
 * Types that mirror the contracts lane (W10, #15).
 *
 * contracts/site.schema.json      -> Site, Readiness, GateOutcome
 * contracts/objective.schema.json -> ObjectiveRow
 *
 * The app never invents a field that the contract does not have. In particular
 * there is no field for a single similarity score and no field that totals the
 * readiness of several objectives (AGENTS.md rule 4, ADR-0002 D4).
 */

export type Dimension =
  | "terrain"
  | "thermal"
  | "illumination"
  | "dustProcess"
  | "waterIce"
  | "surfaceMaterial"
  | "subsurface"
  | "operations";

export type PermanentMismatch = "gravity" | "pressureRegime" | "radiation";

export type Outcome = "pass" | "fail" | "unknown";

export interface GateOutcome {
  outcome: Outcome;
  evidenceRefs: string[];
  note?: string;
}

/** Gates 1-4, one row per required dimension of the objective. */
export interface DimensionGates {
  dimension: Dimension;
  observed: GateOutcome;
  withinTolerance: GateOutcome;
  corroborated: GateOutcome;
  fieldCharacterized: GateOutcome;
}

/** Gates 5-6, once per site. */
export interface SiteGates {
  operable: GateOutcome;
  campaignProven: GateOutcome;
}

/**
 * The Analog Readiness Level for ONE (site, objective) pair.
 * ARL is an ordinal evidence level, never a similarity score, and never
 * aggregated across objectives (ADR-0002 D2/D4).
 */
export interface Readiness {
  objectiveId: string;
  body: "moon" | "mars";
  /** Largest k <= 6 with gates 1..k all passing. */
  arl: number;
  gates: {
    perDimension: DimensionGates[];
    site: SiteGates;
  };
  /** The first gate that does not pass (gate arl+1). null only when arl = 6. */
  limitingGate: string | null;
  /** A required dimension that does not pass the limiting gate. */
  limitingDimension: Dimension | null;
  statementLedger?: string;
}

/** One row of the per-dimension analogy vector. */
export interface AnalogyRow {
  dimension: Dimension;
  /** Mismatch for this one dimension. 0 = good match, larger = worse. */
  loss: number;
  breakdown: boolean;
  breakdownReason?: string | null;
  datasetRefs?: string[];
}

export interface SnapshotRef {
  datasetId: string;
  sourceUrl: string;
  fetchedAt: string;
  sha256: string;
  license?: string;
}

export interface Site {
  siteId: string;
  name?: string;
  geometry: {
    centroidLat: number;
    centroidLon: number;
    cellSizeKm?: number;
    polygonGeoJson?: object | null;
  };
  analogy: AnalogyRow[];
  permanentMismatches: PermanentMismatch[];
  explorationUse?: string[];
  readiness?: Readiness[];
  provenance: {
    statementLedger: string;
    snapshots: SnapshotRef[];
  };
}

export interface ObjectiveMismatch {
  mismatch: PermanentMismatch;
  why: string;
}

export interface ObjectiveRow {
  objectiveId: string;
  body: "moon" | "mars";
  title: string;
  earthTestableComponent: string;
  rateable: boolean;
  requiredDimensions: Dimension[];
  mapping: {
    status: "proposed" | "reviewed";
    sources: string[];
    notes?: string;
  };
  toleranceSource: {
    envelopeId: string | null;
    note?: string;
  };
  notTestableOnEarth: ObjectiveMismatch[];
  source: {
    url: string;
    sha256: string | null;
    fetchedAt: string | null;
    recordedIn?: string;
  };
  notes?: string;
}
