# Implementation Tracking: RFC-OPT-001 Nexus V3 Routing Hardening

## 📋 MVP Roadmap Status
- [x] **P0: Governance Hard Lock (ExtensionGuard)**
- [x] **P1: Dependency-Aware Hazard Mapping**
- [x] **P2: Multi-Factor Proof (MFP)**
- [x] **P3: DDTree Impact-Aware Pruning**
- [x] **P4: Gemma Classifier & Outlier Rejection**

---

## 🛠️ Phase 0: Implementation Boundaries
- **Branch**: `research/rfc-opt-001-v3-hardened`
- **Feature Flag**: `NEXUS_ROUTING_V4_HARDENED` (Default: OFF)

## 📓 Progress Log

### 2026-05-03: Initializing P0+P1
- Initializing implementation based on MVP recommendation.
- **P0 Implemented**: Created `nexus/engine/extension_guard.py` to block code files (.py, .js, .rs, etc.) from L1 (Green-Lane).
- **P1 Implemented**: Created `nexus/engine/hazard_mapper.py` to detect red-zone module impact via `impact_map`.
- **Integrated**: Updated `nexus/engine/autonomic_router.py` to utilize P0 and P1 when `NEXUS_ROUTING_V4_HARDENED` is enabled.
- **Verified**: Created `tests/engine/test_v4_routing_hardening_mvp.py` with 4 test cases covering P0, P1, and feature flag behavior. All tests PASSED.
- **Regression Check**: Existing `router_policy_benchmark.py` remains stable (Metrics: 1.0).

### 2026-05-04: Completed P2+P3+P4 (Hardened Flag Path)
- **P2 Implemented**: Added `nexus/engine/mfp_gate.py` and integrated MFP in `nexus/engine/autonomic_router.py`.
  - Factors: `confidence`, `semantic_entropy`, `history_success_rate`.
  - Env thresholds:
    - `NEXUS_MFP_CONFIDENCE_MIN` (default 0.98)
    - `NEXUS_MFP_ENTROPY_MAX` (default 0.15)
    - `NEXUS_MFP_HISTORY_SUCCESS_MIN` (default 0.95)
  - Behavior: if any factor fails, block L1/early-exit and escalate to `swarm`.
- **P3 Implemented**: Added `nexus/engine/policy_pruner.py` and integrated impact-aware policy filtering in `autonomic_router`.
  - Keeps `GLOBAL` policies always.
  - Prunes tag-mismatched policies when `impact_map` tags exist.
- **P4 Implemented**: Added `nexus/engine/gemma_guard.py` and optional classifier consistency guard.
  - Feature flag: `NEXUS_GEMMA_CLASSIFIER_ENABLED=1`.
  - Applies median-based outlier rejection for `classifier_scores`.
  - On rejection, forces `swarm`.
- **Tests Updated**: Extended `tests/engine/test_v4_routing_hardening_mvp.py` from 4 -> 9 cases.
- **Verification**:
  - `uv run pytest -q tests/engine/test_v4_routing_hardening_mvp.py` -> 9 passed
  - `uv run python scripts/ops/router_policy_benchmark.py` -> precision/recall/f1=1.0
