---
artifact_authority: current
owner: James Chen
status: ACTIVE_LIVE_CLOSURE
task_id: agy-account-pool-real-manager-runtime-closure
campaign_id: agy-account-pool-runtime
depends_on: candidate-commit-git-home-isolation-recovery integrated
commit_required: true
candidate_required: true
worker_may_commit: true
worker_may_approve: false
worker_may_integrate: false
worker_may_push: false
AUTO_CHAIN: false
---

# Task Card: AGY Real Account-Pool Runtime Closure

## Objective

Replace the false-green memory-only account pool with the installed manager runtime at `~/.nexus/agy-account-pool/bin/agy-cli-manager`, consumed only by self-hosted `AgyWorkerAdapter`. Preserve route authority, keep the feature flag default off, and produce a verified Candidate ready for human approval.

## Inputs and authority

- `docs/arch/MODEL_WORKFORCE_POLICY.md`
- `nexus/config/model_workforce.yaml`
- `Nexus_多模型分級協作工作規範_v2.1_20260729.md`
- Plan A handoff supplied by the Owner
- Current Controller revision and this card hash, revalidated immediately before submission

## Allowed files

- `nexus/services/agy_account_pool.py`
- `nexus/executors/worker_registry.py`
- `nexus/executors/worker_contract.py`
- `tests/services/test_agy_account_pool.py`
- `tests/nexus/executors/test_worker_contract.py`
- `tests/nexus/orchestrator/test_self_hosted_task_service.py`

## Forbidden scope

- `nexus/services/unified_runtime.py`
- `CapabilityPlanner`, `HybridRouteDecision`, committee routing, workforce authority files
- provider/model downgrade or alternate router
- legacy dirty checkout `/Users/jameschen/Workspace/nexus`
- manager credentials, account email/token, raw HOME, raw stderr/stdout in receipts
- global/repository Git config or hooks, `--no-verify`, tracked deletion, push, protected-main merge
- feature flag enablement by default

## Required behavior

- Disabled mode is backward compatible: no manager call, one AGY subprocess, no rotation.
- Enabled mode calls absolute manager `ensure-active` before invocation.
- Only explicit quota/auth classification may call `rotate-after-failure`; timeout, generic process, semantic/test, Git, and MCP failures never rotate.
- At most two rotations and three AGY subprocess calls; stable `task_id`, unique attempt IDs, unique redacted account alias hashes, cooldown respected.
- Manager unavailable, invalid JSON, invalid runtime HOME, or pool exhaustion fail closed as `AGY_ACCOUNT_POOL_EXHAUSTED` or a typed manager error.
- AGY credential HOME is passed only to the AGY subprocess; outer process and Candidate Git HOME remain unchanged.
- Receipts contain only redacted alias hashes, attempt index, failure class, manager action, exit code, timing, and hashes.

## Verification commands

- `/usr/bin/env GIT_CONFIG_NOSYSTEM=1 GIT_CONFIG_GLOBAL=/dev/null GIT_AUTHOR_NAME=Nexus\\ Test GIT_AUTHOR_EMAIL=nexus-test@localhost GIT_COMMITTER_NAME=Nexus\\ Test GIT_COMMITTER_EMAIL=nexus-test@localhost PYTHONDONTWRITEBYTECODE=1 python3 -m pytest -q tests/services/test_agy_account_pool.py tests/nexus/executors/test_worker_contract.py tests/nexus/orchestrator/test_self_hosted_task_service.py`
- `/usr/bin/env GIT_CONFIG_NOSYSTEM=1 GIT_CONFIG_GLOBAL=/dev/null PYTHONDONTWRITEBYTECODE=1 python3 -m compileall -q nexus/services/agy_account_pool.py nexus/executors/worker_registry.py nexus/executors/worker_contract.py`
- `git diff --check`
- physical manager smoke: absolute-path `status --json`, `ensure-active --json`, runtime HOME validation, one harmless AGY invocation; output must be sanitized before receipt

## Evidence required

- real manager executable and runtime root verified
- provider/client failures separated from semantic failures
- disabled compatibility, manager command contract, redaction, identity stability, rotation bounds, non-quota no-rotation, and pool exhaustion tests
- no direct product-layer route change
- Candidate commit, durable ref, verified receipt hash, and cleanup receipt

## Claim ceiling

Allowed: `REAL_MANAGER_ENTRYPOINT_VERIFIED`, `REAL_ACCOUNT_SELECTION_VERIFIED`, `POOL_DISABLED_COMPATIBILITY_VERIFIED`, `BOUNDED_ROTATION_MAX_2`, `MAX_AGY_SUBPROCESS_CALLS=3`, `ROTATION_ONLY_ON_QUOTA_OR_AUTH`, `NON_QUOTA_FAILURE_DOES_NOT_ROTATE`, `ACCOUNT_IDENTITY_REDACTED`, `FEATURE_FLAG_DEFAULT_OFF`, `PLAN_A_CANDIDATE_READY`.

Forbidden: `REAL_QUOTA_ROTATION_PHYSICALLY_VERIFIED`, `PRODUCTION_READY`, `PUBLIC_CLAIM_ALLOWED`, merge, push, or self-approval claims.

## Stop and block

Stop and preserve Target on manager path/state failure, credential or HOME leakage, rotation reuse, scope drift, privacy failure, verifier failure, candidate binding mismatch, or any request to modify route authority. Classify temporary environment/runtime issues as `RECOVERABLE_BLOCK`; authority, safety, or evidence-integrity conflicts as `HARD_BLOCK`.
