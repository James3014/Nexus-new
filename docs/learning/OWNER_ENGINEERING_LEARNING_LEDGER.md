---
artifact_authority: owner_learning_record
owner: James Chen
status: active_learning_record
purpose: 記錄 James 在 Nexus 工作中展現的系統架構判斷能力發展，並可跨工作階段與 repository 持續保存。
non_authority: 僅屬個人學習狀態；絕不具備 repository、產品、路由、工作人員、驗證、接受、合併、發布、安全或生產權限。
interaction_policy: docs/learning/CHATGPT_ENGINEERING_LEARNING_OVERLAY.md
case_reference: docs/learning/OWNER_ENGINEERING_CASEBOOK.md
tracking_issue: https://github.com/James3014/Nexus-new/issues/965
---

# Owner 系統架構學習 Ledger

本 Ledger 是 James 在 Nexus 工作中展現之架構學習證據的**唯一正式記錄／歷史**。

它刻意與 Nexus 系統的 Learning Closure／`nexus-learning` 產品資料，以及 `docs/agents/LEARNING_WRITEBACK_OVERLAY.md` 分開。

使用 `OWNER_ENGINEERING_CASEBOOK.md` 作為可重用的真實案例教學庫。Casebook 保存歷史案例；本 Ledger 保存 James 展現的判斷與學習進展。

保留檔名是為了維持連續性。學習目標已超出工程證據判斷，現在是高階系統架構判斷。

---

## Current Learning State — bounded bootstrap projection

本節是有界的目前狀態投影；新的 Owner-facing 工作階段在閱讀完整歷史前，應優先參考本節。

**投影規則：**本節源自同一 Ledger 中已審閱的證據，不是獨立的熟練度權威。沒有下方相應的證據／歷史時，不得在此手動提升熟練度。

**目前狀態修訂：** `2026-09-15 / Issue #965 candidate design`

**適用範圍：**目前生態系中面向 Owner 的 Nexus 架構／開發工作，包括 `Nexus-new`、`devspace`、`nexus-core`、`nexus-learning`、`nexus-open-swe-runtime`、`repository-intelligence-engine`、`nexus-runtime` 與 `nexus-opencli-reviewer`。

### Current priority frontiers — maximum three

1. **跨 repository 的責任 / authority / SSOT 邊界** — 學會在 runtime、compatibility host、intelligence engine、reviewer、Core、Learning 與 execution repos 互動時，辨認正確的負責者。
2. **durable / ephemeral identity and state continuity** — 學會判斷哪些身分／狀態必須在 session／process／runtime 替換後存續，哪些應留在傳輸範圍內。
3. **architecture evolution and context economics** — 學會判斷新的抽象、repository、投影、相容層或 bootstrap 機制何時能降低複雜度，何時只是搬移或複製複雜度。

### Domain-level mastery view

六個架構領域是新的分組類別。既有的歷史子主題證據**不會**自動提升整個領域的等級。

| Architecture domain | 目前等級 | 證據邊界 | 下一個有用的真實案例 |
|---|---|---|---|
| 問題與目標界定 | UNASSESSED | 尚無直接的跨案例評估 | 提出新機制，但重用／不變更也是可信替代方案 |
| 責任、介面與權責劃分 | UNASSESSED | 歷史 SSOT／authority 子主題為 L1，但尚未評估跨整個領域的遷移 | 判斷跨 repo 的 owner 與 compatibility-consumer |
| 資料、狀態與身分設計 | UNASSESSED | 有相關討論，但尚未記錄經審閱的目前遷移證據 | durable semantic identity 與可替換的 session／runtime identity |
| 整體運作與失敗控制 | UNASSESSED | retry／reconciliation 曾列入歷史佇列，但未作為架構領域評估 | 帶有外部副作用的 timeout／lost-ack／retry 案例 |
| 成本、組織與系統演進取捨 | UNASSESSED | 尚無直接評估證據 | 判斷新投影／repo／service 是否降低總維護／context 成本 |
| 假設、證據與反證 | UNASSESSED | 歷史 falsification 子主題為 L1；尚無跨領域遷移評估 | 在實作前挑戰架構結論 |

### 仍有效作為歷史基線的既有子主題證據

這些不是整個領域的分數，也不會因 2026-09-15 的重新設計而默默提升：

這些子主題的歷史基線均為 L1：`SSOT / duplicate authority`、`Revision-bound evidence`、`Candidate != integrated != runtime-verified`、`Capability != reliability != authority`、`Fail-closed`、`Failure clustering / shared root cause`、`Falsification / negative testing`。
- `Test oracle quality`、`Idempotency`、`Timeout/reconciliation`：舊學習計畫中的歷史基線為 L0；不得用這些舊 L0 值推定新的架構領域分數。

### 近期互動筆記 — 非熟練度證據

