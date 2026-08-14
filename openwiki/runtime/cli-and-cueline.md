---
type: Concept
title: CLI, Self-Hosted Task Service & Cueline Operations
description: Current operational reference for the Nexus CLI, durable self-hosted task lifecycle, Cueline process adapter, and bounded NightShift candidate queue.
tags: [cli, cueline, runtime, self-hosted, nightshift, execution]
openwiki:
  roles: [architecture, domain, operations]
  change_kinds: [public-api, workflow]
  source_paths: [scripts/engine/nexus_cli.py, scripts/ops/nexus_cueline_worker.py, nexus/orchestrator/self_hosted_task_service.py, nexus/core/task_continuity.py, nexus/app/nightshift_runner_service.py, nexus/services/nightshift_queue_consumer.py, pyproject.toml]
  symbols: [nexus, SelfHostedTaskService, ContinuitySnapshot, AutoResearchNightShift, NightshiftQueueConsumer]
  test_paths: [tests/test_cli_commands.py, tests/ops/test_nexus_cueline_worker.py, tests/nexus/orchestrator/test_self_hosted_task_service.py, tests/core/test_task_continuity.py, tests/services/test_nightshift_queue_consumer.py]
  invariants: [Cueline accepts one JSON object and uses shell-free argv execution. SelfHostedTaskService preserves existing lifecycle and authority contracts. NightShift queue is candidate-generation-only and forbids worker commit, push, approve, and integrate.]
  validation_commands: [pytest tests/ops/test_nexus_cueline_worker.py tests/nexus/orchestrator/test_self_hosted_task_service.py tests/services/test_nightshift_queue_consumer.py -q]
---

# CLI, Self-Hosted Task Service & Cueline Operations

The repository exposes a Click-based `nexus` CLI and a separate `nexus-cueline-worker` process adapter. Since the previous OpenWiki synchronization, the durable self-hosted task service has expanded materially and the NightShift path now has an explicit fail-closed candidate-queue consumer.

---

## 🛠️ Main CLI and Self-Hosted Surface

The primary CLI entrypoint is registered from `scripts.engine.nexus_cli:nexus`. Use `nexus --help`, `nexus nexus --help`, and `nexus self-hosted --help` for the current physical command inventory rather than copying a historical command list into implementation code.

The durable lifecycle implementation behind the self-hosted surface lives in `nexus/orchestrator/self_hosted_task_service.py`.

`SelfHostedTaskService` composes existing contracts for:

- tracked Task Card and Owner Inline task identity;
- lifecycle action envelopes and idempotency;
- canonical source/Target roots;
- workforce admission and worker registry binding;
- Candidate capture and verification;
- independent Candidate acceptance;
- approval/integration lifecycle;
- recovery, retry, cleanup, reconciliation, and actionable-task projection;
- task-continuity event projection.

It is a service facade over those contracts, not a replacement for their separate authorities.

### Direct vs Isolated execution lane

The current source contains a bounded fast/direct eligibility check. Direct canonical execution is rejected when the task exceeds the safe bounded surface, including cases such as:

- more than four allowed files;
- missing verifier commands;
- deletion authority;
- migration or schema authority;
- route-authority mutation;
- security-policy weakening;
- public/production claim promotion;
- dirty canonical checkout or another active mutation task;
- generated/large changes or lockfile changes.

When blocked from the direct lane, the service projects the work toward an isolated Target instead of silently weakening those conditions.

---

## ⚙️ Cueline Worker (`STANDALONE_OPS`)

`nexus-cueline-worker` reads exactly one JSON object from stdin, validates the operation-specific schema, builds an argv list, and invokes:

```text
python -m scripts.engine.nexus_cli self-hosted <operation>
```

The adapter uses `subprocess` argv execution with `shell=False`. It rejects positional command-line text and unknown payload keys rather than forwarding arbitrary shell input.

Current allowed operations are:

- `submit`
- `status`
- `wait`
- `list-actionable` / `list_actionable`
- `approve`
- `integrate`
- `dispose`
- `cancel`

Example:

```bash
printf '%s\n' '{"op":"status","task_id":"TASK_ID"}' | nexus-cueline-worker
```

Cueline is an adapter into the self-hosted lifecycle; it does not create a parallel task state machine.

---

## 🧠 Cross-Attempt Continuity

`nexus/core/task_continuity.py` projects the existing task/attempt event stream into `ContinuitySnapshot` / `ResumeContext` objects. `SelfHostedTaskService` imports `events_from_attempt_records` from that module.

Continuity preserves evidence references, rejected strategies, unresolved risks, next action, and claim ceiling. The module explicitly states that it is not a task state machine, router, verifier, or lifecycle authority.

---

## 🌙 NightShift Bounded Candidate Queue

