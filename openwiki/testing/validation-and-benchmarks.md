---
type: Concept
title: Validation Suites, Contract Tests & Benchmarks
description: Current-source index of focused runtime, routing, lifecycle, governance, CI, and benchmark validation surfaces.
tags: [testing, validation, contracts, benchmarks, pytest, ci]
openwiki:
  roles: [architecture, operations, testing]
  change_kinds: [public-api, testing]
  source_paths: [tests/, pyproject.toml, .github/workflows/pytest.yml]
  symbols: [pytest, RuntimePhase, CapabilityPlanner, CandidateAcceptanceResult, SWE-bench]
  test_paths: [tests/engine/test_runtime_phase_contract.py, tests/engine/test_capability_planner.py, tests/nexus/orchestrator/test_self_hosted_task_service.py, tests/nexus/orchestrator/test_acceptance_loop.py, tests/ops/test_openwiki_source_contract.py]
  invariants: [Prefer focused revision-bound tests before broad suites. Test evidence proves the tested contract and does not by itself prove production wiring.]
  validation_commands: [pytest tests/ops/test_openwiki_source_contract.py -q]
---

# Validation Suites, Contract Tests & Benchmarks

Nexus has a large and fast-changing test corpus. OpenWiki therefore does not freeze a global test-count baseline. For implementation work, prefer the smallest focused test set that proves the changed contract, then widen verification according to the repository impact and CI policy.

> **Evidence ceiling:** a passing unit or integration test proves tested behavior at the tested revision. It does not by itself prove a production caller, live provider invocation, deployment status, merge, or public claimability.

---

## 🧪 Focused Test Map

### 1. Canonical Runtime Phase Contract
- `tests/engine/test_runtime_phase_contract.py`
- Proves `RUNTIME_PHASE_FLOW == (S, P, D, X, R, A, C)`, legal transition edges, and the explicit audit-pass requirement for `A → C`.

```bash
pytest tests/engine/test_runtime_phase_contract.py -q
```

### 2. Capability Planning & Canonical Execution
- `tests/engine/test_capability_planner.py`
- `tests/contracts/test_canonical_execution.py`
- `tests/contracts/test_hybrid_route_contract.py`

Use this lane for `CapabilityPlanner`, execution-depth, canonical planning-bundle, route-truth, and Planner-derived decision-contract changes.

```bash
pytest tests/engine/test_capability_planner.py tests/contracts/test_canonical_execution.py tests/contracts/test_hybrid_route_contract.py -q
```

### 3. Durable Self-Hosted Lifecycle & Continuity
- `tests/nexus/orchestrator/test_self_hosted_task_service.py`
- `tests/core/test_task_continuity.py`
- `tests/ops/test_nexus_cueline_worker.py`

Use this lane for task identity, retry/recovery/cleanup, direct-vs-isolated execution-lane rules, Cueline forwarding, or cross-attempt continuity projection.

### 4. Independent Acceptance & Outcome Evidence
- `tests/nexus/orchestrator/test_acceptance_loop.py`
- `tests/contracts/test_operator_outcome_receipt.py`

These tests cover exact Candidate/reviewer identity binding, `ACCEPT/REPAIRABLE/BLOCK`, non-promoting acceptance, immutable operator outcome evidence, and provenance validation.

### 5. GitHub Orchestration Contracts
- `tests/contracts/test_github_orchestration.py`
- `tests/nexus/orchestrator/test_github_orchestration.py`

Use this lane for merge-intent evidence freshness, required checks/reviews/impact, independent acceptance, and the non-mutating `mutation_authorized=false` boundary.

### 6. NightShift Candidate Queue
- `tests/services/test_nightshift_queue_consumer.py`
- `tests/ops/test_issue111_nightshift_impact_map.py`

Use this lane for the bounded candidate manifest, required safety controls, workforce-admission evidence, canonical invocation authority, deduplication, and fail-closed dispatch behavior.

