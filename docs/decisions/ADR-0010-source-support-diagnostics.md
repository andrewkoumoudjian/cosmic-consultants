# ADR-0010: Keep source support and calendar diagnostics in native units

Date: 2026-11-15. Status: implementing data preparation in work order #127.
This decision adds no comparison formula or scientific acceptance claim.

The assembler's normalized frames applied the existing IQR formula to numeric
support counts when their IQR was positive. A count of contributing months or
pixels describes a measurement's support, rather than the physical quantity.
The month of an annual maximum also needs its original calendar meaning.

## Decisions

1. Registry columns with `role: diagnostic` retain their source values, types,
   nulls and missing reasons in raw and normalized frames. Done when: the build
   checks exact equality for these columns across both frames. This includes
   source-pixel support fractions for modeled soil and regolith thickness.
2. These columns have no physical trait assignment. Their scale records say
   `inSum: false`, `scaled: false` and `unscaledReason: source-diagnostic`.
   Done when: contributing-month, valid-pixel and calendar fields stay in native
   units even when they have positive IQR.
3. Include dust contributing months, dust maximum month and burned mapped years
   alongside their measurements. Done when: the source joins pass exact-value
   checks and all three diagnostics appear in the delivered frames.
4. Require the merged dust source tables rather than silently skip them.
   Done when: a missing delivered source fails the build.
5. Preserve the current Google Doc's 19-category table and all eight detailed
   menu rows separately. The detailed geology menu currently has eight entries;
   the robotic menu has twelve. The maximum of eight selected metrics is a user
   selection limit. Done when: the captured revision, hash and literal source
   terms accompany the data coverage report.

The IDEA table remains the workflow authority under ADR-0007. Physical values
use the existing ADR-0005 D5 preparation rule. No site score or new physical
interpretation is introduced. Source QA limits in #76, unimplemented exact
features, source coverage, model/proxy limits and permanent Earth breakdowns
remain explicit. Merging the source or assembler does not establish scientific
validity.

Source: https://docs.google.com/document/d/1up_LJPlljDuY-xak0Licddnoj8MakBiD1pv_Vywj8yQ/edit?tab=t.191x2ca9c4uw
