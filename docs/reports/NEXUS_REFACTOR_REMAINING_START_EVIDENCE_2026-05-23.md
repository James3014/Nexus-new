# Nexus Refactor Remaining Start Evidence

Date: `2026-05-23`
Status: `READY_FOR_NEXT_SMALL_SLICES`

## 1. Completed In This Slice

| Area | Result | Evidence |
| --- | --- | --- |
| Research semantic runtime receipts | `DONE` | `nexus/app/research_semantic_runtime.py` now owns judge-panel, ASI constraint, architecture scout, external doc scout, harness runtime receipt, and formal report runtime receipt augmentation. |
| Research Flow compatibility | `DONE` | `research_flow_service.py` keeps `_augment_semantic_runtime_capabilities` as a physical alias to the new Module. |
| Research S2T runtime trace | `DONE` | `nexus/app/research_s2t_runtime.py` now owns autoreason candidate shaping plus S2T shadow event / episode payload serialization. |
| Research S2T compatibility | `DONE` | `research_flow_service.py` keeps `_autoreason_s2t_candidates` and `_record_autoreason_s2t_trace` physical aliases to the new Module. |
| Research auto-flow payload | `DONE` | `nexus/research/flow/auto_flow_payload.py` now owns the public auto-flow report envelope assembly. |
| Research 10-task helper leaves | `DONE` | `runtime_state.py`, `runtime_decision.py`, `report_io.py`, `task_classifier.py`, `governance_packets.py`, `capability_evidence.py`, `capability_planning.py`, and `model_training_export.py` now own formerly inline Research Flow helper responsibilities. |
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

## 2A. Completed Research S2T Runtime Trace Leaf

Current reusable Module:

- `nexus/app/research_s2t_runtime.py::record_autoreason_s2t_trace`
- `nexus/app/research_s2t_runtime.py::autoreason_s2t_candidates`

Why this was accepted:

- It owns a compact, deterministic S2T payload seam: candidate shaping, selector input, JSONL trace append, episode envelope, and cost fields.
- It keeps recursive runtime dispatch closed; this is only shadow trace serialization.
- `research_flow_service.py` keeps physical aliases so historical imports and monkeypatch bindings do not drift.

RED / characterization tests:

- `tests/app/test_research_s2t_runtime.py` initially failed with `ModuleNotFoundError: No module named 'nexus.app.research_s2t_runtime'`.
- `tests/app/test_research_flow_service.py::test_run_auto_flow_populates_autoreason_from_candidate_summaries` initially exposed that the facade still needed `S2TTraceEvent.from_dict` for model-training export.

GREEN:

- Added `research_s2t_runtime.py` and rewired `research_flow_service.py` to delegate `_autoreason_s2t_candidates` / `_record_autoreason_s2t_trace`.
- Kept `S2TTraceEvent` imported in the facade for the downstream training export contract.

Verification:

- `uv run pytest tests/app/test_research_s2t_runtime.py tests/app/test_research_flow_service.py::test_run_auto_flow_populates_autoreason_from_candidate_summaries -q` -> `3 passed`.

Stop condition:

- Do not extract auto-flow executor in this slice.
- Do not open recursive runtime dispatch.
- Any next Research Flow split needs a new focused payload snapshot or deletion test first.

## 2B. Completed Research Auto-Flow Payload Envelope Leaf

Current reusable Module:

- `nexus/research/flow/auto_flow_payload.py::AutoFlowPayloadParts`
- `nexus/research/flow/auto_flow_payload.py::build_auto_flow_payload`

Why this was accepted:

- It owns the top-level auto-flow report envelope shape: guard, learn phase SLO, strategy, success criteria, initial timing, and IO defaults.
- It keeps execution, cost accounting, runtime receipt writes, S2T export, and recursive dispatch outside the new Module.
- It reduces `research_flow_service.py` orchestration body without changing public report schema.

RED / characterization tests:

- `tests/research/test_auto_flow_payload.py` initially failed with `ModuleNotFoundError: No module named 'nexus.research.flow.auto_flow_payload'`.

GREEN:

- Added `auto_flow_payload.py` and rewired `run_auto_flow` to call `build_auto_flow_payload(AutoFlowPayloadParts(...))`.

Verification:

- `uv run pytest tests/research/test_auto_flow_payload.py tests/app/test_research_flow_service.py::test_run_auto_flow_populates_autoreason_from_candidate_summaries -q` -> `2 passed`.

Stop condition:

- This slice only moved envelope assembly.
- Do not extract baseline/hyper execution branches without a separate execution accounting snapshot.
- Do not open recursive runtime dispatch.

## 2C. Completed Research 10-Task Helper Leaf Slice

Completed tasks:

1. `research_s2t_runtime.py` owns S2T shadow trace serialization.
2. `auto_flow_payload.py` owns public auto-flow report envelope assembly.
3. `runtime_state.py` owns tuning / belief / capability / phase-SLO fast readers.
4. `runtime_decision.py` owns tier, HITL, claim-check, ASI record, and plateau decisions.
5. `report_io.py` owns output-file JSON write behavior.
6. `task_classifier.py` owns strict doc-fix classification.
7. `governance_packets.py` owns preflight, session, and governance event packets.
8. `model_training_export.py` owns S2T-backed model training export projection.
9. `capability_evidence.py` owns swarm/drone/nightshift/research/lancedb/semantic/ultra-review evidence shaping.
10. `capability_planning.py` owns capability stack compatibility, runtime budget/env skill mounts, and executor flag shaping.

Verification:

