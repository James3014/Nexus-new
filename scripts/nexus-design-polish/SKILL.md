# Nexus Design Polish Skill (Impeccable Adapter)

## 描述
- 這是 `pbakaus/impeccable` 的 Nexus 適配版本。
- 專注於前端介面的「美學 Audit」與「質感拋光」。
- 用於解決 AI 生成介面的「工程師味」，強化 Glassmorphism 與 Apple 式簡潔美感。

## 指令
- 接收待優化的 HTML/CSS 代碼或路徑。
- 執行 `/audit` 指令識別設計缺陷。
- 執行 `/polish` 調整間距、陰影與文字層次。
- **嚴禁** 使用 AI 慣用的紫色漸層與純黑背景。

## 輸入合約
- **source_file**: 待拋光的 UI 檔案路徑 (str)。
- **audit_only**: 是否僅執行審計不修改代碼 (bool)。

## 輸出合約
- **audited_report**: 繁體中文設計審計報告 (str)。
- **polished_code**: 優化後的 UI 程式碼 (str)。

## 執行細節
- 本技能為「代理型技能」，內部將引導 Agent 調用 `~/.agents/skills/impeccable/`。
- 輸出必須符合繁體中文鐵律。
