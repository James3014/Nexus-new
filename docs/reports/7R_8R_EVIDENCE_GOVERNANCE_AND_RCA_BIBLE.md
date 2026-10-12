# 7R/8R 證據治理與單點 RCA 聖經 (SSOT Governance Bible)

本報告物理記錄了 7R/8R 專案中關於「為什麼現在還卡住」、「接下來要做什麼」與「實際上最合理的下一步」的實證深度閉環文獻，做為後續除障、帳務硬化與 exclusion 決策的唯一物理知識橋樑 (SSOT Context Bridge)。

---

## 🔍 一、 為什麼現在還卡住？

目前最大的卡點是 **token / cost evidence cleanliness**，而非單純 delivery 成不成功。

### 1. **pub-bug-004 的本質阻塞**
- *歷史遙測事實*: with-Nexus delivery 成功過，但 `providertokenmeasured=false`。
- *Bounded Replay 失敗切換*: 
  - 要嘛是 `modelrequiredlocaldeliveryblocked` (破壞隱藏 integration checkpoint)
  - 要嘛是 `modelcallwithouttokens` (無法捕捉 provider tokens)
- *結論*: 該 row 雖然「做對了」，卻不能進 audited combine bundle，也就不能支撐 public cost / promotion。

### 2. **Chunk Rollup PASS 不等價於 Public Claim**
- *事實*: chunk rollup 到 100/100 paired rows 不代表能 claim。
- *原因*: chunk rollup 僅是 continuation/completion artifact。最後仍必須通過單一 audited combine bundle，重新計算五維度（delivery、cost、ledger、token、promotion gates）。
- * fail-closed 鐵律*: 只要某個 chunk 的 public cost gate 不 PASS，整體就必須 100% 維持 fail-closed。

---

## 🚀 二、 接下來要做什麼？

接下來不是無限制重跑，而是照既有 follow-up card 與 fail-closed 流程走。

### 1. **執行 7R 的 claim separation**
- 不得把 partial delivery / partial cost / partial skill-fit 混成 public promotion claim。
- 正式生成 7R claim separation report，並明確把 8R 維持 blocked。

### 2. **對 token / cost blocker 做 targeted replay**
- 絕不整包重跑。
- `hard-neutral-bug-001` 要求用更長 gateway timeout replay。
- `pub-bug-004` 已做 bounded replay，目前仍未得到可 audited 的 clean path，故對其發布 exclusion 決策。

### 3. **對 chunked 結果做 audited combine**
- 不得看 rollup PASS 就往前。
- combine hook 會物理性拒收任何 delivery / public cost / outbound ledger 不 PASS 的 chunk。

### 4. **對 token cleanliness 做 RCA 或 exclusion**
- `chunk10` 因 `parseerror` 與 `stats-outlier token evidence` 必須先停，再做 targeted replay 或 exclusion，不能硬續跑。

### 5. **走 costphase / redesign 策略**
- 若某些 lane 持續低效，改走 costphase / redesign，而不是繼續燒 Flash。
- `governance / research` 已經加了 `costphase contract`：當 `effective rows` 為零時，強制導向 `candidatetaskset redesign`，而不是執行更多 live reruns。

---

## 🎯 三、 實際上最合理的下一步

近期的實體執行與硬化順序必須遵循以下鋼領：

1. **先清掉 7R 的 token/accounting blocker，再談 8R**：
   - 先把 `pub-bug-004` 這類 model-required 但 token 不乾淨的 row 處理到「要嘛 clean replay、要嘛明確排除且不污染 denominator」，再用 audited combine 重建單一 bundle。
   - 只有當 delivery、cost、ledger、token 都能在同一個 combine bundle 內閉合時，8R 才有資格解鎖。
2. **Skill-Fit 路線的 targeted replay 或 redesign**：
   - `governance / research` 仍要繼續 targeted replay 或 `taskset/candidate redesign`。
   - 沒有 receipt-backed 的 Alternate/Default skill verdict，Flash100 與 Pro18 都不該開！

---
## 🏁 終極結語 (SSOT Conclusion)

> **路由是用來省成本又守證據邊界的；現在後續不是「再跑一次」，而是先把 route-cost 證據鏈補齊，尤其是 token/accounting 與 combine bundle，之後才輪得到 8R。**

---
*Bible Created: 2026-05-29 (7R/8R Evidence Governance Bible)*