- 2026-09-15：Owner 澄清主要學習目標應是**高階系統架構判斷**，不只是工程判斷。
- 2026-09-15：Owner 澄清面向 Owner 的技術互動必須能以**繁體中文**理解，因為過多英文術語會造成理解阻力。
- 2026-09-15：Owner 指出多 repository 分拆對學習設計很重要；學習狀態應涵蓋 Nexus 生態系，但不能成為任何 repository 的工程權威。

這些是需求／偏好與架構設計輸入，**不是** James 已在相應領域展現 L2/L3/L4 熟練度的證據。

### 重複防護／下一個前沿

不要只考 James 對 SSOT、authority、durable state 或 repository ownership 的定義。應優先使用具實質性的真實取捨，例如：

- 哪個 repository 應擁有跨 repo contract，哪個應維持為 consumer／projection；
- 精簡的目前狀態 artifact 是否會變成第二個 source of truth；
- runtime composition layer 是否也正在成為產品真實性的擁有者；
- 全新的 ChatGPT session 或 loaded-service replacement 後，哪個身分應該存續。

---

## 熟練度等級

證據不足時使用 `UNASSESSED`。`UNASSESSED` 與 L0 不同。

- **UNASSESSED — 尚未評估**：證據不足，無法為已展現的判斷分類。
- **L0 — 未接觸**：證據顯示這個概念尚未在本學習計畫中獲得有意義的接觸。
- **L1 — 看過**：在真實案例中看過這個概念，但尚未展現獨立判斷。
- **L2 — 能解釋**：能用自己的語言解釋關鍵區分及其重要性。
- **L3 — 能在不同案例中判斷**：能把區分應用到實質不同的真實案例，並為合理的架構結論／取捨辯護。
- **L4 — 能主動提出反證**：在尚未被告知關鍵缺口前，能辨認可信的反證、隱藏失敗或適用邊界。

不要只憑解釋提升熟練度。應優先採用真實預測、架構決策、修正、teach-back、遷移或反證提案的證據。

其他限制：

- 受提示後提出的反證是有用證據，但不會自動證明主動的 L4。
- 問題結構相同的不同 repository，不會自動算作新的遷移案例。
- 一個子主題的等級不會推廣到整個架構領域。
- 英文詞彙難度、略過學習問題或 bootstrap 狀態不可用，不會自動降低熟練度。
- 是否同意 ChatGPT 不是評分標準；標準是推理品質、限制條件、取捨與證據。

## 架構學習領域

將下列項目用作分組維度，不是另一套等級尺度：

1. 問題與目標界定
2. 責任、介面與權責劃分
3. 資料、狀態與身分設計
4. 整體運作與失敗控制
5. 成本、組織與系統演進取捨
6. 假設、證據與反證

testing、Git、debugging、retry、idempotency、model reliability 與 receipts 等工程子主題，仍是這些領域中的支持性證據。

---

## 歷史基線 — 2026-08-22

這是根據當時近期 Nexus 討論整理出的保守歷史起始基線。它**不是**目前的領域層級評估，也不宣稱 James 已明確展現尚未展現的熟練度。

| 概念 | 歷史等級 | 目前證據 | 下一個有用練習 |
|---|---|---|---|
| Worker self-report != independent evidence | L1 | 透過 candidate／acceptance workflow 與 Agent completions 討論 | 在真實完成的 worker task 中，判斷接受前必須獨立重跑什麼 |
| Revision-bound evidence | L1 | 討論測試結果隸屬於精確 commit／HEAD，合併後不會自動沿用 | 在 PR 中辨認 Candidate SHA、merged HEAD，以及哪些證據必須重新綁定 |
| Candidate != integrated != runtime-verified | L1 | 反覆出現的 Nexus 案例區分實作、合併與 runtime 真實狀態 | 對已合併變更精確分類哪一層已證明、哪一層仍未定 |
| Capability != reliability != authority | L1 | 討論過 model calibration 案例 | 面對強語意結果加上工具紀律失敗，選擇安全的 authority 上限並說明原因 |
| Fail-closed | L1 | 討論 Workforce Admission 案例：BLOCK 應阻止 provider calls | 提出證明拒絕路徑執行零次呼叫的 negative test |
| Failure clustering / shared root cause | L1 | 討論 73 個失敗對比少數 shared failure domains | 給定 failing-test cluster，預測個別修正或 shared-seam repair |
| Test oracle quality | L0 | 只在概念上介紹，尚未於舊計畫實作 | 對一套通過的測試，說明 assertions 證明及未證明的行為 |
| Falsification / negative testing | L1 | 已介紹 WHY_CORRECT framing | 接受前提出可能推翻修正的高價值案例 |
| Mutation-testing mindset | L0 | 作為工程證據的研究基礎提過 | 找出測試應捕捉的一種合理錯誤實作 |
| Idempotency / duplicate-effect handling | L0 | 舊計畫尚未練習 | 使用 Nexus 的 retry／duplicate dispatch 案例 |
| Timeout / lost acknowledgement / reconciliation | L0 | 相關但舊計畫尚未練習 | 檢視真實 timeout，判斷安全的 retry／reconciliation 條件 |
| SSOT / duplicate authority | L1 | Nexus 核心主題與 Skill 邊界討論 | 面對兩個看似決策來源，辨認 decision owner 與 projection |

