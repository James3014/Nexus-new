# T3C1 — Committee Per-Member Demand Wiring

**artifact_authority:** current  
**owner:** James Chen  
**status:** COMPLETED / TERMINAL_RECONCILIATION
**task_id:** `model-workforce-v21-runtime-closure-t3c1`

## Scope

Project the existing CapabilityPlanner committee selections into independent
workforce member-demand records. Sources are limited to `proposer_specs`,
`judge_model`, diagnosis/audit model lists, advisor selection, delegated retry
models, and already-provided delegated member specs. The projection carries
provider/model identity and the required lifecycle metadata while retaining
`CapabilityPlanner` as route authority.

This card does not perform admission or provider invocation. Aggregate
admission and physical calls remain T3C2/T3C3.

## Evidence

- campaign INDEX completed-cards records T3C1 integrated at `061286b8c5f7a40caf68e0c4f951ba83364bb8f8` (candidate commit `084a90315372e0ae363c98ed7e6520d89a214f77`; runtime integration history only, not an ancestor of GitHub `main`; metadata reconciliation only, no runtime/production claim)
- `COMMITTEE_MEMBER_DEMAND_WIRING_COMPLETE`
- malformed or missing selected members fail closed without replacement
- every emitted demand has `member_id`, `parent_demand_id`, `phase`, `role`,
  `provider`, `model`, `required_or_optional`, `minimum_autonomy`,
  `context_class`, `mutation_intent`, `external_verification_required`, and
  `route_authority`
- exact verifier: `uv run pytest -q tests/unit/local_heal/test_c6av_committee_solve_reality_check.py tests/contracts/test_p4_committee_routed_tool_receipts.py`
- exact verifier: `git diff --check`

## Next gate

T3C2 may consume these records to perform all-member admission before any
committee provider call. This card does not authorize a new route, topology,
execution channel, or authority.
