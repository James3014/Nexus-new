# Task Card: issue-1232-expired-predecessor-successor-issuance

artifact_authority: current
task_id: `issue-1232-expired-predecessor-successor-issuance`
owner: James Chen
status: ACTIVE
execution_lane: GOVERNED
commit_required: true
candidate_required: true
worker_may_commit: true
worker_may_approve: false
worker_may_integrate: false
worker_may_push: false
AUTO_CHAIN: false

## Objective

Fix Issue #1232 by separating structural predecessor identity reads from live standing-grant authority reads: allow an exact expired same-key predecessor hash to support Owner-confirmed successor CAS without making the expired receipt live authority; keep revoked, malformed, wrong-key, wrong-hash, missing-predecessor, action-widening without explicit requested actions, and conflicting no-CAS paths fail-closed; preserve canonical keyed storage, locking, atomic write, readback, idempotent replay, and AUTO_CHAIN=false.

## Allowed files

- `nexus/orchestrator/unified_mcp_gateway.py`
- `nexus/orchestrator/standing_grant_store.py`
- `tests/nexus/orchestrator/test_unified_mcp_gateway.py`
- `tests/nexus/orchestrator/test_standing_grant_store.py`

## Verification commands

```bash
python3 -m pytest -q tests/nexus/orchestrator/test_unified_mcp_gateway.py -k 'owner_standing_grant_issue'
python3 -m pytest -q tests/nexus/orchestrator/test_standing_grant_store.py -k 'structural or expired_or_revoked or keyed'
python3 -m pytest -q tests/nexus/orchestrator/test_unified_mcp_gateway_http.py -k 'owner_standing_grant_issue'
git diff --check
```

## Exit criteria

Owner review of the exact scoped commit.

## Block classification

Unverifiable or out-of-scope mutation is a HARD_BLOCK.