- `uv run pytest tests/research/test_flow_leaf_modules.py tests/research/test_auto_flow_payload.py tests/app/test_research_s2t_runtime.py tests/app/test_research_flow_service.py::test_run_auto_flow_populates_autoreason_from_candidate_summaries -q` -> `11 passed`.

Stop condition:

- `auto_flow_executor.py` is still not opened because baseline/hyper execution branch movement requires a separate execution-accounting snapshot covering guard fallback, token/cost, wall timing, and model/provider report fields.
- Recursive runtime dispatch remains closed.

## 2D. Auto-Flow Executor Accounting Snapshot Pregate

Status: `DONE_TESTS_ONLY_PREGATE`

What changed:

- Strengthened `tests/app/test_research_flow_service.py::test_hyper_guard_fallback_preserves_gateway_token_source`.
- The test now snapshots guard fallback execution accounting before any `auto_flow_executor.py` extraction: baseline probe status, guard hit, chosen/result flow, provider/model fields, token accounting, gateway token source, wall timing, and absence of recursive RLM dispatch by default.

RED / adjustment:

- First added assertion expected `winner_source` at top-level `result.report`.
- Live behavior keeps winner source inside `result.report.guard_fallback_from`, so the test was adjusted to pin current schema rather than silently changing report shape.

Verification:

- `uv run pytest tests/app/test_research_flow_service.py::test_hyper_guard_fallback_preserves_gateway_token_source -q` -> `1 passed`.

Decision:

- `auto_flow_executor.py` is now startable only as a tests-first split that preserves this snapshot.
- Do not open recursive runtime dispatch.
- Do not change provider/token report schema in the executor extraction slice unless a focused failing test requires it.

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
- Default runner characterization:
  - `uv run pytest tests/engine/test_sandbox_actions.py -q`
  - Result after adding `test_default_sandbox_runner_stays_fail_closed_until_physical_contract_exists`: `4 passed`.

Completed Module:

- `scripts/engine/commands/sandbox_actions.py`
  - `run_sandbox_task(repo_root: Path, task: str, *, runner_factory=...) -> SandboxRunResult`
  - `render_sandbox_run_result(result) -> list[str]`

Preserved stop condition:

- Action Module must not import Click.
- CLI adapter must preserve existing command name and output shape.
- `SandboxRunner.run_task(...)` now has a hardened local physical contract: explicit command, copied local workspace, source symlink non-following, relative cwd, optional output artifact collection with sha256 provenance, source git hook non-copy receipt, Python child external socket barrier, cleanup, timeout, exit code, stdout, stderr, and fail-closed path-escape handling.
- The contract intentionally does not wire `run_challenge(repo_url, task)` into `run_task(...)`; remote clone/fetch/network/hook behavior remains outside this slice.

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

Caller-map evidence added on 2026-05-23:

- `ContextHub.__init__` creates one local `ContextTextStore(self.project_root)` leaf.
- `ContextHub.load_program_rules(...)` delegates to `ContextTextStore.load_program_rules(...)`, which only reads `program.md`-style text via `Path.read_text(encoding="utf-8")` or returns the default rules string.
- `ContextHub._load_last_handoff()` delegates to `ContextTextStore.load_last_handoff()`, which only reads `.nexus/state/last_handoff.json` via UTF-8 JSON text and degrades to `{}` on missing/invalid JSON.
- `ContextHub._context_budget_sources(...)` delegates source shaping to `build_context_budget_sources(...)`; this leaf does not perform file or database I/O.
- Bounded search over `nexus/core/context_hub.py`, `nexus/core/context_text_store.py`, and `nexus/core/context_budget_sources.py` found no `sqlite3` or `SQLiteRetryHandler` usage.

Startable only if:

- A specific storage responsibility has caller map + deletion test.
- SQLite-backed fallback has a real caller, a busy/locked fixture, and does not duplicate `SQLiteRetryHandler`.

First RED:

- A monkeypatch-backed `ContextHub` facade test proving the new leaf is called before moving code.

Current decision:

- Do not add a ContextHub SQLite storage/retry leaf now: there is no third SQLite writer in the current ContextHub path, so a busy/locked fixture would be synthetic and would violate the evidence-first rule.

### 3.5 Planner / Repair Deeper Split

Current state:

- `capability_planner.py` and `pipeline_repair.py` are still large but already have relevant submodules.

Startable only if:

- Policy-order, injection-equivalence, or repair/RLM acceptance tests fail.

Stop condition:

- No broad split from line count.

## 4. Recommended Next Execution Order

1. No remote sandbox expansion until socket/no-network hard barrier, allowlist, hook policy, and artifact provenance have focused failing evidence.
2. Live external fixture clone/setup only after live-network allowlist + socket/no-network barrier + cache provenance receipt are specified.
3. Benchmark orchestration only after a concrete side-effect drift test fails.

## 5. 2026-05-23 Continuation Gate Revalidation

Status: `CONTEXT_HUB_FACADE_DELETION_TESTS_RESTORED`

### 5.1 Targeted Lessons Retrieved

| Source | Applicability | Plan effect |
| --- | --- | --- |
| `nexus_wiki_vault/06_Ops/Ops - Learning Closure Matrix.md` | Impact-map nodeids can drift and turn changed-only evidence false. | Any edited test/source/report path gets a focused impact-map row. |
| `nexus_wiki_vault/06_Ops/Ops - Learning Closure Matrix.md` | Seam successors must re-run first Adapter tests on the live checkout. | Plan/report `DONE` claims are not trusted without current focused tests. |
| `nexus_wiki_vault/06_Ops/Ops - Learning Closure Matrix.md` | ContextHub split must move one leaf with a facade deletion test. | ContextHub work resumed only at existing budget/text leaves; no constructor rewrite. |
| `docs/reports/NEXUS_RLM_RECURSIVE_DISPATCH_GATE_2026-05-22.json` | Recursive dispatch gate is bounded approval evidence, not permission for broad runtime dispatch. | Research runtime receipt work stays outside full recursive dispatch. |

