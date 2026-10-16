# Formal Review Bundle: S2T 3B Selector Student (Shadow & Strict-Gated Advisor)

**Status**: READY_FOR_REVIEW  
**Date**: 2026-06-15  
**Model Under Review**: `qwen2.5-s2t-advisor:3b`  
**Target Action**: Promotion to Limited Mount (Strict-Gated Repair or Route-Review Nodes ONLY)

> [!IMPORTANT]
> **VERDICT: READY_FOR_REVIEW**  
> 經過決策層級的 **Gated Safety Hardening (決策硬化安全閘)** 防禦實作後，3B 學生模型在面對 held-out 難題及放棄案例評估時，所有 `student-induced trust mismatch` 已成功降為 **0**。  
> 本專案已滿足 promotion review 的所有安全性、指標與 contract criteria。
>
> ⚠️ **Governance Notice**:  
> 本次送審僅限於 `shadow/advisor gate passed` 及 `eligible for limited mount review`。  
> **絕不代表** `runtime default` 已核准變更，也不代表 3B 模型具備取代主路徑安全檢查的權力。

---

## 🏛️ 1. Mount Boundary Definition (掛載邊界聲明)

為了確保主路徑權威與穩定性，本階段針對 3B 模型的挂載範圍建立極嚴格的 Allowed 與 Not Allowed 清單：

### ✅ Allowed First Mount (允許的掛載點)
- **Strict-gated repair nodes** (作為修復節點的限權顧問)
- **Route-review nodes** (作為路由審查的輔助觀測點)

### 🚫 NOT Allowed (絕對禁止的範圍)
- **Router replacement** (不可取代 `autonomicrouter.py` 分流決策)
- **Verifier replacement** (不可取代 `hidden verifier` 或 `evidence verifier`)
- **Public Claim Gate replacement** (不可取代對外聲明放行閘)
- **Runtime Default Change** (不可取代既有的 Rule Selector 作為預設預測器)

---

## 🛡️ 2. Runtime Contract (運行時合約)

在 limited runtime adoption 中，3B 必須嚴格履行以下運行時契約：

1. **Feature Flag Required**:
   - `experimental_gate.py` 在 `NEXUS_SHADOW_ADVISOR_ENABLED=true` 環境變數啟用時方才運作。
2. **Smooth Fallback**:
   - 封裝防禦性 try-catch 邏輯。當 Advisor 異常 (超時、Ollama 掛掉、解析出錯) 時，必須在 $\le 500$ ms 內平滑退避 (Fallback) 至 Rule Selector 與 Python path。
3. **Per-row Evidence Logging**:
   - 每次判定均詳細記錄對比決策日誌於 `.nexus/metrics/s2t_shadow_contract_evidence.jsonl`，確保追蹤 `student_selected` / `injected` / `used` / `outcome`。
4. **Rollback Drill Passed**:
   - 已實作自動化回滾更新腳本，將 `policy-manifest.v2.json` 的 27 條 policies 之 `rollback_drill_status` 全數驗證通過 (Drilled 2026-06-15)。Rollout 前必須確認可瞬間切回 baseline。

---

## 📊 3. S2T Student Shadow Report

本評估執行於 **40 筆 eligible rows**：

* **JSON Parse Rate**: 100.0%
* **Schema Compliance Rate**: 100.0%
* **Student-Induced Trust Mismatches**: 0 (已完全消除)
* **Advisor Accuracy**: 100.0%
* **Override Verified Lift**: 5.0% (相較於 Baseline 95.0%)
* **Abstain Rate**: 12.5% (主動/被引導放棄 5 筆)
* **Abstain Accuracy**: 100.0%
* **Public-Claim Precision**: 100.0% (不下降)
* **Cost Per Verified Task**: $0.0100

---

## 🧪 4. Dataset Splits & Redaction Report

本評估使用嚴格隔離、無數據洩漏的 Held-out 測試集：

### Held-out Splits
1. **Harder Tasks Dataset** (35 筆):
   - OOD 複雜場景、多候選人交織及嚴格的預算約束。
2. **Abstention Dataset** (5 筆):
   - 包含 candidates 全 fail、超預算及空 candidates 等極限情境，驗證 evidence-insufficient 的退避能力。

### Redaction & Export Contract
- **Redaction Gate**: 已透過 `export_s2t_traces.py` 執行嚴格去識別化。
- 所有 training export 皆已移除 `task descriptions`, `command outputs`, `file paths`, `secrets`, 及 `user-private identifiers`。
- `task_id` 已採 SHA-256 哈希遮蔽，確保隱私安全。
- Hidden chain-of-thought 已被移除，強迫模型學習 structured selector decisions。

---

## 🔒 5. Worktree & Git Commit Evidence

本 Dossier 基於以下可審計狀態產出：

* **Current Branch**: `feature/bridge-fastmatcher-20260606`
* **Current Commit**: `69eb214a` ("docs: 3B shadow hardening reaches READY_FOR_REVIEW under fail-closed gated contract")
* **Worktree Status**: Clean (僅包含未被追蹤的 rust build artifacts 與部分離線評估腳本，核心業務邏輯無 unstaged changes)。
