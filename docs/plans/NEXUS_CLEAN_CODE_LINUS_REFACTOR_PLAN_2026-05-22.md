# Nexus Clean Code / Linus 重構計劃

Date: `2026-05-22`
Last status update: `2026-05-26`
Status: `P0A_P0B_P1A_G8_G2G7_F01_REAL_TELEMETRY_FIDELITY_SNAPSHOT_P2A_SOURCE_SELECTION_EXTERNAL_ADAPTER_INJECTION_SANDBOXED_LOCAL_ADAPTER_EXTERNAL_OFFLINE_CACHE_MANIFEST_P3_NETWORK_PROVIDER_FAILURE_EVIDENCE_ARTIFACTS_SOCKET_BARRIER_DIRECT_WITH_NEXUS_RUNNER_EVIDENCE_BUNDLE_GATE_POSTURE_X1_X3_PAYLOAD_FINALIZER_RUBRIC_BUNDLE_PUBLIC_COST_ACCOUNTING_CONTEXT_PROVIDER_MODEL_LOCK_ROW_SET_MANIFEST_METADATA_PAYLOAD_HEADER_SECTION_COMPUTED_SECTION_CLAIM_POSTURE_SECTION_PAYLOAD_SECTION_CONTEXT_STATIC_GATE_SECTIONS_POSTURE_FINALIZATION_SECTION_PAYLOAD_ASSEMBLY_SECTION_P4_CODE_ACTIONS_SKILLS_SYNC_LIST_REGISTRY_BENCH_SANDBOX_MULTI_AGENT_CREATE_START_STATUS_AUDIT_VERIFY_CLOSE_INTEGRATE_SUBMIT_LEARN_ASK_CONVERGE_SOURCE_LIFECYCLE_PHASE_REPORT_REPORT_INGEST_GATE_RESEARCH_ROUTE_AUTO_FLOW_RUN_BENCHMARK_ACTIONS_P5_POLICY_LOADER_DEEPENED_P9_SQLITE_RETRY_MEMORY_MANAGER_EVIDENCE_SEALING_REPORT_READER_CONTEXTHUB_BUDGET_SOURCES_CONTEXTHUB_TEXT_STORE_RESEARCH_SEMANTIC_RUNTIME_RECEIPTS_RESEARCH_S2T_RUNTIME_TRACE_RESEARCH_AUTO_FLOW_PAYLOAD_SRE_SANDBOX_KERNEL_ELASTIC_DDTREE_VETO_MISSION_CONTROL_CLI_SUBPROCESS_SQLITE_TIMEOUT_GO_SWARM_ENV_RUST_AST_SCANNER`
Source analysis: `/Users/jameschen/.gemini/antigravity/brain/aff9416a-04e7-48d5-9b10-85410ef6b790/NEXUS_CLEAN_CODE_ANALYSIS.md`
Updated from: second-pass `improve-codebase-architecture` review

## 0. 進度總表

Status legend:

- `DONE`: 已實作、文件更新、focused/changed-only/full gate 有證據。
- `PARTIAL`: 已完成安全 leaf 或 seam，但 facade / orchestration 仍存在。
- `DEFERRED`: 刻意不做；需要新的 failing evidence、caller map、deletion test 或 runtime gate 才能開。
- `OPEN-SEPARATE`: 不是本重構 goal 的 blocker，需另開任務。

### 0.1 已完成

| Area | Status | 完成內容 | 主要證據 |
| --- | --- | --- | --- |
| P0A Golden JSON / schema gate | `DONE` | `.gitattributes`、Golden Schema drift hard gate、UTF-8/LF raw-byte 檢查。 | `tests/ops/test_golden_schema_snapshots.py`、full `ci_gate.py` passed。 |
| P0B Telemetry / Nodeid / Glob pregates | `DONE` | Telemetry canonical comparator、focused nodeid hard gate、strict glob / nonempty JSON helper。 | `tests/benchmark/test_telemetry_fidelity.py`、`tests/ops/test_strict_file_discovery.py`、changed-only gates passed。 |
| P1A Research Flow CodeIntel context | `DONE` | `nexus/research/flow/codeintel_context.py` leaf；`research_flow_service.py` 保留 physical aliases。 | focused app tests + changed-only gate passed。 |
| P2A Fixture materialization | `DONE` | `fixture_materialization.py`、fixture split/source selection、external adapter injection、sandboxed local/file Adapter；remote live clone 仍 fail-closed。 | `tests/benchmark/test_fixture_materialization.py`、benchmark focused tests passed。 |
| P2A External fixture offline cache pregate | `DONE` | `ExternalFixtureCacheManifest` 與 `OfflineCachedExternalFixtureAdapter`；remote repo/ref 必須匹配 local cache manifest，`network_allowed=True` 仍 fail-closed。 | `tests/benchmark/test_fixture_materialization.py` passed。 |
| P3 Benchmark runner seams | `DONE` | direct/with-Nexus runner、socket barrier、failure policy、evidence artifacts、gate/posture/accounting/provider/row/manifest/payload seams、final payload assembly。 | benchmark focused suites passed；full `ci_gate.py` passed after each protected slice。 |
| P4 CLI Action modules | `DONE` | code / skills / registry / bench / sandbox / multi-agent / learn / ask / research route / auto-flow / run 等 command bodies moved to Action modules or equivalent seams。 | `tests/engine/*_actions.py`、CLI semantic/artifact audits、changed-only gates passed。 |
| P5 Policy loader deepening | `DONE` | `route_cost_policy_matcher.py`、`expected_capability_policy.py`、`s2t_policy_loader.py` leaf modules。 | route-cost / expected-capability / S2T policy tests passed；full gate passed。 |
| Research Flow RLM trace leaf | `DONE` | `nexus/research/flow/rlm_trace.py` owns RLM trace slugging and X/R/A JSONL event writes；`research_flow_service.py` keeps physical aliases。 | module characterization + facade alias tests passed。 |
| Research runtime receipt skill-mount leaf | `DONE` | `research_receipt_runtime.py` owns runtime skill-mount receipt confirmation and contract building；`research_flow_service.py` keeps physical aliases。 | module characterization + facade alias + skill-mount receipt tests passed。 |
| Research semantic runtime receipt leaf | `DONE` | `research_semantic_runtime.py` owns judge-panel、ASI constraint、architecture scout、external doc scout、formal report runtime receipt augmentation；`research_flow_service.py` keeps physical alias。 | module characterization + facade alias + semantic auto-flow receipt tests passed。 |
| Research S2T runtime trace leaf | `DONE` | `research_s2t_runtime.py` owns autoreason candidate shaping and S2T shadow trace / episode payload serialization；`research_flow_service.py` keeps physical aliases。 | module characterization + facade alias + auto-flow S2T regression tests passed。 |
| Research auto-flow payload leaf | `DONE` | `auto_flow_payload.py` owns public auto-flow report envelope assembly；`run_auto_flow` now delegates payload dict shape instead of constructing it inline。 | module characterization + auto-flow regression tests passed。 |
| Research flow helper leaves | `DONE_10_TASK_SLICE` | `runtime_state.py`、`runtime_decision.py`、`report_io.py`、`task_classifier.py`、`governance_packets.py`、`capability_evidence.py`、`capability_planning.py`、`model_training_export.py` own formerly inline helper responsibilities；facade keeps physical aliases。 | `tests/research/test_flow_leaf_modules.py` + auto-flow regression tests passed。 |
| P9 SQLite retry first writer | `DONE` | `ProjectMemoryManager._execute_with_retry` 改用 existing `SQLiteRetryHandler`；busy/locked-only retry，corrupt/schema fail-fast。 | `tests/core/test_memory_manager_sqlite_retry.py`、`tests/infrastructure/test_sqlite_retry.py` passed。 |
| P9 SQLite retry second writer | `DONE` | `SkillRegistry.upsert` 與 `update_win_rate` 改用 existing `SQLiteRetryHandler`；busy/locked-only retry，non-busy fail-fast。 | `tests/test_skill_sharing.py`、`tests/infrastructure/test_sqlite_retry.py` passed。 |
| P9 Evidence sealing report reader | `DONE` | `gemini_nexus_report.py::_load_evidence_bundle(require_sealed=...)` opt-in sealed reader；legacy unsealed read-only default preserved。 | `tests/benchmark/test_gemini_nexus_report.py`、`tests/contracts/test_evidence_sealing_barrier.py` passed。 |
| ContextHub budget-source leaf | `DONE` | `context_budget_sources.py` owns L0/L1/history/extra source shaping and token estimator。 | `tests/core/test_context_budget_sources.py` + ContextHub deletion test passed。 |
| ContextHub text-store leaf | `DONE` | `context_text_store.py` owns local `program.md` fallback and `last_handoff.json` UTF-8 JSON fallback；ContextHub facade delegates。 | `tests/core/test_context_text_store.py` + ContextHub deletion test passed；full `ci_gate.py` passed。 |
| Sandbox kernel / elastic hardening | `DONE_2026_05_26` | `SandboxRunner` 已從 Python child socket barrier 補強到 macOS `sandbox-exec` kernel-level network barrier、elastic sandbox profile、auto-elastic profile 與 dynamic blast radius derivation；`DDTreeAdapter` 加入 test veto policy。 | commits `09ac806f`、`4fe6f389`、`668b612c`；`tests/engine/test_sandbox_actions.py`、`tests/engine/test_sandbox_elastic_profile.py`、`tests/engine/test_ddtree_veto_policy.py`。 |
| Mission Control v0 | `DONE_2026_05_26` | 新增 persistent campaign state、budget gates、fingerprint/preflight defense 與 `nexus mission create/start/status/pause/resume` CLI group。 | commit `33222ce1`；`nexus/core/mission_contracts.py`、`tests/core/test_mission_control.py`。 |
| CLI subprocess hardening | `DONE_2026_05_26` | CLI / ops subprocess call sites 加入 command-injection 防線、pipe deadlock 防線、git subprocess timeout 與 `.git/index.lock` transient wait。 | commits `8bd6009a`、`a9f04cc0`；`tests/test_cli_deadlock_and_injection.py`、`tests/ops/test_verify_report_claims.py`。 |
| SQLite timeout SRE hardening | `DONE_2026_05_26` | `NodeRegistry` 與 `CreditLedger` SQLite connections 增加 timeout/WAL concurrency posture；此為 SRE timeout hardening，不等同全域 transaction manager。 | commit `4ae879c5`；`tests/federation/test_sqlite_concurrency.py`。 |
| Go swarm env configurability | `DONE_2026_05_26` | Go swarm socket path、TCP port、brain URL 改由環境變數設定，降低 hardcoded runtime coupling。 | commit `761ec85c`；`packages/swarm/cmd/main.go`。 |
| Rust core AST scanner perf | `DONE_2026_05_26` | `nexus-core` AST scanner 改為 single-pass O(N) 並引入 OnceLock hashing cache，屬 core perf/locality hardening。 | commit `13e0de78`；`nexus-core/src/ast_diff.rs`、`nexus-core/src/lib.rs`。 |

### 0.2 未完成 / 暫不開工

| Area | Status | 未完成內容 | 可開工條件 |
| --- | --- | --- | --- |
| Benchmark harness facade | `NO_SPLIT_NOW` | `capability_ab_runner.py` 仍是 benchmark orchestration facade；provider-token、session-worker contamination、telemetry fidelity focused probes 已通過。 | 只有新的 failing evidence 證明某個 side-effect orchestration seam 需要切，才開更小 slice。 |
| External fixture live clone/setup | `DEFERRED` | offline cache manifest Adapter 已完成；尚未實作 remote clone/setup concrete Adapter。 | 需明確 live-network allowlist、socket/no-network barrier、cache provenance receipt；預設仍 fail-closed。 |
| CLI root registration | `DONE_ACTION_WIRING_ROOT_REGISTRATION_REMAINS` | `code`、`bench effort`、`skills/registry`、`sandbox run`、`multi-agent`、`learn/ask`、`research` live Click commands 已委派 Action/renderer；`sandbox run` 已接本地 physical runner contract；`research:run` 舊內聯 body 已物理刪除。`nexus_cli.py` 仍保留 Click group registration 與 compat shims。 | 後續只在 CLI output schema / deprecated alias / root-registration audit 出現新 failing evidence 時開小切片；sandbox 後續只允許在 no-network / allowlist / hook policy 有新 failing evidence 時擴張。 |
| Research flow runtime receipts | `PARTIAL_EXECUTOR_RESCUE_REPORT_SEAM_DONE` | RLM trace、runtime skill-mount contract、semantic runtime receipt augmentation、S2T shadow trace serialization、auto-flow payload envelope、runtime state、runtime decision、report IO、task classifier、governance packets、capability evidence、capability planning、model training export leaves 已完成；guard fallback execution-accounting snapshot 已保護；forced-hyper direct accounting snapshot 已補；verification-only rescue snapshot 已補；`auto_flow_executor.py` 已抽出 guard fallback accounting、hyper sprint report builder、verification-only rescue report seams。 | 下一步只可在新的 execution-branch snapshot 下擴大 executor；不可打開 recursive runtime dispatch；不得把 X/R-loop state 搬進 executor。 |
| ContextHub storage/retry next leaf | `DEFERRED_CALLER_MAP_DONE_NO_SQLITE` | SQLite-backed fallback / retry leaf 未開；2026-05-23 caller map 證明 current ContextHub path 只有 `ContextTextStore` UTF-8 text/JSON reads 與 budget-source shaping，沒有 `sqlite3` / `SQLiteRetryHandler` writer。 | 只有真 storage responsibility 引入 SQLite-backed fallback，且有 deletion test / busy-locked fixture，才開 code slice；不得改 constructor compatibility / strict deps 行為。 |
| SQLite transaction manager | `DEFERRED` | `memory_manager.py` 與 `skill_registry.py` 已共用 `SQLiteRetryHandler`；尚未升級成全域 `DatabaseTransactionManager`。 | 需第三個 writer 或重複 transaction-shape duplication 證明 context manager seam 有價值。 |
| Capability planner / pipeline repair deeper split | `DEFERRED` | 不做 broad split。 | 僅在 policy order / injection equivalence / repair RLM acceptance gate 出現 failing evidence 時重開。 |
| Root hygiene | `PARTIAL_DOCS_INFO_RETAINED` | root-level entrypoint cleanup 未主動搬移；`docs/info/nexus_flow.html` 與 `docs/info/nexus_flow.json` 已作為 tracked docs orientation artifacts 保留。 | 後續一次一個 entrypoint；需 wrapper、reference map、CLI smoke。`docs/info/nexus_flow.*` 可作拓撲參考，但不是 source-code dependency evidence。 |
| Governance eval quality warning | `OPEN-SEPARATE` | full gate 仍可能警告 `Eval pass rate 20.00% below required 80.00%`。 | 另開 wiki-eval quality debt；不是本重構計劃 blocker。 |

### 0.3 目前結論

本計劃的「可在不影響 runtime/public gates 下直接完成」部分已完成到下一層：Research semantic runtime receipt leaf、S2T runtime trace leaf、auto-flow payload envelope leaf，加上 8 個 Research helper leaves 都已切出。剩餘項目不是漏做，而是按 Clean Code / Linus 原則刻意保留在 `PARTIAL_EXECUTOR_ONLY` 或 `DEFERRED`：沒有 execution accounting snapshot 前，不用 file-size-only 理由硬拆 executor。

目前可接續開工證據包已整理於 `docs/reports/NEXUS_REFACTOR_REMAINING_START_EVIDENCE_2026-05-23.md`。`SkillRegistry` SQLite retry 第二 writer、`sandbox_actions.py` CLI Action seam、`SandboxRunner.run_task` 本地 physical contract、external fixture offline cache manifest pregate、CLI live Action adapter sweep、Research S2T runtime trace leaf、Research auto-flow payload leaf、Research 10-task helper leaf slice 已完成。下一個可接續項只剩 evidence-first 類型：benchmark / CLI root registration audit / ContextHub storage / sandbox no-network hardening / auto-flow executor 仍需依該 evidence report 的 first RED 與 stop condition 啟動。

### 0.4 未完成項開工證據包

| Area | 先補哪個證據 | 第一個 RED / characterization test | 不可越界 |
| --- | --- | --- | --- |
| Benchmark orchestration facade | 找到一個 public gate / accounting / provider side-effect drift。 | 鎖定單一 `tests/benchmark/test_capability_ab_runner.py::<nodeid>`；先證明現有行為，再抽一個 seam。 | 不改 public claim gate schema；不開 live provider socket。 |
| External fixture live clone/setup | offline cache manifest / remote denylist 已完成；下一步只剩 live-network allowlist 與 cache provenance receipt。 | 新 RED 必須先證明 socket/no-network barrier 與 allowlist receipt。 | 沒有 live-network allowlist + no-network barrier 前，不允許 remote clone。 |
| CLI root registration facade | live Action adapter sweep 已完成；後續只剩 root group registration、compat alias、output schema audit 類工作。 | `tests/engine/test_cli_*::<nodeid>` 先固定 stdout/stderr/exit code。 | Action Module 不 import Click；`KeyboardInterrupt` / `click.Abort` pass-through；不做 broad CLI rewrite。 |
| Sandbox physical runner | `run_task` 本地 physical contract、Python child socket barrier、macOS `sandbox-exec` kernel-level network barrier、elastic/auto-elastic profile、dynamic blast radius derivation 已完成。 | 下一個 RED 只允許針對 cross-platform Linux sandbox equivalent、explicit live-network allowlist、或 sandbox profile regression 開小切片。 | 不把現有 `run_challenge(repo_url, task)` 偷接成 remote flow；不開 remote clone / fetch / hook；不得把 macOS-only barrier 宣稱成全平台 kernel sandbox。 |
| Research runtime receipt next leaf | `semantic runtime capability augmentation` 已完成；下一個只剩 auto-flow executor 或 S2T serialization caller map。 | snapshot auto-flow / S2T payload；extract only if payload stable。 | 不開 recursive runtime dispatch；不改 public-safe semantics。 |
| ContextHub storage/retry next leaf | caller map 已補：current path 無 SQLite writer；下一步只在真 storage responsibility 出現時補 deletion test。 | monkeypatch `ContextHub` facade to prove new leaf use before moving code；若是 SQLite fallback，先寫 busy/locked fixture。 | 不改 constructor compatibility / strict deps；不為 synthetic SQLite writer 寫假 fixture。 |
| SQLite transaction manager | 已完成 retry seam writers：`ProjectMemoryManager`、`SkillRegistry`；另完成 SRE timeout writers：`NodeRegistry`、`CreditLedger`。 | 下一步只在第三個 retry-shape writer、跨 writer transaction-shape duplication、或 busy/locked fixture 證明 timeout 不足時新增 context manager RED。 | 不把 connection timeout hardening 誤寫成 full transaction manager；不因多個 writer 存在就跳過 deletion test。 |
| Planner / repair deeper split | collect failing policy-order / injection / RLM acceptance evidence. | focused failing acceptance nodeid first. | 不做 broad split from line count. |
| Root hygiene | `docs/info/nexus_flow.*` 已有 tracked retention evidence；若要搬 root entrypoint，仍需 wrapper + reference map + CLI smoke。 | smoke proves old and new entrypoints both work. | 不做 broad move；不把 docs/info topology artifact 誤當 dependency graph evidence。 |

### 0.5 2026-05-23 續作評估 / 實作結果

本輪重新驗證 live checkout 後，發現 `ContextHub` 兩個 split Module 已存在，但 facade 還沒有委派到 split Module；原本 `DONE` 宣稱缺少 live facade deletion tests。已完成最小安全修正：

| Area | Result | Evidence |
| --- | --- | --- |
| ContextHub budget-source facade delegation | `DONE` | `ContextHub._context_budget_sources` 改委派 `build_context_budget_sources(...)`；新增 monkeypatch deletion test。 |
| ContextHub text-store facade delegation | `DONE` | `ContextHub.load_program_rules` 與 `_load_last_handoff` 改委派 `ContextTextStore`；新增 monkeypatch deletion test。 |
| ContextHub token estimator dedupe | `DONE` | `ContextHub._estimate_context_tokens` 改委派 `estimate_context_tokens(...)`。 |
| Impact map coverage | `DONE` | `docs/testing/test_impact_map.md` 新增 ContextHub split source/test rows，避免 changed-only gate fallback。 |

RED:

- `uv run pytest tests/core/test_context_hub_strict_deps.py::test_context_hub_uses_split_context_budget_source_builder tests/core/test_context_hub_strict_deps.py::test_context_hub_uses_split_context_text_store -q`
- Result: `2 failed`，`context_hub` 沒有 `build_context_budget_sources` / `ContextTextStore` monkeypatch targets。

GREEN:

- `uv run pytest tests/core/test_context_hub_strict_deps.py::test_context_hub_uses_split_context_budget_source_builder tests/core/test_context_hub_strict_deps.py::test_context_hub_uses_split_context_text_store tests/core/test_context_budget_sources.py tests/core/test_context_text_store.py -q`
- Result: `6 passed`。

剩餘未完成項仍按 evidence-first gate 管制：

- Benchmark harness facade：provider-token / session-worker contamination / telemetry fidelity nodeids 已通過；沒有 side-effect drift 前不切 seam。
- External fixture live clone/setup：先補 live-network allowlist、no-network barrier、cache provenance receipt；目前不實作 live clone。
- CLI sandbox physical runner：已補 `SandboxRunner.run_task` 本地 physical execution contract 與 sandbox hardening：Python child external socket barrier、artifact sha256 provenance receipt、source hook non-copy receipt。下一步只針對非 Python command 的 OS/kernel 級 network isolation 或 live-network allowlist 的新 failing evidence 開工，仍不讓 CLI 假造 sandbox success。
- Research runtime receipt：只在 auto-flow / S2T payload snapshot 穩定後切 leaf；不開 full recursive dispatch。
- ContextHub SQLite storage/retry：caller map 已補且確認 current ContextHub 沒有 SQLite writer；需新真實 storage responsibility + busy/locked fixture，才允許開 SQLite fallback。

### 0.5.1 2026-05-23 缺口證據補強

| Area | Result | Evidence |
| --- | --- | --- |
| Sandbox physical runner | `DONE_HARDENED_LOCAL_PHYSICAL_CONTRACT` | 新增 `SandboxRunner.run_task(...)` 本地 contract；`tests/engine/test_sandbox_actions.py` 覆蓋 explicit command fail-closed、本地 command 執行、artifact sha256 provenance、cleanup、cwd escape block、source symlink non-following、source git hook non-copy receipt、Python child external socket barrier、CLI option passthrough。 |
| ContextHub storage/retry | `DONE_CALLER_MAP_ONLY` | Bounded caller map 證明 current ContextHub path 只有 `ContextTextStore` UTF-8 text/JSON reads 與 `build_context_budget_sources(...)` shaping，沒有 SQLite writer；因此不開 synthetic busy/locked fixture。 |
| CLI registry/skills Action wiring | `DONE_LIVE_ADAPTER_RESTORED` | `registry_actions.py` 與 tests 已存在，但 live `nexus_cli.py` 仍未 import/delegate；已將 `skills sync/list`、`registry status` 降為 thin Click adapters 並套 `translate_action_exceptions`。 |

Verification:

- RED artifact provenance：`tests/engine/test_sandbox_actions.py::test_default_sandbox_runner_executes_local_command_and_collects_output` 先因 `KeyError: 'output_artifact'` 失敗；GREEN 後 output artifact receipt 包含 sandbox relative path、artifact path、sha256、size bytes。
- RED Python socket barrier：`tests/engine/test_sandbox_actions.py::test_default_sandbox_runner_blocks_python_external_socket` 先證明 `socket.create_connection(('example.com', 80))` 在 child Python 內成功；GREEN 後由 runner-owned `sitecustomize.py` 阻斷 external host 並保留 loopback allowed boundary。
- RED hook policy receipt：`tests/engine/test_sandbox_actions.py::test_default_sandbox_runner_does_not_copy_source_git_hooks` 先因 `KeyError: 'hook_policy'` 失敗；GREEN 後 result 明確記錄 source git metadata / hooks 未複製且 hooks 不允許。
- `uv run pytest tests/engine/test_sandbox_actions.py -q` -> `10 passed`.
- `uv run python -m py_compile nexus/engine/sandbox_runner.py scripts/engine/commands/sandbox_actions.py scripts/engine/nexus_cli.py tests/engine/test_sandbox_actions.py` -> `PASSED`.
- `uv run pytest tests/engine/test_sandbox_actions.py tests/engine/test_cli_artifact_gate_audit.py tests/engine/test_cli_semantic_contract_audit.py tests/test_cli_commands.py -q` -> `49 passed`.
- `uv run pytest tests/engine/test_bench_actions.py tests/engine/test_code_actions.py tests/engine/test_multi_agent_actions.py tests/engine/test_learn_actions.py tests/engine/test_research_actions.py tests/engine/test_registry_actions.py tests/engine/test_sandbox_actions.py -q` -> `101 passed`.
- `uv run scripts/ops/ci_gate.py --changed-only nexus/engine/sandbox_runner.py scripts/engine/commands/sandbox_actions.py scripts/engine/nexus_cli.py tests/engine/test_sandbox_actions.py docs/testing/test_impact_map.md docs/plans/NEXUS_CLEAN_CODE_LINUS_REFACTOR_PLAN_2026-05-22.md docs/reports/NEXUS_REFACTOR_REMAINING_START_EVIDENCE_2026-05-23.md "nexus_wiki_vault/06_Ops/Ops - Learning Closure Matrix.md"` -> `Changed-Only JIT Tests PASSED`.
- `uv run scripts/ops/ci_gate.py` -> `ALL QUALITY GATES PASSED`.
- `uv run pytest tests/engine/test_registry_actions.py -q` -> RED `6 failed` because `nexus_cli.py` exposed no `get_registry_status` / `get_skills_list` / `sync_external_skills`; GREEN `12 passed` after CLI adapter wiring.
- `uv run pytest tests/engine/test_registry_actions.py tests/engine/test_cli_exception_translation.py tests/engine/test_nexus_cli_registry.py -q` -> `20 passed`.
- `uv run scripts/ops/ci_gate.py --changed-only scripts/engine/nexus_cli.py scripts/engine/commands/registry_actions.py tests/engine/test_registry_actions.py docs/testing/test_impact_map.md docs/plans/NEXUS_CLEAN_CODE_LINUS_REFACTOR_PLAN_2026-05-22.md docs/reports/NEXUS_REFACTOR_REMAINING_START_EVIDENCE_2026-05-23.md "nexus_wiki_vault/06_Ops/Ops - Learning Closure Matrix.md"` -> initial fallback failure from missing test self row; after adding `tests/engine/test_registry_actions.py` row, `Changed-Only JIT Tests PASSED`.

### 0.6 2026-05-23 Complexity Scan 建議採納判定

參考 `/Users/jameschen/Workspace/nexus-perplexity/nexus_complexity_report.md` 與本輪 live checkout 量測。該 report 是 heuristic hotspot scan，不等於 profiler-backed performance proof；採納方式必須先轉成 caller map、characterization tests、focused RED，再進 code。

| Agent 建議 | 判定 | 併入計劃方式 |
| --- | --- | --- |
| `skill_fit_followup.py` / `skill_fit_ablation_core.py` 預索引與拆 leaf | `採納` | 新增 `P6A Skill-fit data-shape pregate`：先固定 RCA / taskset / candidate selection output，再抽 `SkillFitRowIndex` / `SkillFitCandidateIndex` 類深 Module；Interface 必須只接受 frozen / mapping inputs，Implementation 才處理 grouping、bucket counts、sorted top rows。 |
| `sf2_bounded_probe.py` 多處 nested-loop / sort-in-loop | `採納為 tests-only pregate` | 新增 `P6D SF2 bounded-probe fail-closed characterization`：先固定 verdict catalog、live receipt validation、promotion review、completion gate 的多 capability / blocker / runtime-public false contract；不因 heuristic scan 直接抽 production。 |
| `scripts/ops/capability_invocation_matrix.py` 消除 rows × capabilities × receipts 重複掃描 | `採納` | 新增 `P6B Capability invocation matrix index`：先以 JSONL fixture 固定 matrix/diagnostics，再建立 arm-level index，把 expected/public_safe/receipt cells 一次投影為 dict/set。 |
| `capability_ab_runner.py` 抽 `benchmark_sequencer.py` / `side_effect_adapter.py`，Facade 壓到 200 行 | `方向採納，立即降級為 gate` | 不用行數目標做 broad split；只允許在 public gate / accounting / provider context / row mutation 出現 focused drift 時，切單一 sequencing 或 side-effect Module。`200 行 facade` 不列為成功條件。 |
| `contracts/s2t_export.py` / `engine/asi_constraints.py` sort 外置化 | `採納為低風險 pregate` | 兩檔很小，先做 characterization：S2T preference pairs ordering、ASI grouped constraint ordering 必須穩定；若 scan 確認 repeated sort 真的在 event loop 熱路徑，再改成 one-pass best rejected candidate / pre-grouped ordered records。 |
| 全域 frozen config / `FixtureConfig` | `已吸收，不重開` | `ExternalFixtureCacheManifest`、fixture request/source/result、runner/action dataclasses 已是 frozen；後續只補缺口，不做 blanket rewrite。 |
| CLI Click / Action seam / exception translation | `已完成主要 seam，不重開 broad CLI rewrite` | `translate_action_exceptions` 已存在且保留 `KeyboardInterrupt` / `click.Abort` / `SystemExit` 穿透；新 CLI work 只能選單一 command group 與 output schema RED。 |
| `learning_policy_loader.py` matcher / S2T / expected-capability 解耦 | `已完成，不重複列為新債` | `route_cost_policy_matcher.py`、`expected_capability_policy.py`、`s2t_policy_loader.py` 已存在；剩餘債務只在新 failing evidence 出現時開。 |
| no-network socket barrier | `採納，但維持 runner-scoped` | `runner_socket_barrier.py` 已阻斷 external host 並允許 loopback；暫不把 pytest 全域 socket disable 設為預設，以免 coverage/debugger/local services 假陽性。Provider/helper tests 若涉及 runner 必須 opt-in barrier。 |
| `research_flow_service.py` / CodeIntel I/O in loop | `採納為 caller-map pregate` | 先查 `_load_codeintel_graph`、target file restore、companion edit read paths 的 caller map 與 payload snapshot；只切 read-through cache / leaf Module，不改 runtime receipt semantics。 |
| local analysis tools / hook | `採納工具，不採納立即 hook` | `docs/info/nexus_flow.json/html` 可作拓撲參考；`codex-complexity-optimizer` 只作 heuristic lead；`codegraph-audit` 可用 `/private/tmp` disposable snapshot index；`graphify hook` 會寫 git hook，artifact ownership 未定前不安裝 hook。 |

Tool rerun note:

- The old memory path `/Users/jameschen/.codex/skills/complexity-optimizer/scripts/analyze_complexity.py` is stale.
- Current scanner path: `/Users/jameschen/Workspace/test/codex-complexity-optimizer/complexity-optimizer/scripts/analyze_complexity.py`.
- 2026-05-23 scoped reruns against `nexus/learning`, `nexus/core`, and `scripts/ops` kept the same policy: use findings as leads, then require public characterization tests before production extraction.

### 0.7 2026-05-26 Agent 實作後狀態校準

本段補記 2026-05-23 之後其他 agent 已落地的 SRE / runtime hardening / mission-control 工作。這些不是新的 broad refactor 授權，而是把已進入 `main` 的 commits 對齊到本 Clean Code / Linus 計劃的完成狀態，避免後續重複開工。

| Area | Result | Evidence |
| --- | --- | --- |
| Sandbox no-network hardening | `DONE_MACOS_KERNEL_AND_ELASTIC_PROFILE` | `09ac806f` 將 non-Python subprocess 納入 macOS `sandbox-exec` kernel-level network barrier；`4fe6f389` 加入 elastic sandbox profile；`668b612c` 加入 auto-elastic profile 與 dynamic blast radius derivation。 |
| DDTree test veto policy | `DONE` | `4fe6f389` 修改 `nexus/engine/ddtree_adapter.py` 並新增 `tests/engine/test_ddtree_veto_policy.py`，讓 DDTree execution candidate 受測試 veto policy 約束。 |
| Mission Control v0 | `DONE` | `33222ce1` 新增 `nexus/core/mission_contracts.py`、`tests/core/test_mission_control.py`，並在 `scripts/engine/nexus_cli.py` 加入 `nexus mission` command group。 |
| CLI / ops subprocess hardening | `DONE` | `8bd6009a` 以 TDD 補 CLI command injection / pipe deadlock 防線；`a9f04cc0` 對 `verify_report_claims.py` git subprocess 加 timeout 與 `.git/index.lock` transient wait。 |
| SQLite SRE timeout hardening | `DONE_TIMEOUT_ONLY` | `4ae879c5` 對 `nexus/federation/node_registry.py` 與 `nexus/market/credit_ledger.py` 補 SQLite connection timeout / WAL posture，並新增 `tests/federation/test_sqlite_concurrency.py`。這不是 `DatabaseTransactionManager` 完成證據。 |
| Go swarm config decoupling | `DONE` | `761ec85c` 讓 `packages/swarm/cmd/main.go` 的 socket path、port、brain URL 可由環境變數配置。 |
| Rust AST scanner perf/locality | `DONE` | `13e0de78` 將 `nexus-core` AST scanner 改為 single-pass O(N)，並加入 OnceLock hashing cache。 |

Updated interpretation:

- `Sandbox physical runner` 不再只是 local Python-child barrier；macOS non-Python command 已有 kernel-level barrier 與 profile elasticity。後續若要更硬，只能開 cross-platform Linux equivalent、explicit allowlist 或 profile regression 小 slice。
- `Mission Control v0` 已完成，不應再以「mission layer 尚未落地」開新任務；後續只在 budget/preflight/state transition 出現 failing evidence 時補小切片。
- `SQLite transaction manager` 仍維持 `DEFERRED`：已有 retry writers 與 timeout writers，但 timeout/WAL 不是 transaction context manager，也不是 busy/locked retry semantic 的替代。
- `Go swarm env configurability` touched `packages/`，屬既有 agent commit；本計劃只記錄，不把 `packages/` 納入後續 Codex 預設可改範圍。
- `nexus-core` Rust perf work 是完成的 performance/locality hardening；後續若要宣稱效能提升，仍需 profiler/benchmark evidence，不只靠 complexity reasoning。

#### P6A. Skill-fit Data-Shape Pregate

Status: `DONE_INITIAL_PREGATE_ROW_INDEX_CATALOG_INDEX_EXECUTION_MATRIX_CANDIDATE_SELECTION_CHARACTERIZATION_AND_CANDIDATE_INDEX_2026-05-23`

Files:

- `nexus/learning/skill_fit_followup.py`
- `nexus/learning/skill_fit_ablation_core.py`
- `nexus/learning/skill_fit_status.py`
- `tests/learning/test_skill_fit_data_shape_pregate.py`
- `tests/learning/` 或現有 skill-fit focused tests

Problem:

