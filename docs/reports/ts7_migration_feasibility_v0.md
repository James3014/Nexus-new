# Nexus TypeScript 7.0 改寫可行性與架構深度評估報告

**Status**: `TS7_MIGRATION_FEASIBILITY_EVALUATED`  
**Execution Verification**: Verified via CLI `status` and `nexus code scan` dry-runs.

---

## 1. 實體執行數據與瓶頸分析 (Runtime Metrics & Bottlenecks)

在當前 Python + Rust Core 混合架構下，我們在 `/Users/jameschen/Workspace/nexus` 專案上實測了 CodeIntel Scan，得到以下數據：

* **掃描規模**：**5,546 個 Python 檔案 (Nodes)**，**12,153 條匯入依賴關係 (Edges)**。
* **Python 掃描耗時**：**約 17.3 秒** (使用 `ast.parse` 與 `os.walk` 遞迴)。
* **冷啟動開銷**：每次調用 `uv run scripts/nexus_cli.py`，由於 Python 需要載入 `click`, `yaml`, `pydantic` 以及內建的各種 Agent 模組，冷啟動延遲平均高達 **500ms ~ 800ms**。這在與 Git hooks (例如 pre-commit) 整合或進行高頻 CLI 調用時，會產生明顯的黏滯感。

### 1.1 內核調用 IPC 瓶頸
目前 Rust 核心（`nexus-core-rs`）在非 `pyo3` 綁定的模組中，仍大量採用 **JSON-IPC (Stdio 重定向)** 方式調用：
* 每次驗證狀態轉移（`ValidateTransition`）、驗證收據（`VerifyReceipt`）或比對測試（`VerifyReplay`），Python 端必須 spawn 一個 `nexus_core` 獨立進程，透過 stdin 送入 JSON，再從 stdout 讀取 JSON。
* **Process Spawning Overhead**：在高頻的多輪修復實驗中（如 7B/12B 多次 retry），頻繁 spawn 外部 process 與 JSON 序列化/反序列化（Serialization）吃掉了大量 CPU 時間，成為隱式瓶頸。

---

## 2. 雙跑比對與型別守恆 (Dual-Run & Type Preservation)

在 `nexus/bridge/fast_matcher.py` 中，我們發現系統已實裝了 **Dual-run (雙跑比對) 與 MismatchLedger** 機制：
* 系統同時執行 Python 版的 `py_scan` 與 Rust 版的 `rust_core.fast_scan`。
* 當兩者輸出不一致時，會自動記錄至 `rust_mismatch.jsonl`，確保 Rust 化過程的行為等價性（Behavioral Parity）。

### 2.1 型別對齊摩擦 (Type Drift)
當前架構中，狀態機定義 `FlowState` 與意圖規格在 Rust (`src/lib.rs` 中以手動 mapping `match_state`) 與 Python 之間是各自維護的。一旦 Rust 端修改了狀態轉移規則，Python 端無法在編譯期察覺，必須依賴運行時測試或 validation gate 攔截。

---

## 3. TypeScript 7.0 改寫之細部優缺點評估 (TS 7.0 Feasibility Pros & Cons)

### 🟢 深度優點 (Pros)
1. **解決 CLI/SDK 的啟動延遲 (Zero cold-start latency)**
   * TS 7.0 具有更高效的編譯與載入機制。若將 `nexus_cli.py` 改寫為 TS (以 Node.js 執行)，冷啟動延遲可降至 **<50ms**，並可方便打包成 Single-binary 派發。
2. **端到端型別守恆 (Compile-time Contract Preservation)**
   * 透過 **napi-rs**（Node-API 綁定），Rust 核心編譯時可以直接為 TypeScript 產生 `.d.ts` 聲明檔。當 Rust Kernel 的 `FlowState` 改變時，TS 控制面會在編譯期強制報錯，這比 Python (需依賴執行期 `pydantic` 動態解析) 具備更好的靜態防禦力。
3. **無鎖非同步 I/O 與多進程監管 (Asynchronous Event Loop)**
   * Node.js 天然具備無鎖的高並發 event loop，在與多個 MCP servers (如 serena) 進行 CLI 串流輸出與 JSON 通訊時，比 Python `asyncio` 更不容易發生 OS pipe buffer deadlocks，程式碼更為簡潔。

### 🔴 深度缺點 (Cons)
1. **AST 語義解析與操縱難題 (AST Ecosystem Gap)**
   * `local_heal` 管線（特別是 `ast_locator.py`、`surgical_context.py`）需要精確解析與重寫 Python 程式碼的 AST。在 TS/Node 生態中缺乏成熟的 Python AST parser。若為了 TS 控制面而必須跨進程去調用 Python `ast` 模組，會造成二次 IPC 開銷。
2. **AI 與科學計算生態割裂 (Ecosystem Disconnect)**
   * 本地 Qwen 模型的 rerun、數據對齊（Pandas）、以及語義向量檢索（LanceDB）在 Python 中有最原生的支持。若控制面強行 TS 化，勢必在「TS 策略層」與「Python LLM 執行層」之間產生大量的膠水代碼與 JSON-RPC 調用，使 `llm_trace.log` 的 Debug Trace 變得更加複雜與碎片化。

---

## 4. 結論與折衷建議 (Conclusion & Trade-offs)

對 Nexus 而言，**純 TS 或是純 Python 都不是最佳解，而是「三元分層架構」最符合實務**：

```
+-------------------------------------------------------------+
|                TypeScript 7.0 控制面 (Control Plane)        |
|  - CLI Entrypoint (Zero Cold Start)                         |
|  - API Gateway / Tauri UI / Node SDK                       |
|  - Policy & Schema validation (Zod / TypeBox)              |
+-------------------------------------------------------------+
                              |
                     JSON-RPC / N-API FFI
                              |
                              v
+--------------------------+  +-------------------------------+
|     Rust 性能核心         |  |      Python AI 執行層         |
|  - AST Single-Pass Scan  |  |  - local_heal / Ollama rerun  |
|  - Flow Control SM       |  |  - LanceDB / pandas           |
|  - Receipt Verification  |  |  - AST Surgical Patcher       |
+--------------------------+  +-------------------------------+
```

* **TypeScript 7.0 適用於外圍**：產品面、CLI 啟動器、SDK、Tauri 控制台、以及 Zod/TypeBox 型別合約定義。
* **Python 保留在執行層**：模型運行、數據科學分析、Repro run。
* **Rust 固化在性能與安全層**：AST Single-pass 掃描、狀態控制核心。
