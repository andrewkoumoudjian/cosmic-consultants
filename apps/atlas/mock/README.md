# Mock sites — SYNTHETIC, not real

Every file in `sites/` is a **synthetic** cell made for the UI demo.

- The site ids start with `synthetic-` and every name says "SYNTHETIC".
- The coordinates sit in regions that look like real analog terrain, so the map
  is not a grid of dots in the ocean. That does **not** make them assessments
  of those places.
- Every gate outcome is invented. The evidence refs say `synthetic:mock-grid`
  on purpose: there is no measurement behind them.
- `provenance.snapshots` is empty. Nothing here claims a snapshot, because no
  snapshot backs it (AGENTS.md rule 3).

Each file validates against `contracts/site.schema.json`, and the ARL of each
readiness entry is the level its gates give, checked by
`apps/atlas/scripts/check-mock.mjs`.

Regenerate them with:

```bash
python3 apps/atlas/mock/generate_mock.py
```

The generator recomputes every ARL with the frozen rule (largest k ≤ 6 whose
gates 1..k all pass; gates 1–4 must pass for every required dimension of the
objective), so the files cannot drift from the contract.

Real cells arrive from the ingest lane (#19) and the engine lane (#20) and will
replace these files.
