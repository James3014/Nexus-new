# P6-C Report: p3_cheap_verifier and p3_retry_stub runtime real path

- **status**: P6_C_STATUS_PASS
- **date**: 2026-07-10

## Files changed

- `nexus/services/local_heal/p3_local_cheap_verifier_runtime.py` — refactored to `_compute_p3_cheap_verifier_runtime`; added `RealLocalCheapVerifier` class
- `nexus/services/local_heal/p3_local_retry_stub_runtime.py` — refactored to `_compute_p3_retry_stub_runtime`; added `RealLocalRetry` class
- `tests/services/local_heal/test_p3_cheap_verifier_runtime.py` — added 3 new tests
- `tests/services/local_heal/test_p3_retry_stub_runtime.py` — added 3 new tests

## Commands run

```bash
python3 -m py_compile nexus/services/local_heal/p3_local_cheap_verifier_runtime.py nexus/services/local_heal/p3_local_retry_stub_runtime.py
# COMPILE OK

python3 -m pytest tests/services/local_heal/test_p3_cheap_verifier_runtime.py tests/services/local_heal/test_p3_retry_stub_runtime.py -v
# 12 passed in 0.17s
```

## Test count

- P1-C existing tests: 3 + 3 = 6 (all pass)
- P6-C new tests: 3 + 3 = 6 (all pass)
- **Total: 12 passed**

## Governance boundary

- `NEXUS_OLLAMA_ENABLED=1` flag enables real path for both
- Cheap verifier model: ornith:9b
- Retry cascade: qwen2.5-coder:7b → deepseek-coder:6.7b → ornith:9b
- When flag not set: calls `_compute_*` internal (same behavior as P1-C)
