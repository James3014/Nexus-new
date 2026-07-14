# Nexus Benchmark Routing Analysis: May 2026 vs June 2026 vs H5~H8

**Date**: 2026-06-29

---

## May 2026: Gemini+Nexus 六階段路由

### 成績

| Benchmark | Gemini+Nexus | Gemini Bare | Delta |
|---|---|---|---|
| P75 Flash 12x2 (2026-05-05) | 24/24 (100%) | 14/24 (58.3%) | +41.7pp |
| PUBLICATION_READY 12x2 (2026-05-20) | 24/24 (100%) | 16/24 (66.7%) | +33.3pp |
| P90 Three-Arm Flash/Pro (2026-05-10) | solve=1.0, verified=1.0 | — | PASS all arms |
| Neutral Fixture 18x3 Pro (April 2026) | 54/54 (100%) | 51/54 (94.4%) | +5.56pp |

### 路由架構：CapabilityPlanner

完整 S,P,X,D,R,A,C 六階段路由，由 `nexus/engine/capability_planner.py` 驅動。

### 實際 invoked 能力（P44 結案）
codeintel, research, hyper, nightshift, swarm, drone, ultra_review, autoreason, ddtree, lancedb, memory, mempalace_gate, belief, artifact_gate, claim_gate, delivery_gate, semantic_searcher, swarm_quiet_moment, harness_preflight_sensor, bdd_acceptance_skill

---

## June 2026: Local Model + LocalHeal 獨立管線

### 路由架構：HealOrchestrator

五階段：Reproduction → Planning → Localization → PatchSynthesis → Verification

### 成功解題紀錄
```
d6d01c3ed 8/8 SUCCESS benchmark with 7B+14B dynamic routing via BattlesuitGateway
4097bdeaf Task 01 astropy_14526 PASS
01d6a0f14 Task 02 sympy_polys_01 PASS
f1fc65da9 Task 03 nexus_verifier_http_01 PASS
7652f2b3a Task 04 nexus_protocol_boundary_01 PASS
```

### 關鍵優化
- SolidSearchReplaceProtocol (SEARCH/REPLACE 格式)
- GranularMethodLocalizer (精確定位)
- Semantic Retry (verifier feedback 重構 prompt)
- Failure Feedback Builder (建立 retry prompt)
- CommitteeOrchestrator (多模型候選 + Judge 選優)

---

## H5~H8: Local-to-Capability Bridge

51+15+8+10 phases，trace-only/test-only/report-only scaffold。

---

## 三條管線的關係

```
路徑 A: HealPipeline → CommitteeOrchestrator → 5-Phase (6月優化)
         ❌ 沒被 _finalize_with_nexus_row 呼叫

路徑 B: LocalModelExecutor → IsolatedLocalSolveLoop (N1/N3 seam)
         ⚠️ 從 env var 讀 topology，不從 planner 讀

路徑 C: _finalize_with_nexus_row (benchmark 入口)
         → 只接路徑 B
```

---

## 修正方案

**不建新路由，只接現有的 CapabilityPlanner。**

CapabilityPlanner 已有 `local_model_executor` 能力和 `execution_topology` metadata。只需要讓 executor 從 planner 的 signal_snapshot 讀 topology，然後分支到既有的 committee 模組。
