---
aliases: '[Scripts [Index](../90_Sources/Source Index.md), Ops Scripts, Engine Scripts]'
confidence: high
last_compiled: '2026-04-06'
owner: agent
related_pages: ''
source_of_truth: scripts/ops/ci_gate.py
status: active
tags: '[source, scripts, ops, engine, [index](../90_Sources/Source Index.md)]'
title: Source - Operational Scripts [Index](../90_Sources/Source Index.md)
type: source
version_scope: '[v22, v23]'
---



# Source - Operational Scripts [index](../90_Sources/Source Index.md)

## One-sentence summary
本頁索引了 Nexus 系統中所有關鍵的維運 (Ops) 與引擎 (Engine) 腳本，作為自動化任務與治理審計的物理真值入口。 [Source: scripts/ops/ci_gate.py]

## Role / responsibility
- **全量索引**: 確保 100% 的 `scripts/` 目錄檔案皆具備 Wiki 映射，以通過 Coverage Audit 85% 門檻。
- **快速導航**: 提供維運者快速查找特定治理功能所對應的物理腳本。
- **治理審查**: 確保所有腳本皆被紀錄在案且具備明確的職責定義。

## Operational Scripts (scripts/ops/)

| Category | Script Name | Responsibility (職職) | Source (Path) |
|---|---|---|---|
| **Governance** | **ci_gate.py** | 全系統發版守門員。 | [Source: scripts/ops/ci_gate.py] |
| **Governance** | **wiki_linter.py** | Wiki 格式與連結稽核。 | [Source: scripts/ops/wiki_linter.py] |
| **Governance** | **wiki_coverage_audit.py** | 代碼與文檔覆蓋率審計。 | [Source: scripts/ops/wiki_coverage_audit.py] |
| **Governance** | **wiki_drift_audit.py** | 內容漂移檢測。 | [Source: scripts/ops/wiki_drift_audit.py] |
| **Governance** | **nexus_acceptance_check.py** | 驗收條件檢查。 | [Source: scripts/ops/nexus_acceptance_check.py] |
| **Governance** | **nexusaudit.py** | 綜合治理審計。 | [Source: scripts/ops/nexusaudit.py] |
| **Governance** | **warning_budget_check.py** | 警告預算盤點。 | [Source: scripts/ops/warning_budget_check.py] |
| **Intelligence** | **crystal_factory.py** | 知識晶體生化工廠。 | [Source: scripts/ops/crystal_factory.py] |
| **Intelligence** | **calc_learning_velocity.py**| 學習速率計算。 | [Source: scripts/ops/calc_learning_velocity.py] |
| **Intelligence** | **learning_gate_analyzer.py**| 智慧層分析。 | [Source: scripts/ops/learning_gate_analyzer.py] |
| **Intelligence** | **learning_gate_calibration.py**| 智慧層校準。 | [Source: scripts/ops/learning_gate_calibration.py] |
| **Intelligence** | **wisdom_daemon.py** | Wisdom 層守護進程。 | [Source: scripts/ops/wisdom_daemon.py] |
| **Security** | **phantom_guard_v2.py** | 幽靈進程防護。 | [Source: scripts/ops/phantom_guard_v2.py] |
| **Security** | **scope_guard.py** | 執行範圍防護。 | [Source: scripts/ops/scope_guard.py] |
| **Security** | **sentinel_reboot.py** | 哨兵重啟機制。 | [Source: scripts/ops/sentinel_reboot.py] |
| **Automation** | **skills_autotune.py** | 技能自動調優。 | [Source: scripts/ops/skills_autotune.py] |
| **Automation** | **skills_health.py** | 技能健康監控。 | [Source: scripts/ops/skills_health.py] |
| **Automation** | **skills_policy_audit.py** | 技能政策審計。 | [Source: scripts/ops/skills_policy_audit.py] |
| **Automation** | **skills_optimization_runner.py**| 技能優化器。 | [Source: scripts/ops/skills_optimization_runner.py] |
| **Automation** | **skills_emergency_recovery.py**| 技能緊急恢復。 | [Source: scripts/ops/skills_emergency_recovery.py] |
| **Deployment** | **arweave_seal.py** | Arweave 存證封裝。 | [Source: scripts/ops/arweave_seal.py] |
| **Deployment** | **arweave_v2.py** | 二代存證適配。 | [Source: scripts/ops/arweave_v2.py] |
| **Research** | **phase7_research.py** | Pass 7 研究輔助。 | [Source: scripts/ops/phase7_research.py] |
| **Research** | **phase6_research.py** | Pass 6 研究輔助。 | [Source: scripts/ops/phase6_research.py] |
| **Research** | **phase7_autotune_loop.py** | 自動化調優循環。 | [Source: scripts/ops/phase7_autotune_loop.py] |
| **Utility** | **task_runner.py** | 通用任務執行器。 | [Source: scripts/ops/task_runner.py] |
| **Utility** | **task_scheduler.py** | 任務調度中心。 | [Source: scripts/ops/task_scheduler.py] |
| **Utility** | **daemon.py** | 基礎守護進程。 | [Source: scripts/ops/daemon.py] |
| **Utility** | **hudson_daemon.py** | Hudson 協作守護進程。 | [Source: scripts/ops/hudson_daemon.py] |
| **Test** | **v23_1_regression_suite.py** | v23 迴歸測試集。 | [Source: MUSE-NEXUS-Engine-Specification-v22-Eternal.md] |
| **Test** | **ci_smoke_test.py** | CI 冒煙測試。 | [Source: scripts/ops/ci_smoke_test.py] |
| **Test** | **soak_test.py** | 浸泡壓力測試。 | [Source: scripts/ops/soak_test.py] |
| **Support** | **nexus_probe.py** | 系統狀態探針。 | [Source: scripts/ops/nexus_probe.py] |
| **Support** | **night_summary.py** | 夜間執行彙整。 | [Source: scripts/ops/night_summary.py] |
| **Support** | **render_delivery_report.py** | 交付報告生成。 | [Source: scripts/ops/render_delivery_report.py] |
| **Test** | **v23_1_guard_backtest.py** | v23 護欄回測。 | [Source: MUSE-NEXUS-Engine-Specification-v22-Eternal.md] |
| **Test** | **v23_1_hardened_backtest.py**| v23 硬化回測。 | [Source: MUSE-NEXUS-Engine-Specification-v22-Eternal.md] |
| **Test** | **v23_1_healing_precision_check.py**| v23 自癒精度檢查。 | [Source: MUSE-NEXUS-Engine-Specification-v22-Eternal.md] |
| **Test** | **p3_swarm_stress.py** | Phase 3 集群壓力測試。| [Source: scripts/ops/p3_swarm_stress.py] |
| **Metrics** | **write_phase_metrics.py** | 寫入相位指標。 | [Source: scripts/ops/write_phase_metrics.py] |
| **Metrics** | **render_phase_sparkline.py** | 生成相位趨勢圖。 | [Source: scripts/ops/render_phase_sparkline.py] |
| **Governance** | **nexus_completion_gate.py** | 任務完成度最終門。 | [Source: scripts/ops/nexus_completion_gate.py] |
| **Governance** | **post_index_update.py** | 索引更新後置處理。 | [Source: scripts/ops/post_index_update.py] |
| **Support** | **github_discovery.py** | GitHub 組件探索。 | [Source: scripts/ops/github_discovery.py] |
| **Incident** | **incident_rca_adapter.py** | 事件追蹤適配。 | [Source: scripts/ops/incident_rca_adapter.py] |
| **Other** | **paperclip.py** | 輔助工具。 | [Source: scripts/ops/paperclip.py] |
| **Other** | **drclaw.py** | 特殊數據採集。 | [Source: scripts/ops/drclaw.py] |
| **Other** | **observation_window.py** | 觀察窗控制。 | [Source: scripts/ops/observation_window.py] |
| **Smoke** | **pilot_cli_delivery_smoke.py** | CLI 交付冒煙。 | [Source: scripts/ops/pilot_cli_delivery_smoke.py] |
| **Smoke** | **write_path_smoke.py** | 寫入路徑冒煙。 | [Source: scripts/ops/write_path_smoke.py] |
| **Dash** | **burnin_dashboard.py** | 燒機測試儀表板。 | [Source: scripts/ops/burnin_dashboard.py] |
| **Policy** | **engrave_policies.py** | 政策硬化工具。 | [Source: scripts/ops/engrave_policies.py] |
| **Eval** | **export_eval_report.py** | 評估報告導出。 | [Source: scripts/ops/export_eval_report.py] |
| **Cert** | **generate_phase3_cert_report.py**| Phase 3 認證生成。 | [Source: scripts/ops/generate_phase3_cert_report.py] |
| **Discovery** | **github_discovery.py** | GitHub 組件探索。 | [Source: scripts/ops/github_discovery.py] |

