# Campaign Index: ASTRA-P5P6-WRITER-TRANSITION-E-20260909

artifact_authority: current
owner: James Chen
status: active, governed and sequential
AUTO_CHAIN: false

## Objective

Implement the source-owned event producer adapter over the accepted Card D/C/B writer boundary. Own the typed EventWriterAdapter/factory and process-scoped exact-root lookup inside the approved event transport modules, consuming an existing B WriterRegistry through its register/acquire primitives without creating a second registry or authority. Carry the typed event writer binding through actual NexusEventBus configure/publish callers in the pipeline, AsyncFeedbackRouter, and governance packet flow; acquire a thread-local operation lease/context immediately before event append and close it after durable fsync/readback. Bind the exact observed event-log root, role, source/process identity, generation, thread, and causal transaction; unknown roots, stale generations, forged/expired/wrong-thread/replayed contexts, direct unadapted append, and reconfiguration to another active root deny before event bytes. Preserve source-bound root isolation, the no-second-domain-lock rule, deferred cross-domain emission boundary, and accepted P6C owner/effect semantics. Keep DeveloperFeedbackDecisionStore and assisted-job/developer-feedback writers explicitly separate with their existing paths/locks; do not relabel them as event_log. Positive fixtures must execute real pipeline configure/publish, AsyncFeedbackRouter configure/publish, and governance configure/emit caller paths, not direct log-store calls only. Card D dependency is 3afb499128a5efe832dfe1f8e1cb533c4dc5ace7 tree 20b8479623475118d7ba39b857a57210ddcecdb1 and must be independently accepted before this card is dispatched. Follow approved SOURCE_SPEC_ADDENDUM.md SHA bcedf2026499698c40ccf66c7973eaa02a1c570dbb808a2f2618eeb9f8fee2c6. Source/fixture-only work: no new release, live deployment, writer-transition authority publication, provider/API-key/SDK/Agy/native/network action, main/push/merge/approval/integration, or production claim. Preserve full P0-P8 scope and claim ceilings. AUTO_CHAIN=false. Worker may exact-scoped commit after independent review; cannot approve, integrate, or push.

## Ordered cards

| Order | Task ID | Card | Status | Dependency |
|---:|---|---|---|---|
| 0 | `astra-p5p6-writer-transition-e-20260909` | `00-astra-p5p6-writer-transition-e-20260909.md` | ACTIVE | Owner confirmation |
