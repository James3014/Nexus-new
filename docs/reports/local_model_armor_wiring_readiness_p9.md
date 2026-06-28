# Local Model Armor Wiring Readiness Report (P9)

## 1. Executive Verdict

**Verdict: READY FOR STAGE 1 INTEGRATION GATES (NOT PROMOTED)**

Path B (`LocalHealCapabilityAdapter`) has been safely wired into Path A (`capability_ab_runner.py`) behind strict environment-gated seams. All safety locks remain engaged, behavior is unchanged by default, and diagnostic paths (Path D) are isolated.

---

## 2. Four-Path Status

| Path | Description | Status | Verification Reference |
| :--- | :--- | :--- | :--- |
| **Path A** | Mainline capability runner | **Active / Route Truth** | `scripts/bench/capability_ab_runner.py` |
| **Path B** | Local heal capability adapter | **Wired / Gated Seam** | `nexus/services/local_heal/capability_adapter.py` |
| **Path C** | Gated isolated solve loop | **Wired / Gated Seam** | `nexus/services/local_heal/isolated_local_solve_loop.py` |
| **Path D** | Diagnostic-only sandbox scripts | **Isolated / Diagnostic Only** | `docs/reports/local_model_armor_path_freeze_p0.md` |

---

## 3. P0-P9 Completion Table

| Phase | Title | Status | Evidence |
| :--- | :--- | :--- | :--- |
| **P0** | Diagnostic Freeze | **Complete** | [local_model_armor_path_freeze_p0.md](file:///Users/jameschen/Workspace/nexus/docs/reports/local_model_armor_path_freeze_p0.md) |
| **P1** | Four-Path Audit | **Complete** | [local_model_armor_four_path_audit_p1.md](file:///Users/jameschen/Workspace/nexus/docs/reports/local_model_armor_four_path_audit_p1.md) |
| **P2** | Security Contract Tests | **Complete** | [test_hybrid_route_contract.py](file:///Users/jameschen/Workspace/nexus/tests/contracts/test_hybrid_route_contract.py) |
| **P3** | Runner Row Mapping Specification | **Complete** | [local_model_adapter_runner_row_mapping_p3.md](file:///Users/jameschen/Workspace/nexus/docs/reports/local_model_adapter_runner_row_mapping_p3.md) |
| **P4** | Runner Wiring & Integration Seam | **Complete** | [capability_ab_runner.py](file:///Users/jameschen/Workspace/nexus/scripts/bench/capability_ab_runner.py) |
| **P5** | Guarded Smoke Testing | **Complete** | [test_local_model_ollama_smoke_contract.py](file:///Users/jameschen/Workspace/nexus/tests/integration/test_local_model_ollama_smoke_contract.py) |
| **P6** | Candidate Mode Dry-Run | **Complete** | [test_candidate_isolation_gate.py](file:///Users/jameschen/Workspace/nexus/tests/unit/local_heal/test_candidate_isolation_gate.py) |
| **P7** | Isolated Solve Path Validation | **Complete** | [test_isolated_local_solve_loop_seam.py](file:///Users/jameschen/Workspace/nexus/tests/integration/test_isolated_local_solve_loop_seam.py) |
| **P8** | Evidence Bundle Summary | **Complete** | [test_capability_ab_runner.py](file:///Users/jameschen/Workspace/nexus/tests/benchmark/test_capability_ab_runner.py) |
| **P9** | Wiring Readiness Report | **Complete** | This Report (`docs/reports/local_model_armor_wiring_readiness_p9.md`) |

---

## 4. Evidence Files and Commands

### Active Integration Files
- Runner: [capability_ab_runner.py](file:///Users/jameschen/Workspace/nexus/scripts/bench/capability_ab_runner.py)
- Solve Loop: [isolated_local_solve_loop.py](file:///Users/jameschen/Workspace/nexus/nexus/services/local_heal/isolated_local_solve_loop.py)

### Verification Commands
```bash
# Verify Mainline Seams and Evidence Bundle Summary
uv run pytest tests/benchmark/test_capability_ab_runner.py -k "local_model_adapter or hybrid_route or local_guard or evidence_bundle" -q -rs

# Verify Security Contract Validation Integrity
uv run pytest tests/contracts/test_hybrid_route_contract.py -q -rs

# Verify Isolated Solve and Path Traversal Safety Checks
uv run pytest tests/integration/test_abc_local_heal_full_isolated_solve_seam.py tests/integration/test_isolated_local_solve_loop_seam.py tests/unit/local_heal/test_isolated_local_solve_loop.py tests/unit/local_heal/test_local_guard_fail_closed.py -q -rs
```

---

## 5. Safety Invariant Table

| Invariant Requirement | Enforcement Mechanism | Status |
| :--- | :--- | :--- |
| **Path A remains Route Truth** | `adapter_output_is_route_truth` is forced to `False`. | **Enforced** |
| **Gated Seam Only** | Checked via `os.environ.get("NEXUS_WITH_LOCAL_MODEL_ADAPTER") == "1"`. | **Enforced** |
| **No Production Unlocks** | `production_ready` is hardcoded to `False` in runner mappings. | **Enforced** |
| **No Public Claim Unlocks** | `public_claim_allowed` is hardcoded to `False` in runner mappings. | **Enforced** |
| **No Behavior Mutation** | `behavior_changed` remains `False` for local model executions. | **Enforced** |
| **Path Traversal Protection** | `isolated_local_solve_loop` enforces checks on un-normalized paths. | **Enforced** |

---

## 6. Adapter Invocation Status

- **Default State**: Disabled. If `NEXUS_WITH_LOCAL_MODEL_ADAPTER` environment variable is not present or not set to `1`, the adapter block is bypassed entirely, recording a standard disabled row.
- **Seam State**: Gated. When env variable is active, `LocalHealCapabilityAdapter.run()` is called using task details, passing `dry_run=True` to prevent any side effects on the workspace.

---

## 7. Evidence Bundle Summary Status

- Integrated into `write_evidence_bundle()`.
- Produces a distinct `local_model_adapter_summary` property inside the generated `evidence_bundle.json` containing isolated counters:
  - `adapter_trace_count`
  - `adapter_invoked_count`
  - `local_model_called_count`
  - `candidate_isolated_count`
  - `hash_match_count`
  - `verifier_pass_count`
  - `fail_closed_count`
  - `behavior_changed_count` (expected 0 under current gates)
  - `public_claim_allowed_count` (expected 0 under current gates)
  - `production_ready_count` (expected 0 under current gates)

---

## 8. Residual Blockers

No P0-P9 wiring blocker remains for the gated local model adapter seam.

This does not imply production readiness, public claim readiness, or verified Qwen capability lift. The current result only confirms that the adapter is wired into the runner behind fail-closed gates and that the scoped verification commands reported green.

---

## 9. Not Allowed Claims

- **NO** Qwen model capability claims may be published based on this wiring alone.
- **NO** production execution is unlocked.
- **NO** mainline benchmark claims can leverage Path D scripts.

---

## 10. Next Promotion Plan Required

Before unlocking any public claim or allowing local execution to set route truth (i.e. setting `production_ready=True` or `public_claim_allowed=True`), a separate **Phase 2 Promotion and Evaluation Specification** must be written, detailing model benchmarks, A/B lift evidence, and approval by governance.
