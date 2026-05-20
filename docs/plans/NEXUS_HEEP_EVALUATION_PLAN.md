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

---
*Created by Antigravity - Nexus Singularity V17*
