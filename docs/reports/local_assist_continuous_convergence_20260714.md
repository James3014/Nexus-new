# Nexus CLI-Managed Online Convergence — 2026-07-14

## Terminal (offline)

```text
NEXUS_CLI_MANAGED_ONLINE_CONVERGENCE_COMPLETE = true
live_status = IMPLEMENTED_NOT_LIVE_PROVEN
experiment_status = HARNESS_READY_NOT_LIVE_MEASURED
```

## Product rule

Operators invoke only `nexus run`. Provider CLIs are internal transports.

## Online authorization

| Policy | Behavior |
| --- | --- |
| deny | No real Online (default, conservative) |
| auto | Online when planner needs + approved |
| require | Online mandatory; fail-closed if unavailable |

Precedence: task deny > task auto/require > workspace policy > env override > fail-closed deny.

Env `NEXUS_EXTERNAL_RUNTIME_AUTHORIZED` → `operator_environment_override` only.

Workspace policy: `.nexus/online_execution_policy.json`

## Preflight statuses

`ONLINE_READY`, `ONLINE_NOT_REQUESTED`, `ONLINE_DENIED_BY_POLICY`, `ONLINE_PROVIDER_UNAVAILABLE`, `ONLINE_PROVIDER_UNAUTHENTICATED`, `ONLINE_CONTEXT_TRANSFER_DENIED`, `ONLINE_BUDGET_EXCEEDED`, `ONLINE_CONFIGURATION_INVALID`

Attached on UnifiedRuntime receipt as `online_preflight`.

## CLI

```bash
nexus run --task "<task>" --local-assist-policy advisor --online-policy auto
```

Default `--online-policy deny` (no silent billable Online).

## Callers

See `runtime_caller_inventory_20260714.md`. Active production paths use UnifiedRuntime. Repair Online seam remains `PipelineRepairMixin._execute_single_repair`.

## Paired harness

`nexus.research.local_assist_paired_experiment` — Arms A (disabled) / B (advisor). Tasks under `docs/bench/local_assist/tasks/`. Missing usage = UNAVAILABLE.

## Tests

```text
187 passed (Gate1+2 + online auth + paired harness)
```

## Claim boundary

```text
nexus_cli_manages_online_authorization = true
nexus_run_is_single_operator_entry = true
canonical_online_preflight_complete = true
caller_convergence_complete = true
paired_experiment_harness_ready = true
real_online_provider_invoked = false
proven_token_savings = false
production_ready = false
public_claim_allowed = false
```