- Complexity scan 指出 `skill_fit_followup.py` 21 個 heuristic findings，`skill_fit_ablation_core.py` 9 個 findings。
- Live inspection 顯示重複 pattern：row grouping、catalog lookup、candidate capability membership、bucket counting、top-wall row sorting 分散在多個 function。

Deep Module candidate:

- Module: `SkillFitRowIndex`
- Interface: `from_run_summary(run_summary, catalog, capability) -> SkillFitRowIndex`
- Implementation: baseline rows、rows_by_skill、catalog_by_skill、bucket counts、effective rows、phase costs 等預索引。
- Deletion test: 刪除此 Module 後，row grouping / lookup / sorting 會回流到至少 RCA、cost phase contract、candidate followup 三個 caller。
- Module: `SkillFitCatalogIndex`
- Interface: `from_run_summary(run_summary) -> SkillFitCatalogIndex`
- Implementation: catalog rows、capability-only rows、negative-control rows、`(capability, skill_id)` row groups、planned/completed row counts。
- Deletion test: 刪除此 Module 後，catalog grouping / negative-control separation / matrix count shaping 會回流到 `build_skill_fit_catalog(...)`。

First RED / characterization:

- 固定 `build_skill_fit_row_level_rca(...)` output。
- 固定 `build_skill_fit_cost_phase_contract(...)` top-wall ordering 與 cost shares。
- 固定 governance taskset selection / missing specs output。

Completed initial pregate:

- Added pure in-memory Interface `build_skill_fit_data_shape_pregate(...)`.
- The pregate validates catalog / promotion policy / threshold contract pair consistency before any row-index refactor.
- It always returns `runtime_update_allowed=false` and `public_benchmark_allowed=false`.
- Added deletion tests for missing receipts, missing threshold pair, and accidental runtime/public unlock.
- Added changed-only impact-map rows for `skill_fit_status.py` and the new pregate test file.

Completed row-index slice:

- Added frozen `SkillFitRowIndex` in `nexus/learning/skill_fit_followup.py`.
- Reused that index in `build_skill_fit_row_level_rca(...)` and `build_skill_fit_cost_phase_contract(...)` for capability filtering, baseline lookup, skill grouping, catalog lookup, and stable skill ordering.
- Added `test_skill_fit_row_index_groups_baselines_catalog_and_skill_rows_for_rca_and_cost` as the deletion/characterization test.
- Added changed-only impact-map rows for `nexus/learning/skill_fit_followup.py` and the edited `tests/learning/test_skill_fit_ablation.py` test file.

Completed catalog-index slice:

- Added frozen `SkillFitCatalogIndex` in `nexus/learning/skill_fit_ablation_core.py`.
- Reused that index in `build_skill_fit_catalog(...)` for capability-only row accounting, negative-control rows, planned/completed counts, and `(capability, skill_id)` grouping.
- Added `test_skill_fit_catalog_index_groups_rows_by_capability_and_skill_id` as the deletion/characterization test.
- Added changed-only impact-map rows for `nexus/learning/skill_fit_ablation_core.py` and the edited `tests/learning/test_skill_fit_ablation.py` test file.

Completed execution-matrix characterization slice:

- Added public-interface characterization `test_execution_matrix_characterizes_public_row_shape_for_all_arm_types`.
- The test fixes row id shape, task ref, model propagation, gate requirements, runner args, runner env, mount requests, and expected outcomes for `capability_only`, `skill_ablation`, and `wrong_or_quarantined_skill`.
- No production code was changed; this is a deletion test for a future `SkillFitExecutionMatrixIndex` / row-contract deep Module, not an extraction.
- Hook decision remains `NO_HOOK`: the current impact-map plus focused nodeids covers this slice without adding index daemons or git ownership.

Completed candidate-selection characterization slice:

- Added public-interface characterization `test_skill_fit_plan_characterizes_public_candidate_selection_contract`.
- The test fixes the current candidate selection contract through `build_skill_fit_ablation_plan(...)`: one highest-relevance runtime baseline first, then preferred/external distinct candidates, with blocked skills, generic skills, and canonical `gstack-` aliases excluded.
- This was then promoted into a production extraction because the same canonical id and negative-control candidate logic was used by plan construction and follow-up candidate reports.

Completed candidate-index slice:

- Added frozen `SkillFitCandidateIndex` in `nexus/learning/skill_fit_candidate_index.py`.
- Routed `skill_fit_ablation_core.py` candidate matching, explicit selection, selected-arm ordering, canonical id normalization, and negative-control selection through that Module.
- Routed `skill_fit_followup.py` canonical id normalization and negative-control selection through the same Module.
- Added `test_skill_fit_candidate_index_preserves_plan_selection_contract` as the deletion/characterization test.
- Added changed-only impact-map rows for `skill_fit_candidate_index.py` and the edited `tests/learning/test_skill_fit_ablation.py` self row.

Evidence:

- RED: `ImportError: cannot import name 'build_skill_fit_data_shape_pregate' from 'nexus.learning.skill_fit_status'`.
- GREEN: `uv run pytest tests/learning/test_skill_fit_data_shape_pregate.py -q` -> `4 passed`.
- ROW-INDEX RED: `ImportError: cannot import name 'SkillFitRowIndex' from 'nexus.learning.skill_fit_followup'`.
- ROW-INDEX GUARD: `uv run pytest tests/learning/test_skill_fit_data_shape_pregate.py tests/learning/test_skill_fit_ablation.py::test_skill_fit_row_index_groups_baselines_catalog_and_skill_rows_for_rca_and_cost tests/learning/test_skill_fit_ablation.py::test_skill_fit_row_level_rca_recommends_targeted_replay_for_promising_governance_skill tests/learning/test_skill_fit_ablation.py::test_skill_fit_cost_phase_contract_separates_cost_from_delivery_claims -q` -> `7 passed`.
- CATALOG-INDEX RED: `ImportError: cannot import name 'SkillFitCatalogIndex' from 'nexus.learning.skill_fit_ablation_core'`.
- CATALOG-INDEX GUARD: `uv run pytest tests/learning/test_skill_fit_ablation.py::test_skill_fit_catalog_requires_receipt_backed_effective_rows tests/learning/test_skill_fit_ablation.py::test_skill_fit_catalog_groups_verdicts_by_capability_and_skill_id tests/learning/test_skill_fit_ablation.py::test_skill_fit_catalog_index_groups_rows_by_capability_and_skill_id tests/learning/test_skill_fit_ablation.py::test_skill_fit_catalog_returns_when_matrix_incomplete tests/learning/test_skill_fit_data_shape_pregate.py tests/learning/test_skill_fit_ablation.py::test_skill_fit_row_index_groups_baselines_catalog_and_skill_rows_for_rca_and_cost tests/learning/test_skill_fit_ablation.py::test_skill_fit_row_level_rca_recommends_targeted_replay_for_promising_governance_skill tests/learning/test_skill_fit_ablation.py::test_skill_fit_cost_phase_contract_separates_cost_from_delivery_claims -q` -> `11 passed`.
- EXECUTION-MATRIX CHARACTERIZATION: `uv run pytest tests/learning/test_skill_fit_ablation.py::test_execution_matrix_characterizes_public_row_shape_for_all_arm_types tests/learning/test_skill_fit_ablation.py::test_execution_matrix_expands_tasks_by_arms_without_claiming_value tests/learning/test_skill_fit_ablation.py::test_skill_fit_catalog_index_groups_rows_by_capability_and_skill_id -q` -> `3 passed`.
- CANDIDATE-SELECTION CHARACTERIZATION RED: initial `test_skill_fit_plan_characterizes_public_candidate_selection_contract` expected fixed `nexus-tdd` first; live public contract selected higher-relevance `runtime-repair` as the single runtime baseline.
- CANDIDATE-SELECTION CHARACTERIZATION GREEN: `uv run pytest tests/learning/test_skill_fit_ablation.py::test_skill_fit_plan_characterizes_public_candidate_selection_contract -q` -> `1 passed`.
- CANDIDATE-SELECTION GUARD: `uv run pytest tests/learning/test_skill_fit_ablation.py::test_skill_fit_plan_characterizes_public_candidate_selection_contract tests/learning/test_skill_fit_ablation.py::test_plan_prefers_named_repair_candidates_over_generic_candidates tests/learning/test_skill_fit_ablation.py::test_plan_dedupes_gstack_prefixed_skill_aliases tests/learning/test_skill_fit_ablation.py::test_execution_matrix_characterizes_public_row_shape_for_all_arm_types -q` -> `4 passed`.
- CANDIDATE-INDEX RED: `uv run pytest tests/learning/test_skill_fit_ablation.py::test_skill_fit_candidate_index_preserves_plan_selection_contract -q` -> `ModuleNotFoundError: No module named 'nexus.learning.skill_fit_candidate_index'`.
- CANDIDATE-INDEX GREEN: `uv run pytest tests/learning/test_skill_fit_ablation.py::test_skill_fit_candidate_index_preserves_plan_selection_contract tests/learning/test_skill_fit_ablation.py::test_skill_fit_plan_characterizes_public_candidate_selection_contract tests/learning/test_skill_fit_ablation.py::test_plan_dedupes_gstack_prefixed_skill_aliases tests/learning/test_skill_fit_ablation.py::test_research_candidate_v2_report_excludes_rejected_and_selects_source_discipline_candidates tests/learning/test_skill_fit_ablation.py::test_research_candidate_v3_requires_observable_source_discipline_behaviors -q` -> `5 passed`.
- CHANGED-ONLY: `uv run scripts/ops/ci_gate.py --changed-only <refactor-slice paths>` -> `Changed-Only JIT Tests PASSED`.
- CHANGED-ONLY LESSON: first changed-only attempt fell back through the edited test file and hit missing local Playwright browser; fixed by adding the test-file self impact row.

Stop conditions:

- 不改 promotion / runtime apply / public benchmark gate。
- 不把 heuristic finding 當作 performance claim；需要 fixture input-size 或 benchmark evidence 才宣稱速度改善。
- 不把 `SkillFitRowIndex` 或 `SkillFitCatalogIndex` 擴成 policy engine；它們只做 row lookup/indexing。
- `skill_fit_ablation_core.py` candidate selection 與 execution matrix 目前都已有 public characterization；尚未證明 production extraction 必要。

#### P6B. Capability Invocation Matrix Index

Status: `DONE_COMPLETION_SLICE_2026-05-23`

Files:

- `scripts/ops/capability_invocation_matrix.py`
- `scripts/ops/capability_invocation_index.py`
- tests under `tests/ops/`

Problem:

- Complexity scan 指出 `capability_invocation_matrix.py` 13 個 findings。
- Live inspection 顯示 `_arm_from_jsonl(...)` 對 rows、expected capabilities、public-safe capabilities、capability receipts 多次掃描，同一 row 的 coverage/receipt normalization 可先投影。

Deep Module candidate:

- Module: `CapabilityInvocationArmIndex`
- Interface: `build_arm_index(rows) -> CapabilityInvocationArmIndex`
- Implementation: expected set、public_safe set、capability cells、failures、diagnostics、receipt parsing。
- Leverage: matrix builder 與 diagnostics caller 可共用一次解析結果。
- Locality: receipt parsing / capability normalization / missing evidence rules 集中。

First RED / characterization:

- 用固定 JSONL rows 斷言 current matrix payload、failure diagnostics、integrity heatmap 不漂移。
- 加 malformed receipt string fixture，確保 fail-closed degrade 不變。

Completed initial slice:

- Added deep module `CapabilityInvocationArmIndex` with `build_arm_index(rows)`.
- Kept `capability_invocation_matrix.py` as the arm orchestration / report facade.
- Added changed-only hook rows for matrix/index source paths and the matrix test file.
- Added changed-only selector contract to prevent fallback to broad `tests/ops`.
- Added malformed receipt string characterization so bad `capability_receipts` JSON degrades fail-closed through the index instead of crashing or silently passing.

Evidence:

- RED: `ModuleNotFoundError: No module named 'scripts.ops.capability_invocation_index'`.
- Completion characterization: malformed `capability_receipts` JSON now fails closed through `CapabilityInvocationArmIndex` as `expected_capability_not_invoked_with_evidence`.
- Compile: `uv run python -m py_compile scripts/ops/capability_invocation_index.py scripts/ops/capability_invocation_matrix.py tests/ops/test_capability_invocation_matrix.py` -> `PASSED`.
- GREEN: `uv run pytest tests/ops/test_capability_invocation_matrix.py tests/ops/test_ci_gate_report_trust_audit.py::test_run_changed_only_check_selects_capability_invocation_matrix_targets -q` -> `8 passed`.
- Changed-only: `uv run scripts/ops/ci_gate.py --changed-only ...` -> `Changed-Only JIT Tests PASSED`.
- Full gate: `uv run scripts/ops/ci_gate.py` -> `ALL QUALITY GATES PASSED`.

Stop conditions:

- 不改 report schema。
- 不把 row order 改成 unstable dict order；輸出排序仍 canonical。

#### P6C. Small Ordered-Data Pregates

Status: `DONE_TESTS_ONLY_PREGATE_2026-05-23`

Files:

- `nexus/contracts/s2t_export.py`
- `nexus/engine/asi_constraints.py`

Decision:

- 兩檔目前行數小，掃描命中可能是可讀性與資料結構契約問題，不是立即大拆目標。
- 下一步只補 tests：S2T rejected candidate selection、ASI family ordering / confidence / evidence refs。
- 若 RED 證明 sort-in-loop 造成 drift 或 hot path cost，再改為 constructor/pre-index sorted contract 或 one-pass best candidate。

Completed tests-only pregate:

- Added S2T characterization for stable event order and highest-scored failed rejected candidate selection.
- Added ASI characterization for sorted families, confidence formula, evidence-ref order, and `trajectory_step_count=0` as unknown/non-filtered while low positive steps remain filtered.
- Added changed-only impact-map rows for the source/test paths.
- No production code changed because characterization passed and no drift was found.

Evidence:

- `uv run pytest tests/contracts/test_s2t_contracts.py::test_s2t_export_selects_highest_scored_failed_rejected_candidate_stably tests/engine/test_asi_constraints.py::test_asi_constraint_extractor_orders_families_and_preserves_evidence_refs -q` -> `2 passed`.

#### P6D. SF2 Bounded-Probe Fail-Closed Pregate

Status: `DONE_TESTS_ONLY_PREGATE_2026-05-23`

Files:

- `nexus/learning/sf2_bounded_probe.py`
- `tests/learning/test_skill_route_taxonomy.py`

Decision:

- Complexity scan still flags SF2 bounded-probe nested-loop / sort-in-loop hotspots.
- The correct next move is public-interface characterization, not production extraction.
- Runtime default and public benchmark gates must remain false.

Completed tests-only pregate:

- Added `test_sf2_probe_verdict_catalog_characterizes_multicapability_fail_closed_shape`.
- The test fixes multi-capability verdict ordering, blocked capability output, receipt validation blockers, promotion-review blockers, and completion gate fail-closed output.
- Added changed-only impact-map rows for source and test paths.
- No production code changed because characterization passed and no drift was found.

Evidence:

- `uv run pytest tests/learning/test_skill_route_taxonomy.py::test_sf2_probe_verdict_catalog_characterizes_multicapability_fail_closed_shape tests/learning/test_skill_route_taxonomy.py::test_sf2_bounded_probe_static_receipts_keep_runtime_and_benchmark_blocked tests/learning/test_skill_route_taxonomy.py::test_sf2_completion_gate_closes_only_after_receipts_and_dispositions -q` -> `3 passed`.
- `python3 -m py_compile nexus/learning/sf2_bounded_probe.py tests/learning/test_skill_route_taxonomy.py` -> passed.
- `uv run scripts/ops/ci_gate.py --changed-only <refactor-slice paths including sf2_bounded_probe.py and test_skill_route_taxonomy.py>` -> `Changed-Only JIT Tests PASSED`.

## 1. 目標

重新評估 Nexus 目前仍存在的大型技術債，並把舊 agent 的 Clean Code 分析、目前已完成的 Clean Code/CBO/Antigravity/Zero Trust V2 切片、以及新的架構深化建議整合成一份可接續執行的中文計劃。

本計劃不代表先前重構失敗，而是明確區分：

- 已完成的 Clean Code 工作；
- 因相容性仍保留的大型 facade；
- 需要 caller map、deletion test、focused tests 才能動的深模組深化機會；
- 不應在本輪打開的 runtime default、public benchmark、Zero Trust V2 claim gate。

核心準則：

- 切小：每一片只處理一個責任，單次最多 10 個 touched files。
- 模組化：先定義清楚 Module / Interface / Implementation，再搬程式。
- 模組解耦：讓 caller 依賴小 Interface，不依賴大型 Implementation 細節。
- 關注點分離：Click parsing、benchmark fixture、policy matching、SQLite retry、runtime receipts 各自成為深模組。
- 物理相容 Facade：原服務檔必須保留實體別名與 shim，不用動態 `conftest` 重定向掩蓋 import path 變更。
- Golden Master 不可變：歷史 JSON schema 快照必須唯讀、納入 Git 追蹤、由 CI hard gate 阻斷漂移。
- SQLite Retry fail-fast：只 retry busy/locked；corrupt/schema/permission 等嚴重錯誤立即拋出。
- Evidence legacy read-mode：歷史 unsealed telemetry 可作 read-only legacy input，不可給 public claim 或 promotion credit。
- Runner offline tests：拆出的 provider/Nexus runner 單元測試必須預設禁用 socket，禁止意外 live network。
- Stateless executor：`auto_flow_executor.py` 不持有 X/R-loop 狀態；`RlmController` 是狀態唯一真值源。
- RLM atomic state transition：若 `RlmController` 暴露 mutable transition/update receipt 方法，必須有 Thread/Async lock。
- Telemetry Fidelity Snapshot：用固定 mock execution dataset 比對重構前後 telemetry 實體數值，排除 UUID/Timestamp 後 precision 必須一致。
- Golden JSON platform stability：Golden Master 與 telemetry JSON 一律 UTF-8、LF canonicalization、`.gitattributes` 鎖定 EOL。
- Glob / Nodeid Hard Gate：manifest/config glob 空集合必須 fail-fast；focused nodeid 缺失或 skipped 必須讓 CI hard fail。
- Frozen FixtureConfig：benchmark fixture config 必須 immutable、PROJECT_ROOT-relative、canonicalized。
- CLI Exception Translation：Action 層 domain exception 只在 CLI seam 轉換為 exit code/stderr。
- CLI interrupt semantics：`KeyboardInterrupt` / `click.Abort` 必須 bypass exception translation，保留 exit code 130 語義。
- Linus 原則：不要為抽象而抽象；以刪除測試、可回滾、行為不變證據決定是否值得切。

## 2. 當前本地基線

在目前 `main` checkout 量測：

| 檔案 | 行數 | 現況判讀 |
| --- | ---: | --- |
| `scripts/bench/capability_ab_runner.py` | 10192 | 最大剩餘 benchmark harness facade；fixture materialization/source selection、direct provider failure policy、runner seams、evidence artifact writer、evidence bundle gate builder、posture/x1/x3 gate helpers、payload finalizer/writer、rubric bundle、public cost accounting context、provider model-lock context、row-set context、manifest metadata context、payload header section、computed report/contract section、claim/posture section、telemetry completeness section、Nexus wearing context、wall-ledger bundle section、warning-clean section、posture-finalization section 與 top-level payload assembly 已抽出；runner 仍負責 sequencing、side-effect adapters、public gate context inputs 與 final bundle orchestration。 |
| `scripts/engine/nexus_cli.py` | 3337 | Click command registration、少量 legacy command body 與 compat shims 仍集中；learn/research route/session/auto-flow/run/multi-agent/benchmark 多數行為已轉入 Action modules。 |
| `nexus/app/research_flow_service.py` | 3276 | 已比舊 Clean Code 基線小，但仍混合 route、CodeIntel context、runtime receipts、`run_auto_flow` 分支。 |
| `nexus/engine/capability_planner.py` | 1332 | planner facade 仍大，但已有 planner seams；不應無證據大拆。 |
| `nexus/engine/learning_policy_loader.py` | 742 | `LearningPolicyStore` 已存在；剩餘債務是 policy matching、env controls、expected-capability protection 耦合。 |
| `nexus/engine/pipeline_repair.py` | 727 | repair facade 仍大，但 audit/evaluation/escalation/composed-result seams 已存在；只在 failing acceptance evidence 出現時再切。 |
| `nexus/core/context_hub.py` | 569 | `context_view.py`、`context_budget_sources.py`、`context_text_store.py` 已存在且 facade deletion tests 已補；下一步只允許 storage/retry caller-map leaf。 |
| `nexus/learning/skill_fit_followup.py` | 1675 | complexity scan 最高密度 source file；下一步以 data-shape pregate 先固定 row/candidate/taskset output，再決定是否抽 `SkillFitRowIndex`。 |
| `nexus/learning/skill_fit_ablation_core.py` | 1650 | skill-fit ablation / catalog settlement 邏輯仍大；只在 RCA / cost / catalog characterization tests 穩定後抽 index Module。 |
| `scripts/ops/capability_invocation_matrix.py` | 458 | ops scan 最高密度檔之一；適合以 arm-level index 消除 rows × capability × receipt 重複掃描。 |

已存在的抽取模組：

- `nexus/research/flow/route_decider.py`
- `nexus/research/flow/signal_collector.py`
- `nexus/research/flow/evidence_packer.py`
- `nexus/research/flow/phase_clock.py`
- `nexus/research/flow/baseline_report.py`
- `nexus/research/flow/history_signal_store.py`
- `nexus/research/flow/auto_flow_payload.py`
- `nexus/research/flow/orchestrator.py`
- `nexus/engine/repair/audit_evaluator.py`
- `nexus/engine/repair/escalation_manager.py`
- `nexus/engine/repair/composed_phase_result.py`
- `nexus/engine/planner/ab_evaluator.py`
- `nexus/engine/planner/policy_applier.py`
- `nexus/engine/planner/skill_mount_evidence.py`
- `nexus/core/context_view.py`
- `scripts/bench/public_gate_bundle.py`
- `scripts/bench/direct_provider_runner.py`
- `scripts/bench/with_nexus_runner.py`
- `scripts/bench/evidence_bundle_gates.py`
- `scripts/engine/commands/code_actions.py`
- `scripts/bench/public_gate_metrics.py`
- `scripts/bench/receipt_contracts.py`
- `scripts/bench/route_execution_policy.py`
- `scripts/engine/commands/research_support.py`

## 3. 目標式 lesson retrieval

| 來源 | 適用性 | 對本計劃的影響 |
| --- | --- | --- |
| `NEXUS_CLEAN_CODE_ANALYSIS.md` | 指出 `research_flow_service.py`、`ContextHub`、`capability_planner.py`、`pipeline_repair.py`、`learning_policy_loader.py`、root hygiene。 | 方向可用，但需用目前行數與已完成 seams 重新排序。 |
| `docs/plans/NEXUS_CLEAN_CODE_REFACTOR_TASK_PLAN_2026-05-20.md` | 先前 Clean Code plan 已 `COMPLETED`，root cleanup 以 zero moves 結案。 | 不重開大搬移；除非有新的 deletion test。 |
| `docs/plans/NEXUS_ANTIGRAVITY_CLOSURE_AND_DECOUPLED_SWARM_PLAN_2026-05-22.md` | 要求 caller map、deletion tests、rollback path；SQLite retry 已有 adapter，但尚未整合到多個 writer。 | 每個新 task card 必須 narrow、可回滾、gate-backed。 |
| `docs/reports/NEXUS_ANTIGRAVITY_P9_NARROW_INTEGRATION_CALL_SITES_2026-05-22.json` | 六個 adapter/call-site 類別仍是 plan-only 或 narrow-gated。 | P9 只做 successor slices，不做 runtime-wide integration。 |
| `nexus_wiki_vault/06_Ops/Ops - Learning Closure Matrix.md` | benchmark helper 抽取、CLI helper 抽取曾出現 test impact 與 public row contract 風險。 | protected-code slice 必須先做 nodeid-level focused validation，再跑 CI gate。 |
| `docs/testing/test_impact_map.md` | `capability_ab_runner.py`、`nexus_cli.py` 都是 high impact。 | 測試選擇不得只靠粗粒度目錄；需列出精準 nodeids 或 group-specific tests。 |
| `docs/arch/NEXUS_RUNTIME_RECEIPT_LESSONS_2026-05-05.md` | schema 擴展必須與 schema-shape tests 同步。 | Golden Master schema drift 要變成 hard gate，不用測試自動覆寫快照。 |
| `docs/plans/NEXUS_ANTIGRAVITY_CLOSURE_AND_DECOUPLED_SWARM_PLAN_2026-05-22.md` | `SQLiteRetryHandler` 已覆蓋 busy-then-success、retry exhaustion、non-busy fail-fast。 | 不新增大 `DatabaseTransactionManager`；先把既有 retry seam 窄整合到一個真 SQLite writer。 |
| `docs/plans/NEXUS_ANTIGRAVITY_CLOSURE_AND_DECOUPLED_SWARM_PLAN_2026-05-22.md` | `EvidenceSealingBarrier` 已是 contract barrier，但 concrete report reader integration 仍需 narrow call site。 | `gemini_nexus_report.py::_load_evidence_bundle` 整合時要分清 read-only legacy 與 claim-credit eligibility。 |
| `docs/plans/NEXUS_OPTIMIZATION_PLAN_CONTEXT_LEARNING_HARNESS_2026-05-19.md` | 既有 network fetch guard/SSRF guard 要求 private-network target rejection。 | runner 單元測試必須裝 socket barrier，避免拆分後 helper test 觸發 live provider/network。 |
| `nexus/engine/rlm_controller.py` | `RlmController` 與 receipt helpers 已持有 X/R budget、loop decision、handoff receipt。 | `auto_flow_executor.py` 必須無狀態，不複製 X/R counters 或 transition ownership。 |
| `nexus_wiki_vault/06_Ops/Ops - Learning Closure Matrix.md` | high-risk benchmark files 需要 nodeid-specific impact map；粗粒度 benchmark suite 容易被 unrelated failure 污染。 | F02 必須把 focused nodeid existence / skipped status 變成 hard gate。 |
| `nexus_wiki_vault/06_Ops/Ops - Learning Closure Matrix.md` | frozen manifest 缺 top-level fields 會在 preflight 停止；glob/manifest 不可靜默空集合。 | Path glob 找不到 manifest/config 時要丟 `FileNotFoundError`，不得 fallback 成空 taskset。 |
| `nexus_wiki_vault/06_Ops/Ops - Learning Closure Matrix.md` | sandbox/root path 與 optional glob 曾造成 retrieval 或 runner drift。 | FixtureConfig 要 canonicalize 到 `PROJECT_ROOT` 相對路徑，跨 macOS / Linux CI 保持穩定。 |
| `nexus_wiki_vault/06_Ops/Ops - Learning Closure Matrix.md` | hard-gate blocker tests 必須遵守 stable sort order；benchmark row contract 欄位是 public gate input。 | F01 canonical comparison 必須排序無序列表，避免 dict/list traversal order 造成假陽性。 |
| root `.gitattributes` | File is currently absent in this checkout. | G2/G7 implementation must add `.gitattributes` before claiming Golden JSON LF stability. |

## 4. 架構語言與判準

本計劃採用 `improve-codebase-architecture` 的詞彙：

- Module：有 Interface 與 Implementation 的單位，可以是函式、class、檔案、package 或一個執行切片。
- Interface：caller 必須知道的型別、錯誤模式、順序、config、invariants。
- Implementation：Interface 背後的具體程式。
- Seam：Interface 所在的位置；行為可在此替換，不必原地改大型檔。
- Adapter：滿足某個 Interface 的具體實作。
- Depth：小 Interface 後面藏住大量行為，才是 deep module。
- Locality：改動、bug、知識集中，不外溢到多個 caller。
- Leverage：caller 透過小 Interface 得到大量能力。

硬性判準：

1. 不做 file-size-only refactor。
2. 每個 Module 必須通過 deletion test：刪掉後，如果複雜度會回湧到多個 caller，才值得保留。
3. 先保留 compatibility facade，等 caller map 與 focused tests 證明安全後再刪 facade。
4. 先切資料契約與純決策，再切執行分支。
5. 用 guard clauses 壓低巢狀條件，不用新抽象掩蓋混亂控制流。
6. 單 slice 最多 10 個 touched files。
7. 不碰 runtime default、public benchmark claim、Zero Trust V2 report，除非另有 gate authorization。
8. 不做 broad root cleanup；root move 必須先有 wrapper、reference map、CLI smoke。

## 5. 架構安全共識

### G1. 物理相容 Facade 阻斷點

Decision: `MANDATORY_SHIM`

Problem:

- 歷史測試常使用 `from nexus.app.research_flow_service import _helper` 或 monkeypatch 原 module global。
- 如果只靠 `conftest` 動態重定向，CI 可能綠在測試環境，runtime/import path 卻已漂移。

Rule:

- 抽出新 Module 後，原服務檔必須保留實體物理別名：
  - `_collect_route_signals = new_module.collect_route_signals`
  - `_build_codeintel_evidence = codeintel_context.build_codeintel_evidence`
  - 同類 legacy helper aliases 需顯式列出。
- 禁止用動態 `conftest` redirect 當作相容性主方案。
- shim 必須有一個 focused test 證明歷史 import 與 monkeypatch binding 仍有效。

Benefits:

- Locality：新 Implementation 可移到小 Module，舊 caller 仍由原 facade 承接。
- Leverage：每次切片不必同時改所有歷史測試與 caller。
- Deletion test：只有 caller map 證明無人依賴舊 alias 後，才允許刪 shim。

Stop condition:

- 原 module 失去 legacy helper alias；
- mock binding 改到新 path 才能過測；
- `conftest` 需要攔截 import path 才能維持綠燈。

### G2. Immutable Golden Master 與 CI 硬控門禁

Decision: `READONLY_SCHEMA_HARD_GATE`

Problem:

- benchmark row、receipt、runtime trace、public gate artifact 都依賴穩定 schema。
- 測試中自動覆寫 golden snapshot 會把 schema drift 變成隱性改動。

Rule:

- 歷史基準 JSON schema 快照必須唯讀化歸檔並納入 Git 追蹤。
- 測試執行中禁止自動覆寫 golden snapshot。
- schema drift 比對必須納入 `scripts/ops/ci_gate.py` hard gate。
- schema 變更只能透過顯式 migration note + updated golden snapshot + focused schema test。
- Golden Master / telemetry JSON 讀寫必須指定 `encoding="utf-8"`。
- 字串比對前必須做 LF canonicalization：`replace("\r\n", "\n")`。
- 實作時必須新增或更新 root `.gitattributes`：
  - `docs/testing/golden_schemas/*.json text eol=lf`
  - 若 telemetry snapshot 存在獨立目錄，該目錄下 `*.json` 也必須 `text eol=lf`。

Candidate artifacts:

- `docs/testing/golden_schemas/`
- `docs/reports/*schema*.json`
- public benchmark bundle schema snapshots
- runtime receipt schema snapshots

Benefits:

- Locality：schema contract drift 集中在一個 gate，不散落在 runner/report tests。
- Leverage：public claim、runtime receipt、benchmark accounting 共享同一 hard stop。
- Deletion test：若刪除此 gate，schema drift 會回到多個測試與人工 review 中。

Stop condition:

- test helper 自動更新 golden snapshot；
- untracked generated schema 被當成 truth；
- JSON fixture 讀寫未指定 UTF-8；
- CRLF/LF 差異可造成測試失敗；
- `.gitattributes` 未鎖定 golden JSON EOL；
- CI 只 warn 不 block schema drift。

### G3. SQLite Retry 容錯與 Fail-Fast 防線

Decision: `BUSY_LOCKED_ONLY_RETRY`

Problem:

- SQLite retry 可以修復 concurrent busy/locked，但也可能掩蓋 corrupt、permission、schema error。

Rule:

- 最大重試次數：`5`。
- Backoff：jittered exponential backoff。
- 只捕獲 retryable busy/locked 錯誤碼或等價訊號。
- `SQLITE_CORRUPT`、schema mismatch、permission denied、disk/full IO 等嚴重錯誤一律 fail-fast。
- 單元測試必須包含 busy-then-success、retry exhaustion、non-busy fail-fast、corrupt fail-fast。

Benefits:

- Locality：retry/backoff/error classification 集中在 `SQLiteRetryHandler`。
- Leverage：多個 SQLite writer 可共用同一 seam。
- Deletion test：若刪除此 seam，busy/locked retry 與 fail-fast 條件會複製到各 writer。

Stop condition:

- retry 包住非 busy/locked 錯誤；
- retry 次數不可觀測或無上限；
- writer integration 無錯誤注入測試。

### G4. EvidenceSealingBarrier Legacy Read Mode

Decision: `LEGACY_READ_ONLY_NO_CLAIM_CREDIT`

Problem:

- `scripts/bench/gemini_nexus_report.py::_load_evidence_bundle` 目前是 report reader ingress。
- 若 EvidenceSealingBarrier 一接入就 sealed-only hard fail，歷史 unsealed 基準報告可能無法讀取。
- 若直接放行 unsealed telemetry，又會污染 public claim / promotion credit。

Rule:

- 新 evidence bundle：unsealed、hash-invalid、partial、dirty-write evidence 必須 fail-closed。
- 歷史 unsealed telemetry：可轉成 `UNSEALED_LEGACY` read-mode，允許報告讀取與警告輸出。
- `UNSEALED_LEGACY` 不可貢獻 public claim、runtime promotion、training eligibility、cost-efficiency promotion credit。
- report output 必須顯示 legacy warning 與 claim boundary。
- focused tests 必須覆蓋 sealed pass、new unsealed fail-closed、legacy unsealed read-only warning、legacy no-claim-credit。

Benefits:

- Locality：sealed/read-only/claim-credit decision 集中在 evidence barrier Adapter。
- Leverage：舊報告仍可審計，新 claim gate 不被舊資料污染。
- Deletion test：若刪除此 read-mode，reader 會在「全 fail」與「全放行」之間重複手寫例外。

Stop condition:

- `UNSEALED_LEGACY` 被算入 public claim/promotion；
- 新未封存 evidence 只 warn 不 block；
- 歷史報告讀取需要手動 patch JSON。

### G5. Runner No-Network Socket Barrier

Decision: `UNIT_TESTS_OFFLINE_BY_DEFAULT`

Problem:

- `direct_provider_runner.py` 與 `with_nexus_runner.py` 會靠近 provider/subprocess/network seam。
- 拆分後的 unit tests 若 mock 不完整，可能意外觸發 live provider 或 local socket。
- 主 `pyproject.toml` 目前未列 `pytest-socket`；因此必須先明確選擇 socket blocker。

Rule:

