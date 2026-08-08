# Task Card: LEGACY-MCP-SEAM-RATIONALIZATION-01

artifact_authority: current
task_id: `LEGACY-MCP-SEAM-RATIONALIZATION-01`
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

Classify `_apply_assisted_patch`, `nexus_assist_*`, legacy self-hosted MCP,
provider proposal runners, MCP delegation defaults, and ChatGPT delivery paths
as `WIRED`, `UNREACHABLE`, `LEGACY`, or `DUPLICATE_AUTHORITY_RISK`. Apply the
smallest source change that removes or fail-closes remote duplicate mutation
authority while preserving read-only/advisor compatibility where proven useful.

Final remote implementation path:

```text
ChatGPT MCP
-> nexus_worker_candidate
-> SelfHostedTaskService
-> isolated Target
-> verifier
-> Candidate
-> exact Owner-bound integration
```

## Baseline and dependencies

- Canonical baseline at authority creation:
  `230f7c4ed9c48f7431dba9d50d41f22e0c3f5e5b`.
- Re-anchor to fresh canonical before implementation.
- Do not overlap the externally owned `DEEPSEEK-WORKER-READINESS-FIX-01`
  Candidate. If it changes Gateway/service tests, base after its exact
  integration or stop with `RECOVERABLE_BLOCK`.

## Allowed files

- `nexus/orchestrator/unified_mcp_gateway.py`
- `nexus/services/mcp_delegator.py`
- `scripts/ops/nexus_chatgpt_delivery.py` only if its mutation route is proven
  current and duplicate-risk
- `tests/nexus/orchestrator/test_unified_mcp_gateway.py`
- `tests/services/test_mcp_delegator.py`
- `tests/ops/test_nexus_chatgpt_delivery.py`

Do not modify legacy server source unless fresh caller proof shows a smaller,
safer change cannot make it unreachable from supported entrypoints.

## Required controls

- prove the actual LaunchAgent/runtime entrypoint and public `tools/list`;
- prove call references before deleting or narrowing any seam;
- `_apply_assisted_patch` and provider proposal runners cannot be reached from a
  public tool or create a canonical commit;
- `nexus_assist_*` is read-only/advisor-only or explicitly deprecated and must
  never call apply/commit/Target promotion, including `apply=true`;
- MCPDelegator cannot silently default `nexus_self_hosted_*` to the legacy
  29-tool server;
- ChatGPT delivery cannot default a remote worker task to Direct canonical;
- no second public worker/lifecycle surface, router, planner, registry, or raw
  shell action is introduced;
- current typed closure tools remain available as separate approval/integration
  authority, not worker ingress.

## RED -> GREEN

1. Static/call-graph RED proves any reachable direct apply/proposal seam; GREEN
   makes supported public dispatch unable to reach it.
2. `nexus_assist_submit(apply=true)` remains non-mutating and produces no
   canonical commit/Target/Candidate.
3. Legacy self-hosted tool names never appear in Unified Gateway `tools/list`.
4. MCPDelegator legacy default fails closed with a typed deprecation result.
5. ChatGPT delivery worker mutation selects the governed Candidate path only.

## Verification

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m pytest -q -p no:cacheprovider \
  tests/nexus/orchestrator/test_unified_mcp_gateway.py \
  tests/services/test_mcp_delegator.py \
  tests/ops/test_nexus_chatgpt_delivery.py
git diff --check
git diff --name-status
git diff --stat
git diff --cached --name-status
git diff --cached --stat
```

## Forbidden scope

No SelfHostedTaskService, durable/OAuth, route/planner/workforce, provider
onboarding, lifecycle JSON, OpenWiki, live reload, integration, cleanup, push,
or public/production claim. Do not touch another agent's Target.

## Exit criteria

One scoped Candidate commit, exact tests green, no deletions without proven
callers, one public implementation ingress, and independent review. Worker
stops before approval, integration, reload, cleanup, or push.

## Block classification

- `RECOVERABLE_BLOCK`: active overlapping Gateway Candidate or test issue.
- `HARD_BLOCK`: a supported external consumer requires the legacy mutation
  authority and no conservative compatibility path exists, or scope must expand
  into route/lifecycle authority.
