# Nexus Refactor Remaining Start Evidence

Date: `2026-05-23`
Status: `READY_FOR_NEXT_SMALL_SLICES`

## 1. Completed In This Slice

| Area | Result | Evidence |
| --- | --- | --- |
| Research semantic runtime receipts | `DONE` | `nexus/app/research_semantic_runtime.py` now owns judge-panel, ASI constraint, architecture scout, external doc scout, harness runtime receipt, and formal report runtime receipt augmentation. |
| Research Flow compatibility | `DONE` | `research_flow_service.py` keeps `_augment_semantic_runtime_capabilities` as a physical alias to the new Module. |
| Focused tests | `PASS` | `tests/app/test_research_flow_service.py::test_research_semantic_runtime_module_writes_judge_panel_receipt` and compatibility / auto-flow semantic receipt tests passed. |
| Project memory SQLite retry writer | `DONE` | `nexus/core/memory_manager.py::ProjectMemoryManager._execute_with_retry` consumes `SQLiteRetryHandler`; busy/locked and non-busy fail-fast tests passed. |
| SkillRegistry SQLite retry second writer | `DONE` | `nexus/learning/skill_registry.py::SkillRegistry.upsert` and `update_win_rate` consume `SQLiteRetryHandler`; busy/locked retry and non-busy fail-fast tests passed. |

## 2. Completed SQLite Writer Pair

### 2.1 SQLite Second Writer

Current reusable Module:

- `nexus/infrastructure/sqlite_retry.py::SQLiteRetryHandler`

Already integrated writer:

- `nexus/core/memory_manager.py::ProjectMemoryManager._execute_with_retry`

Integrated second writer:

- `nexus/learning/skill_registry.py::SkillRegistry.upsert`
- `nexus/learning/skill_registry.py::SkillRegistry.update_win_rate`

Why this was accepted:

- It is a real SQLite writer with WAL mode and existing write-guard receipt.
- It has focused behavioral coverage in `tests/test_skill_sharing.py`.
- It is lower public-benchmark risk than `nexus/market/credit_ledger.py` and lower federation blast radius than `nexus/federation/node_registry.py`.

RED / characterization tests:

- `tests/test_skill_sharing.py::test_skill_registry_upsert_retries_sqlite_busy_then_success`
- `tests/test_skill_sharing.py::test_skill_registry_upsert_keeps_non_busy_errors_fail_fast`

Stop condition:

- Global `DatabaseTransactionManager` is still deferred until a third writer or repeated transaction-shape duplication appears.
- Do not silently swallow non-busy SQLite errors if retry classification says fail-fast.

Verification:

- `uv run pytest tests/test_skill_sharing.py tests/core/test_memory_manager_sqlite_retry.py tests/core/test_memory_manager_write_guard.py tests/infrastructure/test_sqlite_retry.py -q` -> `19 passed`.

## 3. Remaining Items Now Startable

### 3.1 External Fixture Live Clone / Setup

Current state:

- `scripts/bench/fixture_materialization.py` has `ExternalFixtureAdapter` and default `ExternalFixtureAdapterRequired` fail-closed behavior.
- `SandboxedLocalExternalFixtureAdapter` supports local/file sources and blocks remote URLs/path escapes.
- `ExternalFixtureCacheManifest` and `OfflineCachedExternalFixtureAdapter` now support pinned repo/ref -> local cache materialization without live network.
- `tests/benchmark/test_fixture_materialization.py` covers injected adapter, sandboxed local copy, remote URL block, path escape block, missing offline manifest, repo/ref denylist, and allowlisted local cache materialization.

Completed pregate evidence:

- Add an offline manifest contract before any live clone.
- First RED:
  - `tests/benchmark/test_fixture_materialization.py::test_live_external_fixture_adapter_requires_offline_cache_manifest`
  - `tests/benchmark/test_fixture_materialization.py::test_live_external_fixture_adapter_blocks_remote_without_allowlist`
