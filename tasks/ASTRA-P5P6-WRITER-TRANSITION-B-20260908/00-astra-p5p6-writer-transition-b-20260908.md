# Task Card: astra-p5p6-writer-transition-b-20260908

artifact_authority: current
task_id: `astra-p5p6-writer-transition-b-20260908`
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

Implement the source-owned writer admission, lease, hold, drain, and typed quiescence receipt collector consumed by Card A and Card F, preserving UNKNOWN for missing or unregistered writers and never claiming ACTIVE. Owner approved A-F source work. Card A independently accepted HEAD d4b58d6ade0b7ed2d078e4b2166695a5b5d7312e tree af7261f07d266be584b55dda9b829ab04a10a77b. Follow approved SOURCE_SPEC_ADDENDUM.md SHA bcedf2026499698c40ccf66c7973eaa02a1c570dbb808a2f2618eeb9f8fee2c6 and bounded Card B test matrix at /private/tmp/astra-writer-transition-dependency-review-20260908/CARD_B_TEST_MATRIX.md. Exactly six source files; actual source-owned root/role/process/thread/generation registry, admission leases, durable logical hold epoch, no mutex held while waiting, real Gateway service thread/assist-process and pending-action observations. Missing/orphan/unregistered writers remain UNKNOWN. Exact source-owned collector evidence integrates with accepted Card A private loader seam through Gateway, with no caller override or cross-instance rebind. Source receipt and snapshot bytes verified; no fabricated receipts. Collector produces evidence only, never ACTIVE. Adapter coverage C-E and cohort F remain separate; do not claim legacy writers drained from fixtures. Positive real fixture tests, unknown/forgery/restart/crash and concurrency verifiers required. No live hold/deployment/cutover, actual grant/authority publication, API-key/SDK/Agy/Gemini/provider/native/network, main/push/merge, cleanup or production claims. AUTO_CHAIN=false. Worker may exact scoped candidate commit after independent review; cannot approve/integrate.

## Allowed files

- `nexus/orchestrator/writer_quiescence.py`
- `nexus/orchestrator/unified_mcp_gateway.py`
- `nexus/orchestrator/self_hosted_task_service.py`
- `scripts/ops/mcp_gateway_durable.py`
- `tests/nexus/orchestrator/test_writer_quiescence.py`
- `tests/ops/test_writer_quiescence_receipts.py`

## Verification commands

```bash
python3 -B -m pytest -q tests/nexus/orchestrator/test_writer_quiescence.py tests/ops/test_writer_quiescence_receipts.py
python3 -B -m pytest -q tests/events/test_state_owner_manifest.py tests/events/test_event_writer_generation.py tests/integration/test_p6c_state_consistency.py
python3 -B -m pytest -q tests/contracts/test_gateway_deployment_contract.py
python3 -B -m pytest -q tests/nexus/orchestrator/test_state_owner_transition_service.py tests/nexus/orchestrator/test_unified_mcp_gateway.py tests/nexus/orchestrator/test_self_hosted_task_service.py
git diff --check
```

## Exit criteria

Owner review of the exact scoped commit.

## Block classification

Unverifiable or out-of-scope mutation is a HARD_BLOCK.
