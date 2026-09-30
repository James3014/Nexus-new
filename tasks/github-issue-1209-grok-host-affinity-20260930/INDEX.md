# Campaign Index: github-issue-1209-grok-host-affinity-20260930

artifact_authority: current
owner: James Chen
status: active, governed and sequential
AUTO_CHAIN: false

## Objective

Implement Issue #1209: make the existing Grok credential pool host-affine with a stable non-secret host binding, expose host ownership readback, fail closed on wrong-host use before provider execution, preserve host-sync exclusion of credentials/leases, document supported multi-host behavior, and verify both wrong-host negative and owner-host positive paths without creating a second router/account authority or distributed lease service.

## Ordered cards

| Order | Task ID | Card | Status | Dependency |
|---:|---|---|---|---|
| 0 | `issue-1209-grok-host-affinity` | `00-issue-1209-grok-host-affinity.md` | ACTIVE | Owner confirmation |
