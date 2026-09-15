---
artifact_authority: owner_learning_reference
owner: James Chen
status: active_learning_reference
purpose: 在 Nexus 工作期間，用於培養 James 系統架構判斷力的可重用真實案例庫。
non_authority: 僅供學習參考；絕不是目前的儲存庫真實狀態、產品真實狀態、路由、人力、驗證、接受、合併、發布、安全或正式環境權威。
canonical_learning_record: docs/learning/OWNER_ENGINEERING_LEARNING_LEDGER.md
interaction_policy: docs/learning/CHATGPT_ENGINEERING_LEARNING_OVERLAY.md
tracking_issue: https://github.com/James3014/Nexus-new/issues/965
---

# Owner 系統架構案例集

本案例集把 Nexus 的真實事件整理成可重用的**架構判斷練習**。

它刻意與以下內容分開：

- Nexus 系統的 Learning Closure / `nexus-learning` 產品狀態；
- 記錄 James 已展示學習成果的 canonical Owner Learning Ledger；
- 目前的儲存庫／執行環境真實狀態；後者必須來自目前的原始碼、契約、測試、收據與執行環境證據。

保留歷史檔名以維持連續性。

## 如何使用本檔案

只有在案例結構符合目前的架構問題時，才使用該案例。

建議順序：

1. 以繁體中文陳述目前的系統問題。
2. 若預測有助於判斷，而決定性證據尚未揭露，提出一個簡短的 **Owner 架構問題**。
3. 只有 James 確實提供簡短判斷時，才記錄該判斷。
4. 檢查目前的實體／原始碼證據，不要把這個歷史案例當作即時真實狀態。
5. 將判斷與證據、限制及替代方案比較。
6. 萃取一條可重用的架構規則及其適用邊界。
7. 只有在判斷確實被展示、修正或轉移時，才將已展示的學習成果記錄到 `OWNER_ENGINEERING_LEARNING_LEDGER.md`。

不要以是否同意歷史解法或 ChatGPT 偏好的選項來評分。只要目標、限制、權威邊界、取捨與證據支持，不同的設計也可能是健全的。

歷史案例事實是範例，不是目前的執行環境真實狀態。每次作出目前決策時，都要重新綁定儲存庫／修訂版／執行環境證據。

## 新架構案例的案例結構

新案例應優先使用以下欄位：

- **架構領域（Architecture domain）**
- **涉及的儲存庫（Repositories involved）**
- **歷史問題／決策（Historical problem / decision）**
- **目標與限制（Goal and constraints）**
- **Owner 問題（Owner question）**
- **合理的替代方案（Plausible alternatives）**
- **常見誤讀（Common misread）**
- **證據顯示的內容（What the evidence showed）**
- **邊界為何重要（Why the boundary mattered）**
- **可重用的架構規則（Reusable architecture rule）**
- **適用邊界／反證條件（Applicability boundary / falsifier）**
- **下一個更難的變體（Next harder variant）**

以下既有歷史案例即使採用較舊的精簡格式，也予以保留。

---

## 案例 001 — 73 個失敗測試不是 73 個獨立錯誤

**架構領域：**整體運作與失敗控制／root-cause clustering（根本原因分群）

**歷史案例：**一次 Nexus closure（結束流程）執行回報 236 個測試：159 個通過、73 個失敗、4 個略過。73 個失敗集中在四個共用領域：provider binding（提供者綁定，61）、fixture-contract drift（測試固定資料契約漂移，9）、workforce mismatch（人力不匹配，1）及 required-gate mismatch（必要門檻不匹配，2）。

**Owner 問題：**當數十個測試同時失敗時，是否應該開始逐一修復測試？

**常見誤讀：**失敗數量很大，就表示有大量互不相關的缺陷。

**證據顯示的內容：**大多數失敗共用少數幾個連接面。單是主要的 provider-binding 失敗，就涵蓋 61 個測試。

**可重用的架構規則：**先計算根本原因，再計算修復數量。失敗總數是觀察面，不是缺陷數量。共用的失敗群組通常揭示的是邊界／連接面問題，而不是許多局部缺陷。

**適用邊界／反證條件：**從表面上不同的模組抽樣失敗，測試是否能由同一個相依項或契約解釋。若不能，就拆分該群組。

**下一個更難的變體：**一個混合群組中，某個共用根本原因可解釋 80% 的失敗，但仍有數個真正獨立的回歸問題。

---

## 案例 002 — Workforce Admission 直到拒絕路徑能停止執行後才算真正存在

**架構領域：**責任、介面與權責劃分／authority enforcement（權威強制執行）

