// Lists every placeholder the app registers (PENDING / BLOCKED in src/data),
// with what it waits on. `npm run pending`, or `npm run pending -- --md`.
// Node >= 22.18 / 24 strips the TypeScript types on import.
import { allPlaceholders } from '../src/data/pending.ts';
import '../src/data/catalog.ts';
import '../src/data/placeholders/sites.ts';
import '../src/data/placeholders/limitations.ts';
import '../src/data/placeholders/logistics.ts';
import '../src/data/placeholders/risks.ts';

const rows = allPlaceholders().map((p) => ({ kind: p.kind.toUpperCase(), id: p.id, note: p.kind === 'pending' ? p.awaits : p.reason }));
if (process.argv.includes('--md')) {
  console.log('| Kind | Id | Waits on / reason |\n|---|---|---|');
  for (const r of rows) console.log(`| ${r.kind} | \`${r.id}\` | ${r.note.replace(/\|/g, '\\|')} |`);
} else {
  for (const r of rows) console.log(`${r.kind.padEnd(7)} ${r.id}\n        ${r.note}\n`);
}
console.log(`${rows.length} placeholders (${rows.filter((r) => r.kind === 'BLOCKED').length} blocked). Find one in code: grep -rn "<id>" src`);
