# Phase 5 Evidence Package Checklist

**Status**: Not started
**Goal**: Expand to 30+ eligible shadow rows with full evidence
**Current**: 10 tasks per group (pilot pass only)

---

## 1. Task Expansion Plan

### Current State (10 per group)
| Bucket | Tasks | Held-out |
|:---|:---:|:---:|
| Easy | 3 | 1 |
| Medium | 3 | 1 |
| Hard | 4 | 2 |
| **Total** | **10** | **4** |

### Target State (30+ per group)
| Bucket | Tasks | Held-out | Source |
|:---|:---:|:---:|:---|
| Easy | 10 | 3 | Import tasks, type hints, docstrings |
| Medium | 10 | 3 | Fix annotations, remove unused imports, add defaults |
| Hard | 12 | 4 | Cross-module fixes, refactors, concurrency, circuit breakers |
| **Total** | **32** | **10** | |

### New Tasks to Add

#### Easy (7 new)
```json
{"task_id": "easy-011", "task_family": "easy", "task_desc": "add import hashlib to nexus/services/local_heal/orchestrator.py", "is_held_out": true}
{"task_id": "easy-012", "task_family": "easy", "task_desc": "add import json to nexus/services/local_heal/pipeline.py", "is_held_out": true}
{"task_id": "easy-013", "task_family": "easy", "task_desc": "add import os to nexus/services/local_heal/receipt.py", "is_held_out": false}
{"task_id": "easy-014", "task_family": "easy", "task_desc": "add import sys to nexus/services/local_heal/context.py", "is_held_out": false}
{"task_id": "easy-015", "task_family": "easy", "task_desc": "add import pathlib to nexus/services/local_heal/interface.py", "is_held_out": false}
{"task_id": "easy-016", "task_family": "easy", "task_desc": "add import logging to nexus/services/local_heal/planner.py", "is_held_out": true}
{"task_id": "easy-017", "task_family": "easy", "task_desc": "add import re to nexus/services/local_heal/localizer.py", "is_held_out": false}
```

#### Medium (7 new)
```json
{"task_id": "med-011", "task_family": "medium", "task_desc": "add return type annotation to nexus/services/local_heal/localizer.py Localizer._symbol_score", "is_held_out": true}
{"task_id": "med-012", "task_family": "medium", "task_desc": "fix parameter description in docstring for nexus/services/local_heal/localizer.py Localizer.build_query", "is_held_out": true}
{"task_id": "med-013", "task_family": "medium", "task_desc": "rename variable docs to documents in nexus/services/local_heal/localizer.py Localizer.rank_files", "is_held_out": false}
{"task_id": "med-014", "task_family": "medium", "task_desc": "add input validation for empty query in nexus/services/local_heal/localizer.py Localizer.rank_files", "is_held_out": true}
{"task_id": "med-015", "task_family": "medium", "task_desc": "change logging level from INFO to DEBUG in nexus/services/local_heal/localizer.py Localizer.rank_files", "is_held_out": false}
{"task_id": "med-016", "task_family": "medium", "task_desc": "add default value for max_files in nexus/services/local_heal/localizer.py Localizer.rank_files", "is_held_out": false}
{"task_id": "med-017", "task_family": "medium", "task_desc": "add error handling for empty results in nexus/services/local_heal/localizer.py Localizer.extract_relevant_code", "is_held_out": true}
```

#### Hard (8 new)
```json
{"task_id": "hard-005", "task_family": "hard", "task_desc": "integrate latency_ledger with orchestrator to track per-phase timing", "is_held_out": true}
{"task_id": "hard-006", "task_family": "hard", "task_desc": "fix potential memory leak in nexus/services/local_heal/localizer.py Localizer.rank_files", "is_held_out": true}
{"task_id": "hard-007", "task_family": "hard", "task_desc": "add concurrent file scanning in nexus/services/local_heal/localizer.py Localizer.rank_files using ThreadPoolExecutor", "is_held_out": false}
{"task_id": "hard-008", "task_family": "hard", "task_desc": "add timeout handling for file reads in nexus/services/local_heal/localizer.py Localizer.rank_files", "is_held_out": true}
{"task_id": "hard-009", "task_family": "hard", "task_desc": "add circuit breaker pattern to nexus/services/local_heal/orchestrator.py HealOrchestrator.run", "is_held_out": false}
{"task_id": "hard-010", "task_family": "hard", "task_desc": "fix error propagation in nexus/services/local_heal/orchestrator.py HealOrchestrator.run", "is_held_out": false}
{"task_id": "hard-011", "task_family": "hard", "task_desc": "add metrics collection for repair success/failure rates in nexus/services/local_heal/orchestrator.py", "is_held_out": true}
{"task_id": "hard-012", "task_family": "hard", "task_desc": "fix race condition in nexus/services/local_heal/orchestrator.py HealOrchestrator._reset_workspace", "is_held_out": true}
```

