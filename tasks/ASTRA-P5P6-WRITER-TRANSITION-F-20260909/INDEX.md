# Campaign Index: ASTRA-P5P6-WRITER-TRANSITION-F-20260909

artifact_authority: current
owner: James Chen
status: active, governed and sequential
AUTO_CHAIN: false

## Objective

Implement the source-owned multi-root writer activation cohort coordinator after root acceptance of Card E. Follow SOURCE_SPEC_ADDENDUM.md SHA-256 bcedf2026499698c40ccf66c7973eaa02a1c570dbb808a2f2618eeb9f8fee2c6 and SOURCE_SPEC.md SHA-256 cc3fe1d8e86494f8200494dd9edd5429230e7bb0970496776e9e23ac543fc385. Hold an explicitly authorized ordered set of actual roots under one durable cohort epoch, apply the existing per-root state-owner transition service in deterministic order, persist exact per-root transactions and physical readback, reacquire every loaded writer through the typed B hold/registry API, and expose ACTIVE only after all roots match current manager provenance. F exclusively owns ACTIVE and release: release through a typed loaded-registry operation only after durable ACTIVE, with no default registry, request-selected roots, broad ancestor root, generic WriterHold.release(), or separate-process release. Preserve restart/lost-ACK recovery, PARTIAL_UNKNOWN retention, exact root/source/server/process/role/generation/manifest/snapshot bindings, and the no-second-domain-lock rule. This is source/fixture implementation only; it does not claim bootstrap, live activation, authority publication, provider/API/native/network, main, push, merge, approval, integration, or production completion. Dependency independently accepted E a43fa092a1f42ebae0376d38f3f67c499287f8c4 tree c2b7f420a97f1e13f5f035225342ce25b432dce6. F owns a typed hold-gated reacquisition operation over actual existing TaskStateWriterAdapter, RuntimeWriterAdapter, EventWriterAdapter and attached stores: preserve old registration identity through B observation, derive loaded identity from actual reconfigured typed adapter fields, then update admission registration only after matched physical evidence; never substitute canned callbacks or bypass guards. Preserve zero leases, exact handles/root/source/process, all physical COMMITTED, old token denial, durable recovery, and no second domain lock. This is a new source-owned F coordinator operation, not generic registration permission. No protected state hand edits, no extra writable paths, no live operation. Worker may exact-scoped commit only after independent parent acceptance; no approval/integration/push. AUTO_CHAIN=false.

## Ordered cards

| Order | Task ID | Card | Status | Dependency |
|---:|---|---|---|---|
| 0 | `astra-p5p6-writer-transition-f-20260909` | `00-astra-p5p6-writer-transition-f-20260909.md` | ACTIVE | Owner confirmation |
