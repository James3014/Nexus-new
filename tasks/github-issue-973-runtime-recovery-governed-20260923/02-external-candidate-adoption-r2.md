# Issue #973 — External Candidate adoption bridge R2

This is a second lifecycle re-entry Card for the same immutable governed Candidate after the first adoption task was terminally cancelled by a Gateway restart before Candidate creation.
It does not authorize implementation changes, Candidate rewrite, runtime activation,
approval, integration, release, or production claims.

task_id: `ISSUE-973-RUNTIME-RECOVERY-GOVERNED-ADOPT-R2`
attempt_id: `ISSUE-973-RUNTIME-RECOVERY-GOVERNED-ADOPT-R2`
source_task_card: `tasks/github-issue-973-runtime-recovery-governed-20260923/00-runtime-recovery-one-shot-consumer.md`
source_candidate: `3d88a614c27e0c21a15c68dc70dc3d2193084cee`
source_base: `5e35d4fbfbf5df147a847c7dcf84fefbb7f5f471`
independent_review_artifact_sha256: `ec602688d26be1e69f3de7f16e21ca4016431c420845cc34e849821e2d61dca0`

`AUTO_CHAIN=false`

## Allowed repository paths

- `nexus/contracts/break_glass_recovery.py`
- `nexus/orchestrator/break_glass_recovery.py`
- `scripts/ops/break_glass_recovery.py`
- `tests/contracts/test_break_glass_recovery_contract.py`
- `tests/nexus/orchestrator/test_break_glass_recovery.py`
- `docs/specs/NEXUS_BREAK_GLASS_RECOVERY_001.md`
- `docs/governance/rollback_runbook.md`
- `docs/agents/TASK_EXECUTION_CONTRACT.md`

## Forbidden scope

- `scripts/ops/mcp_gateway_durable.py`
- `nexus/contracts/gateway_deployment.py`
- `tasks/**`

## Exact verification commands

- `uv run pytest -q tests/contracts/test_break_glass_recovery_contract.py tests/nexus/orchestrator/test_break_glass_recovery.py`
- `uv run pytest -q tests/ops/test_bootstrap_authority_files.py::test_external_bootstrap_recovery_boundary_is_fail_closed`
- `uv run ruff check nexus/contracts/break_glass_recovery.py nexus/orchestrator/break_glass_recovery.py scripts/ops/break_glass_recovery.py tests/contracts/test_break_glass_recovery_contract.py tests/nexus/orchestrator/test_break_glass_recovery.py`
- `uv run ruff format --check --preview nexus/contracts/break_glass_recovery.py nexus/orchestrator/break_glass_recovery.py scripts/ops/break_glass_recovery.py tests/contracts/test_break_glass_recovery_contract.py tests/nexus/orchestrator/test_break_glass_recovery.py`
- `uv run python -m py_compile nexus/contracts/break_glass_recovery.py nexus/orchestrator/break_glass_recovery.py scripts/ops/break_glass_recovery.py`
- `git diff --check`

## Re-entry invariants

- Candidate commit/tree/diff must remain physically identical to the values above.
- The bridge may invoke lifecycle-native Candidate verification only; worker invocations must remain zero.
- Independent review must remain bound to the exact Candidate and must report no blocking/material source defect.
- Adoption stops at `PENDING_HUMAN_APPROVAL`; approval and integration are separate Owner actions.
- Runtime activation remains outside this Card and still requires separate exact Owner runtime authority.
