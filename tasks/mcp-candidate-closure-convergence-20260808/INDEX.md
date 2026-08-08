# Campaign Index: mcp-candidate-closure-convergence-20260808

artifact_authority: current
owner: James Chen
status: active, governed and sequential
AUTO_CHAIN: false

## Objective

Repair the canonical Nexus MCP Candidate closure contract without creating a new router, planner, lifecycle, or parallel integration authority. The defect is reproduced: public nexus_candidate_approve can persist Owner approval but public nexus_candidate_integrate then fails with EXTERNAL_ACCEPTANCE_REQUIRED because the live public schema has no way to persist ExternalAcceptanceReceipt and IntegrationAuthorizationEnvelope; nexus_task_finish(ISOLATED_TARGET) is also unable to provide those required closure objects. Preserve CapabilityPlanner and HybridRouteDecision route authority. Use SelfHostedTaskService as the only lifecycle-state persistence authority. Add the minimum typed public plumbing and one idempotent service-level closure-binding path so an already APPROVED exact Candidate can bind an independently produced external acceptance receipt plus Owner integration authorization, then proceed through the existing integrate_approved path. Exact replay of the same closure binding may be idempotent; mismatched task/attempt/task-card/candidate commit/tree/state/verified-receipt/acceptance hash/branch/action-set bindings must fail closed. Do not hand-edit lifecycle JSON, bypass consumed Owner approval, weaken existing one-shot approval checks, add a generic state-mutation API, create a second integration manager, change worker/provider selection, change route authority, push, cleanup, auto-chain, or make production/public claims. Preserve the already-approved LIFECYCLE-AUTHORITY-REMEDIATION-01 Candidate so it can be recovered after this fix without re-running Agy. Stop with HARD_BLOCK if the repair requires files outside the allowed scope or authority beyond this exact closure convergence.

## Ordered cards

| Order | Task ID | Card | Status | Dependency |
|---:|---|---|---|---|
| 0 | `MCP-CANDIDATE-CLOSURE-CONVERGENCE-01` | `00-MCP-CANDIDATE-CLOSURE-CONVERGENCE-01.md` | SOURCE_COMPLETE | Owner confirmation |
| 1 | `MCP-CANDIDATE-CLOSURE-CONSUMED-APPROVAL-01` | `01-MCP-CANDIDATE-CLOSURE-CONSUMED-APPROVAL-01.md` | SOURCE_COMPLETE | Order 0 source complete; live pre-apply reproduction `ARCHITECTURE_APPROVAL_EXPIRED` |
| 2 | `MCP-CANDIDATE-CLOSURE-REBIND-01` | `02-MCP-CANDIDATE-CLOSURE-REBIND-01.md` | ACTIVE | Orders 0-1 source complete; pre-apply canonical HEAD/runtime drift |
