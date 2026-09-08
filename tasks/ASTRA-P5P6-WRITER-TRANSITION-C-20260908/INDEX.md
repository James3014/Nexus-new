# Campaign Index: ASTRA-P5P6-WRITER-TRANSITION-C-20260908

artifact_authority: current
owner: James Chen
status: active, governed and sequential
AUTO_CHAIN: false

## Objective

Implement the source-owned task-state production adapter and no-write HTTP bootstrap over the accepted Card B collector boundary, preserving the existing legacy/unactivated auto_reconcile behavior while activated roots require a fresh operation-scoped writer lease and P6C owner context before any state write. Bind the exact loaded task-state root, role, source/process identity, writer generation, hold epoch, and transaction; route _write_state, _create_state, _mutate_state, reconciliation, and direct locked callers through the adapter; retain the no-second-domain-lock rule and deny missing, stale, wrong-thread, replayed, forked, or wrong-root bindings before bytes change. Card B dependency is HEAD 549a85cdadf9ed1c15052c296a1f2c63c5d36ea3 tree d7caa4dc3ef7bfa8c9d0725583bc3484863f5c4f and must be independently accepted before this card is dispatched. Follow approved SOURCE_SPEC_ADDENDUM.md SHA bcedf2026499698c40ccf66c7973eaa02a1c570dbb808a2f2618eeb9f8fee2c6. Acceptance requires meaningful positive, denial, lease-witness, lock-selection, hold/reacquisition, HTTP no-write bootstrap, restart/PARTIAL_UNKNOWN, and legacy regression evidence. Card C may acknowledge and observe a hold but must not release Card B admission or claim ACTIVE; Card F owns cohort release. Source/fixture-only work: no new release, live deployment, writer-transition authority publication, provider/API-key/SDK/Agy/native/network action, main/push/merge/approval/integration, or production claim. AUTO_CHAIN=false. Worker may exact-scoped commit after independent review; cannot approve, integrate, or push.

## Ordered cards

| Order | Task ID | Card | Status | Dependency |
|---:|---|---|---|---|
| 0 | `astra-p5p6-writer-transition-c-20260908` | `00-astra-p5p6-writer-transition-c-20260908.md` | ACTIVE | Owner confirmation |
