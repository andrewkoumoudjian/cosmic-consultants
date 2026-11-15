/**
 * Night globe (DESIGN.md "Globe"), after the three.js TSL Earth example: a navy sphere,
 * an ultramarine atmosphere, and every published land cell as one dot coloured by the
 * engine's search class. Sites in play and compared sites sit on top.
 * Loaded lazily, so three.js stays out of the first screens.
 */
import { useEffect, useRef } from 'react';
import GlobeGL, { type GlobeInstance } from 'globe.gl';
import { CanvasTexture, MeshBasicMaterial, SRGBColorSpace } from 'three';
import { cellToBoundary, directedEdgeToBoundary, getDirectedEdgeDestination, latLngToCell, originToDirectedEdges } from 'h3-js';
import type { Dataset } from '../../atlas/src/planner/engine.ts';
import { SERIES, coordLabel, latLon } from './model.ts';

/** Colour per search class: 0 no required miss, 1 required miss, 2 required unknown, 3 outside limits. */
const CLASS_INK = ['#b4b9ff', '#2a3170', '#e0a531', '#1a2050'];
const SEA = '#060a26';
const LAND_SHELF = '#0e1645';
const W = 4096, H = 2048;

const coastCache = new WeakMap<Dataset, { dry: Uint8Array; segments: Float32Array }>();

/** Extracts outer coastline segments where water_pct < 50% meets ocean/water cells, cached per Dataset. */
function coastTopology(data: Dataset): { dry: Uint8Array; segments: Float32Array } {
  const cached = coastCache.get(data);
  if (cached) return cached;
  const n = data.h3.length;
  const water = data.yearly.water_pct;
  const dry = new Uint8Array(n);
  const drySet = new Set<string>();
  for (let i = 0; i < n; i++) {
    const wp = water?.[i];
    if (wp === undefined || !Number.isFinite(wp) || wp < 50) {
      dry[i] = 1;
      drySet.add(data.h3[i]!);
    }
  }
  const segs: number[] = [];
  for (const h of drySet) {
    for (const edge of originToDirectedEdges(h)) {
      if (drySet.has(getDirectedEdgeDestination(edge))) continue;
      const b = directedEdgeToBoundary(edge, true);
      for (let k = 1; k < b.length; k++) {
        const [lon1, lat1] = b[k - 1]!;
        const [lon2, lat2] = b[k]!;
        if (Math.abs(lon1 - lon2) > 180) continue; // skip antimeridian wrap segment
        segs.push(lon1, lat1, lon2, lat2);
      }
    }
  }
  const res = { dry, segments: new Float32Array(segs) };
  coastCache.set(data, res);
  return res;
}

function paintTexture(data: Dataset, classes: Uint8Array): HTMLCanvasElement {
  const canvas = document.createElement('canvas');
  canvas.width = W; canvas.height = H;
  const g = canvas.getContext('2d')!;
  g.fillStyle = SEA; g.fillRect(0, 0, W, H);
  g.strokeStyle = 'rgba(140,150,255,0.06)'; g.lineWidth = 1.5;
  for (let lon = -180; lon <= 180; lon += 30) { const x = ((lon + 180) / 360) * W; g.beginPath(); g.moveTo(x, 0); g.lineTo(x, H); g.stroke(); }
  for (let lat = -60; lat <= 60; lat += 30) { const y = ((90 - lat) / 180) * H; g.beginPath(); g.moveTo(0, y); g.lineTo(W, y); g.stroke(); }

  const dot = (i: number, r: number) => {
    const { lat, lon } = latLon(data, i);
    const x = ((lon + 180) / 360) * W, y = ((90 - lat) / 180) * H;
    const stretch = 1 / Math.max(Math.cos((lat * Math.PI) / 180), 0.2);
    g.beginPath(); g.ellipse(x, y, r * stretch, r, 0, 0, Math.PI * 2); g.fill();
  };

  const { dry, segments } = coastTopology(data);
  // 1. Subtle land-shelf fill beneath dry cells so continents read separately from open sea
  g.fillStyle = LAND_SHELF;
  for (let i = 0; i < dry.length; i++) if (dry[i] === 1) dot(i, 4.8);

  // 2. Crisp H3 coastlines separating dry land from water-covered / ocean cells
  g.strokeStyle = 'rgba(155, 178, 255, 0.42)';
  g.lineWidth = 1.6;
  g.beginPath();
  for (let k = 0; k < segments.length; k += 4) {
    const x1 = ((segments[k]! + 180) / 360) * W, y1 = ((90 - segments[k + 1]!) / 180) * H;
    const x2 = ((segments[k + 2]! + 180) / 360) * W, y2 = ((90 - segments[k + 3]!) / 180) * H;
    g.moveTo(x1, y1); g.lineTo(x2, y2);
  }
  g.stroke();

  // 3. Cell dots: water-majority cells (water_pct >= 50%) render dimmer than dry land cells
  for (const cls of [3, 1, 2, 0]) {
    if (cls === 0) {
      g.fillStyle = 'rgba(110,120,255,0.10)';
      for (let i = 0; i < classes.length; i++) if (classes[i] === 0 && dry[i] === 1) dot(i, 4);
    }
    g.fillStyle = CLASS_INK[cls]!;
    for (let i = 0; i < classes.length; i++) {
      if (classes[i] !== cls) continue;
      const isDry = dry[i] === 1;
      g.globalAlpha = isDry ? 1 : 0.42;
      dot(i, cls === 0 ? (isDry ? 2.4 : 1.7) : (isDry ? 1.9 : 1.4));
    }
  }
  g.globalAlpha = 1;
  return canvas;
}

