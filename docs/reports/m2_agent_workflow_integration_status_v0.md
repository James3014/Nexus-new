# M2 Agent Workflow Integration

## Status

`M2_STATUS_CONVERGED_AND_SEALED`

M2 is sealed for the evidence currently accepted: explicit Local Assist, public-fixture Agent operation, user-relay Agent operation, and one bounded any-Agent audited repository task. This is a documentation/status closure. It does not establish outcome contribution, value measurement, production readiness, public claims, M3 automatic dispatch, or M4 real cloud integration.

## Accepted evidence

| Track | State | Evidence |
| --- | --- | --- |
| M1 explicit bridge | `PROVEN` | Existing live Ollama receipts and focused service tests |
| Track A public fixture | `PROVEN` | `docs/reports/m2_external_agent_alternative_paths_v0.md` |
| Track B user relay | `PROVEN` | `docs/reports/m2_external_agent_alternative_paths_v0.md` |
| Any-Agent audited repository task | `PROVEN` | Commit `1ff12d37f`; `.nexus/reports/local_assist/m2-agent-audit-20260713/agent_closeout.json`; `.nexus/reports/local_assist/m2-agent-audit-20260713/agent_closeout_report.json` |

The accepted any-Agent task sequence was: Agent received a bounded repository task, invoked advisor, selected a bounded test target, invoked candidate, consumed the isolated candidate, applied a bounded test change, ran focused pytest, and submitted closeout evidence citing both receipt identities.

## Claim boundary

The closeout records `local_assist_requested=true`, `local_assist_invoked=true`, `local_assist_output_delivered=true`, `local_assist_output_consumed=true`, and `local_candidate_selected=true`. It records `outcome_contributed=false` and `value_measured=false`.

These dimensions remain separate:

| Dimension | Current state |
| --- | --- |
| selected | Proven for advisor and candidate selection |
| invoked | Proven by Local Assist receipts |
| delivered | Proven by delivery fields in the closeout |
| consumed | Proven by citations to both receipt identities |
| contributed | `NOT_PROVEN` (`outcome_contributed=false`) |
| value measured | `NOT_PROVEN` (`value_measured=false`) |

Do not upgrade `outcome_contributed`, `value_measured`, `production_ready`, or `public_claim_allowed` from this evidence.

## Verification evidence

- `.venv/bin/python -m pytest -q tests/services/test_local_assist_closeout.py tests/services/test_local_assist_user_relay.py` → `12 passed in 0.15s`.
- `git diff --check` must pass.
- The scoped commit must contain only the two M2 documentation files.

## Residual debt and next milestone

M3 automatic dispatch is `NOT_STARTED`. M4 real cloud integration is `NOT_PROVEN`. The next milestone is `M3-S0_PLANNER_LOCAL_ASSIST_RECOMMENDATION_SHADOW`, limited to a non-authoritative recommendation receipt for `skip`, `advisor`, `candidate`, or `verified-subtask`. It must not auto-invoke Local Assist, mutate the workspace, add `RouteMode`, Router, Planner, or execution topology, or replace `CapabilityPlanner` as route truth.
