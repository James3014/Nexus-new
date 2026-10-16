# NEXUS Three-Pillar Refactor P77 Report - 2026-05-05

## [任務]
P73-P77 完成三支柱重構收斂：把 typed governance events、route receipt gap、research runtime gate、Flash A/B evidence 接成同一條可量測鏈路。

不跑 Pro；本輪只跑 Flash 12x2。

## [數據]

### P73 Typed Governance Events
- `run_auto_flow` 會在 artifact verified 時產生 `evidence_accepted` 與 `learning_decision=INGEST`。
- artifact 未驗證時產生 `audit_failed` 與 `learning_decision=DISCARD`。
- governance events 已進入 `nexus_usage_trace`、benchmark row、markdown report。
- Flash P75 report 顯示：
  - Governance event present：100.0%
  - Governance event count：2.00 / row
  - Evidence accepted event：100.0%
  - Learning decision event：100.0%

### P74 Route Receipt Gap
- `StateView.receipt_summary()` 已被 `ContextHub.make_pre_routing_decision()` 消費。
- actionable receipt gap 會把 `audit_level` 提升為 `full`。
- non-actionable gap（例如 `feature_flag_disabled`、`recommended_without_invocation`、`pending_executor`）不會誤升級。

### P75 Flash 12x2
- Model：`gemini-3-flash-preview`
- Scope：12 unique tasks x 2 trials = 24 rows per arm
- With Nexus：24/24 eligible，solve rate 100.0%
- Without Nexus：24/24 eligible，solve rate 58.3%
- Solve delta：+41.7%
- Semantic verified delta：+41.7%
- Trust mismatch：0.0% / 0.0%
- Public claim gate：PASS
- Performance claim gate：PASS
- Wearing claim gate：PASS
- Capability-specific claim gate：PASS
- Cost claim gate：PASS
- Per-capability public gate：PASS

### Route Quality
- Selected -> Invoked：97.9%
- Invoked -> Evidence：100.0%
- Evidence -> Outcome：100.0%
- Unnecessary Selected：2.1%

### Research Runtime
- Research preflight present：100.0%
- Research evidence present：100.0%
- Research gate passed：100.0%
- Research doctor pass：100.0%
- Claim probe eligible：100.0%
- Claim probe gate pass：100.0%
- Autoreason A/B/AB factory ready：79.2%
- Autoreason AB winner：79.2%

## [證據]

### 測試
```bash
uv run pytest -q tests/core/test_belief_engine.py tests/app/test_research_flow_service.py::test_run_auto_flow_populates_autoreason_from_candidate_summaries tests/benchmark/test_gemini_nexus_report.py::test_render_markdown_report_includes_research_preflight_metrics
# 8 passed

uv run pytest -q tests/core/test_belief_engine.py tests/core/test_event_bus.py tests/benchmark/test_gemini_nexus_report.py tests/app/test_research_flow_service.py
# 105 passed

uv run pytest -q tests/benchmark/test_capability_ab_runner.py tests/benchmark/test_gemini_nexus_report.py -k 'governance or receipt or extract_record or research_preflight'
# 15 passed
```

### Smoke
```bash
python3 scripts/ops/capability_route_smoke.py
# passed=true
# route_oracles/codeintel_hyper/core_governance_gates/belief_gate all returncode=0

python3 scripts/ops/research_stack_route_smoke.py --jsonl .nexus/reports/bench_route_8oracle_smoke/with_nexus_1777977040.jsonl --require-autoreason-invoked
# passed=true
```

### Flash Report
- `.nexus/reports/bench_gemini3flash_value12x2_20260505_p75/gemini_nexus_report_1777977255.md`
- `.nexus/reports/bench_gemini3flash_value12x2_20260505_p75/with_nexus_1777977255.jsonl`
- `.nexus/reports/bench_gemini3flash_value12x2_20260505_p75/without_nexus_1777977255.jsonl`
- `.nexus/reports/bench_gemini3flash_value12x2_20260505_p75/evidence_bundle.json`

## [殘債]
- Pro 驗證依使用者要求跳過。
- Ultra Review 仍是 selected-only，原因為 `feature_flag_disabled`；不納入 P77 public capability claim。
- DDTREE 仍多為 selected-only；需要 P87+ 針對 executor invocation gate 做獨立優化。
- With Nexus 平均 wall time 較 bare 高：84.75s vs 38.31s；本輪重點是 verified delivery，不是 latency optimization。
- Token measured rate With Nexus 為 95.8%，有 1 row estimated token；cost gate 仍 PASS。

## [下一步：P78-P86]

### P78 Storage Boundary Tests
- 新增 infra contract tests：禁止 `nexus.infrastructure.storage_implementations` 反向依賴 `nexus.services.*`。
- 驗證 tenant path 與 scoped access 不跨 tenant。

### P79 SearchProvider / SemanticSearcher
- `MemoryStorage` 保留 storage 原子操作。
- 搜尋邏輯移到 service/bridge seam。
- 移除 `LanceDBStorage.search()` 對 `MemoryRepository` 的違規 import。

### P80 Scoped Access
- 實作 `scoped_access(tenant_id)`，回傳 tenant-bound storage。
- 測試 tenant A 不可讀 tenant B。

### P81 MemoryService Safe Seams
- `MemoryService` 支援 repo/cache/jsonl/lock 注入。
- 修補 `ingest_episode()` 呼叫不存在 `update_table()` 的靜默失效路徑。

### P82 DistLock Fallback
- Redis 不可用時回 local file lock 或明確標記 `backend=noop`。
- 測試不可把 fallback 誤認為 distributed lock。

### P83 BeliefGate Protocol
- 顯式使用 `BeliefGate` protocol。
- 移除 Orchestrator 對 `MagicMock` 的直接檢查。

### P84 ContextHub Strict DI Mode
- 保留相容 fallback。
- 增加 strict DI mode，禁止 auto try-import。

### P85 Healing / Security / Telemetry
- 定義 `HealingArtifact`。
- `SecureRegistrySync` 改走 `IncomingMessageHandler` seam。
- `NexusTracer.record_belief_shift(task_id, old_val, new_val)`。

### P86 Verification
- targeted pytest。
- route smoke。
- research stack smoke。
- Flash 小回歸；不跑 Pro，除非另行指定。
