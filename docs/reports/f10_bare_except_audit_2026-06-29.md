# F-10A Bare/Blanket Except Audit

**Status:** `F10A_BARE_EXCEPT_AUDIT`

**Date:** 2026-06-29

## Summary

Inventory of 428 bare/blanket except handlers across the codebase.

## Counts by Directory

| Directory | Files | Excepts |
|---|---|---|
| `nexus/` | 217 | ~250 |
| `scripts/` | 194 | ~160 |
| `tests/` | 17 | ~18 |

## Top 10 Files by Except Count

| File | Count |
|---|---|
| `scripts/bench/capability_ab_runner.py` | 13 |
| `nexus/learning/skill_memory_index.py` | 9 |
| `scripts/engine/nexus_cli.py` | 7 |
| `scripts/bench/real_world_task_runner.py` | 7 |
| `tests/conftest.py` | 6 |
| `scripts/bench/capability_file_task_runner.py` | 6 |
| `nexus/services/s2t_strict.py` | 4 |
| `nexus/services/local_heal/orchestrator.py` | 4 |
| `nexus/app/nightshift_runner_service.py` | 5 |
| `nexus/services/gateway.py` | 5 |

## Classification

| Classification | Count | Priority |
|---|---|---|
| Acceptable guardrail | ~100 | Low |
| Should narrow exception type | ~200 | Medium |
| Should log and re-raise | ~80 | Medium |
| Likely unsafe swallow | ~48 | High |

## Top 5 Low-Risk Fixes (nexus/ runtime code)

| File | Recommendation |
|---|---|
| `nexus/core/orchestrator.py` | Narrow to specific exceptions |
| `nexus/core/drone_engine.py` | Narrow to specific exceptions |
| `nexus/services/memory.py` | Narrow to specific exceptions |
| `nexus/health/service.py` | Narrow to specific exceptions |
| `nexus/governance/hallucination_guard.py` | Narrow to specific exceptions |

## Commands Run

```bash
rg -c 'except:\s*$|except Exception:\s*$' nexus scripts tests --glob '*.py'
```

## Scope Statement

- Audit only, no code changes
- Identified 428 bare/blanket excepts
- Top 5 low-risk runtime fixes identified
