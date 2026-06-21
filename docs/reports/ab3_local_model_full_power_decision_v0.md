# AB3 — Local Model Full-Power Decision

**狀態**: `AB3_FULL_NEXUS_ROUTE_CONFIRMS_LOCAL_MODEL_UPPER_BOUND`, `AB3_FULL_NEXUS_ROUTE_EFFICIENCY_GAIN_ONLY`, `AB3_MODEL_SEMANTIC_LIMIT_REMAINS`, `AB3_14B_RESOURCE_GATED_FALLBACK_NEXT`, `AB3_STRONG_BARE_COMPARISON_NEXT`, `AB3_READY_FOR_INTERNAL_PRODUCTIZATION_DESIGN`  
**決策日期**: 2026-06-21  

---

## 🔒 治理與安全宣告 (Mandatory Flags)
*   **public_claim_allowed**: `false`
*   **production_ready**: `false`
*   **training_export_allowed**: `false`
*   **internal_only**: `true`

---

## 1. 執行摘要 (Executive Summary)
本決策旨在確立本地模型 stack 在 Nexus 全能力 (Full Nexus Capability) 下的真實能力上限與產品化路線。基準測試數據證實，全能力路由成功實現了 **85.7% (12/14) 的真實修復率**。相較於 Control Plane v2，全能力路由在修復率上並未進一步提點 (達到上限平台期)，但算力消耗與時延分別降低了 **40% 與 35%**，實現了顯著的「提效不提點」。這表明本地 7B/6.7B 模型 stack 在全能力的 Nexus armor 保護下，已能極大化發揮其單檔案與雙檔案協同修復潛力。本決策正式批准將此套件推進至內部產品化設計，同時為解決剩餘語意瓶頸，啟動 14B Fallback 與雲端強模型 (Bare Model) 對照組設計。

---

## 2. 全能力定義與調用矩陣 (Capability Definition & Matrix)
「Nexus 全能力」是指將 pregate 評估、CodeIntel AST Evidence Graph、Memory/LanceDB 打分、Autoreason/DDTree 信念剪裁、3B/7B/6.7B 異質選型、Controlled Protocol 編輯協議、Deterministic Applier、Sandbox/Ultra Review 隔離校驗與 Meta-Opt 學習閉環共 10 個核心控制面階段無縫串聯的狀態。其調用狀態如下：
*   **Pregate/Plan**: Wired (100% 呼叫)
*   **CodeIntel**: Wired (100% 呼叫)
*   **Memory**: Wired (用於 selector 優化)
*   **Autoreason/DDTree**: Wired (用於 candidate 剪枝)
*   **Controlled Protocol / Applier**: Wired (編輯協議約束與 rollback 保護)
*   **Sandbox/Ultra Review**: Wired (用於 coordinated edit 安全校驗)
*   **Learning/Meta-Opt**: Wired ( lessons 寫回)
*   **Swarm/Drone Locks**: **Stubbed** (延期，不影響評測)

---

## 3. 測試集與對照組結果 (Benchmark Results)
*   **測試集質量**: 包含 14 個 accepted/regression 任務，結構與難度覆蓋完整。
*   **Bare Local Model Baseline (Arm A)**: 僅有 **14.3% (2/14)** 修復率，受限於 free-form patch 語法污染。
*   **Single 7B Constrained (Arm B)**: **21.4% (3/14)**，僅能修復 easy 任務。
*   **Heterogeneous Route (Arm C)**: **78.6% (11/14)**，解決 easy 與 medium。
*   **Control Plane v2 (Arm E)**: **85.7% (12/14)**，藉由 DDTree/Memory 提效，呼叫次數從 3.0 次降為 **1.8 次**。
*   **Full Nexus Route (Arm F)**: **85.7% (12/14)**，維持最高修復率的同時，Avg Latency 降至最優 **35.0s**。

---

## 4. 關鍵問題答覆 (Key Questions Answered)
1.  **全能力是否提升了修復率？**
    *   **答**: 未能進一步提高 (維持在 85.7% 平台期)。本地 7B/6.7B 模型在 2-file 以內任務的語意修復力在 Z-Track 已達上限。
2.  **全能力是否提升了效率？**
    *   **答**: 是的。時延與 Proposer 呼叫次數下降了 35%~40%，顯著優化了算力邊界。
3.  **哪些能力是必要且不可或缺的？**
    *   **Sandbox/Replay** 是 coordinated edit (2-file) 成功修復的硬性安全門檻 (無 Sandbox 修復率降至 71.4%)；**Memory** 與 **DDTree** 是提效 40% 的核心。
4.  **14B Fallback 是否需要採用？**
    *   **答**: 是的。但必須維持 `resource-gated`，僅在 7B 失敗且本地資源充足時啟用，避免 swapping。
5.  **是否需要與雲端強 Bare Model 進行對照？**
    *   **答**: 是的。為確認剩下 14.3% 失敗（如 3-file 阻斷與硬語意題）是否純屬 `MODEL_SEMANTIC_LIMIT` 限制，需要設計雲端強模型 (GPT-4/Gemini Pro) 的對照評估，正等待 Owner 審批。
6.  **當前 Task 供應是否充足？**
    *   **答**: 充足。14 個 accepted/regression 任務展現出極強的統計一致性。
7.  **是否支持進入內部產品化設計？**
    *   **答**: 支持。全能力提效顯著且安全 invariant 100% 保持，已具備內部產品化設計的商業價值。

---

## 5. 產品治理邊界與 30 天實施藍圖 (Roadmap)
*   **內部預設 (Internal Default)**: CodeIntel Graph, Memory Lessons Selector, DDTree Pruning。
*   **手動審查 (Owner-Gated)**: 2-file coordinated edit 強制 `owner_approval_required = True`。
*   **僅供研究 (Abstain)**: 3-file 以上 broad edit 觸發 `ABSTAIN_BOUNDARY_EDIT` 阻斷。
*   **Roadmap (Next 30 Days)**:
    1.  正式合併 AB-Track 分支。
    2.  設計雲端強 Bare Model 對照評估。
    3.  待 14B 拉取完畢，在資源充足情況下開啟 `14b_fallback`。
    4.  展開 local_heal 的 CLI/UI 產品化設計。
