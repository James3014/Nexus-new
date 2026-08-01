# Task Card: provider-registry-open-cline-glm-52

artifact_authority: current
owner: James Chen
status: COMPLETED
task_id: provider-registry-open-cline-glm-52
commit_required: true
candidate_required: true
worker_may_commit: true
worker_may_approve: false
worker_may_integrate: false
worker_may_push: false
AUTO_CHAIN: false

## Objective

Make provider selection provider-neutral for all registered work adapters and
add Cline CLI / `glm-5.2` as an explicit conditional worker identity.

## Allowed files

- `nexus/executors/worker_contract.py`
- `nexus/executors/worker_registry.py`
- `nexus/orchestrator/unified_mcp_gateway.py`
- `nexus/services/unified_runtime.py`
- `nexus/config/model_workforce.yaml`
- `docs/arch/MODEL_WORKFORCE_POLICY.md`
- `tests/nexus/executors/test_worker_contract.py`
- `tests/nexus/orchestrator/test_unified_mcp_gateway.py`
- `tests/services/test_unified_runtime.py`
- `tests/services/test_model_workforce_policy_loader.py`

## Forbidden scope

- Do not remove external-runtime authorization, task-card, target, parser,
  verifier, human approval, or receipt gates.
- Do not invoke Cline or any model during this card; runtime availability is
  verified through deterministic preflight and command-shape tests only.
- Do not modify workforce-v21 closure artifacts, AGY account-pool state, old
  worktrees, or protected branches.

## Verification

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPYCACHEPREFIX=/tmp/nexus-provider-pycache uv run pytest -q tests/nexus/executors/test_worker_contract.py tests/nexus/orchestrator/test_unified_mcp_gateway.py tests/services/test_unified_runtime.py
PYTHONDONTWRITEBYTECODE=1 PYTHONPYCACHEPREFIX=/tmp/nexus-provider-policy-pycache uv run pytest -q tests/contracts/test_model_workforce_policy.py tests/services/test_model_workforce_policy_loader.py
git diff --check
```

## Exit criteria

- Registered assisted providers no longer return `ASSIST_PROVIDER_NOT_AUTHORIZED`.
- Unknown providers still fail closed as unregistered/unavailable.
- `cline` is present in the self-hosted provider contract and registry.
- `cline_glm_52` resolves to provider `cline`, exact model `glm-5.2`, and
  remains conditional until runtime evidence is collected.
- Existing safety and workforce admission tests remain green.

## Completion evidence

- Provider/model registry now includes Cline `glm-5.2`, Grok `grok-4.5`,
  OpenCode identities, MiMo `xiaomi/mimo-v2.5`, and all Ollama/local worker
  identities sourced from the workforce `workers` map.
- Gateway identity smoke resolved `cline_glm_52` to `provider=cline,
  model=glm-5.2` and returned `ASSIST_PROVIDER_UNAVAILABLE` when no live
  provider call was authorized; it did not return the old unauthorized gate.
- MiMo remains fail-closed at workforce admission because the existing policy
  records its account-balance blocker; registration is not a false availability
  claim.
- Verification: 212 focused provider/workforce tests passed; 142 Gateway and
  self-hosted lifecycle tests passed after the auto-route regression fix.

## Block classification

- `RECOVERABLE_BLOCK`: Cline binary/auth unavailable; deterministic registry and
  preflight evidence must still pass.
- `HARD_BLOCK`: opening a provider would require bypassing identity, adapter,
  verifier, approval, or receipt authority.
