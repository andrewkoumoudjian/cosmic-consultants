# Working mission workflow (#132)

Goal: run the IDEA workflow on the delivered assembly while source coverage continues separately.

Existing design: ADR-0005 and ADR-0007; docs/plan/MISSION-PLANNER.md. Dependencies integrated unchanged in this isolated branch: PR #79 contracts, #84 statements, #85 engine foundation and #122 URL codec. This branch does not replace their authors' branches.

## Frozen core statement

`proofs/Analog/Funnel.lean` from PR #84 is frozen unchanged for #132 under Andrew's explicit implementation instruction. SHA256: `8e77499733448106d65756adeab4f2ee5d908e0b4365aa7f18be07925850e59c`. Its definitions and eleven S7 propositions cover known/inside bands, unknowns, month aggregation, must/nice, tighter requirements and unknown operational limits. Empty/reversed/strict bands, empty months and empty must sets were reviewed: empty must is vacuous in this formal model; the UI must make an empty selection explicit. The statements do not validate source physics, application arithmetic or thresholds. Proofs go in a separate module, without changing the frozen file.

## Implementation tasks

- [x] Prove S7 and extend the pinned axiom audit; capture direct build/Lean exit codes.
- [x] Add an assembled-data adapter and verified L4 release command. Reuse existing publisher; verdicts use the same published Float32 values as the browser. Preserve per-cell/month null reasons in a release supplement.
- [x] Implement requirements, monthly verdicts/gaps, limits, Pareto layers and brief output with tests, including strict boundaries, ties and unknowns. A strict upper boundary can miss with zero geometric gap; record the strict boundary explicitly instead of inventing an epsilon.
- [x] Wire a planner entry in the existing atlas: body/objective/category/months, metric bands and must/nice, finder, map, three-site comparison, gaps, logistics/risks and Markdown/print export. Keep available source warnings visible.
- [x] Validate real requests for both bodies, build/test the app and publish a reviewable PR. No scientific acceptance or full-feature completion claim.

## Interfaces

Use the existing plan-request, trait-map and site-plan schemas. Any needed extension is made in contracts first and documented before dependent engine/app code. `planner.assembled` loads only the assembly; `planner.workflow` computes tested results; `planner.release` produces app artifacts and golden conformance cases. Browser code consumes those artifacts only and mirrors the frozen S7 definitions. Existing engine and codec modules stay as foundation.

## Checks

Engine: Python unittest suite normal and optimized. Proofs: pinned `lake build` then `lake env lean Analog/Audit.lean`, direct process return codes. Atlas: codec/workflow tests, TypeScript/Vite build, existing mock check. Real-data publication verifies all recorded output hashes and the registry before use. Golden fixtures contain published Float32 values for exact Python/TS parity. Inputs with NaN/infinity, invalid keys, stale hashes and unavailable data fail or stay explicitly unknown, never silently match.

## Release limits

Source QA remains partial (#76). Published decisions are conditional on the named data/bands, with scale caveats, source hashes and all permanent Earth breakdowns shown. Full exact-feature coverage, correlation, new data collection, S8 closeness and optimizer work are outside this first slice. Past campaigns are cited records, without calculated closeness until S8 is proved. UI output keeps logistics and risk evidence distinct.
