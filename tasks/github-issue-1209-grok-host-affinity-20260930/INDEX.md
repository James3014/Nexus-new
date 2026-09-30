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
| 0 | `issue-1209-grok-host-affinity` | `00-issue-1209-grok-host-affinity.md` | SUPERSEDED | R5 scope correction required by exact-base CI |
| 1 | `issue-1209-grok-host-affinity` | `01-issue-1209-grok-host-affinity-r5.md` | SUPERSEDED | R5 Agy implementation complete; R6 reconciles final PR scope projection |
| 2 | `issue-1209-grok-host-affinity` | `02-issue-1209-grok-host-affinity-r6.md` | SUPERSEDED | R6 exposed base-stability requirement in trusted merge-lane gate |
| 3 | `issue-1209-grok-host-affinity` | `03-issue-1209-grok-host-affinity-r7.md` | ACTIVE | Base-stable final integration contract; six product/test/doc paths |
