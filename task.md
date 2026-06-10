# 🛡️ Nexus Master Taskboard: Surgical Intelligence (v1.0)

## 📋 任務清單 (TODO)

### [P1] 模組化基礎
- [ ] **T1.1**: 實作 `SurgicalRetriever` (職責：檔案粗定位)
- [ ] **T1.2**: 實作 `SurgicalSlicer` (職責：函式級精準切片)
- [ ] **T1.3**: 實作 `SurgicalPacker` (職責：預算動態封裝)

### [P2] TDD 驗證
- [x] TDD: 新增/更新 unit tests (7 new tests)
- [x] 全量 `pytest tests/unit/local_heal/` 無 regression — **23/23 PASSED**
- [x] 本地 Ollama qwen2.5-coder:7b 端到端驗證 `astropy-14096` — **Status: SUCCESS**
  - 成功定位 `__getattr__` property shadow 的根源
  - 透過 refined guidance 導引 7B 模型生成無 regression 的完美 descriptor check 補丁
  - 通過 `verify_bug_14096.py` 的閉環測試驗證astropy-12907 測試案例)
- [ ] **T2.2**: 撰寫 `tests/unit/test_surgical_packer.py` (驗證純淨代碼產出)

### [P3] 系統集成
- [ ] **T3.1**: 重構 `Localizer` Facade
- [ ] **T3.2**: 執行 `astropy-12907` 最終挑戰

[NEXUS STATUS: SURGICAL_INTEL_INITIATED]
