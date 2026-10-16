# Z1 — Capability Binding Audit Report

**狀態**: `Z1_CAPABILITY_BINDING_AUDIT_COMPLETE`, `Z1_CODEINTEL_BINDING_GAP`, `Z1_MEMORY_BINDING_GAP`, `Z1_AUTOREASON_DDTREE_BELIEF_GAP`  
**評估日期**: 2026-06-21  

---

## 🔒 治理與安全宣告 (Mandatory Flags)
*   **public_claim_allowed**: `false`
*   **production_ready**: `false`
*   **training_export_allowed**: `false`
*   **internal_only**: `true`

---

## 1. 核心能力對接審計 (Capability Binding Audit)
我們對 Nexus 十大原生能力組在 `local_heal` 引擎中的對接狀態進行了完整審計，定位了繞過（Bypassed）與僅有虛設（Stubbed）的 Gap 部分：

1.  **CodeIntel (Bypassed)**: 
    - *現狀*: Evidence Graph node/edge 的關係與 hashes 均為 Heuristic 靜態生成，未真正調用 AST 圖譜分析。
2.  **Memory / LanceDB / Findings Memory (Stubbed)**: 
    - *現狀*: 未真正連結 LanceDB。歷史修復成功的 pattern 與錯題懲罰（prior failure penalty）在 candidate selection 中缺席。
3.  **Autoreason (Bypassed)**: 
    - *現狀*: 缺乏候選 patch 的語義合理性與風險評估，全量交給 applier 與 verifier 處理。
4.  **DDTree (Bypassed)**: 
    - *現狀*: Proposer 無限生成 candidate，缺乏決策樹修剪，增加算力耗費。
5.  **Belief (Partially Connected)**: 
    - *現狀*: Uncertainty trigger 使用靜態 heuristic 特徵加權，非動態 Belief 信念系統。
6.  **Artifact / Claim / Delivery Gate (Partially Connected)**: 
    - *現狀*: 產出本地收據 compliance logs，未併入 Nexus 全局 delivery gate 簽署機制。
7.  **Sandbox / Replay (Connected)**: 
    - *現狀*: 已具備隔離 workspace 與 linear replay 驗證。
8.  **Ultra Review (Stubbed)**: 
    - *現狀*: Coordinated two-file edit 雖強制 owner_approval，但缺乏自動化 Ultra Review 安全/邏輯 regression 報告。
9.  **Learning Closure / Meta-Opt (Partially Connected)**: 
    - *現狀*: 僅單向落盤寫入 jsonl 學習矩陣，Selector 未對其反饋引導進行動態權重微調。
10. **Swarm / Drone (Bypassed)**: 
    - *現狀*: 無 Swarm 任務分片或 Drone 收集機制。

---

## 2. 接線優先度計畫 (Prioritized Binding Plan)
為使 `local_heal` 從單純的「本地跑模型」升級為「全能力 control plane 的消費者」，我們規劃以下綁定實現優先級：

- **P0 — CodeIntel to Evidence Graph**: 實作 EvidenceGraphBuilder 調用 Nexus AST 符號庫，實現真實 caller/callee、import 與 state read/write 綁定。
- **P1 — Memory/LanceDB to Action Ranking**: 在 Selector 中加入歷史 lessons 查詢。對符合歷史修復 pattern 的 action 給予 `prior_success_bonus`；對出錯的 patch 給予 `prior_failure_penalty`。
- **P2 — Autoreason / DDTree / Belief to Selection**: 實作 advisory score 寫入收據，並使用 DDTree 在 Planning 階段過濾無效 action。
- **P3 — Sandbox / Replay / Ultra Review**: 對 TWO_FILE_COORDINATED_EDIT 產生 Ultra Review 安全稽核報告，並維持 owner-gate 審核。
- **P4 — Artifact / Claim / Delivery Receipt**: 將本地 contract validation 收據轉換為全域 claim 格式，並實施 false-claim 預防門禁。
- **P5 — Learning Closure / Meta-Opt**: 提供 Selector 內 weights 參數與 learning matrix 的動態反饋對接。

---

## 3. 結論
Capability Binding Audit 完成。我們定位了 4 大 Gap 分類，並生成了對應的優先級對接計畫。允許推進至 Milestone Z2 進行實作對接。
