# Task Card P3: Assisted Canonical Bounded Model Patch

## Identity

- task_id: `single-mcp-three-lane-p3-assisted-canonical`
- campaign_id: `single-mcp-three-lane-fast-dispatch`
- artifact_authority: current
- status: IN_PROGRESS
- owner: James Chen
- objective: Invoke a bounded no-write model in plan mode, validate its unified diff, transactionally apply it to the clean canonical checkout, run scoped verifiers, commit, and return a Direct receipt without creating a Target.
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
- `tasks/single-mcp-three-lane-fast-dispatch/02-p2-dispatch-router.md`
- `nexus/orchestrator/unified_mcp_gateway.py`
- `tests/nexus/orchestrator/test_unified_mcp_gateway.py`
- `docs/arch/MODEL_WORKFORCE_POLICY.md`
- `nexus/config/model_workforce.yaml`

## Allowed Files

- `nexus/orchestrator/unified_mcp_gateway.py`
- `tests/nexus/orchestrator/test_unified_mcp_gateway.py`

## Required Behavior

1. Default provider is `agy` in plan/sandbox mode; no API-key provider path and no model filesystem mutation authority.
2. Model output must be structured JSON containing a unified diff; malformed, empty, out-of-scope, deletion, or base-drift patches fail closed.
3. Apply only on a clean canonical checkout under a process lock; run allowlisted verifier commands and reverse the exact patch on failure.
4. Successful commit is bounded to allowed files and returns provider/control-plane/verifier/commit telemetry plus a Direct receipt.
5. No Target, Candidate, or isolated lifecycle state is created.

## Verification Commands

```bash
git diff --check
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONDONTWRITEBYTECODE=1 PYTHONPYCACHEPREFIX=/tmp/nexus-gateway-pycache .venv/bin/python -m pytest -q -p no:cacheprovider tests/nexus/orchestrator/test_unified_mcp_gateway.py
.venv/bin/python scripts/ops/nexus_mcp_gateway.py --self-test
.venv/bin/python -m scripts.engine.nexus_cli self-hosted list-actionable
```

## Exit Criteria

- Injected model/apply tests prove successful and fail-closed paths without touching the canonical checkout.
- A real provider preflight is reported honestly if unavailable; no fake model success is accepted.
- All patch and verifier gates pass with a scoped commit and Direct receipt.

## Forbidden Scope

- No Target allocation, arbitrary shell, model auto-edit/accept-edits mode, approval, integration, push, or external DevSpace change.
- No automatic retry with a new logical task ID.
