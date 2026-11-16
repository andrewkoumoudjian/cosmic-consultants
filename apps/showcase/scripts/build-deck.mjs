// Builds the Analog Atlas showcase deck.
//
// Writes two files from the content below:
//   composition/index.html  the HyperFrames composition (every slide is a top-level scene)
//   index.html              the website: <hyperframes-slideshow> around <hyperframes-player>
// The slideshow island is written into both from one source, so they can't drift
// (standalone-harness rule 1). Edit the content here, then `npm run build`.
import { writeFileSync } from 'node:fs';
import { APP_URL, DEMO_URL } from './demo-url.mjs';

const REPO = 'https://github.com/andrewkoumoudjian/cosmic-consultants';
const SRC = `${REPO}/blob/main/apps/mission-ui/src/steps`;
const SLOT = 10; // seconds of timeline per slide; the deck is navigated, not played through

// ---------- content ----------

const STEPS = [
  {
    n: 1, label: 'Destination', title: 'Pick a world.', file: 'Setup.tsx', h: 905,
    lead: 'Start with the Moon or Mars. Gravity and air are shown up front, because Earth can match neither.',
    foci: [
      { x: 33, y: 233, w: 677, h: 480, cap: 'Moon: polar terrain, low sun, cold traps, sharp regolith.' },
      { x: 755, y: 662, w: 318, h: 28, cap: 'Mars: 0.38 g and thin CO₂ air, before you begin.' },
    ],
  },
  {
    n: 2, label: 'Objectives', title: 'Say what to test.', file: 'Setup.tsx', h: 900,
    lead: 'Nineteen mission objectives, each tagged with the Earth traits it depends on.',
    foci: [
      { x: 32, y: 188, w: 262, h: 63, cap: 'Robotic mobility needs terrain and illumination.' },
      { x: 590, y: 260, w: 260, h: 63, cap: 'No Earth data yet? It says so instead of guessing.' },
    ],
  },
  {
    n: 3, label: 'Requirements', title: 'Set the bands.', file: 'Setup.tsx', h: 1033,
    lead: 'Each trait gets a range and a priority. Hard limits and a field plan come next.',
    foci: [
      { x: 53, y: 296, w: 1334, h: 136, cap: 'Terrain and illumination: required or preferred.' },
      { x: 32, y: 474, w: 1376, h: 368, cap: 'Limits on travel and slope; months, days and team.' },
    ],
  },
  {
    n: 4, label: 'Sites', title: 'Find the places.', file: 'Sites.tsx', h: 1400,
    lead: 'Every land cell is checked trait by trait. Ties stay ties, and you compare up to three.',
    foci: [
      { x: 1225, y: 105, w: 183, h: 26, cap: '7,599 of 91,800 places fit the demo plan.' },
      { x: 53, y: 292, w: 1334, h: 314, cap: 'Gaps in their own units. No combined score.' },
      { x: 730, y: 792, w: 678, h: 520, cap: 'Pick three sites and read them on the globe.' },
    ],
  },
  {
    n: 5, label: 'Limitations', title: 'Name the limits.', file: 'Limitations.tsx', h: 900,
    lead: 'What no Earth site can reproduce, and which limits matter most for this mission.',
    foci: [
      { x: 32, y: 162, w: 678, h: 212, cap: 'Gravity, air pressure and radiation never match.' },
      { x: 32, y: 396, w: 1376, h: 244, cap: 'How much each limit matters for precision landing.' },
    ],
  },
  {
    n: 6, label: 'Logistics', title: 'Plan the trip.', file: 'Logistics.tsx', h: 1211,
    lead: 'Access, terrain, surface and permits for each site, month by month.',
    foci: [
      { x: 32, y: 162, w: 1376, h: 189, cap: 'Travel to a city, slope, bare ground, permits.' },
      { x: 32, y: 372, w: 1376, h: 158, cap: 'Go, caution, data gap or no-go for every month.' },
      { x: 32, y: 552, w: 1376, h: 468, cap: 'How the engine splits your field days.' },
    ],
  },
  {
    n: 7, label: 'Risks', title: 'Weigh the risks.', file: 'Risks.tsx', h: 977,
    lead: 'Environmental, personnel and impact risks, each with a mitigation and its evidence.',
    foci: [
      { x: 32, y: 228, w: 564, h: 330, cap: 'The team rates likelihood × severity.' },
      { x: 618, y: 228, w: 790, h: 556, cap: 'Data suggests a level; people make the call.' },
    ],
  },
  {
    n: 8, label: 'Lessons learned', title: 'Learn from the past.', file: 'Missions.tsx', h: 900,
    lead: 'Past analog missions near your plan: what worked, what to change, with sources.',
    foci: [
      { x: 32, y: 162, w: 564, h: 478, cap: 'Six missions, from Atacama to Devon Island.' },
      { x: 618, y: 162, w: 790, h: 342, cap: 'Each lesson links back to its source.' },
    ],
  },
];

