# Task Card P1: Unified MCP Gateway Foundation

## Identity

- task_id: `single-mcp-three-lane-p1-authority`
- campaign_id: `single-mcp-three-lane-fast-dispatch`
- artifact_authority: current
- status: IN_PROGRESS
- owner: James Chen
- objective: Establish the bounded card and scope for one GPT-visible Nexus MCP Gateway that composes canonical workspace reads with lifecycle status/finish actions.
- read_only: false
- audit_only: false
- commit_required: true
- candidate_required: false
- worker_may_commit: true
- worker_may_approve: false
- worker_may_integrate: false
- worker_may_push: false
- AUTO_CHAIN: false

## Inputs and Dependencies

- `tasks/single-mcp-three-lane-fast-dispatch/INDEX.md`
- `tasks/single-mcp-three-lane-fast-dispatch/00-p0-authority.md`
- `nexus/orchestrator/self_hosted_mcp.py`
- `nexus/orchestrator/self_hosted_task_service.py`
- `docs/arch/MODEL_WORKFORCE_POLICY.md`

## Allowed Files

- `nexus/orchestrator/unified_mcp_gateway.py`
- `scripts/ops/nexus_mcp_gateway.py`
- `tests/nexus/orchestrator/test_unified_mcp_gateway.py`

## Required Behavior

1. Expose one server identity `nexus-mcp-gateway` and one deterministic tool manifest.
2. Provide bounded workspace snapshot/read/search/diff tools rooted at canonical Nexus only.
3. Provide high-level lifecycle status, finish, and cancel tools without exposing the 29-tool internal surface.
4. Reject absolute paths, traversal, symlink escapes, oversized reads/searches, and arbitrary shell/flag forwarding.
5. Preserve Direct/isolated lifecycle authority in `SelfHostedTaskService`; this card must not implement Assisted routing yet.

## Verification Commands

```bash
git diff --check
PYTHONDONTWRITEBYTECODE=1 PYTHONPYCACHEPREFIX=/tmp/nexus-gateway-pycache .venv/bin/python -m pytest -q -p no:cacheprovider tests/nexus/orchestrator/test_unified_mcp_gateway.py
.venv/bin/python scripts/ops/nexus_mcp_gateway.py --self-test
git status --short --branch
git worktree list --porcelain
.venv/bin/python -m scripts.engine.nexus_cli self-hosted list-actionable
```

## Exit Criteria

- One gateway process serves the bounded public tool list.
- Gateway tests prove protocol identity, tool count, path containment, and lifecycle forwarding.
- No Target, Candidate, or lifecycle state is created by read-only gateway calls.
- A scoped commit exists and the Direct receipt verifies it.

## Forbidden Scope

- No DevSpace external-repository edits or package installation.
- No public connector cutover, token/scope expansion, or automatic approval.
- No `ASSISTED_CANONICAL` implementation in P1; that belongs to P3.

## Block Classification

- `RECOVERABLE_BLOCK`: local test dependency or provider unavailable.
- `HARD_BLOCK`: canonical root/branch drift, active lifecycle action, or request to expose mutation without a task-bound gate.
