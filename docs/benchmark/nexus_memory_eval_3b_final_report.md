# Nexus MEMORY-EVAL-3B Fresh Evidence Package — Final Report

**Date**: 2026-06-21
**Status**: COMPLETE
**Decision**: MEMORY_EVAL_3B_RUNTIME_MEMORY_OFF_READY
**Commit**: `0c001e86`

---

## Changes

| File | Change |
|------|--------|
| `context.py` | Added `memory_arm` and `artifact_output_root` |
| `orchestrator.py` | Fixed arm detection, configurable output root |
| `test_eval_substrate_live_runtime_wiring.py` | Updated to use tmp_path isolation |
| `test_memory_eval_3_runtime_memory_off.py` | Fresh output root tests |

---

## Runtime Path Proven

```
HealOrchestrator.run(ctx)
  -> ctx.op.memory_arm = "nexus_memory_off"
  -> ctx.op.artifact_output_root = <fresh path>
  -> _finalize_run()
  -> _attach_live_full_loop_artifacts()
  -> LiveArtifactCollector(output_dir=output_root)
  -> 11 runtime artifacts (artifact_source=live_runtime)
```

---

## Test Results

| Test | Result |
|------|--------|
| eval_substrate (5 tests) | **5/5 PASS** |
| memory-off (2 tests) | **2/2 PASS** |
| **Total** | **7/7 PASS** |

---

## Validation

| Check | Status |
|-------|--------|
| 11/11 artifacts | YES |
| artifact_source=live_runtime | YES |
| created_during_run=true | YES |
| memory_section_included=false (memory_off) | YES |
| arm_result.arm=nexus_memory_off | YES |
| No eval_substrate pollution | YES |

---

## Flag Confirmations

| Flag | Value |
|------|-------|
| public_claim_allowed | false |
| production_ready | false |
| training_export_allowed | false |
| internal_only | true |
