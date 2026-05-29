# 7R Flash100 真實證據執行計劃 (SSOT Blueprint)

本計畫建立在目前已落地的 preflight、replay queue、audited combine、restart flow、split reports、closeout card 之上，為 **Task R ~ Task V** 的實證執行提供唯一真相來源 (SSOT)，以利 Agent 或工程師精準照表操課。

---

## 🎯 執行主旨

本階段目標不是再新增 orchestration，而是用現有工具對 **真實 7R blocker evidence** 做 live replay、evidence 重算、三分流決策與 blocker closeout。任何 row 若無法同時滿足 delivery、model causality、provider-token measurement、expected capability causality 與 public gate 邊界，就維持 fail-closed，不允許用局部 PASS、route-stability PASS、或 chunk PASS 替代最終 public outcome。

---

## 🚀 總體原則

- **只使用既有工具鏈**：`preflight_7r_restart.py`、`generate_replay_queue.py`、`run_7r_restart_flow.py`、`audited_combine_gate.py`，必要時再調用既有 runner 與 evidence bundle 生成路徑。
- **一切以 manifest-index / row-key 為準**：不允許回退成單純 `task_id` 粗粒度 replay，因為 frozen manifest 可能有 duplicate task IDs，row identity 與 task identity 不等價。
- **開啟 Abort 遙測閥值保護**：direct baseline 一律開啟 timeout / infra abort 門檻，因為 repeated provider timeout、auth、quota、gateway 類失敗會污染 paired denominator 與 comparison evidence。
- **報告物理分離與 MR Refs**：route-stability 報告與 audited combine 報告必須物理分離，且各自掛載 machine-readable evidence refs，單臂穩定性是 diagnostic evidence，不是 public promotion evidence。
- **Go 決策硬門檻**：Go 決策必須同時滿足五維 PASS 與 `expectedcapabilityevidencecontract=PASS`；沒有 expected capability causality，不得視為可 promotion。
- **分類明確與二出口**：若經 clean replay 後仍無法完成 token truth 或 receipt data-contract，應升格為 final blocker verdict，而不是永久 HOLD。

---

## 🔍 前置確認

### **目標**
確認目前 repo 與執行材料已滿足 live replay / combine 的最小條件，避免在錯誤狀態下直接開跑。

### **必要輸入**
- frozen manifest / execution-safe manifest
- `combine_blockers_rca.json`
- replay queue generator
- restart flow 與 combine gate
- 最新 split reports 與 closeout card 路徑

### **檢查項**
1. 確認目前分支與工作區乾淨，沒有未提交的核心 runner / contract / test 變更。
2. 確認 replay queue 已能產生 manifest-index filter，且 `pub-bug-004` 類 blocker 不會被誤納入 replayable queue。
3. 確認 preflight 會同時檢查：
   - selected denominator
   - execution-safe denominator
   - hidden verifier env
   - outbound prompt strict env
   - fail-fast row failure
   - direct timeout abort threshold
   - direct infra abort threshold
4. 確認 export / clean-runner 邊界已滿足；未經核准的 dirty workspace external run 應直接 fail-closed。

### **驗收**
- 所有前置檢查 PASS 才能進 Task R。
- 任一前置檢查失敗，直接停下並更新 `blocker_closeout_action.md`，不得硬跑 live。

---

## 🔧 Task R：Run live targeted replay

### **目標**
對當前 replay queue 中的 `replayable` rows 進行真實 live targeted replay，只處理最小 slice，並保留 fail-fast / fail-closed 邊界。

### **輸入**
- `combine_blockers_rca.json`
- `generate_replay_queue.py` 輸出的 manifest-index filter
- frozen / execution-safe manifest
- clean runner / approved export boundary
- env:
  - `NEXUS_VALUE_HIDDEN_VERIFIER=1`
  - `NEXUS_OUTBOUND_PROMPT_STRICT=1`
  - `NEXUSBENCHFAILFASTONROWFAILURE=1`
  - `NEXUS_DIRECT_TIMEOUT_ABORT_THRESHOLD=<approved value>`
  - `NEXUS_DIRECT_INFRA_ABORT_THRESHOLD=<approved value>`

### **執行步驟**
1. 用 replay queue 只選 `replayable` rows，順序固定：
   - `tokenless_timeout_fallback`
   - `stats_outlier_token`
   - 其他 replayable telemetry issues  
   `non_refillable_model_required` 不納入自動 replay。
2. 強制使用 `--manifest-index-filter` 或 row-key replay，不得僅用 `--task-id-filter`。
3. 以 live mode 執行最小 slice，並保留 row-level artifacts、with/without arm evidence、abort telemetry、provider token telemetry。
4. direct baseline 若觸發 repeated timeout 或 infra streak，立即 early abort，保留 partial evidence 並標記中止原因，不得繼續灌水 denominator。
5. 對每一列 replay row 生成 row-level disposition：
   - clean replay candidate
   - delivery-clean but cost-RETURN
   - direct-provider-abort
   - token-unmeasured
   - receipt-data-contract-failure
   - hard blocker candidate

### **驗收**
- 產出真實 replay artifacts。
- 每一列 replay row 都有明確 disposition，沒有任何 replay row 落在「模糊成功 / 模糊失敗」狀態。

### **失敗分流**
- 若 direct arm timeout / infra 連續觸發，停止 replay lane，記錄為 baseline transport blocker，而不是模型能力 blocker。
- 若 row delivery 成功但 tokens 未 measured，標為 cost / promotion 不可用，不得當作 clean public evidence。

---

## 🔧 Task S：Rebuild audited combine from live replay artifacts

### **目標**
把 live replay 產物與既有可接受 chunk / bundle 重新整合，建立真正的 audited combine 結果，而不是只依賴流程腳本的模擬結論。

