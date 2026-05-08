---
aliases:
- Performance Benchmarks
- LeanCtx Audit
confidence: high
last_compiled: '2026-05-06'
owner: agent
related_pages:
- '[[06_Ops/Ops - CI Failure Playbook.md]]'
source_of_truth: scripts/ops/nexus_benchmark_preflight.py
status: draft
tags:
- ops
- benchmark
- performance
title: Ops - Performance Benchmarks
type: ops
version_scope: v26
---

# Ops - Performance Benchmarks

## One-sentence summary
聚焦核心 benchmark/資源消耗指標，將測試結果轉成可回滾治理判斷依據。 [Source: scripts/ops/nexus_benchmark_preflight.py]

## Role / responsibility
- 追蹤瓶頸指標與回歸風險。 [Source: scripts/ops/nexus_benchmark_preflight.py]
- 將基準結果轉換為可核對的門檻或回滾條件。 [Source: scripts/engine/nexus_cli.py]

## Upstream
- `scripts/ops/nexus_benchmark_preflight.py`
- `03_Flows/Flow - PXDRAC Runtime.md`

## Downstream
- `06_Ops/Ops - Governance SLO Dashboard.md`
- `06_Ops/Ops - CI Failure Playbook.md`

## Related modules / files
- `scripts/ops/nexus_leanctx_performance_audit.py`
- `nexus/core/metrics.py`

## Source notes
- 指標以本地 benchmark 預檢腳本輸出為主。 [Source: scripts/ops/nexus_benchmark_preflight.py]
- 回歸事件與回滾行為以 CI gate 日誌同步。 [Source: scripts/ops/ci_gate.py]

## Open questions / conflicts
- [ ] 是否將性能驗收拆成 Discovery / Fixing 雙套門檻？
- [ ] 實測回歸是否納入固定 baseline 比對窗（rolling window）？

> [!CAUTION]
> 文件中的部分歷史數據僅作為回顧資料，未替代實時可重跑結果。

## 現場測試節錄

| 指標 (Metric) | 安裝前 | 安裝後 | 結論 |
| :--- | :---: | :---: | :--- |
| p50 Latency | 0.0002s | 0.1922s | 監控中 |
| p95 Latency | 0.0003s | 0.2312s | 監控中 |
| Average Tokens | 1,252 | 114 | 節省 90.89% |
| Fallback Rate | 0% | 0% | 穩定 |
| Task Success | 100% | 100% | 穩定 |

## Link to System
[[System Overview]]
