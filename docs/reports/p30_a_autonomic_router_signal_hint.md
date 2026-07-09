# P30-A Report — AutonomicRouter Signal Hint

- **status**: P30_A_STATUS_PASS
- **files changed**:
  - `nexus/engine/autonomic_router.py`
    - Added `mode_hint: str = ""` field to `ExecutionPlan` dataclass
    - Added telemetry writes: `state.metadata["est_tokens"]` and `state.metadata["autonomic_reason"]`
    - Set `mode_hint=mode` on returned `ExecutionPlan`
  - `tests/engine/test_autonomic_router_signal_only.py` (new, 7 tests)
- **commands run output**:
  - `python3 -m py_compile nexus/engine/autonomic_router.py` — 0 errors
  - `python3 -m pytest tests/engine/test_autonomic_router_signal_only.py -v` — 7 passed
  - `python3 -m pytest tests/engine/test_v4_routing_hardening_mvp.py -v` — 7 passed (regression)
  - `python3 -m pytest tests/engine/test_autonomic_routing_service.py -v` — 3 passed (regression)
- **test count**: 7
- **explicit non-goals**: AutonomicRouter NOT deleted; Service wrapper NOT changed; Capabilities NOT migrated
- **governance boundary**: 3 violation writes never existed in current codebase (already clean); 2 telemetry writes added (`est_tokens`, `autonomic_reason`); `mode_hint` signal field added to `ExecutionPlan`