### **輸入**
- live replay row artifacts
- 既有 accepted chunk bundles / evidence bundles
- audited combine gate
- expected capability evidence contract
- route-policy evidence contract
- promotion readiness contract

### **執行步驟**
1. 收集所有可納入 combine 的 chunk 與 replay rows，僅接受具備完整 artifact path 與 bundle refs 的輸入。
2. 重新計算五維：delivery, cost, ledger, token, promotion readiness。
3. 同步重算：
   - `expectedcapabilityevidencecontract`
   - provider token measured rates
   - outbound ledger gate
   - route policy evidence
   - source promotion / boundary eligibility（若適用）
4. 對 combine 內的每個 blocker 做最終分類：
   - replay fixed
   - cost RETURN only
   - observation-only
   - non-refillable blocker
   - excluded by policy
5. 生成新的 machine-readable combine artifact 與對應 markdown report，並將 artifact refs 寫入 durable report。

### **驗收**
- audited combine report 與 machine-readable artifact 一致。
- combine 結果可以明確回答：為何 Go、為何 Observation-only、或為何 Blocked。

### **禁止事項**
- 不得因為 chunk rollup PASS 就跳過 final audited combine。
- 不得把 route-stability PASS 直接轉寫成 promotion PASS。

---

## 🔧 Task T：Generate split reports

### **目標**
產出兩份嚴格分離的 durable reports，讓 agent、dashboard 與後續 closeout 都能讀到一致訊號。

### **報告一：Audited Combine Report**
必須包含：
- combine 所用 artifact / bundle refs
- 五維結果
- expected capability evidence 狀態
- provider-token measurement 狀態
- outbound ledger 狀態
- promotion readiness 結果
- remaining blockers 與 final verdict

### **報告二：Route Stability Report**
必須包含：
- rowcount / successcount / semantic verified
- trust clean
- model participation
- skill mount evidence
- token accounting stability
- 明確聲明「此報告不得用於 public claim / promotion 解鎖」

### **驗收**
- 兩份報告分離落盤，且都附 machine-readable artifact refs。
- 任何 agent 或 dashboard 閱讀報告時，不會把 diagnostic PASS 誤讀成 promotion PASS。

---

## 🔧 Task U：Outcome decision card

### **目標**
根據 live replay + audited combine + split reports 產生唯一的三分流結論。

### **出口 A：Go**
必須全部成立：
- delivery PASS
- cost PASS
- ledger PASS
- token PASS
- promotion readiness PASS
- expected capability evidence PASS (Causality 無缺口)
- non-refillable blockers = 0
- paired baseline evidence completeness 足夠

### **出口 B：Observation-only**
適用條件：
- delivery / trust / route-stability 基本乾淨
- 但 cost、token、provider boundary、promotion readiness 任一未達標
- 或仍需保持 public claim wording locked（不得解鎖宣稱）

### **出口 C：Blocked**
適用條件：
- 仍存在 hard blocker（如 `pub-bug-004` 型）
- 或 direct baseline completeness 不足
- 或 provider-token truth / receipt data contract 無法修復
- 或 combine 後仍 `claimallowed=false` / `promotionallowed=false` 且無明確 clean refill 路徑

### **驗收**
- outcome card 必須只有一個出口，不得同時敘述成多種成功。
- 所有出口都要列出對應證據與下一步卡片。

---

## 🔧 Task V：If blocked, open blocker-specific closeout only

### **目標**
若結果不是 Go，就不要回頭再做新 pipeline，而是開 row-local / blocker-local closeout。

### **closeout 類型**
1. **Provider-token truth closeout**：處理 tokenless fallback、stats outlier、provider token unmeasured。
2. **Receipt causality closeout**：處理 expected capability invocation / receipt-lite / data-contract gap。
3. **Direct baseline transport closeout**：處理 auth / quota / gateway / timeout streak，必要時 direct-only refill。
4. **Non-refillable exclusion decision**：對 `pub-bug-004` 類在多次 bounded replay 後仍不能同時滿足 delivery + model causality + provider-token measurement 的列，轉 final blocker verdict，不再 indefinite HOLD。

### **驗收**
- 每個 blocker 都有唯一 closeout path，不再出現 generic HOLD 或「之後再看看」的模糊狀態。

---

## 🏁 Agent 的具體執行順序與禁止事項

### **執行順序**
1. 檢查 repo / branch / worktree / export boundary 是否可 live run。
2. 重新生成 replay queue，確認 replayable rows 與 manifest-index filter。
3. 設定 abort seams 與 strict env，執行 live targeted replay。
4. 收集 replay artifacts，逐 row 產出 disposition。
5. 執行 audited combine，重算五維與 expected capability evidence。
6. 產出 split reports，附上 machine-readable refs。
7. 產出單一 outcome decision：Go / Observation-only / Blocked。
8. 若非 Go，立即生成 blocker-specific closeout 行動卡，不再新增 orchestration。

### **禁止事項**
- 不得把 chunk rollup PASS 說成 public claim 完成。
- 不得把 route-stability PASS 說成 promotion-ready。
- 不得把 token-normalized row 說成 clean public cost evidence；provider-measured reliable tokens 才能支持 clean cost / promotion。
- 不得用 `task_id` 取代 manifest-index replay，在 duplicate task IDs 存在時尤其禁止。
- 不得因 row delivery SUCCESS 就忽略 `expectedcapabilityevidencecontract`、receipt data-contract 或 provider-token cleanliness。
- 不得讓 hard blocker 永遠停在 HOLD；clean replay 後仍失敗者，必須升格 final blocker verdict。

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
*SSOT Blueprint Created: 2026-05-29 (7R Restart End-to-End)*
