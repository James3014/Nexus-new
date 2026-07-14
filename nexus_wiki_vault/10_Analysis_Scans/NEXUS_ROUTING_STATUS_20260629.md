# Nexus Routing Status — 2026-06-29

**一句話**：三條管線互不相連，但修正方案很簡單 — 不建新路由，只讓 LocalModelExecutor 從 CapabilityPlanner 讀 topology。

---

## 現狀：三條管線

```
路徑 A: HealPipeline → CommitteeOrchestrator → 5-Phase (6月優化，有成功解題)
         ❌ 沒被 _finalize_with_nexus_row 呼叫

路徑 B: LocalModelExecutor → IsolatedLocalSolveLoop (N1/N3 seam)
         ⚠️ 從 env var 讀 topology，不從 planner 讀

路徑 C: _finalize_with_nexus_row (benchmark 入口)
         → 只接路徑 B
```

### 6 月成功解題紀錄（路徑 A）

```
d6d01c3ed 8/8 SUCCESS benchmark with 7B+14B dynamic routing
4097bdeaf Task 01 astropy_14526 PASS
01d6a0f14 Task 02 sympy_polys_01 PASS
f1fc65da9 Task 03 nexus_verifier_http_01 PASS
7652f2b3a Task 04 nexus_protocol_boundary_01 PASS
```

走的是 `HealPipeline → CommitteeOrchestrator → 5-Phase → SEARCH/REPLACE`，不是 `LocalModelExecutor`。

### 路徑 A 的優化模組（存在但沒被接）

| 模組 | 功能 | 被 mainline 呼叫？ |
|---|---|---|
| SolidSearchReplaceProtocol | SEARCH/REPLACE 格式 | ❌ |
| GranularMethodLocalizer | 精確定位 | ❌ |
| Semantic Retry | verifier feedback 重構 prompt | ❌ |
| Failure Feedback Builder | 建立 retry prompt | ❌ |
| CommitteeOrchestrator | 多模型候選 + Judge 選優 | ❌ |

---

## 修正方案：不建新路由，接現有的

```
CapabilityPlanner 已經有：
  - local_model_executor 能力 (line 634)
  - execution_topology metadata (line 883-890)
  - committee_profile metadata (line 887)

問題：
  LocalModelExecutor 從 env var 讀 topology，不從 planner 讀

修正：
  Executor 從 planner 的 signal_snapshot 讀 topology
```

### 具體改動

| Step | 改動 | 檔案 |
|---|---|---|
| 1 | Executor 從 `request.route_context` 讀 topology | `local_model_executor.py` |
| 2 | `_finalize_with_nexus_row` 已傳 `finalized`（含 signal_snapshot） | `capability_ab_runner.py`（不用改） |
| 3 | Executor 根據 topology 分支到既有的 committee 模組 | `local_model_executor.py` |
| 4 | `local_committee_only` 用既有的 SEARCH/REPLACE + Localization + Semantic Retry | `local_model_executor.py` |

### 改動前後對比

```python
# 改動前（從 env var 讀）
execution_topology = os.environ.get("NEXUS_LOCAL_MODEL_EXECUTOR_TOPOLOGY") or "single_local_model"

# 改動後（從 planner 的 signal_snapshot 讀）
execution_topology = request.route_context.get("execution_topology", "single_local_model")
```

### 不做的事

| 不做 | 原因 |
|---|---|
| 不建 `RouteTopology` enum | topology 已在 signal_snapshot 裡 |
| 不建 `local_committee_only` route mode | 只是 executor 內部分支，不是新路由 |
| 不建新 adapter | 只接既有的 committee 模組 |
| 不改 CapabilityPlanner | planner 已有 topology metadata |

---

## 驗證

```bash
# 確認 planner 已有 topology
rg -n "execution_topology\|local_committee" nexus/engine/capability_planner.py

# 確認 executor 從 route_context 讀 topology
rg -n "route_context.*execution_topology\|route_context.*topology" nexus/services/local_heal/local_model_executor.py

# 確認沒有新路由
rg -n "RouteTopology\|new.*route\|route.*mode.*local_committee" nexus/ scripts/
```

---

## 文件清單

| 文件 | 內容 |
|---|---|
| `NEXUS_LOCAL_MODEL_ARMOR_WIRING_PLAN_v1_1.md` | 原始 wiring plan |
| `NEXUS_LOCAL_MODEL_ARMOR_P_TASKS_v1_1.md` | P-task plan |
| `NEXUS_ROUTING_STATUS_20260629.md` | **本文件**（最新狀態） |

---

## 結論

**不建新路由，只接現有的 CapabilityPlanner。**

CapabilityPlanner 已有 `local_model_executor` 能力和 `execution_topology` metadata。只需要讓 executor 從 planner 讀 topology，然後分支到既有的 committee 模組（SEARCH/REPLACE、Localization、Semantic Retry）。

這樣做保持了單一路由系統，不增加複雜度。
