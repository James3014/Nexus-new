# Zero-Trust 技能篩選與推廣政策 (Zero-Trust Skill Selection & Promotion Policy)

本文件定義了 Nexus 專案中能力技能（Capability Skills）的憑證化（Evidence-Backed）推廣路徑。本政策嚴格執行 Nexus 的零信任核心憲法：**任何實體（包括工程 Owner 本人）皆不得繞過 Runtime 閘門。**

---

## 1. 技能生命週期狀態機

技能候選人必須依序通過確定性、分階段的評估管線，才能被晉升為 Runtime 預設技能（Runtime Default）。

```mermaid
stateflow
    [*] --> Candidate : 候選人吸納
    Candidate --> Exploration_Arm : 冷啟動配額
    Exploration_Arm --> Ablation_Arm : 基準對照消融
    Ablation_Arm --> Shadow_Arm : 通過控制消融
    Shadow_Arm --> Promotion_Candidate : 累積 N 次旁路運行成功
    Promotion_Candidate --> Runtime_Review_Ready : 信任不匹配為零
    Runtime_Review_Ready --> Runtime_Default : 通過 Apply 閘門
```

### 階段定義與閘門要求

#### M1. 候選人 (Candidate)
*   **定義**：透過目錄映射或外部引用註冊的原始候選技能。
*   **閘門檢查**：
    *   元數據完整性校驗（名稱、路徑、能力掛載 `capability_mount`、以及 sha256 狀態為 `PASS`）。
    *   安全狀態檢核（非隔離狀態 `quarantined`）。

#### M2. 探索分支 (Exploration Arm)
*   **定義**：分配給新技能的冷啟動評估配額。
*   **閘門檢查**：
    *   透過確定性雜湊（Deterministic Hashing）進行分配以確保可重現性。
    *   *限制*：在建立基礎戰績前，禁止晉升為 Runtime 預設或進入 Shadow 旁路。

#### M3. 消融分支 (Ablation Arm)
*   **定義**：與無技能基準組（`capability_only`）進行的控制組對照測試。
*   **閘門檢查**：
    *   必須與負樣本（Wrong/Quarantined Skill，錯誤或隔離技能）同時運行。
    *   負樣本分支*必須*回傳 `BLOCK` 或 `FAIL_CLOSED` 狀態。

#### M4. 暗影分支 (Shadow Arm)
*   **定義**：在生產/實時任務中進行旁路並行執行（輸出被遮蔽，僅作監測）。
*   **閘門檢查**：
    *   不得干預或影響預設的 Runtime 輸出。
    *   記錄完整的執行遙測數據以供精確對比。

#### M5. 推廣候選人 (Promotion Candidate)
*   **定義**：已證實具有正向貢獻憑證的候選技能。
*   **閘門檢查**：
    *   需要完整且未中斷的執行憑證鏈（Receipt Chain）：
        $$\text{憑證鏈} = \text{selected} \rightarrow \text{injected} \rightarrow \text{used} \rightarrow \text{evidence\_present} \rightarrow \text{gate\_passed} \rightarrow \text{outcome\_contributed}$$

#### M6. 準備就緒審查 (Runtime Review Ready)
*   **定義**：已驗證並清除所有阻礙，進入集成計畫階段。
*   **閘門檢查**：
    *   $\text{Trust Mismatch} == 0$（無安全政策漂移或執行分歧）。
    *   負樣本分支無任何逃逸或失守記錄。
    *   在至少 $N$ 次 Shadow 運行中成功執行。

#### M7. 預設運行技能 (Runtime Default)
*   **定義**：目前被預設啟用的能力技能。
*   **閘門檢查**：
    *   必須由工程人員手動審核並批准 `runtime_policy_apply_gate`。
    *   *嚴格限制*：在任何情況下，技能更新均不得在無手動閘門結算的情況下自動轉為預設（禁止無感升級）。

---

## 2. 強制性政策指令

### 2.1. 禁止單一指標裁剪 (安全角色否決權)
*   **原則**：不得僅依據「正確性 Score Delta」（例如正確率提升的百分比）來裁剪安全、審計或防禦類角色（Safety, Audit, Guard Roles）。
*   **角色歸因要求**：安全角色的必要性，僅能透過其直接歸因的攔截事件（Role-Attributed Negative Block）來證明。例如：
    *   成功識別並攔截負樣本技能。
    *   對分歧執行拋出 `trust_mismatch` 警報。
*   **歸因憑證**：管線層級的 Block 不能自動歸功於特定安全角色，除非有憑證明確證實是該角色的 schema 觸發了阻擋。

