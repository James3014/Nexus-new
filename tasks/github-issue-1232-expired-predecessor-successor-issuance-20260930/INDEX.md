# Campaign Index: github-issue-1232-expired-predecessor-successor-issuance-20260930

artifact_authority: current
owner: James Chen
status: active, governed and sequential
AUTO_CHAIN: false

## Objective

Fix Issue #1232 by separating structural predecessor identity reads from live standing-grant authority reads: allow an exact expired same-key predecessor hash to support Owner-confirmed successor CAS without making the expired receipt live authority; keep revoked, malformed, wrong-key, wrong-hash, missing-predecessor, action-widening without explicit requested actions, and conflicting no-CAS paths fail-closed; preserve canonical keyed storage, locking, atomic write, readback, idempotent replay, and AUTO_CHAIN=false.

## Ordered cards

| Order | Task ID | Card | Status | Dependency |
|---:|---|---|---|---|
| 0 | `issue-1232-expired-predecessor-successor-issuance` | `00-issue-1232-expired-predecessor-successor-issuance.md` | ACTIVE | Owner confirmation |
