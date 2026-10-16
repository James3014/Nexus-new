# Local Deliberation Lane Scaffold Report (Phase 4)

**Date**: 2026-06-15  
**Version**: v1.0.0  
**Status**: **SCAFFOLD COMPLETE & TDD PASSED**  
**Governing spec**: [NEXUS_LOCAL_COLLABORATION_ROADMAP_V3.md](file://../roadmap/NEXUS_LOCAL_COLLABORATION_ROADMAP_V3.md)

---

## 1. 概述
本報告記錄了 `LocalDeliberationLane` 的搭建與 TDD 驗證結果。此 Deliberation Lane 作為 Nexus 受控的模型協商車道，允許 7B（Reasoner/Worker）生成主候選與推理，並由 14B（Judge/Synthesizer）進行 synthesis 與 route-review。

---

## 2. 核心架構與防禦性設計 (Architecture & Guardrails)

1. **僅限低風險與高價值任務 (Selective Triggering)**:
   - `should_trigger` 方法嚴格限制僅在 `high-uncertainty / high-value / research / repair-review` 任務上觸發，常規低風險任務直接旁路，節省物理成本。
2. **運行時合約與主權保護 (No Authority Leakage)**:
   - Deliberation 僅輸出決定性的 advisory 建議，不觸碰 `verifier`、`claim gate`、`delivery gate`，亦不可直接取代預設 router。
3. **健全的 Simulation 與 Fallback 機制 (Fail-Closed Fallback)**:
   - 內建 Ollama 連線異常、超時及 JSON 解析崩潰的自動退避機制。一旦遇到異常，自動降級為預設的 Python rule-based selector 或 simulation mode，確保運行時絕不中斷。

---

## 3. Deliberation Fitness 指標設計

引入了量化的適應度指標 `DeliberationFitness`：
* **agreement_rate**: 7B 和 14B 意見的對位度（一致為 1.0，不一致為 0.0）。
* **confidence_score**: 14B 輸出的決策信賴度。
* **thought_density**: thought tokens 佔總生成 tokens 的比例。
* **fitness_score**: 綜合評分（計算公式：$\text{agreement\_rate} \times 0.4 + \text{confidence\_score} \times 0.6$）。
* **is_stable**: 當 $\text{fitness\_score} \ge 0.75$ 時判定為穩定 (Stable)。

---

## 4. TDD 驗證證據 (TDD Evidence)

撰寫了標準單元測試 [test_local_deliberation_lane.py](file://../../tests/unit/test_local_deliberation_lane.py)，並執行通過：

```bash
uv run pytest -v tests/unit/test_local_deliberation_lane.py
```

**測試用例說明**：
* `test_deliberation_lane_should_trigger`: 驗證在不同 task_type 和 value_tier 下的觸發邏輯是否符合邊界。
* `test_robust_json_parse_handles_markdown_and_variants`: 驗證對 Markdown 程式碼塊包裹或單引號 Python 字典格式的強健解析。
* `test_deliberation_simulation_fallback`: 驗證在 `force_simulation=True`（模擬 Ollama 不可用）時的指標計算與穩定回傳。
* `test_deliberation_empty_candidates`: 驗證候選列表為空時的安全退避。

**執行結果**：
* ✅ **4/4 PASSED**

---

## 5. 結論
`LocalDeliberationLane` 的骨架已成功建立並通過完整測試，滿足 Phase 4 驗收條件，系統已具備受控的 7B/14B 協作審查基礎。