### 5.2 Work Started And Completed

| Area | Previous live-checkout reality | Action | Result |
| --- | --- | --- | --- |
| ContextHub budget-source facade | `context_budget_sources.py` existed, but `ContextHub._context_budget_sources` still built sources inline. | Added monkeypatch deletion test and delegated to `build_context_budget_sources(...)`. | `DONE` |
| ContextHub text-store facade | `context_text_store.py` existed, but `ContextHub.load_program_rules` and `_load_last_handoff` still read files inline. | Added monkeypatch deletion test and delegated to `ContextTextStore`. | `DONE` |
| ContextHub token estimator | Split helper existed, but `ContextHub._estimate_context_tokens` still duplicated logic. | Delegated to `estimate_context_tokens(...)`. | `DONE` |
| Impact map coverage | ContextHub split source/test files had no focused rows. | Added rows for `context_hub.py`, `context_budget_sources.py`, `context_text_store.py`, and `test_context_hub_strict_deps.py`. | `DONE` |

Initial RED:

- `uv run pytest tests/core/test_context_hub_strict_deps.py::test_context_hub_uses_split_context_budget_source_builder tests/core/test_context_hub_strict_deps.py::test_context_hub_uses_split_context_text_store -q`
- Result: `2 failed`; `nexus.core.context_hub` had no `build_context_budget_sources` / `ContextTextStore` monkeypatch targets.

GREEN:

- `uv run pytest tests/core/test_context_hub_strict_deps.py::test_context_hub_uses_split_context_budget_source_builder tests/core/test_context_hub_strict_deps.py::test_context_hub_uses_split_context_text_store tests/core/test_context_budget_sources.py tests/core/test_context_text_store.py -q`
- Result: `6 passed`.

### 5.3 Current Remaining Gate Matrix

| Area | Current state | Can start now? | Next evidence before code |
| --- | --- | --- | --- |
| Benchmark harness facade | Focused provider-token, session-worker contamination, and telemetry fidelity probes pass. | `NO_SPLIT_NOW` | Only split if a future focused nodeid exposes a specific side-effect drift. |
| External fixture live clone/setup | Offline cache manifest pregate exists; live network remains fail-closed. | `NO` | Write live-network allowlist, no-network barrier, and cache provenance receipt tests. |
| CLI root registration / sandbox physical runner | Action seam exists; local `SandboxRunner.run_task(...)` physical contract now executes explicit local commands inside a copied workspace, blocks Python child external sockets, emits artifact provenance and hook-policy receipts, and fails closed on missing command / path escape. | `DONE_HARDENED_LOCAL_PHYSICAL_CONTRACT` | Next code slice only if non-Python command OS/kernel network isolation or live-network allowlist has new failing evidence. |
| Research runtime receipt next leaf | RLM trace, skill-mount receipt, semantic runtime receipt leaves exist. | `PARTIAL` | Snapshot auto-flow / S2T payload first; do not open recursive runtime dispatch. |
| ContextHub storage/retry next leaf | Budget/text facade delegation is now real; caller map confirms no current ContextHub SQLite writer. | `CALLER_MAP_DONE_NO_SQLITE` | Only start code if a real storage responsibility introduces SQLite-backed fallback plus busy/locked fixture. |
| SQLite transaction manager | Two writers share `SQLiteRetryHandler`. | `NO` | Need third writer or repeated transaction-shape duplication before global manager. |
| Skill-fit row/catalog indexing | `SkillFitRowIndex` covers followup RCA/cost row lookup; `SkillFitCatalogIndex` covers ablation-core catalog grouping; execution matrix row shape and candidate selection are now characterized through public builders. | `PARTIAL` | Production extraction remains deferred until candidate/execution duplication, row-contract drift, or a failing focused nodeid proves a new Module is needed. |
| SF2 bounded probe pipeline | Complexity scan still flags `sf2_bounded_probe.py`, but public static-receipt, validation, review, and completion gates are now characterized across pass and fail-closed paths. | `DONE_TESTS_ONLY_PREGATE` | Production extraction remains deferred until ordering/receipt drift, repeated duplication, or measured hot-path evidence appears. |
| Planner / repair deeper split | Existing seams sufficient. | `NO` | Need failing policy-order, injection-equivalence, or repair/RLM acceptance evidence. |
| Root hygiene | Untracked generated artifacts reduced; `docs/info/nexus_flow.html` and `.json` intentionally retained. | `PARTIAL` | Decide whether retained `docs/info` flow artifacts are official docs or local artifacts before tracking. |

### 5.3.1 Local Analysis Tools And Hook Decision

Status: `HOOK_REEVALUATED_NO_2026-05-23`

Tool ranking:

- `docs/info/nexus_flow.json/html`: useful now as retained architecture/topology orientation; it is not source-code dependency evidence.
- `codex-complexity-optimizer`: useful as heuristic hotspot scanner; findings require characterization tests before code changes.
- `codegraph-audit`: useful now only as a disposable snapshot index; current evidence used `/private/tmp/nexus-codegraph-snapshot.GTTKZf/.codegraph` so no Nexus repo artifact or hook ownership was introduced.
- `repomix`: useful only for narrow `--stdout` handoff bundles; broad/default runs can create `repomix-output.xml` and are not needed for this slice.
- `graphify`: deferred; current Nexus `graphify-runs` has empty subdirectories but no artifact files observed, and hook/install commands would add artifact/hook ownership questions.