### 7. MCP & Gateway Ingress
- `tests/nexus/orchestrator/test_unified_mcp_gateway.py`
- `tests/nexus/orchestrator/test_mcp_canonical_ingress.py`
- `tests/nexus/orchestrator/test_unified_mcp_gateway_http.py`
- `tests/nexus/orchestrator/test_self_hosted_mcp.py`

These tests are the focused navigation point for MCP tool registration, canonical ingress, HTTP transport, and self-hosted MCP behavior.

### 8. OpenWiki Source Contract
- `tests/ops/test_openwiki_source_contract.py`
- `tests/ops/test_openwiki_authority_crosswalk.py`
- `tests/ops/test_wiki_coverage_policy.py`

This lane verifies source/test paths, workflow inventory, route-authority wording, surface classification discipline, and deterministic OpenWiki-to-governed-Wiki crosswalk behavior.

```bash
pytest tests/ops/test_openwiki_source_contract.py tests/ops/test_openwiki_authority_crosswalk.py tests/ops/test_wiki_coverage_policy.py -q
```

### 9. Regression & Benchmark Lanes
- `tests/test_v9_regression_p1.py`
- `.github/workflows/benchmark-ci.yml`
- benchmark-specific modules under `nexus/benchmark/` and research/evaluation surfaces

Benchmark evidence remains a benchmark/runtime-surface claim only unless an independent product-runtime witness establishes more.

---

## 🔁 Exact-Base CI Selection

The current `Nexus Pytest CI` workflow does more than run an undifferentiated full suite on every event. For non-manual/non-scheduled events it first runs an **Exact-base impact gate**, checks out the exact head, resolves the comparison base/head, and uses repository impact/test-selection tooling before downstream verification.

Treat CI results as revision-bound evidence. Do not reuse a passing run after the Candidate/head, base, workflow, or selected test set has drifted.

---

## 🏷️ Required V3 Classifications

```yaml
component: PytestSuite
implementation_status: CURRENT
wiring_status: WIRED
runtime_surfaces:
  - TEST
authority_roles:
  - NONE
evidence_basis:
  - pyproject.toml
  - tests/
claim_ceiling: Repository test harness that produces contract-specific verification evidence; passing tests alone do not establish production wiring.
```

```yaml
component: PytestCIWorkflow
implementation_status: CURRENT
wiring_status: WIRED
runtime_surfaces:
  - CI
authority_roles:
  - NONE
evidence_basis:
  - .github/workflows/pytest.yml:on.push
  - .github/workflows/pytest.yml:on.pull_request
  - .github/workflows/pytest.yml:on.schedule
claim_ceiling: GitHub Actions CI surface that binds verification to event/base/head and impact-selection logic; it does not grant merge or release authority by itself.
```

```yaml
component: SWEBenchBenchmarkSurface
implementation_status: CURRENT
wiring_status: WIRED
runtime_surfaces:
  - BENCHMARK
  - CI
authority_roles:
  - NONE
evidence_basis:
  - .github/workflows/benchmark-ci.yml
claim_ceiling: Scheduled/manual benchmark evaluation surface; benchmark results must not be relabeled as product-runtime proof without separate evidence.
```

---

## 🧭 Change Navigation & Validation

### When to Consult
Use this page to locate the smallest adequate test set for runtime phases, route planning, self-hosted lifecycle, acceptance/receipt semantics, GitHub orchestration, NightShift dispatch, MCP ingress, or OpenWiki itself.

### Validation Invariants
- Start focused; widen according to impact and policy.
- Bind evidence to the exact revision and command.
- Distinguish `TEST`, `CI`, `BENCHMARK`, and product runtime surfaces.
- A test import/caller is not a production-wiring witness.
- Do not freeze global test counts in architecture claims.

### Minimal OpenWiki Validation Command
```bash
pytest tests/ops/test_openwiki_source_contract.py tests/ops/test_openwiki_authority_crosswalk.py tests/ops/test_wiki_coverage_policy.py -q
```
