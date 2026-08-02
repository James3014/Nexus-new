# Task Card: runtime-phase-transition-integration

artifact_authority: current
owner: James Chen
status: VERIFIED_CANDIDATE
task_id: runtime-phase-transition-integration
commit_required: true
AUTO_CHAIN: false
candidate_commit: a02506fe0f4c797d9d6398eab28142b012aa3c20
claim_ceiling: IMPLEMENTER_VERIFIED_RUNTIME_PHASE_TRANSITION_CANDIDATE

verification_receipt:
  base_head: 28ab0ac7d3a3c0f1d43a5d8b882c32bca0e0e6f4
  card_hash_at_execution: d7ee2fff748a2e1767b644c883502e73e58e3152dfdac8e68553c7c68e54f661
  focused_tests: 8 passed
  affected_regression: 40 passed
  diff_check: PASS
  evidence_scope: p_d_x_d_research_boundary_r_a_rejection_and_hard_guard
  external_acceptance: DEFERRED_EXTERNAL_ACCEPTANCE

## Objective

Make the existing Pipeline consult the frozen contract for phase start/end,
research continuation, audit rejection and hard/recoverable block behavior
without creating a second executor or changing route authority.

## Allowed files

- `nexus/engine/pipeline.py`
- `nexus/engine/pipeline_repair.py`
- `nexus/engine/runtime_phase_contract.py`
- `tests/engine/test_pipeline_phase_contract.py`
- `tests/engine/test_pipeline_stage_flow.py`

## Verification

```bash
uv run pytest -q tests/engine/test_pipeline_phase_contract.py tests/engine/test_pipeline_stage_flow.py
git diff --check
```

## Exit criteria

No illegal transition reaches an executor; `A → R`, `A → D`, `D → X → D`,
`RECOVERABLE_BLOCK` and `HARD_BLOCK` are covered by deterministic tests, and
existing successful pipeline behavior remains equivalent.