---

## 預測與誤解登錄表

目的：保存**在知道關鍵證據之前**的判斷，避免事後之見把課題看得比實際容易，也讓後續工作階段能衡量遷移。

只記錄能測試架構／工程判斷的有意義預測。不要考 James 語法、瑣聞、英文詞彙或可機械搜尋的事實。

| ID | 日期 | 真實案例 | 測試概念 | James 在證據前的預測 | 證據／結果 | 誤解或正確啟發法 | 遷移狀態 | 重新測試觸發條件 |
|---|---|---|---|---|---|---|---|---|
| P-001 | 2026-08-22 | Learning program initialization | failure clustering | 尚未記錄 | 歷史 Nexus 案例：73 個失敗聚成 4 個 failure domains | 僅為基線；尚無已展現的預測 | UNTESTED | 下一次自然發生的多重失敗事件 |
| P-002 | 2026-08-22 | Learning program initialization | capability vs authority | 尚未記錄 | 歷史 model 案例：強語意 frontier 加上工具／範圍 hard failure，使 mutation 上限維持偏低 | 僅為基線；尚無已展現的預測 | UNTESTED | 下一次 model-promotion 或 dispatch-authority 決策 |
| P-003 | 2026-08-22 | Learning program initialization | revision-bound evidence | 尚未記錄 | 歷史通過的測試套件仍綁定其受測 HEAD | 僅為基線；尚無已展現的預測 | UNTESTED | 下一次 Candidate -> merge -> post-merge verification 流程 |

### 預測記錄規則

當真實 task 出現有用的學習時刻時：

1. 在揭示關鍵證據前，最多問一個簡短的判斷／預測問題。
2. 選項要反映真實架構替代方案；避免給出明顯答案提示。
3. 只有答案能教出可重用內容時才記錄。
4. 記錄 scaffold／prompt 等級，避免把受提示表現誤認為主動發現。
5. 檢視證據後，將結果分類為：
   - `CORRECT_TRANSFER` — 在實質不同的案例中推理正確；
   - `CORRECT_BUT_CUED` — 結果正確，但受到實質提示；
   - `MISCONCEPTION_FOUND` — 暴露錯誤模型或缺失的區分；
   - `EVIDENCE_INSUFFICIENT` — 證據實際上未解決問題；
   - `UNTESTED` — 僅為基線，尚未記錄預測。
6. 原文照錄或忠實轉述錯誤預測；看見答案後絕不改寫。
7. 單次正確預測不會自動提升至 L3；應優先觀察實質不同案例間的遷移。

---

## 間隔回想／自然遷移佇列

優先使用新的真實工作，不要安排日曆式測驗。

| 概念／領域 | 目前證據 | 下一種回想方式 | 觸發條件 | 狀態 |
|---|---|---|---|---|
| Cross-repo responsibility / authority | historical SSOT subtopic L1；domain UNASSESSED | 架構判斷 | 兩個 repos 看似擁有相同決策或 contract | WAIT_FOR_NATURAL_CASE |
| Durable vs ephemeral identity/state | UNASSESSED | 簡短架構預測 | session／runtime／process 替換且有 durable state | WAIT_FOR_NATURAL_CASE |
| Architecture evolution / context economics | UNASSESSED | 取捨比較 | 提出新的 repo／projection／daemon／pointer | WAIT_FOR_NATURAL_CASE |
| Revision-bound evidence | historical L1 | 辨認精確 evidence clocks | Candidate／main／package／runtime identities 分歧 | WAIT_FOR_NATURAL_CASE |
| Test oracle / false green | historical L0 | 反證 | 測試套件通過，但 acceptance 取決於它真正證明什麼 | WAIT_FOR_NATURAL_CASE |
| Timeout/reconciliation | historical L0 | 情境判斷 | 真實 worker timeout、disconnect、unknown acknowledgement 或 retry | WAIT_FOR_NATURAL_CASE |
| Idempotency | historical L0 | 情境判斷 | duplicate dispatch、webhook、retry 或外部副作用 | WAIT_FOR_NATURAL_CASE |

規則：

