---
type: Concept
title: OpenWiki Entrypoint & Task-Routing Quickstart
description: Central entrypoint for navigating the Nexus Singularity OS documentation, component relationships, task routing, and V3 classifications.
tags: [quickstart, overview, navigation, openwiki]
openwiki:
  roles: [architecture, domain]
  change_kinds: [public-api]
  source_paths: [scripts/engine/nexus_cli.py, nexus/engine/capability_planner.py]
  symbols: [nexus, CapabilityPlanner]
  test_paths: [tests/test_cli_commands.py, tests/engine/test_runtime_phase_contract.py, tests/nexus/orchestrator/test_self_hosted_task_service.py]
  invariants: [CapabilityPlanner is sole route and capability-selection authority. HybridRouteDecision is Planner-derived. OpenWiki is derived_non_authoritative.]
  validation_commands: [pytest tests/ops/test_openwiki_source_contract.py -q]
---

# OpenWiki Entrypoint & Task-Routing Quickstart

Welcome to the **Nexus Singularity OS OpenWiki knowledge base**. This documentation is a repository-derived implementation observation layer provided to assist engineers and future autonomous agents in understanding codebase architecture, runtime wiring, execution boundaries, and change recipes.

> ⚠️ **Authority Contract Ceiling**: This OpenWiki is `derived_non_authoritative`. `AGENTS.md` remains repository/agent authority. `CapabilityPlanner` remains the sole route and capability-selection authority. `HybridRouteDecision` is a Planner-derived decision contract/projection, not a second selector, router, or planner. OpenWiki must never create, infer, promote, or duplicate route, approval, integration, or governance authority.

---

## 🗺️ System Architecture Map

The Nexus Singularity OS knowledge base is organized into seven core concept domains:

1. **[Architecture Overview](architecture/overview.md)**: Explains the canonical `S → P → D → X → R → A → C` runtime phase contract, the task-scoped `UnifiedRuntime` seam, and task-continuity projection boundaries.
2. **[Capability Planner & Routing Authority](routing/capability-planner.md)**: Documents `CapabilityPlanner` as the sole route/capability-selection authority and `HybridRouteDecision` as its derived decision payload.
3. **[MCP Gateway & Ingress Protocols](runtime/mcp-gateway.md)**: Covers the Model Context Protocol execution gateway, HTTP/stdio transport adapters, and self-hosted MCP servers.
4. **[CLI Commands & Cueline Operations](runtime/cli-and-cueline.md)**: Details the primary `nexus` CLI surface, Cueline adapter, durable self-hosted task service, and bounded NightShift queue path.
5. **[Governance Gates & Completion Contracts](governance/gates-and-contracts.md)**: Explains fail-closed completion, independent Candidate acceptance, operator outcome receipts, and non-mutating GitHub merge-intent preparation.
6. **[GitHub Actions & CI/CD Lanes](workflows/github-actions.md)**: Catalogs all 10 GitHub Actions workflows and their exact trigger modes.
7. **[Validation Suites & Benchmarks](testing/validation-and-benchmarks.md)**: Categorizes unit, integration, governance, runtime-contract, and benchmark test suites with focused quiet validation commands.

---

## 🧭 Task-Routing Table

Use this matrix to navigate directly from user intent to implementation entrypoints, key symbols, test coverage, and minimal validation commands:

