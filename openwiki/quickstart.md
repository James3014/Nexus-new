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
  test_paths: [tests/test_cli_commands.py]
  invariants: [CapabilityPlanner is sole route authority. OpenWiki is derived_non_authoritative.]
  validation_commands: [pytest tests/test_cli_commands.py -q]
---

# OpenWiki Entrypoint & Task-Routing Quickstart

Welcome to the **Nexus Singularity OS OpenWiki knowledge base**. This documentation is a repository-derived implementation observation layer provided to assist engineers and future autonomous agents in understanding codebase architecture, runtime wiring, execution boundaries, and change recipes.

> ⚠️ **Authority Contract Ceiling**: This OpenWiki is `derived_non_authoritative`. `AGENTS.md` remains repository/agent authority. `CapabilityPlanner` and `HybridRouteDecision` remain sole Nexus route authority. OpenWiki must never create, infer, promote, or duplicate route or governance authority.

---

## 🗺️ System Architecture Map

The Nexus Singularity OS knowledge base is organized into six core concept domains:

1. **[Architecture Overview](architecture/overview.md)**: Explains the P-X-D-R-A-C (Plan, Execute, Diagnose, Research, Audit, Crystallize) engine lifecycle, process isolation via `SanitizedRunner`, and execution streaming via `AsyncProcessExecutor`.
2. **[Capability Planner & Routing Authority](routing/capability-planner.md)**: Documents `CapabilityPlanner` and `HybridRouteDecision`, the sole route authorities governing capability selection and topology planning across all runtime surfaces.
3. **[MCP Gateway & Ingress Protocols](runtime/mcp-gateway.md)**: Covers the Model Context Protocol execution gateway, HTTP/stdio transport adapters, and self-hosted MCP servers.
4. **[CLI Commands & Cueline Operations](runtime/cli-and-cueline.md)**: Details the primary `nexus` CLI surface (`scripts/engine/nexus_cli.py`), command delivery modes (`ask`, `high`), health check levels, and `nexus-cueline-worker` background task execution.
5. **[Governance Gates & Completion Contracts](governance/gates-and-contracts.md)**: Explains delivery verification gates, completion contract envelopes, and `CompletionEnforcer` fail-closed verification.
6. **[GitHub Actions & CI/CD Lanes](workflows/github-actions.md)**: Catalogs all 12 GitHub Actions workflows, distinguishing scheduled triggers, manual dispatches, and event hooks.
7. **[Validation Suites & Benchmarks](testing/validation-and-benchmarks.md)**: Categorizes unit, integration, and benchmark test suites with quiet validation commands.

---

## 🧭 Task-Routing Table

Use this matrix to navigate directly from user intent to implementation entrypoints, key symbols, test coverage, and minimal validation commands:

| Change Area / User Intent | Relevant Wiki Page | Exact Source Entry Points | Important Symbols / Types | Focused Tests | Minimal Validation Command |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **System Lifecycle & Core Runtime** | [Architecture Overview](architecture/overview.md) | `nexus/services/unified_runtime.py`<br>`scripts/engine/nexus_cli.py` | `UnifiedRuntime`<br>`SanitizedRunner`<br>`AsyncProcessExecutor` | `tests/test_cli_deadlock_and_injection.py`<br>`tests/test_service_decomposition.py` | `pytest tests/test_cli_deadlock_and_injection.py -q` |
| **Routing & Capability Selection** | [Routing Authority](routing/capability-planner.md) | `nexus/engine/capability_planner.py`<br>`nexus/contracts/hybrid_route.py` | `CapabilityPlanner`<br>`HybridRouteDecision`<br>`CapabilityPlan` | `tests/test_lite_route_oracle.py`<br>`tests/test_route_optimization.py` | `pytest tests/test_lite_route_oracle.py -q` |
| **MCP Tools & Ingress Handling** | [MCP Gateway](runtime/mcp-gateway.md) | `nexus/orchestrator/unified_mcp_gateway.py`<br>`nexus/orchestrator/self_hosted_mcp_http.py` | `UnifiedMCPGateway`<br>`NexusSelfHostedMCPServer` | `tests/test_battlesuit_gateway.py` | `pytest tests/test_battlesuit_gateway.py -q` |
| **CLI Commands & Subcommands** | [CLI & Cueline](runtime/cli-and-cueline.md) | `scripts/engine/nexus_cli.py`<br>`scripts/ops/nexus_cueline_worker.py` | `nexus` (Click group)<br>`NexusCLI`<br>`main` | `tests/test_cli_commands.py`<br>`tests/test_cli_dispatch.py` | `pytest tests/test_cli_commands.py -q` |
| **Delivery Gates & Completion** | [Governance Gates](governance/gates-and-contracts.md) | `nexus/engine/completion_enforcer.py`<br>`nexus/engine/completion_contract.py` | `CompletionEnforcer`<br>`build_completion_envelope` | `tests/test_task_runner_completion_gate.py`<br>`tests/test_iron_gate_governance.py` | `pytest tests/test_task_runner_completion_gate.py -q` |
| **CI/CD Workflow Triggers** | [GitHub Actions](workflows/github-actions.md) | `.github/workflows/*.yml` | Workflows (`openwiki-update`, `benchmark-ci`, `pytest`) | `tests/test_script_entrypoints.py` | `pytest tests/test_script_entrypoints.py -q` |
| **Testing & Benchmark Verification** | [Validation Suites](testing/validation-and-benchmarks.md) | `tests/`<br>`nexus/benchmark/` | `pytest`<br>`SWE-bench` subset | `tests/test_v9_regression_p1.py` | `pytest tests/test_v9_regression_p1.py -q` |