### 2.2. 確定性探索機制 (防止馬太效應)
*   **原則**：技能篩選機制必須為新註冊或尚未驗證的技能保留 $20\% \sim 30\%$ 的探索配額，以防舊技能因戰績累積而產生馬太效應（Rich-Get-Richer）鎖定。
*   **可重播性**：探索分配不得使用隨機數種子，必須基於能力名稱、候選技能 ID 以及 Git Commit SHA 進行確定性雜湊：
    $$\text{Hash Key} = \text{SHA256}(\text{Capability} + \text{Skill ID} + \text{Commit SHA}) \pmod{100}$$

### 2.3. 禁止無感自動升級 (No Silent Upgrades)
*   **原則**：自動化推廣管線嚴禁直接寫入並修改生產環境的 Runtime 預設技能。
*   **機制**：當 Shadow 分支的技能達到活化閥值（例如連續 10 次成功凭证）時，系統必須自動產生一個 Pull Request，其中包含：
    1.  提議的 `runtime_policy_patch_plan`。
    2.  支持該推廣的完整 execution receipts 憑證鏈。
    3.  自動產生的多維度決策解釋報告。

### 2.4. 四維指標分離原則
*   **原則**：決策解釋器（Explainer）必須將技能評估指標拆分為四個獨立向量，嚴禁輸出單一的綜合得分：
    1.  **正確性評分 (Correctness Score)**：基準能力測試的達成度。
    2.  **安全/審計健壯性 (Safety/Audit Robustness)**：已證實的攔截次數與負樣本防禦能力。
    3.  **憑證鏈完整度 (Receipt Lineage)**：執行狀態審計軌跡的完整性。
    4.  **成本與效率 (Cost Efficiency)**：相對於基準組的 Token 消耗與延遲開銷。

### 2.5. Runtime Apply Reject Conflict Gate
*   **原則**：Runtime apply 不得只依賴 live compare winner，還必須檢查既有 catalog verdict 是否已拒絕同一技能。
*   **同能力拒絕衝突**：若候選技能在同一 `capability` 已有 `verdict=reject` 或 `runtime_eligible=false`，該 runtime apply 必須 `RETURN`，並輸出 `same_capability_reject_conflict` blocker。
*   **跨能力拒絕衝突**：若候選技能只在不同 `capability` 被拒絕，runtime apply 可繼續，但必須在 decision artifact 輸出 `reject_conflict_warnings`。Reviewer 必須能看到原拒絕 capability、verdict 與 `runtime_eligible` 狀態。
*   **語義邊界**：除非政策另行宣告，`runtime_eligible=false` 預設視為 capability-scoped verdict，不自動升格為全域封鎖；若未來定義為 global reject，跨能力拒絕衝突必須改為 blocker。
*   **外部候選邊界**：若 applied winner 的 `source_status=external_reference_candidate`，runtime apply artifact 必須標記 `requires_curation=true` 與 `runtime_review_scope=overlay_only_requires_curation`。這類 overlay 可用於 runtime policy routing，但不得宣稱為完整 Zero-Trust v2 promotion。
*   **Reject 歸因要求**：所有 `verdict=reject` 或 `runtime_eligible=false` 的 catalog verdict 必須輸出非空 `failed_security_contract_rules`，至少能區分 runtime eligibility、capability-scoped reject、promotion contract 缺口。

### 2.6. Schema-Only V2 Gate 與 Evidence 分帳
*   **原則**：現有 runtime overlay 屬於 `security_contract_version=v1_diagnostic_only`，可繼續提供 runtime routing，但不得取得 v2 promotion credit。
*   **分帳要求**：Runtime apply artifact 必須輸出 `v1_evidence_count`、`v2_evidence_count`、`v2_trust_mismatch_count` 與 `promotion_credit_source`。在 schema-only 階段，`promotion_credit_source=none`、`v2_evidence_count=0`、`v2_promotion_eligible=false`。
*   **Sandbox 宣告**：Executable applied winner 必須預先宣告 `requires_sandbox_attestation=true`。在 runner 尚未提供可驗證 attestation 前，artifact 必須標記 `sandbox_attestation_status=missing_not_required_for_overlay_only`，表示該證據只支援 overlay，不支援 v2 promotion。
*   **取代路徑**：未來 v2 管線通過 sandbox attestation、runtime-signed receipt、clean-slate evidence 與 manual apply gate 後，才可將 `promotion_credit_source` 從 `none` 升級為 `v2_only`。
