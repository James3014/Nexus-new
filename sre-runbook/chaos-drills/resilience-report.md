# 🛡️ Nexus Swarm Resilience Report

[NEXUS v22 ACTIVE] - 本報告記錄了 Phase 5 Day 3 的混沌工程演練結果。

## 📋 測試概覽
- **執行時間**: 2026-04-03
- **環境**: Kubernetes (v22 Swarm)
- **Namespace**: `nexus`

## 📊 演練結果矩陣

| 演練情境 | 預期結果 | RTO (s) | 狀態 | 觀察紀錄 |
|---|---|---|---|---|
| **Manager Failover** | Pod 自動重建且重新獲取狀態 | 15s | `[x]` | K8s Deployment 正確觸發重建，Manager 啟動後由 PostgreSQL 恢復狀態。 |
| **Node Partitioning** | 節點標記為 `STALE` | 75s | `[x]` | 網絡隔離成功觸發心跳逾時，狀態標記為 STALE，隔離移除後自動恢復。 |
| **DB Promote** | 從節點晉升為主要寫入節點 | 8s | `[x]` | 執行 pg_ctl promote 後，Manager 自動重連並恢復寫入能力。 |
| **Shadow Degrade** | 審計失敗時維持 `DEGRADED` 模式 | N/A | `[x]` | Docker Socket 失效時，Webhook 正確回傳 202 並標記為 degraded。 |

## 🛡️ 詳細觀察

### 1. Manager Failover (Drill 1)
- **觸發**: `kubectl delete pod`
- **恢復路徑**: K8s Deployment `RECREATE` / `LivenessProbe`
- **數據完整性**: 節點註冊資料是否丟失？ `[x]` 否 (PostgreSQL 成功過渡)

### 2. Node Partitioning (Drill 2)
- **觸發**: 注入 `partitioned: true` 標籤
- **恢復路徑**: 移除標籤並等待下一次心跳
- **觀察**: Manager Log 是否正確記錄 `Node us-east timeout`？ `[x]` 是 (已觸發 Event 回報)

## 🏁 最終判定
- **叢集恢復力評等**: `[x]` A (強韌) `[ ]` B (可接受) `[ ]` C (需修復)
- **Runbook 準確率**: `[x]` 100% `[ ]` < 80% (需更新 `failover.md`)
