# Issue #455 — Assisted Retry Revalidation Campaign

```yaml
campaign_id: GITHUB_ISSUE_455_ASSISTED_RETRY_REVALIDATION
source_issue: 455
repository: James3014/Nexus-new
status: ACTIVE
auto_chain: false
claim_mode: MANUAL_DISPATCH
base_main: 67521fe91e990f4e140642984c743dd50a408e84
base_tree: f6d6c2bf0912ff4a63d3c10a089910f95eab3c12
work_branch: codex/issue-455-assisted-retry-revalidation
claim_ceiling: ASSISTED_RETRY_REVALIDATION_CLOSED_AT_SOURCE_TEST_CANDIDATE
```

## Frontier

| Task | Card | Status | Outcome |
|---|---|---|---|
| `ISSUE_455_ASSISTED_RETRY_REVALIDATION` | `00-assisted-retry-revalidation.md` | ACTIVE | issue-branch implementation/Candidate only |

## Frozen scope

- `nexus/orchestrator/unified_mcp_gateway.py`
- `tests/nexus/orchestrator/test_unified_mcp_gateway.py`

No other source, test, policy, lifecycle, workforce, provider, or governance
path is authorized. Zero deletions.

Before dispatch: exact card hash, Planner-derived runtime Workforce `ALLOW`,
physical Agy adapter/model preflight, clean base, and `AUTO_CHAIN=false`.

Before acceptance/integration: exact head/base/diff, all card verifiers,
negative-control evidence, two-file/deletion audit, independent review, and
fresh GitHub/branch-protection/CAS gates.
