/**
 * The site dossier panel.
 *
 * Everything the panel shows comes from the readiness block of one
 * (site, objective) pair:
 *   - the ARL for THIS objective (ordinal level, never a similarity score),
 *   - the gate ladder with every gate's outcome,
 *   - the limiting dimension and limiting gate,
 *   - the per-dimension analogy vector (one number per dimension, never summed),
 *   - what Earth cannot rehearse for this objective.
 *
 * AGENTS.md rule 4 / ADR-0002 D4: the level is never shown without the vector,
 * the limiting dimension and gate, and the not-testable list.
 */

import {
  ARL_NAME,
  DIMENSION_GATES,
  GATE_LABEL,
  GATE_PLAIN,
  SITE_GATES,
} from "./arl";
import { clear, el } from "./dom";
import type { Dimension, GateOutcome, ObjectiveRow, Outcome, Readiness, Site } from "./types";

const OUTCOME_MARK: Record<Outcome, string> = { pass: "✓", fail: "✗", unknown: "?" };

function outcomeChip(outcome: GateOutcome): HTMLElement {
  const chip = el("span", { class: `chip chip-${outcome.outcome}` });
  chip.append(el("span", { class: "chip-mark", text: OUTCOME_MARK[outcome.outcome] }));
  chip.append(el("span", { class: "chip-text", text: OUTCOME_LABEL_TEXT[outcome.outcome] }));
  return chip;
}

const OUTCOME_LABEL_TEXT: Record<Outcome, string> = {
  pass: "pass",
  fail: "fail",
  unknown: "unknown",
};

function dimensionName(dimension: Dimension): string {
  return dimension.replace(/([A-Z])/g, " $1").replace(/^./, (c) => c.toUpperCase());
}

function gateLadder(readiness: Readiness, objective: ObjectiveRow): HTMLElement {
  const wrap = el("div", { class: "ladder-wrap" });

  const table = el("table", { class: "ladder" });

  const head = el("tr");
  head.append(el("th", { text: "Dimension" }));
  for (const gate of DIMENSION_GATES) {
    head.append(el("th", { class: "ladder-gate", text: GATE_LABEL[gate] }));
  }
  table.append(el("thead", {}, [head]));

  const body = el("tbody");
  const rows = new Map(readiness.gates.perDimension.map((row) => [row.dimension, row]));
  for (const dimension of objective.requiredDimensions) {
    const row = rows.get(dimension);
    const tr = el("tr");
    tr.append(el("th", { class: "ladder-dimension", text: dimensionName(dimension) }));
    for (const gate of DIMENSION_GATES) {
      const cell = el("td");
      const outcome = row ? row[gate] : undefined;
      cell.append(outcome ? outcomeChip(outcome) : el("span", { class: "chip chip-unknown", text: "?" }));
      tr.append(cell);
    }
    body.append(tr);
  }
  table.append(body);
  wrap.append(table);

  // Gates 5 and 6 are about the site, not about one dimension, so they get
  // their own small table instead of empty cells in the dimension rows.
  const siteTable = el("table", { class: "ladder ladder-site" });
  for (const gate of SITE_GATES) {
    const tr = el("tr");
    tr.append(el("th", { class: "ladder-dimension", text: `${GATE_PLAIN[gate]} (site)` }));
    tr.append(el("td", {}, [outcomeChip(readiness.gates.site[gate])]));
    siteTable.append(tr);
  }
  wrap.append(siteTable);

  return wrap;
}

function analogyVector(site: Site): HTMLElement {
  const wrap = el("div", { class: "vector" });
  for (const row of site.analogy) {
    const line = el("div", { class: "vector-row" });
    const label = el("span", { class: "vector-label", text: dimensionName(row.dimension) });
    const bar = el("span", { class: "vector-bar" });
    const fill = el("span", { class: `vector-fill${row.breakdown ? " vector-fill-breakdown" : ""}` });
    fill.style.width = `${Math.min(100, Math.max(2, row.loss * 100))}%`;
    bar.append(fill);
    const value = el("span", {
      class: "vector-value",
      text: row.loss.toFixed(2),
    });
    const flag = row.breakdown
      ? el("span", { class: "vector-flag", text: "breaks down" })
      : el("span", { class: "vector-flag vector-flag-ok", text: "" });
    line.append(label, bar, value, flag);
    wrap.append(line);
  }
  wrap.append(
    el("p", {
      class: "hint",
      text: "One number per dimension. These are never added up, and there is no overall score for a site.",
    }),
  );
  return wrap;
}

function notTestableList(objective: ObjectiveRow, site: Site): HTMLElement {
  const wrap = el("div", { class: "not-testable" });
  const list = el("ul");
  for (const item of objective.notTestableOnEarth) {
    list.append(
      el("li", {}, [
        el("strong", { text: mismatchLabel(item.mismatch) }),
        document.createTextNode(` - ${item.why}`),
      ]),
    );
  }
  wrap.append(list);
  if (site.permanentMismatches.length > 0) {
    wrap.append(
      el("p", {
        class: "hint",
        text: `This cell is also permanently off-target for: ${site.permanentMismatches
          .map(mismatchLabel)
          .join(", ")}.`,
      }),
    );
  }
  return wrap;
}

