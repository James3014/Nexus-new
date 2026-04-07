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
Back to [[System Overview]]---
aliases:
- Release Gate
- Acceptance Policy
confidence: high
last_compiled: 2026-04-06
owner: agent
related_pages:
- Ops - CI/[[CD Promotion Gate|Promotion Gate]]|[[CD [[CD Promotion Gate|Promotion
  Gate]]|CD [[CD Promotion Gate|Promotion Gate]]]]]]
- '[[Protocol - Evidence Map|Evidence Map]]|[[Protocol - [[Protocol - Evidence Map|Evidence
  Map]]|Protocol - [[Protocol - Evidence Map|Evidence Map]]]]]]'
- '[[System Overview|System Overview]]'
- '[[System - Unknowns and Conflicts|Unknowns]] and Conflicts|[[System - [[System
  - Unknowns and Conflicts|Unknowns]] and Conflicts|System - [[System - Unknowns and
  Conflicts|Unknowns]] and Conflicts]]]]'
source_of_truth: scripts/ops/nexus_release_gate.sh
status: active
tags:
- ops
- release
- acceptance
- gate
title: Ops - Acceptance and Release
type: ops
version_scope:
- v17.1
- v22
- v23
---



# Ops - Acceptance and Release

## One-sentence summary
本頁定義 Nexus 軟體正式封版與發布的流程，對齊測試、審計、Manifest 與環境清理的硬性要求。 [Source: MUSE-NEXUS-Engine-Specification-v22-Eternal.md]

## Role / responsibility
- **發布阻斷**: 在未滿足 `[[CD Promotion Gate|Promotion Gate]]` 指標前禁止執行 `git tag`。 [Source: 00_Home/System Overview.md]
- **環境清場**: 要求發布前工作區 (Worktree) 必須 100% 乾淨且通過 `git audit`。 [Source: 00_Home/System Overview.md]
- **同步確認**: 確保 Wiki 與 Repo 之內的 [[README]] 與 Spec 已同步更新。 [Source: MUSE-NEXUS-Engine-Specification-v22-Eternal.md]

## Upstream
- **[[Ops - CI/CD Promotion Gate]]**: 提供晉升核准。
- **Build Server**: 完成底層封裝。

