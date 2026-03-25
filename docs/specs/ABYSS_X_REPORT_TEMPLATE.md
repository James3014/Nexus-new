# ABYSS-X 標準戰報與審查評分模板 (Nexus-v17 專用)

這份模板用於對齊實際專案骨架，作為 Nexus-v17 解決「塔羅斯協議 (Talos Protocol)」跨語言非同步死鎖問題的標準輸出格底，後續 AbyssScore 評分將依據此基準進行校準。

---

## [ROOT_CAUSE]
- 問題概要：跨執行緒無 GIL 的死鎖調用 (Cross-Thread GIL-less Deadlock)。
  在啟用 fast path 的情況下，Rust 非同步任務試圖跨邊界操作或觸發 Python 回調，
  但未正確取得解譯器全域鎖 (GIL)，導致與 Python 事件迴圈／GC 發生致命死鎖。

- Git Origin:
  - 由 `git-spec/commit_2.txt` ("feat: experimental fast path without GIL")
    與 `commit_3.txt` ("fix: rollback unsafe fast path (partial)") 中殘留的
    `#[cfg(feature = "fast_path")]` 分支引入歷史包袱。

- 精準根因（對齊目前骨架）:
  - `core/py_bridge.rs`:
    - 在 commit_2 中新增的 `run_job_fast(...)` 走的是「無 GIL 快速路徑」，
      並在 commit_3 只做部分 rollback，保留了 feature gate 分支仍可達。
    - 該分支在與 Python 互動時缺乏 `Python::with_gil` 保護。
  - `py/worker.py`:
    - 在 commit_4 中，當 `USE_FAST_PATH=1` 時，Worker 將改呼叫 fast path
     （邏輯上對應到殘留的 `run_job_fast`），把 Python callback/未來值暴露給無 GIL 的 Rust 執行緒。
  - `scripts/load_test.py`:
    - 預設不開 `USE_FAST_PATH`，因此 CI / 日常測試不會踩到此分支；
      只有專門壓測才會同時打開 env + feature 組合，使 bug 浮現。

---

## [ASYNC_TRACE]
- 進入點 (Python Async):
  - `scripts/load_test.py`: `main()` 透過 `asyncio.gather()` 併發呼叫 `Worker.run_once(...)` 50 次，在特定壓測環境下設定 `USE_FAST_PATH=1`。

- Python Worker 層:
  - `py/worker.py::Worker.run_once()`:
    - 建立一個 asyncio Future，並在 `_cb` 裡完成 `set_result`。
    - 使用 `loop.run_in_executor(None, self._engine.run_job, payload, _cb)` 將呼叫委派給背景執行緒。

- PyO3 Bridge 層:
  - 在穩定版路徑中，`PyEngine::run_job` 會在持有 GIL 的情況下呼叫 Python callback。
  - 但根據 `git-spec/commit_2.txt` 與 `commit_3.txt`，存在一個 fast path 變體 `run_job_fast`：
    - 嘗試「不持有 GIL」地把 callback 或 PyObject 包裝丟進 Tokio 任務，作為效能優化。

- Tokio 任務層:
  - fast path 下，Engine 內部的任務在 worker thread 中執行完 IO 後，
    直接對 Python callback / PyObject 進行操作（例如 `set_result` 或 `drop`），
    此時該執行緒並未透過 `Python::with_gil` 取得 GIL。

- 絞殺鏈 (Deadlock Pattern):
  - 當主執行緒的 Python 事件迴圈或 GC 在相近時間點觸及同一組 PyObject，
    兩方在未協調的情況下對 CPython 內部鎖進行操作，形成跨執行緒 GIL 死鎖，
    導致 `asyncio.run(...)` 永久掛起而無明顯 stack trace。

---

## [FIX_PLAN]
- 目標：
  - 保留 Fast Path 的存在與對外 async API 形狀（`PyEngine` / `Worker` 不變），同時避免任何「無 GIL 觸碰 Python 物件」的情況。

- Change 1（建議解 - 安全封裝）:
  - 在 fast path 的 Rust 端（`run_job_fast` 對應的實作）中：
    - 僅允許在無 GIL 狀態下執行純 Rust / IO 計算。
    - 一旦需要呼叫 Python callback 或操作 PyObject，必須明確包裹在：
      ```rust
      Python::with_gil(|py| {
          callback.call1(py, (result,))?;
          Ok(())
      })
      ```
      之中。
  - 也就是將「GIL 取得」集中在 PyO3 bridge layer，而不是在 Engine / Tokio 任務內部隱式觸碰。

- Change 2（替代解 - 嚴格隔離）:
  - 若不希望在 Fast Path 中引入任何 GIL 爭用：
    - 調整 `run_job_fast` 的介面，使其只處理與回傳「純 Rust 可 Send 的資料結構」（例如 String / struct DTO），不直接持有 PyAny / PyObject。
    - 在回到 PyO3 bridge 層時，才使用 `Python::with_gil` 將純資料轉回 Python 型別並觸發 callback。

- AST 局部穩定：
  - 不變更 `#[pyclass]` `PyEngine` 與 Python Worker 公開方法簽名。
  - 僅在內部實作中新增一層 GIL-safe 包裝或調整回傳型別，對既有測試與匯入路徑影響最小。

---

## [HEALTH_METRICS]
- Static Audit:
  - AST Scan + Git-spec 分析時間（預估）：< 2 ms（Zero-IPC 全專案掃描）
  - Fast Path 相關分支覆蓋：`engine.rs` / `py_bridge.rs` / `worker.py` / `git-spec/*`

- Dynamic Risk (預估):
  - 在未修復前：
    - `USE_FAST_PATH=1` + `feature=fast_path` 時，有機率出現 `asyncio.run(...)` 永久掛起。
  - 在套用 FIX_PLAN 後：
    - 不再存在任何「無 GIL 操作 Python 物件」的路徑。
    - fast path 僅執行純 Rust 計算，或在回 Python 前強制經過 `Python::with_gil`。

- API / 測試狀態:
  - 對公開 `PyEngine` / `Worker` API 無破壞性變更。
  - 現有以 stable path 為主的測試應維持綠燈，建議新增一個開啟 `USE_FAST_PATH` 的壓測型測試以覆蓋本次修補。

---
> 註：更深淵級的 `_run_job_no_gil` + `Arc<Mutex<PyObject>>` 死亡交叉版本將保留做為 **ABYSS-X-Plus**，專門用於極限壓榨高階 Agent。
