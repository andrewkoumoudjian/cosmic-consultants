// Copies only the website (index.html + composition/) into dist/ for a
// direct upload, e.g. Cloudflare Pages:
//   npm run dist && npx wrangler pages deploy dist --project-name analog-atlas-showcase --branch main
import { cpSync, rmSync, mkdirSync } from 'node:fs';

const root = new URL('../', import.meta.url);
const dist = new URL('dist/', root);
rmSync(dist, { recursive: true, force: true });
mkdirSync(dist, { recursive: true });
cpSync(new URL('index.html', root), new URL('index.html', dist));
cpSync(new URL('composition/', root), new URL('composition/', dist), {
  recursive: true,
  filter: (src) => !src.includes('.hyperframes'),
});
console.log('dist/ ready');