- runner/helper unit tests 預設禁用 socket。
- Preferred Adapter：`pytest-socket` with socket disabled。
- Fallback Adapter：project-local pytest fixture monkeypatching `socket.socket` / `socket.create_connection` for selected tests。
- 若採 project-local socket blocker，允許 loopback whitelist：`127.0.0.1`、`::1`、`localhost`，僅供 pytest/debugger/coverage/local harness。
- 其他 external IP、private metadata IP、domain request 一律阻斷。
- blocker 必須拋 `SocketBlockedError`，錯誤訊息包含目標 host 與 URL/port/protocol。
- live provider tests 必須顯式標記、跳過 by default、不得被 unit validation matrix 選中。
- fixture materialization tests 不得 clone/fetch network，除非測試名稱與 marker 明確宣告 external integration。

Benefits:

- Locality：network denial 在 test seam，不散在 provider runner mocks。
- Leverage：防止 benchmark refactor unit tests 變成外部環境相依。
- Deletion test：刪除此 barrier 後，每個 runner test 都要自行防 live network。

Stop condition:

- unit test 可建立 external real socket；
- loopback whitelist 允許外部 domain 或 private metadata IP；
- `SocketBlockedError` 未包含 blocked host / URL / port；
- provider runner helper test 需要有效 API key；
- external clone/fetch 在未標記 integration 的測試中發生。

### G6. Stateless Auto Flow Executor

Decision: `RLM_CONTROLLER_OWNS_STATE`

Problem:

- `run_auto_flow` 提取為 `auto_flow_executor.py` 時，容易把 X/R-loop counters、transition state、retry counters 搬進 executor。
- 這會讓 `RlmController` 與 executor 同時持有狀態，形成 state twin。

Rule:

- `auto_flow_executor.py` 必須是 stateless executor。
- executor Interface 只接受 immutable request dataclass，回傳 result/receipt，不保存 mutable counters。
- X/R-loop state、budget、continue decision、terminal reason 必須 100% 留在 `RlmController` 或其 receipt helper。
- executor 不可更新 module-level global state，不可持有 controller copy，不可自行遞增 X/R counters。
- 如果 `RlmController` 新增 mutable `transition()`、`update_receipt()`、`observe_*()` 類方法，狀態更新必須在 atomic section 內完成。
- sync path 使用 `threading.RLock` 或等價 lock；async path 使用 `asyncio.Lock` 或明確 async-safe Adapter。
- receipt emission 必須基於鎖內一致 snapshot，不可讀取 half-updated counters。

Benefits:

- Locality：RLM state machine 只在 `RlmController`。
- Leverage：executor 可測 baseline/probe/hyper/original rescue 分支，不需要複製狀態機。
- Deletion test：刪除 executor 只會讓 execution branches 回到 orchestration，不會丟失 RLM state semantics。

Stop condition:

- executor 保存 mutable loop state；
- executor 自行決定 X/R transition；
- `RlmController` mutable state transition 無 lock；
- async/sync callers 共用 controller 但無 concurrency contract；
- receipt 讀到 half-updated counters；
- tests 需要同時 assert executor state 與 `RlmController` state。

### G7. Telemetry Fidelity Snapshot

Decision: `F01_TELEMETRY_FIDELITY_SNAPSHOT`

Problem:

- `capability_ab_runner.py` 拆分後，telemetry field 可能名稱不變但數值計算漂移。
- 只跑 schema/gate tests 可能看不到 precision、ratio、wall/token ledger 的細微退化。

Rule:

- 新增或保留 `tests/benchmark/test_telemetry_fidelity.py`。
- 使用固定 mock execution dataset，不連 live provider。
- 產生重構前後 telemetry JSON canonical snapshot。
- canonicalization 排除 UUID、timestamp、temp path、run id 等非決定性欄位。
- JSON fixture 讀寫指定 `encoding="utf-8"`。
- string canonicalization 先統一 `\r\n` -> `\n`。
- canonicalization 對無序 string lists 先排序，例如 loaded paths、selected helpers、warning code lists。
- canonicalization 對數值列表先排序，再逐項比對。
- 浮點比對使用 `math.isclose(abs_tol=1e-5, rel_tol=1e-5)`，禁止使用 broad tolerance。
- numeric precision 必須一致；允許差異必須逐欄明列，不可用 JSON raw order 當失敗依據。

Benefits:

- Locality：telemetry fidelity 成為一個測試 Module，不散落在 public gate tests。
- Leverage：任何 runner split 都能快速證明數值語義未退化。
- Deletion test：若刪除此 snapshot，欄位存在但數值 drift 會回到人工 review。

Stop condition:

- snapshot 需要 live provider；
- test 使用 blanket tolerance 掩蓋 precision drift；
- raw JSON list order 造成假陽性；
- 無序 string/numeric lists 未 canonicalize；
- encoding 或 EOL 差異造成假陽性；
- UUID/timestamp 以外欄位被無理由排除。

### G8. Glob Assertions / Focused Nodeid Hard Gate

Decision: `F02_NO_SILENT_TEST_OR_MANIFEST_SKIP`

Problem:

- `Path.glob` 找 manifest/config 時，空集合可能讓 benchmark 或 preflight 靜默跳過。
- high-risk file 的 test impact 若只指到整個目錄，容易漏掉必要 focused nodeid 或被 unrelated skipped tests 掩蓋。

Rule:

- manifest/config discovery 使用 `Path.glob` 時，空集合必須丟 `FileNotFoundError`。
- `scripts/ops/ci_gate.py` 必須對照 `docs/testing/test_impact_map.md` 的 focused test nodeid list。
- listed nodeid 必須在目前 test collection 中存在。
- listed nodeid 若 collection 狀態為 skipped、deselected-only、not found，CI hard fail。
- 對 protected files，不能只以目錄級測試當唯一 gate；需要 nodeid-level 或 group-specific test row。

Benefits:

- Locality：test selection contract 集中在 impact map + CI gate。
- Leverage：避免 glob drift、rename drift、skipped drift 讓 refactor 看似綠燈。
- Deletion test：若刪除此 gate，每個 protected slice 都要手動核對 test nodeids。

Stop condition:

- empty glob 被當成空 manifest/config；
- impact-map nodeid 不存在但 CI 仍 pass；
- skipped nodeid 被當成 covered。

### G9. Canonical Frozen FixtureConfig

Decision: `F03_CANONICAL_FROZEN_FIXTURE_CONFIG`

Problem:

- fixture materialization 同時處理 repo root、run dir、cache dir、hidden/visible tests、external clone path。
- mutable config 或 absolute host path 會放大 macOS 與 Linux CI sandbox 差異。

Rule:

- `FixtureConfig` 必須使用 `@dataclass(frozen=True)`。
- `__post_init__` 使用 `object.__setattr__` 做一次 canonicalization。
- 所有 path 必須 canonicalize 到 `PROJECT_ROOT` 相對路徑或明確標記為 isolated temp root。
- config 不可在 runner execution 中被 mutation。
- sandbox 越界 path 必須 fail-fast，不可 fallback 到 host absolute path。

Benefits:

- Locality：fixture path policy 集中在 config Module。
- Leverage：fixture materializer、direct runner、with-Nexus runner 共享同一 config invariants。
- Deletion test：若刪除此 config，path normalization 與 sandbox checks 會回到每個 runner helper。

Stop condition:

- config 可變；
- host absolute path 進入 public evidence；
- macOS-only path 在 CI Linux snapshot 中成為 truth。

### G10. CLI Exception Translation Decorator

Decision: `F04_CLI_EXCEPTION_TRANSLATION_SEAM`

Problem:

- CLI Action Module 若直接處理 Click exit/stderr，Action interface 會被 CLI framework 污染。
- CLI seam 若不統一翻譯 domain exception，錯誤輸出與 exit code 容易漂移。

Rule:

- Action Module 可丟 `NexusDomainException` 或更窄 domain exception。
- CLI boundary 使用 `translate_action_exceptions` decorator。
- decorator 必須先 `raise` / pass-through `KeyboardInterrupt` 與 `click.Abort`，不可包裝。
- decorator 負責把 domain exception 轉成 stable exit code、stderr、JSON error shape。
- Ctrl+C / abort semantics 必須保留 CLI exit code `130` 或 Click 預設 abort 行為。
- Action Module 不 import Click。
- `test_cli_output_schema.py` 必須有異常輸入 snapshot tests。

Benefits:

- Locality：CLI formatting/error policy 集中在 boundary Adapter。
- Leverage：每個 Action 可保持純 Python interface。
- Deletion test：若刪除此 decorator，每個 command body 都會複製 exit/stderr handling。

Stop condition:

- Action Module import Click；
- `KeyboardInterrupt` / `click.Abort` 被轉成 validation/domain error；
- Ctrl+C 不再保留 exit code 130 / abort semantics；
- domain exception 直接穿透成 traceback；
- error snapshot 漂移但沒有 migration note。

## 6. 第二輪 agent 建議評估

### A. `FixtureMaterializer` / `FixtureProvider`

Decision: `ACCEPT_WITH_SHAPE_CHANGE`

可吸收，但 Interface 不能只有 `materialize(task_id: str) -> FixtureResult`。Benchmark fixture 實際上還受 manifest、workspace、visible/hidden split、external clone policy、cache root、fail-closed reason 影響。Interface 必須把這些 invariants 明確化，避免把隱性全域狀態藏進 Implementation。

建議 Module：

- `scripts/bench/fixture_materialization.py`

建議 Interface：

- `materialize_fixture(task: BenchmarkTask, *, run_dir: Path, cache_dir: Path | None, allow_external_clone: bool) -> FixtureMaterializationResult`

Deletion test：

- 如果刪除此 Module，runner 會重新散落 path join、visible/hidden test file generation、external fixture clone/setup、cache cleanup、infra-invalid classification；複雜度會回湧，因此值得切。

Stop condition：

- public task manifest 欄位、hidden verifier contract、external clone fail-closed reason 任一漂移，停止。

### B. `CommandRegistry` / `Action`

Decision: `ACCEPT_PHASED`

方向正確，但不能一次把 `nexus_cli.py` 變成新 registry framework。第一步應保持 command names、Click decorators、compat aliases 不漂移，把 command body 下沉為無 Click 依賴的 Action Module。

建議 Module：

- `scripts/engine/commands/learn.py`
- `scripts/engine/commands/research.py`
- `scripts/engine/commands/multi_agent.py`
- `scripts/engine/commands/bench.py`

建議 Interface：

- `Action.execute(args: ActionArgs) -> ActionResult`
- `register_commands(cli: click.Group) -> None` 只在第二階段引入；第一階段可先搬 body，不改 registration。

Deletion test：

- 若刪除 Action Module，CLI file 會重新同時承擔 parsing、validation、business logic、formatting、file IO；locality 明顯下降。

Stop condition：

- deprecated aliases 漂移；
- tests 依賴 monkeypatch `scripts.engine.nexus_cli` globals 但沒有 adapter seam；
- CLI output JSON shape 改變。

### C. `DynamicPolicyMatcher`

Decision: `ACCEPT_RENAME_TO_DOMAIN_LANGUAGE`

方向正確，但名稱應使用 repo 現有語義，避免 generic dynamic abstraction。剩餘債務不是新增 store，而是把 route-cost matching、expected-capability protection、S2T policy merge 從 loader I/O 中分離。

建議 Module：

- `nexus/engine/route_cost_policy_matcher.py`
- `nexus/engine/expected_capability_policy.py`
- `nexus/engine/s2t_policy_loader.py`

建議 Interface：

- `match_route_cost_policy(features: RouteCostFeatures, policies: Sequence[RouteCostPolicy]) -> RouteCostPolicyDecision`
- `apply_expected_capability_policy(request: CapabilityPolicyRequest) -> ExpectedCapabilityDecision`

Deletion test：

- 如果刪除 matcher，feature rule matching、scope summary、task-id controls、env override 會回到 loader；loader 再次變成 I/O + decision 混合體。

Stop condition：

- route policy output snapshot 漂移；
- benchmark route-cost controls 改變但沒有 migration note；
- 新 storage adapter 沒有第二個 real consumer。

### D. `DatabaseTransactionManager`

Decision: `PARTIAL_DEFER`

問題存在，但不應立刻做全域 `DatabaseTransactionManager`。目前 repo 已有 `SQLiteRetryHandler`，更符合 Linus 原則的下一步是選一個真實 SQLite writer 做窄整合，等出現第二個 Adapter 後再升級成 transaction manager seam。

建議第一步：

- caller map：列出 `memory_manager.py`、`ContextHub`、`FindingsMemoryStore`、其他 SQLite 寫入端。
- 選最小真實 writer：優先 `nexus/core/memory_manager.py::_execute_with_retry` 或已有 P9 報告指定 call site。
- 使用現有 `SQLiteRetryHandler`，不要重新發明 transaction manager。

升級條件：

- 至少兩個 SQLite writer 使用同一 retry Interface；
- 都有 busy/locked 實證或測試 fixture；
- deletion test 證明不集中會造成 retry/error handling 複製。

Stop condition：

- 目標 writer 不是 SQLite-backed；
- 需要改 public/runtime lane；
- retry wrapper 掩蓋 non-busy SQLite 錯誤。

## 7. 剩餘大型技術債排序

### S1. Benchmark Harness Facade

Files:

- `scripts/bench/capability_ab_runner.py`
- `tests/benchmark/test_capability_ab_runner.py`

Problem:

- 同時承擔 fixture materialization、direct provider execution、Nexus execution、row normalization、wall-ledger accounting、public gate posture、evidence bundle writing、preflight、CLI entrypoint。
- blast radius 最大，因為任何欄位漂移都可能影響 public claim eligibility、token/cost accounting、provider variance analysis。

Current progress:

- public gate metrics / bundle checks 已部分抽出。
- receipt/token row fields 已部分抽出。
- route execution policy 與 model-participation rescue policy 已抽出。

Next split candidates:

1. `scripts/bench/fixture_materialization.py`
   - Move: fixture source builders、visible/hidden tests split、external clone/setup、cache path resolution、infra-invalid classification。
   - Interface: `materialize_fixture(...) -> FixtureMaterializationResult`。
   - Config: `FixtureConfig` must be frozen and canonicalized to `PROJECT_ROOT` relative paths。
   - Tests: fixture contract tests，不啟動完整 benchmark。
2. `scripts/bench/direct_provider_runner.py`
   - Move: direct Gemini/Codex prompt、retry、parse、session metadata。
   - Tests: parser/retry tests；socket disabled by default；禁止 live provider calls。
3. `scripts/bench/with_nexus_runner.py`
   - Move: bounded `run_with_nexus` attempt orchestration。
   - Tests: strict baseline、pre-model rescue、supervised bare-first、hidden verifier nodeids；socket disabled by default。
4. `scripts/bench/evidence_bundle_writer.py`
   - Move: bundle assembly；public-gate decisions 必須已在獨立 Module 後方。
   - Tests: `write_evidence_bundle` characterization before/after。

Stop conditions:

- public gate field names 改變；
- cost evidence class 改變但沒有 policy-change report；
- unit tests 需要 live provider call；
- runner/helper unit tests 可建立 real socket；
- telemetry fidelity snapshot drift；
- `FixtureConfig` 可變或含 host absolute path；
- helper extraction 造成 row contract 欄位缺失。

### S1. CLI Command Monolith

Files:

- `scripts/engine/nexus_cli.py`
- `scripts/engine/commands/`

Problem:

- Click decorators、command parsing、input validation、business action、JSON formatting、compatibility aliases 混在同一檔案。
- 新命令工作會反覆碰 root CLI file。

Current progress:

- research session support 已抽到 `scripts/engine/commands/research_support.py`。

Next split candidates:

1. `scripts/engine/commands/learn.py`
   - Move: `learn:*` command bodies 與 learn report formatting。
   - Keep: root Click decorators 可先留在 `nexus_cli.py`。
   - Error seam: domain errors translated only by `translate_action_exceptions` at CLI boundary。
   - Tests: CLI learn tests + `py_compile`。
2. `scripts/engine/commands/research.py`
   - Move: research command bodies；registration 第二階段再抽。
   - Tests: `test_cli_research_seams.py`、research support tests。
3. `scripts/engine/commands/multi_agent.py`
   - Move: multi-agent command group bodies。
   - Tests: swarm/multi-agent command smoke。
4. `scripts/engine/commands/bench.py`
   - Move: bench/sandbox/registry small command bodies。
   - Tests: CLI pregate、registry tests。

Stop conditions:

- command names 或 deprecated aliases 漂移；
- `NexusCLI` compatibility shim 破；
- JSON output shape 改變；
- Action Module import Click；
- domain exception 沒有被 `translate_action_exceptions` 轉成 stable exit/stderr；
- monkeypatch-sensitive tests 沒有 adapter seam。

### S1. Research Flow Orchestration Facade

Files:

- `nexus/app/research_flow_service.py`
- `tests/app/test_research_flow_service.py`

Problem:

- `run_auto_flow` 還承擔 execution branch mechanics。
- CodeIntel context packing、RLM trace writing、capability evidence、runtime receipt、S2T/autoreason trace、skill-mount runtime contract glue 仍集中。

Current progress:

- route decision、signal collection、evidence packing、phase timing、baseline metadata、history IO、bounded orchestrator receipt seams 已存在。

Next split candidates:

1. `nexus/research/flow/codeintel_context.py`
   - Move: `_codeintel_run_cache_graph_path`、`_load_codeintel_graph`、`_build_codeintel_evidence`、`_task_with_codeintel_context`。
   - Compatibility: `research_flow_service.py` must keep physical aliases for moved helpers until caller map proves deletion-safe。
   - Tests: CodeIntel context focused tests + existing app route tests。
2. `nexus/research/flow/runtime_receipts.py`
   - Move: `_runtime_receipt_plan_payload`、skill-mount runtime contract helpers、capability receipt augmentation。
   - Tests: runtime skill-mount contract tests。
3. `nexus/research/flow/auto_flow_executor.py`
   - Move: baseline apply/probe/hyper apply/original verification rescue。
   - Interface: small executor request/result dataclasses。
   - Constraint: stateless executor only；X/R-loop counters and transition state remain in `RlmController`。
   - Tests: baseline-only、probe-success fast path、probe-then-hyper、guard fallback characterization。
4. `nexus/research/flow/rlm_trace.py`
   - Move: `_write_research_rlm_trace` 與 RLM trace payload shaping。
   - Tests: RLM trace path + bounded receipt tests。

Stop conditions:

- `chosen_flow`、`strategy.path`、`semantic_status`、history payload shape 漂移；
- monkeypatch-sensitive tests 需要 broad rewrites；
- moved helpers 沒有原 module physical aliases；
- dynamic `conftest` redirect 成為主要相容策略；
- `auto_flow_executor.py` 持有 mutable X/R-loop state；
- recursive runtime dispatch 被意外打開。

### S2. Learning Policy Loader Deepening

Files:

- `nexus/engine/learning_policy_loader.py`
- `nexus/engine/learning_policy_store.py`

Problem:

- `LearningPolicyStore` 已存在，下一步不是重新定義 store。
- loader 仍混合 schema validation、route-cost feature matching、env controls、expected-capability protection、S2T draft merge、usage ledger。

Next split candidates:

1. `nexus/engine/route_cost_policy_matcher.py`
   - Move: `_controls_from_feature_rules`、`_feature_rule_matches`、scope summaries、task-id policy controls。
   - Tests: route-cost loader tests + matcher edge cases。
2. `nexus/engine/expected_capability_policy.py`
   - Move: executor flag 與 expected-capability protection。
   - Tests: expected-capability override、receipt-lite tests。
3. `nexus/engine/s2t_policy_loader.py`
   - Move: S2T draft schema、promotion gate parsing。
   - Tests: S2T policy draft tests。

Stop conditions:

- route policy output 改變但沒有 explicit migration；
- benchmark route-cost controls 與 snapshot 不一致；
- 新 storage adapter 沒有第二個 consumer。

### S2. ContextHub Physical Split

Files:

- `nexus/core/context_hub.py`
- `nexus/core/context_view.py`

Problem:

- `ContextHub` 同時扮演 high-level context facade 與 lower-level storage/budget behavior。
- physical split 只允許 leaf extraction，不允許 constructor-wide rewrite。

Current progress:

- `context_view.py` 已抽出 `StateView` 與 `ContextDependencies`。
- `context_budget_sources.py` 已抽出 ContextHub budget source shaping 與 token estimate helper。
- `context_text_store.py` 已抽出 local rules text fallback 與 last-handoff JSON fallback；`ContextHub` 保留相容 facade method。
- caller-map / strict-deps compatibility evidence 已存在。

Next split candidates:

1. `nexus/core/context_budget_sources.py`
   - Done: L0/L1/history/extra source shaping、token estimate helper、ContextHub delegation deletion test。
2. `nexus/contracts/context_budget.py`
   - Already owns: token-budget arithmetic、budget receipts。
   - Next only if needed: keep arithmetic contract changes here, not in `ContextHub`。
3. `nexus/core/context_text_store.py`
   - Done: local `program.md` rules fallback、`.nexus/state/last_handoff.json` UTF-8 JSON fallback、invalid JSON degrade to `{}`。
   - Tests: standalone text-store tests + ContextHub monkeypatch deletion test，不改 facade output。
   - Deferred: SQLite-backed store fallback；需先有第二個 SQLite writer caller map + busy/locked fixture。

Stop conditions:

- constructor compatibility 破；
- strict dependency mode 行為改變；
- extraction 產生 hidden mutable global state。

### S2. SQLite Retry / Transaction Seam

Files:

- `nexus/infrastructure/sqlite_retry.py`
- `nexus/core/memory_manager.py`
- `nexus/core/context_hub.py`
- possible SQLite-backed findings/memory stores

Problem:

- SQLite busy/locked retry 已有 reusable handler，且已窄整合到 `ProjectMemoryManager._execute_with_retry`；尚未成為多個 writer 的穩定 seam。
- 直接上 `DatabaseTransactionManager` 會過早抽象化。

Next split candidates:

1. SQLite writer caller map
   - Output: writer list、busy/locked risk、rollback path、test fixture。
2. First writer integration
   - Target: P9 指定的最小 SQLite-backed writer。
   - Use: existing `SQLiteRetryHandler`。
   - Limits: max retries `5`；jittered exponential backoff；busy/locked only。
3. Second writer proof
   - 只有第二個 writer 也需要相同 Interface 時，才考慮 `transaction_retry` context manager。

Stop conditions:

- target writer 不是 SQLite-backed；
- retry 包住 non-busy error；
- `SQLITE_CORRUPT` 或 schema/permission error 被 retry 掩蓋；
- integration 需要 runtime/public gate。

### S3. Conditional Legacy Facades

Files:

- `nexus/engine/pipeline_repair.py`
- `nexus/engine/capability_planner.py`

Problem:

- 兩個檔案仍大，但都已完成部分 split。

Decision:

- 不重開 broad splits。
- 只有 failing acceptance test 證明現有 seam 無法隔離責任時才動。

Allowed future slices:

- `pipeline_repair.py`：repair/RLM acceptance failure 證明 facade responsibility 必須移出。
- `capability_planner.py`：policy-order 或 injection-equivalence failure 證明需要新 planner seam。

Validation:

- `uv run pytest tests/engine/test_pipeline_repair.py tests/engine/repair -q`
- `uv run pytest tests/engine/test_capability_planner.py tests/engine/planner tests/engine/test_learning_policy_store.py -q`

### S3. P9 Adapter Integration Debt

Artifact:

- `docs/reports/NEXUS_ANTIGRAVITY_P9_NARROW_INTEGRATION_CALL_SITES_2026-05-22.json`

Problem:

- 六個 adapters/contracts 仍是 plan-only 或 narrow integration state，尚未 runtime-wide wiring。

Recommended first integration order:

1. SQLite retry handler into `nexus/core/memory_manager.py::_execute_with_retry`
   - lowest public benchmark risk；
   - narrow rollback path。
2. Fault-tolerant AST snapshot into `nexus/services/codeintel/skeleton_context_adapter.py::build_code_skeleton_context`
   - CodeIntel-only blast radius。
3. Evidence sealing barrier into `scripts/bench/gemini_nexus_report.py::_load_evidence_bundle`
   - requires historical unsealed bundle compatibility policy；
   - historical unsealed telemetry may become `UNSEALED_LEGACY` read-only warning；
   - new unsealed evidence remains fail-closed；
   - `UNSEALED_LEGACY` cannot count toward public claim or promotion credit。

Defer:

- Local Gateway runtime wiring，直到有 real unguarded call site。
- Local Memory Hub runtime wiring，直到選到 read-only report consumer。
- Local Event Pipeline beyond test-only，除非 daemon/server gate 另行批准。

### S4. Root Hygiene

Problem:

- root-level scripts 與 generated artifacts 仍視覺噪音高。

Current decision:

- 先前 Clean Code root cleanup 因 reference-safety checks 以 zero moves 結案。

Next valid work:

- 先寫 compatibility wrappers。
- 一次只移一個 root entrypoint。
- reference check + CLI smoke。

Stop condition:

- 沒有 wrapper 與 reference map，不移。

### S4. Governance Eval Quality Warning

Problem:

- `ci_gate.py` 可 pass 但仍可能輸出 `Eval pass rate 20.00% below required 80.00%`。

Decision:

- 這不是 code architecture blocker。
- 若要完全 clean CI output，另開 wiki-eval quality debt。

## 8. 建議執行順序

### P0. Snapshot and guardrails

Output:

- current debt snapshot under `docs/reports/`；
- selected first slice 的 test-impact map；
- git dirty state 記錄。
- mandatory shim map for selected facade extraction。
- readonly Golden Master schema inventory。
- telemetry fidelity snapshot scope。
- focused nodeid list for protected files。

Validation:

- `git status --short`
- `uv run scripts/ops/ci_gate.py`

### P0A. Golden Master hard gate pregate

Output:

- list immutable schema snapshots to track；
- one no-autoupdate test proving golden files are not rewritten during tests；
- planned `ci_gate.py` check path for schema drift。
- `.gitattributes` rule for `docs/testing/golden_schemas/*.json text eol=lf` and telemetry snapshot JSON paths。
- UTF-8 + LF canonicalization helper for golden/telemetry JSON reads。

Stop condition:

- schema snapshot cannot be made deterministic；
- existing tests depend on auto-overwriting golden files；
- `.gitattributes` EOL rule is absent；
- JSON read/write path uses platform default encoding。

### P0B. Telemetry / Nodeid / Glob pregates

Output:

- `tests/benchmark/test_telemetry_fidelity.py` dataset and canonicalization rules；
- canonical comparison helper: exclude volatile ids/timestamps, sort unordered string/numeric lists, compare floats with `math.isclose(..., 1e-5)`；
- canonical comparison helper normalizes CRLF to LF before string comparison；
- impact-map focused nodeid inventory for protected files；
- glob assertion checklist for manifest/config discovery call sites。

Stop condition:

- telemetry dataset needs live provider；
- impact-map nodeids cannot be collected；
- any manifest/config glob can silently return empty.
- EOL/encoding differences can trigger false telemetry failure.

### P1. Lowest-risk leaf extraction

Recommended first implementation:

- `research_flow_service` CodeIntel context extraction，或
- P9 SQLite retry one-writer integration，或
- `ContextHub` token budget leaf。

Selection rule:

- caller set 最小；
- deletion test 最清楚；
- 不碰 public/runtime gate。
- mandatory physical shim 可保留。

### P2. Benchmark fixture materialization

After P1 passes:

- implement `scripts/bench/fixture_materialization.py`。
- implement canonical frozen `FixtureConfig` before moving fixture path logic。
- add or verify runner no-network socket barrier before provider/Nexus runner helper tests。

Validation:

- fixture materialization unit tests；
- selected `tests/benchmark/test_capability_ab_runner.py` nodeids；
- telemetry fidelity snapshot remains identical after canonicalization；
- no live provider calls。
- golden schema drift gate remains PASS。
- socket barrier blocks unintended live network。

### P3. Benchmark runner contract extraction

After fixture seam stable:

- direct provider runner 已抽出；
- with-Nexus runner 已抽出；
- trial evidence artifact writer 已抽出；
- evidence bundle gate builder 已抽出；
- evidence bundle payload finalizer/writer、rubric bundle、accounting context、provider context、row-set context、manifest metadata、section builders 與 top-level payload assembly 已抽出；
- remaining runner work 只允許基於新的 failing evidence 切 side-effect orchestration seam，不做 generic broad split。

Validation:

- helper tests first；
- selected benchmark nodeids；
- socket disabled by default for helper tests；
- socket blocker allows only loopback and reports blocked host/URL；
- full `tests/benchmark/test_capability_ab_runner.py` before merge。

### P4. CLI Action modules

After CLI research support helper settles:

- move learn command bodies；
- move research command bodies；
- move multi-agent command bodies；
- move bench/registry small command bodies。
- add `translate_action_exceptions` before Action Modules start throwing domain exceptions。

Validation:

- group-specific CLI tests；
- deprecated alias tests；
- `test_cli_output_schema.py` exception snapshots；
- Ctrl+C / `click.Abort` bypass tests preserve abort semantics / exit code 130；
- `uv run python -m py_compile scripts/engine/nexus_cli.py`。

### P5. Policy matcher extraction

After benchmark/CLI lower-risk seams:

- extract route-cost policy matcher；
- extract expected-capability policy；
- extract S2T policy loader only if tests identify isolated responsibility。

Validation:

- route-cost loader tests；
- expected-capability tests；
- S2T draft tests。

### P6. Conditional planner/repair work

Only if failing acceptance evidence exists:

- planner injection/policy-order failure；
- repair acceptance/RLM composition failure。

## 9. 驗證矩陣

| Slice | Required focused validation |
| --- | --- |
| Mandatory shim | focused import/monkeypatch compatibility test for moved helper aliases |
| Golden Master schema | `uv run pytest tests/ops/test_ci_gate_*schema* tests/*/*schema* -q`; JSON reads use UTF-8 and LF canonicalization |
| Evidence sealing legacy read | sealed pass, new unsealed fail-closed, legacy `UNSEALED_LEGACY` read-only warning, no claim credit |
| Runner no-network | socket barrier test; external socket blocked; loopback allowed; `SocketBlockedError` includes host/URL/port |
| Stateless auto-flow executor | tests assert executor has no mutable counters and RLM state remains in `RlmController` receipts |
| RLM atomic state | concurrent sync/async transition tests prove `RlmController` counters/receipts are atomic |
| Telemetry fidelity | `uv run pytest tests/benchmark/test_telemetry_fidelity.py -q`; unordered lists sorted; floats `math.isclose(..., 1e-5)`; CRLF normalized |
| Glob assertions | tests prove empty manifest/config glob raises `FileNotFoundError` |
| Focused nodeid gate | CI gate validates `docs/testing/test_impact_map.md` listed nodeids exist and are not skipped |
| Frozen FixtureConfig | fixture config mutation fails, paths canonicalize to `PROJECT_ROOT`, sandbox escape fails fast |
| CLI exception translation | `uv run pytest tests/engine/test_cli_output_schema.py -q`; `KeyboardInterrupt` / `click.Abort` pass through |
| Benchmark fixture | `uv run pytest tests/benchmark/test_capability_ab_runner.py -q -k "fixture or external or hidden"` |
| Benchmark harness | `uv run pytest tests/benchmark/test_route_execution_policy.py tests/benchmark/test_capability_ab_runner.py -q` |
| Research flow | `uv run pytest tests/research tests/app/test_research_flow_service.py -q` |
| CLI | `uv run pytest tests/engine/test_cli_research_support.py tests/engine/test_cli_research_seams.py tests/engine/test_nexus_cli_registry.py tests/engine/test_cli_pregate.py -q` |
| ContextHub | `uv run pytest tests/core/test_context_hub_strict_deps.py tests/core/test_belief_engine.py -q` |
| Learning policy | `uv run pytest tests/engine/test_learning_policy_store.py tests/engine/test_capability_planner.py tests/engine/test_rlm_outcome_integration.py -q` |
| SQLite retry | `uv run pytest tests/infrastructure/test_sqlite_retry.py tests/contracts/test_sqlite_write_guard.py -q` |
| Final gate | `uv run scripts/ops/ci_gate.py` |

## 10. 明確非目標

- 不做 runtime default promotion。
- 不改 public benchmark claim。
- 不改 Zero Trust V2 report。
- 不碰 Swarm / NSP / Go sidecar。
- 不做 broad root cleanup。
- 不用 line count reduction 當成功宣稱。
- 不在沒有 caller map / deletion test / focused tests 的情況下拆 facade。
- 不用 `conftest` 動態重定向取代物理相容 shim。
- 不讓測試自動覆寫 Golden Master schema。
- 不建立無第二個 Adapter 證據的全域 transaction manager。
- 不讓 `UNSEALED_LEGACY` 取得 public claim、runtime promotion、training eligibility 或 cost-efficiency credit。
- 不讓 runner/helper unit tests 連 live provider 或開 real socket。
- 不在 `auto_flow_executor.py` 保存 X/R-loop state。
- 不允許 telemetry refactor 只用 schema pass 取代數值 fidelity pass。
- 不允許 encoding / CRLF drift 造成 golden/telemetry 假陽性。
- 不允許 empty glob 變成空 manifest/config。
- 不允許 focused nodeid 缺失或 skipped 還讓 CI pass。
- 不允許 mutable fixture config 或 host absolute path 進入 benchmark evidence。
- 不允許 Action Module 依賴 Click 或自行格式化 CLI stderr。
- 不允許 `translate_action_exceptions` 包裝 `KeyboardInterrupt` / `click.Abort`。
- 不允許多 thread / async caller 共用 mutable `RlmController` 而沒有 atomic transition contract。

## 11. 最新結論

舊 agent 分析方向正確，但已過期。

仍然正確：

- `research_flow_service.py`、`ContextHub`、policy loading、root hygiene 都仍是債務。

需要修正：

- `capability_planner.py` 與 `pipeline_repair.py` 不再是立即 broad split 目標；只做 conditional facade work。
- `LearningPolicyStore` 已存在；下一步是 policy matcher、expected-capability policy、S2T loader 分離。
- 最大未被舊報告提到的債務是 `scripts/bench/capability_ab_runner.py`。
- `scripts/engine/nexus_cli.py` 是目前排名第二的大型技術債。
- `DatabaseTransactionManager` 應延後；先用現有 `SQLiteRetryHandler` 做一個真實 writer integration。
- 三大架構安全共識已升級為 Hard Gates：Mandatory Shim、Immutable Golden Master schema、SQLite busy/locked-only retry。
- 第三輪三個隱漏盲點已吸收：EvidenceSealingBarrier legacy read-mode、runner no-network socket barrier、stateless auto-flow executor。
- 第四輪四個安全共識已吸收：Telemetry Fidelity Snapshot、Glob/Focused Nodeid Hard Gate、Canonical frozen FixtureConfig、CLI Exception translation decorator。
- 第五輪四個安全補強已吸收：RLM atomic state transition、UTF-8/LF Golden JSON stability、loopback-only socket whitelist、CLI interrupt pass-through。

已完成且不應重開：

