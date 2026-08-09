# Campaign Index: self-hosted-readiness-cost-20260809

artifact_authority: current
owner: James Chen
status: active, governed and sequential
AUTO_CHAIN: false

## Objective

Establish implementation authority for self-hosted readiness and honest cost
accounting. Invalid static contract or verifier input must fail before any
provider call; deterministic failures must not escalate; provider calls must
share one aggregate budget; and telemetry must distinguish measured values from
unknown values without inferring savings.

`CapabilityPlanner` and `WorkerEscalationPolicy` remain the sole routing and
escalation authorities. This campaign adds no router, planner, registry, or
provider.

## Ordered cards

| Order | Task ID | Card | Status | Dependency |
|---:|---|---|---|---|
| 0 | `SELF-HOSTED-READINESS-COST-01` | `00-SELF-HOSTED-READINESS-COST-01.md` | ACTIVE | Owner confirmation |

## Governance

- Separate from Gateway, OAuth, durable launcher, lifecycle closure, and model onboarding.
- Worker may create one scoped Candidate commit only; approval, integration, push, cleanup, and production claims remain separate.
- `AUTO_CHAIN=false`.
