# Verifier Feedback Correction Without Training Report (P4)

本報告總結 **P4 — Verifier Feedback Correction Without Training** 的設計與實作。

## 1. 核心設計與實現
我們在 [patch_synthesis.py](file:///Users/jameschen/Workspace/nexus/nexus/services/local_heal/phases/patch_synthesis.py) 與 [corrector.py](file:///Users/jameschen/Workspace/nexus/nexus/services/local_heal/corrector.py) 中，實現了對 retry 糾錯循環（Self-correction）的嚴格限制：
1. **重試限制提示 (Prompt Contract)**: 當處於控制平面錨定編輯或覆寫模式時，在 `build_retry_prompt` 中附加強硬合約（Contract），禁止模型在 retry 階段變更或自行發明 SEARCH 區塊，限縮修改在 REPLACE 範圍內。
2. **Behavior Collapse Guard**: 若模型在 retry 階段輸出了與歷史 attempt 中相同的 `replacement_text`（去除空白比對），控制平面將直接阻斷該補丁，並將其判定為 `BEHAVIOR_COLLAPSE` 錯誤。這有效預防了 naive self-correction 帶來的行為崩潰與無限循環。
3. **Trace 記錄**: 每次的 `last_replacement_texts` 與 `last_search_anchors` 皆在 execute 與 telemetry 中妥善保留與回寫。

## 2. 單元測試驗證
在 [test_decoupled_architecture_tdd.py](file:///Users/jameschen/Workspace/nexus/tests/unit/local_heal/test_decoupled_architecture_tdd.py) 中新增了對應的單元測試：
- `test_behavior_collapse_guard_during_retry`: 驗證當 `attempt = 2` 且模型的 replacement_text 與上一次相同時，被 Guard 正確阻斷並回報 `BEHAVIOR_COLLAPSE`。

所有測試目前已 100% 通過。

最終狀態：**`P4_VERIFIER_FEEDBACK_CORRECTION_READY`**
