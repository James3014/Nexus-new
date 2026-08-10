# Contributing to Nexus

Keep changes bounded, reproducible, and independently verifiable. Read
[`AGENTS.md`](AGENTS.md) for repository authority and task-scope rules before
editing. Documentation and navigation pages cannot grant route, lifecycle,
approval, integration, or release authority.

## Setup

Bootstrap the pinned Python 3.12 environment from the lockfile first:

```bash
UV_CACHE_DIR=/tmp/nexus-uv-cache uv sync --frozen --all-groups
bash scripts/ops/test_repo.sh environment
```

The core preflight runs the portable doctor without reading `.env`, probing
credentials, or requiring provider tools.

Provider checks are optional and explicit:

```bash
NEXUS_PREFLIGHT_PROVIDER=1 bash scripts/ops/test_repo.sh environment
```

## Focused verification

Use the command matrix in `scripts/ops/test_repo.sh`:

```bash
bash scripts/ops/test_repo.sh fast
bash scripts/ops/test_repo.sh changed <changed-paths...>
bash scripts/ops/test_repo.sh lint <python-files...>
bash scripts/ops/test_repo.sh fixture
```

The fixture command runs exactly five deterministic local cases with checked
fixtures and verifiers. It is not a provider benchmark. A full regression is an
explicit escalation:

```bash
bash scripts/ops/test_repo.sh full --confirm-full
```

## Context and secrets

`configs/codex_task_context_index.json` is a bounded retrieval aid, not an
authority surface. Its validator enforces five task classes, concrete paths,
at most four context files per class, a 16,000-byte context ceiling, and an
8,000-byte index ceiling. Never add live secrets to documentation, fixtures, or
receipts; provider values are presence-only and redacted.

## Pull requests

Include the exact commands run, their outcomes, and the changed-file scope in
the pull request. Preserve historical reports and unrelated worktree changes.
