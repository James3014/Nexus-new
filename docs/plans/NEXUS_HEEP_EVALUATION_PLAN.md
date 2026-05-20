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

---
*Created by Antigravity - Nexus Singularity V17*
