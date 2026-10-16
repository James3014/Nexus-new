# Same-model Gemini A/B lane revival (2026-10-12)

Issue: #1820. Claim ceiling: `AB_LANE_RUNNABLE_SMOKE_ONLY`. This document makes no uplift claim.

## Why this lane

It is the only legacy lane with a credible Nexus-vs-bare comparison on the same model.
No report existed after 2026-08, and the planner moved behind `install_alias` shims
on 2026-10-11/12 (dc49a17d1, 5a77d87f6, 352ecf680), so the lane had to be re-proven.

Runners: `scripts/bench/capability_ab_runner.py` (entry point),
`scripts/bench/direct_provider_runner.py` (bare Gemini arm),
`scripts/bench/with_nexus_runner.py` (library only: Codex with-Nexus attempt helper, no CLI, no strict flag of its own),
`scripts/bench/n30r_real_core_bridge.py` and `scripts/bench/public_credibility_phase_plan.py` (not on the A/B path).

## What was broken, what was fixed

| Finding | State on origin/main 0fb15f3e1 | Fix |
| --- | --- | --- |
| `CapabilityPlanner` / `shared_playbook_root` after the alias move | Not broken. The planner constructs and routes through the shims; the 12-task dry run completes. | None needed. |
| `x1_readiness_history.json` write | Crashes the whole run at the evidence-bundle step on a fresh checkout (`.nexus/reports/learn/` missing). | `_append_x1_readiness_history` creates the parent directory. Line-neutral edit, so the exact-base Ruff debt keys do not shift. |
| Subprocess arm | `uv run scripts/engine/nexus_cli.py` exits 78 ("Legacy commands are unavailable: install them with `uv sync --extra legacy`") in a fresh worktree, so every with-Nexus row silently FAILS. | No code change. Set `NEXUS_BENCH_SUBPROCESS_PYTHON` to a venv that has the legacy extra (or `uv sync --extra legacy`). |
| `--strict-llm-baseline` | Only forced a model baseline call and forbade local fallback. A `SUCCESS` with `model_calls == 0` (hidden-contract fast path, local rescue) still counted as a solve, which the ADRs forbid. | New `scripts/bench/strict_llm_baseline.py`; see below. |
| Gemini provider | The bare arm shells out to the `gemini` CLI, which is no longer usable. | New `agy` provider: `--without-mode agy`, `scripts/bench/agy_provider.py`. The `gemini` path is kept and is legacy. |
| With-Nexus arm model call | Blocked before any provider call: the unified runtime returns `workforce_admission_overall_decision_not_allow` ("workforce_bindings must be an object mapping", no resolved worker). | Not fixed. It needs a Workforce binding and admitted worker, which is a governance decision outside this change. See "With-Nexus arm". |

Pre-existing and untouched: 25 failures in `tests/benchmark/test_capability_ab_runner.py` fail identically on origin/main
(H5/H6 `collect_only` meta tests, H6 report-lock docs, `test_run_with_nexus_codex_provider_delivers_nexus_context`,
`test_nexus_with_local_model_adapter_alone_no_call`). 1407 pass on both base and branch.

## Strict-baseline semantics

Source: ADR-2026-05-07 teacher-student sweep plan and ADR-2026-05-08 route-cost measurement lessons.

With `--strict-llm-baseline`, after each arm finishes:

- A row with `status == SUCCESS` and `model_calls <= 0` (or missing) gets `solve_classification = "deterministic_rescue"` and `deterministic_rescue = true`.
- A `SUCCESS` with `model_calls > 0` is `model_solve`. Anything else is `not_solved`.
- The row `status` is not rewritten, so existing gates and receipts still see what happened.
- The per-arm summary reports `solved_n`, `deterministic_rescue_n`, and recomputes `solve_rate` and `first_pass_rate` from `model_solve` rows only. `strict_llm_baseline_applied` is true.
- Without the flag, summaries are unchanged and carry no rescue fields.
- This applies to both arms. A bare arm that cannot call a model therefore scores 0 solves under strict mode instead of passing visible tests for free.

