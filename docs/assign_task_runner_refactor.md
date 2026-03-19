# Sub-Agent 任務派工單：解耦 Task Runner (階段 1)

**[語義激活鐵律]**：
指揮官指令：本專案已啟用 Serena 語義導航，請優先使用 `serena__` 工具。執行前請先呼叫 `serena__get_current_config` 確保語義索引已掛載。

## 🎯 任務目標
對 `scripts/ops/task_runner.py` 進行模組級別的瘦身（Thinning），落實單一職責原則。
請在隔離工作區 `.worktrees/refactor-task-runner` 下執行以下修改：

## 🛠️ 重構步驟
1. **抽離依賴鏈排序邏輯 (Topo Sort)**
   - 在 `nexus/core/` 下新建 `task_graph.py`。
   - 將 `scripts/ops/task_runner.py` 中的 `topo_sort` 函式完整移轉過去。
   - 確保原 `task_runner.py` 改用 `from nexus.core.task_graph import topo_sort`。

2. **抽離 PID Lock 行為**
   - 在 `scripts/utils/` 下新建 `pid_lock.py`。
   - 將 `acquire_lock` 與 `release_lock` 邏輯移出 `task_runner.py`。
   - 更新 `task_runner.py` 以調用新模組的鎖機制。

## 🛡️ 防幻覺 (Anti-Phantom) 合約與驗收標準
- **禁止吞錯**：任何依賴匯入錯誤必須自然拋出，嚴禁寫 `except: pass` 吞沒錯誤。
- **實體驗證 (L0 Gate)**：完成修改後，必須在該工作區內執行以下指令，確保無損壞：
  ```bash
  uv run python3 scripts/ops/task_runner.py --task preflight.read_index
  ```
  如果 Exit code 非 0，代表重構失敗，請自行查修至通過為止。

---
完成後，請報告 Orchestrator 進行後續的「併幹審查 (Codex-Loop)」。
