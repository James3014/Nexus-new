# 🧬 Nexus Context Adapter Integration Note (P3)

## 1. Overview
The `ContextAdapter` acts as a transport-level proxy between the Nexus core (Legacy `ContextHub`) and the new `lean-ctx` provider. It enables a switchable, safe path for context assembly and enrichment while maintaining strict governance boundaries.

## 2. Non-Authoritative Boundary
A core architectural principle of this integration is the **Non-Authoritative Boundary** for `lean-ctx`.

- **Governance & Memory**: `lean-ctx` **cannot** own or manage memory (LTM/STM) or router governance. These remain the sole responsibility of the Nexus `ContextHub`.
- **Enrichment Only**: `lean-ctx` is used to provide faster or alternative context assembly. In repair cycles, its output is **merged** into the legacy pack, but legacy data (especially router/memory hints) always takes precedence or is preserved.
- **Implementation**: See `ContextAdapter.assemble_repair_pack` where legacy memory reminders and recommended skills are retained even if `lean-ctx` provides root cause enrichment.

## 3. Environment Switch
The provider is toggled via the `NEXUS_CONTEXT_PROVIDER` environment variable:

- `legacy` (default): Use the original `ContextHub` directly.
- `leanctx`: Attempt to use `lean-ctx` binary via subprocess.

## 4. Subprocess Fallback Logic
To ensure system stability, the `ContextAdapter` implements a **fail-safe** mechanism:
- **Timeouts**: Any call to `lean-ctx` that exceeds **5 seconds** is automatically aborted.
- **Errors**: If the `lean-ctx` binary is missing (FileNotFoundError) or returns a non-zero exit code, the adapter silently falls back to the legacy provider.
- **Logging**: Failed calls are logged as warnings to avoid interrupting the main execution flow while alerting operators to provider issues.

## 5. Risks and Rollback
| Risk | Impact | Mitigation / Rollback |
| :--- | :--- | :--- |
| `lean-ctx` binary corruption | Context assembly failure | Automatic fallback to `legacy` provider. |
| Performance degradation in `lean-ctx` | Latency increase | 5s timeout enforcement + manual `unset NEXUS_CONTEXT_PROVIDER`. |
| Memory/Governance leak | Decision instability | Non-authoritative boundary prevents `lean-ctx` from overwriting core governance fields. |

### Rollback Procedure
If `leanctx` mode causes instability:
1.  **Immediate**: `export NEXUS_CONTEXT_PROVIDER=legacy`.
2.  **Permanent**: Remove `NEXUS_CONTEXT_PROVIDER` from the environment configuration (e.g., `.env` or CI/CD secrets).

## 6. P4 Production-Readiness Checklist
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
| **P95 Latency** | < 2.0s for assembly | > 5.0s (triggers timeout) |
| **Fallback Success Rate** | 100% (No crash on failure) | Any crash due to provider failure |
| **Data Integrity** | Legacy memory/router data preserved | `leanctx` overwrites authoritative core fields |