A deterministic rescue is valid evidence of cost avoidance and local-first routing. It is not evidence that the model improved.

Tests: `tests/benchmark/test_ab_lane_revival.py` (fake rows for both arms, summary overlay, no-op without the flag,
`--parallel-arms smoke-only` on the 12-task fixture, and a real no-LLM run that must report 0 solves and all rescues).

## Commands

Fixture: `scripts/bench/public_benchmark_nexus_value_v1.json` (12 tasks), the same file the P16/P75 Flash 12x2 run used.
The May 12x2 command (docs/reports/GEMINI_FLASH_NEXUS_P16_P17_2026-05-05.md) did not pass `--strict-llm-baseline`;
the commands below add it.

Dry, no provider call (about 65 s). This is the CI-covered mode:

```bash
export NEXUS_BENCH_SUBPROCESS_PYTHON=$PWD/.venv/bin/python
uv run python scripts/bench/capability_ab_runner.py \
  --tasks-file scripts/bench/public_benchmark_nexus_value_v1.json \
  --output-dir .nexus/reports/bench/ab_revival_dry_$(date +%Y%m%dT%H%M%S) \
  --max-tasks 12 --repeat-trials 1 --nexus-only --with-llm-mode off \
  --strict-llm-baseline --difficulty all --repo-kind-filter all \
  --materialize-missing --isolation-mode preserve_target \
  --neutralize-history --disable-learning-loop \
  --with-nexus-runner subprocess --evidence-bundle
```

Provider smoke through `agy` (12 tasks, 1 repeat, both arms; sends the task source and visible tests to Gemini 3.8 Flash):

```bash
NEXUS_VALUE_HIDDEN_VERIFIER=1 NEXUS_GATEWAY_PROMPT_TRANSPORT=stdin NEXUS_GATEWAY_COMPACT_PROMPT=1 \
NEXUS_LLM_SELF_HEAL_ON_PYTEST_FAIL=1 NEXUS_BENCH_GATEWAY_TIMEOUT_SEC=300 \
NEXUS_BENCH_SUBPROCESS_PYTHON=$PWD/.venv/bin/python \
uv run python scripts/bench/capability_ab_runner.py \
  --tasks-file scripts/bench/public_benchmark_nexus_value_v1.json \
  --output-dir .nexus/reports/bench/ab_revival_agy_$(date +%Y%m%dT%H%M%S) \
  --max-tasks 12 --repeat-trials 1 --timeout-sec 420 \
  --total-timeout-sec 7200 --stop-loss-sec 7200 --per-task-stop-loss-sec 600 \
  --difficulty all --repo-kind-filter all --force-flow hyper_sprint \
  --with-nexus-runner subprocess --with-llm-mode all --without-mode agy \
  --require-same-model-baseline --strict-llm-baseline \
  --force-learn-slo-ready --neutralize-history --disable-learning-loop \
  --materialize-missing --isolation-mode preserve_target \
  --evidence-bundle --markdown-report auto --progress-log
```

`--without-mode agy` binds both arms to one model through `NEXUS_AGY_MODEL`
(default `gemini-3.8-flash-medium`) and sets `NEXUS_GEMINI_MODEL_NAME` and `NEXUS_DIRECT_GEMINI_MODEL` to it,
so `--require-same-model-baseline` still checks one identity. The legacy form used `--without-mode gemini`.

For the full 12x2 replication use `--repeat-trials 2`. `.nexus/` is gitignored, so reports are not committed.

## Provider: agy (2026-10-12)

The `gemini` CLI is no longer usable (not installed). The lane now reaches Gemini through `agy` print mode.

