# F-11A Oversized File Audit

**Status:** `F11A_OVERSIZED_FILE_AUDIT`

**Date:** 2026-06-29

## Summary

Inventory of oversized Python files (>500 lines) with split recommendations.

## Top 20 Oversized Files

| File | Lines | Type |
|---|---|---|
| `tests/benchmark/test_capability_ab_runner.py` | 33550 | Benchmark test |
| `scripts/bench/capability_ab_runner.py` | 20246 | Benchmark script |
| `tests/learning/test_skill_fit_ablation.py` | 3748 | Test |
| `tests/app/test_research_flow_service.py` | 3706 | Test |
| `scripts/engine/nexus_cli.py` | 2908 | CLI |
| `tests/engine/test_capability_planner.py` | 2757 | Test |
| `tests/research/test_sprint_service.py` | 2326 | Test |
| `scripts/train/finetune_3b_student.py` | 2235 | Training script |
| `nexus/app/research_flow_service.py` | 1958 | Service |
| `nexus/research/sprint_service.py` | 1862 | Service |
| `tests/benchmark/test_gemini_nexus_report.py` | 1770 | Benchmark test |
| `nexus/learning/skill_fit_followup.py` | 1684 | Learning |
| `nexus/learning/skill_fit_ablation_core.py` | 1631 | Learning |
| `nexus/learning/skill_route_taxonomy.py` | 1586 | Learning |
| `nexus/engine/capability_receipt_adapters.py` | 1380 | Engine |
| `nexus/engine/capability_planner.py` | 1371 | Engine |
| `nexus/research/learn_mode.py` | 1316 | Research |
| `nexus/learning/sf2_bounded_probe.py` | 1279 | Learning |
| `nexus/research/local_sprint_mutator.py` | 1254 | Research |

## Classification

| Type | Count | Examples |
|---|---|---|
| Benchmark/test artifact | 4 | test_capability_ab_runner.py, capability_ab_runner.py |
| CLI/service hub | 3 | nexus_cli.py, research_flow_service.py |
| Real refactor candidate | 12 | Various nexus/ modules |

## Top 3 Split Candidates (Best ROI)

| File | Lines | Why |
|---|---|---|
| `nexus/learning/skill_fit_ablation_core.py` | 1631 | Clear import boundaries, testable |
| `nexus/engine/capability_planner.py` | 1371 | Core logic, manageable test surface |
| `nexus/research/learn_mode.py` | 1316 | Research module, extractable helpers |

## Commands Run

```bash
find nexus tests scripts -name '*.py' -print0 | xargs -0 wc -l | sort -nr | head -20
```

## Scope Statement

- Audit only, no code changes
- Identified top split candidates