| Change Area / User Intent | Relevant Wiki Page | Exact Source Entry Points | Important Symbols / Types | Focused Tests | Minimal Validation Command |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **Runtime Phase Contract & Core Pipeline** | [Architecture Overview](architecture/overview.md) | `nexus/engine/runtime_phase_contract.py`<br>`nexus/engine/pipeline.py`<br>`nexus/services/unified_runtime.py` | `RuntimePhase`<br>`RUNTIME_PHASE_FLOW`<br>`NexusPipeline`<br>`UnifiedRuntime` | `tests/engine/test_runtime_phase_contract.py`<br>`tests/test_service_decomposition.py` | `pytest tests/engine/test_runtime_phase_contract.py -q` |
| **Routing & Capability Selection** | [Routing Authority](routing/capability-planner.md) | `nexus/engine/capability_planner.py`<br>`nexus/contracts/canonical_execution.py`<br>`nexus/contracts/hybrid_route.py` | `CapabilityPlanner`<br>`CanonicalPlanningBundle`<br>`HybridRouteDecision`<br>`CapabilityPlan` | `tests/engine/test_capability_planner.py`<br>`tests/contracts/test_canonical_execution.py` | `pytest tests/engine/test_capability_planner.py tests/contracts/test_canonical_execution.py -q` |
| **MCP Tools & Ingress Handling** | [MCP Gateway](runtime/mcp-gateway.md) | `nexus/orchestrator/unified_mcp_gateway.py`<br>`nexus/orchestrator/self_hosted_mcp.py`<br>`nexus/orchestrator/self_hosted_mcp_http.py` | `UnifiedMCPGateway`<br>`NexusSelfHostedMCPServer` | `tests/nexus/orchestrator/test_unified_mcp_gateway.py`<br>`tests/nexus/orchestrator/test_mcp_canonical_ingress.py` | `pytest tests/nexus/orchestrator/test_unified_mcp_gateway.py tests/nexus/orchestrator/test_mcp_canonical_ingress.py -q` |
| **CLI, Self-Hosted Task Lifecycle & Cueline** | [CLI & Cueline](runtime/cli-and-cueline.md) | `scripts/engine/nexus_cli.py`<br>`scripts/ops/nexus_cueline_worker.py`<br>`nexus/orchestrator/self_hosted_task_service.py`<br>`nexus/core/task_continuity.py` | `nexus`<br>`SelfHostedTaskService`<br>`ContinuitySnapshot` | `tests/test_cli_commands.py`<br>`tests/nexus/orchestrator/test_self_hosted_task_service.py`<br>`tests/core/test_task_continuity.py` | `pytest tests/nexus/orchestrator/test_self_hosted_task_service.py tests/core/test_task_continuity.py -q` |
| **Independent Candidate Acceptance & GitHub Merge Intent** | [Governance Gates](governance/gates-and-contracts.md) | `nexus/orchestrator/acceptance_loop.py`<br>`nexus/contracts/github_orchestration.py`<br>`nexus/orchestrator/github_orchestration.py` | `CandidateAcceptanceResult`<br>`GitHubOrchestrationEvidence`<br>`MergeIntent` | `tests/nexus/orchestrator/test_acceptance_loop.py`<br>`tests/contracts/test_github_orchestration.py`<br>`tests/nexus/orchestrator/test_github_orchestration.py` | `pytest tests/nexus/orchestrator/test_acceptance_loop.py tests/contracts/test_github_orchestration.py tests/nexus/orchestrator/test_github_orchestration.py -q` |
| **Operator Outcome Evidence** | [Governance Gates](governance/gates-and-contracts.md) | `nexus/contracts/operator_outcome_receipt.py` | `OperatorOutcomeReceipt`<br>`build_operator_outcome_receipt` | `tests/contracts/test_operator_outcome_receipt.py` | `pytest tests/contracts/test_operator_outcome_receipt.py -q` |
| **NightShift Bounded Candidate Queue** | [CLI & Cueline](runtime/cli-and-cueline.md) | `nexus/app/nightshift_runner_service.py`<br>`nexus/services/nightshift_queue_consumer.py` | `AutoResearchNightShift`<br>`NightshiftQueueConsumer` | `tests/services/test_nightshift_queue_consumer.py`<br>`tests/ops/test_issue111_nightshift_impact_map.py` | `pytest tests/services/test_nightshift_queue_consumer.py tests/ops/test_issue111_nightshift_impact_map.py -q` |
| **Delivery Gates & Completion** | [Governance Gates](governance/gates-and-contracts.md) | `nexus/engine/completion_enforcer.py`<br>`nexus/engine/completion_contract.py` | `CompletionEnforcer`<br>`build_completion_envelope` | `tests/test_task_runner_completion_gate.py`<br>`tests/test_iron_gate_governance.py` | `pytest tests/test_task_runner_completion_gate.py -q` |
| **CI/CD Workflow Triggers** | [GitHub Actions](workflows/github-actions.md) | `.github/workflows/*.yml` | Workflows (`openwiki-update`, `pytest`, `trusted-deletion-anchor`) | `tests/ops/test_openwiki_source_contract.py` | `pytest tests/ops/test_openwiki_source_contract.py -q` |
| **Testing & Benchmark Verification** | [Validation Suites](testing/validation-and-benchmarks.md) | `tests/`<br>`nexus/benchmark/` | `pytest`<br>`SWE-bench` subset | `tests/test_v9_regression_p1.py` | `pytest tests/test_v9_regression_p1.py -q` |

