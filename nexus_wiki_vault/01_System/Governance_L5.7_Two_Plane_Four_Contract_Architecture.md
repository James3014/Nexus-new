# Nexus L5.7 Governance: Two-Plane Four-Contract Architecture
(雙平面四合約架構白皮書)

**建立日期**: 2026-06-05
**架構版本**: Nexus L5.7 / v26.0+
**上下文來源**: 2026-05-28 Learning Closure Matrix

## 1. 架構演進背景 (The Phenomenon & Root Cause)

在先前的輕量級路由 (Light Routing) 優化過程中，系統經常將不同的成功指標混為一談：
* 「Execution 成功」被等同於「可公開宣稱 (Public Claim Safe)」。
* 「Local-only delivery」偷渡成了「Source-promotion-ready」。
* 「Observation-only telemetry」混入了公共成本 (Public cost claim)。

這導致了「假執行感」與治理指標的嚴重失真。為了徹底解決這個問題，Nexus 在 L5.7 版本引入了**兩個平面 (Two-Plane)** 與 **四層合約 (Four-Contract)** 的強硬實體分離邊界。

## 2. 雙平面隔離 (Two-Plane Isolation)

系統在物理與邏輯上切分出兩個互不干涉的平面：
1. **執行與觀察平面 (Execution & Observation Plane)**: 負責實際運算、A/B 測試、局部決定性救援 (Local Deterministic Rescue) 以及背景負載轉移。此平面的產出**絕對不具備**對外宣稱的效力。
2. **公開宣稱與商業推廣平面 (Public Claim & Source Promotion Plane)**: 只有經過嚴格 1.0 代幣完整度校驗、相同的模型對比 (Same-model paired)、且通過三重驗證門檻的證據，才能進入此平面。

## 3. 四層契約實作 (The Four Contracts)

為了在兩個平面間建立防彈玻璃般的審計門檻，Nexus 實作了四層向下相依的合約：

### L1: `lane_capability_contract.py` (通道能力合約)
* **職責**: 處理能力通道的開啟與回退。
* **硬規則**: 強制將 `configured_but_blocked` (設定但被阻斷) 與 `is_active_rescue` (主動救援) 在實體資料欄位上分離。`HYPER_ONLY` 模式具備強制回退機制。

### L2: `receipt_causality_contract.py` (因果收據合約)
* **職責**: 確保執行的證據鏈完整無缺。
* **硬規則**: 包含 `evidence_present`、`gate_passed`、`public_claim_safe` 等六大核心欄位。缺一不可，否則拋出 `ValueError`。嚴禁 `planner_only`、`observation_only` 或 `local_only` 等來源偷渡為完整證據。

### L3: `route_policy_evidence_contract.py` (路由策略證據合約)
* **職責**: 確保路由決策 (Route Decision) 序列化且合法。
* **硬規則**: 若策略 (Policy) 與最終贏家 (Winner) 不一致，則 100% Fail-closed (失效關閉)。被阻斷的通道 (Blocked lane) 永遠不會產生 winner。

### L4: `public_telemetry_boundary_contract.py` (公開遙測邊界合約)
* **職責**: 最終的商業宣稱與推廣守門員。
* **硬規則**: 
  * `provider_token_completeness < 1.0` 立即阻斷。
  * 影子/實驗性 (shadow/experimental) 數據嚴禁進入下游消費。
  * 若直接傳入 `public_claim_safe=True` 意圖繞過審查，立即拋出 `ValueError`。
  * 運算時長殘差 (wall-ledger 殘差) > 5% 立即阻斷。

## 4. 判讀與宣稱門檻 (Claim Gates)

Nexus L5.7 強調：
* **`EXECUTION_READY` 通過 ≠ `SOURCE_PROMOTION_READY`**。
* **`EVIDENCE_READY` 通過 ≠ `COMMERCIAL_BASIS_READY`**。

四段 Gate 必須獨立判讀，不得以前段的成功推斷後段。任何對外公開宣稱，必須按序滿足六大條件：
1. `hidden_verifier_mode=True`
2. same_model paired
3. outbound_prompt_ledger clean
4. `provider_token_completeness=1.0`
5. wall_ledger conserved
6. x3_promotion gate PASS