- Model ids from `agy models`: `gemini-3.8-flash-high`, `gemini-3.8-flash-medium`, `gemini-3.8-flash-low` (also 3.7 and 3.6 Flash tiers and 3.1 Pro).
  The dispatch skill (`devspace-agy-gemini-dispatch`) governs DevSpace `agent_start` dispatch and documents neither a CLI invocation nor a Flash 3.8 tier,
  so the tier is a choice: the default is `gemini-3.8-flash-medium`, overridable with `NEXUS_AGY_MODEL`.
- Invocation per task: `agy --new-project --mode plan --model <id> --output-format json --print-timeout <n>s --print <prompt>`,
  run in an empty temporary directory. No permission bypass, no repository checkout visible, no carried conversation.
  Following the skill, containment is stated as request-only: this is plan mode in an empty directory, not a proven physical sandbox.
- Output: `{"status","response","usage":{"total_tokens",...},"conversation_id"}`. `response` must be the JSON `{status, patch}` the prompt asks for.
  Tokens are provider-measured (`gateway_token_source=usage_metadata`). A billed but unparsable answer is a model failure (`parse_failure`, tokens kept), not infra.
- Failure classes: missing agy gives `infra_invalid_reason=agy_missing` with `model_calls=0`; non-zero exit is `cli_error`; the timeout is `timeout`. No fallback to another provider or a local model.
- `GEMINI_API_KEY` is not used.

### With-Nexus arm

The with-Nexus model call goes through `sprint_service` and the unified runtime. In this checkout every such call is refused before any provider call:
`workforce_admission_overall_decision_not_allow`, reason "demand_online: workforce_bindings must be an object mapping", no resolved worker, `provider_call_count=0`.
`nexus/config/model_workforce.yaml` also registers only `agy_flash` (3.6 high), `agy_flash_medium` (3.6 medium) and `agy_flash_37_medium`, no Gemini 3.8 Flash worker.
Admitting the lane is a Workforce governance change and was not attempted here (since done in #1836; the bindings input is addressed in the 2026-10-12 rerun section below). The rows show up as `model_call_without_tokens` (the row still records `model_calls=1` because the
runner counts the attempt before the runtime refuses; no provider call was made). Only tasks that the deterministic local path solves without a model complete, and those are exactly the `deterministic_rescue` rows.

## Smoke result

Provider smoke, 2026-10-12, `gemini-3.8-flash-medium` through agy, P16 fixture (12 tasks), 1 repeat, `--require-same-model-baseline --strict-llm-baseline`.
Report: `.nexus/reports/bench/ab_revival_agy_final_*` (gitignored).

| Arm | Rows | Eligible | Verified (counted solves) | `deterministic_rescue` | Infra invalid | Avg model calls | Avg wall | Avg tokens |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| bare agy Gemini 3.8 Flash | 12 | 12 | 6 (50.0%) | 0 | 0 | 1.0 | 44.8 s | 34,201 |
| with_nexus | 12 | 2 | 0 | 2 | 10 (`model_call_without_tokens`, Workforce Admission block) | 0.0 | 9.7 s | n/a |

- Bare arm solved hidden-001, hidden-002, gov-001, evidence-001, evidence-002 and trust-001; the other six failed the verifier (`pytest_failed` or no mutation).
- The two eligible with-Nexus rows (repair-001, repair-002) are verified but made no model call, so strict mode counts them as `deterministic_rescue`, not solves.
- A first run of the same command (before keeping tokens on unparsable answers) gave the bare arm 5/9 eligible and 3 `parse_error` rows. Model output is not deterministic, so single 12x1 runs vary.
- No same-model uplift can be read from this run: the with-Nexus arm did not reach the model.

Dry mode, 12 tasks, with-Nexus arm, `--with-llm-mode off --strict-llm-baseline`:

| Arm | Tasks | Eligible | Verified | Counted solves | `deterministic_rescue` | Avg model calls | Avg wall |
| --- | --- | --- | --- | --- | --- | --- | --- |
| with_nexus (no LLM) | 12 | 12 | 12/12 | 0 | 12 | 0.0 | 5.6 s |

