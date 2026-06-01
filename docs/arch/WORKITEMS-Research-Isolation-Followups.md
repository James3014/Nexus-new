# Research Isolation Follow-up Work Items

## Scope Boundary

These items are intentionally outside ADR-014 isolation patch scope.

## Work Item A: LocalHeal Registry Alignment

- Area: `nexus/engine/capability_receipt_policy.py`
- Problem: adapter registry normalization drift (`local_heal` mismatch).
- Done when:
  - `RECEIPT_BACKED_CAPABILITIES` and `RECEIPT_ADAPTERS` normalize to the same
    set.
  - `tests/engine/test_capability_receipt_policy.py::test_receipt_backed_capabilities_match_adapter_registry_after_alias_normalization`
    passes.

## Work Item B: Tactical Route Ordering

- Area: `nexus/engine/route_tactical_policy.py`
- Problem: high-risk tactical sequence can omit `research` evidence step.
- Done when:
  - L1/L2 isolation snapshots force inclusion of `research` in tactical
    sequencing.
  - `tests/engine/test_route_tactical_policy.py::test_tactical_stop_policy_orders_and_marks_evidence_required_tools`
    passes.

## Work Item C: Planner Summary Non-Expansion Guard

- Area: planner and isolation tests.
- Problem: accidental summary growth can re-couple policy logic to planner.
- Done when:
  - tests enforce exact planner summary fields:
    `level`, `goal_visibility`, `output_mode`, `confirmation_required`.
