# Local Model Sprint C1: Single Source Phase Telemetry Contract

**Status:** LOCAL_MODEL_SPRINT_C1_PHASE_TELEMETRY_CONTRACT_PASS
**Date:** 2026-07-01

## Files Changed

| File | Change |
|------|--------|
| `nexus/services/local_heal/local_model_capability_executors.py` | Phase progression extracted from pipeline result context |

## Commands Run

```bash
uv run pytest tests/unit/local_heal/test_localheal_pipeline_seam_truth.py tests/unit/local_heal/test_local_model_executor.py tests/unit/local_heal/test_downstream_enforcement_gates.py -q
# 64 passed
```

## Root Cause Found (C1 verification)

**`OllamaLocalModelProvider` requires `NEXUS_LOCAL_MODEL_CALL_ALLOWED=1` and `NEXUS_LOCAL_MODEL_PROVIDER=ollama` env vars.**

When these are missing, `OllamaLocalModelProvider.generate()` returns `provider_not_configured`. The pipeline's provider wrapper returns empty string. The orchestrator classifies this as `EMPTY_RESPONSE`.

But the M1 benchmark doesn't set these env vars, so the pipeline's internal provider path fails.

## Phase Telemetry Fields

| Field | Source |
|-------|--------|
| `phase_reached` | Last completed phase based on context fields |
| `phases_completed` | List of all completed phases |
| `phase_failed` | Phase that failed (if any) |
| `phase_failure_reason` | Failure reason from context |
| `reproduction_reached` | `repro_evidence` set or `skip_reproduction=True` |
| `planning_reached` | `plan` has `search_symbols` |
| `localization_reached` | `localized_files` non-empty |
| `patch_synthesis_reached` | `final_patch` non-empty |
| `verification_reached` | `evaluation_report` non-empty |

## Explicit Statements

- No parser/protocol/verifier/candidate isolation changes.
- B8 not run.
- Solved rate not claimed.
- Phase telemetry now comes from pipeline result context, not inference.
- Pipeline fails with `provider_not_configured` because env vars are not set.
