# Task Card 01: Core Lifecycle Hardening

## Identity
- task_id: `self-hosted-lifecycle-core-hardening`
- campaign_id: `self-hosted-lifecycle-repair`
- artifact_authority: current
- status: INTEGRATED
- owner: James Chen
- commit_required: true
- candidate_required: true
- worker_may_commit: true
- worker_may_approve: false
- worker_may_integrate: false
- worker_may_push: false
- AUTO_CHAIN: false

## Goal
修復並硬化 Self-hosted Lifecycle 核心執行邏輯與狀態驗證機制。

## Non-goals
- 不修改 P0 功能
- 不修改 P0 durable state
- 不啟動 P2
- 不新增 Router、Agent、Planner、Verifier 或 Receipt authority
- 不修改 GitHub Actions
- 不新增 CI workflow
- 不修改 Model Workforce 政策
- 不 approve
- 不 integrate
- 不 push

## Owner decisions
- 修復範圍限 Self-hosted Lifecycle 核心模組與單元測試。
- 不得自動連帶啟動 Task 02。

## Source and start state
- Starting branch: `nexus/integration/main` after Task 00 integration
- Target worktree: Isolated workspace target root
- Required dependency evidence: Task 00 integration commit must be an ancestor of the Task 01 starting HEAD.

## Authority map
- Selection authority: Model Workforce policy / existing CapabilityPlanner constraints
- Execution authority: Agy bounded Candidate generation
- Verification authority: CandidateVerifier + exact tests
- Receipt authority: SelfHostedTaskService durable state
- Approval authority: James / independent reviewer
- Integration authority: ControlledIntegrationManager

## Allowed scope
Allowed production files (4):
- `nexus/orchestrator/self_hosted_task_service.py`
- `nexus/orchestrator/candidate_commit.py`
- `nexus/orchestrator/governed_integration.py`
- `nexus/orchestrator/worktree_manager.py`

Allowed test files (5):
- `tests/nexus/orchestrator/test_workflow_repair.py`
- `tests/nexus/orchestrator/test_self_hosted_task_service.py`
- `tests/nexus/orchestrator/test_candidate_commit.py`
- `tests/nexus/orchestrator/test_governed_integration.py`
- `tests/nexus/orchestrator/test_worktree_manager.py`

Total allowed files: 9 (Strict limit <= 10).

## Unknown scan
- Evaluated existing unit tests under `tests/nexus/orchestrator/`.

## Mandatory source audit & RED Seams
Verified 10 production RED seams that must fail before implementation:
1. `build_contract()` with no explicit target root returns `/private/tmp` or bypasses canonical resolver.
2. production submit without required lifecycle identity creates state or Target instead of failing.
3. Fast Lane eligible request invokes fallback or provider more than once.
4. verified-uncommitted recovery accepts target HEAD != lease.initial_head.
5. candidate-ref failure still produces PENDING_HUMAN_APPROVAL.
6. record_integration() accepts an unverified arbitrary SHA.
7. commit failure deletes or loses the verified Target.
8. durable state fails to persist `lifecycle_revision`, `lifecycle_executable_path`, and `worker_module_path`.
9. `test_verified_target_preserved_when_commit_fails` fails to simulate real commit failure.
10. `test_mcp_disconnect_does_not_delete_verified_target` fails to simulate real finalizer failure.

## Mandatory Preflight Checks
Before editing code, worker MUST verify:
- `card.task_id == lifecycle.task_id`
- `task_card_path` exists
- `task_card_hash` matches Git-tracked content
- `INDEX` current frontier == `task_id`
- `AUTO_CHAIN == false`
- Task 00 integration commit is ancestor of starting HEAD

## Start-state classification
DEFECT_REPRODUCED

## RED or existing-guard proof
- Execution of `python3 -m pytest -q tests/nexus/orchestrator/test_workflow_repair.py` against baseline before fix must catch/fail on unhandled defect scenarios.

