# Target sites (W49, issue #108)

Cited list of the named sites where Moon and Mars values will be extracted. This
directory is data preparation only: no scoring, ranking, similarity or UI. One
YAML file per site, filename = `siteId`.

## Row schema

- `siteId` — kebab-case, matches the filename (`*.yaml`).
- `name` — human-readable site name as used in the cited source.
- `body` — `moon` or `mars`.
- `kind` — `region` (a landing region), `feature` (an IAU-named landform),
  or `landing-site` (a spacecraft touchdown point).
- `status` — `candidate` (announced and still in the official list),
  `historical` (dropped, superseded, or a completed landed mission),
  `proposed` (other south-polar sites referenced in repo docs or science plans).
- `centreLat` / `centreLon` — planetocentric, east-positive. Deliberately `null`
  when no numeric centre is published in a snapshottable official text; the
  companion rule is enforced by the validator (`p0ingest.targets`): a `null`
  centre must carry `missingReason`, and coordinates may never be typed from
  memory.
- `lonMode` — `east-positive-0-360` (USGS gazetteer exports, Viking 1, Opportunity)
  or `east-positive-minus180-180` (sources quoting west longitudes, JPL press kits).
- `extentRadiusKm` — half-width when the source states a region size (2022
  Artemis regions: "approximately 9.3 by 9.3 miles (15 by 15 kilometers)" -> 7.5 km).
  Feature rows instead carry `extent` bounding boxes taken from the gazetteer export.
- `usgsCrossCheck` — great-circle distance in km from the cited centre to the
  matching USGS gazetteer feature centre, with the tolerance used and why.
  All distances use mean body radii (Moon 1737.4 km, Mars 3389.5 km).

## Conventions enforced by the validator

Every row with a coordinate must quote a verbatim passage from a snapshotted
document (`data/snapshots/`, sha256-pinned in `MANIFEST.json` via
`p0ingest.snapshots.fetch` only), and the latitude/longitude numerals stated in
`centreLat`/`centreLon` are re-parsed out of that quote and compared. Gazetteer
rows must re-compose their record quote from the `<BODY>_nomenclature_center_pts.zip`
DBF exactly. Press-kit PDFs cannot be re-parsed in the frozen environment;
they are hash-verified and carry an informational note.

## What is in here (47 rows)

Moon (23 rows):
- 1 generic envelope target (`moon-south-pole-artemis-envelope`) — the target
  actually named by `data/envelopes/moon-south-pole-v0.json` and referenced by
  the `data/objectives/*.yaml` value envelopes ("Artemis III south-polar
  candidate region"); no numeric centre exists anywhere in the repo for it.
- 9 candidate regions from NASA's 2024-10-28 release (Peak near Cabeus B,
  Haworth, Malapert Massif, Mons Mouton Plateau, Mons Mouton, Nobile Rim 1,
  Nobile Rim 2, de Gerlache Rim 2, Slater Plain) — status `candidate`. NASA
  publishes no numeric centres or region sizes as text in that release, so all
  centres are `null` with that reason.
- 8 regions only in the original 2022-08-19 13-region list (Faustini Rim A,
  Peak Near Shackleton, Connecting Ridge, Connecting Ridge Extension,
  de Gerlache Rim 1, de Gerlache-Kocher Massif, Leibnitz Beta Plateau,
  Amundsen Rim) — status `historical`, `extentRadiusKm: 7.5` from the quoted
  15 x 15 km region size, centres still `null` (graphic only).
- 11 IAU gazetteer features (Shackleton, Haworth, Faustini, de Gerlache,
  Malapert, Nobile, Amundsen, Leibnitz, Mons Mouton, Slater, Cabeus B) with
  exact planetocentric centres and bounding boxes from the USGS gazetteer,
  each cross-checked against itself (0.0 km recorded by construction, since
  the cited coordinate IS the gazetteer centre).

Mars (24 rows):
- 8 host features from the USGS gazetteer (Gale, Jezero, Gusev,
  Meridiani Planum, Utopia Planitia, Chryse Planitia, Elysium Planitia,
  Ares Vallis).
- 9 landed-mission sites with coordinates quoted from NASA sources: Viking 1
  (22.27 N, 312.05 E planetocentric), Viking 2 (47.6673 N, 134.2809 E),
  Pathfinder (19.33 N, 33.55 W), Spirit (14.572 S, 175.478 E), Opportunity
  (1.946 S, 354.473 E, IAU 2000 body-centred as quoted), Phoenix (68.15 N,
  125.9 W nominal), Curiosity (4.6 S, 137.4 E; JPL MSL press kit), InSight
  (4.5 N, 135.9 E; JPL InSight press kit), Perseverance (about 18 N, 77 E;
  JPL Mars 2020 press kit). All are status `historical`. The NSSDC lander pages
  carry centre-to-host-feature distances in `usgsCrossCheck` (e.g. Spirit is
  3.6 km from the Gusev gazetteer centre; Curiosity 51.4 km from Gale's;
  Perseverance 45.6 km from Jezero's). Planitia/vallis-scale hosts are marked
  informational-only — the planitia diameter dwarfs the distance.
- Zhurong is a `landing-site` row with **null** coordinates and an explicit
  `missingReason`: no official NASA/USGS document carrying Zhurong touchdown
  coordinates could be snapshotted through `p0ingest.snapshots.fetch`, so they
  are left blank rather than invented. The `mars-feature-utopia-planitia` row
  covers the host area from the gazetteer.

## Sources

All three datasets have registry rows in `data/catalog/` and MANIFEST entries
produced by `p0ingest.snapshots.fetch`:

- `artemis-iii-candidate-regions` — NASA release 22-089 (2022-08-19, 13
  regions), NASA release 24-136 (2024-10-28, 9 refined regions), and the
  NTRS LPSC abstract 20250011660 (downselection narrative).
- `usgs-planetary-nomenclature` — USGS Astrogeology nomenclature centre-point
  shapefiles for Moon and Mars (public domain).
- `mars-lander-sites` — NSSDCA master-catalog spacecraft pages (Viking 1/2,
  Pathfinder, Spirit, Opportunity, Phoenix) and JPL landing press kits (MSL
  2012, InSight 2018, Mars 2020 2021) via web.archive.org.

Nssdc page text quotes are verified verbatim by the validator on every run;
PDF quotes are hash-pinned (see the validator notes).

## Validation

From `services/ingest/`:

    uv sync --frozen
    uv run python -m p0ingest.targets          # per-row listing, 47/47 rows pass
    uv run python -m unittest discover -s tests  # includes tests/test_targets.py
