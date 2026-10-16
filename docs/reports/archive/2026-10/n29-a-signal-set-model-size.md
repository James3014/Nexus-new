# N29-A Closeout: signal_set 加 model_size 欄位

**Status**: PASS

## Summary

`CapabilitySignalSet` 新增 `model_size: Optional[int] = None` 欄位, 不破既有 caller (frozen dataclass, 新欄位有 default).

## Changes

- `nexus/core/capability_signal_set.py`: 加 `model_size` 欄位 + `from_context` 解析
- `tests/core/test_capability_signal_set.py`: 加 2 個 test

## Verification

```
tests/core/test_capability_signal_set.py::test_signal_set_model_size_field_optional PASSED
tests/core/test_capability_signal_set.py::test_signal_set_model_size_can_be_set PASSED
既 有 4 個 test 全數 PASS (不退步)
```

## Forbidden claims
- 不可聲稱 production_ready
- 不可聲稱 public_claim_allowed
