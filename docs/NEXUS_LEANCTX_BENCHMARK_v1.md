# 🛡️ Nexus 實測報告：Lean-Ctx 上線優化與實作深度分析

## 1. 📊 安裝前後真實數值對比 (Real-World Benchmark)

| 指標 (Metric) | 安裝前 (Legacy) | 安裝後 (Nexus Optimized) | 淨優化 (Net Gain) |
| :--- | :--- | :--- | :--- |
| **Token 消耗 (Scan 模式)** | ~8,441 tokens | **114 tokens** | **節省 98.6%** 🚀 |
| **Token 消耗 (Read 模式)** | ~8,441 tokens | **8,010 tokens** | **節省 5.11%** |
| **處理延遲 (Latency)** | 0.00s | **0.25s** | +0.25s |
| **重複讀取成本** | ~8,441 tokens | **13 tokens** | **節省 99.8%** 🚀 |

## 2. 🛠️ 實作細節

### A. 階層式讀取策略
- **Signatures (-m signatures)**: 專案掃描與 API 定位用。
- **Aggressive (-m aggressive)**: 邏輯審核用。
- **Full (Default)**: Bug 修復與數學對齊用。

### B. 回退機制 (Resilience)
- 自動偵測 Binary 路徑。
- 遺失時自動回退 Legacy 模式，保證任務不中斷。

## 3. ⚠️ 協同優化建議
- **禁令**：涉及數值門檻與 RCA 時，嚴禁僅使用 Signatures 模式。
- **工作流**：推薦「先簽名定範圍，再全文定計劃」的兩階段流程。
- **Cache 提醒**：注意 300s 緩存失效風險。

## 4. 🏁 最終上線判定
**狀態：[GO]** (已達成 P5 實作目標)
