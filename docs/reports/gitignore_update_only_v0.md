# Gitignore Update Only v0 任務報告

## 1. 任務概述與目的
本任務為 `gitignore_update_only_v0`，旨在僅更新 `.gitignore` 檔案以阻斷未來本地模型修復過程中所產生的緩存、日誌及中間產物噪音。本任務嚴格限定「僅編輯 `.gitignore`」，禁止執行任何檔案刪除、`git clean`、`git reset` 或 `git restore` 等可能污染或變更工作樹的破壞性操作。

## 2. Ignore 規則與治理考量

### 2.1 本次核准並追加的規則 (Added Patterns)
本次編輯於 `.gitignore` 追加了以下規則：

```gitignore
# Nexus local generated/cache/debug artifacts
.hypothesis/
**/target/
*.log
scratch/*.log
ollama_calls.log
run_output*.log
last_response.txt
last_patch_call.txt
last_patch_response.txt
```

#### 治理與阻斷防禦原因：
* **`**/target/`**：阻斷 Rust 子專案（例如 `nexus-core-rs/target/`）編譯產生的大量二進位與暫存檔案，防範工作樹被大量編譯產物污染。
* **`*.log` / `scratch/*.log` / `ollama_calls.log` / `run_output*.log`**：封鎖 LLM 呼叫與運行期產生的巨量日誌，維持工作樹清爽。
* **`last_response.txt` / `last_patch_call.txt` / `last_patch_response.txt`**：防止 LLM 單次除錯產生的暫存文字檔被意外 commit。

---

### 2.2 被否決的忽略規則 (Rejected / Owner Review Required Patterns)
以下規則原先擬加入 `.gitignore`，但經審查後判定為**不應被忽略的實驗性輸出**，以維持 Owner 審核的可追溯性：

* **`benchmarking/swebench_lite/*.jsonl`**
* **`benchmarking/swebench_lite/*.json`**

#### 否決原因：
* 這些檔案代表了 benchmark 或 SWE-bench 實驗的最終預測輸出與軌跡。
* 若直接整類忽略，未來將無法對評測實驗的正確性進行溯源與 commit 審查，違反了治理原則。因此將其列為 `rejected_patterns`，未來保留供 owner review。

## 3. 當前工作樹狀態快照 (Post-Update Status)
在完成 `.gitignore` 更新後，對工作樹進行了 porcelain 狀態統計：
* **分支 (Branch)**：`feature/bridge-fastmatcher-20260606`
* **已修改檔案數 (Modified Files)**：66 個 (含 `.gitignore`)
* **未追蹤檔案數 (Untracked Files)**：224 個 (已因 ignore 阻斷規則減少了未來生成物噪音)

## 4. 治理合規聲明 (Governance Preservation)
* **封存鏈狀態**：`local_7b_14b_repair_expansion` 仍處於 `PAUSED_ARCHIVED` 狀態，且 `next_execution_authorized` 依然為 `false`。
* **執行權限**：本階段絕無授權 any 修復執行、評測或導出操作，亦無啟用任何 Strata S1/S2T。
* **安全邊界**：本任務不涉及任何運行代碼與測試的變動，無假綠燈 (False Green) 穿透風險。
