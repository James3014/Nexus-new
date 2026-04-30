# Nexus 能力整合計劃（DDTree + Autoreason + Ultra Review + 新動態路由）

版本: v1.0
日期: 2026-04-28
目標 repo: /Users/jameschen/Workspace/nexus
分支基準: nightshift-1777081808（請實作前再以 git rev-parse 驗證）

## 0) 計劃目的（給 agent 討論用）

本計劃要把兩個新能力納入現有 Nexus：
1) DDTree（推理/解碼加速層）
2) Autoreason（三候選 + 盲評 + 收斂停手）

同時把 Ultra Review 明確納入治理路由，形成「生成能力 + 驗證能力 + 動態路由」的可解釋編排。

---

## 1) 現況 Reality Check（避免重工）

### A. 已有能力（可沿用）
1. 既有 phase 化流程與插件映射
   - P/X/D/C 映射已在 pipeline adapter 中
   - 證據: nexus/engine/pipeline.py:113-119, 168-183

2. X 階段已具研究路由與 explain payload
   - baseline vs hyper_sprint 已可決策
   - 風險、信心、歷史命中、共識票數已輸出
   - 證據: nexus/app/research_flow_service.py:230-337

3. nightshift 執行器已存在（可做高風險執行模式）
   - 證據: nexus/app/nightshift_runner_service.py:55-113

4. Ultra Review 能力已存在（dry-run gate）
   - 三 lane: security_sentry / logic_breaker / ghost_regression
   - gate_passed 與報告產出結構完整
   - 證據: nexus/engine/ultra_review_service.py:12-15, 42-53, 96-107

5. Ultra gate fail-closed 驗證器已存在
   - schema/欄位/三 lane/verified finding 都可阻斷
   - 證據: scripts/ops/ultra_gate.py:10-27, 39-57, 95-103, 109-119

6. CLI 入口已存在
   - `nexus ultra-review` 命令可用
   - 證據: scripts/engine/nexus_cli.py:1711-1731

### B. 部分已有（需補齊）
1. 研究路由有，但尚未原生支援「autoreason」與「ddtree」作為 first-class flow
   - 目前 winner 主要是 baseline/hyper_sprint
   - 證據: nexus/app/research_flow_service.py:250-253, 328-336

2. pipeline 具 phase/plugin 架構，但尚未見 Autoreason phase-skill 綁定與統一執行協定
   - 證據: nexus/engine/pipeline.py:207-208（phase_decisions / phase_skills 欄位已預留）

