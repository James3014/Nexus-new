# 7R/8R 狀態治理與系統性硬化計劃 (Phase 1 ~ Phase 5)

本計劃為 7R Flash100 restart 後半段與 8R 治理階段的唯一真相來源 (SSOT Blueprint)。**主線目標不是再救 `pub-bug-004` 或做新框架，而是將其視為已 formal exclusion 的 blocker，接著把 7R/8R 後續需要的守門、證據鏈、重開條件與下一輪前置修補一次做完。** 執行 **blocked 狀態治理 + 下輪重跑前的系統性硬化**。

---

## 🎯 執行主旨

`pub-bug-004` 既然已被證明是 provider-token combine blocker，而且 standard / self-heal / longer-timeout replay 都無法同時滿足 model causality、delivery 與 provider-token measurement，就不要再把它當成可用既有路徑修好的 row。

後續計劃的完成定義收斂為四件事：
1. 維持 blocked verdict。
2. 補齊所有 fail-fast 守門。
3. 把下輪 public/combine 的前置條件寫成機器可驗證 contract。
4. 只在出現新 clean replay 證據時才允許 reopen。

---

## 🚀 5 大執行階段 (Phase 1 ~ Phase 5)

### 📂 Phase 1：封板與狀態同步
- **目標**: 把所有狀態文件、policy 文件、報告索引與 walkthrough 全部對齊，確保工程完工與 blocked 狀態一致。
- **統一用詞**: **「framework landed、`pub-bug-004` exclusion complete、live outcome blocked、no public claim unlock」**。
- **嚴防誤讀**: Chunk rollup PASS 僅是 execution-control 產物，絕不等於 public claim PASS。任何 delivery/cost/ledger gate 不 PASS 的 chunk 都不得合併為 public evidence。
- **實體交付物**:
  - `docs/reports/7R_8R_governance_status_matrix.md` (狀態總表，列出 blocked reason、closeout artifact、禁止事項與 reopen 條件)。

---

### 📂 Phase 2：把 fail-fast 守門一次補齊
- **目標**: 集中做「不浪費長跑成本」的守門硬化。direct baseline 遇到 repeated timeout、authfailed、quota 或 token outlier 時，若不早停，會直接污染分母並浪費比較預算。
- **守門四大核心開關與閘門**:
  1. **Direct-provider timeout abort**: `--direct-timeout-abort-threshold`
  2. **Direct infra abort**: `--direct-infra-abort-threshold`
  3. **Commercial model basis gate**: 拒絕 skill-fit / ablation matrix，必須要求編譯後的 commercial execution-safe manifest 與 matching disclosure manifest。
  4. **Execution-safe denominator gate**: Flash100 live 必須先滿足 100 selected 且 100 execution-safe，否則阻斷開跑。
- **Gemini Baseline 預設改動**:
  - direct Gemini baseline 維持 read-only model call 的 `approval-mode plan` 預設，避開 transport/tool-policy 雜訊混入。

---

### 📂 Phase 3：把成本與證據鏈分開修
- **目標**: 專門處理「route-cost 仍是 watchlist，但不能拿來越權解鎖 claim」這條線，防範 delivery-ready 誤讀為 public promotion-ready。
- **實作步驟**:
  1. 保留已建立的 route-policy evidence、expected capability evidence 與 public promotion readiness contract，不得因成本弱化。
  2. 將 route-cost RCA 嚴格限制在 bucket / lane 層，不得改動 public claim wording。
  3. 修復屬於「可審計成本」的問題（如 parseerror、stats outlier cumulative、telemetry cleanliness、ledger conservation），禁止將 local fallback 冒充為 model-cost evidence。
- **產出四張專用任務卡**:
  - `token cleanliness guard`
  - `wall-ledger integrity`
  - `route-cost bucket RCA`
  - `observation-only dashboard maintenance`

---

### 📂 Phase 4：下輪重開前置條件 (Contract-First)
- **目標**: 在下一次大跑前，完成 contract-first 的前置驗收，不准先跑再補文書。
- **五大前置驗證條件**:
  1. **Commercial basis manifest & disclosure manifest** 通過 preflight，且 diagnostic matrices 必被 commercial basis gate 拒絕。
  2. **Execution-safe denominator 達標**，不再混入 `repokindnexusinternal`、`reporefcurrent-worktree` 或缺 clone adapter 的 external rows。
  3. **Token cleanliness** 與 parse/token outlier stop rules 會在 chunk 階段即時阻斷 (如 chunk10 曾因 parseerror / stats outlier 阻斷)。
  4. **Expected capability receipts** 在 deterministic rescue 後正確補全 (必須回填 receipts)。
  5. **Route-policy evidence** 修正為只把真正 active 的 pre-model rescue 視為 active rescue evidence，不將 blocked-but-configured 誤算進 public gate。

---

### 📂 Phase 5：唯一允許的 reopen 流程
- **目標**: 排除口頭判定，將 reopen 條件寫成明確的 SOP。
- **唯一允許 Reopen 情況**:
  - 未來出現新的 row-level clean evidence，能同時證明：
    - `verified delivery`
    - `model-causal path`
    - `providertokenmeasured=true`
    - `route-policy evidence PASS`
    - `expected capability evidence PASS`
    - 能被 audited combine 接受。
  - **若不滿足，永久維持 `pub-bug-004` exclusion 與 7R blocked verdict。**
- **嚴格 Reopen 順序 (MANDATORY)**:
  - 必須走 `row-level targeted replay` ➔ `audited combine` ➔ `outcome decision` 三步，禁止從 chunk rollup 或 observation-only dashboard 倒推出 public claim eligibility。

---

## 🚫 禁止事項

- 不得把 route-stability PASS 說成 promotion-ready。
- 不得把 chunk rollup PASS 說成 public claim 完成。
- 不得把 token-normalized 或 local timeout fallback 的 row 說成 clean public cost evidence。
- 不得因為 row 能 deliver 就忽略 provider-token measurement 與 model causality 缺口。

---

## 📦 交付物清單

本輪 agent 執行後，至少要交付：
- live targeted replay artifacts
- row-level replay disposition report
- audited combine machine-readable artifact
- audited combine markdown report
- route-stability markdown report
- single outcome decision card
- blocker-specific closeout card（若非 Go）

---
*System Hardening Plan Created: 2026-05-29 (7R/8R End-to-End)*
