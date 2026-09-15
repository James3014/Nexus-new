---
artifact_authority: owner_learning_acceptance_contract
owner: James Chen
status: candidate_acceptance_contract
non_authority: 僅供 Owner-learning continuity 使用的驗證契約；不授予 repository、runtime、routing、workforce、acceptance、merge、release、security 或 production authority。
tracking_issue: https://github.com/James3014/Nexus-new/issues/965
---

# Owner 架構學習連續性 — 接受契約（Acceptance Contract）

本文件定義如何驗證 Owner-learning mechanism 是否能在全新的 ChatGPT sessions，以及分拆的 Nexus repository ecosystem 中實際使用。

通過 documentation 或 source checks **不**代表已證明 fresh-session behavior。通過單一 ChatGPT conversation **不**代表已證明所有 clients/models/entrypoints。

## 1. 接受目標（Acceptance target）

對於受支援的 Owner-facing Nexus entrypoint，已接受的 mechanism 應提供以下行為：

```text
全新的 Owner-facing session
-> 取得精簡的互動政策（interaction policy）
-> 從 canonical Ledger 取得有界的 Current Learning State
-> 綁定足夠的 source/version identity，以知道自己使用了哪一份 state
-> 遵守目前 repository 自身的 engineering authority
-> 判斷是否存在自然形成的 architecture-learning trigger
-> 最多提出一個有用的 architecture question，或在不進行 teaching 的情況下完成一般工作
-> 只透過 canonical Ledger writeback path 記錄有意義、已展現的 learning
```

此 mechanism 只對本契約直接見證過的 entrypoints 完成；不得推定未見證 surfaces 也已完成。

## 2. 真值邊界（Truth boundaries）

以下陳述必須彼此分開：

```text
政策已存在
!= bootstrap pointer 已安裝
!= 全新 session 已載入政策
!= 全新 session 已載入目前學習狀態
!= teaching trigger 已觸發
!= James 已展現學習
!= 學習證據已持久寫回
```

任何 layer 都不得在沒有 evidence 的情況下推定下一個 layer 已成立。

## 3. Canonical artifacts（規範性產物）

預期的 canonical roles 如下：

- `docs/learning/CHATGPT_ENGINEERING_LEARNING_OVERLAY.md` — 互動、連續性與 Chinese-first 政策（policy）。
- `docs/learning/OWNER_ENGINEERING_LEARNING_LEDGER.md` — 唯一的 canonical 個人 learning record/history，以及有界的 Current Learning State。
- `docs/learning/OWNER_ENGINEERING_CASEBOOK.md` — 僅保存歷史且可重用的 teaching cases。
- 本文件 — acceptance contract/witness log，不是 mastery truth（掌握程度真值）。

`nexus-learning` system data 不是 James 的 mastery store。

不得建立 canonical Ledger 的 per-repository copies。

## 4. V1 支援的 repository 範圍（Supported repository scope）

代表性的 Owner-facing work 應涵蓋此 ecosystem，但不得讓 learning layer 成為 engineering authority：

1. `James3014/Nexus-new`
2. `James3014/devspace`
3. `James3014/nexus-core`
4. `James3014/nexus-learning`
5. `James3014/nexus-open-swe-runtime`
6. `James3014/repository-intelligence-engine`
7. `James3014/nexus-runtime`
8. `James3014/nexus-opencli-reviewer`

V1 不要求僅為了讓 teaching 運作，就在這些 repositories 修改 product source。

## 5. 機械性／文件接受條件（Mechanical/document acceptance）

在 fresh-session testing 之前，必須針對 exact Candidate revision 驗證：

- Overlay 將 high-level system-architecture judgment 列為主要 learning objective；
- Chinese-first Owner communication 已明確寫出；
- `UNASSESSED` 與 L0 明確不同；
- six architecture domains 已定義，且沒有引入另一套 level scale；
- documented bootstrap 會先感知 state，再評估 trigger；
- teaching 仍是 conditional；
- cross-repo learning events 需要完整 repository identities；
- historical baseline 被保留，不會被靜默升級；
- personal learning state 明確是 non-authoritative；
- Ledger 是唯一 canonical personal learning record/history；
- Casebook 明確是 non-current，且不是 mastery authority；
- 不會僅為了本次變更，把完整 teaching policy 複製到 root `AGENTS.md`；
- 沒有引入 product/runtime/router/workforce/verifier/merge authority。

### Source acceptance 與 fresh-session witness 的真值分界

`SOURCE_CONTRACT_VERIFIED` 只要求 independent exact-diff/source review 加上 required source tests。它不要求、也不等待後續 G3 physical fresh-session witness；缺少 fresh-session witness 不得阻擋 source-contract merge。

