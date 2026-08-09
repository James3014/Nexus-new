---
artifact_authority: current
owner: James Chen
status: READY
task_id: github-issue-6-m2-governed-dispatch
campaign_id: github-issue-6-m2-governed-dispatch-20260809
source_issue: https://github.com/James3014/Nexus-new/issues/6
AUTO_CHAIN: false
worker_may_commit: false
worker_may_approve: false
worker_may_integrate: false
worker_may_push: false
---

# Task Card: M2 Governed Dispatch

## Objective

Bind the existing Planner-produced workforce demand and canonical Workforce
Admission decision into self-hosted dispatch so only an admitted
worker/provider/model reaches WorkerRegistry execution, with durable selection
and fallback lineage.

## Inputs and dependencies

- Issue #6 is Ready.
- M1 / Issue #5 physically merged.
- Base revision: `d2e25f19dc93d2ea87a2117919a8e140ac323719`.
- `CapabilityPlanner` remains the sole route/capability-selection authority.
- `HybridRouteDecision` remains its derived decision contract/projection.

## Allowed files

- `nexus/orchestrator/self_hosted_task_service.py`
- `nexus/orchestrator/unified_mcp_gateway.py`
- `tests/nexus/orchestrator/test_self_hosted_task_service.py`
- `tests/nexus/orchestrator/test_unified_mcp_gateway.py`
- `tasks/github-issue-6-m2-governed-dispatch-20260809/INDEX.md`
- `tasks/github-issue-6-m2-governed-dispatch-20260809/00-governed-dispatch.md`

Maximum changed files: 6.

## Forbidden scope

- `nexus/engine/capability_planner.py`
- `nexus/services/runtime_workforce_admission.py`
- `nexus/executors/worker_registry.py`
- `nexus/executors/worker_contract.py`
- `nexus/orchestrator/self_hosted_mcp.py`
- `nexus/services/unified_runtime.py`
- Workforce policy/YAML, route authority, schema migration, lifecycle JSON
- Candidate approval, integration, push, cleanup, runtime activation

## Required behavior

- Consume a canonical ALLOW admission binding and its exact policy/aggregate
  identity; missing, BLOCK, ambiguous, or mismatched bindings fail closed.
- Execute only the admitted selected worker/provider/model through the existing
  WorkerRegistry path.
- Preserve explicit-provider preflight/admission constraints.
- Preserve task, attempt, scope, and admission identity across bounded fallback.
- Persist selected identity, admission binding, provider order, and fallback
  lineage in durable state/receipt.
- Do not create another route or workforce-selection authority.

## Verification

- `.venv/bin/python -m pytest -q tests/nexus/orchestrator/test_self_hosted_task_service.py tests/nexus/orchestrator/test_unified_mcp_gateway.py tests/services/test_runtime_workforce_admission.py`
- `git diff --check`
- Allowed-file, deletion, staged-diff, and card-hash audit

## Required evidence

- Exact base, task id, card path, and card SHA-256
- Positive Planner-demand/admission/registry handoff
- BLOCK/quarantined/mismatch negative tests
- Fallback/retry lineage and durable selected identity
- Independent primary-agent and separate reviewer verification

## Exit criteria

- All Issue #6 acceptance criteria are covered by physical tests.
- No forbidden file or authority surface changes.
- Required tests and diff gate pass.

## Block classification

- `RECOVERABLE_BLOCK`: bounded implementation/test defect.
- `HARD_BLOCK`: acceptance requires changing a forbidden authority or policy
  surface, or the post-M1 contract contradicts Issue #6.
