# Task Card 00: Self-hosted Task-Bound Verification Entrypoint

## Identity
- task_id: `self-hosted-verification-entrypoint`
- campaign_id: `self-hosted-operator-workflow`
- artifact_authority: current
- status: NEEDS_AMENDMENT
- owner: James Chen
- commit_required: true
- candidate_required: true
- worker_may_commit: true
- worker_may_approve: false
- worker_may_integrate: false
- worker_may_push: false
- AUTO_CHAIN: false

## Goal
新增 task-bound、read-only 統一驗證入口：
`nexus self-hosted verify --task-id <TASK_ID>`

它只能執行 durable task state 中已綁定的 verifier_commands，自動套用 canonical verification environment，輸出完整 command receipt，不改變 Lifecycle 狀態、不呼叫模型、不 commit、不 approve、不 integrate。

## Non-goals
- 不接受任意 command 輸入
- 不修改 Candidate
- 不形成 Candidate commit
- 不執行 recovery
- 不 approve
- 不 integrate
- 不 push
- 不修改 Campaign 狀態
- 不新增 MCP surface
- 不執行 Fast Lane Canary

## Allowed scope
Allowed production files (4):
- `nexus/orchestrator/candidate_verifier.py`
- `nexus/orchestrator/self_hosted_task_service.py`
- `scripts/engine/commands/self_hosted_actions.py`
- `scripts/engine/nexus_cli.py`

Allowed test files (3):
- `tests/nexus/orchestrator/test_candidate_verifier.py`
- `tests/nexus/orchestrator/test_self_hosted_task_service.py`
- `tests/engine/test_self_hosted_cli.py`

Total allowed files: 7 (Strict limit <= 10).

## Implementation constraints
- Must preserve authority boundaries (read-only, no state mutation, zero provider calls).

## Review disposition
- Candidate `a2d8e764464a2a0bf3b1fac21f612cc9998a9354` is not approved for integration.
- Remaining fail-open findings are delegated to `self-hosted-verification-entrypoint-final-amendment`.

## Maximum claim
SELF_HOSTED_VERIFICATION_ENTRYPOINT_NEEDS_AMENDMENT