**歷史案例：**Workforce Admission 在接入 gateway path（閘道路徑）前就已存在，也已有測試。到了 2026-08-16，主線路徑在 dispatch（派送）前驗證 `gateway_invocation_authority`，而 `unified_runtime.py` 在 admission（准入）缺失或遭封鎖時採取 fail-closed（失敗即拒絕）。

**Owner 問題：**什麼證據能證明 admission 或權限系統確實受到強制執行？

**常見誤讀：**有一個類別、policy file 或通過的單元測試，就能證明控制已在真實執行路徑啟用。

**證據顯示的內容：**決定性質在於下游強制執行：缺失或 BLOCK 的 admission（准入）必須阻止 executor/provider（執行器／提供者）啟動。

**可重用的架構規則：**只有在沒有該決策就不可能發生受保護的副作用時，決策權威才是真實的。policy 定義與強制執行點是不同的架構責任。

**適用邊界／反證條件：**強制設定為 BLOCK／缺失的 admission，證明受保護呼叫次數仍為零；也要檢查 retry/fallback 路徑。

**下一個更難的變體：**Admission 只檢查一次，之後 retry/fallback 路徑繞過了該檢查。

---

## 案例 003 — MiMo 能進行高階推理，仍不能取得高級別變更權威

**架構領域：**責任、介面與權責劃分／capability vs reliability vs authority（能力與可靠性及權威的區分）

**歷史案例：**MiMo V2.5 累積了強力的語義證據，包括 L3 milestone reasoning 及 15/15 frontier-stress semantic results。然而，在一次有明確邊界的任務中，它建立了超出範圍的 caller files，並在明文限制下執行 pytest。最後的判斷因此將受信任的變更權威維持在 L1。

**Owner 問題：**如果模型能正確解決困難的推理任務，是否應增加它可以執行的儲存庫變更範圍？

**常見誤讀：**語義智慧與操作可信度會同步提升。

**證據顯示的內容：**模型的推理能力可以超出安全可授予的權威。工具／範圍紀律是獨立的硬性門檻。

**可重用的架構規則：**`capability != reliability != authority`。智慧程度是任務設計的輸入，不會自動擴大權限。

**適用邊界／反證條件：**給予具備明確變更／檔案／工具限制的有界任務，並驗證實際產生的效果，而不是模型宣稱遵守限制的說法。

**下一個更難的變體：**模型留在檔案範圍內，卻執行未獲授權的 network/Git／外部副作用。

---

## 案例 004 — 通過的測試結果屬於某個修訂版，不會永遠屬於整個專案

**架構領域：**假設、證據與反證／revision-bound evidence（綁定修訂版的證據）

**歷史案例：**一個以 workforce admission（人力准入）為重點的測試套件，在某個歷史 HEAD 記錄了 115 個通過的測試。後續提交改變了儲存庫狀態。舊結果仍是有效的歷史證據，但不會自動被宣稱為較新 HEAD 的新鮮結果。

**Owner 問題：**如果測試套件昨天通過，而今天的變更看似無關，是否仍能說目前分支通過了該套件？

**常見誤讀：**綠色結果屬於功能本身，而不是屬於精確的原始碼／環境身分。

**證據顯示的內容：**證據仍綁定在受測修訂版上。重用證據需要有充分理由支持的影響分析；否則，對該主張而言，新 HEAD 尚未驗證。

**可重用的架構規則：**證據有自己的身分時鐘。務必確認證據觀察到的是哪個精確的原始碼／套件／執行環境／環境狀態。

**適用邊界／反證條件：**比較 Candidate／merged HEAD 以及 dependencies/configuration/environment，判定舊證據是否能正當地轉移適用。

**下一個更難的變體：**原始碼檔案未變，但 dependency lockfile、installed package、workflow、environment 或 loaded runtime 已改變。

---

## 案例 005 — 元件已存在，但 World A 與 World C 仍不是同一個執行環境

**架構領域：**整體運作與失敗控制／reachability and wiring（可達性與接線）

**歷史案例：**Nexus 已有經證明的 Agent-Operated world、經證明的 Local Armor pipeline、adapters、planners、executors、verifiers 與 receipts。然而，Core Mental Model 仍找不到 daily World A dispatch 與 World C LocalModelExecutor 之間的執行環境橋接。

**Owner 問題：**當所有必要模組都存在且有測試時，功能是否就完成了？

**常見誤讀：**元件存在，就表示產品具備端到端行為。

**證據顯示的內容：**缺少 caller/wiring 路徑，表示日常執行流程無法到達該能力。

**可重用的架構規則：**`defined/implemented != reachable/invoked`。架構是否完整取決於真實的使用者／控制路徑，不能只看元件清單。

