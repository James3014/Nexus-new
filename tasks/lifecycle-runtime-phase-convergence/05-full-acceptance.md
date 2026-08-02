# Task Card: runtime-full-acceptance

artifact_authority: current
owner: James Chen
status: VERIFIED_CANDIDATE
task_id: runtime-full-acceptance
commit_required: true
AUTO_CHAIN: false
candidate_commit: 00df552ecdd328b1b58d42772c8ed0ed57f44e03
claim_ceiling: IMPLEMENTER_VERIFIED_RUNTIME_PHASE_CONVERGENCE_CANDIDATE

verification_receipt:
  base_head: 8ea1bfe7ca431b6db82d6ba12cb39f5c73d7b7c5
  card_hash_at_execution: d455b957f25b4cd73d1f82dc7b99430c08fb2a21
  focused_tests: 32 passed
  acceptance_runner: PASS_LOCAL_CANDIDATE, 5 checks passed
  diff_check: PASS
  evidence_scope: runtime_phase_transitions_receipts_identity_mapping_learning_closure_and_local_acceptance_matrix
  external_acceptance: DEFERRED_EXTERNAL_ACCEPTANCE

## Objective

Run the complete runtime/development/memory acceptance matrix after Cards 0–4
and current P7 disposition are independently verified.

## Allowed files

- `scripts/ops/nexus_runtime_lifecycle_acceptance.py`
- `tests/engine/test_runtime_phase_contract.py`
- `tests/engine/test_pipeline_phase_contract.py`
- `tests/engine/test_pipeline_phase_hooks.py`
- `tests/engine/test_runtime_learning_closure.py`
- `docs/arch/LIFECYCLE_RUNTIME_PHASE_CONTRACT.md`

## Verification

```bash
uv run pytest -q tests/engine/test_runtime_phase_contract.py tests/engine/test_pipeline_phase_contract.py tests/engine/test_pipeline_phase_hooks.py tests/engine/test_runtime_learning_closure.py
uv run python scripts/ops/nexus_runtime_lifecycle_acceptance.py
git diff --check
```

## Exit criteria

Read-only, Direct, Assisted, Isolated Candidate, reconnect, timeout,
definition drift, approval rejection, Candidate disposition, `A → R`,
`A → D`, `D → X → D`, `HARD_BLOCK`, `RECOVERABLE_BLOCK` and terminal C side
effects all pass with receipt-bound evidence. No public or production claim is
made by the worker.