Without the strict flag the dry run would report a 100% solve rate with no model involved, the effect the ADRs warned about.

## Rerun with the workforce_bindings fix (issue #1844, 2026-10-12)

Cause of `workforce_bindings must be an object mapping`: the with-Nexus model path (`LLMCandidateGenerator._ask_unified_candidate` in
`nexus/research/sprint_service.py`) builds its route with `build_online_route(...)`, which carries no `workforce_bindings`, and the unified runtime
(`nexus_runtime` `runtime_workforce_admission`, exact per-channel lookup, no default or inference) refuses a route whose bindings are not a mapping.
Since #1836 registered `agy_flash_38` the only missing input was lane-side.

Fix (no admission bypass, no worker id supplied by the lane):

- `scripts/bench/agy_provider.configure_agy_lane_env` now also sets `NEXUS_OAUTH_PROVIDER=agy` (the with-Nexus subprocess gateway otherwise auto-selects the uninstalled `gemini` CLI)
  and `NEXUS_BENCH_WORKFORCE_BINDINGS_JSON={"online": {"provider": "agy", "model": "<NEXUS_AGY_MODEL>", "controls": [task_card, allowed_files, mandatory_commands, parser, verifier, independent_verification]}}`.
- `sprint_service` forwards that mapping as `route["workforce_bindings"]` when the env var is set (no other behavior change). Admission resolves the exact provider+model identity to `agy_flash_38`.
  An unregistered model id is BLOCKed by admission; it is never substituted.
- Test: `tests/benchmark/test_ab_lane_with_nexus_agy.py` (fake `agy` executable): with the bindings the row is `ALLOW`, resolves `agy_flash_38`, `provider_call_count >= 1`, and the fake agy receives `--model gemini-3.8-flash-medium`;
  without them the runtime still refuses with the mapping reason before any provider call.

Result of the exact 12x1 strict command (same command as above, `NEXUS_AGY_MODEL=gemini-3.8-flash-medium`). Report: `.nexus/reports/bench/ab_revival_agy_20261012_full` (gitignored).

| Arm | Rows | Eligible | Verified (counted solves) | `deterministic_rescue` | Infra invalid | Avg model calls | Avg wall | Avg tokens |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| bare agy Gemini 3.8 Flash | 12 | 12 | 7 (58.3%) | 0 | 0 | 1.0 | 65.5 s | 29,689 |
| with_nexus | 12 | 2 | 0 | 2 | 10 (`model_call_without_tokens`, see below) | 0.0 | 10.1 s | n/a |

The with-Nexus arm is still blocked, now one stage later and for a reason outside the lane. For all 10 model-required rows Workforce Admission returns
`ALLOW` ("demand_online: All constraints and required controls passed"), and the gateway then refuses the call with Online execution authorization
`online_denied_by_workspace_or_default` (`nexus/services/online_execution_policy.py`: no `.nexus/online_execution_policy.json` and no task-level `auto|require`, so the fail-closed default is deny).
`provider_call_count=0`; the rows record `model_calls=1` because the runner counts the attempt before the refusal. Granting Online authorization is an owner decision
(workspace policy file, or the operator override `NEXUS_EXTERNAL_RUNTIME_AUTHORIZED=1`); it was not set or worked around here, and no other model was used.

Capabilities recorded by the with-Nexus receipts (`capability_receipts` in the evidence bundle rows; `real` = `claim_boundary.simulated=false`):

