# Task Card: SELF-HOSTED-READINESS-COST-01

artifact_authority: current
task_id: `SELF-HOSTED-READINESS-COST-01`
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

Implement provider-independent self-hosted readiness and honest cost accounting:

1. Reject malformed task-contract and verifier input before the first provider call.
2. Never escalate deterministic failures; permit transient escalation only through the existing `WorkerEscalationPolicy`.
3. Enforce `maximum_provider_calls` as one aggregate budget across retries and escalated providers.
4. Aggregate actual calls, attempts, and wall time. Token/cost fields are measured or explicitly `null`/unmeasured; savings claims remain false.

Preserve `CapabilityPlanner`, `WorkerEscalationPolicy`, Candidate verification,
precommitted Candidate reuse, and salvage semantics. Add no second authority.

## Baseline and dependencies

- Canonical baseline: `d622a9b6b84e4b2f337f7eb329b27bcad2174d05`.
- Owner confirmation is present in the current continuous P0-B through P4 execution request.
- Re-check the baseline before implementation and rebase only through a clean, evidence-preserving operation.

## Allowed files

- `nexus/orchestrator/self_hosted_task_service.py`
- `nexus/orchestrator/candidate_verifier.py` (static preflight extraction only)
- `nexus/orchestrator/worker_escalation.py`
- `nexus/executors/worker_contract.py`
- `nexus/executors/worker_registry.py` (classification/budget receipt propagation only)
- `tests/nexus/orchestrator/test_self_hosted_task_service.py`
- `tests/nexus/orchestrator/test_candidate_verifier.py`
- `tests/nexus/orchestrator/test_worker_escalation.py`
- `tests/nexus/orchestrator/test_candidate_commit.py`
- `tests/nexus/executors/test_worker_contract.py`
- `tests/nexus/orchestrator/test_task_contract.py`

## Forbidden scope

- Gateway/MCP, OAuth, durable launcher/state schema, lifecycle JSON/API, route defaults, workforce policy, provider onboarding, or another planner/router/registry.
- Approval, integration, merge, push, cleanup, ref deletion, reload, live lifecycle execution, or production/cost-savings claims.
- Any path outside the allowed files and these two authority files.

## RED -> GREEN gates

- Static invalid verifier/contract: provider invoke count remains zero.
- Failure taxonomy: deterministic blocks; timeout/auth/quota/transient may escalate.
- Aggregate budget: max 1 permits one actual provider call; max 2 permits at most two total across providers.
- Telemetry: ordered executions plus summed calls/attempts/wall time; token/cost measured or null with explicit status; `savings_claim_allowed=false`.
- Candidate/reuse/salvage tests remain green and no verifier result is fabricated.

## Verification

```bash
PYTHONDONTWRITEBYTECODE=1 /Users/jameschen/Workspace/nexus/.venv/bin/python -m pytest -q -p no:cacheprovider \
  tests/nexus/orchestrator/test_self_hosted_task_service.py \
  tests/nexus/orchestrator/test_candidate_verifier.py \
  tests/nexus/orchestrator/test_worker_escalation.py \
  tests/nexus/orchestrator/test_candidate_commit.py \
  tests/nexus/executors/test_worker_contract.py \
  tests/nexus/orchestrator/test_task_contract.py
git diff --check
git diff --name-status
git diff --stat
git diff --cached --name-status
git diff --cached --stat
```

## Exit and block rules

- Commit the authority files separately before implementation.
- Implementation requires one scoped commit bound to this card hash and exact test evidence.
- `RECOVERABLE_BLOCK` covers retryable test/environment failures.
- `HARD_BLOCK` covers scope expansion, unverifiable metrics, authority bypass, or a second router/planner/registry.