- GREEN:
  - `uv run pytest tests/benchmark/test_fixture_materialization.py::test_live_external_fixture_adapter_requires_offline_cache_manifest tests/benchmark/test_fixture_materialization.py::test_live_external_fixture_adapter_blocks_remote_without_allowlist tests/benchmark/test_fixture_materialization.py::test_offline_cached_external_fixture_adapter_materializes_allowlisted_cache -q`
  - Result: `3 passed`.

Completed Interface:

- `ExternalFixtureCacheManifest`
  - `allowed_repo`
  - `allowed_ref`
  - `cache_dir`
  - `expected_files`
  - `network_allowed=False` default

Stop condition:

- No live `git clone`, `git fetch`, HTTP, SSH, or DNS in unit tests.
- Remote setup remains fail-closed until no-network barrier and explicit allowlist tests exist.
- `network_allowed=True` remains fail-closed; live network setup is not implemented in this pregate.

### 3.2 CLI Root Registration

Current state:

- `scripts/engine/commands/exception_translation.py` already preserves `KeyboardInterrupt`, `SystemExit`, and `click.Abort`.
- Many learn/research/multi-agent/bench bodies already live in Action modules.
- `scripts/engine/nexus_cli.py::sandbox_run_cmd` now delegates to `scripts/engine/commands/sandbox_actions.py`.

Completed evidence:

- First RED:
  - `uv run pytest tests/engine/test_sandbox_actions.py -q`
  - Result before implementation: `ModuleNotFoundError: No module named 'scripts.engine.commands.sandbox_actions'`.
- GREEN:
  - `uv run pytest tests/engine/test_sandbox_actions.py -q`
  - Result after implementation: `3 passed`.

Completed Module:

- `scripts/engine/commands/sandbox_actions.py`
  - `run_sandbox_task(repo_root: Path, task: str, *, runner_factory=...) -> SandboxRunResult`
  - `render_sandbox_run_result(result) -> list[str]`

Preserved stop condition:

- Action Module must not import Click.
- CLI adapter must preserve existing command name and output shape.
- Default `SandboxRunner` still lacks a real `run_task` Interface; the Action fails closed with `NexusCliActionError` rather than inventing success.

### 3.3 Benchmark Harness Facade

Current state:

- Direct runner, with-Nexus runner, socket barrier, provider failure policy, evidence artifact writer, evidence bundle gate/accounting/provider/row/manifest/payload/posture Modules are already split.
- `capability_ab_runner.py` remains orchestration facade.

Startable only if:

- A focused test exposes side-effect drift in public gate, accounting, provider context, or row mutation.

First acceptable RED examples:

- `tests/benchmark/test_capability_ab_runner.py::test_write_evidence_bundle_fails_cost_gate_when_provider_token_source_missing`
- `tests/benchmark/test_capability_ab_runner.py::test_session_worker_contamination_fails_public_claim_gate`
- `tests/benchmark/test_telemetry_fidelity.py`

Stop condition:

- Do not split benchmark orchestration from line count alone.
- Do not open live provider sockets.

### 3.4 ContextHub Storage / Retry

Current state:

- `nexus/core/context_budget_sources.py` and `nexus/core/context_text_store.py` are already split with deletion tests.
- ContextHub constructor / strict dependency behavior must remain stable.

Startable only if:

- A specific storage responsibility has caller map + deletion test.
- SQLite-backed fallback has a busy/locked fixture and does not duplicate `SQLiteRetryHandler`.

First RED:

- A monkeypatch-backed `ContextHub` facade test proving the new leaf is called before moving code.

### 3.5 Planner / Repair Deeper Split

Current state:

- `capability_planner.py` and `pipeline_repair.py` are still large but already have relevant submodules.

Startable only if:

- Policy-order, injection-equivalence, or repair/RLM acceptance tests fail.

Stop condition:

- No broad split from line count.

## 4. Recommended Next Execution Order

1. Real `SandboxRunner.run_task` Interface only after a separate physical sandbox execution contract is specified.
2. Live external fixture clone/setup only after live-network allowlist + socket/no-network barrier + cache provenance receipt are specified.
3. Benchmark orchestration only after a concrete side-effect drift test fails.