`AutoResearchNightShift` remains the research/repair runner, while `NightshiftQueueConsumer` provides a narrow fail-closed consumer for `.nexus/nightshift/pending.json` candidate demands.

A queue item must satisfy the current source contract before dispatch:

- schema `nexus.nightshift_candidate_demand.v1`;
- role `bounded_candidate_generation`;
- `mutation_intent=false`;
- `external_verification_required=true`;
- required controls include isolated directory, bounded context, JSON event receipt, parser, focused tests, and verifier;
- worker permissions must explicitly forbid `commit`, `push`, `approve`, and `integrate`;
- task and source revision identity must be present;
- `UnifiedRuntime` evidence must report workforce admission `ALLOW`;
- canonical invocation authority must report `ALLOW` with `gate_passed=true`.

Only then does the consumer call its injected dispatcher and mark the manifest item `DISPATCHED`. Invalid or incomplete evidence returns `BLOCK` rather than guessing a fallback.

---

## 🏷️ Required V3 Classifications

```yaml
component: NexusCLIEntrypoint
implementation_status: CURRENT
wiring_status: WIRED
runtime_surfaces:
  - MAIN_CLI
authority_roles:
  - EXECUTION_AUTHORITY
evidence_basis:
  - pyproject.toml:[tool.poetry.scripts].nexus
  - scripts/engine/nexus_cli.py:nexus
claim_ceiling: Registered Click command interface for Nexus command surfaces.
```

```yaml
component: SelfHostedTaskService
implementation_status: CURRENT
wiring_status: WIRED
runtime_surfaces:
  - LOCAL_RUNTIME
authority_roles:
  - EXECUTION_AUTHORITY
evidence_basis:
  - nexus/orchestrator/self_hosted_task_service.py:SelfHostedTaskService
  - scripts/engine/nexus_cli.py:self-hosted
claim_ceiling: Durable restartable service facade for governed task lifecycle actions; it consumes existing route, workforce, verification, approval, integration, and continuity contracts rather than replacing them.
```

```yaml
component: CuelineProcessAdapter
implementation_status: CURRENT
wiring_status: WIRED
runtime_surfaces:
  - STANDALONE_OPS
authority_roles:
  - EXECUTION_AUTHORITY
evidence_basis:
  - pyproject.toml:[tool.poetry.scripts].nexus-cueline-worker
  - scripts/ops/nexus_cueline_worker.py:main
claim_ceiling: Single-request stdin adapter that validates a bounded payload and invokes one self-hosted Nexus CLI subprocess with shell-free argv execution.
```

```yaml
component: NightshiftQueueConsumer
implementation_status: CURRENT
wiring_status: UNKNOWN
runtime_surfaces: []
authority_roles:
  - NONE
evidence_basis:
  - nexus/services/nightshift_queue_consumer.py:NightshiftQueueConsumer
claim_ceiling: Current fail-closed bounded-candidate consumer exists; class/source evidence alone does not establish which production scheduler invokes it.
```

---

## 🧭 Change Navigation & Validation

### When to Consult
Consult this page when changing CLI commands, self-hosted task actions, execution-lane eligibility, task retry/recovery/cleanup behavior, Cueline payloads, continuity projection, or NightShift queue dispatch.

### Runtime Invariants
- Cueline accepts one bounded JSON object and never forwards arbitrary shell text.
- `SelfHostedTaskService` does not create a second route authority.
- Direct canonical eligibility must remain fail-closed; unsafe scope moves to isolated Target handling.
- Task continuity remains projection-only.
- NightShift queued workers cannot commit, push, approve, or integrate.
- Queue dispatch requires both workforce admission and canonical invocation authority evidence.

### Exact Source Files & Symbols
- `scripts/engine/nexus_cli.py` → `nexus` and self-hosted command surface
- `scripts/ops/nexus_cueline_worker.py` → `ALLOWED_OPERATIONS`, `parse_and_validate_input`, `build_cli_argv`, `main`
- `nexus/orchestrator/self_hosted_task_service.py` → `SelfHostedTaskService`, `check_fast_lane_eligible`, lifecycle/retry/action projections
- `nexus/core/task_continuity.py` → continuity projection
- `nexus/app/nightshift_runner_service.py` → `AutoResearchNightShift`
- `nexus/services/nightshift_queue_consumer.py` → `NightshiftQueueConsumer`

### Focused Tests
- `tests/ops/test_nexus_cueline_worker.py`
- `tests/nexus/orchestrator/test_self_hosted_task_service.py`
- `tests/core/test_task_continuity.py`
- `tests/services/test_nightshift_queue_consumer.py`

### Minimal Validation Command
```bash
pytest tests/ops/test_nexus_cueline_worker.py tests/nexus/orchestrator/test_self_hosted_task_service.py tests/services/test_nightshift_queue_consumer.py -q
```
