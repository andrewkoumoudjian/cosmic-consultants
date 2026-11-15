# W15 calibration results (#23)

Expectations sha256 `024c37aa925afa556931aa46f5458b7ef8e636af574a8903791fe6ff7343253c`, frozen at commit `a906a04d9f6bbfa1204e84f258c54d1ffccac733` before this run.

Trait expectations held: 36 of 40. Funnel expectations held: 8 of 10. Grid expectations held: 4 of 4. Unresolved (counted as not held): 0 trait, 0 funnel. Campaigns run: 5; not evaluated: 0; not run: 1.

This counts our predictions. It is not a site score.

| Campaign | Variant | Trait | Priority | Expected | Observed | Value | Holds? |
|---|---|---|---|---|---|---|---|
| mdrs-89 | shipped | terrain | nice | match | match | 4.312 | yes |
| mdrs-89 | shipped | surfaceMaterial | must | match | match | 55.85 | yes |
| mdrs-89 | shipped | dustProcess | must | unknown | unknown (no-band) |  | yes |
| mdrs-89 | shipped | thermal | must | unknown | unknown (no-band) |  | yes |
| mdrs-89 | shipped | *funnel* | — | noMissSomeUnknown | noMissSomeUnknown | | yes |
| mdrs-89 | bandsOnly | terrain | nice | match | match | 4.312 | yes |
| mdrs-89 | bandsOnly | surfaceMaterial | must | match | match | 55.85 | yes |
| mdrs-89 | bandsOnly | dustProcess | nice | unknown | unknown (no-band) |  | yes |
| mdrs-89 | bandsOnly | thermal | nice | unknown | unknown (no-band) |  | yes |
| mdrs-89 | bandsOnly | *funnel* | — | allMatch | allMatch | | yes |
| fmars-expedition-12 | shipped | terrain | nice | match | match | 2.275 | yes |
| fmars-expedition-12 | shipped | surfaceMaterial | must | match | match | 89.31 | yes |
| fmars-expedition-12 | shipped | dustProcess | must | unknown | unknown (no-band) |  | yes |
| fmars-expedition-12 | shipped | thermal | must | unknown | unknown (no-band) |  | yes |
| fmars-expedition-12 | shipped | *funnel* | — | noMissSomeUnknown | noMissSomeUnknown | | yes |
| fmars-expedition-12 | bandsOnly | terrain | nice | match | match | 2.275 | yes |
| fmars-expedition-12 | bandsOnly | surfaceMaterial | must | match | match | 89.31 | yes |
| fmars-expedition-12 | bandsOnly | dustProcess | nice | unknown | unknown (no-band) |  | yes |
| fmars-expedition-12 | bandsOnly | thermal | nice | unknown | unknown (no-band) |  | yes |
| fmars-expedition-12 | bandsOnly | *funnel* | — | allMatch | allMatch | | yes |
| hmp-2015 | shipped | terrain | nice | match | match | 2.275 | yes |
| hmp-2015 | shipped | surfaceMaterial | must | match | match | 89.31 | yes |
| hmp-2015 | shipped | dustProcess | must | unknown | unknown (no-band) |  | yes |
| hmp-2015 | shipped | thermal | must | unknown | unknown (no-band) |  | yes |
| hmp-2015 | shipped | *funnel* | — | noMissSomeUnknown | noMissSomeUnknown | | yes |
| hmp-2015 | bandsOnly | terrain | nice | match | match | 2.275 | yes |
| hmp-2015 | bandsOnly | surfaceMaterial | must | match | match | 89.31 | yes |
| hmp-2015 | bandsOnly | dustProcess | nice | unknown | unknown (no-band) |  | yes |
| hmp-2015 | bandsOnly | thermal | nice | unknown | unknown (no-band) |  | yes |
| hmp-2015 | bandsOnly | *funnel* | — | allMatch | allMatch | | yes |
| desert-rats-2010 | shipped | terrain | nice | match | match | 2.558 | yes |
| desert-rats-2010 | shipped | surfaceMaterial | must | match | miss (gap 46.4 below) | 3.585 | **no** |
| desert-rats-2010 | shipped | dustProcess | must | unknown | unknown (no-band) |  | yes |
| desert-rats-2010 | shipped | thermal | must | unknown | unknown (no-band) |  | yes |
| desert-rats-2010 | shipped | *funnel* | — | noMissSomeUnknown | someMiss | | **no** |
| desert-rats-2010 | bandsOnly | terrain | nice | match | match | 2.558 | yes |
| desert-rats-2010 | bandsOnly | surfaceMaterial | must | match | miss (gap 46.4 below) | 3.585 | **no** |
| desert-rats-2010 | bandsOnly | dustProcess | nice | unknown | unknown (no-band) |  | yes |
| desert-rats-2010 | bandsOnly | thermal | nice | unknown | unknown (no-band) |  | yes |
| desert-rats-2010 | bandsOnly | *funnel* | — | allMatch | someMiss | | **no** |
| atacama-arads-2019 | shipped | terrain | nice | match | miss (gap 0.282 above) | 5.282 | **no** |
| atacama-arads-2019 | shipped | surfaceMaterial | must | match | match | 99.94 | yes |
| atacama-arads-2019 | shipped | dustProcess | must | unknown | unknown (no-band) |  | yes |
| atacama-arads-2019 | shipped | thermal | must | unknown | unknown (no-band) |  | yes |
| atacama-arads-2019 | shipped | *funnel* | — | noMissSomeUnknown | noMissSomeUnknown | | yes |
| atacama-arads-2019 | bandsOnly | terrain | nice | match | miss (gap 0.282 above) | 5.282 | **no** |
| atacama-arads-2019 | bandsOnly | surfaceMaterial | must | match | match | 99.94 | yes |
| atacama-arads-2019 | bandsOnly | dustProcess | nice | unknown | unknown (no-band) |  | yes |
| atacama-arads-2019 | bandsOnly | thermal | nice | unknown | unknown (no-band) |  | yes |
| atacama-arads-2019 | bandsOnly | *funnel* | — | allMatch | allMatch | | yes |

