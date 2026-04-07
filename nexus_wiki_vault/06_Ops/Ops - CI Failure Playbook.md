---
aliases: '[CI [[troubleshooting|Troubleshooting]], [[troubleshooting|Troubleshooting]]
  Guide, Failure Recovery]'
confidence: high
last_compiled: '2026-04-06'
owner: agent
related_pages: ''
source_of_truth: scripts/ops/ci_gate.py
status: active
tags: '[ops, [[troubleshooting|troubleshooting]], failure, recovery]'
title: Ops - CI Failure Playbook
type: ops
version_scope: '[v22, v23]'
---



# Ops - CI Failure Playbook

## One-sentence summary
針對 Nexus [[CD Promotion Gate|CI Gate]] 常見紅燈案例的故障排除與修復手冊。 [Source: scripts/ops/ci_gate.py] [Code: 00_Home/System Overview.md]

## Role / responsibility
- **快速響應**: 提供一致性的初階診斷與修復路徑，縮短 Release 阻斷時間。 [Source: scripts/ops/ci_gate.py]
- **標準化復原**: 確保每位 Agent 修復紅燈時皆遵守 Nexus 治理規範 (DoD)。

## CI Failure Playbook (20 Cases Matrix)

| Tier | ID | Symptom | Common Root Cause | Fix / Repair Command | ReferenceSource |
|---|---|---|---|---|---|
| **P0** | `F-01` | [[Source - Coverage Heatmap|Wiki Coverage]] < 85% | 新檔案未建立對應 Wiki 頁面或缺少 `[Source]`。 | 執行 `wiki_coverage_audit` 找出缺口並補齊。 | [Source: scripts/ops/wiki_coverage_audit.py] |
| **P0** | `F-02` | Wiki Linter FAILED | Frontmatter 格式錯誤或 Source Path 物理不存在。 | `uv run scripts/ops/wiki_linter.py --strict` 檢核錯誤行。 | [Source: scripts/ops/wiki_linter.py] |
| **P0** | `F-03` | [[Ops - Wiki Drift Audit|Wiki Drift]] Detected | 代碼變更但 Wiki 內容未同步更新。 | 執行 `wiki_drift_audit` 並更新相關 Wiki 區塊。 | [Source: scripts/ops/wiki_drift_audit.py] |
| **P0** | `F-04` | [[CD Promotion Gate|CI Gate]] Broken Chain | `ci_gate.py` 本身發生語法錯誤。 | 檢查 `scripts/ops/ci_gate.py` 並執行 `--dry-run`。 | [Source: scripts/ops/ci_gate.py] |
| **P0** | `F-05` | Missing SOT Truth | Truth Registry 中的聲明與物理現實不符。 | 更新 `06_Ops/[[Ops - Truth Claims Register]].md` 並校正驗證命令。 | [Source: nexus_wiki_vault/06_Ops/Ops - Truth Claims Register.md]].md] |
| **P1** | `F-06` | Avg Health < 90% | 模型回應質量下降或發生邏輯混淆。 | `nexus:benchmark --tasks 5` 定位低分 [[task]] 並優化 Prompt。 | [Source: scripts/ops/ci_gate.py] |
| **P1** | `F-07` | Max Drift > 0.5 | Agent 執行路徑偏離預期真值鏈路。 | 檢查 `latest/write_proof.json` 確認漂移點。 | [Source: scripts/ops/ci_gate.py] |
| **P1** | `F-08` | Regression Tests Fail | 新功能破壞既有 v22 核心合約。 | 執行 `pytest tests/test_v9_regression_p1.py -vv`。 | [Source: tests/test_v9_regression_p1.py] |
| **P1** | `F-09` | Contract Auth Missing | DI Gate 發現注入工具未被授權。 | 在 `capability_gate.py` 中更新工具存取列表。 | [Source: nexus/core/capability_gate.py] |
| **P1** | `F-10` | Learning Velocity = 0 | 智慧層未能從 Episode 中提取有效晶體。 | 檢查 `crystal_factory.py` 邏輯與 RAG 召回。 | [Source: scripts/ops/calc_learning_velocity.py] |
| **P1** | `F-11` | Phase Health < 80% | 特定執行相位 (如 D 或 R) 失敗率過高。 | 檢查 `phase_health.py` 並調整特定相位 Guard 規則。 | [Source: nexus/core/phase_health.py] |
| **P1** | `F-12` | Token Budget Limit | 單次任務消耗超過設定閾值。 | 檢查 `cost_hook.py` 並優化上下文壓縮策略。 | [Source: nexus/core/cost_hook.py] |
| **P1** | `F-13` | Artifact Seal Fail | Arweave 或物理證據簽署失敗。 | 檢查 `arweave_uploader.py` 與 [[api|API]] 密鑰狀態。 | [Source: scripts/ops/arweave_v2.py] |
| **P2** | `F-14` | Warning Budget > 70 | 雖通過但非致命警告過多。 | 執行 `warning_budget_check.py` 導出警告清單並修復。 | [Source: scripts/ops/warning_budget_check.py] |
| **P2** | `F-15` | Orphan Wiki Page | 新頁面未被 `[[System Overview]]` 或矩陣連結。 | 在 `00_Home/[[System Overview]].md` 中新增對應章節連結。 | [Source: scripts/ops/wiki_linter.py] |
| **P2** | `F-16` | Stale Last-Verified | 真值聲明的校驗日期超過 7 天。 | 執行對應聲明的驗證命令並更新日期。 | [Source: nexus_wiki_vault/06_Ops/Ops - Truth Claims Register.md]].md] |
| **P2** | `F-17` | Missing Frontmatter | Wiki 頁面缺 `owner`, `source_of_truth` 等必填項。 | 使用 `01_PROTOCOLS_MASTER.md` 的模板補齊。 | [Source: scripts/ops/wiki_linter.py] |
| **P2** | `F-18` | Stale Waiver | Waiver 期限已到但尚未轉正或廢棄。 | 檢查 `06_Ops/[[Ops - Provenance Exceptions and Waivers]].md`。 | [Source: scripts/ops/wiki_linter.py] |
| **P2** | `F-19` | Benchmark Output Err | `ci_benchmark.csv` 格式損壞。 | 清除舊的 `.csv` 並重跑 `nexus:benchmark`。 | [Source: scripts/ops/ci_gate.py] |
| **P2** | `F-20` | Doc-Code Mismatch | [Source] 標籤指向的檔案已更名或刪除。 | 使用 `git log` 追蹤更名紀錄並更新 Wiki。 | [Source: scripts/ops/wiki_drift_audit.py] |

## Operational Recovery Workflow
1. **定位 (Locate)**: 查找 CI 輸出中的 `FAILED` 標誌。
2. **診斷 (Diagnose)**: 依 ID 查表 (本手冊) 確認根因。
3. **修復 (Repair)**: 執行 `Repair Command` 或手動修正。
4. **驗證 (Verify)**: 重跑 `Verification` 命令確保通關。

## Upstream
- **[[System Overview]]**: 系統總覽。
- **[[Ops - CI/CD Promotion Gate]]**: 提供信號定義。

## Downstream
- **[[Agent Onboarding - Command Pack]]**: 提供用於修復的具體命令流。

## Related modules / files
- `scripts/ops/ci_gate.py`: 故障診斷核心。 [Code: scripts/ops/ci_gate.py]

## Source notes
- v22 Engine Spec: 要求「失敗即教育」，要求記錄每個紅燈的修復路徑。 [Source: MUSE-NEXUS-Engine-Specification-v22-Eternal.md]

## Open questions / conflicts
- [ ] **Auto-healing**: 未來是否由 `ci_fix_generator.py` 自動執行 F-01 到 F-20 的修復。

---
Back to [[System Overview]]