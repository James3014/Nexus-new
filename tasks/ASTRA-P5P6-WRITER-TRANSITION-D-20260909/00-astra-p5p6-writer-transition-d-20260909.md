# Task Card: astra-p5p6-writer-transition-d-20260909

artifact_authority: current
task_id: `astra-p5p6-writer-transition-d-20260909`
owner: James Chen
status: ACTIVE
commit_required: true
candidate_required: true
worker_may_commit: true
worker_may_approve: false
worker_may_integrate: false
worker_may_push: false
AUTO_CHAIN: false

## Objective

Implement the source-owned canonical Runtime receipt/effect adapter over the accepted Card C writer boundary. Carry a typed loaded-registry runtime writer port through the actual canonical_task_seam.py -> BattlesuitGateway.ask_unified -> MainchainEntry.run_mainchain -> UnifiedRuntime.run chain, and through run_mainchain_replan -> UnifiedRuntime.run_replan and receipt finalization, without bypassing MainchainEntry or changing Planner selection. Require lease/context evidence before each activated Runtime receipt/effect write, exact loaded root/role/source/process identity/generation/transaction binding, and denial before bytes or dispatch for missing, stale, wrong-root, wrong-thread, replayed, forked, or mismatched bindings. Use a typed lookup of an already-loaded source-owned registry; missing lookup denies activated writes and never creates a fallback registry or new authority. Preserve accepted P6C EffectJournal, EffectDispatchPort, EffectReconcilePort, deterministic reservation/readback, replay/reconcile, and one-domain lock semantics. Scope the receipt owner guard to receipt mutation/readback and do not hold it unnecessarily across the full Runtime/model invocation; fixture evidence must cover the actual canonical run/replan/finalize chain and lease witness. Card C dependency is HEAD dcd8740a3b93ab5befb6dfbe2b3a9f382836036c tree c31d33191649aa6f7fe354add725597ceed7202b and must be independently accepted before this card is dispatched. Follow approved SOURCE_SPEC_ADDENDUM.md SHA bcedf2026499698c40ccf66c7973eaa02a1c570dbb808a2f2618eeb9f8fee2c6. Source/fixture-only work: no new release, live deployment, writer-transition authority publication, provider/API-key/SDK/Agy/native/network action, main/push/merge/approval/integration, or production claim. Preserve full P0-P8 scope and claim ceilings. AUTO_CHAIN=false. Worker may exact-scoped commit after independent review; cannot approve, integrate, or push.

## Allowed files

- `nexus/engine/canonical_task_seam.py`
- `nexus/services/gateway.py`
- `nexus/services/mainchain_entry.py`
- `nexus/services/unified_runtime.py`
- `nexus/orchestrator/writer_quiescence.py`
- `tests/services/test_loaded_runtime_owner_chain.py`
- `tests/integration/test_canonical_runtime_writer_activation.py`

## Verification commands

```bash
python3 -B -m pytest -q tests/services/test_loaded_runtime_owner_chain.py tests/integration/test_canonical_runtime_writer_activation.py
python3 -B -m pytest -q tests/engine/test_canonical_task_seam.py tests/test_battlesuit_gateway.py
python3 -B -m pytest -q tests/services/test_mainchain_entry.py tests/services/test_unified_runtime.py tests/services/test_unified_runtime_effect_fence.py tests/integration/test_unified_runtime_replan_subprocess.py
python3 -B -m pytest -q tests/events/test_effect_journal.py tests/integration/test_p6c_state_consistency.py
python3 -B -m pytest -q tests/nexus/orchestrator/test_unified_mcp_gateway.py tests/nexus/orchestrator/test_unified_mcp_gateway_http.py
python3 -B -m pytest -q tests/nexus/orchestrator/test_writer_quiescence.py tests/ops/test_writer_quiescence_receipts.py
git diff --check
```

## Exit criteria

Owner review of the exact scoped commit.

## Block classification

Unverifiable or out-of-scope mutation is a HARD_BLOCK.
