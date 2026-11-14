# Target envelopes v0 (W5, issue #18)

Two envelope instances, one per target body, validating against
[`contracts/envelope.schema.json`](../../contracts/envelope.schema.json):

| File | `envelopeId` | body | Used by |
|---|---|---|---|
| `moon-south-pole-v0.json` | `moon-south-pole-v0` | moon | `SE-3LM` (waterIce, thermal, subsurface, illumination), `LI-5L` (terrain, illumination) |
| `mars-reference-v0.json` | `mars-reference-v0` | mars | `OP-5LM` (terrain, surfaceMaterial, dustProcess, thermal) |

## What `lo` / `hi` mean here

Each `dimensions[]` entry is a **target-side physical band**: the range of one
physical quantity, in the stated `unit` and at the stated scale, that the target
body or target region presents or is required to present. `sourceDataset` is the
registry `datasetId` (`data/catalog/*.yaml`) that measures that quantity on the
target side.

This file is **not** a loss table and **not** a similarity score. Turning a band
into a per-dimension loss, and an Earth site into a within/outside verdict, is
engine work (ADR-0003 priority order puts the engine after ingest). Per
AGENTS.md rule 4 nothing here is ever aggregated across dimensions, and
`weightFamily` is the declared per-dimension weight family only
(`Analog.Atlas.BoxFamily`, `proofs/Analog/Atlas.lean`) — no certificate exists
for either envelope yet (ADR-0001 experiment gate).

Conventions used in both files:

- `lo = 0` is the **definitional floor** of a non-negative quantity (slope in
  degrees, albedo, a distance). It is not an empirical bound.
- A zero-width band (`lo == hi`) is a **degenerate but legal** envelope
  (`lo <= hi` is the only rule; `Envelope.valid`). ADR-0001 lists "zero-width
  envelope" as a degenerate case to check. Both zero-width bands below are
  flagged as such in the PR.
- One band per dimension. Where a source gives a second scale (for example the
  Moon 2 km EVA slope limit), the README notes it; it is not encoded, because
  the engine must pick one band per dimension.

## Per-bound citations

Every bound below is quoted from a document in `docs/research/` or from a
registry row in `data/catalog/`. No number here was produced by this work
order.

### `moon-south-pole-v0.json`

| Dimension | Band | Value | Unit | `sourceDataset` | Quoted source |
|---|---|---|---|---|---|
| `terrain` | 0 – 10 | max slope over a 100 m baseline | deg (slope over 100 m) | `lola-south-pole-ldem-2023` | doc 08 §3, Moon (Artemis III) column: "Slope, touchdown scale \| ≤ 15° over 5 m \| **< 10° over 100 m** (8° continuous-slope contours shown)"; doc 08 §2 feature `slope_100m`: threshold "`<10 (Artemis III)`", `threshold_src` "ART-2025 req.2" |
| `illumination` | 100 – 100 | share of the stay window with the surface sunlit | % of the stay window sunlit | `lola-polar-illumination` | doc 08 §3, Moon column, Comms / light row: "**surface lit for the whole stay**"; doc 08 §2 feature `illum_frac_avg`: threshold "surface lit for whole surface stay; solar visibility <5% reduces usable area", `threshold_src` "ART-2025 req.5a" |
| `waterIce` | 0 – 2 | distance from the site to the nearest permanently shadowed region | km (distance to nearest PSR) | `lola-south-pole-ldem-2023` (LPSR layer) | doc 08 §4, source `ART-MCDM-2024`: "criteria C1–C6 incl. geologic-unit count and **PSR within a 2 km walk radius**"; doc 08 §2 feature `psr_dist_km`: "distance from site to nearest PSR (straight-line and traversable)", unit km, `target_source` "lola-south-pole-ldem-2023 (LPSR)" |

`sourceDataset` choices come from the catalogue rows themselves:
`lola-south-pole-ldem-2023` `plannedUse` "Moon south-pole envelope (SE-3LM,
LI-5L): slope, roughness, permanently shadowed regions", and
`lola-polar-illumination` `plannedUse` "LI-5L low-sun landing: fraction of time
illuminated, min sun elevation".

### `mars-reference-v0.json`

| Dimension | Band | Value | Unit | `sourceDataset` | Quoted source |
|---|---|---|---|---|---|
| `terrain` | 0 – 5 | mean slope along planned traverse corridors | deg (mean slope, traverse) | `mola-hrsc-blended-dem` | doc 08 §3, Mars (MSL guide v2) column, Slope / surface ops row: "rover static stability ≥ 45°, nominal ops < 30° tilt; design terrain **15% rocks / 5° mean slope** / 10% slip"; doc 08 §2 feature `slope_trav_mean`: threshold "5 (MSL mobility design-reference terrain not a limit)", `threshold_src` "MSL-EUG-v2 §2" |
| `surfaceMaterial` | 0 – 0.25 | Lambert/bolometric albedo | albedo (0–1) | `tes-mgs` | doc 08 §3, Mars column, Surface material row: "Ka-band backscatter > −20 dB; TI < 100 J m⁻² K⁻¹ s⁻¹ᐟ² **and albedo > 0.25 ⇒ unsuitable (dust)**"; doc 08 §2 feature `albedo`: threshold "`<=0.25` with TI>=100 (MSL dust screen)", `threshold_src` "MSL-EUG-v2 §1.8" |

