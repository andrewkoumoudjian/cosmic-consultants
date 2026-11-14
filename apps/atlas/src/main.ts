/**
 * Atlas app entry point (W11, issue #21).
 *
 * What it does, in plain words:
 *   - you pick one NASA objective,
 *   - the map shows the mock Earth cells coloured by how ready they are for
 *     THAT objective (the Analog Readiness Level from ADR-0002),
 *   - click a cell and the panel on the right explains the level: the gate
 *     ladder, the dimension that limits it, the per-dimension numbers, and the
 *     parts Earth cannot rehearse.
 *
 * What it deliberately does not do: there is no single "how Mars-like is this
 * place" score anywhere in this app (AGENTS.md rule 4, ADR-0002 D4).
 */

import "./styles.css";

import { setWorkerUrl, Popup } from "maplibre-gl";

import { ARL_COLOUR, ARL_NAME, NOT_RATED_COLOUR } from "./arl";
import { SITES, readinessFor, siteById } from "./data";
import { renderDossier } from "./dossier";
import { clear, el } from "./dom";
import {
  LAYER_IDS,
  addSiteLayers,
  createMap,
  setLabelsVisible,
  setOpportunityVisible,
  updateSites,
} from "./map";
import { NOT_RATEABLE, OBJECTIVES, OBJECTIVE_BY_ID, P0_OBJECTIVE_IDS } from "./objectives";
import type { ObjectiveRow } from "./types";

const state = {
  objectiveId: P0_OBJECTIVE_IDS[0] ?? "OP-5LM",
  siteId: null as string | null,
  opportunity: false,
  markers: true,
};

const sidebar = requiredElement("sidebar");
const dossier = requiredElement("dossier");
const mapContainer = requiredElement("map");

function requiredElement(id: string): HTMLElement {
  const node = document.getElementById(id);
  if (!node) throw new Error(`the page is missing #${id}`);
  return node;
}

function objectiveRow(): ObjectiveRow {
  const row = OBJECTIVE_BY_ID.get(state.objectiveId);
  if (!row) throw new Error(`unknown objective ${state.objectiveId}`);
  return row;
}

function bodyLabel(body: "moon" | "mars"): string {
  return body === "moon" ? "Moon" : "Mars";
}

// --- sidebar ---------------------------------------------------------------

function renderObjectivePicker(): HTMLElement {
  const section = el("section", { class: "panel" });
  section.append(el("h2", { text: "Pick an objective" }));

  const rated = el("div", { class: "objective-list" });
  for (const objective of OBJECTIVES) {
    const label = el("label", { class: "objective" });
    const input = el("input", { type: "radio", name: "objective", value: objective.objectiveId });
    if (objective.objectiveId === state.objectiveId) input.setAttribute("checked", "checked");
    input.addEventListener("change", () => selectObjective(objective.objectiveId));
    const text = el("span", { class: "objective-text" });
    text.append(
      el("span", { class: "objective-id" }, [
        el("span", { class: "objective-code", text: objective.objectiveId }),
        el("span", { class: "objective-body", text: bodyLabel(objective.body) }),
      ]),
    );
    text.append(el("span", { class: "objective-title", text: objective.title }));
    label.append(input, text);
    rated.append(label);
  }
  section.append(rated);

  const greyed = el("div", { class: "not-rateable" });
  greyed.append(el("h3", { text: "Not rated (Earth cannot rehearse these)" }));
  const list = el("ul");
  for (const item of NOT_RATEABLE) {
    list.append(
      el("li", {}, [
        el("span", { class: "objective-code objective-code-grey", text: item.objectiveId }),
        document.createTextNode(` ${item.title}. ${item.reason}`),
      ]),
    );
  }
  greyed.append(list);
  section.append(greyed);
  return section;
}

function renderLegend(): HTMLElement {
  const section = el("section", { class: "panel" });
  section.append(el("h2", { text: "Readiness for this objective" }));
  const list = el("ul", { class: "legend" });
  for (let arl = 0; arl <= 6; arl += 1) {
    const item = el("li");
    const swatch = el("span", { class: "swatch" });
    swatch.style.background = ARL_COLOUR[arl] ?? NOT_RATED_COLOUR;
    item.append(swatch);
    item.append(
      el("span", { class: "legend-text" }, [
        el("strong", { text: `ARL ${arl}` }),
        document.createTextNode(` - ${ARL_NAME[arl] ?? "Unknown"}`),
      ]),
    );
    list.append(item);
  }
  const unrated = el("li");
  unrated.append(el("span", { class: "swatch swatch-hatched" }));
  unrated.append(el("span", { class: "legend-text", text: "Not rated for this objective" }));
  list.append(unrated);

  const opportunity = el("li");
  opportunity.append(el("span", { class: "swatch swatch-opportunity" }));
  opportunity.append(
    el("span", { class: "legend-text", text: "Opportunity: ARL 3, no field work published yet" }),
  );
  list.append(opportunity);
  section.append(list);
  return section;
}

