# GitHub Issue #522 Retry Dispatch Envelope Rebind

```yaml
campaign_id: GITHUB_ISSUE_522_RETRY_DISPATCH_ENVELOPE_REBIND
source_issue: 522
repository: James3014/Nexus-new
status: ACTIVE
auto_chain: false
parallel_safe_with_issue_526_source_work: true
claim_mode: MANUAL_DISPATCH
base_main: 7ad264e1c12a2b4d3896b4cdeec68688acf034f7
base_tree: b9057f8ef736fb6d3cd30da983f33f5f61fb86e9
work_branch: codex/issue-522-retry-dispatch-envelope-rebind
claim_ceiling: LIFECYCLE_RETRY_DISPATCH_ENVELOPE_REBIND_CLOSED_AT_SOURCE_TEST_CANDIDATE
```

## Frontier

| Task | Card | Status | Outcome |
|---|---|---|---|
| `TASK-522-001` | `00-retry-dispatch-envelope-rebind.md` | ACTIVE | issue-branch source/test Candidate only |

## Frozen scope

- `nexus/orchestrator/self_hosted_task_service.py`
- `tests/nexus/orchestrator/test_self_hosted_task_service.py`

No other source, test, policy, route, admission, provider, capability, Task
Card, generated, or runtime-state path is authorized. No deletions.

Fresh overlap at the bound base is disjoint from Issue #526's Gateway durable
manager surface and PR #521's assisted Gateway retry surface. Source/test work
may proceed in an isolated branch; approval, integration, merge, runtime
activation, and downstream #517 retry remain separate.

## Gates

Before dispatch: exact card hash readback, clean isolated branch, fresh
Workforce Admission for the exact worker/model/role/scope, executable provider
preflight, and `AUTO_CHAIN=false`.

Before acceptance: exact Candidate head/base/diff, all card verifiers,
fresh-envelope positive control, stale-envelope zero-launch negative control,
two-path/deletion audit, and independent review.

