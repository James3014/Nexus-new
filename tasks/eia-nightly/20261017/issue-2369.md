# Task Card: EIA nightly eia-nightly-20261017-i2369

## Identity

- task_id: `eia-nightly-20261017-i2369`
- campaign_id: `eia-nightly`
- artifact_authority: current
- status: ACTIVE
- owner: James Chen
- commit_required: true
- candidate_required: true
- worker_may_commit: true
- worker_may_approve: false
- worker_may_integrate: false
- worker_may_push: false
- AUTO_CHAIN: false
- allow_deletions: false
- execution_lane: `DIRECT_DELEGATED`
- capability_disposition: `EXTEND_EXISTING`
- capability_ids: `nexus_core_domain_runtime`

## Objective

Resolve GitHub Issue #2369: gateway_health_hmac: fsync key before link; pin the exact 64-hex length rule (follow-up to 2226). gateway_health_hmac: fsync the temp key file before os.link, and add a test with a 66-char even-length key proving the exact 64-hex length rule.

The full problem statement is the body of Issue #2369 (difficulty: easy).

## Allowed files

- `scripts/ops/gateway_health_hmac.py`
- `tests/nexus/orchestrator/test_unified_mcp_gateway_http.py`

## Required implementation

Change only the allowed files so that the behaviour described in Issue #2369 holds. Keep
every existing public name and signature working.

## Forbidden scope

No workflow, configuration, dependency, Task Card or control-plane changes; no deletions;
no files outside the allowed list.

## Verification commands

```bash
python3 -m pytest -q -p no:cacheprovider tests/nexus/orchestrator/test_unified_mcp_gateway_http.py
```

## Claim ceiling

`TASK_CANDIDATE_VERIFIED_PENDING_INDEPENDENT_ACCEPTANCE` only. This card grants no approval,
merge, integration or release authority.
