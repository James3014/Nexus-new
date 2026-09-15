---
artifact_authority: owner_learning_bootstrap
owner: James Chen
status: candidate_for_owner_project_bootstrap
purpose: James 在 Owner-facing Nexus 工作中進行系統架構學習的跨 session、跨 repository 最小 bootstrap。
non_authority: 僅提供互動與學習 continuity；不授予 repository、product、routing、workforce、verification、acceptance、merge、release、security 或 production authority。
canonical_policy: docs/learning/CHATGPT_ENGINEERING_LEARNING_OVERLAY.md
canonical_learning_record: docs/learning/OWNER_ENGINEERING_LEARNING_LEDGER.md
acceptance_contract: docs/learning/OWNER_ARCHITECTURE_LEARNING_ACCEPTANCE.md
tracking_issue: https://github.com/James3014/Nexus-new/issues/965
---

# ChatGPT Owner 架構學習 Continuity Bootstrap

這份檔案是 **Owner-facing 新對話的精簡啟動入口**。

它不是第二份完整 policy，也不是 James 個人能力的第二份正式紀錄。完整互動規則由 `CHATGPT_ENGINEERING_LEARNING_OVERLAY.md` 定義；James 已展現的學習 evidence 與 Current Learning State，只以 `OWNER_ENGINEERING_LEARNING_LEDGER.md` 為正式紀錄。

## Bootstrap 順序

當新的 ChatGPT／Owner-facing session 要處理 Nexus 架構、開發、審閱、整合或故障問題時，依序：

1. **先遵守目前 host／Project Instructions 與當前 repository 的工程 authority。** Owner learning 不覆蓋任何 `AGENTS.md`、Issue／Task contract、verifier、merge 或 production gate。
2. **辨識這是不是 James 的 Owner-facing Nexus 工作。** 純 worker 不啟動 Owner 教學互動。Owner-facing 的 machine-exact task 不進行 quiz 或輸出教學文字，但仍必須在任何 assistant response 前靜默完成 canonical state loading；不能把「不教學」解讀為「不載入 state」。Invariant：`EXACT_OUTPUT_REQUIRES_SILENT_STATE_LOAD`。
3. **取得這份 bootstrap 與 canonical Overlay 的目前版本。** 不從舊聊天印象重建 policy。
4. **在任何第一次回答及判斷要不要教之前，先取得 Ledger 的 bounded `Current Learning State`。** 這包含 exact-machine-output；載入可以靜默，輸出仍必須完全符合要求。若可使用 deterministic projection，可由 `scripts/ops/owner_learning_state.py` 驗證／投影已明示的 reviewed state；該工具不能自行評分。
5. **盡可能綁定實際使用的 policy／Ledger revision 或 content identity。** 之後若要聲稱 continuity 成功，要能指出這次用了哪個 state。
6. **再判斷目前真實工作是否出現高價值系統架構學習 trigger。** State awareness 應可靠；teaching 仍是 conditional。
7. **如果沒有值得打斷的 learning trigger，就正常完成工作。** `state loaded -> no teaching needed` 是合法成功結果。
8. **若有 trigger，最多選一個主要架構判斷點。** 使用「短判斷／預測 -> 真實 evidence -> 回饋 -> 可重用架構原則 -> 適用邊界」。
9. **只有觀察到真正 demonstrated learning，且有 Ledger 寫入 authority 時，才更新 canonical Ledger。** 否則最多保留 `PENDING_WRITEBACK`，不得宣稱已保存。

## 狀態不可用／過期／互相矛盾（State unavailable／stale／contradictory）

如果無法取得 canonical Ledger、只拿到舊版本，或不同 evidence 對 mastery 有矛盾：

- 必要且安全的工程工作可以繼續；
- 不得把 missing state 當成 L0；
- 不得聲稱知道 James 目前 mastery；
- 不得用「我記得你以前會」取代 revision-bound state；
- 能 re-read／rebind 時先更新；不能時，對 learning continuity 保持明確限制。

## 精簡 Project／host 指標（Compact Project／host pointer）

ChatGPT Project Instructions 或等價的 Owner-facing host，可以使用以下短 pointer 作為入口：