Hook decision:

- No new hook was installed in this slice.
- Reason: the current safe improvement path was a focused TDD row-index/catalog-index seam. CodeGraph is allowed as disposable snapshot evidence; Graphify/CodeGraph hooks would add workspace artifacts and Git hook behavior without being necessary for the verified change.

Tool rerun evidence:

- The memory path `/Users/jameschen/.codex/skills/complexity-optimizer/scripts/analyze_complexity.py` is stale in this checkout.
- Current scanner path: `/Users/jameschen/Workspace/test/codex-complexity-optimizer/complexity-optimizer/scripts/analyze_complexity.py`.
- Scoped reruns against `nexus/learning`, `nexus/core`, and `scripts/ops` confirmed heuristic hits only; the current safe action is characterization tests, not production extraction or hook installation.

### 5.3.2 Missing Evidence Top-Up

Status: `DONE_HARDENED_LOCAL_PHYSICAL_CONTRACT_2026-05-23`

What changed:

- Added default-runner physical contract for `nexus sandbox run`: `SandboxRunner.run_task(...)` requires an explicit command, copies the local project into `.nexus/sandbox/runs/<run_id>/workspace` without following source symlinks, runs inside the requested sandbox-relative cwd, records stdout/stderr/exit code/timeout metadata, optionally collects a sandbox-relative output artifact with sha256/size provenance, injects a Python child `sitecustomize.py` external socket barrier, emits a hook policy receipt proving source git metadata/hooks are not copied, cleans the copied workspace by default, and fails closed for cwd/output path escape.
- Added ContextHub storage caller-map evidence: current ContextHub split path reads only UTF-8 text/JSON through `ContextTextStore` and shapes budget sources through `build_context_budget_sources(...)`; no ContextHub SQLite writer exists.
- Restored live CLI adapter wiring for registry/skills Actions: `nexus_cli.py` now imports `registry_actions.py`, delegates `skills sync`, `skills list`, and `registry status`, and applies `translate_action_exceptions`.
- Completed the remaining CLI live Action adapter sweep: `bench effort`, `code impact/scan/context`, `multi-agent`, `learn/ask`, and `research` command groups now import/delegate Action functions and renderers from `scripts/engine/commands/*_actions.py`; `research:run` old inline implementation was physically deleted from `nexus_cli.py`.

Verification:

- RED artifact provenance：`tests/engine/test_sandbox_actions.py::test_default_sandbox_runner_executes_local_command_and_collects_output` -> failed with `KeyError: 'output_artifact'`; GREEN added sandbox-relative path, artifact path, sha256, and size receipt.
- RED Python socket barrier：`tests/engine/test_sandbox_actions.py::test_default_sandbox_runner_blocks_python_external_socket` -> external Python socket initially succeeded; GREEN injects runner-owned `sitecustomize.py` and blocks `example.com:80` before DNS/network use.
- RED hook policy receipt：`tests/engine/test_sandbox_actions.py::test_default_sandbox_runner_does_not_copy_source_git_hooks` -> failed with `KeyError: 'hook_policy'`; GREEN emits source git metadata / hook non-copy receipt.
- `uv run pytest tests/engine/test_sandbox_actions.py -q` -> `10 passed`.
- `uv run python -m py_compile nexus/engine/sandbox_runner.py scripts/engine/commands/sandbox_actions.py scripts/engine/nexus_cli.py tests/engine/test_sandbox_actions.py` -> `PASSED`.
- `uv run pytest tests/engine/test_sandbox_actions.py tests/engine/test_cli_artifact_gate_audit.py tests/engine/test_cli_semantic_contract_audit.py tests/test_cli_commands.py -q` -> `49 passed`.
- `uv run pytest tests/engine/test_bench_actions.py tests/engine/test_code_actions.py tests/engine/test_multi_agent_actions.py tests/engine/test_learn_actions.py tests/engine/test_research_actions.py tests/engine/test_registry_actions.py tests/engine/test_sandbox_actions.py -q` -> `101 passed`.
- `uv run scripts/ops/ci_gate.py --changed-only nexus/engine/sandbox_runner.py scripts/engine/commands/sandbox_actions.py scripts/engine/nexus_cli.py tests/engine/test_sandbox_actions.py docs/testing/test_impact_map.md docs/plans/NEXUS_CLEAN_CODE_LINUS_REFACTOR_PLAN_2026-05-22.md docs/reports/NEXUS_REFACTOR_REMAINING_START_EVIDENCE_2026-05-23.md "nexus_wiki_vault/06_Ops/Ops - Learning Closure Matrix.md"` -> `Changed-Only JIT Tests PASSED`.
- `uv run scripts/ops/ci_gate.py` -> `ALL QUALITY GATES PASSED`.
- `uv run pytest tests/engine/test_registry_actions.py -q` -> RED `6 failed` before wiring, GREEN `12 passed` after wiring.
- `uv run pytest tests/engine/test_registry_actions.py tests/engine/test_cli_exception_translation.py tests/engine/test_nexus_cli_registry.py -q` -> `20 passed`.
- `uv run scripts/ops/ci_gate.py --changed-only scripts/engine/nexus_cli.py scripts/engine/commands/registry_actions.py tests/engine/test_registry_actions.py docs/testing/test_impact_map.md docs/plans/NEXUS_CLEAN_CODE_LINUS_REFACTOR_PLAN_2026-05-22.md docs/reports/NEXUS_REFACTOR_REMAINING_START_EVIDENCE_2026-05-23.md "nexus_wiki_vault/06_Ops/Ops - Learning Closure Matrix.md"` -> initial fallback failure from missing `tests/engine/test_registry_actions.py` self row; after adding the self row, `Changed-Only JIT Tests PASSED`.
- `uv run pytest tests/engine/test_bench_actions.py -q` -> RED `2 failed` before bench live adapter import, GREEN `4 passed` after wiring.
- `uv run pytest tests/engine/test_bench_actions.py tests/engine/test_code_actions.py tests/engine/test_multi_agent_actions.py tests/engine/test_learn_actions.py tests/engine/test_research_actions.py tests/engine/test_registry_actions.py tests/engine/test_sandbox_actions.py -q` -> RED `66 passed, 29 failed` before broad live adapter sweep; GREEN `95 passed` after wiring code/multi-agent/learn/research live adapters.
- `uv run pytest tests/engine/test_code_actions.py tests/engine/test_multi_agent_actions.py -q` -> `33 passed`.
- `uv run pytest tests/engine/test_learn_actions.py -q` -> `30 passed`.
- `uv run python -m py_compile scripts/engine/nexus_cli.py` -> compile `PASSED`.
- `uv run pytest tests/engine/test_research_actions.py -q` -> `12 passed`.
- `uv run scripts/ops/ci_gate.py` -> initial Report Trust Audit failure: old source-token audits still required `build_completion_envelope(` / `write_text(` inside `nexus_cli.py` command blocks after Action extraction; `learn:ingest` also needed the CLI compatibility semantic evaluator seam passed into `run_learn_ingest(...)`.
- Fix: `nexus_cli.py` now passes CLI-compatible learn seams (`_write_hallucination_evidence`, `_enforce_hallucination_gate`, `_write_dual_gate_markdown`, `_evaluate_learn_semantic_contract`) into learn Actions; `test_cli_semantic_contract_audit.py` and `test_cli_artifact_gate_audit.py` now check delegated Action modules for semantic/artifact tokens while verifying the CLI block delegates to Action functions.
- `uv run pytest tests/engine/test_cli_semantic_contract_audit.py tests/engine/test_cli_artifact_gate_audit.py tests/test_cli_learn_mode.py::test_learn_ingest_fails_closed_when_semantic_contract_unverified -q` -> `5 passed`.
- `uv run scripts/ops/ci_gate.py --changed-only scripts/engine/nexus_cli.py tests/engine/test_cli_semantic_contract_audit.py tests/engine/test_cli_artifact_gate_audit.py docs/testing/test_impact_map.md docs/plans/NEXUS_CLEAN_CODE_LINUS_REFACTOR_PLAN_2026-05-22.md docs/reports/NEXUS_REFACTOR_REMAINING_START_EVIDENCE_2026-05-23.md "nexus_wiki_vault/06_Ops/Ops - Learning Closure Matrix.md"` -> `Changed-Only JIT Tests PASSED`.
- `uv run scripts/ops/ci_gate.py` -> `ALL QUALITY GATES PASSED`.

