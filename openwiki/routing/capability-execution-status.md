---
type: Concept
title: Capability Execution Status (Planner Node → Executor Reality)
description: Current-source observation of which CapabilityPlanner nodes have a physical executor on each runtime surface after the repository split, including the nexus-runtime executor-resolver seam and the archived (fail-closed) executors in Nexus-new.
tags: [routing, capability-registry, executor, split, evidence]
openwiki:
  roles: [architecture, operations]
  change_kinds: [routing, public-api]
  source_paths: [nexus/services/capability_registry.py, nexus/core/capability_executor_registry.py, nexus/services/runtime_compat.py, nexus/engine/red_team_audit.py, nexus/services/local_heal/orchestrator.py, scripts/eval/run_memory_ab_v1.py, requirements/canonical-runtime.txt]
  symbols: [EXECUTOR_REGISTRY, build_real_executor_invoker, BLOCKED_EXECUTOR_UNAVAILABLE, register_executor_resolver_if_available, _archived_receipt, _exec_stress_test, _exec_learning_closure, _exec_ui_validator, _exec_meta_opt]
  test_paths: [tests/engine/test_capability_planner.py, tests/services/test_runtime_compat.py, tests/services/test_forecast_gate_mainchain_e2e.py, tests/benchmark/test_capability_regression_guard.py]
  invariants: [CapabilityPlanner is the sole route and capability-selection authority. Selection is not invocation; a receipt must carry invocation evidence before a capability may be claimed. Wiring on the Nexus-new CLI surface does not imply wiring on the nexus-runtime surface.]
  validation_commands: [pytest tests/engine/test_capability_planner.py tests/services/test_forecast_gate_mainchain_e2e.py -q]
---

# Capability Execution Status (Planner Node → Executor Reality)

`CapabilityPlanner` is the sole route and capability-selection authority; `HybridRouteDecision` is Planner-derived and is not a second selector, router, or planner. This page observes something narrower: **after the Planner selects a node, does a physical executor exist on the surface that received the plan?** The answer differs per surface and is the main reason capability receipts after the September 2026 repository split look thinner than legacy receipts.

> **Observation revision:** Nexus-new `origin/main` `adedcb7f6` (pins nexus-runtime `e73d152f1`) and nexus-runtime `origin/main` `2b38dd8` (read on 2026-10-16). This page was first written against `0fb15f3e1` / `cfcb38d` on 2026-10-12; the runtime seam and the hollow-executor rows below changed since then. Line numbers will drift.

---

## 🔀 Two copies of the same registry

| Copy | Path | Resolves executors from | Observed state |
| :--- | :--- | :--- | :--- |
| Nexus-new | `nexus/services/capability_registry.py` | `nexus.core.capability_executor_registry.get_executor` (`EXECUTOR_REGISTRY`) | Import succeeds; `build_real_executor_invoker` returns a real invoker for registered keys |
| nexus-runtime | `src/nexus_runtime/support/services/capability_registry.py` | `nexus_runtime.support.services.executor_binding.resolve_executor` (L1343, L1746), an injection seam added by nexus-runtime #163 (`a6801a9`, 2026-10-12) | The runtime no longer imports a host registry. The host registers a resolver once: `nexus/services/runtime_compat.py:register_executor_resolver_if_available` calls `register_executor_resolver(_resolve_physical_executor)` at import time and returns `False` (no-op) when the installed runtime predates the seam. With no resolver registered, `resolve_executor` returns `None` and gated nodes still report `BLOCKED_EXECUTOR_UNAVAILABLE`. Covered by nexus-runtime `tests/test_executor_binding.py` and Nexus-new `tests/services/test_runtime_compat.py`. |

