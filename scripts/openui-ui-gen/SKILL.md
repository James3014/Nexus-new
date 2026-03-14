# OpenUI UI Generation Skill

## 描述
- 基於 OpenUI 的 AI 驅動 UI 生成技能。
- 接收自然語言描述，透過 OpenUI API 生成響應式的 HTML/JS 程式碼。
- 賦予 Nexus 系統快速產出 WarRoom 與應用原型的能力。

## 指令
- 接收 UI 需求（例如：「毛玻璃三欄 WarRoom，支援手拉寬度調整」）。
- 調用 `http://localhost:7878/api/generate` 獲取 UI 代碼。
- 輸出完整 HTML 結構與 Git 分支建議。

## 輸入合約
- **description**: 詳細的 UI 功能與視覺需求（str）。
- **theme**: 介面主題（'apple' | 'dark' | 'glass'）。
- **responsive**: 是否需要響應式設計（bool，預設為 true）。

## 輸出合約
- **ui_code**: 生成的 HTML/JS 代碼（str）。
- **preview_url**: 預覽位址（str）。
- **integration_patch**: 整合建議腳本或補丁（list[str]）。

## 負面約束
- **嚴禁** 生成伺服器端（Backend）代碼。
- **必須** 符合 Nexus v8 的 UI/UX 美學規範（Glassmorphism）。
- **嚴禁** 除了 OpenUI 原生支援外的外部依賴性。

## 執行細節
- 本技能依賴於本地運行的 OpenUI 服務。
- 執行邏輯位於 `scripts/openui-ui-gen.py`。