| Task | Status | Invoked with a gate pass | Invoked, gate failed or not passed (simulated) | Selected, not invoked |
| --- | --- | --- | --- | --- |
| repair-001, repair-002 | SUCCESS, rescue | `delivery_gate` (real), `hyper` (real), `codeintel`, `harness_preflight_sensor`, `hyper` (simulated); repair-002 also `memory` | `artifact_gate`, `claim_gate`, `delivery_gate`, `mempalace_gate` | `repair_loop`, `research_route` |
| hidden-001, hidden-002 | FAILED | `harness_preflight_sensor` (simulated) | `artifact_gate`, `claim_gate`, `delivery_gate`, `mempalace_gate` | none |
| context-001, context-002 | FAILED | `codeintel` (real), `harness_preflight_sensor` (simulated) | `artifact_gate`, `claim_gate`, `delivery_gate`, `mempalace_gate` | context-002: `direct_mode`, `memory`, `research_route` |
| evidence-001, evidence-002, trust-001, trust-002, gov-001, gov-002 | FAILED | `codeintel`, `harness_preflight_sensor` (both simulated) | `artifact_gate`, `claim_gate`, `delivery_gate`, `mempalace_gate` | `hyper`, `research_route`, `plan_quality_gate`, `pregate`, plus per task `acceptance_check`, `jit_validation`, `learn_mode`, `learn_phase_slo`, `sandbox`, `ultra_review`, `semantic_searcher` |

Only the repair rows contain real (non-simulated) capability invocations (`delivery_gate`, `hyper`), and they made no model call. In every failed row the model never ran, so
`expected_capabilities` coverage reports `claim_gate`/`delivery_gate` as missing (`missing_verifier_artifact;missing_source_hash`). This is a smoke run: no public uplift claim,
and no same-model uplift can be read until Online authorization lets the with-Nexus arm reach the model.

## Comparison against May

| Run | Date | Nexus | Bare | Strict baseline | Source |
| --- | --- | --- | --- | --- | --- |
| P75 Flash 12x2 | 2026-05-05 | 24/24 | 14/24 | no | docs/benchmark/NEXUS_MAY_BENCHMARK_ROUTING_ANALYSIS.md |
| PUBLICATION_READY 12x2 | 2026-05-20 | 24/24 | 16/24 | no | docs/reports/NEXUS_PUBLICATION_READY_12X2_SUMMARY_2026-05-20.md |
| Pro 18x3 | 2026-04 | 54/54 | 51/54 | no | same routing analysis |
| Revival smoke, no LLM | 2026-10-12 | 0 counted (12 rescues) | not run | yes | this document |
| Revival smoke, Gemini 3.8 Flash via agy, 12x1 | 2026-10-12 | 0 counted (arm blocked by Workforce Admission, 2 rescues) | 6/12 (50.0%) | yes | this document |
| Rerun after the bindings fix, Gemini 3.8 Flash via agy, 12x1 | 2026-10-12 | 0 counted (admission ALLOW, then Online authorization denied, 2 rescues) | 7/12 (58.3%) | yes | this document |

The May rows were produced without `--strict-llm-baseline`, and the publication summary records 0.9 s per row for Nexus,
which is consistent with a large share of `model_calls=0` rescues. They are also a different model (Gemini 3 Flash preview) and 2 repeats. They are not comparable with strict-baseline numbers until the with-Nexus arm can reach the model.

## Strict mode v2: simulated capabilities do not count

Issue #1856. `--strict-llm-baseline` already refused to count a `model_calls == 0` success as a model solve. v2 does the same for capabilities:
a with-Nexus row only counts as "Nexus-exercised" when at least one capability receipt is real.

### Rule

For every with-Nexus row, each selected capability receipt in `capability_receipts` is classified (`scripts/bench/strict_llm_baseline.py`):

- `selected_not_invoked`: selected by the planner, `invoked` is false.
- `real`: invoked, `claim_boundary.simulated` is not true, and `evidence_refs` is non-empty.
- `simulated`: any other invoked receipt (`simulated == true`, or no evidence refs).

