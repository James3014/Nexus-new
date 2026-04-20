# 🆘 Error Playbook & Recovery

## 1. 常見 Gate 失敗排除 (Troubleshooting)

### ❌ Code 16 (Governance Deadlock)
- **現象**: 提交因「完整性」與「驗收」互斥而死鎖。
- **解法**: 分開提交。先提交 Wiki 補件，通過 `ci_gate` 綠燈後，再執行代碼的 Promote。

### ❌ Hallucination Index >= 6 (REJECTED)
- **現象**: 審計器判定為「空口說白話」，缺乏證據。
- **解法**: 檢查 `hallucination_evidence.json`。確保 `command_artifacts` 包含真實的測試輸出摘要，而不僅是指令名。

### ❌ Wiki Drift Detected (P0)
- **現象**: 修改了核心 `nexus/core/*.py` 但 `Ops - Governance Changelog.md` 沒更新。
- **解法**: 根據當前 Commit 的 Rationale，手動在 Wiki 表格中新增一列，並填寫風險與驗證人。

### ❌ Import Error (Relative Import)
- **現象**: 腳本無法在 `uv run` 下獨立執行。
- **解法**: 全面修正為絕對匯入，如 `from nexus.core.x import y`。

## 2. 恢復指令
- **`nexus resume`**: 從最後一個綠燈 Checkpoint 恢復。
- **`git checkout <STABLE_SHA> -- <FILE>`**: 當核心檔案遭損毀時的物理恢復手段。

---
**[Source: nexus_wiki_vault/06_Ops/Ops - CI Failure Playbook.md]**
