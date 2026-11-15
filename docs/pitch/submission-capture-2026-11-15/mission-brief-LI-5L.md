# Mission plan brief
MOON / LI-5L — Precision landing — shortened by us
Months: 1; team: 6; days: 14

Scientific status: partial. These are conditional screening results, not field certification.
- Scientific acceptance is partial. Requirements and comparisons are conditional on the stated sources, scales and bands.
- DEM nodata filtering was claimed by old column metadata but is not applied by the current terrain builder; values remain unchanged and scientifically unreviewed.
- MOD11C3 QC-bit filtering is not applied; replay counts the actual raw-value threshold, not an invented QA pass.

## 8401b65ffffffff (68.64078521728516, 54.62937545776367)

| Requirement | Priority | Origin | Band | Result | Gap / reason |
|---|---|---|---|---|---|
| terrain (slope_mean_deg) | must | target | 0 to 10 deg (upper excluded) | match |  deg |
| illumination (sun_noon_elev_deg) | must | team | 0 to 10 deg | match |  deg |

### terrain: evidence and limits

Band origin: target.
Basis: moon-south-pole-v0 terrain: max slope over a 100 m baseline <= 10 deg (Artemis III).
Scale caveat: Same number, different statistic: Earth is a mean over a 240 m grid, the Moon band is a max over 100 m. A mean under 10 deg does not guarantee every 100 m patch is under 10 deg.

### illumination: evidence and limits

Band origin: team.
Basis: Landing tests need a low sun and long shadows like the lunar south pole. We use a noon sun above the horizon and at or below 10 deg as the stand-in (polar night fails: no light to land by); it only happens at high latitudes in winter months.
Scale caveat: Computed from latitude only; no terrain shadows.

- Month 1: 0.056532517075538635 deg; match


Operational limits:

## Earth cannot reproduce
- gravity: reduced lunar or Martian gravity.
- pressureRegime: lunar vacuum or thin Martian atmosphere.
- radiation: lunar or Martian radiation environment.
- gravity: Descent and touchdown dynamics depend on lunar gravity (about 0.17 g).
- pressureRegime: In vacuum, engine plumes blast the surface differently than in Earth's air.

## Planning checklist (from the scientist)
Not checked: equipment, permits, personnel, budget, communications and emergency access.

Past-campaign closeness: not checked (S8 pending).
EONET is a curated event list. None recorded does not establish safety.

