# UI Validator Skill (Playwright-based)

## 描述
- 這是 Nexus v8.5 的核心驗證技能。
- 採用 Playwright 在不同瀏覽器內核（Chromium, Firefox, Webkit）中自動執行 UI 點擊、導航與狀態檢查。
- 專門用於捕捉由於環境異質性導致的 Race Condition 或 UI 閃退問題。

## 指令
- 接收目標 URL 或 HTML 路徑。
- 自動掃描頁面上的所有交互元素（Button, Link, Input）。
- 執行「交互矩陣測試」，模擬點擊並檢索內容是否顯示。
- 切換多種視窗尺寸（Mobile/Desktop）驗證響應式穩定性。

## 輸入合約
- **target_url**: 待測 UI 的網址或本地路徑（str）。
- **browsers**: 測試瀏覽器清單（list, 預設為 ["chromium"]）。
- **generate_video**: 是否生成測試錄影證據（bool, 預設為 true）。

## 輸出合約
- **interaction_matrix**: 矩陣結果報告（JSON）。
- **coverage_score**: UI 交互覆蓋率得分（float）。
- **crash_incidents**: 偵測到的閃退或異常事件（list）。
- **video_path**: 錄影儲存路徑（str）。

## 負面約束
- **嚴禁** 使用 `alert()`。若偵測到代碼中包含 `alert()`, `confirm()` 或 `prompt()`，應立即標記為嚴重 Bug。
- **嚴禁** 略過任何具備可交互標籤（如 `onclick`）的元素。

## 執行細節
- 腳本位置：`scripts/ui-validator.py`。
- 必須使用 `uv run --with playwright` 執行。
