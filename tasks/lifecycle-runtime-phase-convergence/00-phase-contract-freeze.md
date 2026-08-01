# Task Card: runtime-phase-contract-freeze

artifact_authority: draft-successor
owner: James Chen
status: DRAFT_PENDING_OWNER_ACTIVATION
task_id: runtime-phase-contract-freeze
commit_required: true
AUTO_CHAIN: false

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
candidate commit.
