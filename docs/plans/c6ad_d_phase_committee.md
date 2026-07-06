# C6AD: D-phase Committee Diagnosis

## 目標
D 階段（診斷/root cause analysis）接上委員會，多模型獨立診斷 → Borda 選最佳診斷。

## Scope（from MEMORY）
- **僅 D-phase**，不做 A-phase，不做大重構
- **Models**: qwen2.5-coder:7b, deepseek-coder:6.7b, ornith:9b, qwythos:9b
- **Selection**: Borda voting 聚合 rankings，consensus diagnosis 進 retry prompt

## 現狀
- Planning phase（Phase 2）是單模型診斷
- CommitteeOrchestrator 只在 R-phase（patch synthesis）有委員會
- D/A 階段都是單模型

## Proposed Changes

### 1. `committee_orchestrator.py`
- 新增 `diagnose_with_committee()` 方法
- 在 `run()` 中，Phase 2 (plan_phase) 前插入委員會診斷
- 多模型獨立產生 diagnosis → Borda 選最佳 → 用最佳診斷驅動後續 phases

### 2. `interface.py`（if needed）
- 新增 `DiagnosisInput` / `DiagnosisOutput` dataclass

### 3. 新增測試
- `test_committee_diagnosis.py`：驗證多模型診斷 + Borda 選擇

## Verification Plan
1. `pytest tests/unit/local_heal/test_committee_diagnosis.py -x`
2. `pytest tests/unit/local_heal/ -x --tb=short`（不 regression）
3. committee trace 裡有 diagnosis 資訊

## Open Questions
- 診斷 Borda 選擇邏輯：用什麼 signal？
- 診斷結果如何注入後續 phases？
