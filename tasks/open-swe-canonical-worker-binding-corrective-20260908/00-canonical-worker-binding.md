# Task Card: canonical-worker-binding

artifact_authority: current
task_id: `canonical-worker-binding`
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

Correct resident External Intelligence ingress so GitHub Issue prose is never Workforce authority. After source lineage and Task Card validation but before any semantic or worker effect, derive the exact demand and obtain one canonical CapabilityPlanner plus Workforce Admission ALLOW binding; carry that binding unchanged through semantic request, fanout unit, replay, and receipt validation. Fail closed before dispatch on missing, ambiguous, blocked, stale, or mismatched binding. Preserve #853 r1-r7 as immutable prior attempts and never resend any OUTCOME_UNKNOWN operation. Do not change workforce policy, routing policy, provider defaults, authorization, publication, or merge behavior.

## Allowed files

- `scripts/ops/external_intelligence_service.py`
- `nexus/services/external_intelligence_automation.py`
- `tests/services/test_external_intelligence_service.py`
- `tests/services/test_external_intelligence_automation.py`
- `tests/services/test_open_swe_worker_transport.py`

## Verification commands

```bash
uv run pytest -q tests/services/test_external_intelligence_automation.py tests/services/test_external_intelligence_service.py tests/services/test_open_swe_worker_transport.py
uv run ruff check scripts/ops/external_intelligence_service.py nexus/services/external_intelligence_automation.py tests/services/test_external_intelligence_service.py tests/services/test_external_intelligence_automation.py tests/services/test_open_swe_worker_transport.py
git diff --check
```

## Exit criteria

Owner review of the exact scoped commit.

## Block classification

Unverifiable or out-of-scope mutation is a HARD_BLOCK.
