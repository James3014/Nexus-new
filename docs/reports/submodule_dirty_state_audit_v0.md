# Submodule Dirty State Audit v0 任務報告

## 1. 執行摘要 (Executive Summary)
本報告為 `submodule_dirty_state_audit_v0`，總結了針對 `.tmp_build` 目錄進行 submodule / gitlink 髒污狀態的唯讀審計結果。
* **唯讀審核**：本任務為純審核性質（audit-only），無執行任何 `git clean/reset/restore`，亦無進行任何 commit 或代碼修改。
* **原因定位**：審計確認 `.tmp_build` 目前為一 nested repository 指向（gitlink），其指向的 commit pointer （`d16bfe05`）未發生改變，髒污完全由子倉庫內部的 modified 與 untracked 檔案引起。

## 2. 來源驗證 (Source Validation)
* **封存狀態**：Local 7B/14B Repair Expansion 封存鏈狀態維持 `PAUSED_ARCHIVED`。
* **S2T Gate 狀態**：前置 S2T Export Guard commit 已成功入庫 (Commit: `9ca56ffe`)。
* **暫存驗證**：審計前無任何檔案處於 staged 狀態。

## 3. 父倉庫子模組狀態 (Parent Submodule State)
* **子模組路徑**：`.tmp_build`
* **對應配置**：`.gitmodules` 中無對應映射（ nested git 倉庫性質）。
* **Pointer 變化**：
  ```
  -Subproject commit d16bfe05a744909de4b27f5875fe0d4ed41ce607
  +Subproject commit d16bfe05a744909de4b27f5875fe0d4ed41ce607-dirty
  ```
  Pointer 本身沒有變化，只是後綴標記為 `-dirty`。

## 4. 子模組內部狀態 (Submodule Internal State)
在 `.tmp_build` 內部執行唯讀檢查之狀態：
* **Head Commit**：`d16bfe05a744909de4b27f5875fe0d4ed41ce607` (detached HEAD)
* **已修改檔案 (Modified)**：
  - `astropy/modeling/separable.py` (5 additions, 2 deletions)
  - `astropy/table/table.py` (1 addition, 3 deletions)
* **未追蹤檔案 (Untracked)**：
  - `astropy/reproduce_bug.py` (重現腳本)
* **變更類別**：`source_or_test_dirty`。主要是先前修復實驗與 bug 重現遺留下來的原始碼修改與實驗腳本。

## 5. 決策方案評估 (Owner Decision Options)
我們提供了以下處置方案：
* **方案 A (APPROVE_SUBMODULE_GENERATED_CACHE_CLEANUP_ONLY)**：僅清理子專案快取，不適用（無單純快取髒污）。
* **方案 B (APPROVE_SUBMODULE_INTERNAL_RESTORE_ONLY)**：強制還原子倉庫，捨棄所有實驗程式碼。
* **方案 C (APPROVE_SUBMODULE_POINTER_COMMIT_REVIEW)**：提交 pointer 變更，不適用（pointer 未改變）。
* **方案 D (APPROVE_SUBMODULE_PRESERVE_DIRTY_STATE) [推薦]**：保留目前子專案髒污狀態以留存重現實驗與腳本。
* **方案 E (APPROVE_RUNTIME_CODE_REVIEW_PACKET_CONTINUE) [推薦]**：忽略此 nested 狀態，繼續進行其餘 runtime code/test 套件的單檔精確 Gate 提交。

**推薦決策**：保留 `.tmp_build` 的髒污狀態以留存實驗數據，並繼續推進其餘 runtime 程式碼單檔提交（例如下一個 runtime code packet）。

## 6. 治理合規聲明 (Governance Preservation)
* **封存狀態**：Local 7B/14B Repair Expansion 封存鏈狀態維持 `PAUSED_ARCHIVED`。
* **合規操作**：無執行 git clean、無 restore、無 reset、無進行任何 commit 與 staging，保證完全唯讀。
