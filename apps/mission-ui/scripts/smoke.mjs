// Walks all eight Analog Atlas steps against a running preview and saves screenshots.
// Usage: BASE_URL=http://localhost:5181/ CHROMIUM_PATH=/usr/bin/chromium node scripts/smoke.mjs <out-dir> [width]
import { chromium } from 'playwright';
import { mkdirSync } from 'node:fs';

const out = process.argv[2] ?? 'shots';
const width = Number(process.argv[3] ?? 1440);
mkdirSync(out, { recursive: true });
const base = process.env.BASE_URL ?? 'http://localhost:5181/';
const b = await chromium.launch({ executablePath: process.env.CHROMIUM_PATH || undefined, args: ['--use-angle=swiftshader', '--enable-unsafe-swiftshader', '--enable-webgl', '--ignore-gpu-blocklist'] });
const p = await b.newPage({ viewport: { width, height: 1000 } });
// Headless Chromium renders the WebGL globe on the CPU (about 1 frame/s), so clicks go through the DOM and waits are long.
p.setDefaultTimeout(120000);
const tap = sel => p.locator(sel).first().evaluate(el => el.click());
const errors = [];
p.on('pageerror', e => errors.push(String(e)));
p.on('console', m => m.type() === 'error' && errors.push(m.text()));
let fails = 0;
const ok = (cond, msg) => { if (!cond) fails++; console.log(`${cond ? 'PASS' : 'FAIL'} ${msg}`); };
const shot = async name => { await p.waitForTimeout(900); await p.screenshot({ path: `${out}/${name}-${width}.png`, fullPage: true }); };
const overflow = async () => p.evaluate(() => document.documentElement.scrollWidth - innerWidth);

await p.goto(base);
await p.waitForSelector('.world', { timeout: 120000 });
ok((await p.textContent('.brand-name')) === 'Analog Atlas', 'brand reads Analog Atlas');
const fonts = await p.evaluate(() => ({ h1: getComputedStyle(document.querySelector('h1')).fontFamily, body: getComputedStyle(document.querySelector('.purpose')).fontFamily }));
ok(fonts.h1.includes('Geist Serif') && fonts.body.includes('Geist Sans'), `fonts: title ${fonts.h1.split(',')[0]}, body ${fonts.body.split(',')[0]}`);
await shot('1-destination');
await p.click('.world[data-world="mars"]');
ok((await p.getAttribute('.world[data-world="mars"]', 'aria-checked')) === 'true', 'Mars selectable');
await p.click('.world[data-world="moon"]');
await p.click('text=Continue →');
await p.waitForSelector('.cat');
await shot('2-test');
// first enabled category
await p.locator('.cat:not([disabled])').first().click();
await p.click('text=Continue →');
await p.waitForSelector('.trait');
ok((await p.locator('.trait').count()) > 0, `requirements: ${await p.locator('.trait').count()} traits`);
await shot('3-requirements');
await p.click('text=Find sites →');
await p.waitForSelector('.site-row', { timeout: 120000 });
const matches = await p.textContent('.kpi .v');
ok(Number(matches.replace(/,/g, '')) > 0, `sites: ${matches} in play`);
// pick three from the list
for (let n = 0; n < 3; n++) { await p.locator('.site-row .pick:not([disabled])').filter({ hasText: '+' }).first().evaluate(el => el.click()); await p.waitForFunction(k => document.querySelectorAll('.site-row .site-badge').length === k, n + 1); }
ok((await p.locator('.site-row .site-badge').count()) === 3, 'three sites picked (A, B, C)');
await p.locator('.site-row').nth(1).evaluate(el => el.click());
await p.waitForSelector('.pinned');
await p.waitForSelector('svg.leader', { state: 'attached' }).catch(() => {});
ok(await p.locator('.pinned .season > span').count() === 12, 'pinned card shows a 12-month season strip');
ok(await p.locator('svg.leader').count() === 1, 'leader line from the cell to the card');
ok(await p.locator('.radar-svg, .fit').count() >= 1, 'fingerprint / band strips render');
ok((await overflow()) <= 0, `no horizontal page scroll (${await overflow()} px)`);
await shot('4-sites');
await tap('text=See limitations →');
await p.waitForSelector('table');
ok(await p.locator('tr.req').count() >= 1, 'limitations: required rows marked');
await shot('5-limitations');
await tap('text=Logistics →');
await p.waitForSelector('text=Permits & local laws');
ok(await p.locator('.no-source').count() >= 3, 'logistics: no-source cards are explicit');
await shot('6-logistics');
await tap('text=Risks →');
await p.waitForSelector('.matrix');
ok(await p.locator('.mchip').count() === 0, 'risk matrix starts empty (nothing rated for you)');
await p.locator('#risk-medical .seg').first().locator('button', { hasText: 'Possible' }).evaluate(el => el.click());
await p.locator('#risk-medical .seg').nth(1).locator('button', { hasText: 'High' }).evaluate(el => el.click());
ok(await p.locator('.mchip').count() === 1, 'rating a risk places it on the matrix');
await shot('7-risks');
await tap('text=Past missions →');
await p.waitForSelector('text=Analog mission spreadsheet');
ok(await p.locator('tbody tr.clickable').count() >= 6, `past missions: ${await p.locator('tbody tr.clickable').count()} campaigns`);
await shot('8-missions');
// the link restores the plan
const url = p.url();
const p2 = await b.newPage({ viewport: { width, height: 1000 } });
await p2.goto(url);
await p2.waitForSelector('text=Analog mission spreadsheet', { timeout: 120000 });
ok(true, 'share link reopens on step 8');
await p2.close();
ok(errors.length === 0, `no console errors${errors.length ? `: ${errors.slice(0, 3).join(' | ')}` : ''}`);
await b.close();
console.log(fails ? `${fails} FAILED` : 'ALL PASS');
process.exit(fails ? 1 : 0);
