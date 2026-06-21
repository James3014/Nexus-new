# R6 — Heterogeneous Portfolio Shadow Benchmark

**狀態**: `R6_HETEROGENEOUS_ROUTE_OUTPERFORMS_SINGLE_7B`, `R6_DEEPSEEK_SECOND_PROPOSER_USEFUL`, `R6_3B_JUDGE_USEFUL_AS_ROUTE_GUARD`  
**評估日期**: 2026-06-21  
**任務規模**: 6 大核心任務 (C_12481, C_13453, geo_distance, perm_inverse, matrix_det, core_simplify)  
**路由配置**: 4 大對比路由 (Route A 到 Route D)

---

## 1. 旁路對照實測數據 (Route Comparison Matrix)

以下為各 shadow 路由在 6 大核心任務上的 Verifier 通過率與詳細指標對比：

| 路由 ID / 名稱 | 組合元件與模型 | Verifier 通過率 | 平均延遲 (ms) | 記憶體峰值 (GB) | 3B 裁判狀態 | 判定與結論 |
| :--- | :--- | :---: | :---: | :---: | :---: | :--- |
| **Route A** (single_qwen_7b) | Qwen 7B primary | 66.7% (4/6) | 1790 | 6.5 | N/A | **FAIL** (C_12481, C_13453) |
| **Route B** (dual_proposer) | Qwen 7B + DeepSeek 6.7B | 100% (6/6) | 1830 | 6.8 | N/A | **PASS** (100% 修復率) |
| **Route C** (judge_plus_dual) | **3B Judge + Qwen 7B + DS 6.7B** | **100% (6/6)** | **1880** | **6.8** | **ACTIVE** | **PASS (推薦主線路由候選)** |
| **Route D** (fallback_14b) | Qwen 14B (Gated) | 0% (Blocked) | N/A | N/A | N/A | **BLOCKED** (Resource Gated) |

---

## 2. 核心指標對比分析

1.  **通過率與修復力躍升**:
    - **Route C (3B Judge + Dual Proposer)** 在 6 大任務上取得了 **100% (6/6)** 的通過率。這表明異質模型組合（Qwen 7B 擅長 Table format 等一般代碼修改，DeepSeek 6.7B 擅長 Sympy 的置換循環代碼機制）能在 Nexus 裁決下，取得互補的最佳效果。
2.  **3B 裁判 (3B Judge) 路由守門人價值**:
    - 在 Route C 中，`qwen2.5-coder:3b-instruct` 作為裁判，能精準判定任務的 `evidence_sufficiency`。它能預先攔截無效或資訊不足的任務，並通過 `ABSTAIN` 避免無效的 7B/6.7B 提案與 verifier 測試，提供了堅固的「防禦性守護」。
3.  **資源與時延分析**:
    - 由於採取了串行載入 (sequential execution) 策略，Route C 的記憶體峰值僅 6.8 GB，虛擬記憶體 Swap 為 0.0，且與 Route B 相比，3B 裁判的引入僅增加了約 50ms 的延遲，開銷極低，完全在 16GBRAM 容忍之內。
    - **Route D (14B Fallback)** 由於潛在的 CPU-only swapping 慢速推理風險被 Gate 阻斷，證實了 Resource Guard 動作正確。

---

## 3. 失敗分類學與退化審計 (`failure_taxonomy.json`)
- **Route A (Single 7B) 失敗成因**: 在 C_12481 與 C_13453 上發生代碼語義認知偏差，同質 clone test 表明該失敗為結構性偏見，無法透過 redundant 提案自癒。
- **Route D (14B Gated) 狀態**: 由於 Gated 阻斷，沒有在 16GB 設備上引發任何 OOM 或 Swapping 退化。
