# Task Card: runtime-phase-contract-freeze

artifact_authority: current
owner: James Chen
status: VERIFIED_CANDIDATE
task_id: runtime-phase-contract-freeze
commit_required: true
AUTO_CHAIN: false
candidate_commit: a8b23a85829039c4fe6734be2752aa7c91877377
claim_ceiling: IMPLEMENTER_VERIFIED_RUNTIME_PHASE_CONTRACT_FREEZE_CANDIDATE

verification_receipt:
  base_head: 4ef2a03b9c40b5ea31d8cd56c9bee9ffc4f62fe4
  activation_commit: 44508f8da6d76eef1993f0d854d5e9f7c9394397
  card_hash_at_execution: 8070998bdf6b7c233a9f6711d4e18a39a6d27d2aa9d56ee11f1a8f9e6aca914d
  focused_tests: 20 passed
  diff_check: PASS
  evidence_scope: contract_identity_transitions_status_vocabulary_and_d_x_d
  external_acceptance: DEFERRED_EXTERNAL_ACCEPTANCE

## Objective

Implement the machine-readable Runtime Phase Contract V1 and deterministic
tests for phase identity, legal transitions, status vocabulary and the
`D → X → D` continuation semantics.

## Allowed files

- `docs/arch/LIFECYCLE_RUNTIME_PHASE_CONTRACT.md`
- `nexus/engine/runtime_phase_contract.py`
- `tests/engine/test_runtime_phase_contract.py`

## Forbidden scope

No route selection, MCP surface, development lifecycle mutation, memory-store
replacement, direct JSON state edit, approval/integration/push, or protected
main cleanup.

## Verification

```bash
uv run pytest -q tests/engine/test_runtime_phase_contract.py
git diff --check
```

## Exit criteria

One importable contract is the only phase/transition definition, all illegal
transitions fail closed, and the test receipt is bound to the card hash and
candidate commit. Owner review, integration and production/public claims
remain pending.
