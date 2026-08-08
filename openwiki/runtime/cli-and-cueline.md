---
type: Concept
title: CLI Commands & Cueline Operations
description: Operational reference for the primary nexus CLI entrypoint, delivery modes, health check levels, and Cueline background task processing.
tags: [cli, cueline, runtime, execution, commands]
openwiki:
  roles: [architecture, domain, operations]
  change_kinds: [public-api, workflow]
  source_paths: [scripts/engine/nexus_cli.py, scripts/ops/nexus_cueline_worker.py, pyproject.toml]
  symbols: [nexus, NexusCLI, CuelineWorker, main]
  test_paths: [tests/test_cli_commands.py, tests/test_cli_dispatch.py, tests/test_cli_health_commands.py]
  invariants: [Main CLI entrypoint registered via pyproject.toml as nexus = scripts.engine.nexus_cli:nexus.]
  validation_commands: [pytest tests/test_cli_commands.py -q]
---

# CLI Commands & Cueline Operations

The primary command-line interface for Nexus Singularity OS is exposed via the `nexus` CLI entrypoint defined in `pyproject.toml` (`scripts.engine.nexus_cli:nexus`). Background queue processing and asynchronous worker execution are handled separately by `nexus-cueline-worker` (`scripts.ops.nexus_cueline_worker:main`).

---

## 🛠️ Main CLI Commands & Subcommand Dispatch

The `nexus` CLI is built using Click / Typer and supports top-level commands as well as targeted sub-namespaces:

### 1. Delivery Gate Commands (`nexus:bug`, `nexus:feature`, `nexus:runner`)
- **`--delivery-mode ask`**: Prompts the user to confirm whether high-standard delivery is required for the task.
- **`--delivery-mode high`**: Enforces completion verification before task reporting. Automatically suggests verification commands for Python, Rust, and Go when `--verify` is omitted.
- Integrates with `[CompletionEnforcer](../governance/gates-and-contracts.md)` to generate verified completion receipts.

### 2. Health & Self-Heal Commands (`nexus:check`, `nexus:self-heal`)
- **`nexus:check --level quick`**: Fast snapshot-only local health audit.
- **`nexus:check --level standard`**: Single-case benchmark replay check.
- **`nexus:check --level high`**: Strict single-case health gate evaluation.
- **`nexus:check --level full`**: Complete benchmark lane evaluation.
- **`nexus:self-heal`**: Supports `--mode dry-run`, `--mode standard`, and `--mode strict`.

---

## ⚙️ Cueline Worker (`STANDALONE_OPS`)

`nexus-cueline-worker` operates on the `STANDALONE_OPS` surface. It monitors local file queues (`/tmp/nexus-cueline-jobs`), pulls task payloads, invokes `[SanitizedRunner](../architecture/overview.md)` for background task execution, and records completion receipts.

---

## 🏷️ Required V3 Classifications

```yaml
component: NexusCLI
implementation_status: CURRENT
wiring_status: WIRED
runtime_surfaces:
  - MAIN_CLI
authority_roles:
  - EXECUTION_AUTHORITY
evidence_basis:
  - pyproject.toml:[tool.poetry.scripts].nexus
  - scripts/engine/nexus_cli.py:nexus
claim_ceiling: Primary interactive CLI command interface for task execution, research flows, and system health checks.
```

```yaml
component: CuelineWorker
implementation_status: CURRENT
wiring_status: WIRED
runtime_surfaces:
  - STANDALONE_OPS
authority_roles:
  - EXECUTION_AUTHORITY
evidence_basis:
  - pyproject.toml:[tool.poetry.scripts].nexus-cueline-worker
  - scripts/ops/nexus_cueline_worker.py:main
claim_ceiling: Background task queue worker executing queued jobs on the STANDALONE_OPS surface.
```

---

## 🛠️ Extension Recipe: Adding a Top-Level CLI Command

To add a new command to `scripts/engine/nexus_cli.py`:

1. **Implement Command Function**: Annotate with `@nexus.command(name="your-command")` and standard `@click.option` parameters.
2. **Sanitize Inputs**: Wrap subprocess execution arguments with `SanitizedRunner.sanitize_arg()`.
3. **Bind Enforcer**: If the command produces code mutations, write completion envelopes via `[CompletionEnforcer](../governance/gates-and-contracts.md)`.
4. **Add Command Tests**: Create test functions in `tests/test_cli_commands.py`.
5. **Run Verification**: `pytest tests/test_cli_commands.py -q`.

---

## 🧭 Change Navigation & Validation

### When to Consult
Consult this page when adding CLI flags, modifying delivery confirmation prompts, adjusting health check thresholds, or updating background queue worker behavior.

### Runtime Invariants
- All subcommands must use `SanitizedRunner` for subprocess calls.
- `nexus-cueline-worker` operates independently from `MAIN_CLI` interactivity.

### Exact Source Files & Symbols
- `scripts/engine/nexus_cli.py` -> `nexus` (Click group), `NexusCLI`
- `scripts/ops/nexus_cueline_worker.py` -> `main`, `CuelineWorker`

### Focused Tests
- `tests/test_cli_commands.py`
- `tests/test_cli_dispatch.py`
- `tests/test_cli_health_commands.py`

### Minimal Validation Command
```bash
pytest tests/test_cli_commands.py -q
```
