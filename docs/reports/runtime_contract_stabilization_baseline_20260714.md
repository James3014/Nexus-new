# Runtime Contract Stabilization Baseline — 2026-07-14

Gate: `NEXUS_RUNTIME_CONTRACT_STABILIZATION` (Gate 1)
Terminal state target: `NEXUS_RUNTIME_CONTRACT_STABILIZED`
Status: baseline recorded; behavior changes follow this document

## Git State (task start)

| Field | Value |
| --- | --- |
| Branch | `feature/repair-mainline-p0-20260708` |
| HEAD | `f4fc2f3dd9202575ab8a1607058f9a872cb40964` |
| HEAD subject | `docs: isolate conflicting root authorities` |
| HEAD time | `2026-07-14 04:22:35 +0800` |
| Recorded at | `2026-07-14 04:48:23 +0800` |

## Relevant Dirty Paths (classification)

| Path | Diff vs HEAD | Classification |
| --- | --- | --- |
| `nexus/app/nightshift_runner_service.py` | tracked modify (+199/-partial in 6-file bundle) | PRE_EXISTING_TRACKED_CHANGE |
| `nexus/engine/capability_planner.py` | tracked modify (+28) | PRE_EXISTING_TRACKED_CHANGE |
| `nexus/research/day_shift_optimizer.py` | tracked modify | PRE_EXISTING_TRACKED_CHANGE |
| `nexus/research/sprint_service.py` | tracked modify | PRE_EXISTING_TRACKED_CHANGE |
| `nexus/services/gateway.py` | tracked modify | PRE_EXISTING_TRACKED_CHANGE |
| `scripts/engine/nexus_cli.py` | tracked modify | PRE_EXISTING_TRACKED_CHANGE |
| `nexus/services/unified_runtime.py` | untracked, 1299 lines | PRE_EXISTING_UNTRACKED_IMPLEMENTATION |
| `tests/services/test_unified_runtime.py` | untracked | PRE_EXISTING_UNTRACKED_IMPLEMENTATION |
| `tests/research/test_day_shift_optimizer.py` | untracked | PRE_EXISTING_UNTRACKED_IMPLEMENTATION |
| `tests/research/test_sprint_service.py` | tracked modify (includes 3 failing cases) | PRE_EXISTING_TRACKED_CHANGE |

Tracked bundle for the six primary runtime callers/entry files at handoff:

```text
6 files changed, 894 insertions(+), 72 deletions(-)
```

Unrelated dirty paths (docs, wiki, local_heal, bench artifacts, learn reports, crystal_factory, etc.) exist in the worktree. They are **out of Gate 1 scope** and must not be staged by this task.

## Environment Probe

```text
BattlesuitGateway(project_root=".").oauth_provider == "ollama"
```

Cause: `oauth_provider=auto` detects a live local Ollama and stores that identity on the Gateway default.

## Known Focused Failures (reproduced)

```text
tests/research/test_sprint_service.py::
  test_llm_generator_uses_unified_runtime_on_revisioned_workspace
  → LLMCandidateError: llm_missing_replacement

tests/research/test_sprint_service.py::
  test_llm_generator_can_route_local_assist_into_online_context
  → LLMCandidateError: llm_missing_replacement

tests/research/test_day_shift_optimizer.py::
  test_dayshift_generation_uses_unified_runtime_on_revisioned_workspace
  → response["patch"] == ""
```

Failure class: provider identity and transport selection are conflated.

Callers copy `gateway.oauth_provider` (`ollama`) into Online `route["provider"]`. Gateway Online resolution then treats `ollama` as a registered Online CLI provider, fails with `provider_adapter_resolution_failed`, and returns an empty Online response even when `ask_structured` is an injected transport.

## Runtime Authority Decision (Phase 1)

### Selected model

```text
Product entry authority:
  nexus run / NexusCommandService

Workflow lifecycle authority:
  NexusPipeline / PXDRAC

Route and capability authority:
  CapabilityPlanner / HybridRouteDecision

Model and capability execution authority:
  UnifiedRuntime

Formal acceptance authority:
  existing verifier / completion gate

Runtime truth authority:
  one canonical task receipt (nexus.unified_runtime.receipt.v1)
```

UnifiedRuntime remains an **execution subsystem**. It owns Local/Online/capability invocation lineage and receipt assembly for those stages. It does **not** own product entry, PXDRAC lifecycle, delivery semantics, or learning policy beyond accepting learning callbacks.

### Rejected alternatives

| Alternative | Why rejected |
| --- | --- |
| UnifiedRuntime replaces NexusPipeline | Would bypass PXDRAC phases, completion gate, delivery semantics, and command-service ownership |
| Agent-specific runtimes (Grok/Codex/Gemini/Claude) | Multiplies provider layers; contradicts provider-neutral contract |
| New Router / Planner / RouteMode / topology | Scope expansion; CapabilityPlanner remains sole route authority |
| Register Ollama as Online CLI only to green tests | Hides identity conflation; no real Online Ollama CLI contract is required here |

### Affected call sites (Gate 1)

- `nexus/services/gateway.py` — Online transport resolution at `ask_unified`
- `nexus/research/sprint_service.py` — Online route provider + response consumption
- `nexus/research/day_shift_optimizer.py` — same
- `nexus/services/unified_runtime.py` — shared binding helpers / response accessor

### Migration boundary

- In scope: provider/transport contract, three integration failures, reviewable Unified Runtime baseline
- Out of scope: `nexus run` Local Assist modes, full caller thin-wrapper convergence, paired cost experiments, public claims

## Claim Boundary (baseline)

The following remain false and are not asserted by this Gate:

```text
production_ready
public_claim_allowed
proven_token_savings
proven_time_savings
proven_cost_reduction
canonical_cli_local_assist_execution_complete
```

## Gate 1 Implementation Notes (post-baseline)

### Provider / transport contract

Added to `nexus/services/unified_runtime.py`:

* `LOCAL_ONLY_PROVIDERS` (includes `ollama`)
* `build_online_route(...)` — does not promote local discovery into Online `route.provider`
* `resolve_online_transport_binding(...)` — deterministic precedence
* `extract_online_stage_payload(...)` — single Online response unwrapping helper

Gateway `ask_unified` uses the binding:

1. explicit `online_invoker`
2. injected / bound `ask_structured`
3. registered Online CLI provider
4. gateway compatibility for empty / local-only provider
5. fail-closed for unknown Online providers

### Caller fixes

* Sprint / DayShift / NightShift: route via `build_online_route`, response via `extract_online_stage_payload`
* Ollama auto-detect no longer empties Online structured output when transport is injected

### Focused gate evidence

```text
145 passed
  tests/engine/test_canonical_task_seam.py
  tests/engine/test_cli_work_path_audit.py
  tests/test_cli_output_contract.py
  tests/test_cli_content_rewrite.py
  tests/services/test_unified_runtime.py
  tests/services/test_local_assist_service.py
  tests/services/test_local_assist_bounded_dispatch.py
  tests/services/test_cloud_agent_cli_adapter.py
  tests/services/test_cloud_agent_contract.py
  tests/services/test_cloud_local_stage_chain.py
  tests/research/test_sprint_service.py
  tests/research/test_day_shift_optimizer.py
```

Three previously failing integration cases are green.

### Claim boundary (unchanged)

```text
production_ready = false
public_claim_allowed = false
proven_token_savings = false
proven_time_savings = false
proven_cost_reduction = false
canonical_cli_local_assist_execution_complete = false
```

## Next Gate (not started)

```text
NEXUS_CLI_LOCAL_ASSIST_EXECUTION
```
