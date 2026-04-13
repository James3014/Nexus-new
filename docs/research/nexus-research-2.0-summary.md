# 🧬 Nexus Auto-Research 2.0 (Gladiator + MemPalace) 系統架構升級說明

*(這份文件匯總了 Gemini 與 Codex 的共同研討結果，將原本的「控制平面」升級為「全鏈路物理化研究工作室」的最新狀態)*

## 🎯 一句話定位
目前的 Nexus 已經從「工程型 AutoResearch 控制平面」，**進化為具備「語義多樣化 (Codex Pivot)」、「物理隔離沙盒 (Swarm Gladiator)」與「長效記憶代謝 (MemPalace)」的實戰級 Auto-Research 引擎。** 我們正式補齊了真實對戰與記憶傳承的最後一哩路。

---

## 🚀 新增了什麼（從 v1 到 v2.0 的進化）

### 1. 語義感知與多樣化生成 (Semantic Candidate Mutation)
*   **過去：** `candidate_count=3` 只是盲目地讓 Agent 重試三次。
*   **現在：** `ResearchPolicy` 具備語義偏移 (Pivot) 能力。當任務包含 `TIMEOUT` 時，系統會自動分配不同的「架構假設」給候選者（例如：Candidate A 假設是 Timeout、Candidate B 假設是 Race Condition）。
*   **AgentOpt 精神：** 便宜的執行模型 (Gemini) 能帶著高熵 (High Entropy) 的多樣化戰術進行探索。

### 2. 實戰沙盒對戰平台 (The Gladiator Benchmark)
*   **過去：** `research:benchmark` 只是個用亂數算機率的模擬摘要工具。
*   **現在：** 它是**全真的 Patch 對戰擂台**。引入了 `Swarm Workspace Broker`，為每一個候選者分配獨立的 `.nexus-swarm-*` 實體結界。
*   **物理隔離：** 候選者在 100% 隔離的結界中執行 `pytest` 或自訂驗證命令，徹底消除高並行下的代碼覆寫競爭，實現**零污染的平行測試**。

### 3. Codex 顧問升級門檻 (Dynamic Escalation Gate)
*   **過去：** 遇到難題只能讓執行模型死嗑，或是每一步都呼叫昂貴的強模型。
*   **現在：** 實作了 Fail-Open 的 **Codex Advisor Threshold**。當系統判定任務的「根因信心度 < 0.6 (Root-cause Confidence)」時，會自動觸發警告，建議升級呼叫 Codex 進行架構級重規劃 (Delta Plan)。這完美實踐了「強模型當顧問、小模型當手腳」的低成本高勝率管線。

### 4. 三位一體記憶庫與代謝機制 (Memory Metabolism)
*   **過去：** 打完擂台、修好 Bug 後，知識就隨報告丟棄了（角鬥士是失憶的）。
*   **現在：** 結合了 `LanceDB (檢索)` + `SQLite (索引)` + `MemPalace (治理)`。
*   **代謝閉環：** Gladiator 戰勝的策略會被送到 AAAK Judge 進行 30x 雜訊壓縮。通過審查的「精煉知識」會被原子寫入資料庫，並獲得模擬上鏈的 `arweave_tx_id`。下次遇到類似任務，系統會**直接調用歷史最佳解**，省下鉅額探索 Token。

---

## 📊 現在能做到的程度 (Capabilities)

1.  **自動分流與動態升級：** 簡單 Bug 直接修；複雜問題自動切入 Gladiator 模式並分配 3~5 個獨立結界對決；高風險/低信心問題主動 Call-out 請求 Codex 介入。
2.  **物理級安全並行：** 可以放心地設定 `max_parallel=10`，在不污染主分支與主工作區的情況下，安全驗證 10 種不同的架構改動。
3.  **「吃自己的狗糧」式開發：** AI 在寫出關鍵代碼前，可以先開個結界跑 3 種參數，選出 `average_score` 最高的勝出者再 Promote，確保代碼品質。
4.  **越戰越聰明：** 透過 MemPalace 與 LanceDB 的代謝，昨日解過的問題，今日將成為系統的「先驗提示 (Historical Hint)」。

---

## 🗺️ 還差什麼（對標 AutoResearchClaw & DeepScientist 的下一階段）

雖然底層引擎與對戰邏輯已極度強悍，但距離「完全無人值守 (Unattended) 的大規模科學工作室」，還有以下三里路：

1.  **長時間 Unattended Loop 的守護進程：**
    *   目前仍需由人或 CI 觸發 `research:run`。我們還需要一個像 `karpathy/autoresearch` 的 Background Daemon，能自動掃描 Codebase、發現優化點、自我提問並自動發起對決。
2.  **多階段研究產出物標準化 (Paper/Report Draft)：**
    *   目前產出的是 machine-readable 的 JSON 戰報。如果要對標 `AutoResearchClaw`，我們需要將戰報（包含對決矩陣、淘汰原因、效能對比）自動轉譯為人類可讀的「ADR (架構決策紀錄)」或微型 Paper。
3.  **Research Map (研究地圖可視化)：**
    *   目前 `palace.sqlite` 中已有完整的 Episode 追蹤，但缺乏一個 Web UI 或 CLI Tree 工具來可視化「這個 Bug 到底歷經了多少輪演化、淘汰了哪些策略分支」。

---
**總結一句話：**
目前的 Nexus 已經不僅僅是「零件」或「控制平面」，它是一座**「裝備了動態資源池 (Swarm)、物理隔離擂台 (Gladiator) 與長效大腦 (MemPalace)」的高效能 AI 角鬥場。**
