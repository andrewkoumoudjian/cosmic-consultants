/**
 * The map: a NASA GIBS WMTS basemap plus the site markers.
 *
 * Basemap: NASA GIBS "Blue Marble Shaded Relief and Bathymetry (MODIS)",
 * EPSG:3857, tile matrix set GoogleMapsCompatible_Level8, JPEG tiles.
 * No API key, no NASA logo, public domain imagery. Layer identifier and tile
 * URL were read out of the live WMTS capabilities document
 * (https://gibs.earthdata.nasa.gov/wmts/epsg3857/best/1.0.0/WMTSCapabilities.xml)
 * and a tile was fetched on 2026-11-14 to confirm it returns a real image.
 */

import {
  AttributionControl,
  Map as MapLibreMap,
  NavigationControl,
  type ExpressionSpecification,
  type GeoJSONSource,
} from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";

import { ARL_COLOUR, NOT_RATED_COLOUR, isOpportunity } from "./arl";
import { readinessFor } from "./data";
import type { Site } from "./types";

export const GIBS_TILE_URL =
  "https://gibs.earthdata.nasa.gov/wmts/epsg3857/best/BlueMarble_ShadedRelief_Bathymetry/default/GoogleMapsCompatible_Level8/{z}/{y}/{x}.jpeg";

export const GIBS_ATTRIBUTION =
  'Basemap: NASA GIBS, "Blue Marble Shaded Relief and Bathymetry (MODIS)" - public domain, no key required';

const SOURCE_ID = "sites";
const OPPORTUNITY_LAYER = "sites-opportunity";
const POINTS_LAYER = "sites-points";
const UNRATED_LAYER = "sites-not-rated";

/** Layer ids, so the app can listen for clicks on them. */
export const LAYER_IDS = {
  points: POINTS_LAYER,
  unrated: UNRATED_LAYER,
  opportunity: OPPORTUNITY_LAYER,
} as const;

/** A hatched grey disc: "we have no level for this objective here". */
function hatchedUnknownIcon(): ImageData {
  const size = 64;
  const canvas = document.createElement("canvas");
  canvas.width = size;
  canvas.height = size;
  const context = canvas.getContext("2d");
  if (!context) throw new Error("no 2d context for the hatched marker");
  context.clearRect(0, 0, size, size);
  context.beginPath();
  context.arc(size / 2, size / 2, size / 2 - 2, 0, Math.PI * 2);
  context.fillStyle = "#e6e8ea";
  context.fill();
  context.save();
  context.clip();
  context.strokeStyle = "#8b9096";
  context.lineWidth = 5;
  for (let offset = -size; offset < size * 2; offset += 14) {
    context.beginPath();
    context.moveTo(offset, 0);
    context.lineTo(offset + size, size);
    context.stroke();
  }
  context.restore();
  context.beginPath();
  context.arc(size / 2, size / 2, size / 2 - 2, 0, Math.PI * 2);
  context.strokeStyle = "#6c7176";
  context.lineWidth = 3;
  context.stroke();
  const imageData = context.getImageData(0, 0, size, size);
  return new ImageData(imageData.data, size, size);
}

export function createMap(container: HTMLElement): MapLibreMap {
  const map = new MapLibreMap({
    container,
    style: {
      version: 8,
      sources: {
        gibs: {
          type: "raster",
          tiles: [GIBS_TILE_URL],
          tileSize: 256,
          maxzoom: 8,
          attribution: GIBS_ATTRIBUTION,
        },
      },
      layers: [
        {
          id: "gibs-basemap",
          type: "raster",
          source: "gibs",
          paint: { "raster-opacity": 0.95 },
        },
      ],
    },
    center: [10, 25],
    zoom: 1.4,
    minZoom: 0,
    maxZoom: 8,
    attributionControl: false,
  });

  map.addControl(new NavigationControl({ showCompass: false }), "top-right");
  map.addControl(
    new AttributionControl({ compact: true, customAttribution: GIBS_ATTRIBUTION }),
    "bottom-right",
  );

  return map;
}

export interface SiteFeatureProperties {
  siteId: string;
  name: string;
  /** ARL for the selected objective, or -1 when the site is not rated for it. */
  arl: number;
  rated: number;
  opportunity: number;
  latitude: number;
  longitude: number;
}

