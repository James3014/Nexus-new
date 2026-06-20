# MicroVerifier Task-Scoped Interpreter Packet — Phase 2

## Summary

Replaced generic interpreter assumptions with task-scoped verification context via env_taxonomy.

## Key Changes

1. **env_taxonomy parameter**: `verify()` now accepts `env_taxonomy` dict as authoritative source for task-scoped interpreter
2. **task_scoped field**: `MicroVerifyResult.task_scoped` records whether env_taxonomy was used
3. **MICRO_VERIFY_CONTEXT_MISSING**: New error when no interpreter + no taxonomy + no allow_bare_python
4. **Fail closed**: No silent fallback to generic python3

## Classification Logic

| Condition | Result | error_message |
|-----------|--------|---------------|
| env_taxonomy has interpreter/verifier_command | PASS, task_scoped=True | — |
| No taxonomy, no interpreter, allow_bare_python=False | FAIL | MICRO_VERIFY_CONTEXT_MISSING |
| No taxonomy, interpreter="python3", allow_bare_python=False | FAIL | ENV_BLOCKED |
| No taxonomy, interpreter=custom, allow_bare_python=True | PASS, task_scoped=False | — |

## Files Modified

- `nexus/services/local_heal/micro_verifier.py`
- `tests/unit/local_heal/test_micro_verifier.py`

## Test Results

- `test_micro_verifier.py`: 9 passed