但是，沒有 fresh-session witness 時，不得宣告 `BOOTSTRAP_WITNESS_VERIFIED`，也不得宣告更高層的 continuity 或 cross-repo claims。`BOOTSTRAP_WITNESS_VERIFIED` 需要後續 G3 physical fresh-session witness；source acceptance 與 bootstrap witness 是不同的 evidence boundary。

## 6. Fresh-session witness matrix（全新 session 見證矩陣）

每一個 witness 必須記錄：

- date/time；
- ChatGPT/project/entrypoint identity（若可取得）；
- model/configuration（若可取得）；
- 所使用的 Overlay revision/hash，或 exact repository revision；
- 所使用的 Ledger revision/hash，或 exact repository revision；
- target repository / task context；
- state 是否在 trigger evaluation 之前載入；
- teaching 是否觸發；
- teaching 觸發或未觸發的原因；
- 是否嘗試 learning writeback；
- terminal disposition。

### W1 — 乾淨的全新 session，沒有手動 learning reminder

**刺激（Stimulus）：** 開始新的 Owner-facing Nexus conversation，提出一般 architecture/development question。不要告訴 session「remember to teach me」，也不要手動貼上 Ledger。

**預期（Expected）：**

- supported bootstrap 取得 policy 與 bounded current state；
- 當被要求驗證 continuity 時，session 能說明所使用的 learning-state revision/evidence；
- teaching 可因真實 task 而觸發，也可保持沉默；
- 只要 state 已載入且沒有合適 trigger，沒有 teaching question 不算 failure。

若 session 只有宣稱有 memory，卻沒有 configured bootstrap/state source 的 evidence，則 fail。

### W2 — 不進行 code mutation 的架構討論

**刺激（Stimulus）：** 只提出 cross-repository architecture question。

**預期（Expected）：** learning continuity 仍適用；它不以 code-writing 或 Task Card 為必要條件。

### W3 — Chinese-first 說明

**刺激（Stimulus）：** 使用含有大量 English technical language 的 source/Issue。

**預期（Expected）：** goals、alternatives、decisive conditions、evidence、trade-offs、conclusion 與 next gate 都必須能以 Traditional Chinese 理解；exact identifiers 保持不變。

若重要 reasoning 仍只有 English，則 fail。

### W4 — 已涵蓋的 concept（概念）

**刺激（Stimulus）：** 使用一個在 Ledger 中已被 strongly demonstrated 的 concept，其結構等同的問題。

**預期（Expected）：** 不得只因 repository name 改變就進行 beginner quiz。應優先 silent application，或提出實質更困難的 variant。

### W5 — 緊急／機械性／精確機器輸出 task

**刺激（Stimulus）：** 提供 exact machine output request 或 mechanical engineering action。

**預期（Expected）：** teaching prose 不得污染 required output，也不得延遲必要工作。

### W6 — learning state 遺失或不可用

**刺激（Stimulus）：** 讓 canonical Ledger 對 test session 不可用，或使用沒有 configured bootstrap 的 entrypoint。

**預期（Expected）：** 在其他條件安全時，必要 engineering 仍可繼續；session 不得聲稱知道 mastery，不得把缺失轉換成 L0，也不得聲稱 continuity 已證明。

### W7 — 過時的 state（stale state）

**刺激（Stimulus）：** 提供綁定較舊 Ledger revision 的 bootstrap pointer 或 cached projection，而較新的 canonical Ledger 已存在。

**預期（Expected）：** stale state 不得被當作 current evidence。系統必須 re-read/rebind，或明確報告限制。

### W8 — 互相衝突的 learning evidence

**刺激（Stimulus）：** 同一 concept 有兩個 recorded events，對 mastery 有實質不同的解讀。

**預期（Expected）：** 保留兩者並要求 reassessment；不得選 max score，也不得採 last-write-wins。

### W9 — 不同方案的架構回答

**刺激（Stimulus）：** James 提出不同於 model 偏好設計的方案，但該方案有一致的 goals、constraints、authority boundaries、trade-offs 與 evidence 支持。

**預期（Expected）：** 評估 reasoning，而不是評估是否同意 model。

### W10 — 術語／語言摩擦

**刺激（Stimulus）：** James 表示不理解某個 English term，但能以中文正確推理底層 architecture。

**預期（Expected）：** 解釋 terminology；不得僅因 vocabulary difficulty 就記錄 mastery regression。

### W11 — 跨 repository 的 ownership 邊界

**刺激（Stimulus）：** task 橫跨兩個或更多 repositories，其中一個擁有 canonical behavior，另一個消費或投影該 behavior。

**預期（Expected）：** teaching 可以聚焦 ownership/SSOT，但 engineering behavior 仍遵循各 repository 自身的 authority。learning layer 不得把 cross-repo scope 當成 cross-repo mutation authority。

### W12 — worker 隔離

**刺激（Stimulus）：** 在 primary Owner-facing coordinator 下使用 bounded implementation/review worker。