export function buildSiteFeatures(sites: Site[], objectiveId: string) {
  const features: Array<{
    type: "Feature";
    geometry: { type: "Point"; coordinates: [number, number] };
    properties: SiteFeatureProperties;
  }> = [];

  for (const site of sites) {
    const readiness = readinessFor(site, objectiveId);
    features.push({
      type: "Feature",
      geometry: {
        type: "Point",
        coordinates: [site.geometry.centroidLon, site.geometry.centroidLat],
      },
      properties: {
        siteId: site.siteId,
        name: site.name ?? site.siteId,
        arl: readiness ? readiness.arl : -1,
        rated: readiness ? 1 : 0,
        opportunity: readiness && isOpportunity(readiness) ? 1 : 0,
        latitude: site.geometry.centroidLat,
        longitude: site.geometry.centroidLon,
      },
    });
  }

  return { type: "FeatureCollection" as const, features };
}

/** Colour expression: ARL 0..6 on the ordinal ramp, everything else grey. */
const arlColourExpression: ExpressionSpecification = [
  "match",
  ["get", "arl"],
  0,
  ARL_COLOUR[0] ?? "#440154",
  1,
  ARL_COLOUR[1] ?? "#3f518b",
  2,
  ARL_COLOUR[2] ?? "#2c728e",
  3,
  ARL_COLOUR[3] ?? "#21918c",
  4,
  ARL_COLOUR[4] ?? "#28ae80",
  5,
  ARL_COLOUR[5] ?? "#5ec962",
  6,
  ARL_COLOUR[6] ?? "#addc30",
  NOT_RATED_COLOUR,
];

export function addSiteLayers(map: MapLibreMap): void {
  if (!map.hasImage("hatched-unknown")) {
    map.addImage("hatched-unknown", hatchedUnknownIcon(), { pixelRatio: 2 });
  }

  map.addSource(SOURCE_ID, {
    type: "geojson",
    data: { type: "FeatureCollection", features: [] },
  });

  // Opportunity layer: ARL 3 with gate 4 not passed yet. A ring, not a colour.
  map.addLayer({
    id: OPPORTUNITY_LAYER,
    type: "circle",
    source: SOURCE_ID,
    filter: ["==", ["get", "opportunity"], 1],
    paint: {
      "circle-radius": 13,
      "circle-color": "rgba(0,0,0,0)",
      "circle-stroke-color": "#ffffff",
      "circle-stroke-width": 2.5,
    },
  });

  map.addLayer({
    id: POINTS_LAYER,
    type: "circle",
    source: SOURCE_ID,
    filter: ["==", ["get", "rated"], 1],
    paint: {
      "circle-radius": 8,
      "circle-color": arlColourExpression,
      "circle-stroke-color": "#1b1b1b",
      "circle-stroke-width": 1.2,
    },
  });

  map.addLayer({
    id: UNRATED_LAYER,
    type: "symbol",
    source: SOURCE_ID,
    filter: ["==", ["get", "rated"], 0],
    layout: {
      "icon-image": "hatched-unknown",
      "icon-size": 0.42,
      "icon-allow-overlap": true,
      "icon-ignore-placement": true,
    },
  });
}

export function updateSites(map: MapLibreMap, sites: Site[], objectiveId: string): void {
  const source = map.getSource(SOURCE_ID) as GeoJSONSource | undefined;
  if (!source) return;
  source.setData(buildSiteFeatures(sites, objectiveId) as never);
}

export function setOpportunityVisible(map: MapLibreMap, visible: boolean): void {
  if (map.getLayer(OPPORTUNITY_LAYER)) {
    map.setLayoutProperty(OPPORTUNITY_LAYER, "visibility", visible ? "visible" : "none");
  }
}

export function setLabelsVisible(map: MapLibreMap, visible: boolean): void {
  if (map.getLayer(POINTS_LAYER)) {
    map.setLayoutProperty(POINTS_LAYER, "visibility", visible ? "visible" : "none");
  }
  if (map.getLayer(UNRATED_LAYER)) {
    map.setLayoutProperty(UNRATED_LAYER, "visibility", visible ? "visible" : "none");
  }
}