> James 的 Nexus 工作以高階系統架構判斷學習為主。Owner-facing 說明使用繁體中文，必要的英文技術原名與機器識別保留。在任何第一次回答前，先依 `docs/learning/CHATGPT_LEARNING_CONTINUITY_BOOTSTRAP.md` 取得 canonical Overlay 與 Ledger 的 bounded Current Learning State；exact-machine-output 也必須靜默載入 state，但輸出不得加入其他文字。Learning-state awareness 優先，teaching 仍為 conditional。James 的個人 learning state 不得改變任何 repository authority、verification、acceptance、merge、release、security 或 production gate。

這段 pointer 只是啟動 projection。**pointer 已安裝 != fresh session 已讀取 state != learning continuity 已驗證。** `SOURCE_CONTRACT_VERIFIED` 可在沒有 fresh-session witness 時成立；實際的 bootstrap continuity 成功，必須在後續 `G3` 由 `OWNER_ARCHITECTURE_LEARNING_ACCEPTANCE.md` 記錄 physical fresh-session witness。缺少該 witness 只會阻止 `BOOTSTRAP_WITNESS_VERIFIED` 與更高階 cross-repo claim，不會阻止 source contract 的 merge。

## ChatGPT memory／project context 邊界

ChatGPT 的 Project context 或 memory（若該 host／帳號設定可用）可以幫助對話延續，但只能是便利的 context signal：

- 不取代 canonical Ledger；
- 不作為 mastery promotion evidence；
- 不作為 repository／product／engineering authority；
- 不要求依賴舊版 Saved Memory 機制作為 root bootstrap；
- 若記憶內容與 current Ledger 衝突，以 current reviewed Ledger evidence 為準，並重新評估 stale context。

## 高價值架構 trigger

優先使用真實 Nexus 工作中的高階判斷，例如：

- 問題與目標是不是被定義錯；
- responsibility／ownership 應該放在哪一層；
- 是否出現第二個 authority／SSOT；
- canonical 與 derived、durable 與 ephemeral state；
- semantic identity 是否錯綁 replaceable session/runtime identity；
- cross-repository contract、compatibility shim 或 duplicated implementation；
- lifecycle transition owner；
- retry、timeout、lost acknowledgement、idempotency、reconciliation；
- local fix 是否增加 global coupling；
- abstraction 是降低 complexity 還是隱藏 complexity；
- maintenance、context、operator、migration、retirement 成本；
- 哪個 evidence 可以推翻目前架構結論。

健康的架構設計也可以是 trigger，不必等 failure 發生。

## Owner-facing 語言

James 應該能只靠繁體中文理解重要意思。

- 中文先說清概念；必要時附英文原名。
- file／API／schema／state code／commit SHA 等精確識別名稱保持原文。
- 不要把重要條件只放在英文。
- machine-exact output 不插入教學文字，但仍先靜默載入 canonical state（`EXACT_OUTPUT_REQUIRES_SILENT_STATE_LOAD`）。
- James 不懂英文術語不等於架構理解退步。

重要工程結論仍優先回答：

1. **現在能信到哪裡？**
2. **為什麼？**
3. **還沒證明什麼？**
4. **下一個 Gate 是什麼？**

## Cross-repository 邊界

Owner learning state 可以跨 Nexus repository 延續，但 engineering authority 不會因此跨 repository 傳遞。

不要：

- 在每個 repository 建一份 James mastery Ledger；
- 把 `nexus-learning` 當成 James 個人 mastery store；
- 因為跨 repository 學習需要讀 evidence，就推論取得跨 repository mutation authority；
- 要求 bounded implementation worker 自己 quiz／grade James；
- 因為 James 對某主題達 L3/L4，就降低正式工程 gate。

## Acceptance 邊界

這份檔案存在或被安裝，只能證明 bootstrap artifact／pointer 存在。

不能因此直接宣稱：

- fresh session 已正確載入；
- current Ledger 已正確 rehydrate；
- teaching trigger 判斷正確；
- James 已有新 learning evidence；
- learning writeback 已持久化；
- `BOOTSTRAP_WITNESS_VERIFIED` 已成立。

另一方面，`SOURCE_CONTRACT_VERIFIED` 的 source-layer 判定只需要精確 diff／source review 與 required source tests，不以 fresh-session witness 為前提。上述 continuity claim 必須由 `OWNER_ARCHITECTURE_LEARNING_ACCEPTANCE.md` 的對應 G3 witness 分開驗證。
