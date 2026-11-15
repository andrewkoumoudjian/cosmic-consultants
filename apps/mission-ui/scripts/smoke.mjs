// Interaction smoke test against the preview server.
import { chromium } from 'playwright';
const out = process.argv[2];
const base = process.env.BASE_URL ?? 'http://localhost:5181/';
const b = await chromium.launch({ executablePath: process.env.CHROMIUM_PATH || undefined, args: ['--use-angle=swiftshader', '--enable-unsafe-swiftshader'] });
const p = await b.newPage({ viewport: { width: 1440, height: 1000 } });
const errors = [];
p.on('pageerror', (e) => errors.push(String(e)));
p.on('console', (m) => m.type() === 'error' && errors.push(m.text()));
const ok = (cond, msg) => console.log(`${cond ? 'PASS' : 'FAIL'} ${msg}`);

await p.goto(base);
await p.evaluate(() => localStorage.clear());
await p.goto('about:blank');
await p.goto(base + '#/location');
await p.waitForTimeout(800);
await p.click('text=Mars');
await p.click('text=Continue →');
await p.waitForTimeout(400);
ok((await p.textContent('.context-row')).includes('Mars / Single selection'), 'world carries into step 2');
ok(await p.isDisabled('.footer .btn--primary'), 'continue disabled with no category');
await p.click('text=Geological exploration & sampling');
await p.click('text=Continue →');
await p.waitForTimeout(400);
ok((await p.locator('.req-row').count()) === 5, 'geological defaults: 5 metric rows');
ok(await p.isDisabled('text=Create mission'), 'create mission disabled until targets set');
// picker: add one, remove one
await p.click('text=+ Choose metrics');
await p.waitForTimeout(300);
await p.click('.picker__row:has-text("Carbonate indicators")');
await p.click('.picker__row:has-text("Lithology class")');
await p.click('.picker .btn--primary');
await p.waitForTimeout(400);
const rows = await p.locator('.req-row__metric > span:first-child').allTextContents();
ok(rows.length === 5 && rows.some((r) => r.includes('Carbonate')) && !rows.some((r) => r.includes('Lithology')), `picker add/remove (${rows.join(' | ')})`);
// condition menu
await p.locator('.req-row').nth(0).locator('.field--button').first().click();
await p.click('.menu >> text=Greater than');
ok((await p.locator('.req-row').nth(0).locator('.field--button').first().textContent()).includes('Greater than'), 'condition menu sets value');
// priority + targets
await p.locator('.req-row').nth(1).locator('.field--button').nth(1).click();
await p.click('.menu >> text=Critical');
const inputs = p.locator('.field--input');
for (let i = 0; i < (await inputs.count()); i++) await inputs.nth(i).fill(i === 0 ? 'abc' : '0.2');
ok(await p.isDisabled('text=Create mission'), 'non-numeric target blocks create');
await inputs.nth(0).fill('0.3');
ok(!(await p.isDisabled('text=Create mission')), 'all targets set enables create');
// row menu remove
await p.locator('.row-menu__trigger').last().click();
await p.click('text=Remove metric');
await p.waitForTimeout(400);
ok((await p.locator('.req-row').count()) === 4, 'row action removes metric');
await p.click('text=Create mission');
await p.waitForTimeout(700);
ok(p.url().endsWith('#/sites'), 'navigates to site finder');
ok((await p.textContent('.header')).includes('Mars / Geological exploration & sampling / Site finder'), 'breadcrumb reflects mission');
// remove a site and restore
await p.click('[aria-label="Remove Mauna Kea"]');
await p.waitForTimeout(300);
ok((await p.textContent('.footer')).includes('8 sites in play · 4 in chart'), 'remove site updates counts');
await p.click('[aria-label="Add Bockfjorden to chart"]');
await p.waitForTimeout(300);
ok((await p.locator('.legend__row').count()) === 5, 'add site to chart');
await p.click('.site-row.is-removed >> nth=0 >> text=Restore');
await p.waitForTimeout(300);
ok((await p.textContent('.footer')).includes('9 sites in play'), 'restore site');
await p.click('text=Elevation');
ok(await p.isVisible('.sitemap__overlay .pending-tag'), 'pending map layer shows placeholder');
await p.screenshot({ path: `${out}/i-sites-mars.png` });
await p.click('text=Compare limitations →');
await p.waitForTimeout(700);
ok((await p.textContent('.matrix')).includes('MARTIAN TARGET'), 'target column follows world');
ok((await p.textContent('.limits')).includes('0.38 g on Mars'), 'gravity text follows world');
await p.screenshot({ path: `${out}/i-limits-mars.png`, fullPage: true });
await p.click('text=Compare logistics →');
await p.waitForTimeout(700);
await p.click('.tab:has-text("Atacama")');
await p.waitForTimeout(400);
ok(await p.isVisible('text=No field plan for Atacama Desert yet.'), 'empty state for site without plan');
await p.click('.tab:has-text("Haughton")');
await p.click('text=Continue →');
await p.waitForTimeout(700);
await p.hover('.rtag >> text=R4');
ok((await p.locator('.register__row.is-hover').count()) === 1, 'hovering matrix tag highlights register row');
await p.check('.toggle input');
ok(await p.isVisible('.app.show-pending'), 'highlight placeholders toggle');
// save draft
await p.click('text=Back');
await p.waitForTimeout(300);
await p.goto(base + '#/metrics');
await p.waitForTimeout(500);
await p.click('text=Save draft');
await p.waitForTimeout(300);
ok(await p.isVisible('.toast >> text=Draft saved'), 'save draft dialog');
await p.keyboard.press('Escape');

// phone width: no horizontal page scroll
const m = await b.newPage({ viewport: { width: 390, height: 844 } });
for (const r of ['location', 'category', 'metrics', 'sites', 'limitations', 'logistics', 'risks']) {
  await m.goto(`${base}#/${r}`);
  await m.waitForTimeout(600);
  const over = await m.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
  ok(over <= 0, `phone width ${r}: horizontal overflow ${over}px`);
  if (r === 'location' || r === 'sites') await m.screenshot({ path: `${out}/m-${r}.png` });
}
await b.close();
console.log(errors.length ? 'ERRORS:\n' + errors.join('\n') : 'no console errors');