---

## 📊 Core V3 Classification Summary Index

Under the **Nexus OpenWiki Implementation-Wiki Contract**, every material subsystem claim is explicitly classified across six mandatory axes:

```yaml
component: CapabilityPlanner
implementation_status: CURRENT
wiring_status: WIRED
runtime_surfaces:
  - MAIN_CLI
  - MCP_GATEWAY
  - LOCAL_RUNTIME
authority_roles:
  - ROUTE_AUTHORITY
evidence_basis:
  - nexus/engine/capability_planner.py:CapabilityPlanner
  - nexus/contracts/canonical_execution.py:_ROUTE_AUTHORITY
claim_ceiling: Sole canonical selection authority for capabilities and execution topology planning.
```

```yaml
component: HybridRouteDecision
implementation_status: CURRENT
wiring_status: WIRED
runtime_surfaces:
  - MAIN_CLI
  - MCP_GATEWAY
  - LOCAL_RUNTIME
authority_roles:
  - ROUTE_AUTHORITY
evidence_basis:
  - nexus/contracts/hybrid_route.py:HybridRouteDecision
  - nexus/services/mainchain_route_freeze.py:HybridRouteDecision
claim_ceiling: Immutable route decision payload bound to CapabilityPlanner truth source.
```

```yaml
component: UnifiedMCPGateway
implementation_status: CURRENT
wiring_status: WIRED
runtime_surfaces:
  - MCP_GATEWAY
authority_roles:
  - EXECUTION_AUTHORITY
evidence_basis:
  - nexus/orchestrator/unified_mcp_gateway.py:UnifiedMCPGateway
  - nexus/orchestrator/self_hosted_mcp_http.py:NexusSelfHostedMCPServer
claim_ceiling: MCP tool ingress and execution gateway; delegates capability route decisions to CapabilityPlanner.
```

```yaml
component: NexusCLI
implementation_status: CURRENT
wiring_status: WIRED
runtime_surfaces:
  - MAIN_CLI
authority_roles:
  - EXECUTION_AUTHORITY
evidence_basis:
  - pyproject.toml:[tool.poetry.scripts].nexus
  - scripts/engine/nexus_cli.py:nexus
claim_ceiling: Primary interactive and script CLI entrypoint; executes commands via SanitizedRunner and AsyncProcessExecutor.
```

```yaml
component: CompletionEnforcer
implementation_status: CURRENT
wiring_status: WIRED
runtime_surfaces:
  - MAIN_CLI
  - MCP_GATEWAY
  - LOCAL_RUNTIME
authority_roles:
  - GOVERNANCE_AUTHORITY
evidence_basis:
  - nexus/engine/completion_enforcer.py:CompletionEnforcer
  - nexus/engine/completion_contract.py:ensure_verified_completion
claim_ceiling: Enforces physical completion envelope verification before task delivery closeout.
```

```yaml
component: OpenWiki
implementation_status: CURRENT
wiring_status: WIRED
runtime_surfaces:
  - LOCAL_RUNTIME
authority_roles:
  - DERIVED_ONLY
evidence_basis:
  - openwiki/INSTRUCTIONS.md
  - .github/workflows/openwiki-update.yml
claim_ceiling: Derived repository observation layer; holds zero governance, route, approval, or release authority.
```

---

## 📋 Concept Relationship Map

- The primary `[NexusCLI](runtime/cli-and-cueline.md)` dispatches task execution requests to `[UnifiedRuntime](architecture/overview.md)`.
- `[UnifiedRuntime](architecture/overview.md)` queries `[CapabilityPlanner](routing/capability-planner.md)` for route authorization and capability graph construction.
- External MCP calls received by `[UnifiedMCPGateway](runtime/mcp-gateway.md)` delegate route selection to `[CapabilityPlanner](routing/capability-planner.md)`.
- Task delivery verification across both CLI and MCP surfaces is enforced by `[CompletionEnforcer](governance/gates-and-contracts.md)`.
- System changes are verified in CI by `[GitHub Actions Workflows](workflows/github-actions.md)` executing `[Validation Suites](testing/validation-and-benchmarks.md)`.

---

## 📑 Backlog

| Area | Source Anchor | Reason / Status |
| :--- | :--- | :--- |
| **Governed Wiki Vault Integration** | `nexus_wiki_vault/` | Out of scope by contract. Vault is governed separately and excluded via `.openwikiignore`. |
| **Historical Task Cards** | `tasks/` | Out of scope by contract. Task cards represent governed execution state and are excluded via `.openwikiignore`. |