`claim_boundary` is read from `receipt_base.claim_boundary` (or a top-level `claim_boundary`). A receipt with no claim_boundary at all makes no simulated claim,
so it is counted `real` when it has evidence refs, but its name is also listed in `capabilities_real_unattested` and the summary reports
`attested_real_capability_rows_n` (rows with a real capability that carries an explicit `simulated=false`) next to `real_capability_rows_n`.
Such receipts come from runner-side telemetry backfill and `deterministic_receipt_lite`, not from the receipt engine.

Row fields: `capabilities_real`, `capabilities_real_unattested`, `capabilities_simulated`, `capabilities_selected_not_invoked`,
`capability_not_exercised` (`capabilities_real` is empty), `solve_without_capability` (verified model solve with `capability_not_exercised`).
Row `status` and `solve_classification` are never rewritten.

With-Nexus arm summary fields: `real_capability_rows_n`, `attested_real_capability_rows_n`, `simulated_only_rows_n` (no real capability, at least one simulated),
`capability_not_exercised_rows_n`, `capability_tally` (`{capability: {real, simulated, selected_not_invoked}}`), `solves_with_real_capability_n`,
`solve_without_capability_n`, `nexus_uplift_solved_n` / `nexus_uplift_solve_rate` (verified model solves with a real capability, over eligible rows).
`solved_n` keeps its meaning. Tallies cover all with-Nexus rows including infra-invalid ones (they still tell what the receipts were); solve figures cover eligible rows.
Nothing changes without `--strict-llm-baseline`, and the without-Nexus arm gets no capability fields.

### Why receipts are simulated

Not a runner switch. `claim_boundary.simulated` defaults to `True` (fail-closed) in `nexus_runtime.planning.evidence.claim_boundary.ClaimBoundary`
(`nexus/evidence/claim_boundary.py` aliases it). In the bench path the receipts come from `build_trace_receipts` (`nexus/engine/capability_receipts.py`) ->
`CapabilityReceipt.to_dict()` in `nexus_runtime.planning.engine.capability_contracts` (pin `cfcb38d`), which always projects `receipt_base` with
`claim_boundary={"public_claim_allowed": False}`; `ClaimBoundary.from_dict` fills every other field from its defaults, so `simulated=true`, `receipt_present=false`,
`claim_eligible=false`, `model_calls=0` for every receipt it emits, whatever the runner flags. The receipt's own `invoked`, `gate_passed` and `evidence_refs` are independent of that field.
`nexus/engine/capability_receipt_adapters.py`, `with_nexus_runner.py` and `capability_ab_runner.py` never set `simulated`. The only `simulated=False` producers in Nexus-new are
`nexus/delivery/report_claims.py`, `nexus/evidence/dedupe_aggregator.py` and `formal_fused_projection`, none on this path.
The policy/switch candidates were checked and are not the cause: `capability_runtime_policy`/`dry_run` appears only as `capability_plan_mode="dry_run"` (planner mode, a plan field),
`NEXUS_ULTRA_REVIEW_DRY_GATE=1` is set at `capability_ab_runner.py:4023` for the ultra_review gate only, and `--with-llm-mode off` does not touch it
(the dry-mode run below has the same simulated receipts as the agy run). Making receipts carry `simulated=false` would need the receipt producer
(nexus-runtime `CapabilityReceipt.to_dict`) to pass an evaluated claim boundary; that behavior was not changed here.

### Re-reading historical reports

`python scripts/bench/strict_llm_baseline.py --reclassify <report_dir>` re-reads `*.jsonl` rows and prints the strict tallies as JSON (no rerun, no provider call).

| Report | With-Nexus rows | Real cap. rows | of which explicit `simulated=false` | Simulated-only rows | Counted model solves | Uplift solves |
| --- | --- | --- | --- | --- | --- | --- |
| agy 12x1 (`ab_revival_agy_20261012_full`) | 12 | 4 (repair-001/002: `delivery_gate`+`hyper`; context-001/002: `codeintel`) | 0 | 8 | 0 (2 `deterministic_rescue`) | 0 |
| dry, `--with-llm-mode off` (`ab_revival_dry_20261012T115733`) | 12 | 12 | 0 | 0 | 0 (12 `deterministic_rescue`) | 0 |