Residual:

- Sandbox remote/network/hook expansion remains deferred; current physical runtime is local-only and blocks Python child external sockets, but does not claim OS/kernel-level network isolation for arbitrary non-Python executables.
- ContextHub SQLite retry remains deferred until a real storage responsibility introduces a SQLite-backed fallback with busy/locked fixture evidence.
- CLI root registration remains a Click group/compat-shim facade, but live command Action adapter wiring is now complete for the tested command groups. Further CLI work requires a new output schema, deprecated alias, or registration audit failure; no broad CLI rewrite is open.

### 5.3.3 Benchmark Harness Facade Evidence Probe

Status: `NO_SPLIT_NOW`

Probe:

- `uv run pytest tests/benchmark/test_capability_ab_runner.py::test_write_evidence_bundle_fails_cost_gate_when_provider_token_source_missing tests/benchmark/test_capability_ab_runner.py::test_session_worker_contamination_fails_public_claim_gate tests/benchmark/test_telemetry_fidelity.py -q`
- Result: `6 passed`.

Decision:

- Provider token-source accounting, session-worker contamination, and telemetry fidelity are currently protected by focused tests.
- No new side-effect drift was observed, so `capability_ab_runner.py` should not be split from line count alone.
- Next benchmark-harness work must start from a new failing focused nodeid that names the exact seam: provider context, public gate serialization, row mutation, or telemetry canonicalization.

### 5.4 P6B Capability Invocation Matrix Completion Slice

Status: `DONE_COMPLETION_SLICE`

What changed:

- Added `scripts/ops/capability_invocation_index.py` as the arm-level deep module for JSONL receipt rows.
- Reduced `scripts/ops/capability_invocation_matrix.py` to reuse `build_arm_index(rows)` for JSONL arms while keeping smoke-summary and matrix orchestration in the facade.
- Added precise changed-only impact rows for `capability_invocation_matrix.py`, `capability_invocation_index.py`, and `test_capability_invocation_matrix.py`.
- Added a changed-only selector hook test proving `scripts/ops/capability_invocation_matrix.py` selects focused matrix tests without broad `tests/ops` fallback.
- Added malformed receipt string characterization so invalid `capability_receipts` fail closed through `CapabilityInvocationArmIndex` instead of crashing or silently passing.

TDD evidence:

- RED: `uv run pytest tests/ops/test_capability_invocation_matrix.py::test_capability_invocation_arm_index_preserves_jsonl_diagnostics -q`
- Result: `ModuleNotFoundError: No module named 'scripts.ops.capability_invocation_index'`.

GREEN:

- `uv run python -m py_compile scripts/ops/capability_invocation_index.py scripts/ops/capability_invocation_matrix.py tests/ops/test_capability_invocation_matrix.py`
- Result: `PASSED`.
- `uv run pytest tests/ops/test_capability_invocation_matrix.py tests/ops/test_ci_gate_report_trust_audit.py::test_run_changed_only_check_selects_capability_invocation_matrix_targets -q`
- Result: `8 passed`.
- `uv run scripts/ops/ci_gate.py --changed-only scripts/ops/capability_invocation_index.py scripts/ops/capability_invocation_matrix.py tests/ops/test_capability_invocation_matrix.py tests/ops/test_ci_gate_report_trust_audit.py docs/testing/test_impact_map.md docs/plans/NEXUS_CLEAN_CODE_LINUS_REFACTOR_PLAN_2026-05-22.md docs/reports/NEXUS_REFACTOR_REMAINING_START_EVIDENCE_2026-05-23.md "nexus_wiki_vault/06_Ops/Ops - Learning Closure Matrix.md"`
- Result: `Changed-Only JIT Tests PASSED`.
- `uv run scripts/ops/ci_gate.py`
- Result: `ALL QUALITY GATES PASSED`.

Residual:

- P6B does not claim performance improvement; it only establishes locality and focused regression protection.
- No new CI hard gate was added because changed-only impact-map selection is the existing approved hook.

### 5.5 P6A Skill-Fit Data-Shape Pregate

Status: `DONE_INITIAL_PREGATE`

What changed:

- Added `build_skill_fit_data_shape_pregate(...)` in `nexus/learning/skill_fit_status.py`.
- Added `tests/learning/test_skill_fit_data_shape_pregate.py` with four pure in-memory checks.
- Added precise changed-only impact rows for `skill_fit_status.py` and the new pregate test file.

TDD evidence:

- RED: `uv run pytest tests/learning/test_skill_fit_data_shape_pregate.py::test_skill_fit_data_shape_pregate_passes_minimal_complete_chain -q`
- Result: `ImportError: cannot import name 'build_skill_fit_data_shape_pregate' from 'nexus.learning.skill_fit_status'`.

GREEN:

- `uv run pytest tests/learning/test_skill_fit_data_shape_pregate.py -q`
- Result: `4 passed`.

Residual:

- This pregate itself did not refactor `skill_fit_followup.py` or `skill_fit_ablation_core.py`.
- Follow-up row indexing for `skill_fit_followup.py` is recorded in section 5.6; `skill_fit_ablation_core.py` still needs a separate characterization slice.

### 5.6 P6A.1 SkillFitRowIndex Initial Slice

Status: `DONE_INITIAL_SLICE`

What changed:

- Added frozen `SkillFitRowIndex` in `nexus/learning/skill_fit_followup.py`.
- Routed `build_skill_fit_row_level_rca(...)` and `build_skill_fit_cost_phase_contract(...)` through the shared row index.
- Added a deletion/characterization test for capability filtering, baseline lookup, skill grouping, catalog lookup, tuple-backed row groups, and deterministic skill order.
- Added focused changed-only impact-map rows for `nexus/learning/skill_fit_followup.py` and the edited `tests/learning/test_skill_fit_ablation.py` test file.

TDD evidence:

- RED: `uv run pytest tests/learning/test_skill_fit_ablation.py::test_skill_fit_row_index_groups_baselines_catalog_and_skill_rows_for_rca_and_cost -q`
- Result: `ImportError: cannot import name 'SkillFitRowIndex' from 'nexus.learning.skill_fit_followup'`.

GREEN:

- `uv run pytest tests/learning/test_skill_fit_ablation.py::test_skill_fit_row_index_groups_baselines_catalog_and_skill_rows_for_rca_and_cost -q`
- Result: `1 passed`.

Guard:

- `uv run pytest tests/learning/test_skill_fit_data_shape_pregate.py tests/learning/test_skill_fit_ablation.py::test_skill_fit_row_index_groups_baselines_catalog_and_skill_rows_for_rca_and_cost tests/learning/test_skill_fit_ablation.py::test_skill_fit_row_level_rca_recommends_targeted_replay_for_promising_governance_skill tests/learning/test_skill_fit_ablation.py::test_skill_fit_cost_phase_contract_separates_cost_from_delivery_claims -q`
- Result: `7 passed`.

Changed-only selector lesson:

- First changed-only attempt treated `tests/learning/test_skill_fit_ablation.py` as unmatched, escalated to broad `tests/core`, and failed on missing local Playwright browser for `tests/core/test_web_dom_mapper.py`.
- Resolution: added the test-file self impact row and recorded the prevention lesson in the Learning Closure Matrix.

Residual:

- This slice does not touch runtime promotion, public benchmark gates, or `skill_fit_ablation_core.py`.
- The ablation-core catalog grouping follow-up is tracked separately in section 5.6.1.

### 5.6.1 P6A.2 SkillFitCatalogIndex Initial Slice

Status: `DONE_INITIAL_SLICE`

What changed:

- Added frozen `SkillFitCatalogIndex` in `nexus/learning/skill_fit_ablation_core.py`.
- Routed `build_skill_fit_catalog(...)` through the shared catalog index for row collection, capability-only rows, negative-control rows, and `(capability, skill_id)` grouping.
- Added a deletion/characterization test for capability/skill grouping, negative-control separation, capability-only row accounting, stable key ordering, and tuple-backed row groups.
- Added focused changed-only impact-map rows for `nexus/learning/skill_fit_ablation_core.py` and the edited `tests/learning/test_skill_fit_ablation.py` test file.

TDD evidence:

