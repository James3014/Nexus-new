# Task Card P8: Bounded Dispatch Soak Gate

## Identity

- task_id: `single-mcp-three-lane-p8-soak-gate`
- campaign_id: `single-mcp-three-lane-fast-dispatch`
- artifact_authority: current
- status: IN_PROGRESS
- owner: James Chen
- objective: Execute a deterministic bounded dispatch matrix proving that ordinary Direct and injected Assisted calls do not allocate Targets, while keeping real-provider and external-connector claims fail-closed.
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

- `tests/nexus/orchestrator/test_unified_mcp_gateway.py`

## Required Behavior

1. Run 10 Direct dispatches and 20 injected Assisted dispatches through one gateway identity.
2. Assert every Direct and Assisted response has `target_created: false` or no lifecycle submission and retains stable telemetry.
3. Run 10 isolated requests without a bound Task Card and assert fail-closed `TASK_CARD_BINDING_REQUIRED` with no Target submission.
4. Label this as synthetic/injected soak evidence; it does not establish real `agy` provider latency, external DevSpace installation, or GPT connector registration.

## Verification Commands

```bash
git diff --check
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONDONTWRITEBYTECODE=1 PYTHONPYCACHEPREFIX=/tmp/nexus-gateway-pycache .venv/bin/python -m pytest -q -p no:cacheprovider tests/nexus/orchestrator/test_unified_mcp_gateway.py
.venv/bin/python scripts/ops/nexus_mcp_gateway.py --self-test
```

## Exit Criteria

- The bounded synthetic matrix passes with no Target or lifecycle state allocation.
- Real-provider, external artifact, connector registration, and two-start identity remain explicit follow-up gates.
- Scoped commit and Direct receipt exist.