type Point = { i: number; lat: number; lng: number; color: string; r: number; alt: number };
type Hex = { i: number; color: string; geometry: { type: 'Polygon'; coordinates: number[][][] } };

/** The cell's real footprint (H3 res 4, about 1,770 km²), so a pin doesn't look like a point site. */
function hex(data: Dataset, i: number, color: string): Hex {
  const ring = cellToBoundary(data.h3[i]!, true);
  return { i, color, geometry: { type: 'Polygon', coordinates: [[...ring, ring[0]!]] } };
}

export default function Globe({ data, classes, inPlay, pins, active, onPick }: {
  data: Dataset; classes: Uint8Array; inPlay: number[]; pins: number[]; active: number | null; onPick: (i: number) => void;
}) {
  const host = useRef<HTMLDivElement>(null);
  const globe = useRef<GlobeInstance | null>(null);
  const byH3 = useRef<Map<string, number>>(new Map());
  const pick = useRef(onPick);
  pick.current = onPick;

  useEffect(() => {
    const el = host.current!;
    if (!byH3.current.size) data.h3.forEach((h, i) => byH3.current.set(h, i));
    const g = new GlobeGL(el, { animateIn: false, rendererConfig: { antialias: true, alpha: true } })
      .backgroundColor('rgba(0,0,0,0)')
      .showAtmosphere(true).atmosphereColor('#4a55ff').atmosphereAltitude(0.16)
      .width(el.clientWidth).height(el.clientHeight)
      .pointLat('lat').pointLng('lng').pointColor('color').pointRadius('r').pointAltitude('alt')
      .pointsMerge(false).pointsTransitionDuration(0)
      .pointLabel((p: object) => coordLabel(data, (p as Point).i))
      .onPointClick((p: object) => pick.current((p as Point).i))
      .onGlobeClick(({ lat, lng }) => {
        const i = byH3.current.get(latLngToCell(lat, lng, 4));
        if (i !== undefined) pick.current(i);
      })
      .polygonGeoJsonGeometry('geometry').polygonCapColor(() => 'rgba(0,0,0,0)').polygonSideColor(() => 'rgba(0,0,0,0)')
      .polygonStrokeColor('color').polygonAltitude(0.004).polygonsTransitionDuration(0)
      .polygonLabel((p: object) => coordLabel(data, (p as Hex).i))
      .ringLat('lat').ringLng('lng').ringColor(() => (t: number) => `rgba(255,255,255,${0.9 * (1 - t)})`)
      .ringMaxRadius(3).ringPropagationSpeed(2).ringRepeatPeriod(1400);
    g.controls().autoRotate = false;
    g.pointOfView({ lat: 20, lng: 0, altitude: 1.75 });
    globe.current = g;
    const ro = new ResizeObserver(() => g.width(el.clientWidth).height(el.clientHeight));
    ro.observe(el);
    return () => { ro.disconnect(); g._destructor(); el.replaceChildren(); globe.current = null; };
  }, [data]);

  useEffect(() => {
    const g = globe.current;
    if (!g) return;
    const texture = new CanvasTexture(paintTexture(data, classes));
    texture.colorSpace = SRGBColorSpace;
    texture.anisotropy = 4;
    const material = new MeshBasicMaterial({ map: texture });
    g.globeMaterial(material);
    return () => { texture.dispose(); material.dispose(); };
  }, [data, classes]);

  useEffect(() => {
    const g = globe.current;
    if (!g) return;
    const pinSet = new Map(pins.map((i, k) => [i, k]));
    const points: Point[] = inPlay.filter(i => !pinSet.has(i)).map(i => ({ i, ...ll(data, i), color: '#ffffff', r: 0.22, alt: 0.006 }));
    for (const [i, k] of pinSet) points.push({ i, ...ll(data, i), color: SERIES[k]!, r: 0.7, alt: 0.03 });
    g.pointsData(points);
    g.ringsData(active === null ? [] : [{ ...ll(data, active) }]);
    const hexes = [...pinSet].map(([i, k]) => hex(data, i, SERIES[k]!));
    if (active !== null && !pinSet.has(active)) hexes.push(hex(data, active, '#ffffff'));
    g.polygonsData(hexes);
  }, [data, inPlay, pins, active]);

  useEffect(() => {
    const g = globe.current;
    if (!g || active === null) return;
    const { lat, lng } = ll(data, active);
    g.pointOfView({ lat, lng, altitude: g.pointOfView().altitude }, 900);
  }, [active, data]);

  return <div ref={host} style={{ width: '100%', height: '100%' }} />;
}

function ll(data: Dataset, i: number) {
  const { lat, lon } = latLon(data, i);
  return { lat, lng: lon };
}