Consequence: on a runtime surface that has imported `nexus.services.runtime_compat`, escalate-gated nodes (`hyper`, `swarm`, `nightshift`, `drone`, `xray`, `ddtree`, `autoreason`, `metabolism`, `ultra_review`) resolve to the Nexus-new executors instead of being blocked by a missing module. Resolution errors are recorded per capability before re-raising (`record_executor_resolution_error_for_key`), so a failed resolve is observable. This is source/test evidence only: it does not show that a given live Gateway process registered the resolver, nor that a selected node was invoked on a real task; read the receipt's invocation evidence for that.

---

## 🧱 Executor reality on the Nexus-new surface

Executors whose body never did the work the node name implies were archived on 2026-10-12 and now fail closed through `_archived_receipt` (`invoked=False`, `gate_passed=False`, `action="archived"`, reason from `ARCHIVED_CAPABILITY_REASONS` in `nexus/services/capability_registry.py`):

| Node | Executor | Before 2026-10-12 | Now |
| :--- | :--- | :--- | :--- |
| `stress_test` | `_exec_stress_test` | Called `nexus/engine/red_team_audit.py`, whose `_test_boundary` / `_test_concurrency` / `_test_fault` return `PASS` unconditionally | Archived receipt; `red_team_audit.py` still contains the unconditional `PASS` helpers but this executor no longer reports them as success |
| `ui_validator` | `_exec_ui_validator` | Returned `BLOCKED` without driving a browser | Archived receipt |
| `learning_closure` | `_exec_learning_closure` | Reported `{"class_instantiated": True}` | Archived receipt; `class_instantiated` and similar keys are listed in `_SHALLOW_SUCCESS_KEYS` ("import/construct alone is never real execution") |
| `oracle_shadow`, `federation` | `_exec_oracle_shadow`, `_exec_federation` | Demo-grade bodies | Archived receipt |
| `meta_opt` | `_exec_meta_opt` | `BLOCKED` unless `plan.constraints["meta_opt_episode"]` is supplied | Unchanged: still gated on `meta_opt_episode` |

Executors with real bodies on this surface (not exhaustive): `_exec_mempalace`, `_exec_lancedb`, `_exec_belief`, `_exec_artifact_gate`, `_exec_claim_gate`, `_exec_forecast_gate` (end-to-end test `tests/services/test_forecast_gate_mainchain_e2e.py`).

---

## 🧪 Why the 2026-10 memory A/B receipts show one capability

`scripts/eval/run_memory_ab_v1.py` imports `nexus.services.local_heal.orchestrator` directly and does not go through `CapabilityPlanner` by default. The 502 local receipts from its first rounds (`artifacts/runtime/memory_ab_v1/`, untracked) all carry `with_nexus_armor=false`, `p4_committee_invoked=false`, and a single `consumption_chain` capability `local_heal_repair`, so they measure a bare local model plus a memory toggle, not the capability graph. The runner now has an `--armor` axis; results from armor-on runs are not recorded on this page.

---

## 🏷️ Required V3 Classifications

```yaml
component: NexusNewCapabilityRegistry
implementation_status: CURRENT
wiring_status: WIRED
runtime_surfaces:
  - MAIN_CLI
authority_roles:
  - NONE
evidence_basis:
  - nexus/services/capability_registry.py:build_real_executor_invoker
  - nexus/core/capability_executor_registry.py:EXECUTOR_REGISTRY
  - scripts/engine/nexus_cli.py (research:auto-flow dispatch into the registry)
claim_ceiling: On the Nexus-new CLI surface, planner nodes with a registered executor are physically invocable; this says nothing about whether the executor body does meaningful work and nothing about which runtime process registered the resolver.
```

