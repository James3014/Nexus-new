# Task Card P4: Minimal Direct Completion Envelope

## Identity

- task_id: `single-mcp-three-lane-p4-direct-completion`
- campaign_id: `single-mcp-three-lane-fast-dispatch`
- artifact_authority: current
- status: COMPLETED
- owner: James Chen
- objective: Let GPT finish a Direct handoff with task ID, base revision, allowed files, verifiers, and expected commit only; derive all Target/controller roots inside the gateway.
- read_only: false
- audit_only: false
- commit_required: true
- candidate_required: false
- worker_may_commit: true
- worker_may_approve: false
- worker_may_integrate: false
- worker_may_push: false
- AUTO_CHAIN: false

## Allowed Files

- `nexus/orchestrator/unified_mcp_gateway.py`
- `tests/nexus/orchestrator/test_unified_mcp_gateway.py`

## Required Behavior

1. `nexus_task_finish` accepts a minimal Direct envelope and derives canonical paths server-side.
2. Raw caller-supplied Target roots are not required and cannot change the canonical authority.
3. Existing scoped commit, clean checkout, branch, worktree, verifier, and receipt gates remain unchanged.
4. Isolated owner-finish behavior remains exact-binding and human-gated.

## Verification Commands

```bash
git diff --check
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONDONTWRITEBYTECODE=1 PYTHONPYCACHEPREFIX=/tmp/nexus-gateway-pycache .venv/bin/python -m pytest -q -p no:cacheprovider tests/nexus/orchestrator/test_unified_mcp_gateway.py
.venv/bin/python scripts/ops/nexus_mcp_gateway.py --self-test
```

## Exit Criteria

- Minimal Direct finish test passes without Target/state creation.
- Existing gateway and assisted tests remain green.
- Scoped commit and Direct receipt exist.

## Completion Evidence

- Runtime commit: `123e639945c252c255b674d81702a9af56f441b1`
- Direct receipt: `8c4e99504774485d0424cc2712207028b8a148c2024b4fba713cab517dc14f52`
- Verification: 10 gateway tests passed; gateway self-test passed; `git diff --check` passed.
