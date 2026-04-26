---
name: notebooklm-bulk-injector
description: 🛡️ NotebookLM 批量物理注入衛星。專門解決「一次上傳大量目錄」的需求，支援自動遞迴掃描、認證自癒與精確計數。
version: 2026.04.21
---

# NotebookLM Bulk Injector

## 🎯 決策邊界
- **使用時機**: 當用戶需要將整個資料夾（含子目錄）同步至 NotebookLM 時。
- **不使用時機**: 單一文件上傳、非 Google 平台任務。

<workflow>
Step 1: Auth Check (認證預檢)
- 動作: 執行 `notebooklm auth check`。
- 若失敗: 執行 `rookiepy` Chrome Session 移植程序。

Step 2: Recursive Scan (遞迴掃描)
- 動作: 遍歷目標目錄，精確統計所有實體檔案。
- 支援格式: .md, .txt, .pdf, .json, .csv。

Step 3: Sequential Ingest (序貫注入)
- 動作: 逐一發送 `notebooklm source add` 指令，支援自動重試。

Step 4: Audit (物理對帳)
- 動作: 比對「本地檔案數」與「成功上傳數」，產出對帳報告。
</workflow>

<output_contract>
- 總掃描數: N
- 成功上傳數: M
- 失敗清單: [Path, Reason]
</output_contract>
