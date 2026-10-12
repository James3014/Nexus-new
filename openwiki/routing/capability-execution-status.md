---
type: Concept
title: Capability Execution Status (Planner Node → Executor Reality)
description: Current-source observation of which CapabilityPlanner nodes have a physical executor on each runtime surface after the repository split, including the dead nexus-runtime executor seam and hollow executors in Nexus-new.
tags: [routing, capability-registry, executor, split, evidence]
openwiki:
  roles: [architecture, operations]
  change_kinds: [routing, public-api]
  source_paths: [nexus/services/capability_registry.py, nexus/core/capability_executor_registry.py, nexus/engine/red_team_audit.py, scripts/engine/commands/stress_test.py, nexus/services/local_heal/orchestrator.py, scripts/eval/run_memory_ab_v1.py, requirements/canonical-runtime.txt]
  symbols: [EXECUTOR_REGISTRY, build_real_executor_invoker, BLOCKED_EXECUTOR_UNAVAILABLE, _exec_stress_test, _exec_learning_closure, _exec_ui_validator, _exec_meta_opt]
  test_paths: [tests/engine/test_capability_planner.py, tests/services/test_forecast_gate_mainchain_e2e.py, tests/benchmark/test_capability_regression_guard.py]
  invariants: [CapabilityPlanner is the sole route and capability-selection authority. Selection is not invocation; a receipt must carry invocation evidence before a capability may be claimed. Wiring on the Nexus-new CLI surface does not imply wiring on the nexus-runtime surface.]
  validation_commands: [pytest tests/engine/test_capability_planner.py tests/services/test_forecast_gate_mainchain_e2e.py -q]
---

# Capability Execution Status (Planner Node → Executor Reality)

`CapabilityPlanner` is the sole route and capability-selection authority; `HybridRouteDecision` is Planner-derived and is not a second selector, router, or planner. This page observes something narrower: **after the Planner selects a node, does a physical executor exist on the surface that received the plan?** The answer differs per surface and is the main reason capability receipts after the September 2026 repository split look thinner than legacy receipts.

> **Observation revision:** Nexus-new `origin/main` `0fb15f3e1` and nexus-runtime `origin/main` `cfcb38d` (both read on 2026-10-12). Line numbers below are from those revisions and will drift.

---

## 🔀 Two copies of the same registry

| Copy | Path | Resolves executors from | Observed state |
| :--- | :--- | :--- | :--- |
| Nexus-new | `nexus/services/capability_registry.py` | `nexus.core.capability_executor_registry.get_executor` (`EXECUTOR_REGISTRY`, ~4078 lines) | Import succeeds; `build_real_executor_invoker` returns a real invoker for registered keys |
| nexus-runtime | `src/nexus_runtime/support/services/capability_registry.py` | `nexus_runtime.support.core.capability_executor_registry.get_executor` (lines 1340, 1736) and `nexus_runtime.support.core.belief_contracts` (line 1735) | **Neither module exists** in `cfcb38d` (`git ls-tree` shows no `support/core/`; `belief_contracts` lives at `planning/core/`). The `try/except` returns `None`, so every escalate-gated node resolves to `BLOCKED_EXECUTOR_UNAVAILABLE`. No test in nexus-runtime exercises this branch. |

Consequence on the nexus-runtime surface: `hyper`, `swarm`, `nightshift`, `drone`, `xray`, `ddtree`, `autoreason`, `metabolism`, `ultra_review` are planned but never executed. Nexus-new's own CLI surface is unaffected because it imports its in-repo registry. A resolver-injection fix (runtime must not import `nexus.*`) is in flight; this page should be re-observed after it lands.

---

## 🧱 Executor reality on the Nexus-new surface

Executors that exist and are reachable but whose body does not do the work the node name implies (read directly from `nexus/core/capability_executor_registry.py` and callees):

| Node | Executor | What it physically does | Receipt consequence |
| :--- | :--- | :--- | :--- |
| `stress_test` | `_exec_stress_test` (L3699) → `nexus/engine/red_team_audit.py` | `_test_boundary`, `_test_concurrency`, `_test_fault` each `return {"status": "PASS", ...}` unconditionally (L35, L39, L43) | Always `SUCCEEDED`; never evidence of a stress test |
| `ui_validator` | `_exec_ui_validator` (L3947) | Returns `BLOCKED` with `no_live_browser_session` or `BLOCKED_EXTERNAL_AUTH`; never drives a browser | Never a validation receipt |
| `learning_closure` | `_exec_learning_closure` (L1760) | Instantiates `LearningClosureBridge()` and reports `{"class_instantiated": True}` (L1770); the same pattern appears at L723, L973, L1495, L1916 for other nodes | `SUCCEEDED` without closure work |
| `meta_opt` | `_exec_meta_opt` (L3738) | `BLOCKED` unless `plan.constraints["meta_opt_episode"]` is supplied; the preset consumer is opt-in and scoped to `research:auto-flow` only | Normally a policy skip |
| `oracle_shadow`, `federation` | `_exec_*` present; runtime marks `EXPERIMENTAL_NOT_PROMOTED` with `physical_callable=None` | `oracle/promote.py` patches a hard-coded `oracle_test.py`; `fed-run` calls a 36-line engine | Demo-grade only |

