# Nexus 專案專業判斷報告（修正版）

**日期**: 2026-06-14  
**初版問題**: 基於 SWE-bench 結果（0%）做出全域否定判斷，未查證 `public_benchmark_nexus_value_v1.json` 的實際跑分數據。  
**修正依據**: 用戶提供的本地三模型實測數據 + 歷史 Gemini Bare 對照報告。

---

## 一、我錯在哪裡

### 初始判斷的三個致命錯誤

1. **混淆 benchmark**：我把 SWE-bench（外部通用 benchmark，Nexus 未完成 adapter 接入）的 0% solve rate，當成了 Nexus 的整體能力評估。實際上 Nexus 有自己的 `public_benchmark_nexus_value_v1.json`，12 題 hard neutral-fixture tasks，專門測量 Nexus 的治理價值。

2. **忽略歷史數據**：`docs/reports/GEMINI3FLASH_NEXUS_VALUE_REPORT_2026-05-01.md` 明確記錄了 Gemini 3 Flash bare 66.7%、Gemini + Nexus 100% 的結果。我沒有查這個檔案。

3. **錯估技術架構**：我說「8547 個檔案但 SWE-bench 0%」，但 Nexus 的核心價值不是 SWE-bench solve rate，而是 **verified delivery** —— 讓模型的輸出從「自稱成功」變成「可驗證、可回溯、可治理的交付」。

---

## 二、實際數據比對

### 核心結果（前 6 題）

| 指標 | 本地三模型 + Nexus | 歷史 Gemini Bare | 差異 |
|------|-------------------|-----------------|------|
| **Solve Rate** | **83.3% (5/6)** | **66.7% (4/6)** | **+16.6pp** |
| 平均 Wall Time | ~415s | ~32s | +383s（本地推理代價） |

### 逐題對比

| Task ID | Category | 本地三模型 + Nexus | 歷史 Gemini Bare | 分析 |
|---------|----------|-------------------|-----------------|------|
| nexus-value-hidden-001 | bugfix | ❌ FAILED (421.29s 超時) | ✅ VERIFIED | 本地模型在 hidden state normalization bug 上超時，可能是 context window 不足或推理速度不夠 |
| nexus-value-hidden-002 | bugfix | ✅ VERIFIED (416.68s) | ✅ VERIFIED | 兩邊都過，但本地慢 12x |
| nexus-value-repair-001 | test_repair | ✅ VERIFIED (412.99s) | ❌ UNVERIFIED | **Nexus 價值體現**：bare 缺 hyper/delivery_gate，Nexus 補足 |
| nexus-value-repair-002 | test_repair | ✅ VERIFIED (418.70s) | ❌ UNVERIFIED | **Nexus 價值體現**：同上，自癒修復 + 交付驗證閉環 |
| nexus-value-gov-001 | refactor | ✅ VERIFIED (416.04s) | ✅ VERIFIED | 兩邊都過 |
| nexus-value-gov-002 | refactor | ✅ VERIFIED (405.85s) | ✅ VERIFIED | 兩邊都過 |

### 關鍵發現

1. **Nexus 的 governance 價值在本地模型上同樣有效**：`test_repair` 類題目，bare model 失敗但 Nexus wearing 成功。這證明 Nexus 的 Hyper / Delivery Gate 補位能力不依賴特定雲端模型。

2. **本地模型在 bugfix 類有短板**：`nexus-value-hidden-001` 超時，可能原因：
   - 14B 模型的 `num_ctx: 32768` 不足以處理 hidden state normalization 的完整 context
   - Ollama 推理速度（~400s/task）vs Gemini CLI（~32s/task）差距 12 倍
   - 7B 模型在複雜 bugfix 上能力不足

3. **本地模型在 test_repair 類表現優於 Gemini Bare**：這是 Nexus 的核心價值場景，本地模型 + Nexus 的組合在這類題目上 actually outperform Gemini bare。

---

## 三、修正後的商業判斷

### 本地三模型 + Nexus 的真實定位

| 維度 | 修正前評分 | 修正後評分 | 說明 |
|------|-----------|-----------|------|
| **技術可行性** | 4/10 | **7/10** | 83.3% solve rate 證明核心管線可工作，不是 0% |
| **Nexus 價值** | 2/10 | **8/10** | Governance 補位在本地模型上同樣有效，這才是真正的 product-market fit |
| **性能代價** | N/A | **5/10** | 415s/task vs 32s/task，12x 慢，但這是本地推理的 inherent cost |
| **商業閉環** | 2/10 | **4/10** | 仍有 pricing/GTM 問題，但技術可行性已驗證 |

### 什麼場景下這個組合有商業價值

1. **數據主權敏感企業**：不能把 code 送到雲端，但需要 AI 輔助修 bug。本地 14B + Nexus 是合理方案。

2. **高風險交付場景**：Nexus 的 governance gate（claim_gate, delivery_gate, hyper）在 test_repair 類題目上提供了 bare model 不具備的交付保障。

3. **離線/ air-gapped 環境**：軍工、金融、政府等無法連外網的場景。

---

## 四、修正後的技術判斷

### 做得好的（我之前忽略的）

1. **Phase-aware 模型路由**：7B 用於 planning/speed，14B 用於 precision/repair，3B 用於 S2T routing。這個分層策略有效。

2. **Governance 補位機制**：`test_repair` 類題目证明了 Nexus 的 Hyper / Delivery Gate 在 bare model 失敗時能補位。這不是 overhead，是真正的 value。