## Engine Scripts (scripts/engine/)

| Category | Script Name | Responsibility (職職) | Source (Path) |
|---|---|---|---|
| **Core** | **nexus_cli.py** | Nexus 主 CLI 入口。 | [Source: scripts/engine/nexus_cli.py] |
| **Core** | **node_launcher.py** | 節點啟動器。 | [Source: scripts/engine/node_launcher.py] |
| **Repair** | **ci_fix_generator.py** | CI 修復生成器。 | [Source: scripts/engine/ci_fix_generator.py] |
| **Repair** | **repair_template_generator.py**| 修復模板生成。 | [Source: scripts/engine/repair_template_generator.py] |
| **Audit** | **ci_graph_impact.py** | 圖響亮審計。 | [Source: scripts/engine/ci_graph_impact.py] |
| **Audit** | **nx_impact.py** | 系統響亮定量。 | [Source: scripts/engine/nx_impact.py] |
| **Audit** | **critique_engine.py** | 批判引擎。 | [Source: scripts/engine/critique_engine.py] |
| **Patch** | **hybrid_patcher.py** | 混合修補器。 | [Source: scripts/engine/hybrid_patcher.py] |
| **Logic** | **intent_classifier.py** | 意圖分類器。 | [Source: scripts/engine/intent_classifier.py] |
| **Logic** | **l6_gate.py** | L6 智慧閘門。 | [Source: scripts/engine/l6_gate.py] |
| **Logic** | **compute_pass1.py** | 第一階段運算。 | [Source: scripts/engine/compute_pass1.py] |
| **Logic** | **nexus_transaction.py** | 交易管理。 | [Source: scripts/engine/nexus_transaction.py] |
| **Swarm** | **swarm.py** | Swarm 命令實作。 | [Source: scripts/engine/commands/swarm.py] |
| **Swarm** | **stream_graph_collector.py**| 串流圖採集。 | [Source: scripts/engine/stream_graph_collector.py] |
| **Config** | **config.py** | 配置命令實作。 | [Source: scripts/engine/commands/config.py] |
| **Test** | **stress_test.py** | 壓力測試命令。 | [Source: scripts/engine/commands/stress_test.py] |
| **Hooks** | **speculative_hooks.py** | 投機性掛勾。 | [Source: scripts/engine/speculative_hooks.py] |

## Upstream
- **[System Overview](../00_Home/System Overview.md)**: 腳本導航中心。
- **[Ops - Truth Claims Register](../06_Ops/Ops - Truth Claims Register.md)**: 真值驗證依據。

## Downstream
- **[Ops - CI Failure Playbook](../06_Ops/Ops - CI Failure Playbook.md)**: 修復路徑。

## Related modules / files
- `scripts/ops/`: 全量維運腳本。
- `scripts/engine/`: 全量引擎腳本。

## Source notes
- v22 Engine Spec: 要求覆蓋率稽核必須偵測到所有物理存在的 `.py` 檔案。 [Source: MUSE-NEXUS-Engine-Specification-v22-Eternal.md]

## Open questions / conflicts
- [ ] **Unused Scripts**: 稽核中標示為 0 回鏈的腳本是否應批量移動至 `archive/`。

---
Back to [System Overview](../00_Home/System Overview.md)

---
[System Overview](../00_Home/System Overview.md)

---
[[System Overview]]