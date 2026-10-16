# Nexus Model-Candidate Demo Package

**Date**: 2026-06-18
**Status**: INTERNAL DEMO — NOT PUBLIC BENCHMARK

---

## 1. What This Package Contains

This is an internal demo package showing Nexus's model-candidate evidence path. It demonstrates:
- Local Qwen14B REPLACE-only patch generation
- Strategy-conditioned prompt rendering
- Indentation-aware insertion
- Source-clean candidate selection
- Deterministic replay under pinned conditions

**This is NOT:**
- A public benchmark
- A Qwen solve rate
- Comparable to official SWE-bench
- A production-ready autonomous patcher

## 2. Capability Summary

| Capability | Status | First Proven |
|------------|--------|-------------|
| REPLACE-only prompt contract | ✓ | T3.2 |
| Context-aware syntax gate | ✓ | T3.5 |
| Indentation normalization | ✓ | T4.8 |
| Source stale guard | ✓ | S4.1 |
| Strategy-specific tournament | ✓ | S2.2 |
| Winner-only execution | ✓ | S2+ |
| Parent-boundary validation | ✓ | S4.5 |
| Indentation-aware insertion | ✓ | S4.6 |
| Deterministic M0 replay | ✓ | S4.9 |
| Source-clean candidate selection | ✓ | S5.5 |

## 3. Verified Candidates (10)

| instance_id | project | evidence_tier | patch_shape |
|-------------|---------|---------------|-------------|
| astropy__astropy-13236 | astropy | stable_fresh_m0 | block_deletion |
| sympy__sympy-13852 | sympy | stable_fresh_m0 | single_line |
| astropy__astropy-12907 | astropy | stable_fresh_m0 | single_line |
| astropy__astropy-14182 | astropy | stable_fresh_m0 | single_line |
| astropy__astropy-13453 | astropy | stable_fresh_m0 | single_line |
| astropy__astropy-13579 | astropy | fresh_m0_verified | insertion |
| sympy__sympy-13031 | sympy | stored_output_replay | block_replacement |
| astropy__astropy-14365 | astropy | stable_fresh_m0 | single_line |
| sympy__sympy-12419 | sympy | stable_fresh_m0 | single_line |
| sympy__sympy-13647 | sympy | stable_fresh_m0 | single_line |

## 4. How to Reproduce

### Prerequisites
- Ollama running with qwen2.5-coder:14b-instruct-q3_K_M
- Python 3.10+ (astropy) or Python 3.9 (sympy)
- Workspace at .nexus/workspaces/

### Replay a candidate
```bash
python3 scripts/strategy/s5_7_consolidation.py --instance_id <instance_id>
```

### Run strategy tournament
```bash
python3 scripts/strategy/s2_diverse_strategy_rollout.py
```

## 5. Non-Claims (MUST INCLUDE)

This package demonstrates internal model-candidate evidence under strict attribution controls. It is NOT:
- A public benchmark result
- A Qwen solve rate
- Comparable to official SWE-bench
- Evidence of production-ready autonomous patching

Human review is required before any training or export use.
