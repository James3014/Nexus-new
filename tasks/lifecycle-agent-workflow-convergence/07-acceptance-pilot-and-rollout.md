# Task Card: lifecycle-workflow-p7-acceptance-rollout

artifact_authority: current
owner: James Chen
status: VERIFIED_PENDING_OWNER_REVIEW
task_id: lifecycle-workflow-p7-acceptance-rollout
commit_required: true
candidate_required: true
worker_may_commit: true
worker_may_approve: false
worker_may_integrate: false
worker_may_push: false
AUTO_CHAIN: false

## Objective

Run the lifecycle acceptance matrix, prove no unnecessary Target creation,
prove cleanup/recovery, and validate the GPT connector smoke path.

## Dependencies

- `lifecycle-workflow-p6-approval-reconnect-drift` integrated.

P6 is verified on canonical HEAD with generic tracked/Owner Inline approval
binding and exact focused suites. The Owner's continuing full-goal request
activates this acceptance implementation card; Cline live execution remains a
separate downstream provider gate.

## Allowed files

- `scripts/ops/nexus_mcp_gateway_acceptance.py`
- `tests/nexus/orchestrator/test_unified_mcp_gateway.py`
- `tests/nexus/orchestrator/test_unified_mcp_gateway_http.py`
- `tests/nexus/orchestrator/test_workflow_repair.py`
- `docs/arch/LIFECYCLE_AGENT_WORKFLOW_CONTRACT.md`

## Verification

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPYCACHEPREFIX=/tmp/nexus-p7-pycache uv run pytest -q tests/nexus/orchestrator/test_unified_mcp_gateway.py tests/nexus/orchestrator/test_unified_mcp_gateway_http.py tests/nexus/orchestrator/test_workflow_repair.py
PYTHONDONTWRITEBYTECODE=1 PYTHONPYCACHEPREFIX=/tmp/nexus-p7-pycache uv run python scripts/ops/nexus_mcp_gateway_acceptance.py
git diff --check
```

## Exit criteria

`active_targets=0`, `duplicate_commits=0`, all non-terminal tasks have one
next_action, protected main is unchanged, push is false, and one live
`nexus01` smoke covers read, Direct, and Candidate disposition.

## Verification receipt

- candidate_commit: `5e290d095`
- local_matrix: `PASS`
- matrix_counts: `read=20, direct=10, assisted=5, isolated=5, duplicate=5, reconcile=3, dispose=3`
- route_decision_p95_ms: `0.944`
- status_snapshot_p95_ms: `0.167`
- target_created: `5` (isolated lane only), `active_targets=0`
- max_active_targets: `1`
- duplicate_commits: `0`
- unknown_nonterminal_next_actions: `0`
- unmapped_worktrees: `0` (the retained parser checkout is classified external-active)
- gateway_workflow_tests: `69 passed, 1 warning` (current post-Cline suite)
- gateway_http_tests: `5 passed, 1 warning`
- gateway_stdio_self_test: `PASS (24 tools)` at commit `04fc0d959`
- temporary_loopback_health: `tool_count=24`,
  `tool_manifest_revision=6c1b0339…`, `reload_required=false` at commit
  `04fc0d959`; this is local Gateway evidence, not GPT connector evidence
- external_proxy_commit: `2d1efff955a9013dfb016deca775f88cf8cdd605`
- external_proxy_tests_and_typecheck: `PASS`
- external_proxy_artifact_sha256: `7155a3b777d8d04fffe3c56536eb8dcb97244edd2b0ae25c0f9ea7d769b3f3a0`
- public_synthetic_tools_list: `PASS (24 tools, approval.v2 schema visible)`
- live_nexus01_smoke: `NOT_PROVEN_AFTER_24_TOOL_RELOAD` (acceptance harness
  rerun reports `NOT_RUN`; public synthetic OAuth proof is separate)
- claim_ceiling: `LOCAL_GATEWAY_ACCEPTANCE_PASS`
- remaining_blocker: `GPT_TO_NEXUS_LIFECYCLE_WORKFLOW_ACCEPTANCE_PASS requires fresh nexus01 reconnect plus read/Direct/Candidate smoke`

## Block classification

- `HARD_BLOCK`: live claim ceiling cannot be proven or public MCP count differs.
- `RECOVERABLE_BLOCK`: provider/connector/environment failure with evidence retained.
