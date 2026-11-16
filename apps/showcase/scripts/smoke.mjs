// Drives the website like a visitor: loads index.html, steps through every
// slide with the arrow key, screenshots each one after its entrance, checks
// the links, auto-play and console errors.
//   python -m http.server 4173   (or any static server, in apps/showcase)
//   node scripts/smoke.mjs [outDir]
import { existsSync, mkdirSync, readdirSync } from 'node:fs';
import { homedir } from 'node:os';
import { join } from 'node:path';
import { chromium } from 'playwright';

const base = process.env.BASE_URL ?? 'http://127.0.0.1:4173/';
const out = process.argv[2] ?? 'out';
mkdirSync(out, { recursive: true });

function findChromium() {
  if (process.env.CHROMIUM_PATH) return process.env.CHROMIUM_PATH;
  const root = join(process.env.LOCALAPPDATA ?? join(homedir(), '.cache'), 'ms-playwright');
  if (!existsSync(root)) return undefined;
  for (const dir of readdirSync(root).filter((d) => d.startsWith('chromium-')).sort().reverse())
    for (const rel of ['chrome-win64/chrome.exe', 'chrome-win/chrome.exe', 'chrome-linux/chrome', 'chrome-linux64/chrome']) {
      const p = join(root, dir, rel);
      if (existsSync(p)) return p;
    }
}

const ok = (c, m) => { console.log(`${c ? 'PASS' : 'FAIL'} ${m}`); if (!c) process.exitCode = 1; };
const browser = await chromium.launch({ executablePath: findChromium(), args: ['--use-angle=swiftshader', '--enable-unsafe-swiftshader'] });
const page = await browser.newPage({ viewport: { width: 1600, height: 900 } });
const errors = [];
page.on('pageerror', (e) => errors.push(String(e)));
page.on('console', (m) => m.type() === 'error' && errors.push(m.text()));

await page.goto(base);
await page.waitForTimeout(2500);
const deck = () => page.frames().find((f) => f.url().includes('composition/index.html'));
ok(!!deck(), 'composition loads inside the player');

// Auto-play is on by default: the cover advances by itself.
await page.waitForTimeout(6800);
const activeId = async () => deck().evaluate(() => [...document.querySelectorAll('.scene-frame')].find((s) => s.style.visibility === 'visible')?.dataset.compositionId);
ok((await activeId()) === 'problem', `auto-play advanced from the cover (now: ${await activeId()})`);
await page.click('#autoplay');
ok((await page.getAttribute('#autoplay', 'aria-pressed')) === 'false', 'pause button stops auto-play');

// Back to the start, then step through manually.
await page.locator('hyperframes-slideshow').focus();
await page.keyboard.press('ArrowLeft');
await page.waitForTimeout(800);
const ids = await deck().evaluate(() => window.__DECK.scenes.map((s) => s.id));
for (let i = 0; i < ids.length; i++) {
  if (i > 0) {
    await page.keyboard.press('ArrowRight');
  }
  const wait = ids[i].startsWith('step-') ? 7600 : ids[i] === 'demo' ? 9000 : 4200;
  await page.waitForTimeout(wait);
  const now = await activeId();
  ok(now === ids[i], `slide ${i + 1}/${ids.length} shows ${ids[i]} (saw ${now})`);
  await page.screenshot({ path: join(out, `${String(i + 1).padStart(2, '0')}-${ids[i]}.png`) });
}

const links = await deck().evaluate(() => [...document.querySelectorAll('a[href]')].map((a) => a.href));
ok(links.filter((h) => h.includes('linkedin.com/in/')).length === 5, 'five LinkedIn links');
ok(links.some((h) => h === 'https://github.com/andrewkoumoudjian/cosmic-consultants'), 'GitHub repo link');
ok(links.filter((h) => h.includes('/apps/mission-ui/src/steps/')).length === 8, 'eight source links, one per step');
ok(links.filter((h) => h.includes('cosmic-mission-ui.pages.dev')).length >= 10, 'live app and per-step demo links');
ok(await deck().evaluate(() => [...document.querySelectorAll('a[target=_blank]')].every((a) => a.rel.includes('noopener'))), 'external links open safely in a new tab');
ok(!!(await deck().evaluate(() => document.getElementById('demo-app').getAttribute('src'))), 'demo iframe loads the live app once its slide opens');

await browser.close();
const real = errors.filter((e) => !/favicon|ERR_BLOCKED_BY_CLIENT/.test(e));
ok(real.length === 0, `no console errors${real.length ? ':\n' + real.join('\n') : ''}`);
