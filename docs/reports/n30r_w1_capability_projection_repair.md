# N30R-W1C Closeout: Capability Projection Closure

**Status**: N30R_W1_CAPABILITY_PROJECTION_PASS

## Baseline
- baseline SHA: 72f92400a
- W1C closure commit: (see git log)

## Contract discovery
- SSD schema source: `nexus/engine/capability_planner.py` (signal_snapshot["ssd_route_map"])
- canonical selected-set source: `ssd_route_map.capability_reasons` keys
- projection helper: `nexus/services/local_heal/local_model_capability_wiring.project_planner_capabilities_for_local_executor()`
- registry source: `nexus/services/local_heal/local_model_capability_wiring.py`
- standalone definitions: `_DEFINITIONS_STANDALONE` (delivery_gate, local_model_executor)
- control-plane set: `CONTROLLER_PLANE_CAPABILITIES` (harness_preflight_sensor, research_route, mempalace_gate)
- executable classifier: `CapabilityWiringStatus` enum
- dependency policy: hard dependency errors invalidate projection (fail-closed)

## Capability accounting (8 planner-selected)

| Capability | Category | Wiring Status | Local Supported |
|---|---|---|---|
| artifact_gate | executable | gate_executable | yes |
| claim_gate | executable | gate_executable | yes |
| delivery_gate | executable | gate_executable (standalone) | yes |
| local_model_executor | executable | executable (standalone) | yes |
| repair_loop | executable | localheal_executable | yes |
| harness_preflight_sensor | control_plane | planner-level sensor | no |
| research_route | control_plane | planner-level routing | no |
| mempalace_gate | control_plane | planner-level governance gate | no |

- executable: 5
- advisory: 0
- control-plane: 3
- unknown: 0
- dropped: 0
- dependency errors: 0

## Projection
- source: ssd_route_map_capability_reasons
- planner selected count: 8
- projected count: **5** (executable + advisory only; control-plane not passed to executor)
- valid: true
- deterministic ordering: alphabetical, deduplicated
- snapshot unchanged: verified

## End-to-end
- Planner → projection accounted: YES (8 = 5 executable + 3 control_plane)
- projection → Executor: YES (selected_capabilities = 5 executable+advisory)
- Executor → Pipeline: YES (same tuple)
- Pipeline → receipt: YES (selected_capabilities_used matches)
- metadata postcondition: bridge verifies request.selected_capabilities == meta["selected_capabilities_used"]

## Receipt provenance
- capability_projection_source: recorded
- planner_selected_capability_count: recorded
- executor_selected_capability_count: recorded
- executable/advisory/control_plane/unknown/dropped counts: recorded
- capability_projection_sha256: recorded

## Tests
- new W1C tests: 28 (tests/unit/local_heal/test_n30r_w1c_capability_projection.py)
- wiring tests: 14 passed (test_local_model_capability_wiring.py)
- bridge tests: 23 passed (test_n30r_real_core_bridge.py)
- W0 contract tests: 24 passed (test_n30r_w0_contract_audit.py)
- additional suites: 58 passed (executors, armor receipt gate, routing contracts)
- total: 147 passed
- live Ollama calls: 0
- R2/R3/R4 executed: no

## Runtime trace
- path: docs/bench/n30r/w1_capability_projection_trace_w1c_001.json
- deterministic mock provider used
- live Ollama calls: 0

## Remaining gaps (for W2)
- source visible to Planner: NO
- codeintel: NO
- target symbol: in request but not in planner
- locked_search: not established
- real evidence refs: NO (placeholder)
- evidence reaches prompt: NO

## Next gate
N30R-W2 Planner/Executor Source Evidence and Locked Search Contract Repair

## Claim boundary
- Nexus effectiveness not measured
- Prompt evidence not yet repaired
- 7B capacity not measured
- R2/R3/R4 not allowed
- production_ready=false
- public_claim_allowed=false