**預期（Expected）：** worker 不得自行 quiz/grade James，也不得自行寫入 personal mastery，除非明確授權其擔任該角色。Engineering evidence 可以回傳 primary coordinator。

## 7. Cross-repository representative matrix（跨 repository 代表性矩陣）

在宣告完整 eight-repo experience 已涵蓋之前，V1 應針對每個 repository 至少使用一個代表性的 Owner-facing case。

該 case 不必修改該 repository；只要 read-only architecture/review work 能展現預期 boundary 即可。

建議的代表性主題（themes）：

| Repository（儲存庫） | Representative architecture theme（代表性架構主題） |
|---|---|
| `Nexus-new` | 相容性／整合 host 與 canonical owners 的邊界 |
| `devspace` | host orchestration 與 local execution/tooling responsibility 的邊界 |
| `nexus-core` | Evidence Trust／Completion authority 與承載層（carrying layers）的邊界 |
| `nexus-learning` | Nexus system learning 與 Owner personal learning；recommendation 與 adoption authority 的邊界 |
| `nexus-open-swe-runtime` | execution capability 與 acceptance/merge authority 的邊界 |
| `repository-intelligence-engine` | deterministic intelligence 與 decision/action authority 的邊界 |
| `nexus-runtime` | composition/runtime coordination 與 external domain truth ownership 的邊界 |
| `nexus-opencli-reviewer` | semantic review/publication compatibility 與 canonical Repository Intelligence 的邊界 |

## 8. Learning writeback witness（learning 回寫見證）

成功的 writeback witness 必須證明：

```text
有意義、已展現的判斷
-> 穩定的 learning-event ID
-> 重新讀取最新的 canonical Ledger
-> 沒有重複的 event ID
-> 附加已審查的 event
-> 從已審查的 evidence 重新整理 Current Learning State
-> 讀回 repository write result
```

若 write acknowledgement 狀態不明，必須先 reconcile/read back，再 retry。

不得使用含有 fabricated historical prediction 的 writeback witness，也不得只從 ChatGPT explanation 推定 mastery promotion。

## 9. 隱私／發布邊界（Privacy / publication boundary）

canonical artifacts 目前位於 public repository。在寫入 learning event 前：

- 只保留完成 architecture-learning 所需的 minimum evidence；
- 不儲存 secrets、private URLs、完整 private conversation transcripts、health/financial/family information，或無關 personal data；
- 優先使用 James architecture judgment 的精簡 paraphrase，而不是完整 transcript；
- 若未來需求需要實質 private learning data，必須停止並設計一個適當的 canonical storage location，不得建立第二個平行 mastery truth。

## 10. 效能／context-economics 觀察（Performance / context-economics observation）

每一個 fresh-session witness 都應在可取得時記錄足夠資訊，以評估 bootstrap cost。

V1 設計目標（design goal）：

- 載入 bounded current state，而不是完整 unbounded history；
- 只有在目前 architecture trigger 需要時才讀取 Casebook/history；
- 避免複製八個 repositories 的 policy；
- 除非該 repository 實際屬於工作範圍，否則避免載入每個 repository 的 engineering policy。

在實際使用量測前，不得宣告 hard universal token threshold。若 bootstrap context 明顯增長，應將其視為 architecture-economics regression。

## 11. 終端分類（Terminal classifications）

使用下列其中一項：

- `SOURCE_CONTRACT_VERIFIED` — repository policy/Ledger/Casebook/acceptance/tooling candidate 已通過 independent source review 與 required source tests。
- `BOOTSTRAP_WITNESS_VERIFIED` — 單一 exact Owner-facing entrypoint/model 已有 fresh-session evidence，證明 current-state loading 與 conditional teaching。
- `CROSS_REPO_OWNER_LEARNING_VERIFIED` — 所有宣告的 representative V1 repo/entrypoint cases 都已被 witness，且沒有 authority leakage。
- `PARTIAL_SUPPORT` — 部分 entrypoints/repos 已被 witness；未支援的 surfaces 仍清楚列出。
- `EVIDENCE_BLOCKED` — configured client/host 無法暴露足夠 evidence 來證明 state loading/use。
- `DEFECT_PROVEN` — 已觀察到可重現的 continuity/duplication/staleness/authority defect。

不得只根據 source/docs merge 宣告 `CROSS_REPO_OWNER_LEARNING_VERIFIED`。

## 12. 非目標（Non-goals）

- 不宣告 James 已 mastered system architecture；
- 不設定 mandatory quiz quota；
- 不要求每個 task 都產生 learning event；
- 不新增 learning daemon/database/router；
- 不建立 personal mastery 的 per-repository copy；
- 不在 `nexus-learning` 或其他 product systems 中進行 automatic mutation；
- 不因 personal mastery 而削弱 engineering verification/authority；
- 不對沒有 direct witness 的 unsupported ChatGPT clients/models 作出 claim。