Executors with real bodies on this surface (not exhaustive): `_exec_mempalace` (L370), `_exec_lancedb` (L807), `_exec_belief` (L1057), `_exec_artifact_gate` (L1504), `_exec_claim_gate` (L1558), `_exec_forecast_gate` (L3312, end-to-end test added 2026-10-12).

---

## 🧪 Why recent experiment receipts show one capability

`scripts/eval/run_memory_ab_v1.py` imports `nexus.services.local_heal.orchestrator` directly (L209–L223) and never calls `CapabilityPlanner`. Local receipts from that runner (502 under `artifacts/runtime/memory_ab_v1/`, untracked) all carry `with_nexus_armor=false`, `p4_committee_invoked=false`, and a single `consumption_chain` capability `local_heal_repair`; `autoreason_advisory` is advisory-only with a constant score and `belief_trace.uncertainty_delta` is 0.0 in 373 of 502. Those receipts therefore measure a bare local model plus a memory toggle, not the capability graph. An `--armor on/off` axis for that runner is in flight.

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
claim_ceiling: On the Nexus-new CLI surface, planner nodes with a registered executor are physically invocable; this says nothing about whether the executor body does meaningful work (see hollow executors above) and nothing about the nexus-runtime surface.
```

```yaml
component: NexusRuntimeExecutorSeam
implementation_status: CURRENT
wiring_status: UNKNOWN
runtime_surfaces: []
authority_roles:
  - NONE
evidence_basis:
  - nexus-runtime@cfcb38d src/nexus_runtime/support/services/capability_registry.py:1340 (import of nexus_runtime.support.core.capability_executor_registry)
  - nexus-runtime@cfcb38d src/nexus_runtime/support/services/capability_registry.py:1735-1736
  - nexus-runtime@cfcb38d git ls-tree origin/main (no src/nexus_runtime/support/core/ directory)
  - requirements/canonical-runtime.txt (Nexus-new pin of that revision)
claim_ceiling: At revision cfcb38d the import target does not exist, so build_real_executor_invoker cannot return an invoker and gated nodes report BLOCKED_EXECUTOR_UNAVAILABLE; this is a source-level observation and the examined scope excludes any out-of-tree injection, so wiring_status stays UNKNOWN rather than UNWIRED.
```

```yaml
component: HollowExecutors
implementation_status: CURRENT
wiring_status: WIRED
runtime_surfaces:
  - MAIN_CLI
authority_roles:
  - NONE
evidence_basis:
  - nexus/core/capability_executor_registry.py:_exec_stress_test
  - nexus/engine/red_team_audit.py (unconditional PASS returns)
  - nexus/core/capability_executor_registry.py:_exec_ui_validator
  - nexus/core/capability_executor_registry.py:_exec_learning_closure (class_instantiated outcome)
  - nexus/core/capability_executor_registry.py:_exec_meta_opt (meta_opt_episode constraint gate)
claim_ceiling: These executors are reachable and return receipts, but their receipts must not be read as evidence that a stress test, UI validation, learning closure, or meta-optimization occurred.
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
Read this page before claiming that a capability "ran" in an experiment, before interpreting `BLOCKED_EXECUTOR_UNAVAILABLE` on the runtime surface, or when adding a new executor to either registry copy.

### Invariants
- `CapabilityPlanner` selects; a registry executor invokes; a receipt proves. Each is separate evidence.
- The two registry copies must be re-compared after any runtime pin bump.
- A `class_instantiated` outcome is presence evidence, not execution evidence.

### Exact Source Files & Symbols
- `nexus/services/capability_registry.py` → `build_real_executor_invoker`, `BLOCKED_EXECUTOR_UNAVAILABLE`, `SKIP_REASONS`
- `nexus/core/capability_executor_registry.py` → `EXECUTOR_REGISTRY`, `_exec_*`
- `nexus/engine/red_team_audit.py` → `RedTeamAudit.stress_test`
- `scripts/eval/run_memory_ab_v1.py` → local-heal A/B harness

### Minimal Validation Command
```bash
pytest tests/engine/test_capability_planner.py tests/services/test_forecast_gate_mainchain_e2e.py -q
```

Governed-Wiki counterpart (authoritative for citability decisions, not generated here): `nexus_wiki_vault/08_Diffs/Diff - Legacy Monolith vs Split Repo Family (2026-10-12).md` and `nexus_wiki_vault/04_State/CAPABILITY_EVIDENCE_LEDGER_2026-10-12.md`.
