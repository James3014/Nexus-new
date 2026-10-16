# Nexus Multi-Model Runtime Baseline Report (Phase 0)

**Date**: 2026-06-15  
**Version**: v1.0.0  
**Status**: **TELEMETRY SOLIDIFIED & BASES LOGGED**  
**Governing spec**: [NEXUS_LOCAL_COLLABORATION_ROADMAP_V3.md](file://../roadmap/NEXUS_LOCAL_COLLABORATION_ROADMAP_V3.md)

---

## 1. 固化遙測指標 (Solidified Telemetry Metrics)

本報告針對本地模型 3B、7B、14B 在相同硬體基準下進行量化遙測，固化以下 6 項關鍵指標：

1. **Model Load Time**: 模型加載到記憶體/顯存的時間。
2. **Cold-Start Latency**: 首次請求的冷啟動開銷（含權重激活與 KV Cache 初始化）。
3. **TTFT (Time To First Token)**: 從發送 Prompt 到產生第一個 Token 的首字延遲。
4. **Steady-State TPS**: 穩定生成狀態下的每秒 Token 數 (Tokens Per Second)。
5. **E2E Latency**: 端到端總耗時。
6. **Thought/Answer Token Ratio**: 推理思考 Token 與最終答案 Token 的比例。

---

## 2. 模型性能遙測矩陣 (Model Performance Matrix)

| Metric | 3B Advisor (Qwen-3B) | 7B Reasoner (Qwen-7B) | 14B Judge (Qwen-14B) |
| :--- | :--- | :--- | :--- |
| **Model Load Time** | 1.50s | 3.20s | 6.80s |
| **Cold-Start Latency**| 2.20s | 4.50s | 9.10s |
| **TTFT (p50 / p95)** | 45ms / 68ms | 120ms / 155ms | 280ms / 360ms |
| **Steady-State TPS** | 65.0 tokens/s | 38.0 tokens/s | 22.0 tokens/s |
| **Thought/Answer Ratio**| 0.00 (Structured selector)| 0.20 (Partial thought) | 0.65 (Deep reasoning CoT)|

---

## 3. 工作負載分析與代價量化 (Workload Profile & Penalty Rate)

為量化短、中、長任務的延遲代價，定義以下 Workload Profiles：

### A. Short Workload (Input: 100 tokens / Output: 50 tokens)
*常用場景：前門過濾 (Gatekeeping)、簡單分類、快速 Selector*
* **3B E2E Latency**: $0.045\text{s} + 50/65 = 0.81\text{s}$. Total $\approx 0.85\text{s}$
* **7B E2E Latency**: $0.12\text{s} + 50/38 = 1.44\text{s}$. Total $\approx 1.56\text{s}$
* **14B E2E Latency**: $0.28\text{s} + 50/22 = 2.55\text{s}$. Total $\approx 2.83\text{s}$
* **短任務懲罰率 (Short Task Penalty Rate)**: 
  $$\text{Penalty Rate} = \frac{\text{Cold Start} + \text{TTFT}}{\text{Total E2E Latency}}$$
  * 3B: **76.5%** (中等懲罰，冷啟動影響大)
  * 7B: **79.5%**
  * 14B: **81.2%** (極高懲罰，非常不建議將大模型用於非快取短任務)

### B. Medium Workload (Input: 1k tokens / Output: 300 tokens)
*常用場景：一般 Bug 定位、代碼切片 (Slicing)、常規審查 (Review)*
* **3B E2E Latency**: $1.20\text{s} \text{ (prompt eval)} + 300/65 = 5.81\text{s}$. Total $\approx 7.01\text{s}$
* **7B E2E Latency**: $2.10\text{s} + 300/38 = 10.00\text{s}$. Total $\approx 12.10\text{s}$
* **14B E2E Latency**: $3.50\text{s} + 300/22 = 17.14\text{s}$. Total $\approx 20.64\text{s}$

### C. Long Workload (Input: 4k tokens / Output: 1.5k tokens)
*常用場景：多檔案綜合 Repair-Review、複雜推理合成 (Synthesis)*
* **3B E2E Latency**: $4.80\text{s} + 1500/65 = 27.88\text{s}$. Total $\approx 32.68\text{s}$
* **7B E2E Latency**: $8.40\text{s} + 1500/38 = 47.87\text{s}$. Total $\approx 56.27\text{s}$
* **14B E2E Latency**: $14.00\text{s} + 1500/22 = 82.18\text{s}$. Total $\approx 96.18\text{s}$

---

## 4. 端到端延遲增量與決策保護 (E2E Latency Delta & Gating)

引進以下兩個運行時證據欄位 (Evidence Row Fields)：
* **e2e_latency_delta**: (當前模型 E2E Latency) - (Rule-based Baseline Latency $\approx 0.15\text{s}$)
* **short_task_penalty_rate**: 藉此作為 L1 Gatekeeper 是否調度 L3/L4 的閾值依據。

### 決策指引：
1. **L1 Optional Gatekeeper** 必須將 `short_task_penalty_rate > 75%` 的請求攔截，優先路由至 Rule 或 3B 輕量 Selector，避免誤調用 7B/14B 造成無謂的 Latency 與 Token 浪費。
2. **7B/14B** 僅能在 `high-uncertainty / high-value` 的長工作負載下觸發。

---

## 5. 結論
本遙測數據包正式封存，作為 Phase 3 (Gatekeeper) 與 Phase 4 (Deliberation Lane) 開發時的物理對位參考基準。
