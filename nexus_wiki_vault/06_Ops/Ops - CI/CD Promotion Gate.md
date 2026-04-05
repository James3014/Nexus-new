---
title: Ops - CI/CD Promotion Gate
aliases: [Promotion Gate, CI Gate, Acceptance Logic]
type: ops
status: active
version_scope: [v17.1, v22, v23]
source_of_truth: scripts/ops/ci_gate.py
raw_sources:
  - nexus_acceptance_check.py
  - warning_budget_check.py
  - MUSE-NEXUS Engine Specification v22
related_pages:
  - "[[Module - State Contracts]]"
  - "[[Protocol - Evidence Chain]]"
  - "[[Ops - CI/CD Promotion Gate]]"
  - "[[System Overview]]"
  - "[[System - Unknowns and Conflicts]]"
  - "[[System - Unknowns and Conflicts]]"
tags: [ops, ci, gate, acceptance, quality]
last_compiled: 2026-04-06
confidence: high
owner: agent
---

# Ops - CI/CD Promotion Gate

## One-sentence summary
本頁定義 Nexus 任務從研發環境晉升至生產環境的 5 大品質門禁 (Quality Gates) 與硬性指標閾值。

## Role / responsibility
- **最終決策**: 決定任務是否符合 `Crystallize` (C) 階段的正式封裝要求。
- **自動化審計**: 執行 `TRU-101` 協議，校驗代碼與治理軌跡的一致性。
- **風險阻斷**: 當 Health 降低或 Drift 升高時自動中斷 Promotion。

## 5-Step Promotion Sequence

### 1. Regression & E2E Gate
- **執行指令**: `pytest tests/contracts/ tests/test_container_orchestration.py`
- **目的**: 確保基礎 DI (Dependency Injection) 與 Core 契約未發生迴歸。

### 2. Warning Budget Check
- **門檻**: **Threshold 70%** (由 `warning_budget_check.py` 判定)。
- **目的**: 防止累積過多 Non-terminal warnings 導致環境噪音。

### 3. Benchmark Replay (Mini-lane)
- **指令**: `nexus:benchmark --tasks 10`
- **實體檢核**: 使用 `[[Ops - Truth Claims Register]]` 驗證本地環境是否存在真值斷裂。 [Source: Page: Ops - Truth Claims Register]
- **主約更新**: 當程式碼變更時，優先更新對應的 Wiki [Source: path] 標籤。
- **指標**: 
    - **Avg Health > 90%**: 任務成功率基準線。 [Source: `ci_gate.py` L137]
    - **Max Drift < 0.5**: 物理狀態與預期狀態的偏移上限。 [Source: `ci_gate.py` L140]
    - **Min Phase Health > 80%**: 確保單一相位 (如 D 或 R) 無重大短板。 [Source: `ci_gate.py` L143]

### 4. Evidence Integrity (Repair Honesty)
- **路徑**: `.nexus/runs/latest/write_proof.json`
- **目的**: 驗證 `N9-REPAIR` 證據是否存在，確保所有的代碼變更均有實體寫入憑證。

### 5. Learning Velocity & Sparkline
- **指標**: `Learning Velocity` (經驗累積速率)。
- **審計**: `TRU-101` Token 捕捉狀態檢查，禁止在 Token 捕捉失敗的情況下晉升。

## Upstream
- **Phase A (Audit)**: 提供 `audit_result.json` 作為輸入。
- **Benchmark Suite**: 提供實體效能與健康數據。

## Downstream
- **Phase C (Crystallize)**: 門禁通過後，執行 `nexus:crystal` 進行經驗落盤。
- **[[Ops - Acceptance and Release]]**: 作為 Release Gate 的最終前置條件。

## Related modules / files
- `scripts/ops/ci_gate.py`: 門禁執行引擎。
- `nexus_acceptance_check.py`: 特定任務的驗收邏輯。

## Source notes
- v22 Engine Spec Part 8: 定義 DoD (Definition of Done) 清單。
- ci_gate.py L137-L145: 硬性 Threshold 定義位置。

## v22.1.1 Production Addendum (Verified Baseline)
- **Baseline commit**: `619e460`（目前 repo HEAD）。 [Source: MUSE-NEXUS-Engine-Specification-v22-Eternal.md]
- **Release tags present**: `v22.1.0-prod`, `v22.1.1-prod`。 [Source: MUSE-NEXUS-Engine-Specification-v22-Eternal.md]
- **Gate health (dry-run)**: `venv_python`, `contracts_dir`, `benchmark_script` 目前可通過。 [Source: scripts/ops/ci_gate.py]
- **Release discipline**: Production promotion 仍以 `ci_gate --strict` + Wiki governance + 實體證據清單 `[[Ops - Truth Claims Register]]` 為準，不因外部報告而豁免。 [Source: scripts/ops/ci_gate.py]

## Open questions / conflicts
- [ ] **Manual Override**: 是否允許人類在 `Health < 90%` 但環境受限的情況下強制 Bypass。
- [ ] **v23.1 Handoff**: 門禁完成後 `last_handoff.json` 的鎖定順序。
