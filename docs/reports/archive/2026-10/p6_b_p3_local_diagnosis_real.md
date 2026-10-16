# P6-B Report: p3_local_diagnosis_runtime real path

- **status**: P6_B_STATUS_PASS
- **date**: 2026-07-10

## Files changed

- `nexus/services/local_heal/p3_local_diagnosis_runtime.py` — refactored to `_compute_p3_local_diagnosis_runtime` internal; added `RealLocalDiagnosis` class with `NEXUS_OLLAMA_ENABLED` env-flag
- `tests/services/local_heal/test_p3_local_diagnosis_runtime.py` — added 5 new tests under `TestRealLocalDiagnosis`

## Commands run

```bash
python3 -m py_compile nexus/services/local_heal/p3_local_diagnosis_runtime.py
# COMPILE OK

python3 -m pytest tests/services/local_heal/test_p3_local_diagnosis_runtime.py -v
# 10 passed in 0.15s
```

## Test count

- P1-B existing tests: 5 (all pass)
- P6-B new tests: 5 (all pass)
- **Total: 10 passed**

## Explicit non-goals

- Real Ollama not called (uses InertLocalModelProvider)
- Backward compatible with P1-B: all 5 existing tests pass

## Governance boundary

- `NEXUS_OLLAMA_ENABLED=1` flag enables real path
- Model: qwen2.5-s2t-advisor:3b via OllamaLocalModelProvider
- When flag not set: calls `_compute_p3_local_diagnosis_runtime` internal (same behavior as P1-B)