- `P1A`: `nexus/research/flow/codeintel_context.py` 已從 `nexus/app/research_flow_service.py` 抽出，原檔保留物理相容 alias。
- `P2A`: `scripts/bench/fixture_materialization.py`、fixture source selection、external fixture injection seam 與 sandboxed local Adapter 已完成；live clone/setup 仍 fail-closed。
- `P3`: benchmark runner 的 direct/with-Nexus runner seams、socket barrier、failure policy、evidence artifacts、gate/posture/accounting/provider/row/manifest/payload seams 與 final payload assembly 已完成。
- `P4`: CLI code / skills / registry / bench / multi-agent / learn / ask / research route / auto-flow / run 等 Action modules 或 equivalent seams 已完成。
- `P5`: route-cost matcher、expected-capability policy、S2T policy loader 已完成。
- `Research Flow RLM trace`: `nexus/research/flow/rlm_trace.py` 已抽出；`research_flow_service.py` 保留 `_safe_trace_slug` / `_write_research_rlm_trace` physical aliases。
- `Research runtime receipt skill-mount`: `research_receipt_runtime.py` 已承接 runtime skill-mount receipt confirmation 與 contract building；`research_flow_service.py` 保留 `_build_runtime_skill_mount_contracts` / `_confirmed_skill_mount_receipt` physical aliases。
- `P9`: SQLite retry 已整合第一個真 writer；EvidenceSealingBarrier 已整合到 benchmark report reader opt-in sealed mode。
- `ContextHub`: `context_budget_sources.py` 與 `context_text_store.py` leaf extraction 已完成。

未完成但可接續：

- `capability_ab_runner.py` 仍是 orchestration facade；下一步只能基於新的 failing evidence 切 side-effect orchestration seam。
- `nexus_cli.py` 仍是 Click registration / compatibility facade；下一步只能基於 CLI output schema、deprecated alias 或 audit failing evidence 開小切片。
- `research_flow_service.py` runtime receipt JSON writer / semantic capability augmentation leaf 仍可接續；需要 focused tests 證明 receipt payload 不漂移。
- `ContextHub` 下一個 storage/retry leaf 只能在新的 caller map + deletion test 證明下開。

刻意未完成 / 暫不打開：

- external fixture remote live clone/setup Adapter：缺 sandboxed clone/cache policy、offline cache manifest、no-network tests、remote URL denylist。
- global `DatabaseTransactionManager`：`memory_manager.py` 與 `skill_registry.py` 已完成第二 writer retry integration；升級成全域 transaction manager 仍需第三個 writer 或重複 transaction-shape duplication 證據。
- planner/repair 更深拆：仍等 failing acceptance evidence，不主動重開。
- root hygiene：缺 wrapper、reference map、CLI smoke 前不搬。
- governance eval quality warning：屬 `OPEN-SEPARATE`，不是本重構計劃 blocker。

## 12. 執行紀錄 2026-05-22

本輪已完成：

- `P0A Golden JSON LF pregate`：新增 root `.gitattributes`，鎖定 tracked JSON、`docs/reports/**/*.json`、`docs/testing/golden_schemas/*.json`、`tests/**/*.json` 為 LF。
- `P0B Telemetry fidelity pregate`：新增 `tests/benchmark/test_telemetry_fidelity.py`，提供 nested canonical comparator，排除 volatile UUID/timestamp/run id，排序無序 string/numeric/dict list，float 用 `math.isclose(..., 1e-5)`，CRLF normalize 到 LF。
- `P0B Focused nodeid gate`：`scripts/ops/ci_gate.py` 新增 impact-map focused nodeid contract，會讀取 `docs/testing/test_impact_map.md` 的 active nodeid，確認 test file 存在，執行 focused nodeids，若有缺失或 skipped 則 hard fail。
- `P0B Impact-map alignment`：新增 `tests/benchmark/test_telemetry_fidelity.py` 自身映射，避免 changed-only selector 對新測試檔 fallback 到無關 `tests/core`。
- `P1A CodeIntel context leaf extraction`：新增 `nexus/research/flow/codeintel_context.py`，把 CodeIntel scan/impact/DCI evidence 與 prompt context formatting 從 `nexus/app/research_flow_service.py` 抽出；原檔保留 `_build_codeintel_evidence`、`_task_with_codeintel_context` 等實體 alias，維持歷史 import/monkeypatch binding。
- `P1A Impact-map alignment`：新增 `nexus/research/flow/codeintel_context.py`、`tests/app/test_research_flow_service.py`、`docs/testing/test_impact_map.md` 的精準映射，避免 P1A changed-only selector fallback 到無關 core suite。
- `G8 Glob strict helper`：新增 `scripts/ops/strict_file_discovery.py`，提供 `strict_glob`、`read_nonempty_json`、`strict_json_glob`；空 glob 會 `FileNotFoundError`，0-byte JSON 會 `ValueError`，壞 JSON 保留 `json.JSONDecodeError` fail-fast。
- `G8 Strategic map integration`：`scripts/ops/strategic_map_audit.py` 的 boundary rule `source_globs` 改用 `strict_glob`，manifest/config glob 不再靜默變成空集合。
- `G2/G7 Golden schema snapshot checker`：新增 `docs/testing/golden_schemas/manifest.json` 與 `telemetry_fidelity_snapshot.v1.json`，用 SHA-256 固化 snapshot；新增 `scripts/ops/check_golden_schema_snapshots.py`，檢查 UTF-8、LF、non-empty JSON、schema_version 與 hash drift。
- `G2/G7 CI hard gate`：`scripts/ops/ci_gate.py` 新增 `run_golden_schema_snapshot_check`，dry-run 與 normal CI path 都會執行 golden schema snapshot check。
- `P2A Fixture materialization first slice`：新增 `scripts/bench/fixture_materialization.py`，把 local fixture case directory、target/visible/hidden test 寫檔、extra file 寫檔與 path-escape 防線抽出；`capability_ab_runner.py` 保留 fixture source selection 與 public manifest semantics。
- `P2A Fixture split second slice`：`fixture_materialization.py` 新增 `split_fixture_tests`、`split_rlm_harder_fixture_tests`、`split_nexus_value_fixture_tests`、`portable_fixture_test_import`；`capability_ab_runner.py` active seam 改用新模組，舊 split 函式改名為 legacy fallback，避免覆蓋 active seam。
- `P2A Fixture split physical cleanup`：物理刪除 `capability_ab_runner.py` 內 legacy split fallback block；當時 runner 只剩 fixture source dictionaries 與 `_nexus_value_fixture_sources` / `_rlm_harder_fixture_sources` source selection，為下一步 source selection extraction 留下單一搬移點。
- `P2A External fixture adapter seam`：`fixture_materialization.py` 新增 `ExternalFixtureRequest`、`ExternalFixtureAdapterRequired`、`resolve_external_fixture`；`capability_ab_runner.py::_resolve_task_files` 改走此 seam，仍保持 fail-closed，不開 live clone/setup。
- `P2A Fixture source selection extraction`：把 Nexus value / RLM harder fixture source dictionaries 搬入 `fixture_materialization.py`，新增 `nexus_value_fixture_source`、`rlm_harder_fixture_source` 兩個小介面；`capability_ab_runner.py` 現在只負責選擇 fixture kind 與呼叫 materializer。
- `P2A External fixture adapter injection seam`：`ExternalFixtureRequest` 補上 `target_file` / `test_file` / `hidden_test_file`，`resolve_external_fixture(request, adapter=...)` 可透過注入 Adapter resolve external checkout；`_resolve_task_files(..., external_fixture_adapter=...)` 可被測試 fake adapter 驗證。預設仍是 `ExternalFixtureAdapterRequired` fail-closed，不開 live clone/setup。
- `P2A Sandboxed local external fixture Adapter`：新增 `SandboxedLocalExternalFixtureAdapter`，Interface 仍是 `resolve(request) -> FixtureMaterializationResult`；Implementation 僅接受本機 path / `file://` source，要求 source 落在 `allowed_source_roots`，拒絕 remote URL、source path escape、case-dir escape，並把 manifest 宣告的 target/visible/hidden files 複製進 workspace `.nexus/bench_cases/{task_id}`。live clone/setup 仍未啟用。
- `P2A External fixture offline cache pregate`：新增 `ExternalFixtureCacheManifest` 與 `OfflineCachedExternalFixtureAdapter`；remote fixture request 必須匹配 pinned `allowed_repo` / `allowed_ref` 並從 local `cache_dir` 複製 manifest-declared files。`network_allowed=True` 與 missing manifest 均 fail-closed，仍不執行 `git clone` / `fetch` / HTTP / SSH。
- `P3 Runner no-network pregate`：新增 `scripts/bench/runner_socket_barrier.py`，提供 scoped `block_external_runner_sockets()` 與 `SocketBlockedError`；外部 host 會 fail-fast，loopback (`localhost` / `127.0.0.0/8` / `::1`) 可通過，作為 direct provider / with-Nexus runner helper 拆分前的測試防線。
- `P3 Runner no-network integration`：`runner_socket_barrier.py` 新增 opt-in env `NEXUS_BENCH_BLOCK_EXTERNAL_RUNNER_SOCKETS=1` 與 `maybe_block_external_runner_sockets()`；`capability_ab_runner.py` 的 direct provider ask 與 with-Nexus Codex direct ask helper 在 opt-in profile 下會阻斷 Python external sockets，預設關閉以避免破壞 public/runtime provider calls。
- `P3 Direct provider failure policy seam`：新增 `scripts/bench/provider_failure_policy.py`，把 per-task stop-loss、direct provider timeout/infra row detection 與 consecutive abort reason helper 抽出；`capability_ab_runner.py` 保留舊 underscored import aliases 以維持既有測試與 caller 相容。
- `P3 Trial evidence artifact writer extraction`：新增 `scripts/bench/evidence_artifacts.py`，把 `_write_trial_evidence` 的 row/diff artifact 寫檔、artifact name sanitize 與 target sha256 計算抽出；`capability_ab_runner.py` 保留 `_write_trial_evidence` import alias，`write_evidence_bundle` 主 gate 計算暫不搬動。
- `P3 Direct provider runner seam`：新增 `scripts/bench/direct_provider_runner.py`，把 direct provider mode validation、provider-specific model label fallback、session reset boundary、prompt hash、prompt attribution buckets、provider response telemetry normalization、direct invocation retry loop 抽出；`capability_ab_runner.py::run_without_nexus` 改走 `_build_direct_provider_prompt`、`_run_direct_provider_attempts`、`_direct_prompt_attribution`、`_normalize_direct_provider_response`。live provider adapter 仍注入，不在 module 內直接綁定 Gemini/Codex CLI。
- `P3 With-Nexus runner seam`：新增 `scripts/bench/with_nexus_runner.py`，把 Codex wearing Nexus prompt、session reset boundary、Nexus control char accounting、first model attempt、pytest verifier pass/fail、bounded self-heal retry 狀態機抽出；provider ask、patch write、verifier execution、timeout 與 socket guard 全由 caller 注入。
- `P3 Evidence bundle gate builder seam`：新增 `scripts/bench/evidence_bundle_gates.py`，把 `write_evidence_bundle` 內 public delivery/cost gate failures、route policy evidence contract、expected-capability evidence contract、skill mount evidence contract、cost efficiency decision、`public_gate_checks`、`public_claim_gates` 集中到 `build_evidence_bundle_gate_outputs(context, config)`；runner 仍保留 payload serialization、direction magnitude、posture/x1/x3 history 與實際檔案寫入，避免一次搬動 public report surface。
- `P3 Evidence bundle posture/x1/x3 seam`：新增 `scripts/bench/evidence_bundle_posture.py`，把 public claim posture、training eligibility posture、valid-comparison readiness、direction magnitude、mutation hardening、recent compatible x1 history、x1 readiness history load/append/path、x3 promotion gate 從 `capability_ab_runner.py` 抽出；runner 保留相容 aliases，避免破壞既有 tests 與 public report call sites。
- `P3 Evidence bundle payload finalizer/writer seam`：新增 `scripts/bench/evidence_bundle_payload.py`，把 evidence bundle final contracts (`external_provider_claim_boundary_contract`、`public_promotion_readiness_contract`) 與 UTF-8 JSON write 從 `capability_ab_runner.py` 抽出；runner 仍保留主 payload dict assembly 與成本/provider variance 計算。
- `P3 Evidence bundle rubric bundle seam`：`scripts/bench/evidence_bundle_payload.py` 新增 `summarize_rubric_contract_rows` 與 `build_rubric_contract_bundle`，把 `rubric_contract` pass-rate/reason aggregation、四個 summary key 與 claim boundary schema 從 `write_evidence_bundle` 抽出；runner 只傳入 with/without/eligible rows。
- `P3 Public cost accounting context seam`：新增 `scripts/bench/evidence_bundle_accounting.py`，集中計算 token/provider measured rates、wall/token/model-call ratios、paired cost ratios、prompt purity、retry cost share、valid comparison readiness 與 systemic regression flags；`capability_ab_runner.py::write_evidence_bundle` 只呼叫 `build_public_cost_accounting_context(...)` 並把結果交給 gate/payload assembly。
- `P3 Provider model-lock context seam`：新增 `scripts/bench/evidence_bundle_provider_context.py`，集中 `model_names`、with/without model set、same-model 判定與 model_lock env metadata；runner 保留 `_model_names` compatibility alias 並只把 `model_lock_context.model_lock` 放進 payload。
- `P3 Evidence bundle row-set context seam`：新增 `scripts/bench/evidence_bundle_rows.py`，集中 with/without rows 分組、eligible rows、row_counts 與 same-task-trials 判定；runner 保留 `_row_key_counts` compatibility alias，payload 直接使用 `row_sets.row_counts`。
- `P3 Evidence bundle manifest metadata seam`：新增 `scripts/bench/evidence_bundle_manifest.py`，集中 artifact file manifest、run identity、task manifest、timeouts 與 raw file manifest；runner 透過 injected sha/git/timeout helpers 呼叫，避免 metadata helper 自行讀寫 gate state。
- `P3 Evidence bundle header section seam`：`scripts/bench/evidence_bundle_payload.py` 新增 `build_evidence_bundle_header_section(...)`，集中 evidence bundle schema、created_at、run identity、model lock、task/taskset manifest、public disclosure default、timeout/raw/artifact file metadata 與 row counts placement；各 metadata value 仍由既有 manifest/context Modules 提供。
- `P3 Evidence bundle computed section seam`：`scripts/bench/evidence_bundle_payload.py` 新增 `build_evidence_bundle_computed_sections(...)`，集中已算好的 route cost、ROI shadow、infra/session、outbound prompt ledger、public lane contracts、S2T、product KPI 與 OpenSeeker alignment payload placement；各 report/contract value 仍由 runner 既有流程先計算，builder 不重算成本、路由或 public gate。
- `P3 Evidence bundle claim/posture section seam`：`scripts/bench/evidence_bundle_payload.py` 新增 `build_evidence_bundle_claim_posture_sections(...)`，集中已算好的 public claim gates、valid comparison readiness、direction magnitude、x3 promotion、mutation hardening、posture finalization、public claim posture 與 training eligibility posture placement；各 gate/posture decision 仍由既有 gate/posture Modules 先產生。
- `P3 Evidence bundle payload section seam`：`scripts/bench/evidence_bundle_payload.py` 新增 `build_telemetry_completeness_section(...)` 與 `build_nexus_wearing_context(...)`，把 telemetry completeness payload 與 Nexus wearing/system execution gate context 從 runner 內聯計算抽出；runner 保留 `nexus_valid_rate`、`local_reflex_verified_rate`、`nexus_system_execution_valid_rate` 等 gate builder 變數名稱，避免 public gate 語意漂移。
- `P3 Evidence bundle static gate section seam`：`scripts/bench/evidence_bundle_payload.py` 新增 `build_wall_ledger_conservation_section(...)` 與 `build_warning_clean_gate_section(...)`，只集中既有 payload schema/claim-boundary 字典組裝；wall telemetry evaluation、warning summarizer 與 gate invalid 判定仍由 runner 既有流程提供。
- `P3 Evidence bundle posture finalization section seam`：`scripts/bench/evidence_bundle_payload.py` 新增 `build_posture_finalization_gate_section(...)`，集中既有 `posture_finalization_gate` schema、training requirement list 與 public efficiency wording boolean；cost/sample/comparison inputs 仍由既有 gate/context flow 提供。
- `F01 Telemetry fidelity snapshot seam`：新增 `scripts/bench/evidence_bundle_fidelity.py`，提供 `extract_telemetry_fidelity_snapshot(payload)`；`tests/benchmark/test_telemetry_fidelity.py` 現在用固定 mock with/without rows 實際呼叫 `write_evidence_bundle(...)`，再比對 telemetry completeness、Nexus wearing、public gate checks、wall-ledger conservation 與 posture snapshot，避免後續 payload extraction 只靠欄位存在測試。
- `P3 Evidence bundle final payload assembly seam`：`scripts/bench/evidence_bundle_payload.py` 新增 `build_evidence_bundle_payload(...)`，集中 top-level section merge order；`capability_ab_runner.py::write_evidence_bundle` 只傳入已解析的 header、telemetry、rubric、wall-ledger、warning-clean、computed、Nexus wearing 與 claim/posture sections，避免 runner 繼續直接維護主 payload dict。
- `P4 CLI exception translation pregate`：新增 `scripts/engine/commands/exception_translation.py`，提供 `NexusCliActionError` 與 `translate_action_exceptions`；domain action error 會轉成 `click.ClickException`，`KeyboardInterrupt` / `click.Abort` / `SystemExit` 穿透，先建立 Action modules 的錯誤邊界，不拆 command body。
- `P4 Registry status Action extraction`：新增 `scripts/engine/commands/registry_actions.py`，把 `nexus registry status` 的 registry manifest 讀取與 output schema render 從 Click command body 抽出；`nexus_cli.py` 現在只保留 Click boundary、exception translation 與 echo formatting。
- `P4 Skills list Action extraction`：`scripts/engine/commands/registry_actions.py` 新增 skills list row normalization 與 table render，把 `nexus skills list` 的 registry 讀取與 fixed-width output schema 從 Click command body 抽出；`nexus skills sync` 仍保留原處，不碰寫入副作用。
- `P4 Skills sync Action extraction`：`scripts/engine/commands/registry_actions.py` 新增 `sync_external_skills` 與 sync completion renderer，把 `nexus skills sync` 的 `ExternalSkillLoader.sync_all()` 呼叫與 added/updated normalization 從 Click command body 抽出；副作用仍集中在 loader Adapter。
- `P4 Bench effort Action extraction`：新增 `scripts/engine/commands/bench_actions.py`，把 `nexus bench effort` 的 ROI report 讀取、typed row normalization 與 output schema render 從 Click command body 抽出；`nexus_cli.py` 保留 Click boundary 與 echo formatting。
- `P4 CodeIntel Action extraction`：新增 `scripts/engine/commands/code_actions.py`，把 `nexus code impact/scan/context` 的 CodeIntel adapter call、report path resolution、UTF-8 JSON write 與 text output schema 從 Click command body 抽出；`nexus_cli.py` 保留 Click options、JSON echo 與 exception translation。
- `P4 Multi-agent metrics Action extraction`：新增 `scripts/engine/commands/multi_agent_actions.py`，把 `nexus multi-agent metrics` 的 orchestrator metrics 讀取與 text output schema render 從 Click command body 抽出；JSON output 仍由 CLI boundary 負責序列化。
- `P4 Multi-agent status/audit Action extraction`：`scripts/engine/commands/multi_agent_actions.py` 新增 read-only task status/audit views，把 `nexus multi-agent status` 與 `nexus multi-agent audit` 的 state-store 讀取、JSON/text render decision、evidence-chain formatting 從 Click command body 抽出；避免碰 `submit` / `verify` / `integrate` 這些完成語義與副作用流程。
- `P4 Multi-agent verify/close Action extraction`：`scripts/engine/commands/multi_agent_actions.py` 新增 `verify_multi_agent_task`、`render_multi_agent_task_verification`、`close_multi_agent_task`，把 `nexus multi-agent verify` 與 `nexus multi-agent close` 的 orchestrator side-effect call 與 output schema 從 Click command body 抽出；測試使用 fake orchestrator，不觸發真 worktree/lock 操作。
- `P4 Multi-agent create/start/integrate Action extraction`：`scripts/engine/commands/multi_agent_actions.py` 新增 `create_multi_agent_task`、`start_multi_agent_task`、`integrate_multi_agent_tasks` 與對應 render views；Click command body 不再直接 import orchestrator / integration manager，所有 create/start/integrate side-effect calls 透過可注入 factory 驗證。
- `P4 Multi-agent submit Action extraction`：`scripts/engine/commands/multi_agent_actions.py` 新增 `submit_multi_agent_task` 與 `TaskSubmissionView`，把 verify gate、hallucination evidence load、delivery receipt assessment、governance event append、commit sha provider、delivery payload render 從 Click command body 抽出；測試用 fake orchestrator / fake receipt / fake governance appender / fake commit sha provider，保持 submission fail-closed。
- `P4 Learn converge Action extraction`：`scripts/engine/commands/learn_actions.py` 新增 `run_learn_converge` 與 `LearnConvergeResult`，把 service converge call、hallucination evidence write、hallucination gate、report write、text render schema 從 Click command body 抽出；CLI 保留 options 與 JSON/text echo。
- `P4 Learn ask Action extraction`：`scripts/engine/commands/learn_actions.py` 新增 `run_learn_ask` 與 `LearnAskResult`，把 service ask call、hallucination evidence write、hallucination gate、UNKNOWN/CONFLICT/answer render schema 從 Click command body 抽出；CLI 保留 options 與 JSON/text echo。
- `P4 Learn source lifecycle Action extraction`：`scripts/engine/commands/learn_actions.py` 新增 `run_learn_register_source`、`run_learn_refresh`、`run_learn_refresh_plan` 與 `verify_learn_source_lifecycle_completion`，把 service call、raw JSON report write、completion envelope finalization、completion verification seam、text render schema 從 Click command body 抽出；CLI 保留 options、JSON/text echo 與完成驗證呼叫順序。
- `P4 Learn phase report Action extraction`：`scripts/engine/commands/learn_actions.py` 新增 `run_learn_phase_slo`、`run_learn_phase_kpi` 與 `verify_learn_phase_report_completion`，把 phase SLO/KPI service call、raw JSON report write、completion envelope finalization、completion verification seam、text render schema 從 Click command body 抽出；CLI 保留 options 與 JSON/text echo。
- `P4 Learn report/ingest/gate Action extraction`：`scripts/engine/commands/learn_actions.py` 新增 `run_learn_report`、`run_learn_ingest`、`run_learn_gate`、semantic contract enforcers 與 gate command runner seam；dual-gate markdown、hallucination evidence/gate、raw report write、threshold gate、acceptance/contract/CI subprocess command construction 均離開 Click command body，CLI 保留 options 與 render/echo 順序。
- `P4 Research route/session Action extraction`：新增 `scripts/engine/commands/research_actions.py` 與 `run_research_route` / research session Actions，把 `research:route` 的 route builder call、optional capability planner、learning policy budget load、route decision build/write、summary/explanation render schema，以及 `research:onboarding` / `research:recommend-next` / `research:packet` / `research:log-from-last` / `research:finalize-preview` / `research:writeback-lessons` / `research:human-report` 的 session service call、JSON read、human report write 從 Click command body 抽出；CLI 保留 options、JSON/text echo 與 warning color rendering。
- `P4 Research auto-flow Action extraction`：`scripts/engine/commands/research_actions.py` 新增 `run_research_auto_flow`、`run_research_auto_flow_route_explanation`、renderers 與 injectable auto-flow/preflight/session/completion seams；`nexus_cli.py::research_auto_flow` 降為 Click parsing、JSON/text echo 與 exit-code adapter。preflight block、completion envelope、report write、completion handoff 由 Action module 擁有。
- `P4 Research run Action extraction`：`scripts/engine/commands/research_actions.py` 新增 `run_research_run`、`ResearchRunResult` 與 renderer，把 `research:run` 的 governance guards、scheduler/evaluator/selector candidate lifecycle、retention、metabolism persistence、completion envelope、continuation command、handoff/report write 從 Click command body 抽出；CLI 降為 Click parsing、JSON echo 與 exit-code adapter。
- `P4 Learn read-only Action extraction`：新增 `scripts/engine/commands/learn_actions.py`，把 `nexus learn:phase-policy` 與 `nexus learn:scheduler-status` 的讀取/推導邏輯與 text output schema render 從 Click command body 抽出；scheduler report JSON 讀取改為明確 `encoding="utf-8"`。
- `P4 Learn benchmark Action extraction`：`scripts/engine/commands/learn_actions.py` 新增 `run_learn_precision_benchmark`、output writer 與 completion renderer，把 `nexus learn:benchmark` 的 manifest parsing、LearnModeService ask loop、precision/unknown metrics 與 JSON write contract 從 Click command body 抽出；legacy `source` / `source-file` 仍保持忽略語義。
- `P4 Sandbox run Action extraction`：新增 `scripts/engine/commands/sandbox_actions.py`，把 `nexus sandbox run` 的 runner dispatch 與 success output schema 從 Click command body 抽出；CLI adapter 只保留 Click option parsing、exception translation 與 echo formatting。後續已補 `SandboxRunner.run_task(...)` 本地 physical contract，Action 對缺少 explicit command 仍 fail-closed，不假造 sandbox success。
- `P5 Route-cost policy matcher extraction`：新增 `nexus/engine/route_cost_policy_matcher.py`，把 feature-rule matching 與 controls extraction 從 `learning_policy_loader.py` 抽出；loader 保留 underscored import aliases，store/env/S2T I/O 不變。
- `P5 Expected-capability policy extraction`：新增 `nexus/engine/expected_capability_policy.py`，把 expected-capability normalization、executor flags、receipt-lite lane allowance、candidate factory protection、baseline protection 從 `learning_policy_loader.py` 抽出；loader 保留原 public function import aliases。
- `P5 S2T policy loader extraction`：新增 `nexus/engine/s2t_policy_loader.py`，把 S2T draft schema parsing、promotion gate、runtime merge 從 `learning_policy_loader.py` 抽出；loader 保留 `load_s2t_policy_draft_budget`、`merge_runtime_s2t_policy_draft`、`DEFAULT_S2T_POLICY_DRAFT_PATH` aliases。

本輪驗證：

