# Runtime Caller Inventory — 2026-07-14

## Authority

```text
NexusPipeline = workflow
CapabilityPlanner = route
UnifiedRuntime = Local/Online invocation
online_execution_policy = Online authorization decision
```

Active repair Online seam: `PipelineRepairMixin._execute_single_repair` only.

## Inventory

| Path | Symbol | Classification | Migration |
| --- | --- | --- | --- |
| `nexus/engine/pipeline_repair.py` | `_run_unified_advisor_online` | CANONICAL_UNIFIED_RUNTIME_CALLER | RETAIN |
| `nexus/services/gateway.py` | `ask_unified` | CANONICAL_UNIFIED_RUNTIME_CALLER | RETAIN (edge adapters) |
| `nexus/research/sprint_service.py` | `_ask_unified_candidate` | CANONICAL_UNIFIED_RUNTIME_CALLER | THIN_COMPATIBILITY_WRAPPER |
| `nexus/research/day_shift_optimizer.py` | `_ask_unified` | CANONICAL_UNIFIED_RUNTIME_CALLER | THIN_COMPATIBILITY_WRAPPER |
| `nexus/app/nightshift_runner_service.py` | `_ask_unified_candidate` | CANONICAL_UNIFIED_RUNTIME_CALLER | THIN_COMPATIBILITY_WRAPPER |
| `scripts/engine/nexus_cli.py` | `content_rewrite` | CANONICAL_UNIFIED_RUNTIME_CALLER | RETAIN |
| `nexus/engine/phases/repair.py` | `surgical_ask` fallback | LEGACY_ACTIVE_CALLER | RETAIN_WITH_JUSTIFICATION (secondary; not nexus-run default Online) |
| `scripts/engine/commands/local_assist_actions.py` | `LocalAssistService.handle` | COMPATIBILITY_WRAPPER | DEFER (explicit local-assist CLI, not nexus run Online) |
| `nexus/services/local_assist_*_canary.py` | canary handlers | TEST_ONLY_CALLER | DEFER |
| `nexus/core/drone_engine.py` | local brain ask | OUT_OF_SCOPE_PRODUCT_PATH | DEFER |

## Authorization

All physical Online CLI invocations enforce `OnlineExecutionDecision` via:

- `physical_online_authorized(context)` in registered CLI guard
- Gateway structured path for non-injected transports

`NEXUS_EXTERNAL_RUNTIME_AUTHORIZED` maps only to `operator_environment_override`.
