# TASK-514-001 Amendment B — preserve #488 non-invocation witness under Planner authority

- **Authority:** Issue #514 contract-delta comment `5381167303`
- **Applies to:** `TASK-514-001`
- **Trigger:** exact-base PR CI classified `tests/core/test_executor_controls_truth.py::test_router_learning_records_failed_for_non_invocation` as a new head failure because its mocked plan lacked the now-required Planner authority marker.
- **Scope delta:** allow editing only that focused test/fixture in `tests/core/test_executor_controls_truth.py`.
- **Production scope delta:** none.
- **Required preservation:** the test must continue proving that a legal Planner-bound plan whose executor reports `invoked=False` produces FAILED/non-invoked learning evidence. It must not weaken `SkillsRouter` rejection of non-Planner plans.
- **Claim ceiling:** unchanged: `LEGACY_CAPABILITY_SELECTOR_AUTHORITY_CONTAINED_AT_SOURCE`.
- **Auto-chain:** `false`.
