# Nexus Hybrid-Ensemble Evaluation Plan (HEEP)

## 1. 概述
本計劃旨在評估 Nexus 能力在「單數 Skill (Solo)」與「複數 Skill (Ensemble)」模式下的表現差異。透過量化品質增量與成本代碼，為每項能力設定最佳裝配策略。

## 2. 測試模式定義
- **Mode A: Lean Solo**
    - **組態**：僅使用 V32 評測第一名的 Primary Skill。
    - **目標**：極致速度與最低 Token 成本。
- **Mode B: Dual Guard**
    - **組態**：使用 Primary Skill + Top 1 挑戰者作為監核。
    - **目標**：攔截邏輯錯誤，提升修復成功率。
- **Mode C: Neural Swarm**
    - **組態**：使用 Top 3 候選 Skill 進行多重共識投票。
    - **目標**：消除 AI 幻覺，確保治理與安全真值。

## 3. 核心指標 (Metrics)
1. **品質增量 (Quality Lift)**：Ensemble 模式相較於 Solo 模式的成功率提升百分比。
2. **溢價係數 (Premium Factor)**：每提升 1% 品質所增加的 Token 成本比。
3. **共識一致性 (Consensus Score)**：複數 Skill 間輸出結果的吻合程度。

## 4. 實施流程
1. **Gold Cases 提取**：從歷史報告中提取各能力的「黃金測試案例」。
2. **三路併行測試**：利用修改後的 `nexus_benchmark_full.py` 進行 A/B/C 組對抗。
3. **動態策略標定**：將測試結果回灌至 `NEXUS_CAPABILITY_SKILL_MAP.md`。

## 5. 落地契約修訂 (2026-05-20)

HEEP 不直接接舊式 `nexus_benchmark_full.py` 作為第一步；第一階段改接現有 SF SSOT 與 overlay artifact，先產生可機器檢查的 discovery-only contract。

- **輸入 SSOT**：
  - `docs/reports/NEXUS_SF_CAPABILITY_PRIMARY_ORIGINAL_SKILL_MAP_2026-05-20.json`
  - `docs/reports/NEXUS_SF_RUNTIME_SKILL_POLICY_OVERLAY_CURRENT_2026-05-20.json`
  - `docs/reports/NEXUS_SF_RUNTIME_SKILL_POLICY_OVERLAY_CURRENT_SMOKE_2026-05-20.json`
- **執行入口**：`uv run python scripts/ops/build_heep_emas_pipeline.py`
- **產物**：
  - `docs/reports/NEXUS_HEEP_EMAS_CONTRACT_2026-05-20.json`
  - `docs/reports/NEXUS_HEEP_ASSEMBLY_CATALOG_2026-05-20.json`
  - `docs/reports/NEXUS_HEEP_GOLD_CASE_MANIFEST_2026-05-20.json`
  - `docs/reports/NEXUS_HEEP_LOCAL_ABC_ROLLUP_2026-05-20.json`
  - `docs/info/NEXUS_CAPABILITY_SKILL_MAP.md`
- **邊界**：本階段只做 deterministic local dry-run 與 catalog/mode 更新；`runtime_update_allowed=false`、`public_benchmark_allowed=false`。
- **下一階段**：只有當 live ensemble runner 產出 runtime-confirmed selected/injected/used/evidence/gate/outcome receipt，Mode B/C 才能進 runtime apply review。

## 6. MAT-B 可執行比對契約 (2026-05-20)

HEEP 的最終選用標準不是 local role coverage，也不是單純「複數 skill 比單 skill 看起來完整」。每個 capability 都必須先以目前 primary skill 作為 **Mode A baseline**，再將 Mode B / Mode C 作為 challenger arm 進入 Flash+Nexus internal live compare。local replay 只能產出候選與 receipt readiness，不能直接產生 replacement verdict。

### 6.1 Arm 定義

- **Baseline arm**：`mode_a_current_primary`，只掛目前 `(capability, primary_skill)`。
- **Challenger arm**：`heep_multi_skill`，掛 Mode B 或 Mode C assembly。
- **比較範圍**：同一 capability、同一 task set、同一 runner boundary、同一 hidden verifier / receipt contract。
- **產物入口**：`docs/reports/NEXUS_HEEP_FLASH_NEXUS_LIVE_COMPARE_QUEUE_2026-05-20.json`。

### 6.2 MAT-B KPI 與判定順序

| 順序 | 維度 | KPI | Gate |
| :--- | :--- | :--- | :--- |
| 1 | Reliability | `success_rate` | challenger 必須 >= baseline，且不得出現 delivery RETURN。 |
| 2 | Quality | `pollution_pct` | challenger 必須 <= baseline，且不得超過該 task family 的污染上限。 |
| 3 | Governance | `evidence_seal_count` | challenger 必須 >= baseline，且 runtime receipt 必須包含 selected / injected / used / evidence / gate / outcome。 |
| 4 | Efficiency | `token_delta`, `wall_delta` | 只有 Reliability、Quality、Governance 全 PASS 後才可判讀；不得用成本改善覆蓋前三項失敗。 |
| 5 | Regression | `reopen_rate` | challenger 必須 <= baseline，且 replay/regression simulation 不得重新打開已關閉問題。 |

`reopen_rate` 的優先來源是 runner 原生欄位。若 runner 尚未輸出原生 `reopen_rate`，HEEP report builder 只能在 row 同時具備 delivery、runtime classification、data contract、cost/evidence/delivery rubric、skill mount contract 與 receipt-chain 信號時，使用 deterministic receipt replay proxy 產生 `0.0` 或 `1.0`。缺少這些 replay inputs 時必須維持 `HOLD_MISSING_MAT_B_EVIDENCE`，不得把空值視為通過。

任何 arm 若出現 `infra_invalid_reason`，該 pair 不得被當作有效勝負比較。baseline infra-invalid 只能 `HOLD_MISSING_MAT_B_EVIDENCE`；challenger infra-invalid 也只能 HOLD。只有 challenger 具備乾淨成本/receipt 證據但 delivery RETURN 時，才可判為 `REJECT_MULTI_SKILL`。

### 6.3 Decision State

- `KEEP_SINGLE_PRIMARY`：Mode A 仍是最佳或 challenger 未通過 MAT-B。
- `PENDING_FLASH_NEXUS_LIVE_COMPARE`：local replay 顯示 Mode B/C 有潛力，但 live KPI 尚未收齊。
- `APPROVE_HEEP_MODE_CANDIDATE`：Mode B/C 在 MAT-B 全部 PASS，可進 runtime apply review packet。
- `REJECT_MULTI_SKILL`：Mode B/C 未通過 Reliability、Quality、Governance 或 Regression。
- `HOLD_MISSING_MAT_B_EVIDENCE`：缺少 live receipt、token/wall truth、污染率或 reopen evidence。

### 6.4 禁止宣稱

- 禁止用 local replay、role count、consensus score 或 synergy factor 直接取代 MAT-B live KPI。
- 禁止將 `APPROVE_HEEP_MODE_CANDIDATE` 等同 runtime default；runtime default 仍需獨立 apply gate。
- 禁止將本 contract 的 internal live compare 等同 public benchmark 或 publication-ready claim。

---
*Created by Antigravity - Nexus Singularity V17*