## Grid-wide

| Objective | Variant | Check | Expected | Observed | Holds? |
|---|---|---|---|---|---|
| OP-5LM | shipped | matches | 0 | 0 | yes |
| OP-5LM | shipped | paretoLayered | 0 | 0 | yes |
| OP-5LM | bandsOnly | matchesAtLeast | 1 | 10703 | yes |
| OP-5LM | bandsOnly | paretoLayered | 0 | 0 | yes |

## Not run

- hiseas-iv: Not run. HI-SEAS IV is a one-year isolation and habitat-microbiome study. None of our three objectives (OP-5LM surface mobility, SE-3LM water ice, LI-5L lunar infrastructure) covers it, and inventing a mapping would make the calibration look broader than it is.

## Inputs

- `data/snapshots/_derived/assembled/assembly-report.json` sha256 `7bf0145ea489fa60cae7f68abe773d5cbb62e7bdca02495f1128178cc1019fd5`
- `data/snapshots/_derived/assembled/sites-r4.parquet` sha256 `8afc8547cb083fa81e2b9d3c4d22a148afa1705772958cd30e09d4986dba65f6`
- `data/snapshots/_derived/assembled/sites-r4-monthly.parquet` sha256 `1e7d2f93fc634e971995ae163044be708d408c3147a21810db5703fe25c80fc9`
- `data/snapshots/_derived/assembled/hazard-events.parquet` sha256 `e699d6d626965dfbbe0b86626ef6be6d06c4abc18055578e2cdc48b6ee8e0545`
- `assembly-report.json (as read)` sha256 `7bf0145ea489fa60cae7f68abe773d5cbb62e7bdca02495f1128178cc1019fd5`
