---
aliases:
- RLM
- Recursive Learning
- Self-Correction Loop
confidence: high
last_compiled: 2026-04-30
owner: agent
related_pages:
- '[[Module - Core Orchestrator]]'
- '[[Protocol - Evidence Chain]]'
source_of_truth: nexus/app/research_flow_service.py
status: active
tags:
- protocol
- rlm
- recursive
- learning
- budget
title: Protocol - RLM Recursive Learning
type: protocol
version_scope:
- v26
---

# Protocol - RLM Recursive Learning (v26 Hardened)

## 🧬 定義與核心概念
**RLM (Recursive Learning Machine)** 是 Nexus v2Singularity 的核心遞迴修正引擎。它將傳統的「一次性生成」轉化為「有預算約束的遞迴演進」。

### 1. 遞迴深度與 Trace Budget
- **Trace Budget**: 每個任務被分配一個總體 Token 與時間預算。
- **Recursive Depth**: 系統在 `A Phase` (Audit) 失敗後，會根據 `Belief` 信號自動決定是否啟動下一輪遞迴。
- **Local Convergence**: 優先在局部 Worktree 進行修復，直到通過 `A Gate` 或預算耗盡。

## 🔄 RLM 工作流 (R-A-C Loop)
1. **R (Repair)**: 生成候選補丁。
2. **A (Audit)**: 執行物理驗證 (Pytest, Ruff, X-Ray)。
3. **If FAIL**: 
   - 記錄失敗原因至 `trace_log`。
   - 扣除 `trace_budget`。
   - 重新進入 R Phase，並注入上一輪的失敗教訓。
4. **If PASS**: 
   - 進入 **C (Crystallize)**，將成功的 Trace 轉化為技能。

## 🛡️ 治理約束 (RLM Guard)
- **Max Strikes**: 預設 3 次失敗後強制升級至 `NightShift` 或轉交人工審核。
- **Bayesian Cooling**: 失敗次數越多，推理溫度 (Temperature) 自動調低，以追求更高確定性。
- **Atomic Rollback**: 每一輪遞迴失敗後必須執行 Git 硬回滾，確保環境純淨。

## 📊 監控與指標
- **Convergence Rate**: 任務在 N 輪內收斂的機率。
- **Budget Efficiency**: 單位 Token 產出的修復品質。
- **Lesson Validity**: 寫回的教訓是否能在未來任務中有效避免同類失敗。

---
[Module - Core Orchestrator](../02_Modules/Module - Core Orchestrator.md)
