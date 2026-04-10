# 🧬 Nexus Context Adapter Integration Note (P3)

## 1. Overview
The `ContextAdapter` acts as a transport-level proxy between the Nexus core (Legacy `ContextHub`) and the new `lean-ctx` provider. It enables a switchable, safe path for context assembly and enrichment while maintaining strict governance boundaries.

## 2. Non-Authoritative Boundary
A core architectural principle of this integration is the **Non-Authoritative Boundary** for `lean-ctx`.

- **Governance & Memory**: `lean-ctx` **cannot** own or manage memory (LTM/STM) or router governance. These remain the sole responsibility of the Nexus `ContextHub`.
- **Enrichment Only**: `lean-ctx` is used to provide faster or alternative context assembly. In repair cycles, its output is **merged** into the legacy pack, but legacy data (especially router/memory hints) always takes precedence or is preserved.
- **Implementation**: See `ContextAdapter.assemble_repair_pack` where legacy memory reminders and recommended skills are retained even if `lean-ctx` provides root cause enrichment.

## 3. Optional-External Strategy
Nexus ships a built-in `ContextAdapter`, but `lean-ctx` is treated as an **optional external binary**.

- **Adapter is built-in**: No extra install is needed for default Nexus behavior.
- **Binary is optional**: `lean-ctx` is only required when operators explicitly enable `NEXUS_CONTEXT_PROVIDER=leanctx`.
- **Safe default**: `legacy` remains the default provider and must keep working without `lean-ctx` installed.

## 4. Environment Switch
The provider is toggled via the `NEXUS_CONTEXT_PROVIDER` environment variable:

- `legacy` (default): Use the original `ContextHub` directly.
- `leanctx`: Attempt to use `lean-ctx` binary via subprocess.

### User Impact
- Users who do not install `lean-ctx` are unaffected as long as they keep `legacy` mode.
- Users who select `leanctx` mode without the binary will see warnings and automatic fallback to `legacy`.

## 5. Subprocess Fallback Logic
To ensure system stability, the `ContextAdapter` implements a **fail-safe** mechanism:
- **Timeouts**: Any call to `lean-ctx` that exceeds **5 seconds** is automatically aborted.
- **Errors**: If the `lean-ctx` binary is missing (FileNotFoundError) or returns a non-zero exit code, the adapter silently falls back to the legacy provider.
- **Logging**: Failed calls are logged as warnings to avoid interrupting the main execution flow while alerting operators to provider issues.

## 6. Risks and Rollback
| Risk | Impact | Mitigation / Rollback |
| :--- | :--- | :--- |
| `lean-ctx` binary corruption | Context assembly failure | Automatic fallback to `legacy` provider. |
| Performance degradation in `lean-ctx` | Latency increase | 5s timeout enforcement + manual `unset NEXUS_CONTEXT_PROVIDER`. |
| Memory/Governance leak | Decision instability | Non-authoritative boundary prevents `lean-ctx` from overwriting core governance fields. |

### Rollback Procedure
If `leanctx` mode causes instability:
1.  **Immediate**: `export NEXUS_CONTEXT_PROVIDER=legacy`.
2.  **Permanent**: Remove `NEXUS_CONTEXT_PROVIDER` from the environment configuration (e.g., `.env` or CI/CD secrets).

## 7. P4 Production-Readiness Checklist
🎯 **Task-4: Docs (Rollout & Go/No-Go)**

### Rollout Checklist (P4)
- [ ] **Contract Verification**: All contract drift tests (timeout, malformed JSON, missing binary) pass in CI.
- [ ] **Performance Baseline**: Simulated `leanctx` benchmark show latency within 10% of legacy for assembly.
- [ ] **Fallback Verification**: End-to-end smoke test confirms fallback to legacy when `lean-ctx` binary is simulated-broken.
- [ ] **Simulated CI Gate**: `nexus-smoke.yml` successfully runs the `leanctx-mode` test leg.
- [ ] **Observability**: Warning logs for `lean-ctx` failures are visible in standard output/logs.

### Go/No-Go Criteria
| Metric | Threshold (Go) | Threshold (No-Go) |
| :--- | :--- | :--- |
| **Contract Stability** | 100% pass on drift tests | Any regression in fallback logic |
| **Latency Delta** | `latency_delta_pct <= 5` | `latency_delta_pct > 5` |
| **Token Delta** | `token_delta_pct < 0` | `token_delta_pct >= 0` |
| **Task Success Delta** | `task_success_rate_delta_pct >= 0` | `task_success_rate_delta_pct < 0` |
| **Fallback Rate** | `fallback_rate < 0.05` | `fallback_rate >= 0.05` |
| **Data Integrity** | Legacy memory/router data preserved | `leanctx` overwrites authoritative core fields |

## 9. 🛡️ Nexus 智慧壓縮執行規約 (Rules Hardened)

為確保 `lean-ctx` 在生產環境下不產生語意偏移，所有 Agent 必須遵守以下物理規則：

### A. 任務模式強制匹配表 (Enforced Mode Map)

| 任務行為 (Task Keyword) | 壓縮模式 | 強制等級 | 理由 |
| :--- | :--- | :--- | :--- |
| `list`, `scan`, `overview` | **-m signatures** | P0 (強制) | 極大化結構探索效率 (-90% Token) |
| `explain`, `logic`, `review` | **-m aggressive** | P1 (推薦) | 平衡邏輯完整性與成本 |
| `fix`, `bug`, `rca`, `math` | **-m full (禁用)** | **CRITICAL** | **防止關鍵業務邏輯在壓縮中遺失** |

### B. CI 守門與物理存證 (Governance Gates)
1. **每月審計**: 必須執行 `scripts/ops/nexus_leanctx_performance_audit.py`。
2. **阻斷標準 (Stop-ship)**:
   - 任何變更導致 **P95 Latency > 500ms**。
   - 任何變更導致 **Fallback Rate > 5%**。
3. **證據連結**: `acceptance-check` 必須包含 `lean-ctx` 的版本校準資訊。

[NEXUS IDENTITY: v22.1 PRODUCTION-READY]
