# Nexus BDD Automation Skill (AI-BDD Adapter)

## 描述
- 整合 `AI-BDD Automation Arsenal` 的 Nexus 適配版。
- 專注於「行為驅動開發 (BDD)」全流程：從 User Story 到 Gherkin (.feature) 產出，再到自動化測試腳本。
- 用於確保 Nexus 生成的功能具備可驗證的業務價值與 100% 測試覆蓋。

## 指令
- **規格定義**: 調用 `aibdd.spec.user-story.gen` 與 `aibdd.spec.prd.detail-req.gen`。
- **場景產出**: 調用 `aibdd.spec.bdd.feature.gen` 生成 Gherkin 語法。
- **自動化實作**: 調用 `aibdd.auto.python.unittest.pytest-bdd.*` 產出測試代碼。

## 輸入合約
- **requirement_desc**: 原始需求描述 (str)。
- **target_lang**: 目標開發語言 (str, 預設 "python")。
- **generate_diagrams**: 是否產出序列圖/活動圖 (bool)。

## 輸出合約
- **feature_file**: Gherkin 特性文件內容 (str)。
- **test_scripts**: 自動化測試腳本內容 (list[str])。
- **requirement_doc**: 結構化 PRD/User Story (str)。

## 執行細節
- 本技能驅動 `~/.agents/skills/aibdd.*` 指令集。
- 產出之規格文件必須符合繁體中文標準。
