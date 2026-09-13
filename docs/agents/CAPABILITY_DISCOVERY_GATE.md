# Architecture Capability Discovery Gate v1

This gate prevents delegated engineering agents from inventing a second implementation before evaluating existing Nexus capabilities.

## Boundary

`CAPABILITY_DISCOVERY_INDEX.v1.json` is navigation evidence only. It is not CapabilityPlanner authority, Workforce Admission authority, execution authority, acceptance authority, merge authority, release authority, or production truth. CapabilityPlanner remains the sole route/capability-selection authority defined by `AGENTS.md`.

## Required discovery before mutation

Before a host dispatches a worker that may mutate a workspace, the controller must produce a bounded discovery receipt covering four evidence layers:

1. `architecture` — the current cross-repository architecture/index relevant to the intent;
2. `source` — current source/symbol evidence from the likely owner/donor repository;
3. `history` — Issue/Task Card/PR/canary evidence showing prior intent or proven behavior;
4. `runtime` — current live capability/tool/provider/runtime evidence when runtime truth matters.

The controller must choose exactly one disposition:

- `REUSE_EXISTING`
- `EXTEND_EXISTING`
- `WRAP_EXISTING`
- `NEW_CAPABILITY_JUSTIFIED`
- `BLOCKED_UNKNOWN`

A mutating worker must never start with `BLOCKED_UNKNOWN`. `NEW_CAPABILITY_JUSTIFIED` requires an explicit explanation of why no existing donor satisfies the need. The discovery receipt does not itself authorize mutation; normal Owner/Nexus execution authority remains separately required.

## Regression: ChatGPT Web / OpenCLI / Open SWE

Intent resembling any of the following must discover `chatgpt_web_semantic_transport` before a new browser transport is proposed:

- automate or operate an authenticated ChatGPT Web conversation;
- create/resume a browser-backed model conversation;
- use OpenCLI as ChatGPT Web transport;
- run Open SWE against ChatGPT Web.

Current donor evidence is indexed to the existing Open SWE → OpenCLI → ChatGPT WEB path, including the resident five-repository canary evidence. A second ChatGPT browser transport is therefore not a valid initial `NEW_CAPABILITY_JUSTIFIED` disposition unless current source/history/runtime evidence proves the indexed donor cannot satisfy the bounded requirement.

## DevSpace enforcement

DevSpace is the mechanical admission boundary for delegated local workers. Its MCP `agent_start` surface must fail closed for a write-capable worker when no valid discovery receipt is supplied. The receipt must be bound to the current canonical `James3014/Nexus-new` main revision and exact tracked bytes of `docs/agents/CAPABILITY_DISCOVERY_INDEX.v1.json`.

DevSpace verifies only receipt/index identity and structural reuse constraints. It does not select the capability, decide correctness, or gain Nexus routing authority. The verified receipt is injected into the delegated worker prompt so the worker inherits the donor/reuse context rather than rediscovering the system from scratch.
