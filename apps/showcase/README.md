# Analog Atlas showcase deck

An animated website that plays like slides: what problem Analog Atlas solves, each
of its eight steps with real screenshots, a live demo of the app, and the team.
Built with [HyperFrames](https://hyperframes.heygen.com/) (`<hyperframes-slideshow>`
around `<hyperframes-player>`), GSAP for motion. Static files only.

| # | Slide | What it shows |
|---|---|---|
| 1 | Cover | Analog Atlas, Moon and Mars (the team's Figma illustrations) |
| 2 | The problem | One real comparison from the app: match, miss with its gap, unknown, and the three traits Earth never matches |
| 3 | How it works | 91,800 land cells; 7,599 fit the demo plan; no single score |
| 4–11 | Steps 1–8 | Destination, Objectives, Requirements, Sites, Limitations, Logistics, Risks, Lessons learned. The camera pans each real screenshot to its key parts; each step links to the live step and its source file |
| 12 | Live demo | The real app in a window, loaded with the demo plan, clickable |
| 13 | The team | Cosmic Consultants, with LinkedIn links, GitHub and the app |

It auto-plays (Pause/Play top right; it waits on the demo and team slides).
Arrow keys, swipe and the bottom-right capsule move by hand; **P** opens presenter
mode with speaker notes.

## Run it

Any static server, from this folder:

```bash
cd apps/showcase
python -m http.server 4173      # or: npm run dev
# open http://127.0.0.1:4173/
```

## Deploy

**Cloudflare Pages (direct upload, no GitHub access needed):**

```bash
cd apps/showcase
npx wrangler@4 login                 # once, opens the browser
npm run deploy:cloudflare            # copies the site into dist/ and uploads it
```

The first run creates the `analog-atlas-showcase` project and prints
`https://analog-atlas-showcase.pages.dev`. Run the same command to update it.

It's static: any host works if you upload `dist/` (`npm run dist`) or this folder as-is. `vercel.json` tells Vercel there's
nothing to install or build, and `.vercelignore` leaves out the dev-only files.

**Vercel, from your machine:**

```bash
cd apps/showcase
npx vercel@latest login          # once
npx vercel@latest                # preview deploy; answer "./" for the directory, no to "modify settings"
npx vercel@latest --prod         # production URL
```

**Vercel, from GitHub:** New Project → import `andrewkoumoudjian/cosmic-consultants`
→ Root Directory `apps/showcase` → Framework Preset `Other` → Deploy.

Cloudflare Pages works the same way: `npx wrangler pages deploy . --project-name analog-atlas-showcase`.

## Edit it

Slides are generated: edit `scripts/build-deck.mjs` (copy, steps, focus boxes,
team), then:

```bash
npm run build      # writes composition/index.html and index.html (the slideshow island is shared)
npm run check      # HyperFrames lint/layout/contrast gate
npm run smoke      # with the server running: steps every slide, checks links, auto-play, console errors
npm run capture    # re-shoots the eight app screenshots from the live demo plan
```

| Path | What |
|---|---|
| `index.html` | The website: player + slideshow + auto-play (generated) |
| `composition/index.html` | The HyperFrames composition, one scene per slide (generated) |
| `composition/deck.js` | Shows one scene per playhead time and runs its motion |
| `composition/deck.css` | Look, from the Analog Atlas tokens |
| `composition/assets/shots/` | Screenshots of the live app, `npm run capture` |
| `scripts/demo-url.mjs` | The demo plan URL used everywhere |

Motion follows one direction: forward moves travel left, Back reverses it, one
slide visible at a time. Inside a slide the frame keeps gaining information
(camera pans, rings, captions). `prefers-reduced-motion` turns tweens and
auto-play off.

Numbers on the slides come from the live app's demo plan (Moon, LI-5L, robotic
mobility & navigation, three sites pinned) captured on 2026-11-15. If the
release changes, re-run `npm run capture` and update the copy in the build script.
