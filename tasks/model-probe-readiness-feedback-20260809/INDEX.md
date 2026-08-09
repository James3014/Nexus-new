# Campaign Index: model-probe-readiness-feedback-20260809

artifact_authority: current
owner: James Chen
status: active, governed and sequential
AUTO_CHAIN: false

## Objective

Close the existing provider-readiness loop so a successful exact model probe
becomes bounded durable evidence consumed by the next provider preflight and by
`nexus_worker_candidate`. Preserve fail-closed execution readiness and project
persisted terminal worker failures into compact status/wait blockers.

## Ordered cards

| Order | Task ID | Card | Status | Dependency |
|---:|---|---|---|---|
| 0 | `MODEL-PROBE-READINESS-FEEDBACK-01` | `00-MODEL-PROBE-READINESS-FEEDBACK-01.md` | ACTIVE | Owner request; canonical `a19d5357...` |

## Governance

- `eff7697055b743fae857be0dd0f46fb65d1128e6` is review evidence only. It is
  not a lifecycle Candidate and must not be merged or edited in place.
- `CapabilityPlanner` and `HybridRouteDecision` remain the only route
  authority. This campaign adds no router, planner, registry, worker, or public
  tool.
- The active legacy-seam rationalization campaign remains paused for Gateway
  overlap until this Candidate is independently accepted and integrated.
- The separate durable-launcher expected-HEAD and OAuth-client persistence work
  is externally owned and forbidden here.
- A Luna worker may create one scoped implementation commit. Approval,
  integration, reload, live provider proof, cleanup, push, and public claims
  remain primary/Owner actions.
