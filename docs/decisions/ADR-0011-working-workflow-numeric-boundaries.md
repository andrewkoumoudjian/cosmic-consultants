# ADR-0011: Common numeric inputs for the working workflow

Date: 2026-11-14. Status: implemented in #132 for owner review.

Andrew prioritized a usable engine/workflow on the delivered data. This release uses the existing assembled tables and published Float32 representation. The engine quantizes copied physical inputs to that same representation before making runtime comparisons; the browser reads the published bytes. User bands remain the same finite IEEE-754 numbers on both sides. No hidden epsilon or rounding of bands is introduced. Exact-real Lean results describe the logic; they do not prove the floating-point implementation.

A strict upper limit excludes equality. A value exactly at that limit is a miss with zero geometric gap and side `above`. The schema allows nonnegative gaps; the semantic validator checks the exact expected geometric gap, including zero. It must not manufacture a smallest positive step. Required-boundary tests cover equality and neighbors.

The planner consumes verified assembled artifacts only. Source values remain unchanged in the original files. Float32 conversion is declared in the published release, which retains source hashes, null reasons and source-quality warnings. Support diagnostics remain outside physical comparisons. Missing values and unavailable bands stay unknown.

Expanded source coverage, new target profiles and past-campaign closeness are later increments. The first release includes existing objective presets and editable Earth-unit bands with their caveats. A category label is context, not proof that every test in that category is supported. The release is conditional on its inputs and requirements; scientific acceptance remains partial.