function mismatchLabel(mismatch: string): string {
  if (mismatch === "gravity") return "Gravity";
  if (mismatch === "pressureRegime") return "Air pressure";
  if (mismatch === "radiation") return "Radiation";
  return mismatch;
}

function evidenceList(readiness: Readiness): HTMLElement {
  const items: HTMLElement[] = [];
  for (const row of readiness.gates.perDimension) {
    for (const gate of DIMENSION_GATES) {
      const outcome = row[gate];
      if (outcome.note || outcome.evidenceRefs.length > 0) {
        items.push(
          el("li", {
            text: `${dimensionName(row.dimension)} - ${GATE_PLAIN[gate]}: ${outcome.outcome}${
              outcome.note ? ` (${outcome.note})` : ""
            }${outcome.evidenceRefs.length ? ` [${outcome.evidenceRefs.join(", ")}]` : ""}`,
          }),
        );
      }
    }
  }
  for (const gate of SITE_GATES) {
    const outcome = readiness.gates.site[gate];
    if (outcome.note || outcome.evidenceRefs.length > 0) {
      items.push(
        el("li", {
          text: `${GATE_PLAIN[gate]} (site): ${outcome.outcome}${
            outcome.note ? ` (${outcome.note})` : ""
          }${outcome.evidenceRefs.length ? ` [${outcome.evidenceRefs.join(", ")}]` : ""}`,
        }),
      );
    }
  }
  if (items.length === 0) {
    return el("p", { class: "hint", text: "No evidence recorded (mock data)." });
  }
  return el("ul", { class: "evidence" }, items);
}

export function renderDossier(
  container: HTMLElement,
  site: Site | undefined,
  objective: ObjectiveRow,
  readiness: Readiness | undefined,
): void {
  clear(container);

  if (!site) {
    container.append(
      el("div", { class: "dossier-empty" }, [
        el("h2", { text: "Pick a site" }),
        el("p", {
          text: "Click a marker on the map to see its gate ladder, the dimension that limits it, and what Earth cannot rehearse there.",
        }),
      ]),
    );
    return;
  }

  container.append(el("h2", { class: "dossier-title", text: site.name ?? site.siteId }));
  container.append(
    el("p", { class: "dossier-meta" }, [
      el("span", { class: "tag tag-synthetic", text: "SYNTHETIC" }),
      document.createTextNode(
        ` ${site.geometry.centroidLat.toFixed(2)}, ${site.geometry.centroidLon.toFixed(2)}`,
      ),
    ]),
  );

  if (!readiness) {
    container.append(
      el("div", { class: "notice" }, [
        el("p", {
          text: `No readiness entry for ${objective.objectiveId} at this cell. That means "not rated here" - it is not a bad score, and the grey hatched marker says the same thing on the map.`,
        }),
      ]),
    );
    container.append(el("h3", { text: "Per-dimension vector" }));
    container.append(analogyVector(site));
    return;
  }

  const badge = el("div", { class: "arl-badge" });
  badge.append(el("span", { class: "arl-number", text: `ARL ${readiness.arl}` }));
  badge.append(el("span", { class: "arl-name", text: ARL_NAME[readiness.arl] ?? "Unknown" }));
  container.append(badge);
  container.append(
    el("p", {
      class: "hint",
      text: `Readiness level for ${objective.objectiveId} (${objective.body}) only. It says nothing about any other objective, and it is not a similarity score.`,
    }),
  );

  container.append(el("h3", { text: "What limits it" }));
  if (readiness.limitingGate === null) {
    container.append(
      el("p", {
        text: "Nothing limits it yet: all six gates pass, so this is the top of the ladder for this objective.",
      }),
    );
  } else {
    const gate = readiness.limitingGate as (typeof DIMENSION_GATES)[number] & string;
    const label = GATE_PLAIN[gate as keyof typeof GATE_PLAIN] ?? readiness.limitingGate;
    container.append(
      el("p", {}, [
        el("strong", { text: `Limiting gate: ${label}` }),
        document.createTextNode(
          readiness.limitingDimension
            ? ` - the weak dimension is ${dimensionName(readiness.limitingDimension)}.`
            : " - this is a site-wide gate, so no single dimension is to blame.",
        ),
      ]),
    );
  }

  container.append(el("h3", { text: "Gate ladder" }));
  container.append(gateLadder(readiness, objective));

  container.append(el("h3", { text: "Per-dimension vector" }));
  container.append(analogyVector(site));

  container.append(el("h3", { text: "Earth cannot rehearse this" }));
  container.append(notTestableList(objective, site));

  container.append(el("h3", { text: "Evidence behind each gate" }));
  container.append(evidenceList(readiness));

  container.append(el("h3", { text: "Provenance" }));
  container.append(
    el("p", {
      class: "hint",
      text: `Statement ledger: ${readiness.statementLedger ?? site.provenance.statementLedger}. Snapshots: ${site.provenance.snapshots.length}. Mock data has no snapshots yet; real cells will link every number to a file in data/snapshots/.`,
    }),
  );
}