```yaml
component: NexusRuntimeExecutorSeam
implementation_status: CURRENT
wiring_status: WIRED
runtime_surfaces:
  - MCP_GATEWAY
authority_roles:
  - NONE
evidence_basis:
  - nexus/orchestrator/unified_mcp_gateway.py imports nexus.services.unified_runtime, which imports nexus.services.runtime_compat (module-level register_executor_resolver_if_available() call)
  - nexus-runtime@2b38dd8 src/nexus_runtime/support/services/executor_binding.py:register_executor_resolver
  - nexus-runtime@2b38dd8 src/nexus_runtime/support/services/capability_registry.py:1343,1746 (resolve_executor)
  - nexus/services/runtime_compat.py:register_executor_resolver_if_available
  - tests/services/test_runtime_compat.py
claim_ceiling: Source shows the MCP Gateway import chain registers the host resolver with a seam-capable runtime (pin e73d152f1 includes a6801a9), and unit tests cover registration; this does not prove that a particular deployed Gateway process runs that pin or that a selected node was invoked on a real task.
```

```yaml
component: ArchivedExecutors
implementation_status: HISTORICAL_OR_LEGACY
wiring_status: WIRED
runtime_surfaces:
  - MAIN_CLI
authority_roles:
  - NONE
evidence_basis:
  - nexus/core/capability_executor_registry.py:_archived_receipt
  - nexus/core/capability_executor_registry.py:_exec_stress_test
  - nexus/core/capability_executor_registry.py:_exec_ui_validator
  - nexus/core/capability_executor_registry.py:_exec_learning_closure
  - nexus/services/capability_registry.py:ARCHIVED_CAPABILITY_REASONS
claim_ceiling: These nodes are still selectable and reachable, but their receipts are explicit fail-closed archive results and are never evidence that a stress test, UI validation, learning closure, oracle shadow, or federation run occurred.
```

```yaml
component: MemoryABRunner
implementation_status: CURRENT
wiring_status: WIRED
runtime_surfaces:
  - STANDALONE_OPS
authority_roles:
  - NONE
evidence_basis:
  - scripts/eval/run_memory_ab_v1.py (direct import of nexus.services.local_heal.orchestrator)
  - artifacts/runtime/memory_ab_v1/*/reports/local_heal/*/receipt.json (local, untracked; with_nexus_armor=false in all 502)
claim_ceiling: The runner exercises local heal with a memory toggle and bypasses CapabilityPlanner; its results bound memory-on/off effects on a bare local model only.
```

---

## 🧭 Change Navigation & Validation

### When to Consult
Read this page before claiming that a capability "ran" in an experiment, before interpreting `BLOCKED_EXECUTOR_UNAVAILABLE` on the runtime surface (usually: no resolver registered in that process), or when adding a new executor to either registry copy.

### Invariants
- `CapabilityPlanner` selects; a registry executor invokes; a receipt proves. Each is separate evidence.
- The two registry copies must be re-compared after any runtime pin bump.
- A `class_instantiated` outcome is presence evidence, not execution evidence.
- An `action="archived"` receipt is a fail-closed result, not a skipped or passed capability.

### Exact Source Files & Symbols
- `nexus/services/capability_registry.py` → `build_real_executor_invoker`, `BLOCKED_EXECUTOR_UNAVAILABLE`, `SKIP_REASONS`
- `nexus/core/capability_executor_registry.py` → `EXECUTOR_REGISTRY`, `_exec_*`
- `nexus/services/runtime_compat.py` → `register_executor_resolver_if_available`, `_resolve_physical_executor`
- `nexus/engine/red_team_audit.py` → unconditional-`PASS` helpers (no longer reported by `_exec_stress_test`)
- `scripts/eval/run_memory_ab_v1.py` → local-heal A/B harness

### Minimal Validation Command
```bash
pytest tests/engine/test_capability_planner.py tests/services/test_forecast_gate_mainchain_e2e.py -q
```

Governed-Wiki counterpart (authoritative for citability decisions, not generated here): `nexus_wiki_vault/08_Diffs/Diff - Legacy Monolith vs Split Repo Family (2026-10-12).md` and `nexus_wiki_vault/04_State/CAPABILITY_EVIDENCE_LEDGER_2026-10-12.md`.