const TEAM = [
  { name: 'Nicolas David Romero', url: 'https://www.linkedin.com/in/nicolasdavidromero/' },
  { name: 'Kashish M.', url: 'https://www.linkedin.com/in/kashish-m-79a11424a/' },
  { name: 'Cristian Kefallinos', url: 'https://www.linkedin.com/in/cristian-kefallinos-055a76276/' },
  { name: 'Andrew Koumoudjian', url: 'https://www.linkedin.com/in/andrewkoumoudjian/' },
  { name: 'Derek Gallagher', url: 'https://www.linkedin.com/in/derekgallagher1/' },
];

// Problem slide: one published comparison from the live app (Sites step, target
// Shackleton, Earth cell 48.3°N 114.1°E), plus the three permanent breakdowns.
const PROBLEM_ROWS = [
  { trait: 'Slope', v: 'match', note: 'gap 0.0003°' },
  { trait: 'Day/night range', v: 'miss', note: 'gap 79.8 K' },
  { trait: 'Cold temperature', v: 'miss', note: 'gap 206 K' },
  { trait: 'Surface material', v: 'unknown', note: 'no supported band' },
  { trait: 'Gravity', v: 'never', note: '0.17 g on the Moon' },
  { trait: 'Air pressure', v: 'never', note: 'vacuum' },
  { trait: 'Radiation', v: 'never', note: 'no magnetic field' },
];

// ---------- helpers ----------

