# Nexus 導覽包 v1（Context+ 思維版，Read-Only）

## 0) 一頁摘要（先建立心智模型）
Nexus 不是單一「任務執行器」，而是「治理先行」的協調作業系統：
- 入口層：`scripts/engine/nexus_cli.py`（命令面）
- 路由層：Capability Planner / Selector / Autonomic Router（決定要用哪些能力）
- 證據層：Capability Receipt Adapters + Runtime Receipts（證明有執行、有證據、有 gate）
- 安全層：Hallucination Guard + Delivery/Acceptance/Contract/CI gate（fail-closed）
- 執行層：Research Flow / Hyper / Swarm / Nightshift 等能力執行

理解 Nexus 的關鍵不是「看完全部檔案」，而是抓 4 條主鏈：
1) CLI 命令如何進入核心流程
2) 能力如何被選擇與約束
3) 證據如何被組裝為 receipt
4) gate 如何最終阻擋或放行

---

## 1) 15 個必讀檔（依優先順序）
1. `scripts/engine/nexus_cli.py`
2. `nexus/app/research_flow_service.py`
3. `nexus/engine/capability_contracts.py`
4. `nexus/engine/capability_planner.py`
5. `nexus/engine/capability_selector.py`
6. `nexus/engine/autonomic_routing_service.py`
7. `nexus/engine/capability_receipt_adapters.py`
8. `nexus/engine/runtime_capability_receipts.py`
9. `nexus/engine/capability_receipt_policy.py`
10. `nexus/governance/hallucination_guard.py`
11. `nexus/core/hallucination_guard.py`（facade）
12. `scripts/ops/_nexus_preflight.sh`
13. `scripts/ops/start_gemini_nexus_enforced.sh`
14. `scripts/ops/run_gemini_nexus_round.sh`
15. `scripts/ops/ci_gate.py`

---

## 2) 三條閱讀路線（避免迷路）

### 路線 A：治理與放行鏈（最重要）
目標：回答「什麼情況可宣稱完成？」
- 讀檔順序：
  1) `scripts/ops/_nexus_preflight.sh`
  2) `scripts/ops/start_gemini_nexus_enforced.sh`
  3) `scripts/ops/ci_gate.py`
  4) `nexus/governance/hallucination_guard.py`
  5) `nexus/engine/capability_receipt_policy.py`
- 你會得到：
  - 啟動前檢查、enforced runner、fail-closed gate、幻覺風險守門、receipt policy 的完整閉環。

### 路線 B：能力路由鏈（理解「為何選這些能力」）
目標：回答「任務如何被分配到 codeintel/research/hyper/swarm？」
- 讀檔順序：
  1) `nexus/engine/capability_contracts.py`
  2) `nexus/engine/capability_planner.py`
  3) `nexus/engine/capability_selector.py`
  4) `nexus/engine/autonomic_routing_service.py`
- 你會得到：
  - capability node（成本/效益/風險）
  - phase hook（S/P/X/D/R/A/C）
  - direct mode vs autonomic routing 的切換點。

### 路線 C：執行與可追溯鏈（理解「做了什麼、怎麼證明」）
目標：回答「執行結果如何落成證據？」
- 讀檔順序：
  1) `scripts/engine/nexus_cli.py`
  2) `nexus/app/research_flow_service.py`
  3) `nexus/engine/capability_receipt_adapters.py`
  4) `nexus/engine/runtime_capability_receipts.py`
  5) `scripts/ops/run_gemini_nexus_round.sh`
- 你會得到：
  - CLI 入口 -> 執行服務 -> receipt adapter 組裝 -> runtime evidence 寫出。

---

## 3) 你現在可直接問的 8 個高價值問題（用來快速掌握）
1. `nexus_cli.py` 中，`nexus` 子命令實際轉進哪個 service？
2. `capability_planner` 的 default nodes 哪些是 production/beta？
3. `capability_selector` 在什麼訊號下會升級到 swarm/nightshift？
4. `autonomic_routing_service` 何時會 bypass（direct mode）？
5. `capability_receipt_adapters` 對「selected但未invoked」如何 fail-closed？
6. `runtime_capability_receipts` 會落哪些 report 檔？
7. `hallucination_guard` 觸發最高風險的 pattern 是什麼？
8. `ci_gate.py` 哪幾個 step 失敗會直接阻擋 closeout？

---

## 4) 以 Context+ 工具使用時的呈現型式（你會看到什麼）
- `get_context_tree`：輸出「分層模組樹 + symbol line range」
- `get_file_skeleton`：輸出「函數/類別簽名地圖」
- `semantic_navigate`：輸出「語意群組（routing / governance / receipts / runners）」
- `get_blast_radius`：輸出「某 symbol 的影響半徑（檔案與行號）」

建議輸出格式（方便決策）：
- Topology Map（拓樸圖）
- Critical Path（治理關鍵路徑）
- Hotspots（高耦合高風險區）
- Next 5 Reads（下一步精讀清單）

---

## 5) 第一輪執行邊界（避免工具反客為主）
- 僅 read-only（不使用 propose_commit）
- 先看主鏈，不追測試檔細節
- 先把名詞對齊：capability / receipt / gate / claim / route
- 每輪只回答一個主問題，避免一次全覽造成噪音

---

## 6) 本版結論
Context+ 可以幫你「看懂 Nexus」：特別是快速定位核心鏈路與影響半徑。
但它不替代 Nexus 治理本身。最有效組合是：
- Context+：理解與導航
- Nexus：執行與驗收（fail-closed）
