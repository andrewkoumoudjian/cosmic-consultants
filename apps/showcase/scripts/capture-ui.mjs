// Captures every step of the live Analog Atlas app for the deck, from the demo
// plan URL (the app restores the plan from the query and the step from #step=N).
//   npm run capture            (writes composition/assets/shots/step-N.jpg)
import { mkdirSync, existsSync, readdirSync, writeFileSync } from 'node:fs';
import { homedir } from 'node:os';
import { join } from 'node:path';
import { chromium } from 'playwright';
import { DEMO_URL } from './demo-url.mjs';

const out = new URL('../composition/assets/shots/', import.meta.url).pathname.replace(/^\/([A-Za-z]:)/, '$1');
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

const browser = await chromium.launch({ executablePath: findChromium(), args: ['--use-angle=swiftshader', '--enable-unsafe-swiftshader'] });
const sizes = {};
for (let step = 1; step <= 8; step++) {
  const page = await browser.newPage({ viewport: { width: 1440, height: 900 }, deviceScaleFactor: 1.25 });
  await page.goto(`${DEMO_URL}#step=${step}`);
  await page.waitForSelector('main h1', { timeout: 60000 });
  await page.waitForTimeout(4500); // data load + globe draw
  await page.evaluate(() => window.scrollTo(0, 0));
  const h = await page.evaluate(() => Math.min(document.documentElement.scrollHeight, 3600));
  await page.screenshot({ path: join(out, `step-${step}.jpg`), type: 'jpeg', quality: 86, clip: { x: 0, y: 0, width: 1440, height: h }, fullPage: true });
  sizes[step] = { width: 1440, height: h };
  console.log('step', step, h);
  await page.close();
}
await browser.close();
writeFileSync(join(out, 'sizes.json'), JSON.stringify(sizes, null, 2));