- P4 sandbox run 初次 RED：`tests/engine/test_sandbox_actions.py` 匯入 `scripts.engine.commands.sandbox_actions` 失敗，證明 `sandbox_run_cmd` runner dispatch 與 output schema 仍留在 Click command body。
- 修正：新增 `SandboxRunResult`、`run_sandbox_task(...)` 與 `render_sandbox_run_result(...)`；`nexus_cli.py::sandbox_run_cmd` 降為 thin adapter 並套 `translate_action_exceptions`。後續 `SandboxRunner.run_task(...)` 補上本地 workspace copy / command / cwd / output / cleanup / timeout / exit semantics；無 explicit command 與 path escape 仍 fail-closed。
- `uv run pytest tests/engine/test_sandbox_actions.py -q` -> `3 passed` after sandbox run Action extraction.
- `uv run pytest tests/ops/test_ci_gate_report_trust_audit.py tests/benchmark/test_telemetry_fidelity.py -q` -> `19 passed`
- `uv run python -c "from scripts.ops.ci_gate import run_focused_nodeid_contract_check; raise SystemExit(0 if run_focused_nodeid_contract_check() else 1)"` -> focused nodeid contract `PASSED`
- `uv run scripts/ops/ci_gate.py --changed-only scripts/ops/ci_gate.py tests/ops/test_ci_gate_report_trust_audit.py tests/benchmark/test_telemetry_fidelity.py` -> changed-only gate `PASSED`
- `uv run pytest tests/ops/test_select_tests.py -q` -> `13 passed`
- `uv run pytest tests/app/test_research_flow_service.py::test_codeintel_context_helpers_keep_research_flow_facade_aliases tests/app/test_research_flow_service.py::test_codeintel_context_is_injected_into_task_text tests/app/test_research_flow_service.py::test_codeintel_context_compact_mode_keeps_evidence_but_trims_payload tests/app/test_research_flow_service.py::test_codeintel_dci_runs_only_for_evidence_heavy_lane -q` -> `4 passed`
- `uv run pytest tests/app/test_research_flow_service.py -q` -> `102 passed`
- `uv run scripts/ops/ci_gate.py --changed-only nexus/research/flow/codeintel_context.py nexus/app/research_flow_service.py tests/app/test_research_flow_service.py docs/testing/test_impact_map.md` -> changed-only gate `PASSED`
- `uv run pytest tests/ops/test_select_tests.py tests/ops/test_ci_gate_report_trust_audit.py tests/benchmark/test_telemetry_fidelity.py -q` -> `32 passed`
- `uv run pytest tests/ops/test_strict_file_discovery.py tests/ops/test_strategic_map_audit.py -q` -> `7 passed`
- `uv run scripts/ops/ci_gate.py --changed-only scripts/ops/strict_file_discovery.py scripts/ops/strategic_map_audit.py tests/ops/test_strict_file_discovery.py docs/testing/test_impact_map.md` -> changed-only gate `PASSED`
- `uv run pytest tests/ops/test_golden_schema_snapshots.py tests/ops/test_ci_gate_report_trust_audit.py -q` -> `20 passed`
- `uv run scripts/ops/check_golden_schema_snapshots.py` -> `status=PASS`
- `uv run scripts/ops/ci_gate.py --changed-only scripts/ops/check_golden_schema_snapshots.py docs/testing/golden_schemas/manifest.json docs/testing/golden_schemas/telemetry_fidelity_snapshot.v1.json tests/ops/test_golden_schema_snapshots.py scripts/ops/ci_gate.py tests/ops/test_ci_gate_report_trust_audit.py docs/testing/test_impact_map.md` -> changed-only gate `PASSED`
- `uv run pytest tests/app/test_research_flow_service.py tests/benchmark/test_telemetry_fidelity.py tests/ops/test_select_tests.py tests/ops/test_ci_gate_report_trust_audit.py tests/ops/test_strict_file_discovery.py tests/ops/test_strategic_map_audit.py tests/ops/test_golden_schema_snapshots.py -q` -> `145 passed`
- `uv run scripts/ops/ci_gate.py --changed-only scripts/ops/ci_gate.py scripts/ops/check_golden_schema_snapshots.py scripts/ops/strict_file_discovery.py scripts/ops/strategic_map_audit.py nexus/app/research_flow_service.py nexus/research/flow/codeintel_context.py docs/testing/test_impact_map.md docs/testing/golden_schemas/manifest.json docs/testing/golden_schemas/telemetry_fidelity_snapshot.v1.json tests/app/test_research_flow_service.py tests/benchmark/test_telemetry_fidelity.py tests/ops/test_ci_gate_report_trust_audit.py tests/ops/test_strict_file_discovery.py tests/ops/test_strategic_map_audit.py tests/ops/test_golden_schema_snapshots.py` -> changed-only gate `PASSED`
- `uv run pytest tests/benchmark/test_fixture_materialization.py tests/benchmark/test_capability_ab_runner.py::test_materialize_fixture_writes_files tests/benchmark/test_capability_ab_runner.py::test_materialize_nexus_value_fixture_uses_fixture_kind tests/benchmark/test_capability_ab_runner.py::test_materialize_model_required_named_fixtures_write_visible_and_hidden_contracts tests/benchmark/test_capability_ab_runner.py::test_materialize_all_nexus_value_manifest_fixtures_are_distinct tests/benchmark/test_capability_ab_runner.py::test_public_candidate_fixtures_have_distinct_visible_and_hidden_tests tests/benchmark/test_capability_ab_runner.py::test_route_oracle_fixtures_have_hidden_capability_conditions -q` -> `9 passed`
- `uv run scripts/ops/ci_gate.py --changed-only scripts/bench/fixture_materialization.py scripts/bench/capability_ab_runner.py tests/benchmark/test_fixture_materialization.py docs/testing/test_impact_map.md` -> changed-only gate `PASSED`
- `uv run pytest tests/benchmark/test_capability_ab_runner.py -q` -> `340 passed`
- `uv run pytest tests/benchmark/test_fixture_materialization.py tests/benchmark/test_capability_ab_runner.py::test_materialize_nexus_value_fixture_uses_fixture_kind tests/benchmark/test_capability_ab_runner.py::test_public_candidate_fixtures_have_distinct_visible_and_hidden_tests tests/benchmark/test_capability_ab_runner.py::test_route_oracle_fixtures_have_hidden_capability_conditions -q` -> `8 passed`
- `uv run pytest tests/benchmark/test_capability_ab_runner.py -q` -> `340 passed` after split seam move
- `uv run scripts/ops/ci_gate.py --changed-only scripts/bench/fixture_materialization.py scripts/bench/capability_ab_runner.py tests/benchmark/test_fixture_materialization.py docs/testing/test_impact_map.md` -> changed-only gate `PASSED` after split seam move
- `python3 -m py_compile scripts/bench/capability_ab_runner.py scripts/bench/fixture_materialization.py` -> compile `PASSED`
- `uv run pytest tests/benchmark/test_capability_ab_runner.py -q` -> `340 passed` after physical legacy cleanup
- `uv run scripts/ops/ci_gate.py --changed-only scripts/bench/fixture_materialization.py scripts/bench/capability_ab_runner.py tests/benchmark/test_fixture_materialization.py docs/testing/test_impact_map.md` -> changed-only gate `PASSED` after physical legacy cleanup
- `uv run pytest tests/benchmark/test_fixture_materialization.py tests/benchmark/test_capability_ab_runner.py::test_materialize_fixture_writes_files tests/benchmark/test_capability_ab_runner.py::test_public_candidate_fixtures_have_distinct_visible_and_hidden_tests -q` -> `8 passed` after external adapter seam
- `uv run pytest tests/benchmark/test_capability_ab_runner.py -q` -> `340 passed` after external adapter seam
- `uv run scripts/ops/ci_gate.py --changed-only scripts/bench/fixture_materialization.py scripts/bench/capability_ab_runner.py tests/benchmark/test_fixture_materialization.py docs/testing/test_impact_map.md` -> changed-only gate `PASSED` after external adapter seam
- `python3 -m py_compile scripts/bench/capability_ab_runner.py scripts/bench/fixture_materialization.py` -> compile `PASSED` after source selection extraction
- `uv run pytest tests/benchmark/test_fixture_materialization.py -q` -> `8 passed`
- `uv run pytest tests/benchmark/test_capability_ab_runner.py::test_materialize_nexus_value_fixture_uses_fixture_kind tests/benchmark/test_capability_ab_runner.py::test_materialize_model_required_named_fixtures_write_visible_and_hidden_contracts tests/benchmark/test_capability_ab_runner.py::test_public_candidate_fixtures_have_distinct_visible_and_hidden_tests tests/benchmark/test_capability_ab_runner.py::test_route_oracle_fixtures_have_hidden_capability_conditions -q` -> `4 passed`
- `uv run pytest tests/benchmark/test_capability_ab_runner.py -q` -> `340 passed` after fixture source selection extraction
- `uv run scripts/ops/ci_gate.py --changed-only scripts/bench/fixture_materialization.py scripts/bench/capability_ab_runner.py tests/benchmark/test_fixture_materialization.py docs/testing/test_impact_map.md` -> changed-only gate `PASSED` after fixture source selection extraction
- `python3 -m py_compile scripts/bench/runner_socket_barrier.py` -> compile `PASSED`
- `uv run pytest tests/benchmark/test_runner_socket_barrier.py -q` -> `3 passed`
- `uv run scripts/ops/ci_gate.py --changed-only scripts/bench/runner_socket_barrier.py tests/benchmark/test_runner_socket_barrier.py docs/testing/test_impact_map.md` -> changed-only gate `PASSED`
- `python3 -m py_compile scripts/bench/capability_ab_runner.py scripts/bench/provider_failure_policy.py` -> compile `PASSED`
- `uv run pytest tests/benchmark/test_provider_failure_policy.py tests/benchmark/test_capability_ab_runner.py::test_per_task_stop_loss_marks_row_infra_invalid tests/benchmark/test_capability_ab_runner.py::test_per_task_stop_loss_allows_rows_within_budget tests/benchmark/test_capability_ab_runner.py::test_direct_timeout_abort_triggers_only_after_consecutive_without_timeouts tests/benchmark/test_capability_ab_runner.py::test_direct_infra_abort_triggers_on_consecutive_infra_invalid_rows -q` -> `9 passed`
- `uv run scripts/ops/ci_gate.py --changed-only scripts/bench/provider_failure_policy.py scripts/bench/capability_ab_runner.py tests/benchmark/test_provider_failure_policy.py docs/testing/test_impact_map.md` -> changed-only gate `PASSED`
- `uv run pytest tests/benchmark/test_capability_ab_runner.py -q` -> `340 passed` after direct provider failure policy extraction
- `uv run scripts/ops/ci_gate.py --changed-only scripts/bench/fixture_materialization.py scripts/bench/runner_socket_barrier.py scripts/bench/provider_failure_policy.py scripts/bench/capability_ab_runner.py tests/benchmark/test_fixture_materialization.py tests/benchmark/test_runner_socket_barrier.py tests/benchmark/test_provider_failure_policy.py docs/testing/test_impact_map.md docs/plans/NEXUS_CLEAN_CODE_LINUS_REFACTOR_PLAN_2026-05-22.md` -> combined changed-only gate `PASSED` after adding plan impact-map row
- `uv run scripts/ops/ci_gate.py` -> `ALL QUALITY GATES PASSED`
- `python3 -m py_compile scripts/engine/commands/exception_translation.py` -> compile `PASSED`
- `uv run pytest tests/engine/test_cli_exception_translation.py -q` -> `5 passed`
- `uv run scripts/ops/ci_gate.py --changed-only scripts/engine/commands/exception_translation.py tests/engine/test_cli_exception_translation.py docs/testing/test_impact_map.md` -> changed-only gate `PASSED`
- `uv run scripts/ops/ci_gate.py` -> `ALL QUALITY GATES PASSED` after P4 exception pregate
- `python3 -m py_compile nexus/engine/learning_policy_loader.py nexus/engine/route_cost_policy_matcher.py` -> compile `PASSED`
- `uv run pytest tests/engine/test_route_cost_policy_matcher.py tests/engine/test_capability_planner.py::test_route_cost_policy_loader_applies_feature_rules_without_task_id tests/engine/test_capability_planner.py::test_route_cost_policy_loader_can_match_local_reflex_features tests/engine/test_learning_policy_store.py -q` -> `6 passed`
- `uv run scripts/ops/ci_gate.py --changed-only nexus/engine/route_cost_policy_matcher.py nexus/engine/learning_policy_loader.py tests/engine/test_route_cost_policy_matcher.py docs/testing/test_impact_map.md` -> changed-only gate `PASSED` after adding `learning_policy_loader.py` impact-map row
- `uv run scripts/ops/ci_gate.py` -> `ALL QUALITY GATES PASSED` after P5 matcher extraction
- `python3 -m py_compile nexus/engine/learning_policy_loader.py nexus/engine/expected_capability_policy.py` -> compile `PASSED`
- `uv run pytest tests/engine/test_expected_capability_policy.py tests/engine/test_capability_planner.py::test_route_cost_controls_enable_gate_only_receipt_lite_for_governance_lane tests/engine/test_capability_planner.py::test_route_cost_controls_protect_expected_capabilities_from_cost_slimming tests/engine/test_capability_planner.py::test_route_cost_controls_keep_model_path_for_non_receipt_lite_expected_capabilities tests/engine/test_learning_policy_store.py -q` -> `9 passed`
- `uv run scripts/ops/ci_gate.py --changed-only nexus/engine/expected_capability_policy.py nexus/engine/learning_policy_loader.py tests/engine/test_expected_capability_policy.py docs/testing/test_impact_map.md` -> changed-only gate `PASSED`
- `uv run scripts/ops/ci_gate.py` -> `ALL QUALITY GATES PASSED` after P5 expected-capability extraction
- `python3 -m py_compile nexus/engine/learning_policy_loader.py nexus/engine/s2t_policy_loader.py` -> compile `PASSED`
- `uv run pytest tests/engine/test_s2t_policy_loader.py tests/engine/test_capability_planner.py::test_s2t_policy_draft_loader_feeds_shadow_scoring_without_runtime_promotion tests/engine/test_capability_planner.py::test_s2t_policy_draft_promoted_runtime_requires_gate tests/engine/test_capability_planner.py::test_s2t_policy_draft_promoted_runtime_can_downgrade_costly_non_floor_caps tests/engine/test_learning_policy_store.py -q` -> `8 passed`
- `uv run scripts/ops/ci_gate.py --changed-only nexus/engine/s2t_policy_loader.py nexus/engine/learning_policy_loader.py tests/engine/test_s2t_policy_loader.py docs/testing/test_impact_map.md` -> changed-only gate `PASSED`
- `uv run scripts/ops/ci_gate.py` -> `ALL QUALITY GATES PASSED` after P5 S2T loader extraction
- `git diff --check -- .gitattributes docs/plans/NEXUS_CLEAN_CODE_LINUS_REFACTOR_PLAN_2026-05-22.md docs/testing/test_impact_map.md nexus/engine/learning_policy_loader.py nexus/engine/expected_capability_policy.py nexus/engine/s2t_policy_loader.py tests/engine/test_expected_capability_policy.py tests/engine/test_s2t_policy_loader.py` -> diff hygiene `PASSED`
- `uv run scripts/ops/ci_gate.py` -> `ALL QUALITY GATES PASSED` after P5 verification refresh
- `python3 -m py_compile scripts/engine/nexus_cli.py scripts/engine/commands/registry_actions.py tests/engine/test_registry_actions.py` -> compile `PASSED`
- `uv run pytest tests/engine/test_registry_actions.py tests/engine/test_cli_exception_translation.py tests/engine/test_nexus_cli_registry.py -q` -> `12 passed`
- `uv run scripts/ops/ci_gate.py --changed-only scripts/engine/commands/registry_actions.py scripts/engine/nexus_cli.py tests/engine/test_registry_actions.py docs/testing/test_impact_map.md` -> changed-only gate `PASSED`
- `uv run scripts/ops/ci_gate.py` -> `ALL QUALITY GATES PASSED` after P4 registry Action extraction
- `python3 -m py_compile scripts/engine/nexus_cli.py scripts/engine/commands/bench_actions.py tests/engine/test_bench_actions.py` -> compile `PASSED`
- `uv run pytest tests/engine/test_bench_actions.py tests/engine/test_registry_actions.py tests/engine/test_cli_exception_translation.py -q` -> `13 passed`
- `uv run scripts/ops/ci_gate.py --changed-only scripts/engine/commands/bench_actions.py scripts/engine/nexus_cli.py tests/engine/test_bench_actions.py docs/testing/test_impact_map.md` -> changed-only gate `PASSED`
- `uv run scripts/ops/ci_gate.py` -> `ALL QUALITY GATES PASSED` after P4 bench Action extraction
- `python3 -m py_compile scripts/engine/nexus_cli.py scripts/engine/commands/multi_agent_actions.py tests/engine/test_multi_agent_actions.py` -> compile `PASSED`
- `uv run pytest tests/engine/test_multi_agent_actions.py tests/engine/test_bench_actions.py tests/engine/test_registry_actions.py tests/engine/test_cli_exception_translation.py -q` -> `18 passed`
- `uv run scripts/ops/ci_gate.py --changed-only scripts/engine/commands/multi_agent_actions.py scripts/engine/nexus_cli.py tests/engine/test_multi_agent_actions.py docs/testing/test_impact_map.md` -> changed-only gate `PASSED`
- `uv run scripts/ops/ci_gate.py` -> `ALL QUALITY GATES PASSED` after P4 multi-agent metrics Action extraction
- `python3 -m py_compile scripts/bench/capability_ab_runner.py scripts/bench/evidence_artifacts.py tests/benchmark/test_evidence_artifacts.py` -> compile `PASSED`
- `uv run pytest tests/benchmark/test_evidence_artifacts.py tests/benchmark/test_capability_ab_runner.py::test_write_trial_evidence_and_bundle -q` -> `3 passed`
- `uv run scripts/ops/ci_gate.py --changed-only scripts/bench/evidence_artifacts.py scripts/bench/capability_ab_runner.py tests/benchmark/test_evidence_artifacts.py docs/testing/test_impact_map.md` -> changed-only gate `PASSED`
- `uv run scripts/ops/ci_gate.py` -> `ALL QUALITY GATES PASSED` after P3 trial evidence artifact writer extraction
- `python3 -m py_compile scripts/engine/nexus_cli.py scripts/engine/commands/learn_actions.py tests/engine/test_learn_actions.py` -> compile `PASSED`
- `uv run pytest tests/engine/test_learn_actions.py tests/engine/test_multi_agent_actions.py tests/engine/test_bench_actions.py tests/engine/test_registry_actions.py tests/engine/test_cli_exception_translation.py -q` -> `26 passed`
- `uv run scripts/ops/ci_gate.py --changed-only scripts/engine/commands/learn_actions.py scripts/engine/nexus_cli.py tests/engine/test_learn_actions.py docs/testing/test_impact_map.md` -> changed-only gate `PASSED`
- `uv run scripts/ops/ci_gate.py --changed-only scripts/engine/commands/learn_actions.py scripts/engine/nexus_cli.py tests/engine/test_learn_actions.py docs/testing/test_impact_map.md docs/plans/NEXUS_CLEAN_CODE_LINUS_REFACTOR_PLAN_2026-05-22.md` -> changed-only gate `PASSED`
- `uv run scripts/ops/ci_gate.py` -> `ALL QUALITY GATES PASSED` after P4 learn read-only Action extraction
- `python3 -m py_compile scripts/engine/nexus_cli.py scripts/engine/commands/multi_agent_actions.py tests/engine/test_multi_agent_actions.py` -> compile `PASSED` after P4 multi-agent status/audit Action extraction
- `uv run pytest tests/engine/test_multi_agent_actions.py tests/engine/test_cli_exception_translation.py -q` -> `19 passed`
- `uv run scripts/ops/ci_gate.py --changed-only scripts/engine/commands/multi_agent_actions.py scripts/engine/nexus_cli.py tests/engine/test_multi_agent_actions.py docs/testing/test_impact_map.md` -> changed-only gate `PASSED`
- `uv run scripts/ops/ci_gate.py --changed-only scripts/engine/commands/multi_agent_actions.py scripts/engine/nexus_cli.py tests/engine/test_multi_agent_actions.py docs/testing/test_impact_map.md docs/plans/NEXUS_CLEAN_CODE_LINUS_REFACTOR_PLAN_2026-05-22.md` -> changed-only gate `PASSED`
- `uv run scripts/ops/ci_gate.py` -> `ALL QUALITY GATES PASSED` after P4 multi-agent status/audit Action extraction
- `python3 -m py_compile scripts/engine/nexus_cli.py scripts/engine/commands/registry_actions.py tests/engine/test_registry_actions.py` -> compile `PASSED` after P4 skills list Action extraction
- `uv run pytest tests/engine/test_registry_actions.py tests/engine/test_cli_exception_translation.py -q` -> `13 passed`
- `uv run scripts/ops/ci_gate.py --changed-only scripts/engine/commands/registry_actions.py scripts/engine/nexus_cli.py tests/engine/test_registry_actions.py docs/testing/test_impact_map.md` -> changed-only gate `PASSED`
- `uv run scripts/ops/ci_gate.py --changed-only scripts/engine/commands/registry_actions.py scripts/engine/nexus_cli.py tests/engine/test_registry_actions.py docs/testing/test_impact_map.md docs/plans/NEXUS_CLEAN_CODE_LINUS_REFACTOR_PLAN_2026-05-22.md` -> changed-only gate `PASSED`
- `uv run scripts/ops/ci_gate.py` -> `ALL QUALITY GATES PASSED` after P4 skills list Action extraction
- `python3 -m py_compile scripts/engine/nexus_cli.py scripts/engine/commands/learn_actions.py tests/engine/test_learn_actions.py` -> compile `PASSED` after P4 learn benchmark Action extraction
- `uv run pytest tests/engine/test_learn_actions.py tests/engine/test_cli_exception_translation.py -q` -> `17 passed`
- `uv run scripts/ops/ci_gate.py --changed-only scripts/engine/commands/learn_actions.py scripts/engine/nexus_cli.py tests/engine/test_learn_actions.py docs/testing/test_impact_map.md` -> changed-only gate `PASSED`
- `uv run pytest tests/engine/test_cli_artifact_gate_audit.py tests/engine/test_learn_actions.py -q` -> `15 passed` after artifact audit update
- `uv run pytest tests/ops/test_select_tests.py tests/ops/test_ci_gate_report_trust_audit.py::test_focused_nodeids_from_impact_map_reads_active_nodeids tests/engine/test_cli_artifact_gate_audit.py tests/engine/test_learn_actions.py -q` -> `29 passed` after Learning Closure impact-map row
- `uv run scripts/ops/ci_gate.py --changed-only tests/engine/test_cli_artifact_gate_audit.py scripts/engine/commands/learn_actions.py scripts/engine/nexus_cli.py tests/engine/test_learn_actions.py docs/testing/test_impact_map.md "nexus_wiki_vault/06_Ops/Ops - Learning Closure Matrix.md"` -> changed-only gate `PASSED`
- `uv run scripts/ops/ci_gate.py` -> `ALL QUALITY GATES PASSED` after P4 learn benchmark Action extraction and audit repair
- `python3 -m py_compile scripts/bench/runner_socket_barrier.py scripts/bench/capability_ab_runner.py tests/benchmark/test_runner_socket_barrier.py tests/benchmark/test_capability_ab_runner.py` -> compile `PASSED`
- `uv run pytest tests/benchmark/test_runner_socket_barrier.py tests/benchmark/test_capability_ab_runner.py::test_run_without_nexus_direct_provider_socket_barrier_blocks_external_python_socket -q` -> `6 passed`
- `uv run pytest tests/ops/test_select_tests.py tests/ops/test_ci_gate_report_trust_audit.py::test_focused_nodeids_from_impact_map_reads_active_nodeids tests/benchmark/test_runner_socket_barrier.py tests/benchmark/test_capability_ab_runner.py::test_run_without_nexus_direct_provider_socket_barrier_blocks_external_python_socket -q` -> `20 passed`
- `uv run scripts/ops/ci_gate.py --changed-only scripts/bench/runner_socket_barrier.py scripts/bench/capability_ab_runner.py tests/benchmark/test_runner_socket_barrier.py tests/benchmark/test_capability_ab_runner.py docs/testing/test_impact_map.md "nexus_wiki_vault/06_Ops/Ops - Learning Closure Matrix.md"` -> changed-only gate `PASSED`
- `uv run scripts/ops/ci_gate.py` -> `ALL QUALITY GATES PASSED` after P3 socket barrier integration
- `python3 -m py_compile scripts/engine/nexus_cli.py scripts/engine/commands/registry_actions.py tests/engine/test_registry_actions.py` -> compile `PASSED` after P4 skills sync Action extraction
- `uv run pytest tests/engine/test_registry_actions.py tests/engine/test_cli_exception_translation.py -q` -> `17 passed`
- `uv run scripts/ops/ci_gate.py --changed-only scripts/engine/commands/registry_actions.py scripts/engine/nexus_cli.py tests/engine/test_registry_actions.py docs/testing/test_impact_map.md` -> changed-only gate `PASSED`
- `uv run pytest tests/benchmark/test_direct_provider_runner.py -q` -> initial red `ModuleNotFoundError: No module named 'scripts.bench.direct_provider_runner'`
- `python3 -m py_compile scripts/bench/direct_provider_runner.py scripts/bench/capability_ab_runner.py tests/benchmark/test_direct_provider_runner.py` -> compile `PASSED`
- `uv run pytest tests/benchmark/test_direct_provider_runner.py -q` -> `4 passed`
- `uv run pytest tests/benchmark/test_direct_provider_runner.py tests/benchmark/test_capability_ab_runner.py::test_run_without_nexus_gemini_mode_uses_direct_flash_baseline tests/benchmark/test_capability_ab_runner.py::test_run_without_nexus_codex_mode_uses_direct_codex_baseline tests/benchmark/test_capability_ab_runner.py::test_run_without_nexus_hidden_verifier_omits_tests_from_prompt tests/benchmark/test_capability_ab_runner.py::test_run_without_nexus_hidden_verifier_omits_rlm_harder_tests tests/benchmark/test_capability_ab_runner.py::test_run_without_nexus_session_worker_records_row_metadata tests/benchmark/test_capability_ab_runner.py::test_run_without_nexus_direct_provider_socket_barrier_blocks_external_python_socket -q` -> `10 passed`
- `uv run pytest tests/benchmark/test_direct_provider_runner.py -q` -> initial red `ImportError: cannot import name 'normalize_direct_provider_response'`
- `python3 -m py_compile scripts/bench/direct_provider_runner.py scripts/bench/capability_ab_runner.py tests/benchmark/test_direct_provider_runner.py` -> compile `PASSED` after response normalization extraction
- `uv run pytest tests/benchmark/test_direct_provider_runner.py -q` -> `7 passed`
- `uv run pytest tests/benchmark/test_direct_provider_runner.py tests/benchmark/test_capability_ab_runner.py::test_run_without_nexus_gemini_mode_uses_direct_flash_baseline tests/benchmark/test_capability_ab_runner.py::test_run_without_nexus_codex_mode_uses_direct_codex_baseline tests/benchmark/test_capability_ab_runner.py::test_run_without_nexus_gemini_quota_is_infra_invalid tests/benchmark/test_capability_ab_runner.py::test_run_without_nexus_gemini_timeout_before_response_is_recorded tests/benchmark/test_capability_ab_runner.py::test_run_without_nexus_session_worker_records_row_metadata -q` -> `12 passed`
- `uv run pytest tests/engine/test_code_actions.py -q` -> initial red `ModuleNotFoundError: No module named 'scripts.engine.commands.code_actions'`
- `python3 -m py_compile scripts/engine/commands/code_actions.py scripts/engine/nexus_cli.py tests/engine/test_code_actions.py` -> compile `PASSED`
- `uv run pytest tests/engine/test_code_actions.py -q` -> `4 passed`
- `uv run pytest tests/engine/test_code_actions.py tests/test_cli_commands.py tests/test_cli_learn_mode.py -q` -> `57 passed`
- `uv run scripts/ops/ci_gate.py --changed-only scripts/bench/direct_provider_runner.py scripts/bench/capability_ab_runner.py tests/benchmark/test_direct_provider_runner.py tests/benchmark/test_capability_ab_runner.py scripts/engine/commands/code_actions.py scripts/engine/nexus_cli.py tests/engine/test_code_actions.py docs/testing/test_impact_map.md docs/plans/NEXUS_CLEAN_CODE_LINUS_REFACTOR_PLAN_2026-05-22.md "nexus_wiki_vault/06_Ops/Ops - Learning Closure Matrix.md"` -> changed-only gate `PASSED`
- `git diff --check -- scripts/bench/direct_provider_runner.py scripts/bench/capability_ab_runner.py tests/benchmark/test_direct_provider_runner.py scripts/engine/commands/code_actions.py scripts/engine/nexus_cli.py tests/engine/test_code_actions.py docs/testing/test_impact_map.md docs/plans/NEXUS_CLEAN_CODE_LINUS_REFACTOR_PLAN_2026-05-22.md "nexus_wiki_vault/06_Ops/Ops - Learning Closure Matrix.md"` -> diff hygiene `PASSED`
- `uv run scripts/ops/ci_gate.py` -> `ALL QUALITY GATES PASSED` after P3 direct-provider prompt/response seam and P4 CodeIntel Action extraction
- `uv run pytest tests/benchmark/test_direct_provider_runner.py -q` -> initial red `ImportError: cannot import name 'run_direct_provider_attempts'`
- `python3 -m py_compile scripts/bench/direct_provider_runner.py scripts/bench/capability_ab_runner.py tests/benchmark/test_direct_provider_runner.py` -> compile `PASSED` after direct invocation retry seam
- `uv run pytest tests/benchmark/test_direct_provider_runner.py -q` -> `10 passed`
- `uv run pytest tests/benchmark/test_direct_provider_runner.py tests/benchmark/test_capability_ab_runner.py::test_run_without_nexus_gemini_mode_uses_direct_flash_baseline tests/benchmark/test_capability_ab_runner.py::test_run_without_nexus_codex_mode_uses_direct_codex_baseline tests/benchmark/test_capability_ab_runner.py::test_run_without_nexus_retries_direct_gemini_cli_error_without_tokens tests/benchmark/test_capability_ab_runner.py::test_run_without_nexus_resets_direct_gemini_invalid_session_before_retry tests/benchmark/test_capability_ab_runner.py::test_run_without_nexus_gemini_timeout_before_response_is_recorded tests/benchmark/test_capability_ab_runner.py::test_run_without_nexus_direct_provider_socket_barrier_blocks_external_python_socket -q` -> `16 passed`
- `uv run scripts/ops/ci_gate.py --changed-only scripts/bench/direct_provider_runner.py scripts/bench/capability_ab_runner.py tests/benchmark/test_direct_provider_runner.py tests/benchmark/test_capability_ab_runner.py docs/testing/test_impact_map.md docs/plans/NEXUS_CLEAN_CODE_LINUS_REFACTOR_PLAN_2026-05-22.md` -> changed-only gate `PASSED`
- `git diff --check -- scripts/bench/direct_provider_runner.py scripts/bench/capability_ab_runner.py tests/benchmark/test_direct_provider_runner.py docs/testing/test_impact_map.md docs/plans/NEXUS_CLEAN_CODE_LINUS_REFACTOR_PLAN_2026-05-22.md` -> diff hygiene `PASSED`
- `uv run scripts/ops/ci_gate.py` -> `ALL QUALITY GATES PASSED` after P3 direct invocation retry seam
- `uv run pytest tests/benchmark/test_with_nexus_runner.py -q` -> initial red `ModuleNotFoundError: No module named 'scripts.bench.with_nexus_runner'`
- `python3 -m py_compile scripts/bench/with_nexus_runner.py scripts/bench/capability_ab_runner.py tests/benchmark/test_with_nexus_runner.py` -> compile `PASSED`
- `uv run pytest tests/benchmark/test_with_nexus_runner.py -q` -> `2 passed`
- `uv run pytest tests/benchmark/test_with_nexus_runner.py tests/benchmark/test_capability_ab_runner.py::test_run_with_nexus_subprocess_preserves_executor_receipts_without_llm -q` -> `3 passed`
- `uv run scripts/ops/ci_gate.py --changed-only scripts/bench/with_nexus_runner.py scripts/bench/capability_ab_runner.py tests/benchmark/test_with_nexus_runner.py tests/benchmark/test_capability_ab_runner.py docs/testing/test_impact_map.md docs/plans/NEXUS_CLEAN_CODE_LINUS_REFACTOR_PLAN_2026-05-22.md` -> changed-only gate `PASSED`
- `git diff --check -- scripts/bench/direct_provider_runner.py scripts/bench/with_nexus_runner.py scripts/bench/capability_ab_runner.py tests/benchmark/test_direct_provider_runner.py tests/benchmark/test_with_nexus_runner.py docs/testing/test_impact_map.md docs/plans/NEXUS_CLEAN_CODE_LINUS_REFACTOR_PLAN_2026-05-22.md` -> diff hygiene `PASSED`
- `uv run scripts/ops/ci_gate.py` -> `ALL QUALITY GATES PASSED` after P3 with-Nexus prompt seam
- `uv run pytest tests/benchmark/test_with_nexus_runner.py -q` -> initial red `ImportError: cannot import name 'run_with_nexus_codex_attempts'`
- `python3 -m py_compile scripts/bench/with_nexus_runner.py scripts/bench/capability_ab_runner.py tests/benchmark/test_with_nexus_runner.py` -> compile `PASSED` after with-Nexus live invocation/self-heal helper
- `uv run pytest tests/benchmark/test_with_nexus_runner.py -q` -> `5 passed`
- `uv run pytest tests/benchmark/test_with_nexus_runner.py tests/benchmark/test_capability_ab_runner.py::test_run_with_nexus_subprocess_preserves_executor_receipts_without_llm tests/benchmark/test_capability_ab_runner.py::test_skill_mount_evidence_contract_accepts_causal_runtime_mount tests/benchmark/test_capability_ab_runner.py::test_skill_mount_evidence_contract_rejects_quarantined_mount -q` -> `8 passed`
- `uv run scripts/ops/ci_gate.py --changed-only scripts/bench/with_nexus_runner.py scripts/bench/capability_ab_runner.py tests/benchmark/test_with_nexus_runner.py tests/benchmark/test_capability_ab_runner.py docs/testing/test_impact_map.md docs/plans/NEXUS_CLEAN_CODE_LINUS_REFACTOR_PLAN_2026-05-22.md` -> changed-only gate `PASSED` after with-Nexus live invocation/self-heal seam
- `git diff --check -- scripts/bench/with_nexus_runner.py scripts/bench/capability_ab_runner.py tests/benchmark/test_with_nexus_runner.py docs/testing/test_impact_map.md docs/plans/NEXUS_CLEAN_CODE_LINUS_REFACTOR_PLAN_2026-05-22.md` -> diff hygiene `PASSED`
- `uv run scripts/ops/ci_gate.py` -> `ALL QUALITY GATES PASSED` after with-Nexus live invocation/self-heal seam
- `uv run pytest tests/benchmark/test_evidence_bundle_gates.py -q` -> initial red `ModuleNotFoundError: No module named 'scripts.bench.evidence_bundle_gates'`
- `uv run pytest tests/benchmark/test_evidence_bundle_gates.py -q` -> initial integration failure `KeyError: 'config'` from extracted `build_public_gate_checks` context
- `python3 -m py_compile scripts/bench/evidence_bundle_gates.py scripts/bench/capability_ab_runner.py tests/benchmark/test_evidence_bundle_gates.py` -> compile `PASSED` after evidence bundle gate seam
- `uv run pytest tests/benchmark/test_evidence_bundle_gates.py tests/benchmark/test_capability_ab_runner.py::test_write_trial_evidence_and_bundle tests/benchmark/test_capability_ab_runner.py::test_write_evidence_bundle_fails_gate_for_single_arm_run tests/benchmark/test_capability_ab_runner.py::test_write_evidence_bundle_fails_cost_safety_when_prompt_purity_regresses tests/benchmark/test_capability_ab_runner.py::test_write_evidence_bundle_separates_delivery_lift_from_cost_efficiency_regression tests/benchmark/test_capability_ab_runner.py::test_write_evidence_bundle_fails_gate_when_route_decision_missing tests/benchmark/test_capability_ab_runner.py::test_write_evidence_bundle_fails_cost_gate_when_provider_token_source_missing tests/benchmark/test_capability_ab_runner.py::test_session_worker_contamination_fails_public_claim_gate -q` -> `9 passed`
- `uv run pytest tests/benchmark/test_capability_ab_runner.py -q` -> `341 passed`
- `uv run scripts/ops/ci_gate.py --changed-only scripts/bench/evidence_bundle_gates.py scripts/bench/capability_ab_runner.py tests/benchmark/test_evidence_bundle_gates.py tests/benchmark/test_capability_ab_runner.py docs/testing/test_impact_map.md docs/plans/NEXUS_CLEAN_CODE_LINUS_REFACTOR_PLAN_2026-05-22.md "nexus_wiki_vault/06_Ops/Ops - Learning Closure Matrix.md"` -> changed-only gate `PASSED`
- `git diff --check -- scripts/bench/evidence_bundle_gates.py scripts/bench/capability_ab_runner.py tests/benchmark/test_evidence_bundle_gates.py tests/benchmark/test_capability_ab_runner.py docs/testing/test_impact_map.md docs/plans/NEXUS_CLEAN_CODE_LINUS_REFACTOR_PLAN_2026-05-22.md "nexus_wiki_vault/06_Ops/Ops - Learning Closure Matrix.md"` -> diff hygiene `PASSED`
- `uv run scripts/ops/ci_gate.py` -> first full rerun failed at `Lesson Writeback Check` because local date had crossed to `2026-05-23` and the existing evidence-bundle lesson was dated `2026-05-22`
- `nexus_wiki_vault/06_Ops/Ops - Learning Closure Matrix.md` -> added `2026-05-23: Lesson Writeback Gates Use Current Local Date`
- `uv run scripts/ops/ci_gate.py` -> `ALL QUALITY GATES PASSED` after P3 evidence bundle gate seam and same-day lesson writeback; CI emitted existing eval pass-rate warning but did not fail the gate
- `uv run pytest tests/engine/test_multi_agent_actions.py -q` -> initial red `ImportError: cannot import name 'TaskVerificationView'`
- `python3 -m py_compile scripts/engine/commands/multi_agent_actions.py scripts/engine/nexus_cli.py tests/engine/test_multi_agent_actions.py` -> compile `PASSED` after multi-agent verify/close Action extraction
- `uv run pytest tests/engine/test_multi_agent_actions.py -q` -> `19 passed`
- `uv run scripts/ops/ci_gate.py --changed-only scripts/engine/commands/multi_agent_actions.py scripts/engine/nexus_cli.py tests/engine/test_multi_agent_actions.py docs/testing/test_impact_map.md docs/plans/NEXUS_CLEAN_CODE_LINUS_REFACTOR_PLAN_2026-05-22.md "nexus_wiki_vault/06_Ops/Ops - Learning Closure Matrix.md"` -> changed-only gate `PASSED`
- `uv run scripts/ops/ci_gate.py` -> `ALL QUALITY GATES PASSED` after P4 multi-agent verify/close Action extraction; CI emitted existing eval pass-rate warning but did not fail the gate
- `uv run pytest tests/engine/test_multi_agent_actions.py -q` -> initial red `ImportError: cannot import name 'TaskIntegrationView'`
- `python3 -m py_compile scripts/engine/commands/multi_agent_actions.py scripts/engine/nexus_cli.py tests/engine/test_multi_agent_actions.py` -> compile `PASSED` after multi-agent create/start/integrate Action extraction
- `uv run pytest tests/engine/test_multi_agent_actions.py -q` -> `25 passed`
- `uv run scripts/ops/ci_gate.py --changed-only scripts/engine/commands/multi_agent_actions.py scripts/engine/nexus_cli.py tests/engine/test_multi_agent_actions.py docs/testing/test_impact_map.md docs/plans/NEXUS_CLEAN_CODE_LINUS_REFACTOR_PLAN_2026-05-22.md "nexus_wiki_vault/06_Ops/Ops - Learning Closure Matrix.md"` -> changed-only gate `PASSED`
- `uv run scripts/ops/ci_gate.py` -> `ALL QUALITY GATES PASSED` after P4 multi-agent create/start/integrate Action extraction; CI emitted existing eval pass-rate warning but did not fail the gate
- `uv run pytest tests/engine/test_multi_agent_actions.py -q` -> initial red `ImportError: cannot import name 'TaskSubmissionView'`
- `python3 -m py_compile scripts/engine/commands/multi_agent_actions.py scripts/engine/nexus_cli.py tests/engine/test_multi_agent_actions.py` -> compile `PASSED` after multi-agent submit Action extraction
- `uv run pytest tests/engine/test_multi_agent_actions.py -q` -> `29 passed`
- `uv run pytest tests/engine/test_multi_agent_actions.py tests/engine/test_cli_exception_translation.py -q` -> `34 passed`
- `uv run scripts/ops/ci_gate.py --changed-only scripts/engine/commands/multi_agent_actions.py scripts/engine/nexus_cli.py tests/engine/test_multi_agent_actions.py docs/testing/test_impact_map.md docs/plans/NEXUS_CLEAN_CODE_LINUS_REFACTOR_PLAN_2026-05-22.md "nexus_wiki_vault/06_Ops/Ops - Learning Closure Matrix.md"` -> changed-only gate `PASSED`
- `uv run scripts/ops/ci_gate.py` -> `ALL QUALITY GATES PASSED` after P4 multi-agent submit Action extraction; CI emitted existing eval pass-rate warning but did not fail the gate
- `uv run pytest tests/engine/test_learn_actions.py -q` -> initial red `ImportError: cannot import name 'LearnConvergeResult'`
- `python3 -m py_compile scripts/engine/commands/learn_actions.py scripts/engine/nexus_cli.py tests/engine/test_learn_actions.py` -> compile `PASSED` after learn converge Action extraction
- `uv run pytest tests/engine/test_learn_actions.py tests/test_cli_learn_mode.py -q` -> `32 passed`
- `uv run scripts/ops/ci_gate.py` -> first full rerun failed at Report Trust Audit because `tests/engine/test_cli_semantic_contract_audit.py` and `tests/engine/test_cli_artifact_gate_audit.py` still required `_write_hallucination_evidence` / `_enforce_hallucination_gate` tokens inside the `learn:converge` Click block
- `uv run pytest tests/engine/test_cli_semantic_contract_audit.py tests/engine/test_cli_artifact_gate_audit.py tests/engine/test_learn_actions.py -q` -> `20 passed` after audit update followed extracted `run_learn_converge` seam
- `uv run scripts/ops/ci_gate.py --changed-only scripts/engine/commands/learn_actions.py scripts/engine/commands/multi_agent_actions.py scripts/engine/nexus_cli.py tests/engine/test_learn_actions.py tests/engine/test_multi_agent_actions.py tests/engine/test_cli_semantic_contract_audit.py tests/engine/test_cli_artifact_gate_audit.py docs/testing/test_impact_map.md docs/plans/NEXUS_CLEAN_CODE_LINUS_REFACTOR_PLAN_2026-05-22.md "nexus_wiki_vault/06_Ops/Ops - Learning Closure Matrix.md"` -> first changed-only rerun failed because `tests/engine/test_cli_semantic_contract_audit.py` lacked a self row and selector fallback pulled `tests/core/test_web_dom_mapper.py`, which needs a missing local Playwright browser
- `docs/testing/test_impact_map.md` -> added `tests/engine/test_cli_semantic_contract_audit.py` self row
- `uv run scripts/ops/ci_gate.py --changed-only scripts/engine/commands/learn_actions.py scripts/engine/commands/multi_agent_actions.py scripts/engine/nexus_cli.py tests/engine/test_learn_actions.py tests/engine/test_multi_agent_actions.py tests/engine/test_cli_semantic_contract_audit.py tests/engine/test_cli_artifact_gate_audit.py docs/testing/test_impact_map.md docs/plans/NEXUS_CLEAN_CODE_LINUS_REFACTOR_PLAN_2026-05-22.md "nexus_wiki_vault/06_Ops/Ops - Learning Closure Matrix.md"` -> changed-only gate `PASSED`
- `uv run scripts/ops/ci_gate.py` -> `ALL QUALITY GATES PASSED` after P4 learn converge Action extraction and audit/impact-map repair; CI emitted existing eval pass-rate warning but did not fail the gate
- `uv run pytest tests/engine/test_learn_actions.py -q` -> initial red `ImportError: cannot import name 'LearnAskResult'`
- `uv run pytest tests/engine/test_learn_actions.py tests/test_cli_learn_mode.py -q` -> first green attempt failed because `FakeAskService.ask` did not match the real ask interface with `top_k` / evidence / staleness kwargs
- `python3 -m py_compile scripts/engine/commands/learn_actions.py scripts/engine/nexus_cli.py tests/engine/test_learn_actions.py` -> compile `PASSED` after learn ask Action extraction
- `uv run pytest tests/engine/test_learn_actions.py tests/test_cli_learn_mode.py -q` -> `35 passed`
- `uv run scripts/ops/ci_gate.py --changed-only scripts/engine/commands/learn_actions.py scripts/engine/nexus_cli.py tests/engine/test_learn_actions.py docs/plans/NEXUS_CLEAN_CODE_LINUS_REFACTOR_PLAN_2026-05-22.md "nexus_wiki_vault/06_Ops/Ops - Learning Closure Matrix.md"` -> changed-only gate `PASSED` after P4 learn ask Action extraction and lesson writeback
- `uv run scripts/ops/ci_gate.py` -> `ALL QUALITY GATES PASSED` after P4 learn ask Action extraction; CI emitted existing eval pass-rate warning but did not fail the gate
- `uv run pytest tests/engine/test_learn_actions.py -q` -> initial red `ImportError: cannot import name 'LearnSourceLifecycleResult'`
- `uv run pytest tests/engine/test_learn_actions.py -q` -> first green attempt failed because the test expected an exact minimal completion payload instead of the full `build_completion_envelope` contract with runtime classification and timestamp fields
- `uv run pytest tests/engine/test_cli_semantic_contract_audit.py tests/engine/test_cli_artifact_gate_audit.py -q` -> first audit attempt failed because lifecycle command audits still required `_finalize_semantic_payload` / `write_text(` inside the Click command block after extraction
- `python3 -m py_compile scripts/engine/commands/learn_actions.py scripts/engine/nexus_cli.py tests/engine/test_learn_actions.py tests/engine/test_cli_semantic_contract_audit.py tests/engine/test_cli_artifact_gate_audit.py` -> compile `PASSED` after learn source lifecycle Action extraction and audit repair
- `uv run pytest tests/engine/test_learn_actions.py tests/test_cli_learn_mode.py tests/engine/test_cli_semantic_contract_audit.py tests/engine/test_cli_artifact_gate_audit.py -q` -> `44 passed`
- `uv run pytest tests/engine/test_learn_actions.py -q` -> initial red `ImportError: cannot import name 'LearnReportResult'`
- `uv run pytest tests/engine/test_cli_semantic_contract_audit.py tests/engine/test_cli_artifact_gate_audit.py -q` -> first learn report audit attempt failed because audits still required `semantic_status` / `write_text(` inside the Click command block
- `uv run pytest tests/engine/test_learn_actions.py -q` -> initial red `ImportError: cannot import name 'LearnIngestResult'`
- `uv run pytest tests/engine/test_learn_actions.py tests/test_cli_learn_mode.py -q` -> first learn ingest green attempt failed because legacy tests monkeypatched `nexus_cli._evaluate_learn_semantic_contract`, but CLI adapter did not pass that seam into the extracted Action
- `uv run pytest tests/engine/test_cli_semantic_contract_audit.py tests/engine/test_cli_artifact_gate_audit.py -q` -> first learn ingest audit attempt failed because audits still required `semantic_status` / `_write_hallucination_evidence` inside the Click command block
- `uv run pytest tests/engine/test_learn_actions.py -q` -> initial red `ImportError: cannot import name 'LearnGateResult'`
- `uv run pytest tests/engine/test_cli_semantic_contract_audit.py tests/engine/test_cli_artifact_gate_audit.py -q` -> first learn gate artifact audit attempt failed because audits still required `acceptance-check` / `contract-check` inside the Click command block
- `python3 -m py_compile scripts/engine/commands/learn_actions.py scripts/engine/nexus_cli.py tests/engine/test_learn_actions.py tests/engine/test_cli_semantic_contract_audit.py tests/engine/test_cli_artifact_gate_audit.py` -> compile `PASSED` after learn report/ingest/gate Action extraction and audit repair
- `uv run pytest tests/engine/test_learn_actions.py tests/test_cli_learn_mode.py tests/engine/test_cli_semantic_contract_audit.py tests/engine/test_cli_artifact_gate_audit.py -q` -> `55 passed`
- `uv run scripts/ops/ci_gate.py --changed-only scripts/engine/commands/learn_actions.py scripts/engine/nexus_cli.py tests/engine/test_learn_actions.py tests/engine/test_cli_semantic_contract_audit.py tests/engine/test_cli_artifact_gate_audit.py docs/plans/NEXUS_CLEAN_CODE_LINUS_REFACTOR_PLAN_2026-05-22.md "nexus_wiki_vault/06_Ops/Ops - Learning Closure Matrix.md"` -> changed-only gate `PASSED` after P4 learn report/ingest/gate Action extraction and lesson writeback
- `uv run scripts/ops/ci_gate.py` -> `ALL QUALITY GATES PASSED` after P4 learn report/ingest/gate Action extraction; CI emitted existing eval pass-rate warning but did not fail the gate
- `uv run pytest tests/engine/test_learn_actions.py -q` -> initial red `ImportError: cannot import name 'LearnPhaseReportResult'`
- `uv run pytest tests/engine/test_cli_semantic_contract_audit.py tests/engine/test_cli_artifact_gate_audit.py -q` -> first learn phase report audit attempt failed because audits still required `_finalize_semantic_payload` / `ensure_verified_completion` / `write_text(` inside the Click command block
- `python3 -m py_compile scripts/engine/commands/learn_actions.py scripts/engine/nexus_cli.py tests/engine/test_learn_actions.py tests/engine/test_cli_semantic_contract_audit.py tests/engine/test_cli_artifact_gate_audit.py` -> compile `PASSED` after learn phase SLO/KPI Action extraction and audit repair
- `uv run pytest tests/engine/test_learn_actions.py tests/test_cli_learn_mode.py tests/engine/test_cli_semantic_contract_audit.py tests/engine/test_cli_artifact_gate_audit.py -q` -> `58 passed`
- `uv run scripts/ops/ci_gate.py --changed-only scripts/engine/commands/learn_actions.py scripts/engine/nexus_cli.py tests/engine/test_learn_actions.py tests/engine/test_cli_semantic_contract_audit.py tests/engine/test_cli_artifact_gate_audit.py docs/plans/NEXUS_CLEAN_CODE_LINUS_REFACTOR_PLAN_2026-05-22.md "nexus_wiki_vault/06_Ops/Ops - Learning Closure Matrix.md"` -> changed-only gate `PASSED` after P4 learn phase SLO/KPI Action extraction and lesson writeback
- `uv run scripts/ops/ci_gate.py` -> `ALL QUALITY GATES PASSED` after P4 learn phase SLO/KPI Action extraction; CI emitted existing eval pass-rate warning but did not fail the gate
- `uv run pytest tests/engine/test_research_actions.py -q` -> initial red `ModuleNotFoundError: No module named 'scripts.engine.commands.research_actions'`
- `uv run pytest tests/engine/test_research_actions.py tests/test_cli_commands.py::test_research_route_findings_reinjection tests/test_cli_commands.py::test_research_route_recommended_flow_baseline tests/test_cli_commands.py::test_research_route_recommended_flow_hyper_for_risky_task tests/test_cli_commands.py::test_research_route_writes_route_decision_report_when_requested -q` -> first green attempt failed because planner test stored route by reference and later `route_decision_report` mutation polluted the captured route payload
- `python3 -m py_compile scripts/engine/commands/research_actions.py scripts/engine/nexus_cli.py tests/engine/test_research_actions.py` -> compile `PASSED` after P4 research route Action extraction
- `uv run pytest tests/engine/test_research_actions.py tests/test_cli_commands.py::test_research_route_findings_reinjection tests/test_cli_commands.py::test_research_route_recommended_flow_baseline tests/test_cli_commands.py::test_research_route_recommended_flow_hyper_for_risky_task tests/test_cli_commands.py::test_research_route_writes_route_decision_report_when_requested -q` -> `7 passed`
- `uv run pytest tests/engine/test_research_actions.py tests/test_cli_commands.py::test_research_route_findings_reinjection tests/test_cli_commands.py::test_research_route_recommended_flow_baseline tests/test_cli_commands.py::test_research_route_recommended_flow_hyper_for_risky_task tests/test_cli_commands.py::test_research_route_writes_route_decision_report_when_requested tests/engine/test_cli_artifact_gate_audit.py -q` -> `10 passed`
- `uv run scripts/ops/ci_gate.py --changed-only scripts/engine/commands/research_actions.py scripts/engine/nexus_cli.py tests/engine/test_research_actions.py tests/engine/test_cli_artifact_gate_audit.py docs/testing/test_impact_map.md docs/plans/NEXUS_CLEAN_CODE_LINUS_REFACTOR_PLAN_2026-05-22.md "nexus_wiki_vault/06_Ops/Ops - Learning Closure Matrix.md"` -> changed-only gate `PASSED` after P4 research route Action extraction and lesson writeback
- `uv run scripts/ops/ci_gate.py` -> `ALL QUALITY GATES PASSED` after P4 research route Action extraction; CI emitted existing eval pass-rate warning but did not fail the gate
- `uv run pytest tests/engine/test_research_actions.py -q` -> initial red `ImportError: cannot import name 'ResearchHumanReportResult'`
- `python3 -m py_compile scripts/engine/commands/research_actions.py scripts/engine/nexus_cli.py tests/engine/test_research_actions.py` -> compile `PASSED` after P4 research session Action extraction
- `uv run pytest tests/engine/test_research_actions.py tests/engine/test_cli_research_seams.py::test_research_session_loop_cli_drives_route_packet_and_ledger tests/engine/test_cli_research_seams.py::test_research_session_loop_marks_failure_lessons_pending -q` -> `8 passed`
- `uv run pytest tests/engine/test_research_actions.py tests/engine/test_cli_research_seams.py::test_research_session_loop_cli_drives_route_packet_and_ledger tests/engine/test_cli_research_seams.py::test_research_session_loop_marks_failure_lessons_pending tests/engine/test_cli_artifact_gate_audit.py -q` -> `11 passed` after P4 research session Action extraction and artifact audit contract update
- `uv run scripts/ops/ci_gate.py --changed-only scripts/engine/commands/research_actions.py scripts/engine/nexus_cli.py tests/engine/test_research_actions.py tests/engine/test_cli_artifact_gate_audit.py docs/testing/test_impact_map.md docs/plans/NEXUS_CLEAN_CODE_LINUS_REFACTOR_PLAN_2026-05-22.md "nexus_wiki_vault/06_Ops/Ops - Learning Closure Matrix.md"` -> changed-only gate `PASSED` after P4 research session Action extraction and lesson writeback
- `uv run scripts/ops/ci_gate.py` -> `ALL QUALITY GATES PASSED` after P4 research session Action extraction; CI emitted existing eval pass-rate warning but did not fail the gate
- `uv run pytest tests/benchmark/test_evidence_bundle_posture.py -q` -> initial red `ModuleNotFoundError: No module named 'scripts.bench.evidence_bundle_posture'`
- `python3 -m py_compile scripts/bench/evidence_bundle_posture.py scripts/bench/capability_ab_runner.py tests/benchmark/test_evidence_bundle_posture.py` -> compile `PASSED` after P3 posture/x1/x3 seam extraction
- `uv run pytest tests/benchmark/test_evidence_bundle_posture.py tests/benchmark/test_capability_ab_runner.py::test_training_posture_observation_only_when_cost_efficiency_regresses tests/benchmark/test_capability_ab_runner.py::test_training_posture_blocks_synthetic_readiness_shortcut tests/benchmark/test_capability_ab_runner.py::test_valid_comparison_readiness_gate_requires_two_thirds_bare_eligibility tests/benchmark/test_capability_ab_runner.py::test_valid_comparison_readiness_gate_returns_when_without_rows_missing tests/benchmark/test_capability_ab_runner.py::test_direction_magnitude_gate_marks_small_delta_as_neutral tests/benchmark/test_capability_ab_runner.py::test_mutation_hardening_gate_returns_on_forged_warning_clean_signal tests/benchmark/test_capability_ab_runner.py::test_mutation_hardening_gate_returns_on_forged_wall_conserved_error_ratio tests/benchmark/test_capability_ab_runner.py::test_mutation_hardening_gate_counts_suspicious_zero_fill_rows tests/benchmark/test_capability_ab_runner.py::test_x3_promotion_gate_requires_two_valid_x1_rounds tests/benchmark/test_capability_ab_runner.py::test_x3_promotion_gate_passes_on_two_consecutive_ready_rounds tests/benchmark/test_capability_ab_runner.py::test_x3_promotion_gate_does_not_treat_truthy_strings_as_pass tests/benchmark/test_capability_ab_runner.py::test_recent_compatible_x1_history_filters_mismatch_and_non_dict_rows tests/benchmark/test_capability_ab_runner.py::test_load_x1_readiness_history_returns_empty_on_corrupt_json tests/benchmark/test_capability_ab_runner.py::test_append_x1_readiness_history_caps_entries tests/benchmark/test_capability_ab_runner.py::test_x1_readiness_history_path_prefers_repo_stable_learn_dir tests/benchmark/test_capability_ab_runner.py::test_x1_readiness_history_path_allows_explicit_override -q` -> `19 passed`
- `uv run pytest tests/benchmark/test_capability_ab_runner.py tests/benchmark/test_evidence_bundle_posture.py tests/benchmark/test_evidence_bundle_gates.py -q` -> first full runner characterization failed with 19 bundle tests all rooted in missing `_x1_readiness_pass` compatibility alias; after importing the alias from `evidence_bundle_posture`, rerun produced `346 passed`
- `uv run scripts/ops/ci_gate.py --changed-only scripts/bench/evidence_bundle_posture.py scripts/bench/capability_ab_runner.py tests/benchmark/test_evidence_bundle_posture.py docs/testing/test_impact_map.md docs/plans/NEXUS_CLEAN_CODE_LINUS_REFACTOR_PLAN_2026-05-22.md "nexus_wiki_vault/06_Ops/Ops - Learning Closure Matrix.md"` -> changed-only gate `PASSED` after P3 posture/x1/x3 seam extraction and lesson writeback
- `uv run scripts/ops/ci_gate.py` -> `ALL QUALITY GATES PASSED` after P3 posture/x1/x3 seam extraction; CI emitted existing eval pass-rate warning but did not fail the gate
- `uv run pytest tests/benchmark/test_fixture_materialization.py::test_resolve_external_fixture_uses_injected_adapter tests/benchmark/test_capability_ab_runner.py::test_resolve_task_files_uses_external_fixture_adapter -q` -> initial red `TypeError` for missing `target_file` request field and missing `_resolve_task_files(..., external_fixture_adapter=...)`
- `python3 -m py_compile scripts/bench/fixture_materialization.py scripts/bench/capability_ab_runner.py tests/benchmark/test_fixture_materialization.py tests/benchmark/test_capability_ab_runner.py` -> compile `PASSED` after P2A external fixture adapter injection seam
- `uv run pytest tests/benchmark/test_fixture_materialization.py::test_resolve_external_fixture_fails_closed_until_clone_adapter_exists tests/benchmark/test_fixture_materialization.py::test_resolve_external_fixture_uses_injected_adapter tests/benchmark/test_capability_ab_runner.py::test_resolve_task_files_fails_closed_for_external_without_adapter tests/benchmark/test_capability_ab_runner.py::test_resolve_task_files_uses_external_fixture_adapter -q` -> `4 passed`
- `uv run pytest tests/benchmark/test_fixture_materialization.py tests/benchmark/test_capability_ab_runner.py tests/benchmark/test_evidence_bundle_posture.py tests/benchmark/test_evidence_bundle_gates.py -q` -> `356 passed` after P2A external fixture adapter injection seam
- `uv run scripts/ops/ci_gate.py --changed-only scripts/bench/fixture_materialization.py scripts/bench/capability_ab_runner.py scripts/bench/evidence_bundle_posture.py tests/benchmark/test_fixture_materialization.py tests/benchmark/test_capability_ab_runner.py tests/benchmark/test_evidence_bundle_posture.py docs/testing/test_impact_map.md docs/plans/NEXUS_CLEAN_CODE_LINUS_REFACTOR_PLAN_2026-05-22.md "nexus_wiki_vault/06_Ops/Ops - Learning Closure Matrix.md"` -> changed-only gate `PASSED` after P2A external fixture adapter injection seam and lesson writeback
- `uv run scripts/ops/ci_gate.py` -> `ALL QUALITY GATES PASSED` after P2A external fixture adapter injection seam; CI emitted existing eval pass-rate warning but did not fail the gate
- `uv run pytest tests/benchmark/test_fixture_materialization.py -q` -> initial sandboxed local Adapter red `ImportError: cannot import name 'SandboxedLocalExternalFixtureAdapter'`
- `python3 -m py_compile scripts/bench/fixture_materialization.py tests/benchmark/test_fixture_materialization.py` -> compile `PASSED` after sandboxed local external fixture Adapter implementation
- `uv run pytest tests/benchmark/test_fixture_materialization.py -q` -> `12 passed` after sandboxed local external fixture Adapter implementation
- `uv run pytest tests/benchmark/test_fixture_materialization.py tests/benchmark/test_capability_ab_runner.py::test_resolve_task_files_uses_external_fixture_adapter tests/benchmark/test_capability_ab_runner.py::test_resolve_task_files_fails_closed_for_external_without_adapter -q` -> `14 passed`, proving injected adapter path and default fail-closed path still both work
- `uv run pytest tests/benchmark/test_fixture_materialization.py tests/benchmark/test_capability_ab_runner.py tests/benchmark/test_evidence_bundle_posture.py tests/benchmark/test_evidence_bundle_gates.py -q` -> `359 passed` after sandboxed local external fixture Adapter implementation
- `uv run scripts/ops/ci_gate.py --changed-only scripts/bench/fixture_materialization.py tests/benchmark/test_fixture_materialization.py tests/benchmark/test_capability_ab_runner.py docs/testing/test_impact_map.md docs/plans/NEXUS_CLEAN_CODE_LINUS_REFACTOR_PLAN_2026-05-22.md "nexus_wiki_vault/06_Ops/Ops - Learning Closure Matrix.md"` -> changed-only gate `PASSED` after sandboxed local external fixture Adapter and impact-map nodeid update
- `uv run scripts/ops/ci_gate.py` -> `ALL QUALITY GATES PASSED` after sandboxed local external fixture Adapter; CI emitted existing eval pass-rate warning but did not fail the gate
- `uv run pytest tests/benchmark/test_evidence_bundle_payload.py -q` -> initial red `ModuleNotFoundError: No module named 'scripts.bench.evidence_bundle_payload'`
- `uv run pytest tests/benchmark/test_evidence_bundle_payload.py tests/benchmark/test_capability_ab_runner.py::test_write_trial_evidence_and_bundle tests/benchmark/test_capability_ab_runner.py::test_write_evidence_bundle_fails_gate_for_single_arm_run -q` -> first green attempt failed because the test expected a guessed requirement key; actual contract uses `external_provider_public_claim_allowed`
- `python3 -m py_compile scripts/bench/evidence_bundle_payload.py scripts/bench/capability_ab_runner.py tests/benchmark/test_evidence_bundle_payload.py` -> compile `PASSED` after P3 payload finalizer/writer seam extraction
- `uv run pytest tests/benchmark/test_evidence_bundle_payload.py tests/benchmark/test_capability_ab_runner.py::test_write_trial_evidence_and_bundle tests/benchmark/test_capability_ab_runner.py::test_write_evidence_bundle_fails_gate_for_single_arm_run -q` -> `4 passed`
- `uv run pytest tests/benchmark/test_capability_ab_runner.py tests/benchmark/test_evidence_bundle_payload.py tests/benchmark/test_evidence_bundle_posture.py tests/benchmark/test_evidence_bundle_gates.py -q` -> `349 passed` after P3 payload finalizer/writer seam extraction
- `uv run scripts/ops/ci_gate.py --changed-only scripts/bench/evidence_bundle_payload.py scripts/bench/capability_ab_runner.py tests/benchmark/test_evidence_bundle_payload.py docs/testing/test_impact_map.md docs/plans/NEXUS_CLEAN_CODE_LINUS_REFACTOR_PLAN_2026-05-22.md "nexus_wiki_vault/06_Ops/Ops - Learning Closure Matrix.md"` -> changed-only gate `PASSED` after P3 payload finalizer/writer seam and lesson writeback
- `uv run scripts/ops/ci_gate.py` -> `ALL QUALITY GATES PASSED` after P3 payload finalizer/writer seam; CI emitted existing eval pass-rate warning but did not fail the gate
- `uv run pytest tests/benchmark/test_evidence_bundle_payload.py -q` -> rubric-summary RED `ImportError: cannot import name 'summarize_rubric_contract_rows'`
- `python3 -m py_compile scripts/bench/evidence_bundle_payload.py scripts/bench/capability_ab_runner.py tests/benchmark/test_evidence_bundle_payload.py` -> compile `PASSED` after rubric summary seam extraction
- `uv run pytest tests/benchmark/test_evidence_bundle_payload.py tests/benchmark/test_capability_ab_runner.py::test_write_trial_evidence_and_bundle tests/benchmark/test_capability_ab_runner.py::test_write_evidence_bundle_fails_gate_for_single_arm_run -q` -> `6 passed` after rubric summary seam extraction
- `uv run pytest tests/benchmark/test_capability_ab_runner.py tests/benchmark/test_evidence_bundle_payload.py tests/benchmark/test_evidence_bundle_posture.py tests/benchmark/test_evidence_bundle_gates.py -q` -> `351 passed` after rubric summary seam extraction
- `uv run scripts/ops/ci_gate.py --changed-only scripts/bench/evidence_bundle_payload.py scripts/bench/capability_ab_runner.py tests/benchmark/test_evidence_bundle_payload.py docs/testing/test_impact_map.md docs/plans/NEXUS_CLEAN_CODE_LINUS_REFACTOR_PLAN_2026-05-22.md "nexus_wiki_vault/06_Ops/Ops - Learning Closure Matrix.md"` -> changed-only gate `PASSED` after rubric summary seam extraction
- `uv run scripts/ops/ci_gate.py` -> `ALL QUALITY GATES PASSED` after rubric summary seam extraction; CI emitted existing eval pass-rate warning but did not fail the gate
- `uv run pytest tests/benchmark/test_evidence_bundle_payload.py -q` -> rubric bundle RED `ImportError: cannot import name 'build_rubric_contract_bundle'`
- `python3 -m py_compile scripts/bench/evidence_bundle_payload.py scripts/bench/capability_ab_runner.py tests/benchmark/test_evidence_bundle_payload.py` -> compile `PASSED` after rubric bundle seam extraction
- `uv run pytest tests/benchmark/test_evidence_bundle_payload.py tests/benchmark/test_capability_ab_runner.py::test_write_trial_evidence_and_bundle tests/benchmark/test_capability_ab_runner.py::test_write_evidence_bundle_fails_gate_for_single_arm_run -q` -> `7 passed` after rubric bundle seam extraction
- `uv run pytest tests/benchmark/test_capability_ab_runner.py tests/benchmark/test_evidence_bundle_payload.py tests/benchmark/test_evidence_bundle_posture.py tests/benchmark/test_evidence_bundle_gates.py -q` -> `352 passed` after rubric bundle seam extraction
- `uv run pytest tests/benchmark/test_evidence_bundle_accounting.py -q` -> initial red `ModuleNotFoundError: No module named 'scripts.bench.evidence_bundle_accounting'`
- `python3 -m py_compile scripts/bench/evidence_bundle_accounting.py scripts/bench/capability_ab_runner.py tests/benchmark/test_evidence_bundle_accounting.py` -> compile `PASSED` after public cost accounting context seam extraction
- `uv run pytest tests/benchmark/test_evidence_bundle_accounting.py -q` -> `2 passed`
- `uv run pytest tests/benchmark/test_evidence_bundle_accounting.py tests/benchmark/test_capability_ab_runner.py::test_write_trial_evidence_and_bundle tests/benchmark/test_capability_ab_runner.py::test_write_evidence_bundle_fails_gate_for_single_arm_run tests/benchmark/test_capability_ab_runner.py::test_write_evidence_bundle_separates_delivery_lift_from_cost_efficiency_regression -q` -> `5 passed`
- `uv run pytest tests/benchmark/test_capability_ab_runner.py tests/benchmark/test_evidence_bundle_accounting.py tests/benchmark/test_evidence_bundle_payload.py tests/benchmark/test_evidence_bundle_posture.py tests/benchmark/test_evidence_bundle_gates.py -q` -> first characterization failed because `capability_ab_runner.derive_valid_comparison_readiness_gate` compatibility alias had been removed
- `uv run pytest tests/benchmark/test_capability_ab_runner.py::test_valid_comparison_readiness_gate_requires_two_thirds_bare_eligibility tests/benchmark/test_capability_ab_runner.py::test_valid_comparison_readiness_gate_returns_when_without_rows_missing tests/benchmark/test_evidence_bundle_accounting.py -q` -> `4 passed` after restoring the compatibility alias
- `uv run pytest tests/benchmark/test_capability_ab_runner.py tests/benchmark/test_evidence_bundle_accounting.py tests/benchmark/test_evidence_bundle_payload.py tests/benchmark/test_evidence_bundle_posture.py tests/benchmark/test_evidence_bundle_gates.py -q` -> `354 passed` after public cost accounting context seam extraction
- `uv run scripts/ops/ci_gate.py --changed-only scripts/bench/evidence_bundle_accounting.py scripts/bench/capability_ab_runner.py tests/benchmark/test_evidence_bundle_accounting.py tests/benchmark/test_capability_ab_runner.py docs/testing/test_impact_map.md docs/plans/NEXUS_CLEAN_CODE_LINUS_REFACTOR_PLAN_2026-05-22.md "nexus_wiki_vault/06_Ops/Ops - Learning Closure Matrix.md"` -> changed-only gate `PASSED` after public cost accounting context seam and impact-map row
- `uv run scripts/ops/ci_gate.py` -> `ALL QUALITY GATES PASSED` after public cost accounting context seam; CI emitted existing eval pass-rate warning but did not fail the gate
- `uv run pytest tests/benchmark/test_evidence_bundle_provider_context.py -q` -> initial red `ModuleNotFoundError: No module named 'scripts.bench.evidence_bundle_provider_context'`
- `python3 -m py_compile scripts/bench/evidence_bundle_provider_context.py scripts/bench/capability_ab_runner.py tests/benchmark/test_evidence_bundle_provider_context.py` -> compile `PASSED` after provider model-lock context seam extraction
- `uv run pytest tests/benchmark/test_evidence_bundle_provider_context.py tests/benchmark/test_capability_ab_runner.py::test_write_trial_evidence_and_bundle tests/benchmark/test_capability_ab_runner.py::test_write_evidence_bundle_fails_gate_for_single_arm_run -q` -> `5 passed`
- `uv run pytest tests/benchmark/test_capability_ab_runner.py tests/benchmark/test_evidence_bundle_accounting.py tests/benchmark/test_evidence_bundle_provider_context.py tests/benchmark/test_evidence_bundle_payload.py tests/benchmark/test_evidence_bundle_posture.py tests/benchmark/test_evidence_bundle_gates.py -q` -> `357 passed` after provider model-lock context seam extraction
- `uv run scripts/ops/ci_gate.py --changed-only scripts/bench/evidence_bundle_provider_context.py scripts/bench/evidence_bundle_accounting.py scripts/bench/capability_ab_runner.py tests/benchmark/test_evidence_bundle_provider_context.py tests/benchmark/test_evidence_bundle_accounting.py tests/benchmark/test_capability_ab_runner.py docs/testing/test_impact_map.md docs/plans/NEXUS_CLEAN_CODE_LINUS_REFACTOR_PLAN_2026-05-22.md "nexus_wiki_vault/06_Ops/Ops - Learning Closure Matrix.md"` -> changed-only gate `PASSED` after provider model-lock context seam and impact-map row
- `uv run scripts/ops/ci_gate.py` -> `ALL QUALITY GATES PASSED` after provider model-lock context seam; CI emitted existing eval pass-rate warning but did not fail the gate
- `uv run pytest tests/benchmark/test_evidence_bundle_rows.py -q` -> initial red `ModuleNotFoundError: No module named 'scripts.bench.evidence_bundle_rows'`
- `python3 -m py_compile scripts/bench/evidence_bundle_rows.py scripts/bench/capability_ab_runner.py tests/benchmark/test_evidence_bundle_rows.py` -> compile `PASSED` after row-set context seam extraction
- `uv run pytest tests/benchmark/test_evidence_bundle_rows.py tests/benchmark/test_capability_ab_runner.py::test_write_trial_evidence_and_bundle tests/benchmark/test_capability_ab_runner.py::test_write_evidence_bundle_fails_gate_for_single_arm_run -q` -> first focused run failed because tests assumed `trial_index=0` should be distinct, but existing `_row_key_counts` treats falsy `0` as default `"1"`
- `uv run pytest tests/benchmark/test_evidence_bundle_rows.py tests/benchmark/test_capability_ab_runner.py::test_write_trial_evidence_and_bundle tests/benchmark/test_capability_ab_runner.py::test_write_evidence_bundle_fails_gate_for_single_arm_run -q` -> `5 passed` after locking existing trial-index compatibility semantics
- `uv run pytest tests/benchmark/test_capability_ab_runner.py tests/benchmark/test_evidence_bundle_rows.py tests/benchmark/test_evidence_bundle_accounting.py tests/benchmark/test_evidence_bundle_provider_context.py tests/benchmark/test_evidence_bundle_payload.py tests/benchmark/test_evidence_bundle_posture.py tests/benchmark/test_evidence_bundle_gates.py -q` -> `360 passed` after row-set context seam extraction
- `uv run scripts/ops/ci_gate.py --changed-only scripts/bench/evidence_bundle_rows.py scripts/bench/capability_ab_runner.py tests/benchmark/test_evidence_bundle_rows.py tests/benchmark/test_capability_ab_runner.py docs/testing/test_impact_map.md docs/plans/NEXUS_CLEAN_CODE_LINUS_REFACTOR_PLAN_2026-05-22.md "nexus_wiki_vault/06_Ops/Ops - Learning Closure Matrix.md"` -> changed-only gate `PASSED` after row-set context seam and impact-map row
- `uv run scripts/ops/ci_gate.py` -> `ALL QUALITY GATES PASSED` after row-set context seam; CI emitted existing eval pass-rate warning but did not fail the gate
- `uv run pytest tests/benchmark/test_evidence_bundle_manifest.py -q` -> initial red `ModuleNotFoundError: No module named 'scripts.bench.evidence_bundle_manifest'`
- `python3 -m py_compile scripts/bench/evidence_bundle_manifest.py scripts/bench/capability_ab_runner.py tests/benchmark/test_evidence_bundle_manifest.py` -> compile `PASSED` after manifest metadata seam extraction
- `uv run pytest tests/benchmark/test_evidence_bundle_manifest.py tests/benchmark/test_capability_ab_runner.py::test_write_trial_evidence_and_bundle tests/benchmark/test_capability_ab_runner.py::test_write_evidence_bundle_fails_gate_for_single_arm_run -q` -> `7 passed`
- `uv run pytest tests/benchmark/test_capability_ab_runner.py tests/benchmark/test_evidence_bundle_manifest.py tests/benchmark/test_evidence_bundle_rows.py tests/benchmark/test_evidence_bundle_accounting.py tests/benchmark/test_evidence_bundle_provider_context.py tests/benchmark/test_evidence_bundle_payload.py tests/benchmark/test_evidence_bundle_posture.py tests/benchmark/test_evidence_bundle_gates.py -q` -> `365 passed` after manifest metadata seam extraction
- `uv run scripts/ops/ci_gate.py --changed-only scripts/bench/evidence_bundle_manifest.py scripts/bench/capability_ab_runner.py tests/benchmark/test_evidence_bundle_manifest.py tests/benchmark/test_capability_ab_runner.py docs/testing/test_impact_map.md docs/plans/NEXUS_CLEAN_CODE_LINUS_REFACTOR_PLAN_2026-05-22.md "nexus_wiki_vault/06_Ops/Ops - Learning Closure Matrix.md"` -> changed-only gate `PASSED` after manifest metadata seam and impact-map row
- `uv run scripts/ops/ci_gate.py` -> `ALL QUALITY GATES PASSED` after manifest metadata seam; CI emitted existing eval pass-rate warning but did not fail the gate
- `uv run pytest tests/engine/test_research_actions.py -q` -> research auto-flow RED `ImportError: cannot import name 'ResearchAutoFlowResult'`
- `python3 -m py_compile scripts/engine/commands/research_actions.py scripts/engine/nexus_cli.py tests/engine/test_research_actions.py` -> compile `PASSED` after research auto-flow Action extraction
- `uv run pytest tests/engine/test_research_actions.py tests/engine/test_cli_research_support.py tests/engine/test_cli_research_seams.py::test_research_auto_flow_cli_uses_service_seam tests/engine/test_cli_research_seams.py::test_research_auto_flow_emits_completion_contract tests/engine/test_cli_research_seams.py::test_research_auto_flow_gate_blocks_unverified_claim_before_execution tests/engine/test_cli_research_seams.py::test_research_auto_flow_session_logs_success_packet -q` -> `16 passed` after research auto-flow Action extraction
- `uv run pytest tests/engine/test_cli_artifact_gate_audit.py tests/engine/test_cli_semantic_contract_audit.py -q` -> initial audit failure because audits still required `research:auto-flow` completion tokens inside Click block
- `uv run pytest tests/engine/test_research_actions.py tests/engine/test_cli_research_support.py tests/engine/test_cli_research_seams.py::test_research_auto_flow_cli_uses_service_seam tests/engine/test_cli_research_seams.py::test_research_auto_flow_emits_completion_contract tests/engine/test_cli_research_seams.py::test_research_auto_flow_gate_blocks_unverified_claim_before_execution tests/engine/test_cli_research_seams.py::test_research_auto_flow_session_logs_success_packet tests/engine/test_cli_artifact_gate_audit.py tests/engine/test_cli_semantic_contract_audit.py -q` -> `27 passed` after audit ownership moved to `research_actions.py`
- `uv run pytest tests/engine/test_research_actions.py tests/engine/test_cli_research_seams.py tests/engine/test_cli_research_support.py tests/engine/test_research_auto_flow_guard_audit.py -q` -> `28 passed` after research auto-flow Action extraction
- `uv run scripts/ops/ci_gate.py --changed-only scripts/engine/commands/research_actions.py scripts/engine/nexus_cli.py tests/engine/test_research_actions.py tests/engine/test_cli_research_seams.py tests/engine/test_cli_artifact_gate_audit.py tests/engine/test_cli_semantic_contract_audit.py docs/testing/test_impact_map.md docs/plans/NEXUS_CLEAN_CODE_LINUS_REFACTOR_PLAN_2026-05-22.md "nexus_wiki_vault/06_Ops/Ops - Learning Closure Matrix.md"` -> initial changed-only failure because `tests/engine/test_cli_research_seams.py` lacked an impact-map self row and fallback pulled `tests/core/test_web_dom_mapper.py`
- `uv run scripts/ops/ci_gate.py --changed-only scripts/engine/commands/research_actions.py scripts/engine/nexus_cli.py tests/engine/test_research_actions.py tests/engine/test_cli_research_seams.py tests/engine/test_cli_artifact_gate_audit.py tests/engine/test_cli_semantic_contract_audit.py docs/testing/test_impact_map.md docs/plans/NEXUS_CLEAN_CODE_LINUS_REFACTOR_PLAN_2026-05-22.md "nexus_wiki_vault/06_Ops/Ops - Learning Closure Matrix.md"` -> changed-only gate `PASSED` after adding `tests/engine/test_cli_research_seams.py` self row
- `uv run scripts/ops/ci_gate.py` -> `ALL QUALITY GATES PASSED` after research auto-flow Action extraction; CI emitted existing eval pass-rate warning but did not fail the gate
- `uv run pytest tests/engine/test_research_actions.py -q` -> research run RED `ImportError: cannot import name 'ResearchRunResult'`
- `python3 -m py_compile scripts/engine/commands/research_actions.py scripts/engine/nexus_cli.py tests/engine/test_research_actions.py` -> compile `PASSED` after research run Action extraction
- `uv run pytest tests/engine/test_research_actions.py -q` -> `12 passed` after research run Action extraction
- `uv run pytest tests/engine/test_cli_research_seams.py::test_research_run_gate_blocks_unverified_claim_before_candidates tests/engine/test_cli_research_seams.py::test_research_run_does_not_route_through_legacy_run_seam tests/engine/test_cli_artifact_gate_audit.py tests/engine/test_cli_semantic_contract_audit.py -q` -> initial audit failure because audits still required `research:run` completion tokens inside Click block
- `uv run pytest tests/engine/test_research_actions.py tests/engine/test_cli_research_seams.py::test_research_run_gate_blocks_unverified_claim_before_candidates tests/engine/test_cli_research_seams.py::test_research_run_does_not_route_through_legacy_run_seam tests/engine/test_cli_artifact_gate_audit.py tests/engine/test_cli_semantic_contract_audit.py -q` -> `26 passed` after audit ownership moved to `research_actions.py`
- `uv run pytest tests/engine/test_research_actions.py tests/engine/test_cli_research_seams.py tests/engine/test_cli_research_support.py tests/engine/test_research_auto_flow_guard_audit.py tests/engine/test_cli_artifact_gate_audit.py tests/engine/test_cli_semantic_contract_audit.py -q` -> `42 passed` after research run Action extraction
- `uv run scripts/ops/ci_gate.py --changed-only scripts/engine/commands/research_actions.py scripts/engine/nexus_cli.py tests/engine/test_research_actions.py tests/engine/test_cli_research_seams.py tests/engine/test_cli_artifact_gate_audit.py tests/engine/test_cli_semantic_contract_audit.py docs/testing/test_impact_map.md docs/plans/NEXUS_CLEAN_CODE_LINUS_REFACTOR_PLAN_2026-05-22.md "nexus_wiki_vault/06_Ops/Ops - Learning Closure Matrix.md"` -> changed-only gate `PASSED` after research run Action extraction
- `uv run scripts/ops/ci_gate.py` -> `ALL QUALITY GATES PASSED` after research run Action extraction; CI emitted existing eval pass-rate warning but did not fail the gate

