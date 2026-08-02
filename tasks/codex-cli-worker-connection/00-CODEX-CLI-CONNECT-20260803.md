# Task Card: CODEX-CLI-CONNECT-20260803

artifact_authority: current
task_id: `CODEX-CLI-CONNECT-20260803`
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

Connect the Nexus Codex worker to the installed Codex CLI and bind worker invocations to gpt-5.6-luna with medium reasoning. Modify only nexus/executors/worker_registry.py, nexus/executors/codex_executor.py, and nexus/services/unified_runtime.py. Codex preflight and invocation must share the registered provider executable resolution; preserve NEXUS_CODEX_BIN and PATH precedence with an executable-only ~/.local/bin/codex fallback; default model must be gpt-5.6-luna; add validated NEXUS_CODEX_REASONING_EFFORT defaulting to medium; pass -c model_reasoning_effort=medium to codex exec; preserve all existing sandbox and receipt controls; preserve unrelated dirty state. Do not modify tests, policy, user config, lockfiles, or unrelated paths. Do not integrate or push.

## Allowed files

- `nexus/executors/worker_registry.py`
- `nexus/executors/codex_executor.py`
- `nexus/services/unified_runtime.py`

## Verification commands

```bash
uv run python -m py_compile nexus/executors/worker_registry.py nexus/executors/codex_executor.py nexus/services/unified_runtime.py
uv run pytest -q -k "codex or registered_provider_executable" --maxfail=1
```

## Exit criteria

Owner review of the exact scoped commit.

## Block classification

Unverifiable or out-of-scope mutation is a HARD_BLOCK.
