# Campaign Index: Lifecycle Agent Workflow Convergence

artifact_authority: current
owner: James Chen
status: active, governed and sequential
source_specification: /Users/jameschen/.codex/attachments/cdd553cb-7acc-4ff3-92a0-fb32b4a0a3f1/pasted-text-1.txt
AUTO_CHAIN: false

## Objective

Converge the existing Nexus MCP facade and self-hosted lifecycle into a fast,
restartable, evidence-bound delivery loop. Small tasks stay on the canonical
checkout; isolated Targets are reserved for explicit risk or Candidate work.

## Authority boundaries

- Canonical root: `/Users/jameschen/Workspace/nexus`.
- Route authority remains `CapabilityPlanner` / `HybridRouteDecision`.
- `nexus/orchestrator/self_hosted_task_service.py` remains lifecycle authority.
- The public surface remains one Gateway; the self-hosted MCP is an internal provider.
- Workers may commit within a card; they may not approve, integrate, push, or clean up their own Candidate.
- `AUTO_CHAIN=false`; every successor requires a fresh Owner gate.
- This campaign does not alter `model-workforce-v21-runtime-closure` or the AGY account-pool campaign.

## Ordered cards

| Order | Task ID | Card | Status | Dependency |
|---:|---|---|---|---|
| 0 | `lifecycle-workflow-p0-authority-baseline` | `00-authority-and-baseline.md` | COMPLETED | none |
| 1 | `lifecycle-workflow-p1-action-envelope` | `01-lifecycle-action-envelope.md` | IN_PROGRESS | P0 commit `eb41555f5` |
| 2 | `lifecycle-workflow-p2-durable-canonical-actions` | `02-durable-direct-action-state.md` | PENDING | P1 integrated |
| 3 | `lifecycle-workflow-p3-fast-three-lane-dispatch` | `03-three-lane-fast-dispatch.md` | PENDING | P2 integrated |
| 4 | `lifecycle-workflow-p4-public-recovery-actions` | `04-public-recovery-surface.md` | PENDING | P3 integrated |
| 5 | `lifecycle-workflow-p5-enforcement-permissions` | `05-enforcement-and-permissions.md` | PENDING | P4 integrated |
| 6 | `lifecycle-workflow-p6-approval-reconnect-drift` | `06-approval-reconnect-definition-drift.md` | PENDING | P5 integrated |
| 7 | `lifecycle-workflow-p7-acceptance-rollout` | `07-acceptance-pilot-and-rollout.md` | PENDING | P6 integrated |

## Residual campaigns

- Skills/Handoff updates are a separate machine-local campaign after P6.
- Memory/Learning lineage is a separate campaign after P6 and after the active workforce learning gate is resolved.

## P0 exit

P0 may commit only the campaign authority and contract. Runtime mutation begins
at P1 through the formal lifecycle surface and the current frontier card.

## Current frontier

`lifecycle-workflow-p1-action-envelope` is the only executable card. No
successor may start until it receives a scoped commit, verification evidence,
and explicit promotion through the formal lifecycle surface.
