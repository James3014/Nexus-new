# 01_PERF_INDEX.md

**Purpose**: Master index for the v22.5 Performance Regression Pack.
**Source**: Performance Audit v22.5
**Commit**: v22.5-stable-baseline
**Generated_at**: 2026-04-08 06:35

---

## 🏗️ Intelligence Layer (01-05)
- [01_PERF_INDEX.md](file:///Users/jameschen/Workspace/nexus/perf_regression_pack_v22.5/01_PERF_INDEX.md)
- [02_REGRESSION_BASELINE_VS_CURRENT.md](file:///Users/jameschen/Workspace/nexus/perf_regression_pack_v22.5/02_REGRESSION_BASELINE_VS_CURRENT.md)
- [03_WORKLOAD_AND_TEST_CONDITIONS.md](file:///Users/jameschen/Workspace/nexus/perf_regression_pack_v22.5/03_WORKLOAD_AND_TEST_CONDITIONS.md)
- [04_TRACE_TIMELINE_BREAKDOWN.md](file:///Users/jameschen/Workspace/nexus/perf_regression_pack_v22.5/04_TRACE_TIMELINE_BREAKDOWN.md)
- [05_ROOT_CAUSE_HYPOTHESIS_MATRIX.md](file:///Users/jameschen/Workspace/nexus/perf_regression_pack_v22.5/05_ROOT_CAUSE_HYPOTHESIS_MATRIX.md)

## 🛠️ Engineering Internals (06-13)
- [06_ORCHESTRATOR_CODE_PATHS.md](file:///Users/jameschen/Workspace/nexus/perf_regression_pack_v22.5/06_ORCHESTRATOR_CODE_PATHS.md)
- [07_GUARD_HEALER_DECISION_CHAIN.md](file:///Users/jameschen/Workspace/nexus/perf_regression_pack_v22.5/07_GUARD_HEALER_DECISION_CHAIN.md)
- [11_RECOMMENDED_FIX_ASYNC_BLUEPRINT.md](file:///Users/jameschen/Workspace/nexus/perf_regression_pack_v22.5/11_RECOMMENDED_FIX_ASYNC_BLUEPRINT.md)

## ✅ Validation & Reports (14-26)
- [25_PATCH_B_REPORT.md](file:///Users/jameschen/Workspace/nexus/perf_regression_pack_v22.5/25_PATCH_B_REPORT.md)
- [26_PATCH_C_PARALLEL_REPORT.md](file:///Users/jameschen/Workspace/nexus/perf_regression_pack_v22.5/26_PATCH_C_PARALLEL_REPORT.md)

---

# 02_REGRESSION_BASELINE_VS_CURRENT.md

## 1. Metric: Serialization Latency
- **Baseline (v21.0)**: 50ms per tool call.
- **Regression (v22.0)**: 450ms per tool call (Bottleneck detected).
- **Target (v23.5)**: < 30ms via Direct-Buffer IO.

## 2. Metric: Parallel Swarm Concurrency
- **Baseline**: 10 active agents (No drift).
- **Current**: 100 active agents (Evidence corruption detected at > 50).

---

# 05_ROOT_CAUSE_HYPOTHESIS_MATRIX.md

| ID | Hypothesis | Severity | Status |
| :-- | :-- | :-- | :-- |
| **RC-01** | Synchronous I/O Blocking Orchestration | **CRITICAL** | **PROVED** |
| **RC-02** | Python GIL Bottleneck in Multi-Session | **MED** | **MITIGATED** |
| **RC-03** | LanceDB Inverted Index Lock | **HIGH** | **FIXED** |
