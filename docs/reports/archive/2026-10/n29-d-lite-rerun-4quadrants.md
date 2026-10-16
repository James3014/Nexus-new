# N29-D Closeout: Lite 重跑 N28 12 題 4 象限 (48 run)

**Status**: PASS

## 4 象限解題率對比 (N28 vs N29 Lite)

| 象限 | N28 (7 階段) | N29 (Lite) | 增減 |
|------|-------------|------------|------|
| with_nexus | 4/12 (33%) | 2/12 (17%) | -2 題 |
| bare | 5/12 (42%) | 3/12 (25%) | -2 題 |
| local_only_executed | 5/12 (42%) | 4/12 (33%) | -1 題 |
| cloud_exhausted | 4/12 (33%) | 6/12 (50%) | +2 題 |
| **Total** | **18/48 (37.5%)** | **15/48 (31.25%)** | **-3 題** |

## 結論

- N29 Lite (15/48) < N28 (18/48): Lite 對弱模型 (7B) 在多數象限解題率下降
- cloud_exhausted 象限 N29 > N28: Lite 在 quota 用盡場景略有優勢
- 結論: Lite 對弱模型效果 mixed, 不應全面替換 7 階段

## Lite auto trigger 驗證

所有 48 run 均帶 `model_size=7_000_000_000`, `lite_auto_trigger=auto_lite_weak_model_size_lt_8B`, 確認第 6 種觸發已生效.

## Forbidden claims
- 不可聲稱 production_ready
- 不可聲稱 public_claim_allowed
- 不可聲稱 "Nexus 比較好"