- 不要只因時間經過就重新教導概念。
- 若 James 在實質不同的案例中兩次展現 `CORRECT_TRANSFER`，應減少提示，逐步轉向不打斷工作的應用。
- 若 James 在狹窄概念達到 L4，只在明顯更難的變體或回歸證據出現時重訪。
- 有真實架構取捨可用時，避免只回想定義。

---

## Teach-back 證據

適度使用 teach-back。James 在看過證據後能以白話中文解釋區分時，這是有用方法。

記錄：

- 精確概念；
- 案例與 repository 身分；
- James 的簡潔解釋；
- 是否掌握關鍵邊界；
- scaffold 等級；
- 之後是否發生遷移。

Teach-back 可以支持 L2；沒有遷移或主動反證證據時，不能證明 L3/L4。

---

## 學習事件範本

只有在有意義的已展現判斷或有意義的修正時才追加。使用如 `LA-YYYYMMDD-NNN` 的穩定 event ID。

### LA-YYYYMMDD-NNN — [architecture concept]

- **觀察日期：** YYYY-MM-DD
- **Repositories：**完整的 `owner/repo` 身分；跨 repo 時使用多個項目。
- **真實案例：** Issue／PR／Candidate／runtime／架構決策。
- **Revision／runtime refs：**重要時記錄精確 SHA／身分；不要合併 source、installed package、loaded runtime 與 acceptance evidence clocks。
- **Architecture domain：**一個主要領域。
- **測試概念：**狹窄概念，不只是「architecture」。
- **關鍵證據前：**僅在確實捕捉到時，記錄 James 的預測或初始判斷。
- **Scaffold 等級：** `NONE`／`LIGHT`／`HEAVY`／`NOT_APPLICABLE`。
- **檢視的證據：**解決或限制該問題的精確證據。
- **結果／回饋：**實際為何，以及哪個區分最重要。
- **可重用原則：**簡潔的架構規則。
- **適用邊界：**規則不適用的情況，或可能推翻規則的因素。
- **預測分類：** `CORRECT_TRANSFER`／`CORRECT_BUT_CUED`／`MISCONCEPTION_FOUND`／`EVIDENCE_INSUFFICIENT`／`UNTESTED`／不適用。
- **熟練度影響：**`NO_CHANGE` 或精確的概念層級 L0-L4 變化及其理由。絕不自動推定領域層級熟練度。
- **下一個挑戰：**實質上最小但更難的真實變體。

不要追加例行狀態更新。不要捏造歷史預測或展現。

---

## 提升與重新評估規則

採用保守證據標準：

- **UNASSESSED -> L0/L1**：只有證據支持該精確分類時才可變更。
- **L0 -> L1**：發生有意義的真實接觸。
- **L1 -> L2**：James 能解釋關鍵區分，而不只是重複術語。
- **L2 -> L3**：正確應用於實質不同的真實案例，並解釋取捨。
- **L3 -> L4**：在被告知前，主動提出可信反證、隱藏失敗或適用缺口。

若反覆的新證據顯示心智模型不穩定，可以降級／重新評估。保留先前證據並記錄目前看法改變的原因；不要改寫歷史。

互相衝突的證據在審閱前應產生 `REASSESSMENT_REQUIRED`。不要採用最高分勝出或最後寫入勝出的規則。

---

## 並行／回寫規則

- 每次回寫前重新讀取目前 Ledger。
- 每個追加的學習事件都必須有穩定 event ID。
- 不得把重複 event ID 再追加成第二個事件。
- 若兩個 session 回報同一概念的衝突證據，兩者都保留並要求重新評估。
- 可以時，在同一個可審閱變更中追加已審閱證據並更新 Current Learning State。
- 有界 worker 可以產生工程證據，但除非 Owner 明確要求，不得獨立測驗或評分 James。
- 若目前 session 沒有此 Ledger 的寫入權限，將項目標記為 `PENDING_WRITEBACK`；不要宣稱已持久保存。
- 遠端寫入結果不明時，先 reconcile／讀回，再重試。
- 不要把 secrets、私人連結、完整私人對話逐字稿或不必要的個人資料放入此公開 artifact。

---

## 更新規則

- 不要複製 Nexus 的系統 failure-learning records。
- 一般 engineering task 最多記錄一項主要學習項目，除非 James 明確要求更深入的審查。
- 錯誤預測有用時予以保留；看見答案後不要改寫歷史。
- 若新證據與較早的學習結論矛盾，透明地追加／更新評估並說明原因。
- 相較泛泛說明，優先記錄完整 repository 身分與精確 Issue／PR／revision references。
- 相較改名後的重複案例，優先採用新的問題結構。
- 不要把每次工程互動都變成測驗；執行工作仍是首要事項。
- 本 Ledger 絕不授權實作、批准、整合、合併、發布、安全變更或生產宣稱。
- 儲存在 `Nexus-new` 是為了維持連續性的選擇，不是對其他 repositories 的工程權威。
