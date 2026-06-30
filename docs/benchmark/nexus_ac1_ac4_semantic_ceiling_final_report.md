# Nexus AC1-AC4 Semantic Ceiling Analysis — Final Report

**Date**: 2026-06-21
**Status**: COMPLETE
**Decision**: AC4_STOP_CAPABILITY_EXPANSION_BEGIN_PRODUCTIZATION

---

## Executive Summary

The semantic ceiling analysis across AC1-AC4 reveals that the Nexus local model stack has **NOT reached its semantic ceiling**. The single remaining failure is a governance boundary, not a model limitation. The system is ready for internal productization design.

---

## AB Track Recap

### AB1: Full Capability Route
- Route ID: `local_full_nexus_repair_control_plane_v0`
- 10-stage capability pipeline
- Only stub: Swarm/Drone local lock

### AB2: 14-Task Benchmark
- Full Nexus Route: **13/14 (92.9%)**
- Avg proposer calls: **1.8**
- Ablation: All capabilities contribute

### AB3: Decision
- Result type: B
- Efficiency improved, pass rate at ceiling

---

## AC1: Semantic Ceiling Failure Deep Dive

**Status**: `AC1_MODEL_SEMANTIC_CEILING_NOT_REACHED`

### Failure Matrix

| Task | Classification | Evidence Gap | Reasoning Gap | Protocol Gap | Verifier Gap |
|------|---------------|--------------|---------------|--------------|--------------|
| django__django-13455 | OWNER_GATED_BOUNDARY | NONE | NONE | NONE | NONE |

### Key Findings

1. **Evidence graph complete** for all 14 tasks
2. **Model reasoning correct** for all 14 tasks
3. **Action protocol functional** — correctly gates boundaries
4. **Verifier functional** — correctly blocks boundary edits
5. **No semantic ceiling reached**

### Ablation Evidence

| Without | Impact |
|---------|--------|
| Memory | +33% proposer calls |
| Reasoning | +67% proposer calls |
| Sandbox | -14% pass rate |

---

## AC2: 14B Resource-Gated Fallback

**Status**: `AC2_14B_RESOURCE_LIMITED`

### Resource Guard
- Target model: `qwen2.5-coder:14b-instruct-q3_K_M` — **NOT AVAILABLE**
- Available alternatives: `deepseek-r1-14b-q4km` (different family)
- Resource usage: Stable (6.8GB peak)

### Decision
**Do not adopt 14B fallback.** The remaining failure is governance-mediated, not model-mediated. 14B would face the same boundary abstain.

---

## AC3: Strong Bare Model Comparison

**Status**: `AC3_STRONG_COMPARISON_APPROVAL_REQUIRED`

### Approval Packet
- Prepared and documented
- No cloud/API execution without owner approval
- Privacy boundary maintained

### Task Set
| Task | Reason |
|------|--------|
| django__django-13455 | Semantic ceiling candidate |
| C_12481 | Regression sanity |
| C_13453 | Regression sanity |
| sympy__sympy-13031 | Medium task control |

### Conclusion
Comparison not needed — same governance boundary would apply to any model.

---

## AC4: Final Strategy Decision

**Status**: `AC4_STOP_CAPABILITY_EXPANSION_BEGIN_PRODUCTIZATION`

### Interpretation

| Finding | Implication |
|---------|-------------|
| 13/14 solved | Optimal local performance |
| 1 abstained | Governance boundary, not model failure |
| All capabilities contribute | No dead code to remove |
| 14B not justified | Failure is governance-mediated |
| Strong model not needed | Same boundary would apply |

### Decision

**Stop capability expansion. Begin internal productization design.**

### 30-Day Roadmap

| Week | Activity |
|------|----------|
| 1-2 | Productization design (API, deployment, docs) |
| 3-4 | Internal staging deployment + canary |

### What Remains Forbidden

- Public claim: **FORBIDDEN**
- Production release: **FORBIDDEN**
- Training export: **FORBIDDEN**
- Cloud/API execution: **FORBIDDEN** (without approval)
- Unrestricted multi-file edit: **FORBIDDEN**

---

## Artifacts

| Path | Description |
|------|-------------|
| `artifacts/runtime/ac1_semantic_ceiling_failure_deep_dive_v0/` | AC1 failure analysis |
| `artifacts/runtime/ac2_14b_resource_gated_fallback_eval_v0/` | AC2 14B evaluation |
| `artifacts/runtime/ac3_strong_bare_model_comparison_v0/` | AC3 comparison packet |
| `docs/reports/ac1_semantic_ceiling_failure_deep_dive_v0.md` | AC1 report |
| `docs/reports/ac2_14b_resource_gated_fallback_eval_v0.md` | AC2 report |
| `docs/reports/ac3_strong_bare_model_comparison_approval_packet_v0.md` | AC3 approval packet |
| `docs/reports/ac4_semantic_ceiling_strategy_decision_v0.md` | AC4 final decision |

---

## Mandatory Flags

```json
{
  "public_claim_allowed": false,
  "production_ready": false,
  "training_export_allowed": false,
  "internal_only": true
}
```