本輪失敗與修正：

- 初次 changed-only gate 失敗：新 `tests/benchmark/test_telemetry_fidelity.py` 未列入 impact map，JIT selector fallback 拉進無關 `tests/core`，其中 `tests/core/test_web_dom_mapper.py` 因本機 Playwright browser executable 不存在失敗。
- 修正：補上新測試檔自身 impact-map row，再重跑 changed-only gate 通過。
- P1A 初次 changed-only gate 失敗：`tests/app/test_research_flow_service.py` 與 `docs/testing/test_impact_map.md` 沒有自我映射，selector fallback 又拉進 `tests/core`，同樣撞到本機 Playwright browser executable 缺失。
- 修正：補上 test file 與 impact-map 文件自身 contract rows，再重跑 changed-only gate 通過。
- G2/G7 初次 CRLF 測試失敗：`Path.read_text()` 會做 universal newline normalization，讓 `"\r\n"` 檢查看不到原始 CRLF。
- 修正：`check_golden_schema_snapshots.py::_read_text_lf` 改用 `read_bytes()` 先檢查 `b"\r\n"`，再 UTF-8 decode。
- combined changed-only 初次失敗：`tests/ops/test_strategic_map_audit.py` 缺自我映射，selector fallback 拉進 `tests/core`，撞到本機 Playwright executable 缺失。
- 修正：補上 `tests/ops/test_strategic_map_audit.py` self row，重跑 combined changed-only gate 通過。
- P2/P3 combined changed-only 初次失敗：`docs/plans/NEXUS_CLEAN_CODE_LINUS_REFACTOR_PLAN_2026-05-22.md` 缺 impact-map row，selector fallback 拉進 `tests/core`，撞到本機 Playwright executable 缺失。
- 修正：補上 plan document 的 `plan_contract` impact-map row，並把 lesson 寫回 `nexus_wiki_vault/06_Ops/Ops - Learning Closure Matrix.md`；重跑 combined changed-only gate 通過。
- P5 changed-only 初次失敗：`nexus/engine/learning_policy_loader.py` 缺精準 impact-map row，被 broad `nexus/engine` row 拉進整個 engine suite，撞到既有 recursive repair / tactical route failures。
- 修正：補上 `learning_policy_loader.py` 的 focused row，並把 lesson 寫回 Learning Closure；重跑 P5 changed-only gate 通過。
- P4 learn benchmark full gate 初次失敗：`tests/engine/test_cli_artifact_gate_audit.py` 仍要求 `learn:benchmark` Click block 內含 `json.dump(`；Action extraction 後 artifact writer 已移到 `scripts/engine/commands/learn_actions.py::write_learn_precision_benchmark_output`。
- 修正：artifact audit 改為要求 CLI adapter 呼叫 writer seam，並新增 extracted action writer token check；把 lesson 寫回 Learning Closure。
- P4 learn benchmark changed-only 重跑初次失敗：Learning Closure Matrix 本身缺 impact-map row，被 selector fallback 拉進 `tests/core`，撞到本機 Playwright executable 缺失。
- 修正：補上 `nexus_wiki_vault/06_Ops/Ops - Learning Closure Matrix.md` 的 `lesson_writeback_contract` row，並把 lesson 寫回 Learning Closure；重跑 changed-only gate 通過。
- P3 socket barrier focused tests 初次失敗：noop context 測試錯把 `assert_runner_socket_allowed()` 當成受 context 控制的 API；實際上它是硬斷言。runner row 也沒有頂層 `error` 欄位，錯誤收斂在 `nexus_failure_reason`。
- 修正：noop 測試改檢查 socket monkeypatch identity；runner test 改斷言 `nexus_failure_reason` 包含 `SocketBlockedError`。
- P3 socket barrier changed-only 初次失敗：`tests/benchmark/test_capability_ab_runner.py` 本身缺 impact-map row，即使 source runner row 精準，測試檔變更仍 fallback 到 `tests/core`，撞到本機 Playwright executable 缺失。
- 修正：補上 `tests/benchmark/test_capability_ab_runner.py` 的 `benchmark_runner_test_contract` self row，並把 lesson 寫回 Learning Closure；重跑 changed-only gate 通過。
- P3 direct provider prompt seam 初次整合驗證失敗：direct baseline 成功路徑計算 `difflib.unified_diff`，但 `capability_ab_runner.py` 未顯式 import `difflib`，抽取後 focused 成功路徑立即暴露 `NameError: name 'difflib' is not defined`。
- 修正：補上顯式 `import difflib`，並把 lesson 寫回 Learning Closure；direct provider seam 與既有 direct baseline focused tests 重跑通過。
- P3 evidence bundle gate builder 初次 RED：新增 `tests/benchmark/test_evidence_bundle_gates.py` 後先跑出 `ModuleNotFoundError: No module named 'scripts.bench.evidence_bundle_gates'`，證明測試先於 module。
- P3 evidence bundle gate builder 初次 GREEN 失敗：module 建立後，`build_public_gate_checks` 需要 `config` 但 extracted local context 未傳入，focused test 暴露 `KeyError: 'config'`。
- 修正：`build_evidence_bundle_gate_outputs` 把 `config` 顯式放回 local context，並用 route policy contract failure 測試守住 fail-closed public gate。
- P3 evidence bundle focused characterization 初次失敗：命令使用已改名的 route-decision/provider-token nodeids，pytest 回報 `not found`。
- 修正：用 `rg` 從 `tests/benchmark/test_capability_ab_runner.py` 解析現行 nodeids，並把 lesson 寫回 Learning Closure。
- P3 evidence bundle final full gate 初次重跑失敗：本地時間跨到 `2026-05-23` 後，`lesson_writeback_check.py` 要求今天日期的 Learning Closure entry；當時只有 `2026-05-22` lesson。
- 修正：補上 `2026-05-23: Lesson Writeback Gates Use Current Local Date`，重跑 full CI 通過。
- P4 multi-agent verify/close 初次 RED：action tests 匯入 `TaskVerificationView` 時失敗，證明測試先於 Action seam。
- 修正：新增 `TaskVerificationView`、`verify_multi_agent_task`、`render_multi_agent_task_verification`、`close_multi_agent_task`，CLI command 改成 thin adapter 並套 `translate_action_exceptions`。
- P4 multi-agent create/start/integrate 初次 RED：action tests 匯入 `TaskIntegrationView` 時失敗，證明測試先於 Action seam。
- 修正：新增 create/start/integrate Action views 與 injectable factories，CLI command 改成 thin adapter 並套 `translate_action_exceptions`。
- P4 multi-agent submit 初次 RED：action tests 匯入 `TaskSubmissionView` 時失敗，證明測試先於 Action seam。
- 修正：新增 `submit_multi_agent_task`、`TaskSubmissionView` 與 receipt/governance/commit injectable seams；CLI command 改成 thin adapter 並套 `translate_action_exceptions`。
- P4 learn converge 初次 RED：action tests 匯入 `LearnConvergeResult` 時失敗，證明測試先於 Action seam。
- 修正：新增 `run_learn_converge`、`LearnConvergeResult`、hallucination evidence writer/gate seams；CLI command 改成 thin adapter 並套 `translate_action_exceptions`。
- P4 learn converge full gate 初次失敗：semantic/artifact audits 還把 hallucination evidence/gate token 綁在 Click command block。
- 修正：audit 改成要求 CLI adapter 呼叫 `run_learn_converge`，並在 extracted `learn_actions.py` 檢查 `_write_learn_hallucination_evidence`、`_enforce_learn_hallucination_gate`、`write_text(`。
- P4 learn converge changed-only 重跑初次失敗：`tests/engine/test_cli_semantic_contract_audit.py` 缺 self row，selector fallback 拉進 `tests/core`，撞到本機 Playwright browser executable 缺失。
- 修正：補上 semantic contract audit self row，避免 docs/audit test edits 擴大到 unrelated core suite。
- P4 learn ask 初次 RED：action tests 匯入 `LearnAskResult` 時失敗，證明測試先於 Action seam。
- P4 learn ask 初次 GREEN 失敗：fake `LearnModeService.ask` 沒有支援真 interface 的 `top_k` / `min_evidence` / `min_token_coverage` / `max_staleness_days` / `allow_cross_pack` kwargs。
- 修正：新增 `run_learn_ask`、`LearnAskResult`、hallucination evidence writer/gate seams，並讓 fake service 覆蓋真 ask interface；CLI command 改成 thin adapter 並套 `translate_action_exceptions`。
- P4 learn source lifecycle 初次 RED：action tests 匯入 `LearnSourceLifecycleResult` 時失敗，證明測試先於 Action seam。
- P4 learn source lifecycle 初次 GREEN 失敗：測試把 completion payload 寫成極小固定 dict，未納入既有 `build_completion_envelope` 會補 `runtime_classification`、`retryable`、`timestamp` 等欄位。
- 修正：測試改為欄位契約比對；Action 保持 raw report 先寫、completion envelope 再 merge 的既有語義。
- P4 learn source lifecycle audit 初次失敗：semantic/artifact audits 還把 `_finalize_semantic_payload` / `write_text(` token 綁在 Click command block。
- 修正：audit 改成要求 CLI adapter 呼叫 `run_learn_register_source` / `run_learn_refresh` / `run_learn_refresh_plan` 與 `verify_learn_source_lifecycle_completion`，並在 extracted `learn_actions.py` 檢查 `_write_json_report`、`_finalize_learn_semantic_payload`、`ensure_verified_completion`。
- P4 learn report 初次 RED：action tests 匯入 `LearnReportResult` 時失敗，證明測試先於 Action seam。
- P4 learn report audit 初次失敗：semantic/artifact audits 還把 `semantic_status` / `write_text(` token 綁在 Click command block。
- 修正：新增 `run_learn_report`、`LearnReportResult`、dual-gate markdown writer seam、semantic evaluator seam、semantic contract enforcer，並讓 audits 跟隨 Action module 的 markdown/report write token。
- P4 learn ingest 初次 RED：action tests 匯入 `LearnIngestResult` 時失敗，證明測試先於 Action seam。
- P4 learn ingest 初次 GREEN 失敗：legacy test 透過 monkeypatch `nexus_cli._evaluate_learn_semantic_contract` 模擬 fail-closed，但 CLI adapter 沒有把 semantic evaluator seam 傳入 Action。
- 修正：CLI adapter 顯式傳入 `_evaluate_learn_semantic_contract`，保留舊測試與外部 monkeypatch seam；Action 仍可在單元測試中注入 fake evaluator。
- P4 learn ingest audit 初次失敗：semantic/artifact audits 還把 `semantic_status` / `_write_hallucination_evidence` token 綁在 Click command block。
- 修正：audit 改成要求 CLI adapter 呼叫 `run_learn_ingest` / `enforce_learn_ingest_semantic_contract`，並在 extracted `learn_actions.py` 檢查 hallucination evidence/gate、dual-gate markdown、semantic evaluator、report write token。
- P4 learn gate 初次 RED：action tests 匯入 `LearnGateResult` 時失敗，證明測試先於 Action seam。
- P4 learn gate artifact audit 初次失敗：audit 還把 `acceptance-check` / `contract-check` subprocess token 綁在 Click command block。
- 修正：新增 `run_learn_gate`、`LearnGateResult`、threshold fail-closed gate、command runner seam；audit 改到 Action module 檢查 acceptance/contract/CI command tokens。
- P4 learn phase report 初次 RED：action tests 匯入 `LearnPhaseReportResult` 時失敗，證明測試先於 Action seam。
- P4 learn phase report audit 初次失敗：semantic/artifact audits 還把 `_finalize_semantic_payload` / `ensure_verified_completion` / `write_text(` token 綁在 Click command block。
- 修正：新增 `run_learn_phase_slo`、`run_learn_phase_kpi`、`LearnPhaseReportResult` 與 completion verifier seam；audit 改到 Action module 檢查 JSON report write、completion envelope 與 verification token。
- P4 research route 初次 RED：action tests 匯入 `scripts.engine.commands.research_actions` 時失敗，證明測試先於 Action seam。
- P4 research route 初次 GREEN 失敗：route decision report 寫入後會在 payload 上加 `route_decision_report`，fake planner 若保存 route 參照就會被後續 mutation 污染。
- 修正：`run_research_route` 傳入 planner 的 route 改為 `dict(payload)` snapshot，避免 report path mutation 洩漏到 planner seam；新增 route builder / planner / policy loader / decision builder / report writer / timestamp provider seams。
- P4 research session 初次 RED：action tests 匯入 `ResearchHumanReportResult` / `ResearchSessionActionResult` 時失敗，證明測試先於 Action seam。
- 修正：新增 research session Actions 與 renderers，把 `ResearchSessionLoopService` call、relative JSON read、human report output write 從 Click command body 抽到 `scripts/engine/commands/research_actions.py`；既有 `test_cli_research_seams.py` session flow focused tests 維持通過。
- P3 posture/x1/x3 初次 RED：新測試匯入 `scripts.bench.evidence_bundle_posture` 時失敗，證明測試先於 deep module。
- P3 posture/x1/x3 full runner 初次失敗：`write_evidence_bundle` 仍直接呼叫 `_x1_readiness_pass`，抽出後沒有保留相容 alias，導致所有 evidence bundle writer tests 同根因失敗。
- 修正：`capability_ab_runner.py` 從 `evidence_bundle_posture.py` 匯入 `_x1_readiness_pass` 相容 alias；posture module direct tests、runner alias tests、完整 benchmark runner characterization 全部通過。
- P2A external fixture adapter 初次 RED：`ExternalFixtureRequest` 尚未攜帶 target/test paths，`_resolve_task_files` 也無法注入 adapter，導致 fake external adapter 無法測。
- 修正：補上 `ExternalFixtureAdapter` protocol、request target/test/hidden fields、`resolve_external_fixture(..., adapter=...)` 與 `_resolve_task_files(..., external_fixture_adapter=...)`；預設行為仍 fail-closed，不開 live clone/setup。
- P2A sandboxed local external Adapter 初次 RED：tests 要求 `SandboxedLocalExternalFixtureAdapter`，但 module 尚未提供 concrete Adapter，證明 external seam 仍停留在 fake/injection 層。
- 修正：新增 `SandboxedLocalExternalFixtureAdapter` 與 `ExternalFixturePolicyError`；只接受本機 path / `file://`，以 `allowed_source_roots` 限制 source，拒絕 remote URL 與 path escape，並維持 default no-adapter fail-closed。
- P3 payload finalizer 初次 RED：新測試匯入 `scripts.bench.evidence_bundle_payload` 時失敗，證明測試先於 serialization seam。
- P3 payload finalizer 初次 GREEN 失敗：測試猜測 public promotion contract requirement key，實際既有 key 是 `external_provider_public_claim_allowed`。
- 修正：測試改回檢查現有 contract key；新增 payload finalizer/writer module，runner 只呼叫 finalizer 與 UTF-8 writer，完整 benchmark bundle characterization 維持通過。
- P3 rubric summary 初次 RED：payload test 匯入 `summarize_rubric_contract_rows` 時失敗，證明 rubric aggregation 還留在 runner 內聯函式。
- 修正：把 rubric contract pass-rate 與 hard-fail reason aggregation 搬到 `evidence_bundle_payload.py`，補 empty rows 合約與 duplicate reason dedupe 測試；完整 benchmark bundle characterization 維持通過。
- P3 rubric bundle 初次 RED：payload test 匯入 `build_rubric_contract_bundle` 時失敗，證明 runner 仍知道 rubric bundle schema、四個 summary key 與 claim boundary 文案。
- 修正：新增 `build_rubric_contract_bundle`，runner 改為只傳 with/without/eligible row groups；rubric schema ownership 轉入 payload module。
- P3 public cost accounting context 初次 RED：accounting tests 匯入 `scripts.bench.evidence_bundle_accounting` 失敗，證明 token/provider measured rates、paired cost ratios、prompt purity、retry share 與 systemic regression flags 還留在 runner 內聯計算。
- P3 public cost accounting context 初次 full characterization 失敗：移除 `capability_ab_runner.derive_valid_comparison_readiness_gate` import alias 後，既有 tests/callers 仍依賴 runner facade 上的 compatibility surface。
- 修正：新增 `PublicCostAccountingContext` 與 `build_public_cost_accounting_context(...)`，runner 改為呼叫 accounting Module 後把結果交給既有 gate/payload assembly；同時保留 `derive_valid_comparison_readiness_gate` compatibility alias，不改 public cost gate 語義。
- P3 provider model-lock context 初次 RED：provider context tests 匯入 `scripts.bench.evidence_bundle_provider_context` 失敗，證明 model set / same-model / env model-lock payload 仍留在 runner 內聯。
- 修正：新增 `ModelLockContext`、`model_names`、`build_model_lock_context(...)`，runner 改用 provider context module，同時保留 `_model_names` compatibility alias。
- P3 row-set context 初次 RED：row-set tests 匯入 `scripts.bench.evidence_bundle_rows` 失敗，證明 with/without 分組、eligible rows、row_counts 與 same-task-trials 還留在 runner 內聯。
- P3 row-set context 初次 focused 失敗：tests 預期 `trial_index=0` 應獨立，但既有 `_row_key_counts` 使用 `row.get("trial_index") or "1"`，所以 falsy `0` 是 default trial `"1"`；這是 compatibility surface，不能在 extraction slice 偷改。
- 修正：新增 `EvidenceBundleRowSets`、`build_evidence_bundle_row_sets(...)` 與 `row_key_counts(...)`，runner 改用 row-set module，同時保留 `_row_key_counts` compatibility alias；tests 明確鎖住 `trial_index=0` 的既有語義。
- P3 manifest metadata context 初次 RED：manifest tests 匯入 `scripts.bench.evidence_bundle_manifest` 失敗，證明 artifact file manifest、run identity、task manifest、timeout manifest 與 raw file manifest 還在 runner payload assembly 內聯。
- P3 manifest metadata retrieval 小失敗：一次 `rg` command 因 zsh unmatched quote 失敗；修正為單引號 pattern，避免工具查證本身污染進度。
- 修正：新增 `build_artifact_file_manifest(...)`、`build_run_identity(...)`、`build_task_manifest(...)`、`build_timeout_manifest(...)`、`build_raw_file_manifest(...)`，runner 用 injected sha/git/timeout helper 呼叫，避免 helper 偷讀 public gate state。
- P3 payload section context 初次 RED：payload tests 匯入 `build_nexus_wearing_context` 時失敗，證明 telemetry completeness 與 Nexus wearing/system execution context 仍留在 runner payload assembly 內聯。
- 修正：新增 `build_telemetry_completeness_section(...)` 與 `build_nexus_wearing_context(...)`；runner 改用 payload Module，同時保留 `locals()` gate builder 需要的既有變數名稱，避免 `derive_public_gate_failures` / `build_public_gate_checks` 語意漂移。
- `python3 -m py_compile scripts/bench/evidence_bundle_payload.py scripts/bench/capability_ab_runner.py tests/benchmark/test_evidence_bundle_payload.py` -> compile `PASSED` after payload section context seam extraction.
- `uv run pytest tests/benchmark/test_evidence_bundle_payload.py tests/benchmark/test_capability_ab_runner.py::test_write_trial_evidence_and_bundle tests/benchmark/test_capability_ab_runner.py::test_write_evidence_bundle_fails_gate_for_single_arm_run tests/benchmark/test_capability_ab_runner.py::test_session_worker_contamination_fails_public_claim_gate -q` -> `10 passed` after payload section context seam extraction.
- `uv run pytest tests/benchmark/test_capability_ab_runner.py tests/benchmark/test_evidence_bundle_payload.py tests/benchmark/test_evidence_bundle_manifest.py tests/benchmark/test_evidence_bundle_rows.py tests/benchmark/test_evidence_bundle_accounting.py tests/benchmark/test_evidence_bundle_provider_context.py tests/benchmark/test_evidence_bundle_posture.py tests/benchmark/test_evidence_bundle_gates.py -q` -> `367 passed` after payload section context seam extraction.
- `uv run scripts/ops/ci_gate.py --changed-only scripts/bench/evidence_bundle_payload.py scripts/bench/capability_ab_runner.py tests/benchmark/test_evidence_bundle_payload.py docs/plans/NEXUS_CLEAN_CODE_LINUS_REFACTOR_PLAN_2026-05-22.md "nexus_wiki_vault/06_Ops/Ops - Learning Closure Matrix.md"` -> changed-only gate `PASSED` after payload section context seam extraction.
- `uv run scripts/ops/ci_gate.py` -> `ALL QUALITY GATES PASSED` after payload section context seam extraction; CI emitted existing eval pass-rate warning but did not fail the gate.
- P3 static gate section 初次 RED：payload tests 匯入 `build_wall_ledger_conservation_section` 時失敗，證明 wall-ledger bundle 與 warning-clean gate section schema 仍留在 runner payload assembly 內聯。
- 修正：新增 `build_wall_ledger_conservation_section(...)` 與 `build_warning_clean_gate_section(...)`；runner 只傳入既有 summary/invalid/required inputs，不重新計算 wall telemetry 或 warning invalid 判定。
- `python3 -m py_compile scripts/bench/evidence_bundle_payload.py scripts/bench/capability_ab_runner.py tests/benchmark/test_evidence_bundle_payload.py` -> compile `PASSED` after static gate section seam extraction.
- `uv run pytest tests/benchmark/test_evidence_bundle_payload.py tests/benchmark/test_capability_ab_runner.py::test_write_trial_evidence_and_bundle tests/benchmark/test_capability_ab_runner.py::test_write_evidence_bundle_fails_gate_for_single_arm_run tests/benchmark/test_capability_ab_runner.py::test_session_worker_contamination_fails_public_claim_gate -q` -> `12 passed` after static gate section seam extraction.
- `uv run pytest tests/benchmark/test_capability_ab_runner.py tests/benchmark/test_evidence_bundle_payload.py tests/benchmark/test_evidence_bundle_manifest.py tests/benchmark/test_evidence_bundle_rows.py tests/benchmark/test_evidence_bundle_accounting.py tests/benchmark/test_evidence_bundle_provider_context.py tests/benchmark/test_evidence_bundle_posture.py tests/benchmark/test_evidence_bundle_gates.py -q` -> `369 passed` after static gate section seam extraction.
- `uv run scripts/ops/ci_gate.py --changed-only scripts/bench/evidence_bundle_payload.py scripts/bench/capability_ab_runner.py tests/benchmark/test_evidence_bundle_payload.py docs/plans/NEXUS_CLEAN_CODE_LINUS_REFACTOR_PLAN_2026-05-22.md "nexus_wiki_vault/06_Ops/Ops - Learning Closure Matrix.md"` -> changed-only gate `PASSED` after static gate section seam extraction.
- `uv run scripts/ops/ci_gate.py` -> `ALL QUALITY GATES PASSED` after static gate section seam extraction; CI emitted existing eval pass-rate warning but did not fail the gate.
- P3 posture finalization section 初次 RED：payload tests 匯入 `build_posture_finalization_gate_section` 時失敗，證明 `posture_finalization_gate` schema 與 public efficiency wording boolean 仍留在 runner payload assembly 內聯。
- 修正：新增 `build_posture_finalization_gate_section(...)`；runner 只傳入既有 `cost_efficiency_status`、`cost_efficiency_sample_sufficient`、`valid_comparison_ready` 與 `training_eligibility_posture`，不搬動 public/training posture derivation。
- `python3 -m py_compile scripts/bench/evidence_bundle_payload.py scripts/bench/capability_ab_runner.py tests/benchmark/test_evidence_bundle_payload.py` -> compile `PASSED` after posture finalization section seam extraction.
- `uv run pytest tests/benchmark/test_evidence_bundle_payload.py tests/benchmark/test_capability_ab_runner.py::test_write_trial_evidence_and_bundle tests/benchmark/test_capability_ab_runner.py::test_write_evidence_bundle_fails_gate_for_single_arm_run tests/benchmark/test_capability_ab_runner.py::test_write_evidence_bundle_separates_delivery_lift_from_cost_efficiency_regression -q` -> `13 passed` after posture finalization section seam extraction.
- `uv run pytest tests/benchmark/test_capability_ab_runner.py tests/benchmark/test_evidence_bundle_payload.py tests/benchmark/test_evidence_bundle_manifest.py tests/benchmark/test_evidence_bundle_rows.py tests/benchmark/test_evidence_bundle_accounting.py tests/benchmark/test_evidence_bundle_provider_context.py tests/benchmark/test_evidence_bundle_posture.py tests/benchmark/test_evidence_bundle_gates.py -q` -> `370 passed` after posture finalization section seam extraction.
- `uv run scripts/ops/ci_gate.py --changed-only scripts/bench/evidence_bundle_payload.py scripts/bench/capability_ab_runner.py tests/benchmark/test_evidence_bundle_payload.py docs/plans/NEXUS_CLEAN_CODE_LINUS_REFACTOR_PLAN_2026-05-22.md "nexus_wiki_vault/06_Ops/Ops - Learning Closure Matrix.md"` -> changed-only gate `PASSED` after posture finalization section seam extraction.
- `uv run scripts/ops/ci_gate.py` -> `ALL QUALITY GATES PASSED` after posture finalization section seam extraction; CI emitted existing eval pass-rate warning but did not fail the gate.
- F01 telemetry fidelity snapshot 初次 RED：`tests/benchmark/test_telemetry_fidelity.py` 匯入 `scripts.bench.evidence_bundle_fidelity` 失敗，證明固定 mock bundle snapshot extraction seam 尚不存在。
- F01 telemetry fidelity snapshot 初次 GREEN 失敗：expected snapshot 把完整 matched-pair fixture 的 `valid_comparison_readiness_gate` 預估成 `RETURN`，但實際既有行為是 `PASS`。
- 修正：新增 `extract_telemetry_fidelity_snapshot(payload)`，只抽穩定 telemetry/public-gate fields；測試改為鎖住實際 `PASS` readiness 行為。
- `uv run pytest tests/benchmark/test_telemetry_fidelity.py -q` -> `4 passed` after fixed mock evidence-bundle telemetry snapshot seam.
- `python3 -m py_compile scripts/bench/evidence_bundle_fidelity.py tests/benchmark/test_telemetry_fidelity.py` -> compile `PASSED` after fixed mock telemetry snapshot seam.
- `uv run pytest tests/benchmark/test_telemetry_fidelity.py tests/benchmark/test_evidence_bundle_payload.py tests/benchmark/test_capability_ab_runner.py::test_write_trial_evidence_and_bundle tests/benchmark/test_capability_ab_runner.py::test_write_evidence_bundle_separates_delivery_lift_from_cost_efficiency_regression -q` -> `16 passed` after fixed mock telemetry snapshot seam.
- `uv run pytest tests/benchmark/test_capability_ab_runner.py tests/benchmark/test_telemetry_fidelity.py tests/benchmark/test_evidence_bundle_payload.py tests/benchmark/test_evidence_bundle_manifest.py tests/benchmark/test_evidence_bundle_rows.py tests/benchmark/test_evidence_bundle_accounting.py tests/benchmark/test_evidence_bundle_provider_context.py tests/benchmark/test_evidence_bundle_posture.py tests/benchmark/test_evidence_bundle_gates.py -q` -> `374 passed` after fixed mock telemetry snapshot seam.
- `uv run scripts/ops/ci_gate.py --changed-only scripts/bench/evidence_bundle_fidelity.py tests/benchmark/test_telemetry_fidelity.py docs/testing/test_impact_map.md docs/plans/NEXUS_CLEAN_CODE_LINUS_REFACTOR_PLAN_2026-05-22.md "nexus_wiki_vault/06_Ops/Ops - Learning Closure Matrix.md"` -> changed-only gate `PASSED` after fixed mock telemetry snapshot seam.
- `uv run scripts/ops/ci_gate.py` -> `ALL QUALITY GATES PASSED` after fixed mock telemetry snapshot seam; CI emitted existing eval pass-rate warning but did not fail the gate.
- P3 payload header section 初次 RED：payload tests 匯入 `build_evidence_bundle_header_section` 失敗，證明 schema/header/manifest/raw-file/row-count placement 仍留在 runner 主 payload dict assembly。
- 修正：新增 `build_evidence_bundle_header_section(...)`，runner 透過 `**header_section` 組裝 payload 開頭；metadata value 來源仍由既有 manifest/context helpers 提供。
- `python3 -m py_compile scripts/bench/evidence_bundle_payload.py scripts/bench/capability_ab_runner.py tests/benchmark/test_evidence_bundle_payload.py tests/benchmark/test_telemetry_fidelity.py` -> compile `PASSED` after payload header section seam extraction.
- `uv run pytest tests/benchmark/test_evidence_bundle_payload.py tests/benchmark/test_telemetry_fidelity.py tests/benchmark/test_capability_ab_runner.py::test_write_trial_evidence_and_bundle tests/benchmark/test_capability_ab_runner.py::test_write_evidence_bundle_fails_gate_for_single_arm_run -q` -> `17 passed` after payload header section seam extraction.
- `uv run pytest tests/benchmark/test_capability_ab_runner.py tests/benchmark/test_telemetry_fidelity.py tests/benchmark/test_evidence_bundle_payload.py tests/benchmark/test_evidence_bundle_manifest.py tests/benchmark/test_evidence_bundle_rows.py tests/benchmark/test_evidence_bundle_accounting.py tests/benchmark/test_evidence_bundle_provider_context.py tests/benchmark/test_evidence_bundle_posture.py tests/benchmark/test_evidence_bundle_gates.py -q` -> `375 passed` after payload header section seam extraction.
- `uv run scripts/ops/ci_gate.py --changed-only scripts/bench/evidence_bundle_payload.py scripts/bench/capability_ab_runner.py tests/benchmark/test_evidence_bundle_payload.py tests/benchmark/test_telemetry_fidelity.py docs/plans/NEXUS_CLEAN_CODE_LINUS_REFACTOR_PLAN_2026-05-22.md "nexus_wiki_vault/06_Ops/Ops - Learning Closure Matrix.md"` -> changed-only gate `PASSED` after payload header section seam extraction.
- `uv run scripts/ops/ci_gate.py` -> `ALL QUALITY GATES PASSED` after payload header section seam extraction; CI emitted existing eval pass-rate warning but did not fail the gate.
- P3 computed section 初次 RED：payload tests 匯入 `build_evidence_bundle_computed_sections` 失敗，證明 route-cost/report/contract/S2T/product/OpenSeeker payload placement 仍分散在 runner 主 payload dict assembly。
- 修正：新增 `build_evidence_bundle_computed_sections(...)`，runner 只把已計算完成的 report/contract values 傳入 builder；不搬動 cost accounting、provider variance、S2T shadow scoring、public gate decision 或 report computation。
- `python3 -m py_compile scripts/bench/evidence_bundle_payload.py scripts/bench/capability_ab_runner.py tests/benchmark/test_evidence_bundle_payload.py tests/benchmark/test_telemetry_fidelity.py` -> compile `PASSED` after computed section seam extraction.
- `uv run pytest tests/benchmark/test_evidence_bundle_payload.py tests/benchmark/test_telemetry_fidelity.py tests/benchmark/test_capability_ab_runner.py::test_write_trial_evidence_and_bundle tests/benchmark/test_capability_ab_runner.py::test_write_evidence_bundle_fails_gate_for_single_arm_run -q` -> `18 passed` after computed section seam extraction.
- `uv run pytest tests/benchmark/test_capability_ab_runner.py tests/benchmark/test_telemetry_fidelity.py tests/benchmark/test_evidence_bundle_payload.py tests/benchmark/test_evidence_bundle_manifest.py tests/benchmark/test_evidence_bundle_rows.py tests/benchmark/test_evidence_bundle_accounting.py tests/benchmark/test_evidence_bundle_provider_context.py tests/benchmark/test_evidence_bundle_posture.py tests/benchmark/test_evidence_bundle_gates.py -q` -> `376 passed` after computed section seam extraction.
- `uv run scripts/ops/ci_gate.py --changed-only scripts/bench/evidence_bundle_payload.py scripts/bench/capability_ab_runner.py tests/benchmark/test_evidence_bundle_payload.py tests/benchmark/test_telemetry_fidelity.py docs/plans/NEXUS_CLEAN_CODE_LINUS_REFACTOR_PLAN_2026-05-22.md "nexus_wiki_vault/06_Ops/Ops - Learning Closure Matrix.md"` -> changed-only gate `PASSED` after computed section seam extraction.
- `uv run scripts/ops/ci_gate.py` -> `ALL QUALITY GATES PASSED` after computed section seam extraction; CI emitted existing eval pass-rate warning but did not fail the gate.
- P3 claim/posture section 初次 RED：payload tests 匯入 `build_evidence_bundle_claim_posture_sections` 失敗，證明 public claim gates、readiness/direction/x3/mutation/posture/training payload placement 仍留在 runner 主 payload dict assembly。
- 修正：新增 `build_evidence_bundle_claim_posture_sections(...)`，runner 只把已算好的 gate/posture outputs 傳入 builder；不搬動 public gate derivation、training posture derivation 或 x1/x3 policy logic。
- `python3 -m py_compile scripts/bench/evidence_bundle_payload.py scripts/bench/capability_ab_runner.py tests/benchmark/test_evidence_bundle_payload.py tests/benchmark/test_telemetry_fidelity.py` -> compile `PASSED` after claim/posture section seam extraction.
- `uv run pytest tests/benchmark/test_evidence_bundle_payload.py tests/benchmark/test_telemetry_fidelity.py tests/benchmark/test_capability_ab_runner.py::test_write_trial_evidence_and_bundle tests/benchmark/test_capability_ab_runner.py::test_write_evidence_bundle_fails_gate_for_single_arm_run tests/benchmark/test_capability_ab_runner.py::test_write_evidence_bundle_separates_delivery_lift_from_cost_efficiency_regression -q` -> `20 passed` after claim/posture section seam extraction.
- `uv run pytest tests/benchmark/test_capability_ab_runner.py tests/benchmark/test_telemetry_fidelity.py tests/benchmark/test_evidence_bundle_payload.py tests/benchmark/test_evidence_bundle_manifest.py tests/benchmark/test_evidence_bundle_rows.py tests/benchmark/test_evidence_bundle_accounting.py tests/benchmark/test_evidence_bundle_provider_context.py tests/benchmark/test_evidence_bundle_posture.py tests/benchmark/test_evidence_bundle_gates.py -q` -> `377 passed` after claim/posture section seam extraction.
- `uv run scripts/ops/ci_gate.py --changed-only scripts/bench/evidence_bundle_payload.py scripts/bench/capability_ab_runner.py tests/benchmark/test_evidence_bundle_payload.py tests/benchmark/test_telemetry_fidelity.py docs/plans/NEXUS_CLEAN_CODE_LINUS_REFACTOR_PLAN_2026-05-22.md "nexus_wiki_vault/06_Ops/Ops - Learning Closure Matrix.md"` -> changed-only gate `PASSED` after claim/posture section seam extraction.
- `uv run scripts/ops/ci_gate.py` -> `ALL QUALITY GATES PASSED` after claim/posture section seam extraction; CI emitted existing eval pass-rate warning but did not fail the gate.
- P3 final payload assembly 初次 RED：payload tests 匯入 `build_evidence_bundle_payload` 失敗，證明 top-level payload merge order 仍由 runner 主函式直接維護。
- 修正：新增 `build_evidence_bundle_payload(...)`，runner 改為傳入各 section builder 的 resolved outputs；builder 只合併 sections，不計算成本、provider variance、public gate、x1/x3 或 report values。
- `python3 -m py_compile scripts/bench/evidence_bundle_payload.py scripts/bench/capability_ab_runner.py tests/benchmark/test_evidence_bundle_payload.py tests/benchmark/test_telemetry_fidelity.py` -> compile `PASSED` after final payload assembly seam extraction.
- `uv run pytest tests/benchmark/test_evidence_bundle_payload.py tests/benchmark/test_telemetry_fidelity.py tests/benchmark/test_capability_ab_runner.py::test_write_trial_evidence_and_bundle tests/benchmark/test_capability_ab_runner.py::test_write_evidence_bundle_fails_gate_for_single_arm_run tests/benchmark/test_capability_ab_runner.py::test_write_evidence_bundle_separates_delivery_lift_from_cost_efficiency_regression -q` -> `21 passed` after final payload assembly seam extraction.
- `uv run pytest tests/benchmark/test_capability_ab_runner.py tests/benchmark/test_telemetry_fidelity.py tests/benchmark/test_evidence_bundle_payload.py tests/benchmark/test_evidence_bundle_manifest.py tests/benchmark/test_evidence_bundle_rows.py tests/benchmark/test_evidence_bundle_accounting.py tests/benchmark/test_evidence_bundle_provider_context.py tests/benchmark/test_evidence_bundle_posture.py tests/benchmark/test_evidence_bundle_gates.py -q` -> `378 passed` after final payload assembly seam extraction.
- `uv run scripts/ops/ci_gate.py --changed-only scripts/bench/evidence_bundle_payload.py scripts/bench/capability_ab_runner.py tests/benchmark/test_evidence_bundle_payload.py tests/benchmark/test_telemetry_fidelity.py docs/plans/NEXUS_CLEAN_CODE_LINUS_REFACTOR_PLAN_2026-05-22.md "nexus_wiki_vault/06_Ops/Ops - Learning Closure Matrix.md"` -> changed-only gate `PASSED` after final payload assembly seam extraction.
- `uv run scripts/ops/ci_gate.py` -> `ALL QUALITY GATES PASSED` after final payload assembly seam extraction; CI emitted existing eval pass-rate warning but did not fail the gate.
- P9 SQLite retry memory-manager one-writer 初次 RED：`tests/core/test_memory_manager_sqlite_retry.py` 先失敗於 `memory_manager` 沒有 `SQLiteRetryHandler` seam 與 `last_sqlite_retry_receipt`，證明 `ProjectMemoryManager._execute_with_retry` 仍使用本地 retry loop。
- 修正：`ProjectMemoryManager._execute_with_retry` 改用既有 `SQLiteRetryHandler` 包單一 SQLite writer，busy/locked retry receipt 落在 `last_sqlite_retry_receipt`；non-busy/corrupt error 維持 fail-fast，`_is_retryable_sqlite_lock` 只作為 compatibility wrapper 委派到 `is_retryable_sqlite_busy`。
- `python3 -m py_compile nexus/core/memory_manager.py tests/core/test_memory_manager_sqlite_retry.py tests/core/test_memory_manager_write_guard.py` -> compile `PASSED` after P9 memory-manager one-writer integration.
- `uv run pytest tests/core/test_memory_manager_sqlite_retry.py tests/core/test_memory_manager_write_guard.py tests/infrastructure/test_sqlite_retry.py -q` -> `12 passed` after P9 memory-manager one-writer integration.
- `uv run scripts/ops/ci_gate.py --changed-only nexus/core/memory_manager.py tests/core/test_memory_manager_sqlite_retry.py docs/testing/test_impact_map.md docs/plans/NEXUS_CLEAN_CODE_LINUS_REFACTOR_PLAN_2026-05-22.md "nexus_wiki_vault/06_Ops/Ops - Learning Closure Matrix.md"` -> changed-only gate `PASSED` after P9 memory-manager one-writer integration.
- `uv run scripts/ops/ci_gate.py` -> `ALL QUALITY GATES PASSED` after P9 memory-manager one-writer integration; CI emitted existing eval pass-rate warning but did not fail the gate.
- P9 evidence sealing report-reader 初次 RED：`tests/benchmark/test_gemini_nexus_report.py::test_load_evidence_bundle_can_require_sealed_evidence_policy` 失敗於 `_load_evidence_bundle()` 不接受 `require_sealed`，證明 report reader 尚未接入 `EvidenceSealingBarrier`。
- 修正：`scripts/bench/gemini_nexus_report.py::_load_evidence_bundle` 新增 opt-in `require_sealed`；預設仍讀 legacy unsealed bundle，opt-in 時只接受 `evidence_seal` envelope 並透過 `read_sealed_evidence_payload(...)` 讀取，unsealed bundle 由 `UnsealedEvidenceError` fail-closed。CLI 新增 `--require-sealed-evidence-bundle`，只影響 report reader，不解鎖 public/runtime gates。
- `uv run pytest tests/benchmark/test_gemini_nexus_report.py::test_load_evidence_bundle_can_require_sealed_evidence_policy -q` -> `1 passed` after P9 evidence sealing report-reader integration.
- `python3 -m py_compile scripts/bench/gemini_nexus_report.py tests/benchmark/test_gemini_nexus_report.py nexus/core/memory_manager.py tests/core/test_memory_manager_sqlite_retry.py` -> compile `PASSED` after P9 evidence sealing report-reader integration.
- `uv run pytest tests/benchmark/test_gemini_nexus_report.py tests/contracts/test_evidence_sealing_barrier.py tests/core/test_memory_manager_sqlite_retry.py tests/core/test_memory_manager_write_guard.py tests/infrastructure/test_sqlite_retry.py -q` -> `46 passed` after P9 evidence sealing report-reader integration.
- `uv run scripts/ops/ci_gate.py --changed-only scripts/bench/gemini_nexus_report.py tests/benchmark/test_gemini_nexus_report.py nexus/core/memory_manager.py tests/core/test_memory_manager_sqlite_retry.py docs/testing/test_impact_map.md docs/plans/NEXUS_CLEAN_CODE_LINUS_REFACTOR_PLAN_2026-05-22.md "nexus_wiki_vault/06_Ops/Ops - Learning Closure Matrix.md"` -> changed-only gate `PASSED` after P9 evidence sealing report-reader integration.
- `uv run scripts/ops/ci_gate.py` -> `ALL QUALITY GATES PASSED` after P9 evidence sealing report-reader integration; CI emitted existing eval pass-rate warning but did not fail the gate.
- ContextHub budget-source leaf 初次 RED：`tests/core/test_context_budget_sources.py` 匯入 `nexus.core.context_budget_sources` 失敗，證明 L0/L1/history/extra source shaping 仍留在 `ContextHub._context_budget_sources`。
- 修正：新增 `nexus/core/context_budget_sources.py`，提供 `build_context_budget_sources(...)` 與 `estimate_context_tokens(...)`；`ContextHub._context_budget_sources` 改為只讀 state/L0/L1，並委派 split Module。`tests/core/test_context_hub_strict_deps.py::test_context_hub_uses_split_context_budget_source_builder` 作為 deletion test，證明 facade 真的透過 split Module 取得 budget sources。
- `uv run pytest tests/core/test_context_budget_sources.py tests/core/test_context_hub_strict_deps.py::test_context_hub_uses_split_context_budget_source_builder tests/core/test_context_hub_strict_deps.py::test_context_hub_builds_read_only_context_budget_receipt tests/core/test_context_hub_strict_deps.py::test_context_hub_builds_context_assembly_contract -q` -> `5 passed` after ContextHub budget-source leaf extraction.
- `python3 -m py_compile nexus/core/context_budget_sources.py nexus/core/context_hub.py tests/core/test_context_budget_sources.py tests/core/test_context_hub_strict_deps.py` -> compile `PASSED` after ContextHub budget-source leaf extraction.
- `uv run pytest tests/core/test_context_budget_sources.py tests/core/test_context_hub_strict_deps.py tests/contracts/test_context_budget.py tests/contracts/test_context_assembly.py -q` -> `29 passed` after ContextHub budget-source leaf extraction.
- `uv run pytest tests/core/test_context_hub_strict_deps.py tests/core/test_belief_engine.py -q` -> `32 passed` after ContextHub budget-source leaf extraction.
- `uv run scripts/ops/ci_gate.py --changed-only nexus/core/context_budget_sources.py nexus/core/context_hub.py tests/core/test_context_budget_sources.py tests/core/test_context_hub_strict_deps.py docs/testing/test_impact_map.md docs/plans/NEXUS_CLEAN_CODE_LINUS_REFACTOR_PLAN_2026-05-22.md "nexus_wiki_vault/06_Ops/Ops - Learning Closure Matrix.md"` -> changed-only gate `PASSED` after ContextHub budget-source leaf extraction.
- `uv run scripts/ops/ci_gate.py` -> `ALL QUALITY GATES PASSED` after ContextHub budget-source leaf extraction; CI emitted existing eval pass-rate warning but did not fail the gate.
- ContextHub text-store leaf 初次 RED：`tests/core/test_context_text_store.py` 匯入 `nexus.core.context_text_store` 失敗，證明 `load_program_rules` 與 `_load_last_handoff` 的 local text/JSON fallback 還留在 `ContextHub` facade。
- 修正：新增 `nexus/core/context_text_store.py`，提供 `ContextTextStore.load_program_rules(...)` 與 `load_last_handoff()`；`ContextHub` 建立 text-store leaf 並保留原 `load_program_rules` / `_load_last_handoff` facade methods。`tests/core/test_context_hub_strict_deps.py::test_context_hub_uses_split_context_text_store` 作為 deletion test。
- `uv run pytest tests/core/test_context_text_store.py tests/core/test_context_hub_strict_deps.py::test_context_hub_uses_split_context_text_store -q` -> `3 passed` after ContextHub text-store leaf extraction.
- `python3 -m py_compile nexus/core/context_text_store.py nexus/core/context_hub.py tests/core/test_context_text_store.py tests/core/test_context_hub_strict_deps.py` -> compile `PASSED` after ContextHub text-store leaf extraction.
- `uv run pytest tests/core/test_context_text_store.py tests/core/test_context_hub_strict_deps.py tests/core/test_belief_engine.py -q` -> `35 passed` after ContextHub text-store leaf extraction.
- `uv run scripts/ops/ci_gate.py --changed-only nexus/core/context_text_store.py nexus/core/context_hub.py tests/core/test_context_text_store.py tests/core/test_context_hub_strict_deps.py docs/testing/test_impact_map.md docs/plans/NEXUS_CLEAN_CODE_LINUS_REFACTOR_PLAN_2026-05-22.md "nexus_wiki_vault/06_Ops/Ops - Learning Closure Matrix.md"` -> changed-only gate `PASSED` after ContextHub text-store leaf extraction.
- `uv run scripts/ops/ci_gate.py` -> `ALL QUALITY GATES PASSED` after ContextHub text-store leaf extraction; CI emitted existing eval pass-rate warning but did not fail the gate.
- Research Flow RLM trace leaf 初次 RED：`tests/app/test_research_flow_service.py::test_research_flow_rlm_trace_module_writes_recursive_events` 與 `test_research_flow_service_keeps_rlm_trace_compatibility_alias` 失敗於 `ImportError: cannot import name 'rlm_trace' from 'nexus.research.flow'`，證明 RLM trace writer 還沒有 leaf Module。
- 修正：新增 `nexus/research/flow/rlm_trace.py`，提供 `safe_trace_slug(...)` 與 `write_research_rlm_trace(...)`；`research_flow_service.py` 保留 `_safe_trace_slug` / `_write_research_rlm_trace` physical aliases，runtime caller 不改。
- `uv run pytest tests/app/test_research_flow_service.py::test_research_flow_rlm_trace_module_writes_recursive_events tests/app/test_research_flow_service.py::test_research_flow_service_keeps_rlm_trace_compatibility_alias -q` -> `2 passed` after RLM trace leaf extraction.
- `python3 -m py_compile nexus/research/flow/rlm_trace.py nexus/app/research_flow_service.py tests/app/test_research_flow_service.py` -> compile `PASSED` after RLM trace leaf extraction.
- `uv run pytest tests/app/test_research_flow_service.py::test_research_flow_rlm_trace_module_writes_recursive_events tests/app/test_research_flow_service.py::test_research_flow_service_keeps_rlm_trace_compatibility_alias tests/app/test_research_flow_service.py::test_run_auto_flow_writes_rlm_trace_when_enabled tests/app/test_research_flow_service.py::test_run_auto_flow_writes_recursive_research_x_trace_when_enabled -q` -> `4 passed` after RLM trace leaf extraction.
- `uv run scripts/ops/ci_gate.py --changed-only nexus/research/flow/rlm_trace.py nexus/app/research_flow_service.py tests/app/test_research_flow_service.py docs/testing/test_impact_map.md docs/plans/NEXUS_CLEAN_CODE_LINUS_REFACTOR_PLAN_2026-05-22.md "nexus_wiki_vault/06_Ops/Ops - Learning Closure Matrix.md"` -> changed-only gate `PASSED` after RLM trace leaf extraction.
- `uv run scripts/ops/ci_gate.py` -> `ALL QUALITY GATES PASSED` after RLM trace leaf extraction; CI emitted existing eval pass-rate warning but did not fail the gate.
- Research runtime receipt skill-mount leaf 初次 RED：`tests/app/test_research_flow_service.py::test_research_receipt_runtime_module_builds_skill_mount_contract` 與 `test_research_flow_service_keeps_runtime_receipt_compatibility_aliases` 失敗於 `AttributeError: module 'nexus.app.research_receipt_runtime' has no attribute 'build_runtime_skill_mount_contracts'`，證明 runtime skill-mount contract logic 還留在 `research_flow_service.py`。
- 修正：`nexus/app/research_receipt_runtime.py` 新增 `build_runtime_skill_mount_contracts(...)`、`confirmed_skill_mount_receipt(...)`、`skill_mount_receipt_names(...)` 與 `SKILL_MOUNT_CAPABILITY_ALIASES`；`research_flow_service.py` 保留 `_build_runtime_skill_mount_contracts` / `_confirmed_skill_mount_receipt` / `_skill_mount_receipt_names` physical aliases。
- `uv run pytest tests/app/test_research_flow_service.py::test_research_receipt_runtime_module_builds_skill_mount_contract tests/app/test_research_flow_service.py::test_research_flow_service_keeps_runtime_receipt_compatibility_aliases tests/app/test_research_flow_service.py::test_runtime_skill_mount_contract_requires_confirmed_capability_receipt tests/app/test_research_flow_service.py::test_runtime_skill_mount_contract_blocks_unconfirmed_planned_mount tests/app/test_research_flow_service.py::test_runtime_skill_mount_contract_confirms_forecast_pregate_alias tests/app/test_research_flow_service.py::test_runtime_receipt_plan_prunes_unexecuted_judge_panel tests/app/test_research_flow_service.py::test_runtime_receipt_plan_adds_runtime_autoreason_success -q` -> `7 passed` after runtime skill-mount leaf extraction.
- `python3 -m py_compile nexus/app/research_receipt_runtime.py nexus/app/research_flow_service.py nexus/research/flow/rlm_trace.py tests/app/test_research_flow_service.py` -> compile `PASSED` after runtime skill-mount leaf extraction.
- `uv run pytest tests/app/test_research_flow_service.py::test_research_receipt_runtime_module_builds_skill_mount_contract tests/app/test_research_flow_service.py::test_research_flow_service_keeps_runtime_receipt_compatibility_aliases tests/app/test_research_flow_service.py::test_runtime_skill_mount_contract_requires_confirmed_capability_receipt tests/app/test_research_flow_service.py::test_runtime_skill_mount_contract_blocks_unconfirmed_planned_mount tests/app/test_research_flow_service.py::test_runtime_skill_mount_contract_confirms_forecast_pregate_alias tests/app/test_research_flow_service.py::test_runtime_receipt_plan_prunes_unexecuted_judge_panel tests/app/test_research_flow_service.py::test_runtime_receipt_plan_adds_runtime_autoreason_success tests/app/test_research_flow_service.py::test_research_flow_rlm_trace_module_writes_recursive_events tests/app/test_research_flow_service.py::test_research_flow_service_keeps_rlm_trace_compatibility_alias tests/app/test_research_flow_service.py::test_run_auto_flow_writes_rlm_trace_when_enabled tests/app/test_research_flow_service.py::test_run_auto_flow_writes_recursive_research_x_trace_when_enabled -q` -> `11 passed` after RLM trace + runtime skill-mount receipt leaves.
- `uv run scripts/ops/ci_gate.py --changed-only nexus/app/research_receipt_runtime.py nexus/research/flow/rlm_trace.py nexus/app/research_flow_service.py tests/app/test_research_flow_service.py docs/testing/test_impact_map.md docs/plans/NEXUS_CLEAN_CODE_LINUS_REFACTOR_PLAN_2026-05-22.md "nexus_wiki_vault/06_Ops/Ops - Learning Closure Matrix.md"` -> changed-only gate `PASSED` after RLM trace + runtime skill-mount receipt leaves.
- `uv run scripts/ops/ci_gate.py` -> `ALL QUALITY GATES PASSED` after RLM trace + runtime skill-mount receipt leaves; CI emitted existing eval pass-rate warning but did not fail the gate.
- Research semantic runtime receipt leaf 初次 RED：`tests/app/test_research_flow_service.py::test_research_semantic_runtime_module_writes_judge_panel_receipt` 與 `test_research_flow_service_keeps_semantic_runtime_compatibility_alias` 失敗於 `ImportError: cannot import name 'research_semantic_runtime' from 'nexus.app'`，證明 judge-panel / ASI / architecture scout / external doc scout / formal report runtime receipt augmentation 還沒有獨立 Module。
- 修正：新增 `nexus/app/research_semantic_runtime.py`，提供 `augment_semantic_runtime_capabilities(...)` 與 runtime receipt JSON helper；`research_flow_service.py` 保留 `_augment_semantic_runtime_capabilities` physical alias。
- `uv run pytest tests/app/test_research_flow_service.py::test_research_semantic_runtime_module_writes_judge_panel_receipt tests/app/test_research_flow_service.py::test_research_flow_service_keeps_semantic_runtime_compatibility_alias -q` -> `2 passed` after semantic runtime receipt leaf extraction.
- `uv run pytest tests/app/test_research_flow_service.py::test_research_semantic_runtime_module_writes_judge_panel_receipt tests/app/test_research_flow_service.py::test_research_flow_service_keeps_semantic_runtime_compatibility_alias tests/app/test_research_flow_service.py::test_auto_flow_writes_semantic_research_runtime_receipts tests/app/test_research_flow_service.py::test_auto_flow_keeps_external_doc_scout_rejected_only_diagnostic tests/app/test_research_flow_service.py::test_formal_report_includes_autoreason_discriminator_receipt -q` -> `5 passed` after semantic runtime receipt leaf extraction.
- `docs/reports/NEXUS_REFACTOR_REMAINING_START_EVIDENCE_2026-05-23.md` added remaining-item start evidence: SQLite second writer candidate is `SkillRegistry`; fixture live clone requires offline cache manifest and no-network tests; CLI candidate was `sandbox_actions.py` and is now completed; benchmark remains evidence-gated.
- P2A offline external fixture pregate 初次 RED：`tests/benchmark/test_fixture_materialization.py::test_live_external_fixture_adapter_requires_offline_cache_manifest` 等 nodeids 匯入 `ExternalFixtureCacheManifest` 失敗，證明 remote fixture cache manifest contract 尚不存在。
- 修正：新增 `ExternalFixtureCacheManifest` 與 `OfflineCachedExternalFixtureAdapter`；remote request 必須 match pinned repo/ref 並從 local cache materialize expected files。missing manifest、repo/ref mismatch、`network_allowed=True` 都 fail-closed，不執行 live clone/setup。
- `uv run pytest tests/benchmark/test_fixture_materialization.py::test_live_external_fixture_adapter_requires_offline_cache_manifest tests/benchmark/test_fixture_materialization.py::test_live_external_fixture_adapter_blocks_remote_without_allowlist tests/benchmark/test_fixture_materialization.py::test_offline_cached_external_fixture_adapter_materializes_allowlisted_cache -q` -> `3 passed` after offline external fixture pregate.
- P9 SQLite retry revalidation RED：`uv run pytest tests/core/test_memory_manager_sqlite_retry.py tests/infrastructure/test_sqlite_retry.py -q` 失敗於 `memory_manager` 沒有 `SQLiteRetryHandler` seam 與 `last_sqlite_retry_receipt`，證明 start-evidence report 宣稱的一 writer integration 與目前 checkout 不一致。
- 修正：`ProjectMemoryManager._execute_with_retry` 重新接入 `SQLiteRetryHandler`，並保留 `_is_retryable_sqlite_lock` compatibility wrapper 委派到 `is_retryable_sqlite_busy`。
- SkillRegistry second writer 初次 RED：`tests/test_skill_sharing.py::test_skill_registry_upsert_retries_sqlite_busy_then_success` 未寫入資料且只 log `database is locked`；`test_skill_registry_upsert_keeps_non_busy_errors_fail_fast` 未 raise，證明 `SkillRegistry.upsert` 仍吞掉 SQLite error 且沒有 retry receipt。
- 修正：`SkillRegistry.upsert` 與 `update_win_rate` 共用 `_execute_with_retry(...)`，透過 `SQLiteRetryHandler` 做 busy/locked-only retry；non-busy SQLite error 記錄後重拋，`last_sqlite_retry_receipt` 保留 evidence。
- `uv run pytest tests/test_skill_sharing.py::test_skill_registry_upsert_retries_sqlite_busy_then_success tests/test_skill_sharing.py::test_skill_registry_upsert_keeps_non_busy_errors_fail_fast -q` -> `2 passed` after SkillRegistry retry integration.
- `uv run pytest tests/test_skill_sharing.py tests/core/test_memory_manager_sqlite_retry.py tests/core/test_memory_manager_write_guard.py tests/infrastructure/test_sqlite_retry.py -q` -> `19 passed` after SQLite writer pair validation.
- P4 sandbox run 初次 RED：`tests/engine/test_sandbox_actions.py` 匯入 `scripts.engine.commands.sandbox_actions` 失敗，證明 `sandbox_run_cmd` runner dispatch 與 output schema 仍留在 Click command body。
- 修正：新增 `SandboxRunResult`、`run_sandbox_task(...)` 與 `render_sandbox_run_result(...)`；`nexus_cli.py::sandbox_run_cmd` 降為 thin adapter 並套 `translate_action_exceptions`。後續 `SandboxRunner.run_task(...)` 補上本地 workspace copy / command / cwd / output / cleanup / timeout / exit semantics；無 explicit command 與 path escape 仍 fail-closed。
- `uv run pytest tests/engine/test_sandbox_actions.py -q` -> `3 passed` after sandbox run Action extraction.
- P4 research auto-flow 初次 RED：Action tests 匯入 `ResearchAutoFlowResult` / `run_research_auto_flow` 時失敗，證明 `research:auto-flow` execution、preflight、completion 與 report write 仍留在 Click command body。
- P4 research auto-flow audit 初次失敗：semantic/artifact audits 仍要求 `build_completion_envelope` / `ensure_verified_completion` / `semantic_status` 在 Click block 內；Action extraction 後這些 token 應由 `research_actions.py` 擁有。
- 修正：新增 auto-flow Action result/renderers 與 injectable runner/preflight/session/completion seams；CLI 降為 thin adapter；audit 改為要求 CLI 呼叫 `run_research_auto_flow` 並在 Action module 檢查 completion/report/handoff tokens。
- P4 research auto-flow changed-only 初次失敗：`tests/engine/test_cli_research_seams.py` 缺 self row，selector fallback 拉進 `tests/core`，撞到本機 Playwright executable 缺失。
- 修正：補上 `tests/engine/test_cli_research_seams.py` 的 `test_contract` impact-map row，讓 research seam test edits 維持在自身測試。
- P4 research run 初次 RED：Action tests 匯入 `ResearchRunResult` / `run_research_run` 時失敗，證明 `research:run` governance、candidate lifecycle、completion、continuation 與 report write 仍留在 Click command body。
- P4 research run audit 初次失敗：semantic/artifact audits 仍要求 `build_completion_envelope` / `ensure_verified_completion` / `semantic_status` / `write_text` 在 Click block 內；Action extraction 後這些 token 應由 `research_actions.py` 擁有。
- 修正：新增 `ResearchRunResult`、`run_research_run` 與 renderer；CLI 降為 thin adapter；audit 改為要求 CLI 呼叫 `run_research_run` 並在 Action module 檢查 completion/report/handoff tokens。
- P4 live adapter sweep RED：`uv run pytest tests/engine/test_bench_actions.py tests/engine/test_code_actions.py tests/engine/test_multi_agent_actions.py tests/engine/test_learn_actions.py tests/engine/test_research_actions.py tests/engine/test_registry_actions.py tests/engine/test_sandbox_actions.py -q` 初次為 `66 passed, 29 failed`，失敗集中在 `nexus_cli.py` 沒有 expose/delegate `run_code_*`、`*_multi_agent_*`、`run_learn_*`、`run_research_*` Action seams。
- 修正：`nexus_cli.py` 匯入並委派 bench/code/multi-agent/learn/research Action functions 與 renderers；所有對應 command bodies 套用 `translate_action_exceptions`；`research:run` 舊內聯實作物理刪除，保留 thin adapter。
- `uv run pytest tests/engine/test_code_actions.py tests/engine/test_multi_agent_actions.py -q` -> `33 passed` after code/multi-agent live adapter wiring.
- `uv run pytest tests/engine/test_learn_actions.py -q` -> `30 passed` after learn/ask live adapter wiring.
- `uv run python -m py_compile scripts/engine/nexus_cli.py` -> compile `PASSED` after research adapter body deletion.
- `uv run pytest tests/engine/test_research_actions.py -q` -> `12 passed` after research live adapter wiring and `research:run` body deletion.
- `uv run pytest tests/engine/test_bench_actions.py tests/engine/test_code_actions.py tests/engine/test_multi_agent_actions.py tests/engine/test_learn_actions.py tests/engine/test_research_actions.py tests/engine/test_registry_actions.py tests/engine/test_sandbox_actions.py -q` -> `95 passed` after full CLI Action live-adapter sweep.
- Full gate Report Trust Audit 初次失敗：舊 source-token audits 仍要求 `build_completion_envelope(` / `write_text(` 留在 `nexus_cli.py` command blocks，與 Action extraction 後的深模組 seam 衝突；同時 `learn:ingest` wrapper 需把 CLI compatibility semantic evaluator seam 傳入 Action。
- 修正：`nexus_cli.py` 對 learn Actions 傳入 `_write_hallucination_evidence`、`_enforce_hallucination_gate`、`_write_dual_gate_markdown`、`_evaluate_learn_semantic_contract`；CLI semantic/artifact audits 改為 CLI block 驗證 delegate token、Action module 驗證 semantic/artifact token。
- `uv run pytest tests/engine/test_cli_semantic_contract_audit.py tests/engine/test_cli_artifact_gate_audit.py tests/test_cli_learn_mode.py::test_learn_ingest_fails_closed_when_semantic_contract_unverified -q` -> `5 passed` after Action-aware audit update.
- `uv run scripts/ops/ci_gate.py --changed-only scripts/engine/nexus_cli.py tests/engine/test_cli_semantic_contract_audit.py tests/engine/test_cli_artifact_gate_audit.py docs/testing/test_impact_map.md docs/plans/NEXUS_CLEAN_CODE_LINUS_REFACTOR_PLAN_2026-05-22.md docs/reports/NEXUS_REFACTOR_REMAINING_START_EVIDENCE_2026-05-23.md "nexus_wiki_vault/06_Ops/Ops - Learning Closure Matrix.md"` -> `Changed-Only JIT Tests PASSED`.
- `uv run scripts/ops/ci_gate.py` -> `ALL QUALITY GATES PASSED` after CLI live Action adapter sweep and Action-aware audit update.

