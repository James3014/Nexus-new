# 🛡️ PHASE 5: Canary Execution Plan

## 1. 計劃定位 (Rationale)
Phase 5 旨在驗證 Phase 4 硬化成果（Syntax Preflight, Refusal Recovery, 7B/14B Split）在實戰場景下的穩定性與效益。本計畫採「受控小流量」模式，確保優化行為不污染 production 審計邊界。

## 2. 核心變更與觀測項目 (Key Metrics)
每一筆 Canary 執行必須產出包含以下欄位的 `nexus.localheal.canaryreceipt.v1`：

| 欄位名稱 | 說明 |
|---|---|
| `expected_stop_layer` | 預期的治理出口層級 |
| `observed_stop_layer` | 實際的物理退出層級 |
| `stop_layer_matched` | 治理一致性布林值 |
| `failure_class` | 歸一化錯誤桶（Taxonomy） |
| `syntax_gate_passed` | `ast.parse` 預檢結果 |
| `refusal_detected` | 模型拒答/道歉偵測 |
| `wall_time_sec` | 量化牆鐘時間 |
| `retry_count` | 迭代重試次數 |

## 3. 分桶優化路徑 (Bucket Convergence)
根據 Canary 數據，我們將對以下「高頻失敗桶」進行定向優化：
- **SYNTAX_INVALID**: 強化提示詞契約與更正引導文案。
- **SEARCH_MISMATCH**: 升級 HUD Canonical Snippet 回填策略。
- **REFUSAL/EMPTY**: 實裝 `aider-strict-v1` 提示詞分流。

## 4. 治理邊界
- **Promotion Effect**: **NONE**.
- **Public Claim**: **NOT ALLOWED**.
- **Visibility**: **INTERNAL AUDIT ONLY**.

---
**NEXUS IDENTITY: 384c6fd02 + v2.9 RUNTIME-ALIGNED**
