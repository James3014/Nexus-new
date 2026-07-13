# CLI Local Assist Advisor — Gate 2 Baseline (2026-07-14)

Terminal target: `NEXUS_CLI_LOCAL_ASSIST_ADVISOR_EXECUTION_PROVEN`  
Status: baseline + authority trace recorded; behavior changes follow this document

## Starting Baseline

| Field | Value |
| --- | --- |
| Branch | `feature/repair-mainline-p0-20260708` |
| HEAD at Gate 2 start | `3ac3eaa146aaceb5c2cfcf0b6376338574b1e597` |
| Gate 1 contract commit | `ace476cd5239e9cc646c1b1c2d8a544fc40d13d2` |
| Gate 1 suite | 151 passed (prior Gate 1 evidence) |
| Recorded at | 2026-07-14 |

Gate 1 ancestry (recent):

```text
3ac3eaa14 docs: canonicalize historical PR task pack
ace476cd5 fix(runtime): normalize online invoker payload and binding identity
f43ff615b docs(runtime): record gate1 runtime contract stabilization baseline
871cd1975 fix(runtime): keep local ollama discovery off online transport path
d533eecf6 feat(runtime): land unified runtime with provider/transport contract
```

## Path Classification (allowed scope)

| Path | State at start | Classification |
| --- | --- | --- |
| `scripts/engine/nexus_cli.py` | tracked dirty (+119 content-rewrite UnifiedRuntime) | PRE_EXISTING_TRACKED_CHANGE |
| `nexus/app/command_service.py` | clean | NEW_GATE2_CHANGE (if touched) |
| `nexus/engine/canonical_task_seam.py` | clean | NEW_GATE2_CHANGE |
| `nexus/services/canonical_local_assist_policy.py` | clean | NEW_GATE2_CHANGE |
| `nexus/services/unified_runtime.py` | clean (Gate 1 tracked) | NEW_GATE2_CHANGE only if required |
| `nexus/services/gateway.py` | clean (Gate 1 tracked) | avoid unless required |
| `nexus/engine/pipeline_repair.py` | clean | NEW_GATE2_CHANGE (selected seam) |
| `nexus/engine/phases/repair.py` | clean | rejected as primary insertion |

Unrelated dirty wiki/bench/local_heal paths remain out of Gate 2 scope.

## [Active Repair Authority]

```text
Product entry:          nexus run / NexusCommandService
Workflow lifecycle:     NexusPipeline (PXDRAC)
Route authority:        CapabilityPlanner
Execution lineage:      UnifiedRuntime (Local + Online stages)
Formal acceptance:      existing verifier / completion gate
```

UnifiedRuntime must not replace NexusPipeline.

## [Physical Caller Trace]

```text
scripts/engine/nexus_cli.py :: run / top_run
  → execute_single_task_via_service(task_id, REPO_ROOT)
      (nexus/engine/canonical_task_seam.py)
  → TaskRequest → NexusCommandService.execute_bug|execute_feature
      (nexus/app/command_service.py)
  → NexusEngine.run_bug|run_feature
      (nexus/engine/coordinator.py)
      state.metadata.update(context)
  → NexusPipeline
      (nexus/engine/pipeline.py)
  → PipelineRepairMixin._repair_audit_loop
  → PipelineRepairMixin._execute_single_repair
      (nexus/engine/pipeline_repair.py)
      → gateway.surgical_ask(...)   [when use_surgical_repair]
      OR ctx.repairer.run(...)      [RepairPhaseHandler fallback]
```

Composition R plugins (PhaseFactory → `phases/repair.py`) only run when registry plugin `R` is active; the default Online surgical path for `nexus run` is owned by **`pipeline_repair.py`**.

## [Rejected Insertion Points]

| Point | Why rejected |
| --- | --- |
| CLI → `LocalAssistService.handle()` directly | Bypasses pipeline / command service authority |
| UnifiedRuntime as full workflow engine | Replaces NexusPipeline lifecycle |
| `phases/repair.py` as sole Gate 2 seam | Secondary/fallback path; not the default Online surgical owner for `nexus run` |
| New Router / Planner / RouteMode | Hard-rule prohibition |
| Second repair path that duplicates Online | Forbidden third repair path |

## [Selected Insertion Point]

```text
nexus/engine/pipeline_repair.py
  PipelineRepairMixin._execute_single_repair
```

Advisor (when mode=`advisor`) inserts **before** Online provider invocation on this path, owned by UnifiedRuntime Local-before-Online, with pipeline report referencing the Unified Runtime receipt.

## Claim Boundary (Gate 2 start)

```text
production_ready = false
public_claim_allowed = false
proven_token_savings = false
proven_time_savings = false
proven_cost_reduction = false
local_candidate_execution_complete = false
verified_subtask_execution_complete = false
```

## Implementation Notes (post-baseline)

### CLI policy semantics

Canonical: `disabled | shadow | advisor`  
Legacy aliases (receipt-recorded): `planner→shadow`, `explicit→advisor`  
Invalid policy: fail-closed `invalid_local_assist_policy`

### Context propagation

```text
CLI --local-assist-policy
→ build_execution_context_fields
→ execute_single_task_via_service(..., execution_context=...)
→ TaskRequest.execution_context
→ NexusCommandService merges into engine context
→ state.metadata
→ PipelineRepairMixin._execute_single_repair
```

### Advisor execution

Selected seam: `PipelineRepairMixin._execute_single_repair`  
Local+Online lineage: `UnifiedRuntime` (not CLI→LocalAssistService)  
Bounded scope via `collect_bounded_allowed_files`  
Degrade: `ONLINE_CONTINUED_WITHOUT_LOCAL_ASSIST` / `degraded_to_online`  
Pointer: `.nexus/reports/run/{task}.unified_runtime_pointer.json` linked from pipeline report

### Focused suite evidence

```text
168 passed (Gate 1 suite + Gate 2 policy/propagation/advisor tests)
SCRATCH: focused_gate.log, policy_contract.log, advisor_runtime.log
```

### Live smoke

```text
status = IMPLEMENTED_NOT_LIVE_PROVEN
reason = NEXUS_EXTERNAL_RUNTIME_AUTHORIZED unset; refuse live Online provider invocation
ollama_reachable = true (local only; not sufficient for Online authorization)
```

Terminal marker `NEXUS_CLI_LOCAL_ASSIST_ADVISOR_EXECUTION_PROVEN` is **not** claimed without live Local+Online receipts.


## Skeptic remediation (2026-07-14)

* Removed blind `local_forwarded=True` when Local invoked without packed `local_outputs`.
* `local_context_forwarded` / `local_assist_contributed` require evidence_refs packing proof.
* Distinct booleans on metadata/pointer/report:
  `local_assist_success`, `online_success`, `runtime_receipt_complete`, `task_pipeline_success`.
* Non-surgical `_execute_single_repair` now runs Advisor via injected Online or `gateway.ask_structured`.
* Tests enter production `_execute_single_repair` (surgical + non-surgical).
* Focused suite: **173 passed**.
* Live: `IMPLEMENTED_NOT_LIVE_PROVEN` (no `NEXUS_EXTERNAL_RUNTIME_AUTHORIZED`).
