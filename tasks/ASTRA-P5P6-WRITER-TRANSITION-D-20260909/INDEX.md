# Campaign Index: ASTRA-P5P6-WRITER-TRANSITION-D-20260909

artifact_authority: current
owner: James Chen
status: active, governed and sequential
AUTO_CHAIN: false

## Objective

Implement the source-owned canonical Runtime receipt/effect adapter over the accepted Card C writer boundary. Carry a typed loaded-registry runtime writer port through the actual canonical_task_seam.py -> BattlesuitGateway.ask_unified -> MainchainEntry.run_mainchain -> UnifiedRuntime.run chain, and through run_mainchain_replan -> UnifiedRuntime.run_replan and receipt finalization, without bypassing MainchainEntry or changing Planner selection. Require lease/context evidence before each activated Runtime receipt/effect write, exact loaded root/role/source/process identity/generation/transaction binding, and denial before bytes or dispatch for missing, stale, wrong-root, wrong-thread, replayed, forked, or mismatched bindings. Use a typed lookup of an already-loaded source-owned registry; missing lookup denies activated writes and never creates a fallback registry or new authority. Preserve accepted P6C EffectJournal, EffectDispatchPort, EffectReconcilePort, deterministic reservation/readback, replay/reconcile, and one-domain lock semantics. Scope the receipt owner guard to receipt mutation/readback and do not hold it unnecessarily across the full Runtime/model invocation; fixture evidence must cover the actual canonical run/replan/finalize chain and lease witness. Card C dependency is HEAD dcd8740a3b93ab5befb6dfbe2b3a9f382836036c tree c31d33191649aa6f7fe354add725597ceed7202b and must be independently accepted before this card is dispatched. Follow approved SOURCE_SPEC_ADDENDUM.md SHA bcedf2026499698c40ccf66c7973eaa02a1c570dbb808a2f2618eeb9f8fee2c6. Source/fixture-only work: no new release, live deployment, writer-transition authority publication, provider/API-key/SDK/Agy/native/network action, main/push/merge/approval/integration, or production claim. Preserve full P0-P8 scope and claim ceilings. AUTO_CHAIN=false. Worker may exact-scoped commit after independent review; cannot approve, integrate, or push.

## Ordered cards

| Order | Task ID | Card | Status | Dependency |
|---:|---|---|---|---|
| 0 | `astra-p5p6-writer-transition-d-20260909` | `00-astra-p5p6-writer-transition-d-20260909.md` | ACTIVE | Owner confirmation |