`sourceDataset` choices come from the catalogue rows themselves:
`mola-hrsc-blended-dem` `plannedUse` "Mars terrain envelope at 200 m",
and `tes-mgs` `plannedUse` "Mars thermal/dust envelope".

## Dimensions left out at v0 (unknown, not zero)

Per the issue's kill criterion, a bound with no traceable source is left out and
the dimension is **unknown** for that objective. Missing bands are absent from
`dimensions[]` (the contract has no "unknown" member), so the missing list lives
here, in the objective `toleranceSource.note`, and in the validator output.

| Envelope | Dimension | Why it is unknown | What would close it |
|---|---|---|---|
| `moon-south-pole-v0` | `thermal` | doc 08 §2 feature `tsurf_ann_max_psr` threshold is "cold-trap temperature criterion (value to pin from a primary source)"; doc 08 §5 item 2 says the lunar cold-trap temperature criteria "were removed here because only search-engine summaries carried them". The only "~100 K" in our docs is a `mismatch` label (doc 08 §1), not a measured band. | A primary-source lunar cold-trap temperature criterion, then the `diviner-l4` Polar Resource Product to measure it against. |
| `moon-south-pole-v0` | `subsurface` | `pit_cave_presence` (doc 08 §2) has no numeric threshold, and the only regolith number (`regolith_thick` ">5 (InSight HP3 mole)") is a Mars in-situ value from INSIGHT-2017, which doc 08 §4 marks "abstract-level only" and doc 08 §5 item 2 says to re-pin. | A lunar regolith thickness / pit-and-lava-tube characterisation with a citable primary source (`lroc-pits-atlas`, `diviner-l4`). |
| `mars-reference-v0` | `thermal` | The only candidate was one InSight reading (sol 675 average air temperature, −62.314 °C, from the doc 01 §2 probe log). Dropped at review: it's a single point rather than a range, it's air temperature while the Earth side measures ground (land surface) temperature, there's no hashed snapshot behind it (AGENTS.md rule 3), and the `insight-weather-archive` licence is unverified. | A Mars surface-temperature range from `tes-mgs` or `themis-ir-controlled-mosaics` over the reference zone, snapshotted with a hash. |
| `mars-reference-v0` | `dustProcess` | The `dustProcess` features in doc 08 §2 (`dust_cover_index`, `cdod_ann`, `cdod_storm_freq`) carry no numeric threshold in any of our sources; the only dust number we hold (the MSL dust screen) is expressed through thermal inertia and albedo, which are the `thermal` and `surfaceMaterial` dimensions. | A pinned dust-cover index or column optical depth value from `tes-mgs` / `mars-dust-climatology-lmd` (both in the registry). |

## Open items (not blockers for v0)

- The stay length for the Moon illumination band is not pinned in our sources:
  doc 08 §4 marks `ART-PSR-2022` ("continuous sunlight over a 6.5-day stay") a
  **secondary** source to re-cite before quoting, so the band is written as a
  share of the stay window and does not name a number of days.
- `tes-mgs` `plannedUse` says the "specific product (e.g. Putzig thermal inertia
  map) [is] to pin in W5". v0 cites the dataset level; the product-level pin
  needs a live probe plus a hashed snapshot, which belongs to the ingest lane
  (#19).
- `mola-megdr` is the second terrain source for the Mars band (its `plannedUse`
  is "Mars target envelope (OP-5LM): slope/roughness of reference zones").
- The contract has no way to state "this dimension is unknown". If the owner
  wants that in the data rather than in this README, it is a
  `contracts/envelope.schema.json` change (contracts lane), not a data-lane edit.

## Units: target side vs Earth side (read before W7)

These bands are measured on the Moon or Mars. The Earth cells from W6 (#19)
measure similar but not identical quantities, so the engine has to map them,
or leave gate 2 unknown where no fair mapping exists:

| Envelope band | Closest Earth column (W6) | Gap to handle in W7 |
|---|---|---|
| Moon terrain: max slope over 100 m | `slope_mean_deg`, `slope_frac_lt15` (240 m grid) | different baseline and statistic |
| Mars terrain: mean slope on traverses | `slope_mean_deg` | Earth value is a cell-wide mean, not a traverse mean |
| Moon illumination: sunlit for the whole stay | `polar_day` (computed from latitude) | only polar summer gets close; no terrain shadows yet |
| Moon waterIce: PSR within 2 km | `permafrost_pct` | different quantity; needs an explicit proxy rule or stays unknown |
| Mars surfaceMaterial: albedo ≤ 0.25 | none yet (`barren_pct` is land cover, not albedo) | needs MODIS albedo (`modis-mcd43c3-albedo`) or stays unknown |

## Reproducing the checks

```sh
uv run --no-project --with jsonschema==4.23.0 --with pyyaml==6.0.2 \
  python scripts/validate_contracts.py --self-test
```

The validator checks, for each envelope: JSON Schema validity, `lo <= hi` per
dimension (`Envelope.valid`), that every `sourceDataset` is a registry
`datasetId` in `data/catalog/*.yaml`, that the named dataset covers the
envelope's `body` and lists the dimension, and that every objective's
`toleranceSource.envelopeId` resolves to a file in this directory. It prints the
covered and unknown dimensions per objective.
