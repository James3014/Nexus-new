# 🛡️ CI Release Gate & Closeout Contract
**[PHYSICAL_STATUS: PARALLEL_AUDIT | TRUTH_ENFORCED]**

## 1. 物理發布門禁
Nexus 不允許未經「物理驗證」的代碼進入主線。由 `scripts/ops/ci_gate.py` 強制執行。

## ⚙️ 實體化門禁規約
- **並行審計 (Parallel Audit)**: 
    - 採用 `ThreadPoolExecutor` 將 Wiki 漂移、能力覆蓋、回寫狀態與回歸審計並行化。
    - **效能**: 審計總耗時降低了約 75%。
- **檢查項清單**:
    - **Physical Integrity**: 基礎設施探針。
    - **Agent Protocol**: 嚴格遵守 `allowed_paths` 與檔案修改上限。
    - **Lesson Writeback**: 檢查 24 小時內教訓回寫紀錄。
    - **Wiki Sync**: 支援 `[wiki:auto-gen]` 自動合成治理日誌。
- **結案硬門檻 (Closeout)**:
    - **`contract-check`**: 比對 `task_contract.json` 定義的檔案範圍與物理變更。
    - **SHA Alignment**: 結案前強制對齊 `git rev-parse HEAD`。

## 2. 執行命令 (Enforced)
```bash
uv run scripts/ops/ci_gate.py --dry-run --wiki-drift-enforce-level p0
```

---
**[Source: New Dimension Audit Batch D - 2026-04-20]**
