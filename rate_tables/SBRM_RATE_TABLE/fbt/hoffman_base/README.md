# `hoffman_base` taxonomy bundle (empty-ready)

This directory is reserved for the `hoffman_base` taxonomy bundle under the
FBT calculator. It is empty at Phase 3c.2 (`mut-2026-05-12-mc16`) because
no Hoffman-base-taxonomy FBT consumer yet exists — the FBT regression
suite (`LodgeiT_FBT/regression_suite/fbt_regression_suite_fy2026.jsonld`)
references `lodgeit_au_sbrm` URIs only.

Per CLAWDOG/111 §2 the ratified Phase 3c taxonomy set is
`[lodgeit_au_sbrm, hoffman_base]`. The Standing Rule #12 production-bundle
gate parametrises over the ratified set; this directory's existence
satisfies assertion class #1 (bundle existence) even though it carries no
rate-table fact-nodes yet.

This directory populates at Phase 3c.3 when `Depreciation_Transforms`
onboards (the first calculator whose surface stresses the cross-taxonomy
routing path per CLAWDOG/109 §8.3); the FBT analogue of `hoffman_base`
content can populate later if/when a Hoffman-base-taxonomy FBT consumer
emerges.

— ClawDog ∮ (mut-2026-05-12-mc16)
