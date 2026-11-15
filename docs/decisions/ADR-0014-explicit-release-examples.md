# ADR-0014 — Explicit release examples and browser data loading

Date: 2026-11-15. Status: proposed in #183 / PR #184; accepted only on owner merge.

The supplementary target models are examples of a field plan. They are separate
from the objective-based finder. They do not set new accepted planetary bands.

- Every example parameter lives in `data/pipeline/release-scenarios.yaml`, with
  its origin and reason. `contracts/release-scenarios.schema.json` requires both.
  Output repeats those assumptions and labels its scientific status partial.
- The 50 percent minimum land share applies only when the example explicitly
  requests it. The general target-ranking function has no implicit land cutoff.
  The finder also has no implicit cutoff. These are different requests, not two
  implementations of the same policy. Unknown land share remains unknown.
- The screen reduces known ocean contamination; it does not repair terrain or
  certify coastal values. A full DEM and MODIS QA replay remains work order #76.
  WBM/EDM masking is opt-in until that replay. Its cache is isolated by policy,
  input tile list, and grid hash. Missing requested masks fail the tile rather
  than silently publishing unmasked pixels. Elevation and slope keep separate
  sample counts so a missing slope does not erase a known elevation.
- Campaign results separate a certified suboptimality bound from a numerical
  estimate. A failed solve is visible in the release summary. Missing historical
  years or no eligible candidates produce an explicit not-run reason.
- The initial binary keeps the existing fields plus land share. Extra yearly
  measurements are separate hashed Float32 arrays loaded on request. The
  browser uses its existing compiled TypeScript engine; no Rust/WASM target
  currently exists. Python campaign optimization remains a publication step.

Lean proofs establish the stated mathematical results. Tests check executable
agreement on selected cases. Neither establishes physical analogy validity.
