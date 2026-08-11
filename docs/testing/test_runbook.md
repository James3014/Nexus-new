# Nexus testing runbook

This runbook describes the current, repository-owned verification commands.
Use the wrapper so core setup, focused tests, and full-suite escalation remain
distinct.

## Environment and provider lanes

```bash
bash scripts/ops/test_repo.sh environment
```

This runs the secrets-free `repo_doctor` core checks and the CLI help smoke.
Provider tools and variables are optional and are only reported when requested:

```bash
NEXUS_PREFLIGHT_PROVIDER=1 bash scripts/ops/test_repo.sh environment
```

The core verdict does not imply provider authentication or production readiness.

## Command matrix

| Mode | Command | Scope |
| --- | --- | --- |
| Fast | `bash scripts/ops/test_repo.sh fast` | Curated fast checks |
| Changed | `bash scripts/ops/test_repo.sh changed <paths...>` | Tests selected for changed paths |
| Lint | `bash scripts/ops/test_repo.sh lint [files...]` | Ruff on explicit files (default is the command-contract test) |
| Fixture | `bash scripts/ops/test_repo.sh fixture` | Exactly five deterministic provider-free smoke cases |
| Full | `bash scripts/ops/test_repo.sh full --confirm-full` | Fail-fast full suite; explicit escalation required |

For a direct focused test after bootstrap, use the project interpreter with a
concrete test path:

```bash
.venv/bin/python -m pytest -q <exact-test-path>
```

Do not use an unbounded test invocation as a repository contract.

## Required checks for documentation or command changes

```bash
PYTHONDONTWRITEBYTECODE=1 python3 scripts/ops/validate_codex_context_index.py configs/codex_task_context_index.json
PYTHONDONTWRITEBYTECODE=1 python3 -m pytest -q tests/ops/test_codex_task_context_index.py tests/ops/test_repo_test_commands.py tests/ops/test_repo_doctor.py
git diff --check
```

The context index is `non_authoritative_bounded_retrieval`; it cannot choose a
route, provider, model, worker, or lifecycle state. Its validator caps each
task class at four context files and 16,000 bytes, and caps the index at 8,000
bytes.

## Deterministic smoke boundary

The fixture smoke uses `scripts/ci/run_swebench_subset.py --mode smoke` and
`scripts/ci/smoke_cases.json`. It validates five local fixture/verifier pairs
and is intentionally separate from live provider or release evidence.
