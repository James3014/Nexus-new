---
type: Concept
title: MCP Gateway & Ingress Protocols
description: Technical design and V3 classification of the Model Context Protocol (MCP) gateway, HTTP/stdio transport adapters, and self-hosted MCP services.
tags: [runtime, mcp, gateway, ingress, transport]
openwiki:
  roles: [architecture, domain]
  change_kinds: [public-api, integration]
  source_paths: [nexus/orchestrator/unified_mcp_gateway.py, nexus/orchestrator/self_hosted_mcp_http.py, nexus/orchestrator/canonical_mcp_ingress.py]
  symbols: [UnifiedMCPGateway, NexusSelfHostedMCPServer, build_mcp_execution_context]
  test_paths: [tests/test_battlesuit_gateway.py]
  invariants: [MCP Gateway must delegate capability route decisions to CapabilityPlanner.]
  validation_commands: [pytest tests/test_battlesuit_gateway.py -q]
---

# MCP Gateway & Ingress Protocols

The **Model Context Protocol (MCP) Gateway** exposes Nexus capabilities to external agents, MCP tools, and HTTP clients. It translates incoming tool calls into canonical task contexts while delegating route authorization strictly to `[CapabilityPlanner](../routing/capability-planner.md)`.

---

## 🏗️ Gateway Architecture & Ingress Pipeline

The MCP subsystem consists of three primary components:
1. **`UnifiedMCPGateway`** (`nexus/orchestrator/unified_mcp_gateway.py`): Core gateway orchestrator managing MCP tool registration, health checking, and execution contexts (`schema: nexus.mcp_canonical_runtime.v1`).
2. **`NexusSelfHostedMCPServer`** (`nexus/orchestrator/self_hosted_mcp_http.py`): HTTP/JSON-RPC server handling `/mcp` endpoints and rejecting non-MCP paths.
3. **`canonical_mcp_ingress`** (`nexus/orchestrator/canonical_mcp_ingress.py`): Constructs `CanonicalTaskContext` payloads with `transport_ingress="mcp"`.

---

## 🔄 MCP Ingress Sequence Flow

```mermaid
sequenceDiagram
    autonumber
    actor Client as External MCP Client
    participant HTTP as NexusSelfHostedMCPServer
    participant Ingress as canonical_mcp_ingress
    participant Gateway as UnifiedMCPGateway
    participant Planner as CapabilityPlanner
    participant Enforcer as CompletionEnforcer

    Client->>HTTP: POST /mcp (JSON-RPC tool call)
    HTTP->>Ingress: build_mcp_execution_context(request)
    Ingress-->>HTTP: CanonicalTaskContext
    HTTP->>Gateway: handle_mcp_request(ctx)
    Gateway->>Planner: plan(task_desc, route)
    Planner-->>Gateway: CapabilityPlan
    Gateway->>Gateway: Execute MCP Tool Action
    Gateway->>Enforcer: verify_mcp_completion(receipt)
    Enforcer-->>Gateway: Verification OK
    Gateway-->>HTTP: JSON-RPC Response
    HTTP-->>Client: Tool Result Payload
```
*Figure 1: Request flow for incoming Model Context Protocol tool invocations through HTTP ingress and CapabilityPlanner routing.*

---

## 🏷️ Required V3 Classifications

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
claim_ceiling: Core MCP execution gateway; handles MCP tool requests and binds execution contexts to CapabilityPlanner routing.
```

```yaml
component: NexusSelfHostedMCPServer
implementation_status: CURRENT
wiring_status: WIRED
runtime_surfaces:
  - MCP_GATEWAY
authority_roles:
  - EXECUTION_AUTHORITY
evidence_basis:
  - nexus/orchestrator/self_hosted_mcp_http.py:NexusSelfHostedMCPServer
claim_ceiling: Self-hosted HTTP server providing JSON-RPC transport over /mcp endpoints.
```

```yaml
component: canonical_mcp_ingress
implementation_status: CURRENT
wiring_status: WIRED
runtime_surfaces:
  - MCP_GATEWAY
authority_roles:
  - NONE
evidence_basis:
  - nexus/orchestrator/canonical_mcp_ingress.py:build_mcp_execution_context
claim_ceiling: Ingress context builder standardizing incoming MCP requests into CanonicalTaskContext.
```

---

## 🛠️ Extension Recipe: Adding an MCP Tool Endpoint

To expose a new tool through the MCP Gateway:

1. **Define Tool Schema**: Add the JSON Schema declaration in `nexus/orchestrator/unified_mcp_gateway.py`.
2. **Register Handler**: Map the tool name in `UnifiedMCPGateway._register_default_tools()`.
3. **Route Wire**: Ensure execution invokes `[CapabilityPlanner](../routing/capability-planner.md)` for route authorization before executing tool logic.
4. **Validation Test**: Add a test case in `tests/test_battlesuit_gateway.py` verifying tool invocation and error handling.
5. **Execute Validation**: Run `pytest tests/test_battlesuit_gateway.py -q`.

---

## 🧭 Change Navigation & Validation

### When to Consult
Consult this page when extending MCP tool APIs, debugging HTTP/stdio transport errors, or modifying MCP ingress context construction.

### Runtime Invariants
- Direct MCP tool execution without obtaining a `CapabilityPlan` from `[CapabilityPlanner](../routing/capability-planner.md)` is prohibited.
- Requests to non-`/mcp` HTTP paths must be rejected by `NexusSelfHostedMCPServer`.

### Exact Source Files & Symbols
- `nexus/orchestrator/unified_mcp_gateway.py` -> `UnifiedMCPGateway`
- `nexus/orchestrator/self_hosted_mcp_http.py` -> `NexusSelfHostedMCPServer`
- `nexus/orchestrator/canonical_mcp_ingress.py` -> `build_mcp_execution_context`

### Focused Tests
- `tests/test_battlesuit_gateway.py`

### Minimal Validation Command
```bash
pytest tests/test_battlesuit_gateway.py -q
```

## 🧭 Diagnostic Boundary: `HOST_ACTION_BINDING_GAP`

When ChatGPT discovers an MCP action or tool but direct invocation fails
host-side with `The nexus tool has been disabled` or an equivalent action
binding error, classify the event as `HOST_ACTION_BINDING_GAP` only when the
same event shows no ingress in DevSpace or Gateway evidence and the Nexus
server processes remain healthy. The absence of ingress is load-bearing
evidence: do not patch, restart, reinstall, or rewrite the Nexus Gateway for
this class of event without separate runtime evidence.

The historical maximum claim for this diagnosis is
`B1_HOST_BINDING_FAILURE_LOCALIZED`; it does not establish that the ChatGPT
platform is permanently fixed. Record the event, host-side error, ingress
observation, process-health observation, and evidence timestamp before any
independent remediation.