---

## 2. Required Metrics Per Row

Each task must produce these fields:

| Field | Type | Description |
|:---|:---|:---|
| `task_id` | string | Unique task identifier |
| `bucket` | string | easy/medium/hard |
| `route_path_id` | string | Code path taken (e.g., "localheal_pipeline", "direct_repair") |
| `selector_mode` | string | "rule" or "3b_advisor" |
| `verified_success` | bool | Final verification result |
| `first_pass_success` | bool | Success on first attempt |
| `report_generated` | bool | Whether run report was produced |
| `receipt_generated` | bool | Whether receipt was produced |
| `verified_result_source` | string | "run_report", "state_file", "execute_bug" |
| `claim_gate_seen` | bool | Whether claim gate was invoked |
| `delivery_gate_seen` | bool | Whether delivery gate was invoked |
| `trust_mismatch` | bool | Whether trust mismatch occurred |
| `public_claim_precision` | bool | Whether public claim precision maintained |
| `authority_drift` | bool | Whether authority drift occurred |
| `role_drift` | bool | Whether role drift occurred |
| `gate_bypass` | bool | Whether gate was bypassed |
| `wall_time_sec` | float | Total wall time |
| `model_time_sec` | float | Model inference time |
| `token_usage` | int | Total tokens used |
| `retry_count` | int | Number of retries |
| `abstain` | bool | Whether advisor abstained |
| `selector_override` | bool | Whether selector overrode baseline |
| `selector_override_verified` | bool | Whether override was verified |

---

## 3. Execution Commands

### Run All 4 Groups
```bash
for g in baseline pact_only pact_memory full; do
  echo "--- $g ---"
  NEXUS_OAUTH_PROVIDER=ollama NEXUS_USE_SURGICAL_REPAIR=1 \
  NEXUS_S2T_PACT_ENABLED=$([[ $g == "baseline" ]] && echo 0 || echo 1) \
  NEXUS_S2T_SKILL_MEMORY_ENABLED=$([[ $g == "pact_memory" || $g == "full" ]] && echo 1 || echo 0) \
  NEXUS_RETRIEVAL_MULTIGRANULARITY_ENABLED=$([[ $g == "full" ]] && echo 1 || echo 0) \
  uv run python /tmp/eval_10.py $g
done
```

### Verify Warm State
```bash
# Always run 1 warmup task first
NEXUS_OAUTH_PROVIDER=ollama uv run python -c "
from nexus.engine.canonical_task_seam import build_command_service
from nexus.app.command_service import TaskRequest
from pathlib import Path
service = build_command_service(Path('.'))
request = TaskRequest(task='add import hashlib', delivery_mode='standard')
service.execute_bug(request)
print('Warmup done')
"
```

---

## 4. Evidence Files to Generate

| File | Content |
|:---|:---|
| `.nexus/eval/results_baseline_30.json` | Baseline group results |
| `.nexus/eval/results_pact_only_30.json` | PACT Only group results |
| `.nexus/eval/results_pact_memory_30.json` | PACT+Memory group results |
| `.nexus/eval/results_full_30.json` | Full Uplift group results |
| `.nexus/eval/per_row_evidence.jsonl` | Per-row evidence records |
| `.nexus/eval/shadow_report.json` | Aggregated shadow report |

---

## 5. Acceptance Criteria

Before this checklist is complete:

- [ ] 30+ eligible shadow rows per group
- [ ] Held-out harder tasks included
- [ ] Per-row evidence records generated
- [ ] Selector override analysis included
- [ ] Abstain rate tracked
- [ ] Trust mismatch rate = 0
- [ ] Public claim precision maintained
- [ ] All 4 groups use same authority/success criterion/evidence contract
- [ ] No runtime default changes
- [ ] Feature flags remain OFF

---

*Checklist generated: 2026-06-15*
*Status: Not started — needs 30+ task expansion*