## Downstream
- **Production Environment**: 正式部署。
- **Release Registry**: 更新全域版本號。 [Source: nexus_wiki_vault/90_Sources/Source Index.md]]`]

## Related modules / files
- `scripts/ops/nexus_release_gate.sh`: 正式發布腳本。 [Code: 00_Home/System Overview.md]
- `scripts/ops/nexus_completion_gate.py`: 任務完成檢核器。 [Code: 00_Home/System Overview.md]

## Source notes
- Hardened v17.1 Spec: 定義 acceptance reports 的結構要求。
- v22 Engine Spec: 確立「無證據不發布」的核心紀律。 [Source: MUSE-NEXUS-Engine-Specification-v22-Eternal.md]

## Open questions / conflicts
- [ ] **Hotfix Policy**: 針對緊急修復是否允許 Bypass 部分門禁指標。
- [ ] **Staging Layer**: 是否需要在 Production 前新增一個 Staging 相位。

---
[[System Overview]]
---
title: Ops - Closeout Hard Gate
aliases: [Closeout Gate, Done Contract Gate]
type: ops
status: active
version_scope: [v22, v23]
source_of_truth: repo-root
related_pages:
  - "[[System Overview]]"
  - "[[Ops - CI/CD Promotion Gate]]"
  - "[[Ops - Governance Changelog]]"
tags: [ops, closeout, governance, gate]
last_compiled: 2026-04-07
confidence: high
owner: agent
---
# Ops - Closeout Hard Gate

## One-sentence summary
定義任務完成前的最終阻斷閘門，未通過 `nexus:closeout` 禁止宣告 PASS。 [Source: scripts/ops/closeout_guard.py]

## Role / responsibility
- **完成宣告阻斷**: 要求任務在回報完成前提供可驗證 `done_contract`。 [Source: AGENT_PROTOCOL_v2.md]
- **契約校驗**: 驗證 `linter_exit_code`、`ci_gate_exit_code`、`required_tests_passed`、`commit_sha`、`changed_files`。 [Source: scripts/ops/closeout_guard.py]

## Upstream
- **實作完成階段**: 任務完成後產生 `.nexus/reports/done_contract.json`。 [Source: scripts/engine/nexus_cli.py]
- **協議約束**: `AGENT_PROTOCOL_v2.md` 定義未過 closeout 禁止結案。 [Source: AGENT_PROTOCOL_v2.md]

## Downstream
- **[[Ops - CI/CD Promotion Gate]]**: Closeout 作為 release 前的人機協作最終門檻之一。 [Source: scripts/ops/ci_gate.py]
- **[[Ops - Governance Changelog]]**: 記錄 closeout 規則變動與升級。 [Source: nexus_wiki_vault/06_Ops/Ops - Governance Changelog.md]

## Related modules / files
- `scripts/ops/closeout_guard.py`: done contract 驗證器。
- `scripts/engine/nexus_cli.py`: `nexus:closeout` 指令入口。
- `tests/ops/test_closeout_guard.py`: closeout guard 單元測試。
- `tests/test_cli_commands.py`: `nexus:closeout` CLI 測試。

## Source notes
- 建議標準流程：先完成測試與 CI gate，再執行 `nexus:closeout`。 [Source: docs/ops/closeout_enforcement.md]
- 任何缺失欄位或非零 exit code 均應阻斷完成回報。 [Source: scripts/ops/closeout_guard.py]

## Open questions / conflicts
- [ ] 是否應在 `ci_gate.py` 增加可選 `--require-closeout-contract` 模式以統一入口阻斷。
- [ ] 是否需要將 done contract schema 提升為 JSON Schema 並加入 CI 檢查。
---
aliases: '[Intelligence Governance, [[MUSE_ENGINE_SPEC|v23 Wisdom]]]'
confidence: high
last_compiled: '2026-04-06'
owner: agent
related_pages: ''
source_of_truth: '[[v23_wisdom_spec|v23_wisdom_spec]].md'
status: active
tags: '[ops, wisdom, intelligence, governance, v23]'
title: Ops - Wisdom Layer
type: ops
version_scope: '[v23]'
---



# Ops - Wisdom Layer

## One-sentence summary
本頁定義 v23 智慧治理層的運行邏輯、共識護欄與模式檢索機制。 [Source: MUSE-NEXUS-Engine-Specification-v22-Eternal.md]] Supplement]

## Role / responsibility
- **決策偏好 (Bias)**: 從 `Memory Repository` 提取相似教訓以引導當前任務路由。 [Source: memory_indexer.py]
- **共識護欄 (ConsensusGuard)**: 在高風險操作前執行多重判斷與幻覺檢測。 [Code: consensus_guard.py]
- **自我修復 (PredictiveHealer)**: 在故障發生前預測並觸發 Rollback 或修補。 [Code: predictive_healer.py]

## Upstream
- **[[Module - Memory Repository]]**: 提供向量經驗底座。
- **[[SYSTEM_ARCHITECTURE_BLUEPRINT|PXDRAC]] Feedback Loop**: 提供實時執行結果回饋。

## Downstream
- **Orchestrator Decision Node**: 修正 `nexus_cli.py` 的調度路徑。 [Code: nexus_cli.py]
- **[[Ops - CI/CD Promotion Gate]]**: 提供智慧審計結果。

## Related modules / files
- `nexus/intelligence/online_learner.py`: 在線學習引擎。 [Code: online_learner.py]
- `nexus/delivery/phantom_guard.py`: 幽靈狀態校驗。 [Code: 00_Home/System Overview.md]

## Source notes
- [[MUSE_ENGINE_SPEC|v23 Wisdom]] Supplement: 詳細定義「智慧層（v23）疊加於主線（v22）」的版本邊界。 [Source: MUSE-NEXUS-Engine-Specification-v22-Eternal.md]

## Open questions / conflicts
- [ ] **Risk Threshold**: `--risk` 參數的具體數值如何與實施阻斷邏輯對接。
- [ ] **Knowledge Decay**: 智慧層是否應具備「遺忘」過時模式的能力。

---
[[System Overview]]