剩餘 / 暫不打開：

- P2A 後續：external fixture 已有 injectable adapter seam、sandboxed local/file Adapter 與 offline cache manifest Adapter；預設仍由 `ExternalFixtureAdapterRequired` 或 offline manifest fail-closed。live clone/setup concrete adapter 仍未實作，除非後續有 live-network allowlist、socket/no-network barrier 與 cache provenance receipt 證明可控，否則不可打開外部下載。
- P3 後續：trial evidence artifact writer、socket barrier、direct provider failure policy、direct provider prompt/attribution/response normalization/invocation retry seam、with-Nexus prompt/live invocation/self-heal seam、evidence bundle gate builder、posture/x1/x3 gate helpers、payload final contracts/writer、rubric bundle、public cost accounting context、provider model-lock context、row-set context、manifest metadata context、payload header section、computed report/contract section、claim/posture section、telemetry completeness section、Nexus wearing context、wall-ledger bundle section、warning-clean section、posture-finalization section、top-level payload assembly 與 fixed mock telemetry fidelity snapshot 已完成；runner 仍是 benchmark orchestration facade。下一步只應在新的 failing evidence 下切更小的 side-effect orchestration seam，不再用 generic "split runner" 當任務。
- P4 後續：`nexus code impact/scan/context`、`nexus skills sync/list`、`nexus registry status`、`nexus bench effort`、`nexus sandbox run`、`nexus multi-agent metrics/create-task/start/status/audit/verify/close/integrate/submit`、`nexus learn:phase-policy`、`nexus learn:scheduler-status`、`nexus learn:phase-slo`、`nexus learn:phase-kpi`、`nexus learn:benchmark`、`nexus learn:converge`、`nexus ask`、`nexus learn:register-source`、`nexus learn:refresh`、`nexus learn:refresh-plan`、`nexus learn:report`、`nexus learn:ingest`、`nexus learn:gate`、`nexus research:route`、`nexus research:auto-flow`、`nexus research:run`、`nexus research:onboarding`、`nexus research:recommend-next`、`nexus research:packet`、`nexus research:log-from-last`、`nexus research:finalize-preview`、`nexus research:writeback-lessons`、`nexus research:human-report` 已搬入 Action modules 並套用 exception translation 或 equivalent Action seam。後續 CLI work 只應基於新的 audit/failing evidence 開小切片，不做一次性 broad CLI rewrite。
- P5 後續：policy loader deepening 的三個 planned leaf modules 已完成；後續只允許基於 failing policy-order / injection evidence 做更深拆，不做新的 generic policy abstraction。
