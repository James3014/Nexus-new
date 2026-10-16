# P6-D Report: 4 stage orchestrator

- **status**: P6_D_STATUS_PASS
- **date**: 2026-07-10

## Files created

- `nexus/services/local_heal/four_stage_orchestrator.py` — `FourStageOrchestrator` + `FourStageReceipt` (frozen dataclass)
- `tests/services/local_heal/test_four_stage_orchestrator.py` — 8 tests covering all 3 paths

## Commands run

```bash
python3 -m py_compile nexus/services/local_heal/four_stage_orchestrator.py
# COMPILE OK

python3 -m pytest tests/services/local_heal/test_four_stage_orchestrator.py -v
# 8 passed in 0.16s
```

## Test count

- 8 new tests passing

## Governance boundary

- Orchestrator does not call real cloud or Ollama (uses mocked sub-components)
- All 4 sub-component classes are instantiated with env-flag guards internally

## 4-stage sequence

1. Stage 1: `RealLocalDiagnosis.compute_p3_local_diagnosis_runtime()` — local 3B diagnosis
2. Stage 2: `RealCloudExecutor.run_with_compact_prompt()` — cloud candidate with ≤500 chars
3. Stage 3: `RealLocalCheapVerifier.compute_p3_cheap_verifier_runtime()` — 9B verifier
4. Stage 4 (if stage 3 fails): `RealLocalRetry.compute_p3_retry_stub_runtime()` — 7B→6.7B→9B cascade
