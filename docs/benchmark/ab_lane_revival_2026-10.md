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
| Gemini provider | The bare arm and the with-Nexus model path shell out to the `gemini` CLI (`NEXUS_GEMINI_BIN`, `which gemini`, `/Users/jameschen/.npm-global/bin/gemini`). Nothing in the lane calls the Gemini API with `GEMINI_API_KEY`. | None. See "Provider availability". |

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

Smoke with a provider (needs the `gemini` CLI and its credential; 12 tasks, 1 repeat, both arms, same model):

```bash
NEXUS_VALUE_HIDDEN_VERIFIER=1 \
NEXUS_GEMINI_MODEL_NAME=gemini-3-flash-preview \
NEXUS_DIRECT_GEMINI_MODEL=gemini-3-flash-preview \
NEXUS_GATEWAY_PROMPT_TRANSPORT=stdin NEXUS_GATEWAY_COMPACT_PROMPT=1 \
NEXUS_LLM_SELF_HEAL_ON_PYTEST_FAIL=1 NEXUS_BENCH_GATEWAY_TIMEOUT_SEC=300 \
NEXUS_BENCH_SUBPROCESS_PYTHON=$PWD/.venv/bin/python \
uv run python scripts/bench/capability_ab_runner.py \
  --tasks-file scripts/bench/public_benchmark_nexus_value_v1.json \
  --output-dir .nexus/reports/bench/ab_revival_$(date +%Y%m%dT%H%M%S) \
  --max-tasks 12 --repeat-trials 1 --timeout-sec 420 \
  --total-timeout-sec 7200 --stop-loss-sec 7200 --per-task-stop-loss-sec 600 \
  --difficulty all --repo-kind-filter all --force-flow hyper_sprint \
  --with-nexus-runner subprocess --with-llm-mode all --without-mode gemini \
  --require-same-model-baseline --strict-llm-baseline \
  --force-learn-slo-ready --neutralize-history --disable-learning-loop \
  --materialize-missing --isolation-mode preserve_target \
  --evidence-bundle --markdown-report auto --progress-log
```

For the full 12x2 replication use `--repeat-trials 2`. `.nexus/` is gitignored, so reports are not committed.

## Provider availability on this machine (2026-10-12)

- `GEMINI_API_KEY` is set, but the lane does not use it directly.
- `gemini` CLI: not on PATH, and `/Users/jameschen/.npm-global/bin/gemini` does not exist.
- `agy` exists, but it is an agent dispatcher (DevSpace profile flow), not the lane's Gemini CLI contract. Substituting it would change the arm under test, so it was not used.
- Local models are out of scope (M5-only policy).

Fail-closed check (no provider call made): `--without-only --without-mode gemini --require-same-model-baseline --strict-llm-baseline --max-tasks 2`
produced 2 rows with `infra_invalid_reason=cli_missing`, `eligible_n=0`, `solve_rate=null`. Note the top-level JSON `status` still says `SUCCESS` in that case; read `eligible_n`.

## Smoke result

Provider smoke: **not run: no usable provider** (Gemini CLI missing, see above). Rerun the provider command above once the CLI is installed.

Dry mode, 12 tasks, with-Nexus arm, `--with-llm-mode off --strict-llm-baseline` (origin/main + this change):

| Arm | Tasks | Eligible | Verified (semantic) | Counted solves | `deterministic_rescue` | Avg model calls | Avg wall |
| --- | --- | --- | --- | --- | --- | --- | --- |
| with_nexus (no LLM) | 12 | 12 | 12/12 | 0 | 12 | 0.0 | 5.6 s |
| bare Gemini | not run | | | | | | |

All 12 dry-mode successes are deterministic rescues and, correctly, score zero solves under the strict baseline. This is the
effect the ADRs warned about: without the flag the same run reports a 100% solve rate with no model involved.

## Comparison against May

| Run | Date | Nexus | Bare | Strict baseline | Source |
| --- | --- | --- | --- | --- | --- |
| P75 Flash 12x2 | 2026-05-05 | 24/24 | 14/24 | no | docs/benchmark/NEXUS_MAY_BENCHMARK_ROUTING_ANALYSIS.md |
| PUBLICATION_READY 12x2 | 2026-05-20 | 24/24 | 16/24 | no | docs/reports/NEXUS_PUBLICATION_READY_12X2_SUMMARY_2026-05-20.md |
| Pro 18x3 | 2026-04 | 54/54 | 51/54 | no | same routing analysis |
| Revival smoke, no LLM | 2026-10-12 | 0 counted (12 rescues) | not run | yes | this document |
| Revival smoke, Flash 12x1 | not run | n/a | n/a | yes | no Gemini CLI |

The May rows were produced without `--strict-llm-baseline`, and the publication summary records 0.9 s per row for Nexus,
which is consistent with a large share of `model_calls=0` rescues. They are not comparable with strict-baseline numbers until the lane is rerun with a provider.
