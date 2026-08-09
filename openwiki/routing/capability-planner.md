---
type: Concept
title: Capability Planner & Routing Authority
description: Deep dive into CapabilityPlanner and HybridRouteDecision, the sole Nexus route authority governing capability graph composition.
tags: [routing, capability-planner, hybrid-route, authority]
openwiki:
  roles: [architecture, domain]
  change_kinds: [public-api, routing]
  source_paths: [nexus/engine/capability_planner.py, nexus/contracts/hybrid_route.py, nexus/services/mainchain_route_freeze.py]
  symbols: [CapabilityPlanner, HybridRouteDecision, CapabilityPlan, MAINCHAIN_AUTHORITY]
  test_paths: [tests/test_lite_route_oracle.py, tests/test_route_optimization.py]
  invariants: [CapabilityPlanner and HybridRouteDecision remain sole Nexus route authority. OpenWiki has zero route authority.]
  validation_commands: [pytest tests/test_lite_route_oracle.py -q]
---

# Capability Planner & Routing Authority

In Nexus Singularity OS, **`CapabilityPlanner`** and **`HybridRouteDecision`** represent the canonical **Route Authority**. All execution requests originating from `[NexusCLI](../runtime/cli-and-cueline.md)`, `[UnifiedMCPGateway](../runtime/mcp-gateway.md)`, or autonomous workers must obtain routing authorization through `CapabilityPlanner`.

> 🏛️ **Authority Contract Requirement**: `AGENTS.md` remains repository governance authority. `CapabilityPlanner` and `HybridRouteDecision` remain Nexus route authority. OpenWiki documentation must never create, infer, promote, or duplicate route authority.

---

## 🎯 Capability Planning Logic & Flow

`CapabilityPlanner` evaluates task descriptions, risk scores, code intelligence signals, and budget constraints to compute an optimal execution depth (`LIGHT`, `STANDARD`, or `DEEP`) and activate appropriate governance and tool nodes.

<!-- openwiki: mermaid parse failed and this diagram was converted to a text fence so it does not break rendering. Fix the diagram source and restore the mermaid fence. Parser error: Heuristic: an unescaped angle bracket inside a label breaks rendering; rephrase the label. -->
```text
flowchart TD
    A["Task Description & Route Inputs"] --> B["build_capability_signals()"]
    B --> C["_decide_routing_tier(signals)"]
    C --> D{"base_depth == LIGHT & Safety Blockers > 0?"}
    D -- "Yes" --> E["Escalate to STANDARD depth"]
    D -- "No" --> F["Preserve Base Depth"]
    E --> G["Enforce Required Gates: mempalace, artifact, claim"]
    F --> G
    G --> H["Produce CapabilityPlan & HybridRouteDecision"]
```
*Figure 1: CapabilityPlanner signal evaluation, safety floor escalation, and execution depth resolution logic.*

---

## 🔒 Governance & Delivery Hard Constraints

`CapabilityPlanner` enforces mandatory governance nodes regardless of task parameters:
- **`mempalace_gate`**: Requires memory palace verification for state consistency.
- **`artifact_gate`**: Ensures code modification artifacts conform to schema.
- **`claim_gate`**: Enforces physical evidence verification before claim verification.
- **`delivery_gate`**: Activates fail-closed delivery contracts.

---

## 🏷️ Required V3 Classifications

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
  - nexus/services/mainchain_route_freeze.py:MAINCHAIN_AUTHORITY
claim_ceiling: Canonical route authority responsible for capability node graph composition and execution depth determination.
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
claim_ceiling: Immutable payload contract capturing CapabilityPlanner selection state and route features.
```

```yaml
component: CapabilityRegistry
implementation_status: CURRENT
wiring_status: WIRED
runtime_surfaces:
  - LOCAL_RUNTIME
authority_roles:
  - NONE
evidence_basis:
  - nexus/services/capability_registry.py:CapabilityRegistry
claim_ceiling: Registry mapping CapabilityPlanner node names to UnifiedRuntime invokers; holds zero route authority.
```

---

## 🛠️ Extension Recipe: Adding a Capability Node

To register a new capability node in the `CapabilityPlanner` execution graph:

1. **Define the Node**: Add a new `CapabilityNode` entry in `default_capability_nodes()` within `nexus/engine/capability_planner.py`.
2. **Bind to Registry**: Map the node name to its invoker in `nexus/services/capability_registry.py`.
3. **Register Invoker**: Implement the node execution hook in `[UnifiedRuntime](../architecture/overview.md)`.
4. **Unit Validation**: Add test coverage verifying that `CapabilityPlanner.plan()` correctly sets node status (`required`, `optional`, `conditional`).
5. **Run Checks**: Run `pytest tests/test_lite_route_oracle.py -q` to ensure no route regression.

---

## 🧭 Change Navigation & Validation

### When to Consult
Consult this page when modifying capability selection rules, adding new tools to the planner graph, modifying execution depth safety floors, or debugging route authorization failures.

### Runtime Invariants
- `route_truth_source` in all execution receipts must evaluate to `"CapabilityPlanner"`.
- Modifying route authority elsewhere in the codebase violates system governance.

### Exact Source Files & Symbols
- `nexus/engine/capability_planner.py` -> `CapabilityPlanner`, `CapabilityPlan`
- `nexus/contracts/hybrid_route.py` -> `HybridRouteDecision`
- `nexus/services/mainchain_route_freeze.py` -> `MAINCHAIN_AUTHORITY`

### Focused Tests
- `tests/test_lite_route_oracle.py`
- `tests/test_route_optimization.py`

### Minimal Validation Command
```bash
pytest tests/test_lite_route_oracle.py -q
```