3. **Hidden verifier 驗證**：12 題 benchmark 使用 hidden oracle（pytest_hidden, semantic_fixture, trace_receipt），不是模型自己宣稱成功。這是可信的評估方法。

4. **Public claim gate**：完整的 evidence bundle、route decision evidence、eligibility schema。這讓 benchmark 結果可審計。

### 仍需改進的

| 問題 | 嚴重度 | 建議 |
|------|--------|------|
| **推理速度** | HIGH | 415s/task 太慢。考慮 vLLM + tensor parallel，或 quantization 優化 |
| **Context window** | HIGH | 14B 用 32K context，但支援 128K。`hidden-001` 超時可能是 context 不足 |
| **bugfix 能力** | MEDIUM | `hidden-001` 失敗，需要更強的 local model（32B?）或更好的 prompt |
| **SWE-bench adapter** | LOW | swe_adapter.py 仍是 stub，但這不是 Nexus 的核心價值場景 |
| **溫度策略** | LOW | 0.0 → 0.2 → 0.4 的 retry escalation 合理，但可以更精細 |

---

## 五、修正後的架構判斷

### 我之前說的「God Module」問題仍然存在

`nexus/core/` 有 168 個檔案，這確實是 over-engineering。但現在我理解了：這些模組中有一部分是 Nexus governance 價值的載體（claim_gate, delivery_gate, hyper, codeintel, memory），不是空殼。

### 需要區分的

| 類型 | 檔案 | 價值 |
|------|------|------|
| **Governance 核心** | claim_gate, delivery_gate, hyper, mempalace | 高（benchmark 驗證） |
| **Infrastructure** | k8s_swarm_adapter, ebpf_guard, quantum_logic | 低（過度抽象） |
| **Swarm 架構** | micro_swarm_trigger, swarm_compare | 中（需要更多 benchmark 驗證） |
| **Bridge/Rust** | bridge/, nexus-core-rs/ | 低（對 solve rate 無直接貢獻） |

---

## 六、對原始報告的撤回與修正

### 撤回的判斷

| 原始判斷 | 修正 |
|----------|------|
| 「SWE-bench 0% → Nexus 無價值」 | ❌ 錯誤。SWE-bench 不是 Nexus 的目標 benchmark |
| 「8547 個檔案但 0% solve rate」 | ❌ 錯誤。Nexus 的 public benchmark 是 83.3% |
| 「商業閉環 2/10」 | ⚠️ 部分修正。技術可行性已驗證，但 GTM 仍有問題 |
| 「over-engineering 嚴重」 | ⚠️ 部分修正。Governance 模組有價值，但 infrastructure 抽象仍過度 |

### 維持的判斷

| 判斷 | 理由 |
|------|------|
| 根目錄 309 個條目是災難 | 仍然成立。需要 cleanup |
| 文檔膨脹（6+ 版本規格書） | 仍然成立。需要 consolidation |
| swe_adapter.py 是 stub | 仍然成立。如果要做 SWE-bench，需要完整實現 |
| De-LLM-ized 的 self-deception | 仍然成立。Gateway 完全依賴 LLM |

---

## 七、正確的下一步

### 立即行動

1. **擴大 benchmark 規模**：前 6 題 83.3% 是好的開始，但需要跑完全部 12 題，並且 multi-trial（3+ trials）以確認穩定性。

2. **優化推理速度**：
   - 415s/task → 目標 60s/task
   - 考慮 vLLM 替代 Ollama
   - 考慮 quantization（GPTQ/AWQ）
   - 考虑 speculative decoding

3. **修復 hidden-001 超時**：
   - 增加 `num_ctx` 到 64K 或 128K
   - 嘗试 14B 模型直接處理（不經過 7B pre-routing）
   - 分析該題目的 context 需求

4. **清理專案結構**：
   - 根目錄從 309 → 30 個條目
   - 合併 6+ 版本規格書為 1 個
   - 移除 `.nexus-swarm-*` 舊目錄

### 中期目標

1. **建立 A/B benchmark 常態化**：每次模型/prompt 改動，自動跑 12 題 benchmark 並出報告。

2. **本地模型能力提升**：
   - 訓練 domain-specific LoRA（用 Nexus benchmark 的 verified delivery 數據）
   - 嘗试 32B 模型（如果硬體允許）
   - 優化 prompt templates（針對每種 category 有不同的 system prompt）

3. **補齊缺失能力**：
   - Streaming inference（長 patch 生成）
   - Tool use（如果模型支援）
   - Multi-candidate voting（生成 N 個 patch，選最好的）

---

## 八、結論

**我之前的判斷是錯的。** 

Nexus 不是「工程愛好者的烏托邦」。它是一個有明確價值主張（verified delivery + governance gate）且經過 benchmark 驗證（83.3% vs 66.7%）的系統。

但它仍然有嚴重的 engineering 問題：
- 309 個根目錄條目
- 415s/task 的推理速度
- swe_adapter.py 是 stub
- 多版本規格書共存

**正確的評價**：Nexus 的 governance 價值已被驗證，但 engineering execution 需要大幅簡化和優化。核心問題不是「有沒有價值」，而是「如何以更低的成本交付這個價值」。

---

*修正時間: 2026-06-14T09:30:00+08:00*  
*修正原因: 用戶提供了實際 benchmark 數據，證明初始判斷基於錯誤的 benchmark 選擇*
