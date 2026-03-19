# 2026-03-18 Nexus Night Shift 整合分級路線圖

## 目標
將既有 `scripts/nightshift.py` 從歷史實驗腳本，升級為可接入 Nexus v1.8 主流程的夜間自動化能力。

## 分級方案

### Level 1（1-2 天）可用版
範圍：
1. 夜間排程執行 `scripts/ops/ci_gate.py` + benchmark。
2. 輸出統一報告（PASS/FAIL、失敗 case、關鍵指標）。
3. 早晨摘要（Markdown + Slack 可選）。

DoD：
- 每晚可穩定產生一份夜跑報告。
- 報告可追溯到 `ci_benchmark.csv` 與測試輸出。

### Level 2（約 1 週）半自動修復版（建議目標）
範圍：
1. 對高信心問題產出 patch proposal（diff/PR 草稿）。
2. 人審核後才可合併（Human-in-the-loop）。
3. 修補後自動回跑回歸與 drift gate。

DoD：
- 每個 patch proposal 都有對應測試證據。
- Gate fail 時自動回滾提案，不進主分支。

### Level 3（2-4 週）準自治版
範圍：
1. 多分身並行修復（Gemini worker + 主代理整合）。
2. 自動事件化（Jira/Slack）與 RCA 草稿。
3. 記憶回放與策略升降級（接 memory v2）。

DoD：
- 多任務夜跑穩定，無互相污染。
- 重大異常可自動生成可審計 RCA。

## 不做事項（當前階段）
1. 不做 production 全自動合併。
2. 不做無人監督自動修復。

## 推進順序
1. 先完成 Level 1
2. 通過 1 週穩定運行後進 Level 2
3. Level 2 穩定後再評估 Level 3

## 建議
以 Level 2 作為近期目標，兼顧效益與風險控制。
