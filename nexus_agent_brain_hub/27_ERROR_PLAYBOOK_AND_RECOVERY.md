# 🆘 Error Playbook & Recovery
**[PHYSICAL_STATUS: DEADLOOP_DECOUPLED | AUTO_RECOVERY]**

## 1. 常見 Gate 失敗排除 (Troubleshooting)

### ❌ Code 16 (Governance Deadlock)
- **現象**: 提交因「完整性」與「驗收」互斥而死鎖。
- **解法**: 系統已實作「解耦機制」，區分 `Integrity Claims` 與 `Acceptance Quality`。

### ❌ Hallucination Index >= 6 (REJECTED)
- **現象**: 審計器判定證據不足。
- **解法**: 檢查 `hallucination_evidence.json`。確保 `command_artifacts` 包含真實輸出摘要。

### ❌ Wiki Drift Detected (P0)
- **現象**: 修改了核心代碼但 Wiki 未更新。
- **解法**: 執行 `wiki:auto-gen` 自動合成條目，或手動更新 `Governance Changelog` 表格。

## 2. 恢復指令
- **`nexus resume`**: 從物理快照點（`.nexus/metabolism/task_stack.json`）精準恢復。
- **`git checkout <SHA> -- <FILE>`**: 物理恢復受損的核心檔案。

---
**[Source: New Dimension Audit Batch E - 2026-04-20]**