function renderToggles(): HTMLElement {
  const section = el("section", { class: "panel" });
  section.append(el("h2", { text: "Layers" }));

  const opportunityLabel = el("label", { class: "toggle" });
  const opportunityInput = el("input", { type: "checkbox" });
  opportunityInput.addEventListener("change", () => {
    state.opportunity = opportunityInput.checked;
    setOpportunityVisible(map, state.opportunity);
  });
  opportunityLabel.append(opportunityInput, document.createTextNode("Opportunity layer"));
  section.append(opportunityLabel);

  const markerLabel = el("label", { class: "toggle" });
  const markerInput = el("input", { type: "checkbox" });
  markerInput.setAttribute("checked", "checked");
  markerInput.addEventListener("change", () => {
    state.markers = markerInput.checked;
    setLabelsVisible(map, state.markers);
  });
  markerLabel.append(markerInput, document.createTextNode("Show markers"));
  section.append(markerLabel);
  return section;
}

function renderHowToRead(): HTMLElement {
  const section = el("section", { class: "panel" });
  section.append(el("h2", { text: "How to read this" }));
  const list = el("ul", { class: "howto" });
  const lines = [
    "Readiness is measured for one objective at a time. Pick a different objective and the map changes.",
    "The colour is an ordinal level from 0 to 6, not a score. Higher means more evidence is in place.",
    "There is no single 'how Mars-like is this place' number, and the levels of different objectives are never combined.",
    "Grey hatched markers are places we have not rated for the objective you picked. That is unknown, not bad.",
    "Every site on this map is synthetic right now. Real data lands later.",
  ];
  for (const line of lines) list.append(el("li", { text: line }));
  section.append(list);
  return section;
}

function renderSidebar(): void {
  clear(sidebar);
  sidebar.append(renderObjectivePicker(), renderLegend(), renderToggles(), renderHowToRead());
}

// --- behaviour -------------------------------------------------------------

let map: ReturnType<typeof createMap>;

function selectObjective(objectiveId: string): void {
  state.objectiveId = objectiveId;
  state.siteId = null;
  updateSites(map, SITES, state.objectiveId);
  renderSidebar();
  renderDossierPanel();
}

function renderDossierPanel(): void {
  const site = state.siteId ? siteById(state.siteId) : undefined;
  const objective = objectiveRow();
  const readiness = site ? readinessFor(site, objective.objectiveId) : undefined;
  renderDossier(dossier, site, objective, readiness);
}

// MapLibre v6 runs the map inside a web worker and looks for its worker file
// next to the bundle. We point it at the copy the Vite plugin serves
// (see vite.config.ts).
setWorkerUrl(new URL("maplibre-gl-worker.mjs", document.baseURI).href);

map = createMap(mapContainer);
map.on("load", () => {
  addSiteLayers(map);
  updateSites(map, SITES, state.objectiveId);
  setOpportunityVisible(map, state.opportunity);
  setLabelsVisible(map, state.markers);
});

for (const layerId of [LAYER_IDS.points, LAYER_IDS.unrated]) {
  map.on("click", layerId, (event) => {
    const feature = event.features?.[0];
    const siteId = feature?.properties?.siteId;
    if (typeof siteId !== "string") return;
    state.siteId = siteId;
    renderDossierPanel();
  });
  map.on("mouseenter", layerId, () => {
    map.getCanvas().style.cursor = "pointer";
  });
  map.on("mouseleave", layerId, () => {
    map.getCanvas().style.cursor = "";
  });
}

// Hover card: the site name and its level for the objective that is selected.
const hoverPopup = new Popup({ closeButton: false, closeOnClick: false, offset: 12 });
for (const layerId of [LAYER_IDS.points, LAYER_IDS.unrated]) {
  map.on("mousemove", layerId, (event) => {
    const feature = event.features?.[0];
    if (!feature || !event.lngLat) return;
    const properties = feature.properties as
      | { name?: string; arl?: number }
      | undefined;
    const objective = objectiveRow();
    const arl = Number(properties?.arl);
    const card = el("div", { class: "hover-card" });
    card.append(el("strong", { text: properties?.name ?? "" }));
    card.append(
      el("span", {
        text:
          arl >= 0
            ? `ARL ${arl} for ${objective.objectiveId}`
            : `Not rated for ${objective.objectiveId}`,
      }),
    );
    hoverPopup.setLngLat(event.lngLat).setDOMContent(card).addTo(map);
  });
  map.on("mouseleave", layerId, () => hoverPopup.remove());
}

renderSidebar();
renderDossierPanel();

// Small debug hook. It lets a screenshot script (or anyone with a console)
// drive the app without clicking, and it does not change any behaviour.
(window as unknown as { __atlas?: unknown }).__atlas = {
  map,
  state,
  selectObjective,
  selectSite: (siteId: string, focus = false) => {
    state.siteId = siteId;
    renderDossierPanel();
    const site = siteById(siteId);
    if (focus && site) {
      map.flyTo({
        center: [site.geometry.centroidLon, site.geometry.centroidLat],
        zoom: 3,
        duration: 800,
      });
    }
  },
};
