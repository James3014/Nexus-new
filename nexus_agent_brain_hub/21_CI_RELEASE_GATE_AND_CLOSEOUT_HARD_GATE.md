# 🛡️ CI Release Gate & Closeout Hard Gate

## 1. 物理發布門禁
Nexus 不允許未經「物理驗證」的代碼進入主線。這是由 `scripts/ops/ci_gate.py` 強制執行的。

## 2. 檢查項清單 (Gate Checklist)
- **Physical Integrity**: 虛擬環境與基礎設施探針。
- **Agent Protocol**: 檢查是否遵守 `allowed_paths`。
- **Lesson Writeback**: 檢查 24 小時內是否有教訓回寫紀錄。
- **Wiki Sync**: 確保 `nexus_wiki_vault/` 檔案與程式碼異動同步。

## 3. 結案硬門檻 (Closeout Hard Gate)
在任務結算 (Closeout) 時，系統執行：
- **`contract-check`**: 比對 `task_contract.json` 定義的檔案範圍與實際變更。
- **`wiki-drift-enforce`**: 檢測 Wiki 與代碼間的語義漂移 (P0 級別漂移將直接阻斷)。

## 4. 執行命令 (Enforced)
```bash
# 完整門禁檢查 (Dry-run 模式)
uv run scripts/ops/ci_gate.py --dry-run --wiki-drift-enforce-level p0
```

---
**[Source: nexus_wiki_vault/06_Ops/Ops - Closeout Hard Gate.md]**
