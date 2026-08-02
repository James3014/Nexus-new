# Campaign Index: codex-cli-worker-connection

artifact_authority: current
owner: James Chen
status: active, governed and sequential
AUTO_CHAIN: false

## Objective

Connect the Nexus Codex worker to the installed Codex CLI and bind worker invocations to gpt-5.6-luna with medium reasoning. Modify only nexus/executors/worker_registry.py, nexus/executors/codex_executor.py, and nexus/services/unified_runtime.py. Codex preflight and invocation must share the registered provider executable resolution; preserve NEXUS_CODEX_BIN and PATH precedence with an executable-only ~/.local/bin/codex fallback; default model must be gpt-5.6-luna; add validated NEXUS_CODEX_REASONING_EFFORT defaulting to medium; pass -c model_reasoning_effort=medium to codex exec; preserve all existing sandbox and receipt controls; preserve unrelated dirty state. Do not modify tests, policy, user config, lockfiles, or unrelated paths. Do not integrate or push.

## Ordered cards

| Order | Task ID | Card | Status | Dependency |
|---:|---|---|---|---|
| 0 | `CODEX-CLI-CONNECT-20260803` | `00-CODEX-CLI-CONNECT-20260803.md` | ACTIVE | Owner confirmation |
