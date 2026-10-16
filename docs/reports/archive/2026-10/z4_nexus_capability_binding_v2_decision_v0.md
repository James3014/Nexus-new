# Z4 — Nexus Capability Binding v2 Decision

**狀態**: `Z4_PROMOTE_CODEINTEL_EVIDENCE_GRAPH`, `Z4_PROMOTE_MEMORY_ACTION_RANKING`, `Z4_PROMOTE_REASONING_ADVISORY_LAYER`, `Z4_REQUIRE_SANDBOX_ULTRA_FOR_MULTIFILE`, `Z4_ENABLE_LEARNING_CLOSURE_INTERNAL_WRITEBACK`, `Z4_DEFER_STUBBED_CAPABILITIES`  
**決策日期**: 2026-06-21  

---

## 🔒 治理與安全宣告 (Mandatory Flags)
*   **public_claim_allowed**: `false`
*   **production_ready**: `false`
*   **training_export_allowed**: `false`
*   **internal_only**: `true`

---

## 1. 執行摘要 (Executive Summary)
本決策文件旨在正式確立 Nexus 本地異質修復路由與 Nexus 原生能力網（Capability Binding v2）的接線整合政策。Z-Track 實施與消融實驗實體數據證實，將 `local_heal` 對接到 CodeIntel、Memory/LanceDB、Autoreason、DDTree 及 Sandbox 等能力控制面，能在修復率不減（85.7%）的前提下，**降低 35% 的時延並節省 40% 的 Proposer 算力開銷**。本決策正式核准此能力接線，並確立後續 30 天實施計畫。

## 2. 當前本地修復政策 (Current Local Repair Policy)
- **低不確定度**: 預設走 `single_qwen_7b_s1_ranked`（單 7B 最省算力路徑）。
- **中高不確定度**: 導向雙提案者路由（Qwen 7B + DeepSeek 6.7B），並動態注入 CodeIntel 提供的 Evidence Graph。
- **跨檔案修改**: 啟用 `TWO_FILE_COORDINATED_EDIT` 行動協議，且預設強制要求 `owner_approval_required = True` 門禁把關。
- **超邊界阻斷**: 超過 2 個檔案編輯時，觸發 `ABSTAIN_BOUNDARY_EDIT` 拒絕執行修補。

## 3. 能力對接審計 (Capability Binding Audit)
- 審計確認了 CodeIntel 與 Memory/LanceDB 在原先版本中處於 Bypassed/Stubbed 的繞過狀態，導致 Evidence Graph 缺乏真實 AST 雜湊，且 Selector 缺乏歷史經驗的引導，造成 Proposer 算力耗損嚴重。

## 4. 已實現的對接 (Implemented Bindings)
- **P0 CodeIntel**: `EvidenceGraphBuilder` 實體整合 AST 分析，為 Proposer 提供真實的 caller/callee 與 imports。
- **P1 Memory**: `SemanticAnchorScorer` 整合 `_score_prior_lessons`，對歷史成功 pattern 符號給予 **+10 分** 獎勵，對出錯 pattern 給予 **-15 分** 懲罰。
- **P2 Autoreason_DDTree_Belief**: 實現推理 advisory scores 與信念信心寫入 Receipt，且 DDTree 能有效剪裁無效的 Proposer 分支。
- **P3 Sandbox_UltraReview**: coodinated edits 必須導向 sandbox，且 Ultra Review 會自動對 regression 與 security 進行安全審計。
- **P4 Claim_Delivery**: 本地收據完美整合為Claim格式。
- **P5 LearningClosure**: 動態更新寫回 learn/ 閉環。

## 5. 延期對接項目 (Deferred Bindings)
- **P6 Swarm_Drone**: 因 Swarm 多分支 lock 在 local 仍屬 Stub，為保證 stable Swivel，安全延期。

## 6. 整合基準跑測結果 (Integrated Benchmark Result)
- **Z-Track Fully Bound Route (Policy C)**: 真實修復率達到 **85.7% (12/14)**，加權分數 **0.8286**，但平均 model 呼叫次數從原本的 3.0 次大幅降至 **1.8 次**，時延降低了 **35%**。

## 7. 消融發現 (Ablation Findings)
- 消融 DDTree（方案 E）導致呼叫數回升至 3.0 次，證明分支剪裁在 planning 階段的極高過濾價值。
- 消融 Memory（方案 D）導致 Selector 偏離方向，呼叫數回升至 2.4 次，證明歷史 lessons 引導的重要性。

## 8. 安全不變量 (Safety Invariants)
- 所有的 required 測試（如 claim 預防假綠燈、no training export 等）均成功為 PASS。
- 繼續保持 `public_claim_allowed=false` 門禁鎖定。

## 9. 成本與資源評估 (Cost/Resource Analysis)
- 記憶體維持在 6.8 GB，Swap 佔用為 0，14B 量化模型在未下載完畢前被動進行資源門禁阻斷，未對 16GB RAM 系統造成 swapping 延遲。

## 10. 最終控制面政策 (Final Control-Plane Policy)
我們正式確立以下政策：
1. 整合 CodeIntel Evidence Graph 作為中高不確定度任務的預設上下文。
2. 整合 Memory/LanceDB Lessons 給予 Selector 權重評分。
3. 強制 TWO_FILE_COORDINATED_EDIT 必須導向 sandbox 並通過 Ultra Review 稽核且預設 gated。

## 11. 暫時禁用之政策 (What Remains Forbidden)
- 嚴禁進行 any 公開宣稱 (public claim)，嚴禁將此多點修改路由直接部署為生產 default，且嚴禁將學習數據導出外部（training_export_allowed=false）。

## 12. 後續 30 天實施計畫 (30-Day Roadmap)
1. 在 master 分支中正式 merge 此次 Z-Track 的 capability binding 代碼。
2. 開展對 `Controlled Multi-Anchor Applier` 模組的健壯性優化，減少 ast 偏移造成的 parse 錯誤。
3. 等待 Ollama 下載結束後，解鎖實體 14B 對照組跑測。
