# NEXUS Refactor P86 Report - 2026-05-05

## [任務]
P78-P86 完成五大重構缺口的最小可驗證切片：Storage Decoupling、BeliefGate、Secure Transport seam、HealingArtifact contract、Semantic Telemetry，並以 route smoke 驗證新路由仍可調用全能力。

## [數據]

### P78-P82 Storage Decoupling
- `LanceDBStorage.search()` 不再從 infrastructure 層 import `nexus.services.memory_repository`。
- `LanceDBStorage.scoped_access(tenant_id)` 已支援 tenant-bound view。
- tenant scoped search 已驗證不跨 tenant 讀取。
- `DistLock` Redis unavailable 時改為明確 `backend=local_file`，不再假裝 distributed lock acquired。
- `MemoryRepository.update_table()` 已補上，修掉 `MemoryService.ingest_episode()` 呼叫不存在方法的靜默失效風險。
- `MemoryService` 已支援 injected repo / redis_client，保留預設相容行為。

### P83 BeliefGate
- `BeliefGate` protocol 保留為 Orchestrator 依賴面。
- `NexusOrchestrator` 不再直接 import / isinstance 檢查 `MagicMock`。
- 缺失依賴改由 method capability 判斷與 null fallback seam 處理。

### P85 Healing / Secure Transport / Telemetry
- 新增 frozen `HealingArtifact` contract。
- 新增 `IncomingMessageHandler` protocol 與 `RegistryMessageHandler`。
- `SecureRegistrySync._handle_client()` 收斂為 TLS peer 驗證、JSON line IO、handler dispatch。
- `NexusTracer.record_belief_shift(task_id, old_val, new_val)` 已新增，會產生 `belief.shift` span event。

### P86 Route Verification
- Route smoke：PASS。
- Research stack smoke：PASS。
- 最新 route smoke 8-oracle：8 rows，全 SUCCESS。
- Route quality：
  - selected_to_invoked_rate：1.0
  - invoked_to_evidence_rate：1.0213
  - evidence_to_outcome_rate：0.9792
  - unnecessary_selected_rate：0.0
- Research stack smoke：
  - autoreason_selected：8
  - autoreason_invoked：8
  - autoreason_ab_factory_ready：8
  - autoreason_ab_winner：8
  - research_doctor_pass：8
  - claim_probe_gate_passed：8
  - checkpoints_seen：candidate_tournament_receipt、claim_citation_verification、fixed_budget_metric_contract、packet_session_ledger

## [證據]

```bash
uv run pytest -q tests/infrastructure/test_storage_implementations.py tests/infrastructure/test_dist_lock.py tests/services/test_memory_repository.py tests/test_memory.py
# 17 passed

uv run pytest -q tests/core/test_belief_engine.py tests/core/test_belief_contracts.py tests/security/test_secure_sync.py tests/telemetry/test_tracer.py
# 18 passed

uv run pytest -q tests/infrastructure/test_storage_implementations.py tests/infrastructure/test_dist_lock.py tests/services/test_memory_repository.py tests/test_memory.py tests/core/test_belief_engine.py tests/core/test_belief_contracts.py tests/security/test_secure_sync.py tests/telemetry/test_tracer.py
# 35 passed

python3 scripts/ops/capability_route_smoke.py
# passed=true

python3 scripts/ops/research_stack_route_smoke.py --jsonl .nexus/reports/bench_route_8oracle_smoke/with_nexus_1777980623.jsonl --require-autoreason-invoked
# passed=true
```

## [殘債]
- `MemoryService` 尚未完全移除所有 JSONL direct open；本輪只完成注入 seam 與最危險的 infra reverse import / update_table bug。
- `MemPalace.list_beliefs()` 與 router bias provider 尚未完全改成注入 store，延後 P87+。
- `HealingArtifact` 尚未接 artifact store / RLM trace / EventBus persistence，延後 P87+。
- `record_belief_shift()` 尚未自動串接 `BeliefEngine.process_audit_outcome()`，延後 P87+。
- `SecureRegistrySync` 尚未做 request size limit、protocol versioning、CN allowlist，延後 P87+。

## [下一步：P87-P95]

### P87 MemPalace Storage Provider
- `list_beliefs()` 改用 injected belief store。
- `get_router_bias()` 改用 config provider。
- 保留舊路徑相容 adapter。

### P88 MemoryService JSONL Store
- 抽 `JsonlStore` seam。
- `fault_lessons` / `policy_memory` read-write 走 injected store。
- 測試 service 初始化不碰 Redis/LanceDB/open。

### P89 HealingArtifact Persistence
- HealingArtifact 寫入 `.nexus/artifacts/healing/`。
- route/report 能引用 healing artifact id。

### P90 Belief Shift Telemetry Wiring
- `BeliefEngine.process_audit_outcome()` 自動呼叫 `record_belief_shift()`。
- 報告加入 belief shift count / avg delta。

### P91 Secure Sync Hardening
- request size limit。
- typed JSON error response。
- CN allowlist / node authorization seam。

### P92 Ultra Review Invocation Gate
- 處理 `feature_flag_disabled` 造成 selected-only。
- 避免 public capability claim 仍被 selected-only 擋住。

### P93 DDTree Invocation Gate
- 把 selected-only 轉成 clear eligibility 或 actual invocation。
- route quality 維持 unnecessary_selected <= 5%。

### P94 Flash Regression
- Flash 12x2 或小回歸，依 P92/P93 變更大小決定。
- 不跑 Pro，除非使用者指定。

### P95 Final Public Report
- 產出中文公開報告：能力提升 / 治理可交付 / 成本效率 / route quality。