const esc = (s) => String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
const pad = (n) => String(n).padStart(2, '0');
function rng(seed) {
  // mulberry32: seeded, so the markup is the same on every build
  return () => {
    seed |= 0; seed = (seed + 0x6d2b79f5) | 0;
    let t = Math.imul(seed ^ (seed >>> 15), 1 | seed);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}
const ext = (href, text, cls = 'link') => `<a class="${cls}" href="${esc(href)}" target="_blank" rel="noopener noreferrer">${text}</a>`;

// ---------- scenes ----------

const scenes = [];
function scene(id, label, inner, extraClass = '') {
  const start = scenes.length * SLOT;
  scenes.push({ id, label, start, duration: SLOT });
  return `
<div id="scene-${id}" class="scene-frame clip ${extraClass}" data-composition-id="${id}" data-label="${esc(label)}" data-start="${start}" data-duration="${SLOT}" data-width="1920" data-height="1080" data-track-index="1" data-hold>
${inner}
  <div class="foot" data-anim><span class="foot-brand"><i class="mark"></i>Analog Atlas</span>${ext(REPO, 'github.com/andrewkoumoudjian/cosmic-consultants', 'link foot-link')}</div>
</div>`;
}

const stars = (() => {
  const r = rng(7);
  let s = '';
  for (let i = 0; i < 140; i++) s += `<circle cx="${(r() * 1920).toFixed(1)}" cy="${(r() * 1080).toFixed(1)}" r="${(0.6 + r() * 1.4).toFixed(2)}" opacity="${(0.15 + r() * 0.5).toFixed(2)}"/>`;
  return `<svg class="stars" viewBox="0 0 1920 1080" aria-hidden="true">${s}</svg>`;
})();

const cover = scene('cover', 'Analog Atlas', `
  ${stars}
  <img class="planet planet-moon" data-glide src="assets/img/moon.webp" alt="The Moon, from the team's Figma illustration" width="560" height="560" />
  <img class="planet planet-mars" data-glide src="assets/img/mars.webp" alt="Mars, from the team's Figma illustration" width="560" height="560" />
  <div class="cover-copy">
    <p class="eyebrow" data-anim>NASA SPACE APPS CHALLENGE 2026 · COSMIC CONSULTANTS</p>
    <h1 class="t-hero" data-anim>Analog Atlas</h1>
    <p class="lead" data-anim>Find the places on Earth that best stand in for the Moon and Mars.</p>
    <p class="hint" data-anim>Use ← → to move, or let it play.</p>
  </div>`);

const verdictGlyph = { match: '●', miss: '◆', unknown: '○', never: '✕' };
const verdictWord = { match: 'Match', miss: 'Miss', unknown: 'Unknown', never: 'Never on Earth' };
const problem = scene('problem', 'The problem', `
  <div class="col-text">
    <p class="eyebrow" data-anim>THE PROBLEM</p>
    <h2 class="t-title" data-anim>Every mission is rehearsed on Earth first.</h2>
    <p class="lead" data-anim>But no place on Earth is the Moon or Mars. Teams need to know which parts match, where, and when.</p>
  </div>
  <div class="card table-card" data-glide>
    <p class="card-head">One Earth site vs. Shackleton crater <span class="muted">48.3°N 114.1°E</span></p>
    <ul class="verdicts">
      ${PROBLEM_ROWS.map((r, i) => `<li class="vrow v-${r.v}" data-row="${i}"><span class="vt">${r.trait}</span><span class="vg" aria-hidden="true">${verdictGlyph[r.v]}</span><span class="vw">${verdictWord[r.v]}</span><span class="vn">${r.note}</span></li>`).join('\n      ')}
    </ul>
    <p class="punch" data-punch>No single score. Every trait keeps its own verdict.</p>
  </div>`);

const hexes = (() => {
  const cols = 26, rows = 15, s = 26, r = rng(42);
  const total = cols * rows;
  const fit = Math.round((total * 7599) / 91800); // same share as the demo plan
  const chosen = new Set();
  while (chosen.size < fit) chosen.add(Math.floor(r() * total));
  const pts = (cx, cy) => Array.from({ length: 6 }, (_, k) => {
    const a = (Math.PI / 3) * k + Math.PI / 6;
    return `${(cx + s * 0.92 * Math.cos(a)).toFixed(1)},${(cy + s * 0.92 * Math.sin(a)).toFixed(1)}`;
  }).join(' ');
  let out = '';
  let i = 0;
  for (let y = 0; y < rows; y++) for (let x = 0; x < cols; x++, i++) {
    const cx = 30 + x * s * 1.732 + (y % 2 ? s * 0.866 : 0);
    const cy = 30 + y * s * 1.5;
    out += `<polygon class="hx${chosen.has(i) ? ' fit' : ''}" points="${pts(cx, cy)}"/>`;
  }
  return `<svg class="hexes" viewBox="0 0 1220 640" aria-hidden="true">${out}</svg>`;
})();

const approach = scene('approach', 'How it works', `
  <div class="col-text">
    <p class="eyebrow" data-anim>HOW IT WORKS</p>
    <h2 class="t-title" data-anim>Every place on Earth, trait by trait.</h2>
    <div class="counters" data-anim>
      <p><span class="num" data-count="91800">91,800</span><span class="unit">land cells, each ≈1,770 km²</span></p>
      <p class="fitline"><span class="num accent" data-count="7599">7,599</span><span class="unit">fit the demo plan</span></p>
    </div>
  </div>
  <div class="hexwrap" data-glide>${hexes}</div>
  <p class="lead small approach-note" data-anim>Sites that tie are never forced into a ranking. Each keeps a verdict per trait: match, miss with its gap, or unknown.</p>
  <p class="sources" data-anim>Earth data: Copernicus DEM · NASA MODIS · MERRA-2 · ESA CCI Permafrost · travel time (Weiss et al. 2018) · OurAirports · NASA EONET</p>`);

const FRAME_W = 1000, SCALE = FRAME_W / 1440, FRAME_H = 700;
const stepScenes = STEPS.map((s) => scene(`step-${s.n}`, `${pad(s.n)} ${s.label}`, `
  <div class="col-text col-step">
    <p class="eyebrow" data-anim>STEP ${pad(s.n)} / 08 · ${s.label.toUpperCase()}</p>
    <h2 class="t-title" data-anim>${s.title}</h2>
    <p class="lead" data-anim>${s.lead}</p>
    <ol class="caps">
      ${s.foci.map((f, i) => `<li class="cap" data-cap="${i}"><span class="capn">${i + 1}</span>${f.cap}</li>`).join('\n      ')}
    </ol>
    <p class="links" data-anim>${ext(`${DEMO_URL}#step=${s.n}`, 'Open this step live ↗')}${ext(`${SRC}/${s.file}`, 'Source on GitHub ↗')}</p>
  </div>
  <div class="browser" data-glide style="width:${FRAME_W}px">
    <div class="chrome" data-layout-ignore><i></i><i></i><i></i><span>cosmic-mission-ui.pages.dev · step ${s.n}</span></div>
    <div class="viewport" style="height:${Math.min(FRAME_H, Math.ceil(s.h * SCALE))}px">
      <div class="shot" data-shot data-h="${s.h}" style="width:1440px;height:${s.h}px">
        <img src="assets/shots/step-${s.n}.jpg" alt="Analog Atlas, step ${s.n}: ${esc(s.label)}" width="1440" height="${s.h}" />
        ${s.foci.map((f, i) => `<span class="ring" data-ring="${i}" data-y="${f.y}" style="left:${f.x - 6}px;top:${f.y - 6}px;width:${f.w + 12}px;height:${f.h + 12}px"></span>`).join('\n        ')}
      </div>
    </div>
  </div>`, 'step'));

const demo = scene('demo', 'Live demo', `
  <div class="col-text col-demo">
    <p class="eyebrow" data-anim>LIVE DEMO</p>
    <h2 class="t-title" data-anim>Try it.</h2>
    <p class="lead" data-anim>This is the real app, loaded with the demo plan: the Moon, precision landing, three sites compared.</p>
    <p class="buttons" data-anim>${ext(`${DEMO_URL}#step=4`, 'Open the demo plan ↗', 'btn primary')}${ext(APP_URL, 'Start your own plan ↗', 'btn')}</p>
    <p class="note" data-anim>Click around inside the window. The deck waits here.</p>
  </div>
  <div class="browser demo-frame" data-glide>
    <div class="chrome" data-layout-ignore><i></i><i></i><i></i><span>cosmic-mission-ui.pages.dev · demo plan</span></div>
    <div class="viewport demo-viewport">
      <div class="demo-wait">Loading the live app…</div>
      <iframe id="demo-app" title="Analog Atlas, live demo" data-src="${esc(DEMO_URL)}#step=4" loading="lazy"></iframe>
    </div>
  </div>`, 'demo');

const initials = (n) => n.split(/\s+/).filter((w) => /^[A-Z]/.test(w)).slice(0, 2).map((w) => w[0]).join('');
const team = scene('team', 'The team', `
  <div class="team-head">
    <p class="eyebrow" data-anim>THE TEAM</p>
    <h2 class="t-title" data-anim>Cosmic Consultants</h2>
    <p class="lead" data-anim>Built for NASA Space Apps 2026: identify Earth locations that analog permanent Moon base sites and Mars.</p>
  </div>
  <ul class="people">
    ${TEAM.map((p) => `<li class="person" data-person><span class="avatar" aria-hidden="true">${initials(p.name)}</span><span class="pname">${p.name}</span>${ext(p.url, 'LinkedIn ↗', 'link plink')}</li>`).join('\n    ')}
  </ul>
  <p class="buttons team-links" data-anim>${ext(REPO, 'Code on GitHub ↗', 'btn primary')}${ext(APP_URL, 'Open Analog Atlas ↗', 'btn')}</p>`);

const ALL = [cover, problem, approach, ...stepScenes, demo, team].join('\n');
const TOTAL = scenes.length * SLOT;

// ---------- slideshow island (shared by both files) ----------

const notes = {
  cover: 'Analog Atlas: find places on Earth that stand in for the Moon and Mars.',
  problem: 'One real comparison from the app. Some traits match, some miss with a gap, one is unknown, and three never match on Earth.',
  approach: '91,800 H3 cells (res 4). The demo plan (Moon, precision landing) leaves 7,599 that fit; ties are not ranked.',
  demo: 'The embedded app is live. Click inside it; arrow keys still move the deck once you click outside.',
  team: 'LinkedIn links for each of us; the code is public on GitHub.',
};
const island = JSON.stringify(
  {
    slides: scenes.map((s) => ({
      sceneId: s.id,
      notes: notes[s.id] ?? `Step ${s.id.split('-')[1]}: ${STEPS[Number(s.id.split('-')[1]) - 1].lead}`,
    })),
  },
  null,
  2,
);

// Dwell per slide for auto-play (seconds). Step slides wait for every highlight.
const dwell = Object.fromEntries(scenes.map((s) => {
  if (s.id.startsWith('step-')) return [s.id, 1.4 + STEPS[Number(s.id.split('-')[1]) - 1].foci.length * 2.7 + 2.4];
  return [s.id, { cover: 6, problem: 9, approach: 10.5, demo: 0, team: 0 }[s.id]];
}));

// ---------- composition/index.html ----------

const composition = `<!doctype html>
<!-- GENERATED by scripts/build-deck.mjs. Edit the script, not this file. -->
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=1920, height=1080" />
    <title>Analog Atlas · composition</title>
    <script src="https://cdn.jsdelivr.net/npm/gsap@3.15.0/dist/gsap.min.js"></script>
    <link rel="stylesheet" href="deck.css" />
  </head>
  <body>
    <script type="application/hyperframes-slideshow+json">
${island}
    </script>
    <div id="root" data-composition-id="root" data-start="0" data-duration="${TOTAL}" data-width="1920" data-height="1080">
${ALL}
    </div>

    <!-- Root timeline: establishes the seekable range the player drives. -->
    <script>
      (function () {
        window.__timelines = window.__timelines || {};
        var tl = gsap.timeline({ paused: true });
        tl.to({}, { duration: ${TOTAL} });
        window.__timelines["root"] = tl;
      })();
    </script>
    <script>window.__DECK = ${JSON.stringify({ scenes, total: TOTAL, dwell, scale: SCALE, frameH: FRAME_H })};</script>
    <script src="deck.js"></script>
  </body>
</html>
`;

// ---------- index.html (the website) ----------

const wrapper = `<!doctype html>
<!-- GENERATED by scripts/build-deck.mjs. Edit the script, not this file. -->
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>Analog Atlas · Cosmic Consultants</title>
    <meta name="description" content="Analog Atlas finds places on Earth that stand in for the Moon and Mars, trait by trait. NASA Space Apps 2026, Cosmic Consultants." />
    <link rel="icon" href="data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 16 16'%3E%3Ccircle cx='7' cy='8' r='6' fill='%23c4c9d2'/%3E%3Ccircle cx='12.5' cy='12' r='2.5' fill='%23e0654f'/%3E%3C/svg%3E" />
    <script src="https://cdn.jsdelivr.net/npm/@hyperframes/player@0.9.55/dist/hyperframes-player.global.js"></script>
    <script src="https://cdn.jsdelivr.net/npm/@hyperframes/player@0.9.55/dist/slideshow/hyperframes-slideshow.global.js"></script>
    <style>
      *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
      html, body { width: 100%; height: 100%; overflow: hidden; background: #0c0d10; color: #eceef2; font: 500 13px/1 system-ui, sans-serif; }
      #autoplay {
        position: fixed; top: 14px; right: 14px; z-index: 20;
        display: inline-flex; align-items: center; gap: 8px; height: 34px; padding: 0 14px;
        border: 1px solid #3a3e47; border-radius: 999px; background: #131519; color: #eceef2; cursor: pointer;
      }
      #autoplay:hover { border-color: #a5b4fc; }
      #autoplay:focus-visible { outline: 2px solid #a5b4fc; outline-offset: 2px; }
      #autoplay .bar { width: 46px; height: 3px; background: #272a31; border-radius: 2px; overflow: hidden; }
      #autoplay .bar i { display: block; height: 100%; width: 0; background: #a5b4fc; }
      noscript p { padding: 24px; }
    </style>
  </head>
  <body>
    <hyperframes-slideshow tabindex="0" style="display: block; position: relative; width: 100vw; height: 100vh">
      <hyperframes-player interactive style="position: absolute; inset: 0" src="composition/"></hyperframes-player>
      <script type="application/hyperframes-slideshow+json">
${island}
      </script>
    </hyperframes-slideshow>
    <button id="autoplay" type="button" aria-pressed="true"><span id="autoplay-label">Pause</span><span class="bar"><i id="autoplay-bar"></i></span></button>
    <noscript><p>This site is a slide deck and needs JavaScript. The app itself: <a href="${APP_URL}">${APP_URL}</a></p></noscript>
    <script>
      // Auto-play: advance like the → key after each slide's dwell. The composition
      // reports the active slide; manual navigation restarts the timer.
      (function () {
        var DWELL = ${JSON.stringify(dwell)};
        var ORDER = ${JSON.stringify(scenes.map((s) => s.id))};
        var btn = document.getElementById('autoplay');
        var label = document.getElementById('autoplay-label');
        var bar = document.getElementById('autoplay-bar');
        var reduce = matchMedia('(prefers-reduced-motion: reduce)').matches;
        var playing = !reduce, current = ORDER[0], startedAt = 0, raf = 0, synthetic = false;
        function render() {
          btn.setAttribute('aria-pressed', String(playing));
          label.textContent = playing ? 'Pause' : 'Play';
          btn.title = playing ? 'Pause auto-play' : 'Play the deck';
        }
        function next() {
          synthetic = true;
          window.dispatchEvent(new KeyboardEvent('keydown', { key: 'ArrowRight', code: 'ArrowRight', bubbles: true }));
          synthetic = false;
        }
        function tick(now) {
          raf = requestAnimationFrame(tick);
          var d = DWELL[current] || 0;
          if (!playing || !d) { bar.style.width = '0'; return; }
          var p = Math.min(1, (now - startedAt) / (d * 1000));
          bar.style.width = (p * 100).toFixed(1) + '%';
          if (p >= 1) { startedAt = now; next(); }
        }
        window.addEventListener('message', function (e) {
          if (!e.data || e.data.source !== 'analog-atlas-deck' || e.data.type !== 'slide') return;
          current = e.data.id;
          startedAt = performance.now();
        });
        window.addEventListener('keydown', function (e) { if (!synthetic && /Arrow|Space|PageDown|PageUp/.test(e.key + e.code)) startedAt = performance.now(); });
        btn.addEventListener('click', function () {
          playing = !playing;
          if (playing && !DWELL[current]) { next(); }
          startedAt = performance.now();
          render();
          document.querySelector('hyperframes-slideshow').focus();
        });
        render();
        startedAt = performance.now();
        raf = requestAnimationFrame(tick);
      })();
    </script>
  </body>
</html>
`;

const root = new URL('../', import.meta.url);
writeFileSync(new URL('composition/index.html', root), composition);
writeFileSync(new URL('index.html', root), wrapper);
console.log(`wrote ${scenes.length} slides, ${TOTAL}s timeline`);
