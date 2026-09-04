# Depreciation rate-table registry — scope of consumption

**Fable D6 mc21 2026-09-04 manifest-fidelity note.**

The following URIs are registered here:

- `urn:sbrm:rate:depreciation:fy2026:audit-variance-threshold`
- `urn:sbrm:rate:depreciation:fy2026:instant-asset-write-off-threshold`
- `urn:sbrm:rate:depreciation:fy2026:small-business-pool-rate`

**None of these are consumed by the v1 depreciation `/at/` or `/range/`
compute paths.** They belong to features (pool assets, IAWO, audit-
variance) that are refused out of T6 scope at the engine layer with
typed `refusal_class: pool_asset_out_of_t6_scope`, or belong to
audit-time comparisons that are not part of point-in-time WDV or range
depreciation.

The response manifest for `/at/` and `/range/` at v1 therefore emits
`rate_table_uris: []`, and the D6 empty-manifest advisory branch fires
correctly — it asserts *"no statutory rate tables are consumed by this
calculation"* which is true against these compute paths.

**Why keep the files here at all?** They are pre-registered for the
T6.1 pool-retrofit sprint. Registering them now (rather than at
consumption time) means the rate-table resolver has the substrate ready
when pool support lands, and prevents "you added the URI in the same
PR you added the consumer" as a class of merge coupling.

**When they start being consumed:** the engine will begin emitting
their URIs in `rate_uris_consumed`; the gateway's `build_manifest`
will populate `rate_table_uris` accordingly; and the D6 conditional
will automatically switch to the incumbent citing-rate-tables text.
The advisory follows the emitted manifest, not the calculator
identity (Fable D6 verbatim: *"if depreciation ever consumes a rate
table, the text follows without anyone remembering."*).

**Fidelity gate**: Fable Q2 mc22 2026-09-04 landed a
`test_depreciation_response_carries_manifest_block` in
`tests/test_manifest_fidelity.py` that asserts every registered
depreciation calc-URI emits a `manifest` block in its response. If a
future compute path silently starts referencing these URIs without
also emitting them in `rate_uris_consumed`, the gap surfaces at
that layer.
