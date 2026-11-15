# Planner art direction: "Observatory"

A white page with one dark object on it: the globe. Everything else is ink,
one ultramarine accent, and data. No captions, no stat cards, no framed panels.

The owner rejected the first take (cobalt on bone paper, "plates" with
`FIG.` captions) on 2026-11-15: too much filler, and Figma is a loose guide,
not the source of truth. This file replaces that direction.

## Rules

| Element | Rule |
|---|---|
| Page | `#fafaf9`. One sticky top bar holds the brand, the seven steps as pills, and "Copy link". No sidebar. |
| Titles | Source Serif 4, weight 300, 56px. The title is the content where it can be (step 4: "7,599 sites *of 91,800*"). |
| Text | Geist Sans 14px in ink `#0e1020`, muted `#6b6e7f`. No subtitle under titles. |
| Numbers | Geist Mono, tabular, right-aligned in tables. |
| Accent | Ultramarine `#3036e6`, used for selection and matches only. |
| Verdicts | ● match (accent), ◆ miss with its gap (`#d23f2a`), ○ unknown (`#a87400`). Always a shape plus a colour; screen readers get the word. |
| Compared sites | Teal, magenta and green: they read on the white page and on the night globe, and stay apart from the verdict colours. |
| Buttons | Pills. Primary is ink and turns accent on hover. |
| Tables | The JSheets look: thin grid, grey header row, frozen first column, mono numbers. |
| Globe | After the three.js TSL Earth example: navy sea `#0a0f33`, an ultramarine atmosphere, and every published land cell as a dot. Matches glow like city lights; misses are dim blue; unknown is amber. Built with globe.gl on three.js. |
| Motion | Steps fade in and rise 6px (Motion). Reduced motion turns it off. |
| Imagery | Derek's Moon and Mars engravings from the team Figma file, used as they are. |

## JSheets

JSheets (matsonj/jsheets-releases) is a native desktop app with DuckDB inside,
so it can't run in the page. Each report step has "Open in JSheets (.csv)": a
tidy table with one row per compared site and trait (verdict, value, band, gap,
reason), plus limit and logistics rows, each carrying the release manifest hash.
Missing values stay empty, with a reason. See ADR-0012 point 7.

## Hero (later)

Parked. The owner asked to ship the planner screens first.

## What we did not take

- Saturated multi-colour gradients (uisabor, uihssn). They cut the contrast
  between verdicts.
- A single "match %" anywhere. Rule 4 still applies everywhere.

## Moodboard (links only; we do not copy their images)

Hero: hollycurates/2088832635350978947, DevDsgn/2089230868380537028,
Palakonweb/2090003678103265595. System: praveenisomer (2118667212974428551,
2114680944196264294, 2105983637615526301, 2121566361021530366), emirbekin/2117574487835296203,
jakubkrehel/2089009286940639674, s3ththompson/2107512006706397450,
foodofthegods3/2099784849665986731, buildwithsid/2111785463396839782,
_davideast/2106194893810852153, BenjaminUIX/2086828047244939570,
VadimCarazan/2089697424331669921, uisabor/2117902781935915021,
uihssn (2117805357703802904, 2087495607615406357), pranavoriginals/2105346116388868364.
Globe: threejs.org/examples/webgpu_tsl_earth.html.