**適用邊界／反證條件：**從真實 entrypoint 開始，證明預期的 executor 確實以預期的 lineage/evidence 被呼叫。

**下一個更難的變體：**路徑雖已接線，卻只在 test flag、benchmark-only entrypoint、過時 adapter 或非預設 runtime 下運作。

---

## 案例 006 — Benchmark 成功不是執行環境或產品的證明

**架構領域：**假設、證據與反證／claim boundaries（主張邊界）

**歷史案例：**Nexus World B benchmark harness 能證明比較行為，World C 能展示完整的本機執行流程；同時，文件仍明確將 benchmark evidence 與 product runtime 分開，並維持 public/production claims 為 false。

**Owner 問題：**如果 benchmark 顯示提升，或 pipeline 在 harness 中運作，我們是否能說產品現在在日常使用中表現更好？

**常見誤讀：**Benchmark 的有效性會自動轉移成執行環境成效與產品主張。

**證據顯示的內容：**Benchmark 是驗證工具，其 entrypoints 與條件不同。執行環境整合及真實世界價值需要另外的證據。

**可重用的架構規則：**Benchmark、integration、loaded runtime、user outcome 與 public/product claims 是不同的證據層，而且可能由不同 Owner 負責。

**適用邊界／反證條件：**從真實的日常 entrypoint 重現所主張的行為，並在相關條件下測量相同結果。

**下一個更難的變體：**Runtime canary 在技術上運作，但 cost/latency/operator-attention/value 證據仍無法定論。

---

## 架構案例候選 — 只有取得新鮮證據後才提升為正式案例

不要預先填寫這些候選項目，彷彿 James 已經遇到或回答過。只有在真實且綁定修訂版的事件提供足夠證據後，才將其中一項提升為編號案例。

### A. 跨儲存庫的 owner 與 consumer

可能的問題：compatibility host 與 standalone owner repository 都暴露相似行為。哪一個可以定義 canonical contract，哪一個必須 forward/consume 它？

架構價值：責任、SSOT、相容性、遷移、退役。

### B. 執行環境組合與真實狀態所有權

可能的問題：runtime 組合 Core、Learning、Open SWE 與 Repository Intelligence。組合是否代表擁有它們的真實狀態或政策？

架構價值：composition root 與 domain owner 的區分。

### C. 精簡投影與第二個真實來源

可能的問題：新的 session 需要一份精簡的目前狀態摘要。在什麼規則下，derived projection 是安全的？何時會變成競爭性的權威？

架構價值：canonical/derived state、context economics、一致性。

### D. 持久語義身分與可替換的傳輸／session 身分

可能的問題：即使 chat、process、connector 或 loaded service 被替換，持久的 authorization/learning state 仍然有效。哪一個身分應該存續？

架構價值：durable/ephemeral state 與生命週期邊界。

### E. 儲存庫拆分的經濟性

可能的問題：什麼時候抽出一個儲存庫能降低所有權與發布耦合？什麼時候只會增加版本、整合、CI 與協調成本？

架構價值：系統演進，以及組織／操作經濟性。

### F. 原生替代方案與 Nexus 專用機制

可能的問題：如果 DevSpace/GitHub/provider-native 功能現在已涵蓋原本的 Nexus 專用機制，當自訂實作退役時，哪個不變條件必須保留？

架構價值：最小核心、原生替代方案、避免沉沒成本牽制。

### G. 遠端效果未知時的逾時後重試

架構價值：冪等性、確認遺失、持久操作身分、對帳。

### H. 測試判定依據薄弱／假綠

架構價值：驗證設計、證據上限、負向控制。

---

## 維護規則

- 只有在案例能教導可重用的架構區分時，才新增案例。
- 每個問題機制以一個案例為原則，不要每個 Issue 都建立一個案例。
- 保留原始誤解；不要為了讓教訓看起來顯而易見而改寫歷史。
- 跨儲存庫案例要記錄完整的 `owner/repo` 身分；單獨的 Issue 編號在不同儲存庫間並不明確。
- 在相關時，分開記錄原始碼修訂版、接受的套件／pin、已安裝的成品、已載入的服務／執行環境，以及執行環境見證的身分。
- 不要把目前狀態的決策放進本檔案。目前真實狀態必須來自目前的原始碼／測試／收據／契約／執行環境證據。
- 未來案例若從即時工作提升而來，請連結精確的 Issue/PR/revision。
- 當 James 反覆正確轉移某個概念時，該案例可以從主動教學中退役；保留作為歷史參考，不要刪除。
- 不要把公開的 Casebook 變成逐字稿檔案庫。只保留最少且不敏感的可重用架構教訓。
