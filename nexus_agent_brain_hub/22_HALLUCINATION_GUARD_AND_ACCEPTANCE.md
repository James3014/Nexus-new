# 🧠 Hallucination Guard & Acceptance Check

## 1. 證據驅動驗收 (Acceptance-First)
Nexus 拒絕口頭宣稱「已修復」。所有的完成宣告必須有物理證據 (Artifacts) 支撐。

## 2. 幻覺指數 (Hallucination Index, HI)
- **原理**: `HallucinationGuard` 掃描 Agent 的回覆內容與 `evidence_bundle`，尋找「過度承諾」或「證據缺失」的信號。
- **評分標準**:
    - **VERIFIED (0-2分)**: 證據充足，命令執行成功。
    - **PARTIAL (3-5分)**: 有修改但缺乏關鍵測試輸出。
    - **REJECTED (>=6分)**: 宣稱修復但無對應變更或測試失敗。

## 3. 證據清單格式 (evidence_ingest.json)
必須包含：
- **`code_artifacts`**: 實際修改的檔案路徑。
- **`test_artifacts`**: 測試指令與關鍵結果。
- **`command_artifacts`**: 修改系統狀態的關鍵 Bash 指令及其回傳碼。

## 4. 執行與審計
- **入口**: `uv run scripts/engine/nexus_cli.py nexus acceptance-check`。
- **動作**: 系統自動解析 `.nexus/reports/hallucination_evidence.json` 並給出 Verdict。

---
**[Source: scripts/ops/nexus_acceptance_check.py]**