## Implementation constraints
- Must enforce Git environment isolation (`GIT_CONFIG_NOSYSTEM=1`, `GIT_CONFIG_GLOBAL=/dev/null`).
- Provider calls in Fast Lane strictly capped at 1.

## GREEN and regression gates
- All collected tests in `tests/nexus/orchestrator/` pass: 0 failed, 0 unexpected skipped.
- 0 tracked deletion.
- Clean diff check.

## Mandatory command manifest
Required command receipt format: `command_id`, `cwd`, `exact_command`, `exit_code`, `passed`, `failed`, `skipped`, `duration`.
```bash
/usr/bin/env GIT_CONFIG_NOSYSTEM=1 GIT_CONFIG_GLOBAL=/dev/null PYTHONDONTWRITEBYTECODE=1 python3 -m pytest -q tests/nexus/orchestrator/test_workflow_repair.py
/usr/bin/env GIT_CONFIG_NOSYSTEM=1 GIT_CONFIG_GLOBAL=/dev/null PYTHONDONTWRITEBYTECODE=1 python3 -m pytest -q tests/nexus/orchestrator/test_self_hosted_task_service.py
/usr/bin/env GIT_CONFIG_NOSYSTEM=1 GIT_CONFIG_GLOBAL=/dev/null PYTHONDONTWRITEBYTECODE=1 python3 -m pytest -q tests/nexus/orchestrator/test_candidate_commit.py
/usr/bin/env GIT_CONFIG_NOSYSTEM=1 GIT_CONFIG_GLOBAL=/dev/null PYTHONDONTWRITEBYTECODE=1 python3 -m pytest -q tests/nexus/orchestrator/test_governed_integration.py
/usr/bin/env GIT_CONFIG_NOSYSTEM=1 GIT_CONFIG_GLOBAL=/dev/null PYTHONDONTWRITEBYTECODE=1 python3 -m pytest -q tests/nexus/orchestrator/test_worktree_manager.py
/usr/bin/env GIT_CONFIG_NOSYSTEM=1 GIT_CONFIG_GLOBAL=/dev/null PYTHONDONTWRITEBYTECODE=1 python3 -m pytest -q tests/nexus/orchestrator/
python3 -m compileall nexus/orchestrator/self_hosted_task_service.py nexus/orchestrator/candidate_commit.py nexus/orchestrator/governed_integration.py nexus/orchestrator/worktree_manager.py
git diff --check
git diff --name-status --diff-filter=D
git diff --cached --name-status --diff-filter=D
git diff --stat
git diff --cached --stat
```

## Physical evidence
- starting_head: `756d62a5d6748e32eac321b8b64ff91846cc27a2`
- candidate_commit: `c369288c485c7238412f35a25d7caa76713679bf`
- candidate_tree: `d3b867980074fc969069739c270b8ef6dad03345`
- integration_commit: `a99c71d8c0628e1d383adaf3a905cad2c6b1b7f4`
- integration_branch: `nexus/integration/main`
- post_integration_orchestrator_tests: `235 passed`
- post_integration_mcp_http_cli_tests: `40 passed`
- git_environment: `GIT_CONFIG_NOSYSTEM=1`, `GIT_CONFIG_GLOBAL=/dev/null`
- bare_pytest_observation: `PREEXISTING_ENVIRONMENTAL_CONTAMINATION caused by user global core.hooksPath; not treated as Task 01 regression`

## Independent review
Required human review by James Chen prior to integration.

## Exit conditions
- All 10 defect items fixed and verified by explicit unit tests.
- Preflight checks verified.
- Candidate commit formed under isolated environment.
- Status set to `INTEGRATED`.

## RECOVERABLE_BLOCK / HARD_BLOCK
- RECOVERABLE_BLOCK: Test fixture failure or transient filesystem lock.
- HARD_BLOCK: Modification outside allowed 9 files or scope creep into GitHub Actions / P2.

## Maximum claim
SELF_HOSTED_CORE_HARDENING_INTEGRATED
