---
type: Concept
title: CLI Commands & Cueline Operations
description: Operational reference for the Click-based nexus CLI entrypoint and the Cueline stdin-to-subprocess adapter.
tags: [cli, cueline, runtime, execution, commands]
openwiki:
  roles: [architecture, domain, operations]
  change_kinds: [public-api, workflow]
  source_paths: [scripts/engine/nexus_cli.py, scripts/ops/nexus_cueline_worker.py, pyproject.toml]
  symbols: [nexus, nexus_group, parse_and_validate_input, build_cli_argv, main]
  test_paths: [tests/test_cli_commands.py, tests/test_cli_dispatch.py, tests/ops/test_nexus_cueline_worker.py]
  invariants: [Main CLI entrypoint registered via pyproject.toml as nexus = scripts.engine.nexus_cli:nexus.]
  validation_commands: [pytest tests/test_cli_commands.py -q]
---

# CLI Commands & Cueline Operations

The primary command-line interface for Nexus Singularity OS is exposed via the `nexus` CLI entrypoint defined in `pyproject.toml` (`scripts.engine.nexus_cli:nexus`). The separate `nexus-cueline-worker` entrypoint (`scripts.ops.nexus_cueline_worker:main`) adapts one JSON request from stdin into one self-hosted CLI subprocess invocation.

---

## 🛠️ Main CLI Commands & Subcommand Dispatch

The `nexus` CLI is built using Click. The registered entrypoint exposes root commands and the nested `nexus` core command group. Use `nexus --help` and `nexus nexus --help` for the current command inventory.

### 1. Root Commands
- **`nexus status [--json]`**: Shows the direct status surface.
- **`nexus run TASK_ID`**: Compatibility alias that forwards to the nested core `run` command.
- **`nexus self-hosted --help`**: Lists self-hosted lifecycle commands.

### 2. Nested Core Commands
- **`nexus nexus status [--json]`**: Shows system status and trust scores.
- **`nexus nexus run TASK_ID`**: Runs the Nexus master loop for a task identifier.
- **`nexus nexus acceptance-check`**: Runs the acceptance check and hallucination guard.
- **`nexus nexus delivery-gate --evidence FILE`**: Runs fail-closed delivery verification.
- **`nexus nexus delivery-receipt`**: Reads the last machine-generated delivery receipt.

---

## ⚙️ Cueline Worker (`STANDALONE_OPS`)

`nexus-cueline-worker` operates on the `STANDALONE_OPS` surface as a single-request process adapter. It rejects positional CLI text, reads exactly one JSON object from stdin, validates the operation and its fields, and builds an argv list for `python -m scripts.engine.nexus_cli self-hosted <operation>`. It invokes that command with `subprocess.run(..., shell=False)`, forwards captured stdout and stderr, and returns the subprocess exit code. It does not poll a filesystem queue or create completion receipts itself; the `wait` request merely forwards timeout and poll-interval options to the self-hosted `wait` command.

Supported operations are `submit`, `status`, `wait`, `list-actionable`, `approve`, `integrate`, `dispose`, and `cancel`. For example:

```bash
printf '%s\n' '{"op":"status","task_id":"TASK_ID"}' | nexus-cueline-worker
```

---

## 🏷️ Required V3 Classifications

```yaml
component: NexusCLIEntrypoint
implementation_status: CURRENT
wiring_status: WIRED
runtime_surfaces:
  - MAIN_CLI
authority_roles:
  - EXECUTION_AUTHORITY
evidence_basis:
  - pyproject.toml:[tool.poetry.scripts].nexus
  - scripts/engine/nexus_cli.py:nexus
claim_ceiling: Registered Click command interface for the root and nested Nexus command groups.
```

```yaml
component: CuelineProcessAdapter
implementation_status: CURRENT
wiring_status: WIRED
runtime_surfaces:
  - STANDALONE_OPS
authority_roles:
  - EXECUTION_AUTHORITY
evidence_basis:
  - pyproject.toml:[tool.poetry.scripts].nexus-cueline-worker
  - scripts/ops/nexus_cueline_worker.py:main
claim_ceiling: Single-request stdin adapter that validates a Cueline payload and invokes one self-hosted Nexus CLI subprocess.
```

---

## 🛠️ Extension Recipe: Adding a Top-Level CLI Command

To add a new command to `scripts/engine/nexus_cli.py`:

1. **Implement Command Function**: Annotate with `@nexus.command(name="your-command")` and standard `@click.option` parameters.
2. **Handle Subprocesses Safely**: Build argv lists and invoke subprocesses without shell expansion.
3. **Bind Enforcer**: If the command produces code mutations, write completion envelopes via `[CompletionEnforcer](../governance/gates-and-contracts.md)`.
4. **Add Command Tests**: Create test functions in `tests/test_cli_commands.py`.
5. **Run Verification**: `pytest tests/test_cli_commands.py -q`.

---

## 🧭 Change Navigation & Validation

### When to Consult
Consult this page when adding CLI flags, changing the registered command inventory, or updating Cueline stdin validation and subprocess forwarding.

### Runtime Invariants
- The root `nexus` entrypoint and nested `nexus` command group are Click command surfaces.
- `nexus-cueline-worker` accepts one JSON object on stdin and invokes one self-hosted CLI command with `shell=False`.

### Exact Source Files & Symbols
- `scripts/engine/nexus_cli.py` -> `nexus`, `nexus_group` (Click groups)
- `scripts/ops/nexus_cueline_worker.py` -> `parse_and_validate_input`, `build_cli_argv`, `main`

### Focused Tests
- `tests/test_cli_commands.py`
- `tests/test_cli_dispatch.py`
- `tests/ops/test_nexus_cueline_worker.py`

### Minimal Validation Command
```bash
pytest tests/test_cli_commands.py -q
```
