# N29-C Closeout: TDD 4 RED tests

**Status**: PASS (RED confirmed)

## Summary

4 個 RED test 寫完, N29-B 還沒改 code, 4 個 test 全部 FAIL (符合 TDD 紅燈預期).

## Test Results

```
tests/integration/test_n29_weak_model_auto_lite.py::test_weak_model_7b_auto_lite FAILED
tests/integration/test_n29_weak_model_auto_lite.py::test_strong_model_14b_keeps_heavy_route FAILED
tests/integration/test_n29_weak_model_auto_lite.py::test_7b_with_low_risk_still_lite FAILED
tests/integration/test_n29_weak_model_auto_lite.py::test_14b_with_low_risk_still_lite FAILED

4 failed — TypeError: should_use_lite_route() got an unexpected keyword argument 'model_size'
```

## Forbidden claims
- 不可聲稱 production_ready
- 不可聲稱 public_claim_allowed
