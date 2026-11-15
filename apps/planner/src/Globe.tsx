/**
 * Night globe (DESIGN.md "Globe"), after the three.js TSL Earth example: a navy sphere,
 * an ultramarine atmosphere, and every published land cell as one dot coloured by the
 * engine's search class. Sites in play and compared sites sit on top.
 * Loaded lazily, so three.js stays out of the first screens.
 */
import { useEffect, useRef } from 'react';
import GlobeGL, { type GlobeInstance } from 'globe.gl';
import { CanvasTexture, MeshBasicMaterial, SRGBColorSpace } from 'three';
import { latLngToCell } from 'h3-js';
import type { Dataset } from '../../atlas/src/planner/engine.ts';
import { SERIES, coordLabel, latLon } from './model.ts';

/** Colour per search class: 0 no required miss, 1 required miss, 2 required unknown, 3 outside limits. */
const CLASS_INK = ['#b4b9ff', '#2a3170', '#e0a531', '#1a2050'];
const SEA = '#0a0f33';
const W = 4096, H = 2048;

function paintTexture(data: Dataset, classes: Uint8Array): HTMLCanvasElement {
  const canvas = document.createElement('canvas');
  canvas.width = W; canvas.height = H;
  const g = canvas.getContext('2d')!;
  g.fillStyle = SEA; g.fillRect(0, 0, W, H);
  g.strokeStyle = 'rgba(140,150,255,0.07)'; g.lineWidth = 1.5;
  for (let lon = -180; lon <= 180; lon += 30) { const x = ((lon + 180) / 360) * W; g.beginPath(); g.moveTo(x, 0); g.lineTo(x, H); g.stroke(); }
  for (let lat = -60; lat <= 60; lat += 30) { const y = ((90 - lat) / 180) * H; g.beginPath(); g.moveTo(0, y); g.lineTo(W, y); g.stroke(); }
  const dot = (i: number, r: number) => {
    const { lat, lon } = latLon(data, i);
    const x = ((lon + 180) / 360) * W, y = ((90 - lat) / 180) * H;
    const stretch = 1 / Math.max(Math.cos((lat * Math.PI) / 180), 0.2);
    g.beginPath(); g.ellipse(x, y, r * stretch, r, 0, 0, Math.PI * 2); g.fill();
  };
  // faint classes first so matches print on top; matches get a soft halo, like lights on the night side
  for (const cls of [3, 1, 2, 0]) {
    if (cls === 0) {
      g.fillStyle = 'rgba(110,120,255,0.10)';
      for (let i = 0; i < classes.length; i++) if (classes[i] === 0) dot(i, 4);
    }
    g.fillStyle = CLASS_INK[cls]!;
    for (let i = 0; i < classes.length; i++) if (classes[i] === cls) dot(i, cls === 0 ? 2.4 : 1.9);
  }
  return canvas;
}

type Point = { i: number; lat: number; lng: number; color: string; r: number; alt: number };

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
