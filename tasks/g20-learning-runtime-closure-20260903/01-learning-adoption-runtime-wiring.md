# G20-LEARNING-ADOPTION-RUNTIME-WIRING

```yaml
task_id: G20-LEARNING-ADOPTION-RUNTIME-WIRING
status: ACTIVE
authority: OWNER_CURRENT_INSTRUCTION
owner_instruction: "目標完成g20，沒完成不要回報"
base_commit: 4cebc4d5a59260ded0240bef7a2c5f7c7bf9286e
base_tree: 4b5ed0765cead74414e6d587293ec6bb2f6ca993
execution_lane: GOVERNED
auto_chain: false
```

## Objective

Wire the already-merged `nexus.learning_policy_adoption.v1` / rollback contracts into the existing authoritative runtime learning-policy loader so the canonical product execution seam can supply an exact-scope adoption projection to `CapabilityPlanner`. The Planner remains the sole capability/route decision authority.

## Allowed files

- `nexus/engine/learning_policy_loader.py`
- `nexus/engine/canonical_task_seam.py`
- `tests/engine/test_learning_policy_store.py`
- `tests/engine/test_canonical_task_seam.py`
- `tasks/g20-learning-runtime-closure-20260903/INDEX.md`
- `tasks/g20-learning-runtime-closure-20260903/01-learning-adoption-runtime-wiring.md`

## Required behavior

1. Reuse `LearningPolicyStore`; no parallel persistence subsystem.
2. Load one governed adoption artifact and optional rollback artifact from the existing `.nexus/policy` authority surface.
3. Validate content-addressed adoption/rollback contracts before projection.
4. Fail closed on malformed/tampered artifacts and stale source revision.
5. Apply exact task-family/model/runtime scope through `project_adoption_into_planner_budget()`.
6. Merge the projected learning-policy fields without deleting existing promoted/dynamic learning-policy evidence.
7. Canonical product execution must load this budget before calling `CapabilityPlanner`; LocalModelExecutor must not become a policy authority.
8. Rollback must reconstruct as disabled policy through the same durable loader after process restart.

## Verification

- focused loader/store positive, out-of-scope, stale, tamper, rollback tests;
- canonical product task proof that the persisted governed projection reaches Planner inputs;
- existing learning contract tests;
- canonical task-seam regressions;
- exact-base lint/type/test CI before merge;
- `git diff --check`.

## Non-goals

No model promotion, route override, learned Router, new database, production release, or universal-learning claim.

## Completion evidence

Candidate commit/tree/diff, focused test results, exact-base CI, independent review, protected merge, then separate G20 exact-runtime witnesses.