---

## 📊 Core V3 Classification Summary Index

Under the **Nexus OpenWiki Implementation-Wiki Contract**, every material subsystem claim is explicitly classified across six mandatory axes:

```yaml
component: CapabilityPlanner
implementation_status: CURRENT
wiring_status: WIRED
runtime_surfaces:
  - LOCAL_RUNTIME
authority_roles:
  - ROUTE_AUTHORITY
evidence_basis:
  - nexus/engine/capability_planner.py:CapabilityPlanner
  - nexus/contracts/canonical_execution.py:_ROUTE_AUTHORITY
  - nexus/services/unified_runtime.py:CapabilityPlanner
claim_ceiling: Sole canonical route and capability-selection authority for the task-scoped runtime seam.
```

```yaml
component: HybridRouteDecision
implementation_status: CURRENT
wiring_status: UNKNOWN
runtime_surfaces: []
authority_roles:
  - NONE
evidence_basis:
  - nexus/contracts/hybrid_route.py:HybridRouteDecision
  - nexus/contracts/hybrid_route.py:route_truth_source
claim_ceiling: Planner-derived immutable decision payload whose route_truth_source is CapabilityPlanner; this definition alone does not prove a runtime surface.
```

```yaml
component: RuntimePhaseContract
implementation_status: CURRENT
wiring_status: WIRED
runtime_surfaces:
  - LOCAL_RUNTIME
authority_roles:
  - NONE
evidence_basis:
  - nexus/engine/runtime_phase_contract.py:RUNTIME_PHASE_FLOW
  - nexus/engine/pipeline.py:CANONICAL_STAGE_FLOW
claim_ceiling: Canonical runtime phase and transition contract used by NexusPipeline; it does not own routing, approval, integration, or learning authority.
```

```yaml
component: SelfHostedTaskService
implementation_status: CURRENT
wiring_status: WIRED
runtime_surfaces:
  - LOCAL_RUNTIME
authority_roles:
  - EXECUTION_AUTHORITY
evidence_basis:
  - nexus/orchestrator/self_hosted_task_service.py:SelfHostedTaskService
  - nexus/orchestrator/self_hosted_task_service.py:CandidateAcceptanceResult
claim_ceiling: Durable restartable task-service facade that consumes existing lifecycle, acceptance, workforce, and continuity contracts without replacing their authorities.
```

```yaml
component: OpenWiki
implementation_status: CURRENT
wiring_status: WIRED
runtime_surfaces:
  - CI
authority_roles:
  - DERIVED_ONLY
evidence_basis:
  - openwiki/INSTRUCTIONS.md
  - .github/workflows/openwiki-update.yml:on.workflow_dispatch
claim_ceiling: Derived repository observation layer maintained through a manual-only CI workflow; holds zero runtime, governance, route, approval, integration, or release authority.
```

---

## 📋 Concept Relationship Map

- `NexusPipeline` derives `CANONICAL_STAGE_FLOW` from the runtime phase contract `S → P → D → X → R → A → C`.
- `UnifiedRuntime` is a provider-neutral task-scoped Online/Local execution seam and invokes `CapabilityPlanner` for canonical planning.
- `HybridRouteDecision` carries Planner-derived route facts; it is not a second route authority.
- `SelfHostedTaskService` composes existing task, workforce, Candidate verification, independent acceptance, integration, and continuity contracts into a durable service facade.
- `reduce_candidate_acceptance()` never performs approval, integration, merge, or public-claim promotion.
- GitHub orchestration prepares a bounded merge intent from fresh checks/reviews/impact/independent-acceptance evidence; the intent remains `mutation_authorized=false`.
- OpenWiki remains navigation-only and must be verified against current source, tests, or bound runtime evidence.

---

## 📑 Backlog

| Area | Source Anchor | Reason / Status |
| :--- | :--- | :--- |
| **Governed Wiki Vault Integration** | `nexus_wiki_vault/` | Out of scope by contract. Vault is governed separately and excluded via `.openwikiignore`. |
| **Historical Task Cards** | `tasks/` | Out of scope by contract. Task cards represent governed execution state and are excluded via `.openwikiignore`. |
