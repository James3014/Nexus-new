# Task Card P6: Unified Gateway Runtime Identity

## Identity

- task_id: `single-mcp-three-lane-p6-runtime-cutover`
- campaign_id: `single-mcp-three-lane-fast-dispatch`
- artifact_authority: current
- status: COMPLETED
- owner: James Chen
- objective: Provide one authenticated loopback HTTP runtime for the unified gateway with health identity, deterministic manifest revision, and bounded request handling.
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

- `scripts/ops/nexus_mcp_gateway_http.py`
- `tests/nexus/orchestrator/test_unified_mcp_gateway_http.py`

## Required Behavior

1. Bind loopback by default; remote bind requires explicit opt-in.
2. Require bearer token on `/mcp`; reject non-POST MCP methods and oversized bodies.
3. `/health` reports `nexus-mcp-gateway`, current canonical HEAD, manifest revision, and tool count.
4. HTTP handler forwards JSON-RPC only to `UnifiedMCPGateway`; no second tool registry.
5. External DevSpace package/connector remains unchanged until a later fresh artifact and two-start cutover gate.

## Verification Commands

```bash
git diff --check
PYTHONDONTWRITEBYTECODE=1 PYTHONPYCACHEPREFIX=/tmp/nexus-gateway-pycache .venv/bin/python -m pytest -q -p no:cacheprovider tests/nexus/orchestrator/test_unified_mcp_gateway_http.py
```

## Exit Criteria

- Auth, method, body-size, health identity, and JSON-RPC forwarding tests pass.
- Scoped commit and Direct receipt exist.
- No public connector cutover is claimed by this card.

## Completion Evidence

- Runtime commit: `595b83c957c2c365279471c132267f220650d22e`
- Direct receipt: `a63177872d989fe16e792ebebbe8a5fc81e01edb58da00e48cfc84bfa9841996`
- Verification: HTTP gateway tests passed 5/5 with loopback bind permission; `git diff --check` passed.
