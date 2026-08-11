---
type: Concept
title: Validation Suites & Benchmarks
description: Technical index of test categories, benchmark suites, and minimal quiet validation commands.
tags: [testing, validation, benchmarks, pytest, ci]
openwiki:
  roles: [architecture, operations, testing]
  change_kinds: [public-api, testing]
  source_paths: [tests/, pyproject.toml]
  symbols: [pytest, SWE-bench, benchmark]
  test_paths: [tests/test_cli_commands.py, tests/test_task_runner_completion_gate.py, tests/test_v9_regression_p1.py]
  invariants: [Validation commands must use -q flag to suppress verbose output.]
  validation_commands: [pytest tests/test_v9_regression_p1.py -q]
---

# Validation Suites & Benchmarks

Verification in Nexus Singularity OS spans over 100 test modules under `tests/` covering over 4,200 test cases. The test suite is organized into distinct functional tiers to enable fast local feedback and isolated CI checks.

---

## 🧪 Test Suite Categorization

### 1. Core CLI & Subprocess Tests
- **`tests/test_cli_commands.py`**: Verifies top-level Click commands, argument parsing, and output formatting.
- **`tests/test_cli_dispatch.py`**: Validates subcommand routing.
- **`tests/test_cli_deadlock_and_injection.py`**: Ensures `SanitizedRunner` blocks shell injection and `AsyncProcessExecutor` handles stream buffers without deadlocks.

### 2. Routing & Capability Oracle Tests
- **`tests/test_lite_route_oracle.py`**: Tests `[CapabilityPlanner](../routing/capability-planner.md)` signal evaluation and safety floor escalation.
- **`tests/test_route_optimization.py`**: Verifies routing weight adjustments and execution depth calculations.

### 3. MCP & Gateway Ingress Tests
- **`tests/nexus/orchestrator/test_unified_mcp_gateway.py`**: Tests `[UnifiedMCPGateway](../runtime/mcp-gateway.md)` tool registration, execution, and error payloads.
- **`tests/nexus/orchestrator/test_mcp_canonical_ingress.py`**: Tests canonical MCP ingress and route-bound task dispatch.
- **`tests/nexus/orchestrator/test_unified_mcp_gateway_http.py`** and **`tests/nexus/orchestrator/test_self_hosted_mcp.py`**: Test HTTP transport and self-hosted server behavior.

### 4. Governance & Completion Gate Tests
- **`tests/test_task_runner_completion_gate.py`**: Verifies fail-closed behavior in `[CompletionEnforcer](../governance/gates-and-contracts.md)`.
- **`tests/test_iron_gate_governance.py`**: Validates governance policy enforcement.

### 5. Regression & Benchmark Lanes
- **`tests/test_v9_regression_p1.py`**: Core P1 anti-regression suite.
- **`nexus/benchmark/` / `SWE-bench`**: Evaluates model performance across benchmark tasks.

---

## 🤫 Quiet Validation Discipline

To keep agent execution logs clean and non-redundant, always pass quiet flags (`-q`) during test execution:

```bash
# Minimal quiet check for core CLI
pytest tests/test_cli_commands.py -q

# Minimal quiet check for routing authority
pytest tests/test_lite_route_oracle.py -q

# Minimal quiet check for completion enforcer
pytest tests/test_task_runner_completion_gate.py -q
```

---

## 🏷️ Required V3 Classifications

```yaml
component: PytestSuite
implementation_status: CURRENT
wiring_status: WIRED
runtime_surfaces:
  - TEST
authority_roles:
  - GOVERNANCE_AUTHORITY
evidence_basis:
  - pyproject.toml:[dependency-groups].dev.pytest
  - tests/
claim_ceiling: Primary automated test execution harness providing verification evidence across repository modules.
```

```yaml
component: SWEBenchSuite
implementation_status: CURRENT
wiring_status: WIRED
runtime_surfaces:
  - BENCHMARK
authority_roles:
  - NONE
evidence_basis:
  - .github/workflows/benchmark-ci.yml
claim_ceiling: Benchmark evaluation harness evaluating agent performance on standardized task datasets.
```

---

## 🧭 Change Navigation & Validation

### When to Consult
Consult this page when looking for existing test coverage for a subsystem, adding new unit or integration test cases, or running targeted verification commands.

### Runtime Invariants
- Tests must pass cleanly with exit code `0`.
- Validation commands must use `-q` to preserve failure diagnostics while suppressing noisy stdout.

### Exact Source Paths
- `tests/`
- `pyproject.toml`

### Focused Tests
- `tests/test_v9_regression_p1.py`
- `tests/test_script_entrypoints.py`

### Minimal Validation Command
```bash
pytest tests/test_v9_regression_p1.py -q
```