- RED: `uv run pytest tests/learning/test_skill_fit_ablation.py::test_skill_fit_catalog_index_groups_rows_by_capability_and_skill_id -q`
- Result: `ImportError: cannot import name 'SkillFitCatalogIndex' from 'nexus.learning.skill_fit_ablation_core'`.

GREEN:

- `uv run pytest tests/learning/test_skill_fit_ablation.py::test_skill_fit_catalog_index_groups_rows_by_capability_and_skill_id -q`
- Result: `1 passed`.

Guard:

- `uv run pytest tests/learning/test_skill_fit_ablation.py::test_skill_fit_catalog_requires_receipt_backed_effective_rows tests/learning/test_skill_fit_ablation.py::test_skill_fit_catalog_groups_verdicts_by_capability_and_skill_id tests/learning/test_skill_fit_ablation.py::test_skill_fit_catalog_index_groups_rows_by_capability_and_skill_id tests/learning/test_skill_fit_ablation.py::test_skill_fit_catalog_returns_when_matrix_incomplete tests/learning/test_skill_fit_data_shape_pregate.py tests/learning/test_skill_fit_ablation.py::test_skill_fit_row_index_groups_baselines_catalog_and_skill_rows_for_rca_and_cost tests/learning/test_skill_fit_ablation.py::test_skill_fit_row_level_rca_recommends_targeted_replay_for_promising_governance_skill tests/learning/test_skill_fit_ablation.py::test_skill_fit_cost_phase_contract_separates_cost_from_delivery_claims -q`
- Result: `11 passed`.

Residual:

- This slice does not change verdict policy, promotion policy, runtime apply, public benchmark gates, or production candidate selection.
- `skill_fit_ablation_core.py` now has catalog grouping, execution matrix row-shape, and candidate selection characterization; production extraction still needs focused drift or duplication evidence.

### 5.6.2 P6A.3 Execution Matrix Row-Shape Characterization

Status: `DONE_TESTS_ONLY_PREGATE`

What changed:

- Added `tests/learning/test_skill_fit_ablation.py::test_execution_matrix_characterizes_public_row_shape_for_all_arm_types`.
- The test uses only `build_skill_fit_ablation_plan(...)` and `build_skill_fit_execution_matrix(...)`.
- It fixes row id shape, task refs, model propagation, gate requirements, runner args, runner env, mount requests, and expected outcomes for `capability_only`, `skill_ablation`, and `wrong_or_quarantined_skill`.
- No production code changed; this is a deletion/characterization test before any future execution-matrix extraction.

Verification:

- `uv run pytest tests/learning/test_skill_fit_ablation.py::test_execution_matrix_characterizes_public_row_shape_for_all_arm_types tests/learning/test_skill_fit_ablation.py::test_execution_matrix_expands_tasks_by_arms_without_claiming_value tests/learning/test_skill_fit_ablation.py::test_skill_fit_catalog_index_groups_rows_by_capability_and_skill_id -q`
- Result: `3 passed`.
- `uv run scripts/ops/ci_gate.py --changed-only <refactor-slice paths>`
- Result: `Changed-Only JIT Tests PASSED`.

Decision:

- Do not extract a `SkillFitExecutionMatrixIndex` yet. The public row contract is now pinned, but there is not enough duplicated production logic to justify a new Module.
- Do not install a hook. The changed-only impact map and focused nodeids are sufficient for this slice without taking ownership of git hooks or background indexes.

### 5.6.3 P6A.4 Candidate Selection Public-Plan Characterization

Status: `DONE_PROMOTED_TO_CANDIDATE_INDEX`

What changed:

- Added `tests/learning/test_skill_fit_ablation.py::test_skill_fit_plan_characterizes_public_candidate_selection_contract`.
- The test uses only `build_skill_fit_ablation_plan(...)`.
- It fixes the current candidate selection contract: one highest-relevance runtime baseline first, then preferred/external distinct candidates, while blocked repair skills, generic skills, and canonical `gstack-` aliases are excluded.
- The characterization was promoted into a production `SkillFitCandidateIndex` extraction after bounded inspection showed canonical skill id and negative-control candidate logic was shared by plan construction and follow-up candidate reports.

TDD evidence:

- RED: initial expectation assumed fixed `nexus-tdd` first; live public contract selected higher-relevance `runtime-repair` as the single runtime baseline.
- GREEN: `uv run pytest tests/learning/test_skill_fit_ablation.py::test_skill_fit_plan_characterizes_public_candidate_selection_contract -q`
- Result: `1 passed`.
- Guard: `uv run pytest tests/learning/test_skill_fit_ablation.py::test_skill_fit_plan_characterizes_public_candidate_selection_contract tests/learning/test_skill_fit_ablation.py::test_plan_prefers_named_repair_candidates_over_generic_candidates tests/learning/test_skill_fit_ablation.py::test_plan_dedupes_gstack_prefixed_skill_aliases tests/learning/test_skill_fit_ablation.py::test_execution_matrix_characterizes_public_row_shape_for_all_arm_types -q`
- Result: `4 passed`.
- Changed-only: `uv run scripts/ops/ci_gate.py --changed-only <refactor-slice paths>`
- Result: `Changed-Only JIT Tests PASSED`.

Candidate-index extraction:

- Added `nexus/learning/skill_fit_candidate_index.py::SkillFitCandidateIndex`.
- Routed `skill_fit_ablation_core.py` candidate matching, explicit skill selection, selected-arm ordering, canonical id normalization, and negative-control selection through the new Module.
- Routed `skill_fit_followup.py` canonical id normalization and negative-control selection through the same Module.
- Added `tests/learning/test_skill_fit_ablation.py::test_skill_fit_candidate_index_preserves_plan_selection_contract`.