3. Ultra Review 目前為 CLI/報告能力，未確認為 pipeline 內建強制 gate
   - 證據: search in nexus/* 僅見 ultra_review_service 實作，未見明確 pipeline 自動掛載點

### C. 未有（需新開發）
1. Autoreason 核心流程（A/B/AB、blind judge panel、Borda、A 連勝停手）
2. DDTree 加速適配層（僅在特定 flow 啟用）
3. 新動態路由：在同一任務中可疊加能力（非單選模式）
4. 路由 explainability：輸出「為何啟用 autoreason / ddtree / ultra」的結構化理由

---

## 2) 能力定位（討論共識版）

1) Autoreason
- 類型: 生成/改進能力（R-phase 子策略）
- 作用: 在高不確定、非線性修復任務中提升品質與穩定收斂
- 不應全域常開；由風險與信心路由啟用

2) DDTree
- 類型: 加速能力（execution accelerator）
- 作用: 降低候選生成與評估延遲，提升吞吐
- 與 Autoreason/Hyper/Nightshift 可疊加，不互斥

3) Ultra Review
- 類型: 治理/驗證能力（A/C gate）
- 作用: fail-closed 阻斷高風險回歸、安全洞、不可重現結論
- 對寫碼是「可信度放大器」，不是主生成器

---

## 3) 新動態路由規劃（可疊加、可解釋）

## 3.1 Router 輸出 contract（新增）
在現有 route payload 基礎上新增：
- selected_capabilities: ["baseline"|"hyper_sprint"|"autoreason", ...]
- acceleration_layers: ["ddtree"] 或 []
- governance_layers: ["ultra_review"] 或 []
- explain_caps: [{capability, enabled:boolean, reasons:[...], evidence:[...]}]
- stop_policy: {type:"a_streak"|"budget"|"plateau", threshold:int/float}

## 3.2 啟用規則（第一版）
1. Autoreason 啟用條件（任一達成）
- route_recommended_flow == hyper_sprint
- adjusted_root_cause_confidence < 0.75
- findings_hits > 0 或 memory_hits > 0
- cross_module / hard keyword 任務

2. DDTree 啟用條件（任一達成）
- Autoreason 啟用且 candidate_count >= 3
- task 為高 token / 多輪評審任務
- 估算 round budget 超過基準門檻

3. Ultra Review 啟用條件（強制 gate）
- 變更觸及 engine/orchestrator/research/security
- cross-module 或 high/critical risk_score
- 發版前/合併前（可由 CI 或 closeout 強制）

## 3.3 路由模式（非單選）
- 簡單修正：baseline + (optional ultra_review)
- 中高風險：hyper_sprint + ultra_review
- 高不確定高成本：autoreason + ddtree + ultra_review

---

## 4) 實作分期（P0/P1/P2）

## P0（先打通最小可用）
1. 在 research route 輸出新增 capability stack 欄位
2. 定義 AutoreasonRunner（先本地 mock judge + Borda）
3. 將 Ultra Review 納入標準 closeout gate（至少 CLI/CI 一條路）
4. 增加 route explain 輸出到報告

驗收:
- 同任務可同時看到 selected_capabilities + governance_layers
- 產生可機器判定的路由決策證據

## P1（能力實體化）
1. Autoreason 正式化
   - A/B/AB 候選生產
   - blind judge panel
   - Borda 聚合
   - A 連勝停手策略
2. DDTree Adapter
   - 先做抽象介面與 feature flag
   - 僅在 autoreason/hyper 指定段落啟用
3. Ultra Review 與 Autoreason 結果接軌
   - 結果必須經 ultra_gate 才可 promote

驗收:
- 針對同一測試集，至少輸出 baseline vs autoreason 對照報告
- 報告含成本（token/time）與品質差

## P2（策略優化與收斂控制）
1. 動態 stop policy（A-streak + plateau + budget）
2. DDTree 啟用門檻自動調節（按任務長度/成本）
3. 路由回寫學習（下次任務可引用歷史成效）

驗收:
- 路由可說明「為何這次要/不要開 autoreason、ddtree、ultra」
- 回歸任務中，錯誤升級與誤報率下降（以內部指標追蹤）

---

## 5) 建議檔案改動點（給實作 agent）

1. 路由層
- Modify: nexus/app/research_flow_service.py
  - 擴充回傳 payload（selected_capabilities / governance_layers / explain_caps）

2. Pipeline context 層
- Modify: nexus/engine/pipeline.py
  - 將新路由欄位持久化到 state.metadata

3. 新能力執行器
- Create: nexus/engine/autoreason_service.py
- Create: nexus/engine/ddtree_adapter.py

4. 治理 gate 串接
- Modify: scripts/engine/nexus_cli.py
  - 在研究/修復 closeout 末端接入 ultra-review + ultra_gate
- Modify/Add: scripts/ops/* (若需 CI 集成)

5. 測試
- Create: tests/engine/test_autoreason_service.py
- Create: tests/engine/test_ddtree_adapter.py
- Modify: tests/ops/test_ultra_gate.py（補整合情境）
- Modify/Add: tests/app/*（route payload contract 測試）

---

## 6) 風險與治理

1. 成本風險
- Autoreason 多輪 + 多 judge，成本高於 baseline
- 緩解: 僅在高不確定場景啟用；加入 budget stop

2. 速度風險
- 引入 Ultra Review 會增加時間
- 緩解: 依變更範圍啟用 lane；保留 fast path

3. 可靠性風險
- 若 judge 噪音過高，收斂不穩
- 緩解: 最低 judge 數、tie-break 規則、A-streak + plateau 雙停手

---

## 7) Source Index（來源清單，供討論核對）

A. Nexus 現況代碼
1. pipeline phase/plugin 與 context
- /Users/jameschen/Workspace/nexus/nexus/engine/pipeline.py:113-119, 126-133, 168-183, 207-208, 248-251

2. 研究路由與 explain/consensus
- /Users/jameschen/Workspace/nexus/nexus/app/research_flow_service.py:230-337

3. nightshift 執行器
- /Users/jameschen/Workspace/nexus/nexus/app/nightshift_runner_service.py:55-113

4. Ultra Review 服務
- /Users/jameschen/Workspace/nexus/nexus/engine/ultra_review_service.py:12-15, 42-53, 74-100, 103-107

5. Ultra Review CLI 命令
- /Users/jameschen/Workspace/nexus/scripts/engine/nexus_cli.py:1711-1731

6. Ultra gate fail-closed 規則
- /Users/jameschen/Workspace/nexus/scripts/ops/ultra_gate.py:10-27, 39-57, 95-103, 109-119

7. Ultra 測試（行為與阻斷）
- /Users/jameschen/Workspace/nexus/tests/engine/test_ultra_review_service.py:20-60, 138-149, 175-194
- /Users/jameschen/Workspace/nexus/tests/ops/test_ultra_gate.py:46-67, 69-81, 96-122, 124-133

B. 外部能力來源（learn mode ingest 來源）
1. Autoreason README
- /Users/jameschen/Workspace/nexus/docs/external/autoreason/repo/README.md:9-12, 17-26, 29-41

2. Autoreason experiment context
- /Users/jameschen/Workspace/nexus/docs/external/autoreason/repo/paper/experiment_context.md:7, 11-35, 59-62, 151-153

3. DDTree README
- /Users/jameschen/Workspace/nexus/docs/external/ddtree/repo/README.md:4-6, 20, 26-33

---

## 8) 討論時建議先決三題

1. Autoreason 收斂門檻預設值
- A 連勝幾次停手？（2 或 3）

2. DDTree 初期掛載範圍
- 僅 autoreason stage 還是含 hyper_sprint stage1？

3. Ultra Review 強制範圍
- 先限高風險變更，還是所有 R/A 路徑都跑？

---

結論（短版）:
- 這次不是「加三個互斥模式」，而是「一個動態路由下的可疊加能力堆疊」：
  base/hyper/autoreason（生成層） + ddtree（加速層） + ultra_review（治理層）。
- 先做 P0 合約化與可觀測，再做 P1 真正能力落地，最後 P2 做策略自適應。