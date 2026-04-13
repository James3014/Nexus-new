# ADR 012: AutoResearch 控制平面實作與三方對位

## 1. 現象與背景
Nexus 之前的自動化研究缺乏嚴格的評估契約與安全回滾機制，導致實驗結果難以重現，且在模型幻覺發生時可能損毀核心代碼。

## 2. 修復決策
對齊 `karpathy/autoresearch` (評估)、`ARC` (流水線) 與 `DeepScientist` (記憶與接管)，實作以下控制平面組件：
- **ExperimentScheduler**: 負責物理隔離與 `modifiable_scope` 硬化校核。
- **UnifiedEvaluator**: 強化統計嚴謹性，強制使用固定 Seeds 進行多輪驗收。
- **SelectorRollback**: 實作非破壞性安全回滾，使用檔案級備份取代 `git reset --hard`。
- **Phase Semantics**: 新增 `E` (Evaluate) 與 `S` (Select) 階段，確保語意全鏈路對齊。

## 3. 預防機制
- **Modifiable Scope**: 嚴格限制研究任務的寫入範圍，防止損毀核心代碼。
- **Safe Rollback**: 確保回滾不影響開發者未提交的工作。
- **Runbook**: 提供標準化的人機接管與失敗排查流程。

## 4. 驗收證據
- `tests/research/test_p1_gates.py`: 通過 (安全回滾與評估重現)。
- `tests/research/test_p2_gates.py`: 通過 (Scope 硬化與狀態轉移)。
- `tests/test_typed_handoff_v22.py`: 通過 (Phase 語意對齊)。
