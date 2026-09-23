# Issue #973 — External Candidate adoption bridge R2

This Card authorizes lifecycle re-entry of the same immutable governed Candidate after the
R1 adoption attempt was canonically cancelled because its controller/runtime binding became
stale during the required Gateway rebind. R1 history remains terminal and must not be reused.

This Card does not authorize implementation changes, Candidate rewrite, runtime activation,
approval, integration, release, or production claims.

task_id: `ISSUE-973-RUNTIME-RECOVERY-GOVERNED-R2`
attempt_id: `ISSUE-973-RUNTIME-RECOVERY-GOVERNED-R2-ADOPT-1`
source_task_card: `tasks/github-issue-973-runtime-recovery-governed-20260923/00-runtime-recovery-one-shot-consumer.md`
source_candidate: `3d88a614c27e0c21a15c68dc70dc3d2193084cee`
source_base: `5e35d4fbfbf5df147a847c7dcf84fefbb7f5f471`
prior_adoption_task: `ISSUE-973-RUNTIME-RECOVERY-GOVERNED`
prior_adoption_disposition: `CANCELLED`
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

- Candidate/base/tree/diff/evidence identities remain identical to the independently reviewed R1 Candidate.
- R1 task `ISSUE-973-RUNTIME-RECOVERY-GOVERNED` must remain terminal `CANCELLED`; R2 never overwrites or retries it.
- R2 requires a fresh one-shot `CANDIDATE_ADOPT_EXTERNAL` authority bound to the live Gateway server, controller revision, Task Card hash, task, attempt, Candidate, and evidence.
- The bridge may invoke lifecycle-native Candidate verification only; worker invocations remain zero.
- Adoption stops at `PENDING_HUMAN_APPROVAL`; approval and integration are separate Owner actions.
- Runtime activation of the #973 break-glass consumer remains outside this Card.
