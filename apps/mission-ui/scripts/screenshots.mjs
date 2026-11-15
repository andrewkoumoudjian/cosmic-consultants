// Screenshots every screen at the Figma frame size (1440 wide) for a visual
// check against the design. Needs a running server:
//   npm run build && npx vite preview   (then)   npm run shots [-- outDir]
// Uses the Playwright Chromium on this machine; set CHROMIUM_PATH to override.
import { existsSync, mkdirSync, readdirSync } from 'node:fs';
import { homedir } from 'node:os';
import { join } from 'node:path';
import { chromium } from 'playwright';

const base = process.env.BASE_URL ?? 'http://localhost:5181/';
const out = process.argv[2] ?? 'screenshots';
mkdirSync(out, { recursive: true });

function findChromium() {
  if (process.env.CHROMIUM_PATH) return process.env.CHROMIUM_PATH;
  const root = join(process.env.LOCALAPPDATA ?? join(homedir(), '.cache'), 'ms-playwright');
  if (!existsSync(root)) return undefined;
  for (const dir of readdirSync(root).filter((d) => d.startsWith('chromium-')).sort().reverse()) {
    for (const rel of ['chrome-win64/chrome.exe', 'chrome-win/chrome.exe', 'chrome-linux/chrome', 'chrome-linux64/chrome']) {
      const p = join(root, dir, rel);
      if (existsSync(p)) return p;
    }
  }
  return undefined;
}

const draft = {
  world: process.env.WORLD ?? 'moon',
  category: 'robotic-mobility',
  requirements: [
    { metric: 'slope-100m', condition: 'at-most', target: '15', priority: 'high' },
    { metric: 'mean-traverse-slope', condition: 'at-most', target: '10', priority: 'high' },
    { metric: 'elevation-relief', condition: 'at-most', target: '50', priority: 'medium' },
    { metric: 'albedo', condition: 'equals', target: '0.12', priority: 'medium' },
    { metric: 'sunlit-fraction', condition: 'at-least', target: '70', priority: 'high' },
  ],
  removed: { 'wadi-rum': 'sand too fine for traction tests' },
  inChart: ['mauna-kea', 'haughton-crater', 'atacama', 'lanzarote', 'mount-etna'],
};
const emptyTargets = { ...draft, requirements: draft.requirements.map((r) => ({ ...r, target: '' })) };

const shots = [
  { name: '01-location', route: 'location', state: null },
  { name: '02-category', route: 'category', state: draft },
  { name: '03-metrics', route: 'metrics', state: emptyTargets },
  { name: '03b-picker', route: 'metrics', state: emptyTargets, click: 'text=+ Choose metrics' },
  { name: '03c-condition-menu', route: 'metrics', state: emptyTargets, click: '.req-row >> nth=0 >> .field--button >> nth=0' },
  { name: '04-sites', route: 'sites', state: draft },
  { name: '05-limitations', route: 'limitations', state: draft, full: true },
  { name: '06-logistics', route: 'logistics', state: draft, full: true },
  { name: '07-risks', route: 'risks', state: draft, full: true },
];

const browser = await chromium.launch({ executablePath: findChromium(), args: ['--use-angle=swiftshader', '--enable-unsafe-swiftshader'] });
const page = await browser.newPage({ viewport: { width: 1440, height: 1000 }, deviceScaleFactor: 1 });
const errors = [];
page.on('pageerror', (e) => errors.push(String(e)));
page.on('console', (m) => m.type() === 'error' && errors.push(m.text()));

for (const s of shots) {
  await page.goto(base);
  await page.evaluate((st) => {
    if (st) localStorage.setItem('cosmic-mission-ui:draft', JSON.stringify(st));
    else localStorage.removeItem('cosmic-mission-ui:draft');
  }, s.state);
  await page.goto('about:blank');
  await page.goto(`${base}#/${s.route}`);
  await page.waitForTimeout(1400);
  if (s.click) {
    await page.click(s.click);
    await page.waitForTimeout(500);
  }
  await page.screenshot({ path: join(out, `${s.name}.png`), fullPage: !!s.full });
  console.log('shot', s.name);
}
await browser.close();
if (errors.length) {
  console.error('Page errors:\n' + errors.join('\n'));
  process.exitCode = 1;
}
