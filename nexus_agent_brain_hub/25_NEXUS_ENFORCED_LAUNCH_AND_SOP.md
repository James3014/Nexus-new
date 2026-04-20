# 🚀 Nexus Enforced Launch & SOP

## 1. 啟動入口規範 (Entrypoints)
Nexus 嚴禁「裸執行」。所有的 Agent 會話必須經由啟動腳本進入，以載入必要的預檢環境與治理規約。

## 2. 標準啟動腳本
- **Gemini**: `bash scripts/ops/start_gemini_nexus_enforced.sh [prompt-file]`
- **Antigravity**: `bash scripts/ops/start_antigravity_nexus_enforced.sh [model]`
- **功能**: 
    1.  **Preflight**: 檢查 `uv`, `node`, `git` 狀態。
    2.  **Briefing**: 強制顯示當前任務契約與 `MUSE_PROTO`。
    3.  **Audit**: 任務結束後自動觸發 `acceptance-check`。

## 3. 標準作業程序 (SOP)
1.  **對齊**: 執行 `nexus:status` 確認當前工作區 SHA。
2.  **分發**: 使用 `nexus:route` 決定任務模式 (Baseline/Hyper/NightShift)。
3.  **實作**: 在隔離環境執行代碼修改。
4.  **證據**: 收集測試 Log 並寫入 `hallucination_evidence.json`。
5.  **結案**: 執行 `nexus:acceptance-check` 並回寫 Wiki。

## 4. 異常處理
- 若 Preflight 失敗：禁止繼續任務，優先修復基礎設施。
- 若 Contract 錯位：執行 `git rev-parse HEAD` 手動更新合約。

---
**[Source: nexus_wiki_vault/06_Ops/NEXUS_ENFORCED_LAUNCH.md]**
