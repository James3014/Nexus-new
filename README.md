# Nexus

Nexus is a verification-oriented orchestration layer for auditable software
development. This repository's developer contract is deliberately split into
portable core checks, optional provider checks, and bounded test commands.

## Quick start

Create the pinned Python 3.12 environment and install the locked dependencies
first. This is the only bootstrap step required for a fresh checkout:

```bash
# Python 3.12 pin; locked, provider-free dependency bootstrap
UV_CACHE_DIR=/tmp/nexus-uv-cache uv sync --frozen --all-groups

# Core preflight, including repo_doctor and the CLI help smoke
bash scripts/ops/test_repo.sh environment
```

The core checks are secrets-free and do not require a provider CLI. The
preflight uses the project environment created by `uv sync`.

Provider readiness is a separate, optional lane. To report provider tool and
variable presence (values remain redacted), opt in explicitly:

```bash
NEXUS_PREFLIGHT_PROVIDER=1 bash scripts/ops/test_repo.sh environment
```

## Test command matrix

Use the repository-owned wrapper instead of ad-hoc full-suite commands:

```bash
bash scripts/ops/test_repo.sh fast                 # curated fast checks
bash scripts/ops/test_repo.sh changed <paths...>   # impacted tests
bash scripts/ops/test_repo.sh lint [files...]      # Ruff checks
bash scripts/ops/test_repo.sh fixture              # deterministic five-case smoke
bash scripts/ops/test_repo.sh full --confirm-full  # explicit full-suite escalation
```

The fixture mode is a local, provider-free smoke only; it does not establish a
live model, release, or production claim.

## Navigation

- [Contributing](CONTRIBUTING.md)
- [Testing runbook](docs/testing/test_runbook.md)
- [Bounded Codex context index](configs/codex_task_context_index.json)
- [OpenWiki quickstart](openwiki/quickstart.md) (derived, non-authoritative)

Repository and agent authority remains in `AGENTS.md`. Route, lifecycle, and
approval authority are not created by README or OpenWiki content.