Agy run per-capability `{real, simulated, selected_not_invoked}`: `artifact_gate` {0,12,0}, `claim_gate` {0,12,0}, `harness_preflight_sensor` {0,12,0}, `mempalace_gate` {0,12,0},
`delivery_gate` {2,10,0}, `codeintel` {2,8,0}, `hyper` {2,0,6}, `research_route` {0,0,9}, `acceptance_check`/`jit_validation`/`plan_quality_gate`/`pregate` {0,0,4} each,
`repair_loop`/`sandbox`/`ultra_review` {0,0,2} each, `memory` {0,1,1}, and one selected-not-invoked each for `direct_mode`, `learn_mode`, `learn_phase_slo`, `semantic_searcher`.
All 4 "real" rows are backfill receipts without any claim_boundary; none of the 12 rows has a capability receipt that explicitly attests `simulated=false`.
The 4 context/repair `codeintel` and `hyper` receipts are real in the sense of carrying evidence refs (scan reports, hidden verifier), and codeintel on the two context rows
is real even though those rows FAILED at the model step; this is why real-capability rows are not the same as solves.
In the dry run the 12 "real" rows come from backfilled `claim_gate`/`delivery_gate`/`artifact_gate`/`mempalace_gate`/`codeintel`/`memory`/`hyper` receipts on rows solved by the
deterministic path with no model, so they remain `deterministic_rescue`, never uplift.

May 2026 reports (the 24/24 results): no `with_nexus_*.jsonl`/`summary*.json` report directory from May exists on this host
(`find` over Nexus-new and nexus found only `.nexus/reports/bench/wave34/wave34_run_1789877609.json`, a 2026-09-20 `--with-llm-mode off` run summary, not a May report, with no per-row receipts; `.nexus/` is gitignored).
They cannot be reclassified here; by the mechanism above any run on the pinned runtime had simulated receipts for the engine-built capabilities, so their with-Nexus figures should be
read as not capability-attributed until re-read with `--reclassify` against a surviving report.

## Bench path precheck (counted runs, 2026-10-16)

nexus-runtime (e73d152f1) renders the resolved run root into the with-Nexus `[NEXUS MODEL CONTEXT]` block. That run root is an absolute path inside the bench worktree. The prompt symmetry audit rejects a Nexus-block string that:
- is not a plain absolute path (`abs_path`: `^/[A-Za-z0-9_./-]+$`);
- is longer than 120 characters (`MAX_JSON_STRING_CHARS`);
- contains a hidden-only word, line or literal of the task, in the string itself or in any decoded variant (percent, base64 or hex).

Any of these voids the whole counted run (`nexus_block_string_not_allowed`), and only after the paid calls. Example: `main` is hidden-only for hard_v1 `oabh-remote`.

`capability_ab_runner` now checks the bench paths with the audit's own functions (`scripts/bench/bench_path_precheck.py`) before any subprocess starts: confinement parity, persistent worker and legs. The audit itself is unchanged. For a counted run (`--counted-first-attempt` with model calls) it refuses to start with exit code 2.

- **Paths checked for format, length and hidden text.** These are the paths that get rendered:
  - the repo root, which is the location of the runner's checkout. It is checked as the runner's unresolved module path, as the cwd, and resolved.
  - the default run root the executor registry derives for every task id (`_resolve_run_root`: `<repo>/.nexus/runtime/<task id>`).
- **Path checked for hidden text only.** The output dir.
- **Fixtures.** A fixture that cannot be read is reported with its task id; it is never skipped.
- **Messages.** A message prints the task id, the path, and the single offending word. A literal or line is reported only as its length and a sha256 prefix, never as text.

To fix a refused run, move the runner checkout or `--output-dir` (or rename the task) so that the reported path no longer carries the word or character.
