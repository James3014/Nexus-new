# Task Card: keyed-store

artifact_authority: current
task_id: `keyed-store`
owner: James Chen
status: ACTIVE
commit_required: true
candidate_required: true
worker_may_commit: true
worker_may_approve: false
worker_may_integrate: false
worker_may_push: false
AUTO_CHAIN: false

## Objective

Implement Ready Issue #888, https://github.com/James3014/Nexus-new/issues/888, on frozen base 01e3d2f32ec326cc2631da2b374a1602fa6d2f05. Add keyed standing-grant storage and fenced legacy migration using full RepositoryIdentity+Goal+durable coordinator scope. Preserve validated receipt v1 and semantic evaluator. Fixed derived paths, no arbitrary path/request authority selectors, per-key CAS and source-owned registered hash-pinned scope. Explicit migration intent/completion fences must recover crash prefixes and deny legacy replay/fallback. Read APIs write no state. Keep unmigrated legacy behavior. Cover distinct-key subprocess coexistence, same-key CAS race, stale/forged scope, unsafe filesystem, expiry/revocation, migration crashes/replay. Detailed reviewed interface proposal: /private/tmp/astra-keyed-grant-pregate-20260909/DECISION.md; only store/docs portion applies. Gateway/A integration is downstream. Single Luna implementer; root independently verifies exact candidate. Worker cannot alter live grants, protected state, cards, other files, providers, main, approve, push, merge or deploy. AUTO_CHAIN=false. Current Owner explicitly approved Frontier/Astra shared handoff; formal bootstrap receipt and lease are independently recorded, not created by worker.

## Allowed files

- `nexus/orchestrator/standing_grant_store.py`
- `tests/nexus/orchestrator/test_standing_grant_store.py`
- `tests/nexus/orchestrator/test_standing_grant_session_continuity.py`
- `tests/nexus/orchestrator/test_keyed_standing_grant_store.py`
- `docs/agents/TASK_EXECUTION_CONTRACT.md`

## Verification commands

```bash
/private/tmp/astra-host-root-acceptance-20260909/bin/python -B -m pytest -q -p no:cacheprovider tests/nexus/orchestrator/test_standing_grant_store.py tests/nexus/orchestrator/test_standing_grant_session_continuity.py tests/nexus/orchestrator/test_keyed_standing_grant_store.py
ruff check nexus/orchestrator/standing_grant_store.py tests/nexus/orchestrator/test_keyed_standing_grant_store.py
git diff --check
```

## Exit criteria

Owner review of the exact scoped commit.

## Block classification

Unverifiable or out-of-scope mutation is a HARD_BLOCK.
