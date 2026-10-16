# Worktree Cleanup Plan v0

## 1. Executive Summary
本計畫正式提出針對 Local 7B/14B 修復擴充能力沙盒封存後的「工作樹衛生清理計畫」。本報告僅做為清理方案計畫，**目前無執行任何刪除、還原或清理動作**，封存之實驗鏈狀態依然定為 **PAUSED_ARCHIVED**，且清理執行目前尚未被授權 (`cleanup_execution_authorized=false`)。

## 2. Source Hygiene Report
* **盤點報告來源**：`post_archive_worktree_hygiene_v0` 已完成，並盤點目前工作樹具有 modified 及 untracked 狀態。
* **主要髒污來源**：編譯產物緩存、 ad-hoc 實驗日誌以及尚未切分之未來工程代碼。

## 3. Current Git Status Snapshot
* **目前分支 (Current Branch)**：`feature/bridge-fastmatcher-20260606`
* **HEAD 提交**：`0e20fceb`
* **已追蹤但修改檔案數 (Tracked Modified)**：37
* **未追蹤檔案數 (Untracked)**：112
* **工作樹狀態**：髒 (Dirty)

## 4. Cleanup Action Matrix
針對髒工作樹中的所有主要檔案類型，規畫之處置矩陣如下：
* **Rust target 編譯產物**：核准後安全刪除。
* **Python pycache**：核准後安全刪除。
* **.hypothesis 測試緩存**：核准後安全刪除。
* **本地與 scratch 除錯日誌**：核准後安全刪除。
* **暫存 parser 腳本**：核准後安全刪除。
* **實驗性預測與基準 JSONL 檔**：核准後安全刪除。
* **未 committed 的正式 reports**：封存保留於 review 分組。
* **local_heal 運行代碼與單元測試**：保留並移轉至新工程 review 分支。
* **S2T 守衛與對齊候選**：保留並移轉至對應專門審查分支。

## 5. Proposed .gitignore Additions
建議新增以下 ignore 規則至 `.gitignore` 檔案中，以阻斷未來緩存與日誌被追蹤：
```text
# Cache and build outputs
nexus-core-rs/target/
.hypothesis/
**/__pycache__/
**/*.pyc

# Local execution logs and LLM traces
*.log
scratch/*.log
ollama_calls.log
run_output*.log
last_response.txt
last_patch_call.txt
last_patch_response.txt

# Experimental benchmark outputs
benchmarking/swebench_lite/*.jsonl
benchmarking/swebench_lite/*.json
```

## 6. Safe Delete Candidates
以下為低風險、可安全清理之緩存/日誌候選：
* `nexus-core-rs/target/` (建議命令：`rm -rf nexus-core-rs/target/`)
* `.hypothesis/` (建議命令：`rm -rf .hypothesis/`)
* `scratch/*.log` (建議命令：`rm -f scratch/*.log`)
* `ollama_calls.log` (建議命令：`rm -f ollama_calls.log`)
* `run_output*.log` (建議命令：`rm -f run_output*.log`)
* `parse_test*.py` (建議命令：`rm -f parse_test*.py`)

## 7. Tracked Restore Candidates
以下為已被 git 追蹤但屬於本地臨時修改的 restore/revert 候選：
* `Daily_Log.md` (需要 diff 審查)
* `implementation_plan.md` (需要 diff 審查)

## 8. Preserve-for-Review Packets
以下為未來工程線核心代碼與測試，應完全保留、不可進行清理，未來將移轉至對應分支：
* **local_heal_transport_hardening**：包含 `localizer.py`, `evidence_compactor.py`, `protocol.py` 等。
* **s2t_export_guard_candidate**：包含 `s2t_export_guard.py` 及單元測試。
* **strategy_or_strata_candidate**：包含 `strategy_envelope.py` 策略規劃核心。
* **tests_for_future_hardening**：包含單元測試。

## 9. Formal Evidence Commit Candidates
* `post_archive_worktree_hygiene_v0/`
* `worktree_cleanup_plan_v0/` (本計畫目錄)
建議在 owner 審查後，將這兩個正式盤點證據目錄與報告 commit 入倉庫。

## 10. Execution Options
後續清理執行選項：
* `APPROVE_SAFE_CACHE_AND_LOG_CLEANUP_ONLY` (僅清理安全緩存與日誌)
* `APPROVE_GITIGNORE_UPDATE_ONLY` (僅更新 .gitignore) — **推薦第一步**。
* `APPROVE_TRACKED_GENERATED_RESTORE_PLAN` (核准追蹤生成檔還原)
* `APPROVE_FORMAL_EVIDENCE_COMMIT_REVIEW` (核准盤點證據提交)
* `APPROVE_LOCAL_HEAL_HARDENING_REVIEW_PACKET` (核准切分新分支)
* `REMAIN_PAUSED_NO_CLEANUP` (保持現狀無清理)

## 11. Governance Preservation
本計畫完全符合治理防禦防線，不執行任何程式碼修改、S2T 導出、公開宣稱、或 StraTA 對齊。
