# Task Card 02: Recovery Command Surfaces Integration

## Identity
- task_id: `self-hosted-lifecycle-recovery-surfaces`
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
將經 Task 01 硬化的 verified-uncommitted recovery 能力正式接到 MCP 與 CLI，並證明無法繞過 approval／integration authority。

## Non-goals
- 不修改核心 recovery semantics
- 不自行 integrate
- 不新增平行 Lifecycle service
- 不新增 Router
- 不修改 GitHub Actions

## Owner decisions
- MCP 與 CLI 命令介面必須嚴格經由 Task 01 硬化之 `SelfHostedTaskService`。

## Source and start state
- Starting branch: `nexus/integration/main` after Task 01 integration
- Target worktree: Isolated workspace target root
- Task 01 integration commit: `a99c71d8c0628e1d383adaf3a905cad2c6b1b7f4`
- Dependency gate: Task 01 integration commit is an ancestor of Task 02 starting HEAD.
- Task 02 has not started.
- No Target has been created.
- AUTO_CHAIN=false.

## Authority map
- Selection authority: Model Workforce policy / existing CapabilityPlanner constraints
- Execution authority: Agy bounded Candidate generation
- Verification authority: CandidateVerifier + exact tests
- Receipt authority: SelfHostedTaskService durable state
- Approval authority: James / independent reviewer
- Integration authority: ControlledIntegrationManager

## Allowed scope
Allowed production files (3):
- `nexus/orchestrator/self_hosted_mcp.py`
- `scripts/engine/commands/self_hosted_actions.py`
- `scripts/engine/nexus_cli.py`

Allowed test files (4):
- `tests/nexus/orchestrator/test_self_hosted_mcp.py`
- `tests/nexus/orchestrator/test_self_hosted_mcp_http.py`
- `tests/engine/test_self_hosted_cli.py`
- `tests/nexus/orchestrator/test_workflow_repair.py`

Total allowed files: 7 (Strict limit <= 10).

## Unknown scan
- Evaluated existing MCP actions and CLI subcommands in `scripts/engine/` and `tests/engine/test_self_hosted_cli.py`.

## Mandatory source audit
- Audit MCP recovery tool definitions to ensure parameters require explicit task_id.

## Start-state classification
EVIDENCE_INSUFFICIENT

## RED or existing-guard proof
Physical seams verified before implementation:
- MCP recovery tool / CLI recovery command is absent before Task 02.
- Recovery call with unknown task_id fails.
- Recovery call for non-verified task status fails.
- Recovery call cannot approve or integrate candidate.
- Returned status from MCP/CLI surface is candidate state only, never APPROVED or INTEGRATED.

## Implementation constraints
- Must preserve authority boundaries (no auto-approval from MCP/CLI).

## GREEN and regression gates
- `test_self_hosted_mcp.py`, `test_self_hosted_mcp_http.py`, and `test_self_hosted_cli.py` pass.
- Clean diff check.

## Mandatory command manifest
Required command receipt format: `command_id`, `cwd`, `exact_command`, `exit_code`, `passed`, `failed`, `skipped`, `duration`.
```bash
/usr/bin/env GIT_CONFIG_NOSYSTEM=1 GIT_CONFIG_GLOBAL=/dev/null PYTHONDONTWRITEBYTECODE=1 python3 -m pytest -q tests/nexus/orchestrator/test_self_hosted_mcp.py tests/nexus/orchestrator/test_self_hosted_mcp_http.py tests/engine/test_self_hosted_cli.py
git diff --check
git diff --name-status --diff-filter=D
git diff --cached --name-status --diff-filter=D
git diff --stat
git diff --cached --stat
```

## Physical evidence
- starting_head: `fcd8d933514ec41de41b6dc9b3471a8596fca118`
- candidate_commit: `2455f80a2df998eb7608c8d1d076e70dd76fe069`
- candidate_tree: `1e6d624bb128304023e998c681a5bd359755344f`
- integration_commit: `c78b7138d2008fb71cc18f31becef069bc03354c`
- integration_branch: `nexus/integration/main`
- post_integration_recovery_surface_tests: `65 passed`
- post_integration_core_non_regression: `62 passed`
- provider_calls_during_recovery: `0`
- maximum_recovery_status: `PENDING_HUMAN_APPROVAL`
- tracked_deletions: `0`

## Independent review
Required human review by James Chen prior to integration.

## Exit conditions
- MCP and CLI surfaces expose recovery actions cleanly.
- Status set to `CANDIDATE_READY`.

## RECOVERABLE_BLOCK / HARD_BLOCK
- RECOVERABLE_BLOCK: Port or transport binding error during test.
- HARD_BLOCK: Bypass of approval authority or scope creep outside allowed 7 files.

## Maximum claim
SELF_HOSTED_RECOVERY_SURFACES_INTEGRATED
