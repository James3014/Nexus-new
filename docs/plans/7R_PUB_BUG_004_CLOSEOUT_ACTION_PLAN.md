# 7R pub-bug-004 Closeout 實體行動卡計劃 (Phase A ~ D)

**接下來不要再做新的 framework、plan、orchestration。主線只剩一件事：把 `pub-bug-004` 這個 P0 blocker 做完 closeout，然後依結果決定是正式 exclusion，還是真的找到可重開 combine 的 clean replay。**

---

## 🏁 當前真實定位與狀態

- 路由/成本優化框架已經做了很多，也已經把 replay、combine、split reports、decision flow 都物理落地並提交。
- 但 final public-ready 結論仍被 `pub-bug-004` 卡住，因為它在 bounded replay 中始終無法同時滿足「model-required causality + successful delivery + provider-token measured」。
- 後續工作的唯一正確方向是：**單點 closeout 這個 P0 阻塞源，讓證據自己決定是 Go、Obs-only 還是 Blocked。**

---

## 🚀 4 大執行階段 (Phase A ~ Phase D)

### 📂 Phase A：凍結現況，停止框架變更
- **目標**: 把目前已經完成的 framework 視為封板，不再新增 orchestration 或改 decision layer，避免問題越修越大。
- **限制事項**:
  - 不再新增任何 restart flow、report splitter、combine wrapper、dashboard hook。
  - 所有後續 commit 只允許落在：`pub-bug-004` row-level RCA、targeted replay / bounded probe、direct-only refill 驗算與 exclusion verdict 產出。
- **驗收**: 之後所有工作項都能對應到 `pub-bug-004 closeout`，而不是泛化成 route-cost 大改。

---

### 📂 Phase B：做 pub-bug-004 的 row-level 證據總表
- **目標**: 把 `pub-bug-004` 的所有歷史 replay 與當前狀態整理成一張單點證據矩陣，先把「到底失敗在哪」寫死。
- **實體交付物**:
  - `docs/reports/7R_pub_bug_004_evidence_matrix.md`
  - 對應 machine-readable JSON 一份
- **矩陣欄位規範**:
  - `Replay variant`: standard / self-heal / longer-timeout / 其他已跑變體
  - `Winner source`: llm / local / timeout fallback / blocked
  - `Model calls`: 是否真的有 model call
  - `Provider tokens measured`: true / false
  - `Delivery status`: verified / blocked / partial
  - `Infrainvalid reason`: modelcallwithouttokens / modelrequiredlocaldeliveryblocked / 其他
  - `Route policy evidence`: 是否完整
  - `Expected capability evidence`: 是否完整
  - `Can enter audited combine?`: yes / no
- **執行步驟**:
  1. 收集 standard replay、self-heal replay 與 longer-timeout replay 證據。
  2. 填充每種 replay 的 row 結果進入矩陣，明確標出各類不合格切換狀態。
  3. 報告尾端寫入實體判定: `currently_non_refillable=true/false` 及 `combine_eligible=true/false`。
- **驗收**: 只看這張表，就知道為何它卡住 combine。

---

### 📂 Phase C：尋找「第四條 clean replay 路徑」
- **目標**: 有紀律地檢查是否存在新的 clean path。如果沒有，就要停止幻想，正式 closeout。
- **只允許檢查的 4 種候選路徑 (不得發散)**:
  1. **Direct-only accounting repair path**: 檢查是否能用 row-keyed refill 補完整 telemetry，而不改變 solver 語意。
  2. **Longer timeout but still model-causal path**: 驗證是否存在更長 timeout 下，能同時滿足 verified delivery + model-required source + provider-token measured true。
  3. **Route-policy classification issue**: 檢查是否其實走對了路，但被 telemetry 誤判為 active rescue / invalid source。
  4. **Provider variance only, not logic failure**: 若 row 邏輯與 delivery 都乾淨，只差 capture 邊界，則方可進行 accounting-only refill。
- **物理禁令 (MANDATORY)**:
  - 不得因為 row 能 deliver 就當作已解。
  - 不得用 local timeout fallback 充當 clean model evidence。
  - 不得降低 cost gate 或 provider-token gate 來遷就這列。
  - 不得再開新 orchestration 來包裝問題。
- **實體交付物**:
  - `docs/reports/7R_pub_bug_004_clean_path_decision.md`
- **驗收**: 結論只能是 `clean_path_found` 或 `exclusion_recommended` 二選一。

---

### 📂 Phase D：正式 closeout 或重開 combine
本階段只能二選一，不允許模糊地停在中間。

#### **路線 1：若找到 clean replay path (Go)**
1. 只 replay `pub-bug-004` 這一列，不重跑整包。
2. 用 manifest-index / row-key 精準定位，不准退回 task-id filter。
3. 產出新的 row artifact，確認 delivery, model causality, provider-token measured, route-policy evidence, expected capability evidence 全部 PASS 成立。
4. 將這列併入 audited combine，重算五維，更新 report。
- **驗收**: combine 後全綠，才有資格將 Blocked 狀態改為可前進狀態。

#### **路線 2：若找不到 clean replay path (Blocked)**
1. 正式將 `pub-bug-004` 標記為: `non_refillable` / `combine_blocker` / `promotion_blocker` / `8R_blocked_reason`。
2. 生成 durable artifact 交付物:
   - `docs/reports/7R_pub_bug_004_exclusion_verdict.md`
3. 在 `blocker_closeout_action.md` 中把後續收斂寫死：不再 replay、不再嘗試解鎖 7R。
4. 更新 walkthrough / SSOT 狀態為: **「framework landed, live outcome blocked, closeout complete, no public claim unlock」**。
- **驗收**: Blocked 狀態有正式依據，排除反覆測試與 indefinite HOLD 的灰色狀態。

---

## 🏁 明天第一張執行卡 (The Next Card)

### **「pub-bug-004 Closeout Card：建立 row-level evidence matrix，判定是否存在第四條 clean replay path；若否，生成 exclusion verdict。」**

---
*Blueprint Created: 2026-05-29 (7R P0 Blocker Single-Point Closeout)*
