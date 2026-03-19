# Nexus Trinity Evolution: Formal Build Spec (v1.0)

> [!abstract] 執行摘要
> 本專案旨在將楊定一博士的「意圖、同步、演化」哲學硬化為 Nexus 的工程能力。透過 TDD 流程，建立 P 階段意圖契約（Intent Contracts）、Context Hub 語義壓縮（Semantic Compression）與 C 階段創傷驅動調權（Trauma-Driven Weighting）。目標是讓 Nexus 具備 100% 的意圖對位率與自動化自癒能力。

---

## 1. Executive Summary (執行摘要)
- **核心目標**：實現「心領神會」的 LLM 協作。
- **三大支柱**：
    1. **Intent Gate (P Phase)**：防止模糊指令進入執行鏈。
    2. **Coherence Filter (Context Hub)**：透過 TOON 消除 70% 的 Context 噪訊。
    3. **Autonomic Weighting (Crystal)**：將失敗轉化為負向權重，避免重複錯誤。

---

## 2. State Transition & Lifecycle (狀態遷移與生命週期)
### 2.1 增強型 P-D-X-R-A-C 流程
- **[Forbidden]**：禁止在 `plan.json` 未通過驗證前進入 D 階段。
- **[Forbidden]**：禁止在 `learning_velocity < -0.5` 時跳過 Crystal 階段。
- **生命週期變更**：
    - P 階段新增 `IntentGuard` 審查。
    - A 階段失敗後強制觸發 `TraumaCapture` 寫入 Reflection。

---

## 3. JSON Schema Contracts (JSON 契約)
### 3.1 `plan.json` (強化版)
```json
{
  "intent_id": "uuid",
  "task_goal": "string",
  "success_criteria": ["string"],
  "scope_boundary": {"include": [], "exclude": []},
  "confidence_score": 0.0,
  "is_grounded": true
}
```

### 3.2 `autonomic_weights.json`
```json
{
  "skill_weights": {
    "nexus-debug-expert": 1.2,
    "generalist": 0.8
  },
  "trauma_records": [
    {"failure_signature": "string", "penalty": -0.5, "expiry": "timestamp"}
  ]
}
```

---

## 4. I/O Contracts (輸入輸出契約)
- **Context Hub -> LLM**：輸出必須包含 `[TOON_SUMMARY]` 視圖。
- **Audit -> Crystal**：傳遞 `last_audit_failure` 與 `retry_count` 作為調權權重。

---

## 5. Mechanized Safeguards: TDD Plan (測試驅動守護)
### 5.1 [RED] 失敗案例構造
- `tests/test_intent_gate.py`: 模擬模糊輸入 "修好它"，預期 `ValidationError`。
- `tests/test_semantic_compression.py`: 輸入 50KB 日誌，預期輸出 `< 5KB` 且保留關鍵錯誤。
- `tests/test_autonomic_learning.py`: 連續兩次同樣錯誤，預期 `skill_weight` 下降。

### 5.2 [GREEN] 最小實作
- 實作 `IntentGuard` 邏輯與 Pydantic 驗證。
- 實作 `ToonRenderer` 基礎摘要演算法。
- 實作 `WeightAdjuster` 數學模型。

---

## 6. Memory & Retrieval Policy (記憶與檢索策略)
- **Episodic Compression**：每 10 輪任務自動執行 `flash_ingest` 壓縮至 LanceDB。
- **Rerank Weight**：`learning_velocity` 權重佔決策比重 40%。

---

## 7. Migration & Rollback (遷移與回滾)
- **Patch-Only**：先發布 `state_contracts.py` 變更。
- **Rollback**：若 `avg_health < 80`，自動回滾 `autonomic_weights.json` 至 `baseline_v1`。

---

## 8. Observability & Telemetry (觀測與遙測)
- **指標 A**：`intent_alignment_rate` (P 階段修改率)。
- **指標 B**：`token_compression_ratio` (Context Hub 效能)。
- **指標 C**：`error_repeat_rate` (演化效能)。

---
%% 
由 Muse-Core Orchestrator 於 2026-03-19 完成 Trinity Evolution 計畫。
%%