RED / GREEN:

- RED: `uv run pytest tests/learning/test_skill_fit_ablation.py::test_skill_fit_candidate_index_preserves_plan_selection_contract -q`
- Result: `ModuleNotFoundError: No module named 'nexus.learning.skill_fit_candidate_index'`.
- GREEN: `uv run pytest tests/learning/test_skill_fit_ablation.py::test_skill_fit_candidate_index_preserves_plan_selection_contract tests/learning/test_skill_fit_ablation.py::test_skill_fit_plan_characterizes_public_candidate_selection_contract tests/learning/test_skill_fit_ablation.py::test_plan_dedupes_gstack_prefixed_skill_aliases tests/learning/test_skill_fit_ablation.py::test_research_candidate_v2_report_excludes_rejected_and_selects_source_discipline_candidates tests/learning/test_skill_fit_ablation.py::test_research_candidate_v3_requires_observable_source_discipline_behaviors -q`
- Result: `5 passed`.
- Compile: `uv run python -m py_compile nexus/learning/skill_fit_candidate_index.py nexus/learning/skill_fit_ablation_core.py nexus/learning/skill_fit_followup.py tests/learning/test_skill_fit_ablation.py`
- Result: passed.

Decision:

- Do not expand `SkillFitCandidateIndex` into promotion policy, runtime policy, or public benchmark gate logic. It only pre-indexes candidate rows and returns deterministic candidate selections.
- Do not install a hook. The existing changed-only impact map should cover this by adding the new nodeid to the skill-fit rows.

### 5.7 P6C Ordered-Data Pregate

Status: `STARTABLE_AS_TESTS_ONLY_PREGATE`

Bounded exploration result:

- `nexus/contracts/s2t_export.py` can receive a characterization test for rejected-candidate ordering.
- `nexus/engine/asi_constraints.py` can receive a characterization test for family ordering, confidence, evidence refs, and low-step semantics.
- Production refactor is not justified yet because both files are small; tests should prove data-shape drift before code changes.

Existing evidence:

- `uv run pytest --collect-only -q tests/contracts/test_s2t_contracts.py tests/engine/test_asi_constraints.py -p no:cacheprovider`
- Result: `14 tests collected`.
- `uv run pytest tests/contracts/test_s2t_contracts.py tests/engine/test_asi_constraints.py -q -p no:cacheprovider`
- Result: `14 passed in 0.27s`.

Stop condition:

- Do not change production code unless the ordered-data characterization tests expose real drift.

Completed:

- Added `tests/contracts/test_s2t_contracts.py::test_s2t_export_selects_highest_scored_failed_rejected_candidate_stably`.
- Added `tests/engine/test_asi_constraints.py::test_asi_constraint_extractor_orders_families_and_preserves_evidence_refs`.
- Added impact-map rows for `nexus/contracts/s2t_export.py`, `nexus/engine/asi_constraints.py`, and edited test files.
- Production refactor remains deferred because the characterization tests passed.

Verification:

- `uv run pytest tests/contracts/test_s2t_contracts.py::test_s2t_export_selects_highest_scored_failed_rejected_candidate_stably tests/engine/test_asi_constraints.py::test_asi_constraint_extractor_orders_families_and_preserves_evidence_refs -q`
- Result: `2 passed`.

### 5.8 P6D SF2 Bounded-Probe Fail-Closed Characterization

Status: `DONE_TESTS_ONLY_PREGATE`

Tool signal:

- `codex-complexity-optimizer` rerun against `nexus/learning` still flags `nexus/learning/sf2_bounded_probe.py` for multiple `nested-loop` and `sort-in-loop` heuristic hits.
- The scanner is heuristic only; this is not measured performance evidence.

What changed:

- Added `tests/learning/test_skill_route_taxonomy.py::test_sf2_probe_verdict_catalog_characterizes_multicapability_fail_closed_shape`.
- The test uses public SF2 builders: `build_sf2_probe_verdict_catalog(...)`, `build_sf2_live_receipt_validation(...)`, `build_sf2_promotion_review(...)`, and `build_sf2_completion_gate(...)`.
- It fixes multi-capability ordering, blocked capability output, validated receipt counts, review blockers, and the fail-closed `runtime_update_allowed=false` / `public_benchmark_allowed=false` contract.
- Added impact-map rows for `nexus/learning/sf2_bounded_probe.py` and `tests/learning/test_skill_route_taxonomy.py`.
- No production code changed.

Verification:

- `uv run pytest tests/learning/test_skill_route_taxonomy.py::test_sf2_probe_verdict_catalog_characterizes_multicapability_fail_closed_shape tests/learning/test_skill_route_taxonomy.py::test_sf2_bounded_probe_static_receipts_keep_runtime_and_benchmark_blocked tests/learning/test_skill_route_taxonomy.py::test_sf2_completion_gate_closes_only_after_receipts_and_dispositions -q`
- Result: `3 passed`.
- `python3 -m py_compile nexus/learning/sf2_bounded_probe.py tests/learning/test_skill_route_taxonomy.py`
- Result: passed.
- `uv run scripts/ops/ci_gate.py --changed-only <refactor-slice paths including sf2_bounded_probe.py and test_skill_route_taxonomy.py>`
- Result: `Changed-Only JIT Tests PASSED`.

Decision:

- Do not extract an SF2 index Module yet. Public fail-closed shape is now pinned, but production extraction still needs ordering drift, receipt drift, repeated duplication, or measured hot-path evidence.
- Do not install a hook. The existing changed-only impact map remains the active guard.