## Sources
Build manifest SHA256: 2cd4e1899bc6111dbe0c3c6251b1392ab4fa1fdf673cc6ea86542c52b1e4b0fe
- apps/atlas/src/planner/engine.ts: 05a9e9fd8e9d2d334dfaa7ca5339076f11b63425c30fe738240a353be3b40ad3
- contracts/planner-runtime.schema.json: f33ec50e39c2fb611bdba6ecca2f77bab8f684bfa9d64b8bb68cd7e96e02aa79
- contracts/release-scenarios.schema.json: 50b248e25abafa665a197217d9f2547312ea930c177fb20e41d72a6e7bf97393
- contracts/site-plan.schema.json: 3ee9c400dd7750dd1dcb2576f5c92b8a1e5481b290119ae0154543183d2cca21
- data/campaigns/atacama-arads-2019.yaml: 6a9462a8535da857b02a7b9cff1b048be002218e35720b9fe93a93c731443597
- data/campaigns/desert-rats-2010.yaml: 09a30001e329050648628ec22bbaca7962bc4400a188f23c1f730d17cec521f9
- data/campaigns/fmars-expedition-12.yaml: bf6c19b744ea6838a3bd14a63d316211bdbbfd80daad53eb91863af4f01aadc9
- data/campaigns/hiseas-iv.yaml: cb5415e2b28e49c4eed3b97ec41d176b0d342268e18a471babee923cc81289b1
- data/campaigns/hmp-2015.yaml: 55bf7c18d57962e04bae304a2105756e18da562ae2347934421b4b27d152b306
- data/campaigns/mdrs-89.yaml: 88c04848baee3d5c2b798ac162b7eedc9479937c81bcb7535b575b0e039b7b6c
- data/objectives/li-5l-moon.yaml: f91847820f4bc292fecb11e08c64bf1ab69db7328c7c763ad36387c902107e1e
- data/objectives/op-5lm-mars.yaml: fcb37046cbd7add5a3d4f09177a115c57acf659882209172d7700db4715e65f4
- data/objectives/se-3lm-moon.yaml: 425355a683c3ab6e5ded24b72df6a354483601b1c20a2a7d56b367b5d3eec3c5
- data/pipeline/columns.yaml: 194dea666d2d20bb26cabfe253119a8d915a9fbbad60d56dc247b0f285f9a9d9
- data/pipeline/evidence.yaml: 7af8c86da896aa367ec77ddef4ad82852c497efdee7e099707508ee1bb837d3d
- data/pipeline/release-scenarios.yaml: 87c72ce6c16865f11afbf28a4104a951b0f33874225a553d9a68c8dfaf64d3c1
- data/pipeline/test-categories.yaml: 54e02e3cc093efa78b32f6dbd84d4bdd6d4d9ce3c4942debdd75cd5788658355
- data/requirements/trait-map.yaml: 35e97a9aae8a77a70cea40c7f8c709284551f0d85a248f0ace8943b354f7e250
- data/snapshots/MANIFEST.json: bd1519f48a21c7f1c8235fe9cba56a8b41ed0440fb01be40780c305f397f3138
- data/snapshots/_derived/assembled/assembly-report.json: 04d8a595665073cf0afb7982eb578db33fce96728a71ab478103cef0e6a1ebe7
- data/snapshots/_derived/assembled/earth-features-r4.parquet: 8360aaf6c06ae8789862da18d3079cad6eccab804cb96afd8cc7f4aa0d998cf7
- data/snapshots/_derived/assembled/hazard-events.parquet: e699d6d626965dfbbe0b86626ef6be6d06c4abc18055578e2cdc48b6ee8e0545
- data/snapshots/_derived/assembled/planetary-targets.parquet: 3d891aab18da56a6050077e08ed68a3ad81bc8b698615c37b55ff3714c4aa5bf
- data/snapshots/_derived/assembled/sites-r4-monthly.parquet: 1e7d2f93fc634e971995ae163044be708d408c3147a21810db5703fe25c80fc9
- data/snapshots/_derived/assembled/sites-r4.parquet: 80fce95adddab7d970182aa55cf51023005de15c06bdbb3a5736f31a4a1ad657
- data/snapshots/_derived/cells-r4-monthly-years.parquet: dcb5fe60f4326c517f5a2f456808c25ef56ba7797225ab7c0dc8ea8d156cbe83
- proofs/Analog/CampaignOpt.lean: 475d0bda4033b1dfb4ae3963ffaed95129648d606ced9563b15ac6d51d1a12eb
- proofs/Analog/Funnel.lean: 8e77499733448106d65756adeab4f2ee5d908e0b4365aa7f18be07925850e59c
- proofs/Analog/FunnelProofs.lean: 2dae1144bd10d50ba493d46a71cb478b5abae7934eecd9be17b34847f483a8f6
- proofs/Analog/ParetoLayers.lean: 877b5362043ce9b1434826b439a0e68e4f65459f93758d23000735a70272168e
- services/engine/src/planner/assembled.py: 682ca529028c821b893bba41a1a521082c17db36b253ccf71f1e44cdccec6c11
- services/engine/src/planner/optimizer.py: 501a023d45cc5f5cdeece37b9e595650939beee9278e3510a66888d52a35bf03
- services/engine/src/planner/pareto_model.py: 151461c95592aa982b9f5fde490df0a75fccab326cbfe458af7b1c1b0f55fe33
- services/engine/src/planner/release.py: f6d9bef7acb4703d2ac34b97dcc6e5698be6bee254cb4c4c57e70ae7514cf9e6
- services/engine/src/planner/workflow.py: 3160ee3e182860b2634e230ddd7c48edfb33c85167d001b23a40b79672f1d20b
