# Nexus Local Model Armor Issues Report

**Date**: 2026-06-29

---

## 已修復的 Issues

| Issue | 狀態 |
|---|---|
| dry_run 參數未使用 | ✅ Fixed |
| Runner 缺少 env vars | ✅ Fixed |
| Runner controls 缺少 keys | ✅ Fixed |
| Exception 吞噬 | ✅ Fixed |
| Adapter output 未驗證 safety locks | ✅ Fixed |
| Runner 預設 enable_local_heal=True | ✅ Fixed |

---

## 核心架構問題

### 三條管線互不相連

```
路徑 A: HealPipeline → CommitteeOrchestrator → 5-Phase (6月優化)
         ❌ 沒被 _finalize_with_nexus_row 呼叫

路徑 B: LocalModelExecutor → IsolatedLocalSolveLoop (N1/N3 seam)
         ⚠️ 從 env var 讀 topology，不從 planner 讀

路徑 C: _finalize_with_nexus_row (benchmark 入口)
         → 只接路徑 B
```

### LocalModelExecutor 的 execution_topology 是 dead metadata

```python
# local_model_executor.py:55
execution_topology = os.environ.get(...) or "single_local_model"
# 讀了但從不分支
```

### 路徑 A 的優化沒被接

| 模組 | 功能 | 被 mainline 呼叫？ |
|---|---|---|
| SolidSearchReplaceProtocol | SEARCH/REPLACE 格式 | ❌ |
| GranularMethodLocalizer | 精確定位 | ❌ |
| Semantic Retry | verifier feedback 重構 prompt | ❌ |
| Failure Feedback Builder | 建立 retry prompt | ❌ |
| CommitteeOrchestrator | 多模型候選 + Judge 選優 | ❌ |

---

## 修正方案

**不建新路由，只接現有的 CapabilityPlanner。**

1. Executor 從 planner 的 signal_snapshot 讀 topology
2. Executor 根據 topology 分支到既有的 committee 模組
3. 不建新 enum、不建新 adapter、不改 CapabilityPlanner

---

## 測試狀態

```
tests/unit/local_heal/test_capability_adapter.py → 11/11 ✅
tests/integration/test_abc_local_heal_full_isolated_solve_seam.py → 2/2 ✅
tests/contracts/test_hybrid_route_contract.py → 17/17 ✅
tests/benchmark/test_capability_ab_runner.py -k "local_model_adapter" → 12/12 ✅
Total: 122 adapter-related tests passing ✅
```
