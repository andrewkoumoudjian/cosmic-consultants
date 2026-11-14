# ADR-0008: Prepare planetary products at their source support

Date: 2026-11-14. Status: source preparation implemented under #74;
scientific acceptance and target extraction remain open.

Andrew's scope is data acquisition, transformation, preparation and underlying
technology. The Google Doc IDEA tab guides needed quantities. This change
adds actual planetary source products to the Earth data work.

- Preserve Diviner south-pole PRP triangle records and TES day/night map
  pixels at native support. Done when: source values and positions survive
  decoding with input/output hashes and byte/row checks.
- Keep Diviner annual average temperature at its stated depth of 2 cm.
  Keep annual surface maximum separate. Both are model statistics in Kelvin.
  Done when: field descriptions and units travel with the prepared data.
- Label Diviner ice depth as calculated ice stability, not observed ice.
  Keep zero; turn the declared -999 exclusion into null and retain its raw
  value. Done when: source exclusions and prepared nulls agree exactly.
- Exclude interpolated TES pixels from the usable thermal-inertia column,
  retaining raw values and the interpolation mask. Keep the published
  computed range of 5 to 5000 J/(m^2*K*sqrt(s)). Done when: masks, range,
  null reasons and non-null values agree with raw products.
- Preserve the TES IAU_1991 reference frame, source grid and 1999–2004
  observation period. Keep Diviner triangle geometry and source time caveats.
  Done when: no Earth H3 assignment or invented observation year appears.
- Implement bounded-memory readers and pinned Polars preparation.
  Done when: the full sources build without loading the full character
  table or materializing both global maps as Python objects.

This step directly decodes existing scientific products and applies their
declared exclusions. It introduces no new scientific model, physical feature
formula, target requirement, similarity measure or acceptance theorem. New
calculations and comparisons still require the applicable Lean-first freeze
and audit under ADR-0001. Passing source checks does not validate the source
models or establish support for all 55 features or all test categories.

The first batch includes the Moon's south polar PRP and both global TES
thermal-inertia maps with masks. Other lunar products, per-target extraction,
terrain at declared baselines and historical test measurement extraction
remain follow-on data work in #74.

The TES DSMAP document's equation signs conflict with its stated upper-left
and edge conventions. This batch retains source line/sample indices and
records that conflict; geographic extraction is pending independent review.
No target location is silently assigned using either interpretation.

The same work order adds a small ARADS 2019 extraction from its existing
hashed CC BY article: achieved command cycles, drilling depth and instrument
delivery count. Native units and exact source passages/character offsets
travel with each record. Those are reported results, not universal test
requirements. Missing historical conditions remain unknown.

Andrew additionally supplied eleven NASA/CSA/ESA/JAXA resources. Their
inventory is `data/sources/agency-portals.yaml`; a reproducible reachability
probe preserves successes and failures. Discovery portals, display imagery
and tutorials remain distinct from acquired physical datasets. New partner
products require their own version, licence, QA and acquisition checks;
portal reachability alone never marks a feature complete.

Sources:
- https://pds-geosciences.wustl.edu/lro/urn-nasa-pds-lro_diviner_derived1/data_derived_prp/dlre_prp_south.xml
- https://pds-geosciences.wustl.edu/mgs/mgs-m-tes-5-timap-v1/mgst_9001/aareadme.txt
- Source labels, documentation, licence evidence and hashes are recorded in
  `data/snapshots/MANIFEST.json` and the generated preparation report.
