# N29-B Closeout: Lite route 加第 6 種自動觸發

**Status**: PASS

## Summary

`should_use_lite_route` 新增 `model_size` 參數 + 第 6 種自動觸發 (`model_size < 8B`). 既有 5 種觸發邏輯未改.

## Changes

- `nexus/core/lite_route_oracle.py`: 函式 signature 加 `model_size` + 第 6 種觸發 (5 行)
- `tests/test_lite_route_oracle.py`: 加 6 個新 test

## Trigger 6 Logic

```python
# 6. Weak model auto lite: model_size < 8B
if model_size is not None and model_size < 8_000_000_000:
    return LiteRouteDecision(is_lite=True, reason="auto_lite_weak_model_size_lt_8B", ...)
```

## Test Results

```
tests/test_lite_route_oracle.py: 19 passed (13 existing + 6 new)
tests/integration/test_n29_weak_model_auto_lite.py: 4 passed (N29-C RED → GREEN)
tests/core/: 228 passed (不退步)
```

## Forbidden claims
- 不可聲稱 production_ready
- 不可聲稱 public_claim_allowed
