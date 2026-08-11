---
type: Concept
title: OpenWiki Entrypoint & Task-Routing Quickstart
description: Derived navigation for the Nexus repository; current authority lives in AGENTS.md and executable contracts.
tags: [quickstart, overview, navigation, openwiki]
openwiki:
  roles: [architecture, domain]
  change_kinds: [public-api]
  source_paths: [scripts/engine/nexus_cli.py, nexus/engine/capability_planner.py]
  symbols: [nexus, CapabilityPlanner]
  test_paths: [tests/ops/test_codex_task_context_index.py]
  invariants: [CapabilityPlanner is sole route authority. OpenWiki is derived_non_authoritative.]
  validation_commands: [python3 -m pytest -q tests/ops/test_codex_task_context_index.py]
---

# OpenWiki quickstart

OpenWiki is a repository-derived observation and navigation layer. It is
`derived_non_authoritative`: `AGENTS.md`, task cards, and executable contracts
remain authoritative. OpenWiki cannot create, infer, promote, or duplicate
route, governance, approval, lifecycle, or release authority.

## Start with canonical developer surfaces

- [Repository README](../README.md): portable core/provider setup split and the
  test command matrix.
- [Contributing guide](../CONTRIBUTING.md): bounded change and evidence rules.
- [Testing runbook](../docs/testing/test_runbook.md): current verification
  commands and claim ceilings.
- [Codex context index](../configs/codex_task_context_index.json): bounded,
  non-authoritative task retrieval map.

The context index is validated by:

```bash
python3 scripts/ops/validate_codex_context_index.py configs/codex_task_context_index.json
```

## Knowledge map

The repository-derived knowledge base is organized into seven core concept domains:

1. **[Architecture Overview](architecture/overview.md)**: Explains the P-X-D-R-A-C (Plan, Execute, Diagnose, Research, Audit, Crystallize) engine lifecycle, process isolation via `SanitizedRunner`, and execution streaming via `AsyncProcessExecutor`.
2. **[Capability Planner & Routing Authority](routing/capability-planner.md)**: Documents `CapabilityPlanner` and `HybridRouteDecision`, the sole route authorities governing capability selection and topology planning across all runtime surfaces.
3. **[MCP Gateway & Ingress Protocols](runtime/mcp-gateway.md)**: Covers the Model Context Protocol execution gateway, HTTP/stdio transport adapters, and self-hosted MCP servers.
4. **[CLI Commands & Cueline Operations](runtime/cli-and-cueline.md)**: Details the primary `nexus` CLI surface (`scripts/engine/nexus_cli.py`), command delivery modes (`ask`, `high`), health check levels, and `nexus-cueline-worker` background task execution.
5. **[Governance Gates & Completion Contracts](governance/gates-and-contracts.md)**: Explains delivery verification gates, completion contract envelopes, and `CompletionEnforcer` fail-closed verification.
6. **[GitHub Actions & CI/CD Lanes](workflows/github-actions.md)**: Catalogs all 9 GitHub Actions workflows, distinguishing scheduled triggers, manual dispatches, and event hooks.
7. **[Validation Suites & Benchmarks](testing/validation-and-benchmarks.md)**: Categorizes unit, integration, and benchmark test suites.

---

## 🧭 Task-Routing Table

Use this matrix to navigate directly from user intent to implementation entrypoints, key symbols, test coverage, and minimal validation commands:

| Change Area / User Intent | Relevant Wiki Page | Exact Source Entry Points | Important Symbols / Types | Focused Tests | Minimal Validation Command |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **System Lifecycle & Core Runtime** | [Architecture Overview](architecture/overview.md) | `nexus/services/unified_runtime.py`<br>`scripts/engine/nexus_cli.py` | `UnifiedRuntime`<br>`SanitizedRunner`<br>`AsyncProcessExecutor` | `tests/test_cli_deadlock_and_injection.py`<br>`tests/test_service_decomposition.py` | `.venv/bin/python -m pytest -q tests/test_cli_deadlock_and_injection.py` |
| **Routing & Capability Selection** | [Routing Authority](routing/capability-planner.md) | `nexus/engine/capability_planner.py`<br>`nexus/contracts/hybrid_route.py` | `CapabilityPlanner`<br>`HybridRouteDecision`<br>`CapabilityPlan` | `tests/test_lite_route_oracle.py`<br>`tests/test_route_optimization.py` | `.venv/bin/python -m pytest -q tests/test_lite_route_oracle.py` |
| **MCP Tools & Ingress Handling** | [MCP Gateway](runtime/mcp-gateway.md) | `nexus/orchestrator/unified_mcp_gateway.py`<br>`nexus/orchestrator/self_hosted_mcp.py`<br>`nexus/orchestrator/self_hosted_mcp_http.py` | `UnifiedMCPGateway`<br>`NexusSelfHostedMCPServer` | `tests/nexus/orchestrator/test_unified_mcp_gateway.py`<br>`tests/nexus/orchestrator/test_mcp_canonical_ingress.py` | `.venv/bin/python -m pytest -q tests/nexus/orchestrator/test_unified_mcp_gateway.py tests/nexus/orchestrator/test_mcp_canonical_ingress.py` |
| **CLI Commands & Subcommands** | [CLI & Cueline](runtime/cli-and-cueline.md) | `scripts/engine/nexus_cli.py`<br>`scripts/ops/nexus_cueline_worker.py` | `nexus` (Click group)<br>`NexusCLI`<br>`main` | `tests/test_cli_commands.py`<br>`tests/test_cli_dispatch.py` | `.venv/bin/python -m pytest -q tests/test_cli_commands.py` |
| **Delivery Gates & Completion** | [Governance Gates](governance/gates-and-contracts.md) | `nexus/engine/completion_enforcer.py`<br>`nexus/engine/completion_contract.py` | `CompletionEnforcer`<br>`build_completion_envelope` | `tests/test_task_runner_completion_gate.py`<br>`tests/test_iron_gate_governance.py` | `.venv/bin/python -m pytest -q tests/test_task_runner_completion_gate.py` |
| **CI/CD Workflow Triggers** | [GitHub Actions](workflows/github-actions.md) | `.github/workflows/*.yml` | Workflows (`openwiki-update`, `benchmark-ci`, `pytest`) | `tests/test_script_entrypoints.py` | `.venv/bin/python -m pytest -q tests/test_script_entrypoints.py` |
| **Testing & Benchmark Verification** | [Validation Suites](testing/validation-and-benchmarks.md) | `tests/`<br>`nexus/benchmark/` | `pytest`<br>`SWE-bench` subset | `tests/test_v9_regression_p1.py` | `bash scripts/ops/test_repo.sh fast` |

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

It covers five task classes and is limited to four context files / 16,000 bytes
per class and 8,000 bytes overall.

## Architecture pointers

The source observations below are navigation aids only; verify every claim
against current source and tests:

- [Capability planner](routing/capability-planner.md) — `CapabilityPlanner` and
  `HybridRouteDecision` remain route authorities.
- [CLI and cueline](runtime/cli-and-cueline.md) — the primary CLI source is
  `scripts/engine/nexus_cli.py`.
- [Validation suites](testing/validation-and-benchmarks.md) — use the current
  `scripts/ops/test_repo.sh` modes and the bounded fixture smoke.

## Authority ceiling

```yaml
component: OpenWiki
implementation_status: CURRENT
wiring_status: WIRED
runtime_surfaces:
  - LOCAL_RUNTIME
  - CI
authority_roles:
  - DERIVED_ONLY
evidence_basis:
  - openwiki/INSTRUCTIONS.md
  - .github/workflows/openwiki-update.yml
claim_ceiling: Derived repository observation layer; holds zero governance, route, approval, or release authority.
```

This page does not replace repository policy, select providers or models, run
lifecycle transitions, or establish benchmark, release, or production truth.
