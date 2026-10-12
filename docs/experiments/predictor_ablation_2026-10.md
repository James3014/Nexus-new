# Predictor ablation: `latent_predictor_v20` and `lewm_predictor` (2026-10)

Issue: James3014/Nexus-new#1822. Runner: `scripts/eval/run_predictor_ablation.py`.
Run: `artifacts/runtime/predictor_ablation/20261012T040008Z/` (untracked; `rows.jsonl`, `scorecard.json`).

## Result in one paragraph

Neither predictor is on the local-heal path. In 96 local-heal attempts (24 fixtures x 4 arms) the
predictors were consulted 0 times, so the pass-count differences between arms (21 / 21 / 23 / 22)
are model run-to-run noise, not a predictor effect. On the sites where the predictors do sit, fed
with the same 24 fixture problem statements and the real predictors, the latent predictor was
consulted 48 times per arm and the LeWM predictor 24 times per arm, and `changed_decision` was true
0 times for both. Measured on these fixtures, both predictors are inert: they never altered a
decision. That is not evidence that they are harmless in general; it is evidence that the
fixtures never trigger them (see "Why they are inert").

## What each predictor is

Neither is a trained neural model in the code that runs today.

- `LatentPredictorV20` (`nexus/learning/latent_predictor_v20.py`).
  - `forecast_roi(task_desc)`: queries `VectorRAG` for up to 5 similar past missions and averages
    `metadata.actual_tokens`. `roi_score = clamp(1 - avg_tokens / 10000, 0.1, 1.0)`. With no history it
    returns a cold-start constant: `est_tokens=1500`, `roi_score=0.5`, `confidence="LOW"`.
  - `predict_risk(task_desc)`: a substring list (`subprocess`, `rm -rf`, `hardcode`, `NexusState`).
    `reject_prob = 0.05 + 0.4 per hit`, capped at 0.99. No `torch` import.
- `LeWMPredictor` (`nexus/learning/lewm_predictor.py`). A singleton. `simulate()` returns
  `SKIPPED` unless `torch` imports and a checkpoint file over 1 KiB exists at a hard-coded path.
  Even then the checkpoint is not loaded (`torch.load` is commented out). The verdict is a keyword
  test on the patch text (`state_contracts`, `core/state`, `serialization`, `high-risk`, `NexusState`):
  a hit gives `REJECTED` (cost 0.95), otherwise `PASSED` (cost 0.05).

## Per-site analysis

| Site | Predictor | Decision it can change | If absent |
| --- | --- | --- | --- |
| `ForecastGateService.evaluate` (`nexus/engine/forecast_gate_service.py`), called from `Coordinator._execute_task_workflow` and from `_exec_forecast_gate` in `nexus/core/capability_executor_registry.py` | latent | Go / no-go of the whole task. When the state carries no `roi_score`, the forecast and risk come from the predictor and go to `GateEvaluator.should_proceed("D", ...)`. It rejects on `roi < 0.5`, `reject_prob > 0.8` or a cost rule chain. A rejection returns `proceed=False` (the coordinator returns without working) and triggers the ASH selector. | No forecast: the preflight passes. Metadata overrides (`roi_score`, `forecast_tokens`, `reject_prob`) already bypass the predictor. |
| `SelfHealingSelector.rank_strategies` (`nexus/engine/self_healing_selector.py`), reached from the gate on rejection | latent | Candidate ranking and the selected repair strategy. `success_prob = strategy.success_base * roi_score`, times `(1 - reject_prob)` when risk is `CAUTION`. | Ranked by the matrix prior `success_base` alone. |
| `RepairAttemptService._run_lewm_sim` (`nexus/engine/repair_attempt_service.py`), start of `execute_attempt` | lewm | Abort or continue the repair attempt. `REJECTED` returns `status=abort` before any patch work. Runs only if `state.metadata["sim_lewm"]` is truthy. | The attempt continues. |
| `AutonomicRoutingService.apply` to `AutonomicRouter.route` | latent (indirect) | The forecast dict is passed to the router as `forecast`. With the default `NEXUS_ROUTING_V4_HARDENED=0` the router reads only `est_tokens` from it for metadata, so the route is unchanged. With V4 hardened on, `route()` does `float(forecast["confidence"])`; the latent forecast carries `"LOW"`/`"MEDIUM"`/`"HIGH"`, so it raises `ValueError` (reproduced). | The forecast is `{}` and the router uses its defaults. Not instrumented: calling `route` twice has side effects. |
| `Coordinator.__init__`, `build_engine_components` (`nexus/engine/coordinator.py`, `nexus/engine/bootstrap.py`) | latent | None. Construction and wiring of the forecaster, which goes to the gate. `bootstrap.py` also imports `LeWMPredictor` without using it. | n/a |

Findings that follow from the code:

- Nothing in the repo sets `sim_lewm` outside tests and the audit schema. In production the LeWM
  predictor is never consulted by `RepairAttemptService`, and its simulator would return `SKIPPED`
  anyway on a machine without the checkpoint.
- The latent predictor's influence is limited to the preflight gate, the ASH ranking and (latent
  bug) the V4 router path. The gate can only reject on a high-token history (`avg_tokens > 5000`) or
  on two or more risk substrings in the task description.
- The local-heal pipeline (`nexus/services/local_heal/`) never imports either predictor.
- The default ASH matrix on a checkout without `.nexus/ash_matrix.yaml` has `replan_swarm`
  failing to resolve (`Unknown command ref: replan`), so that strategy is skipped during ranking. This
  is existing behaviour, left unchanged.

## Switches

| Predictor | Env var | Default | Off values |
| --- | --- | --- | --- |
| `latent_predictor_v20` | `NEXUS_LATENT_PREDICTOR` | on | `0`, `false`, `no`, `off` |
| `lewm_predictor` | `NEXUS_LEWM_PREDICTOR` | on | `0`, `false`, `no`, `off` |

Helpers are in `nexus/learning/predictor_toggle.py`. Off means the site takes the path it takes
without the module:

- Gate: no forecast; `proceed=True`, `reason="latent_predictor_disabled"`, `GateEvaluator` not called.
- ASH selector: `success_prob = success_base`, `prediction=None`, `risk_status="NOT_EVALUATED"`.
- `_exec_forecast_gate` and `get_self_healing_selector`: `LatentPredictorV20` is not constructed.
- LeWM: the simulator is not constructed or called; the attempt continues.

`Coordinator.__init__` and `bootstrap.py` are unchanged: they still construct the forecaster, but the
gate and selector do not consult it when the switch is off.

## Receipt visibility

Each site appends an entry to `state.metadata["predictor_influence"]` (a list) and to a bounded
process ledger (`drain_ledger()`, used by the ablation runner):

```
{name, enabled, consulted, changed_decision, before, after, site}
```

`before` is the decision without the predictor and `after` is the decision taken, so
`changed_decision = consulted and before != after`. Gate: `{"proceed": True}` vs the verdict.
Selector: top strategy by prior vs top strategy after prediction (plus `before_order` and
`after_order`, also in the `trigger_ash` result). LeWM: `continue` vs `continue`/`abort`. The
forecast-gate capability receipt carries the list at `outcome.predictor_influence`.

Tests: `tests/engine/test_predictor_toggle.py` (flag on/off per site, off equals the no-module
path, `changed_decision` on a fixture that changes the decision and on one that does not) and
`tests/eval/test_predictor_ablation.py`.

## Method

Arms, memory off in all of them, baseline `both_off`:

| Arm | `NEXUS_LATENT_PREDICTOR` | `NEXUS_LEWM_PREDICTOR` |
| --- | --- | --- |
| `both_on` | on | on |
| `latent_off` | off | on |
| `lewm_off` | on | off |
| `both_off` | off | off |

- Tasks: `scripts/eval/memory_ab_tasks_v3`, 24 fixtures. Model: `incoai/Qwen3.6-35B-A3B-Splash`
  (the round-9 model of the memory A/B record) through the M5 Ollama tunnel at
  `http://127.0.0.1:11434`. No model was started on the M4.
- Phase 1, local heal: the harness helpers of `run_memory_ab_v1.py` (imported, not modified), memory arm
  `off`. The process ledger counts predictor consultations on this path.
- Phase 2, decision-site probe, no model call: each fixture's problem statement goes through the
  gate (real `LatentPredictorV20`, real `GateEvaluator`), `rank_strategies`, and `_run_lewm_sim` with
  `sim_lewm` forced on. This is the only way to exercise those sites with the fixtures, since local
  heal does not reach them.
- Scoring: `nexus_learning.effectiveness_measurement` (`paired_memory_uplift`,
  `compare_workflows_at_required_quality`, `replay_scorecard`). The paired helper pairs a
  `memory_on` slot with a `memory_off` slot; each arm is relabelled into the `memory_on` slot against
  `both_off` in the `memory_off` slot. Memory is off in both.

## Results

Run `20261012T040008Z`, 96 attempts, 370 model calls.

Consultation and decision change (24 fixtures per arm; the latent predictor has two sites, the gate
and the selector, so 48 entries per arm):

| Arm | Path | latent consulted | latent changed_decision | lewm consulted | lewm changed_decision |
| --- | --- | --- | --- | --- | --- |
| both_on | local heal | 0 | 0 | 0 | 0 |
| both_on | decision-site probe | 48 | 0 | 24 | 0 |
| latent_off | local heal | 0 | 0 | 0 | 0 |
| latent_off | decision-site probe | 0 | 0 | 24 | 0 |
| lewm_off | local heal | 0 | 0 | 0 | 0 |
| lewm_off | decision-site probe | 48 | 0 | 0 | 0 |
| both_off | local heal | 0 | 0 | 0 | 0 |
| both_off | decision-site probe | 0 | 0 | 0 | 0 |

Local-heal outcome (independent repro re-run), 24 fixtures per arm:

| Arm | Passed | Paired uplift vs `both_off` (eligible / denominator) |
| --- | --- | --- |
| both_on | 21 | 0 / 24 |
| latent_off | 21 | 0 / 24 |
| lewm_off | 23 | 1 / 24 |
| both_off | 22 | baseline |

`uplift_claimable` is false for every arm. The flips (`greedy_regex_multiline-a` and
`shallow_copy_nested-a`) cannot come from a predictor, because the predictors were consulted 0
times on this path. They are run-to-run variance of the 35B model, the same effect recorded for the
M5 model in the memory A/B record.

### Why they are inert

None of the 24 fixture problem statements contains any of the risk substrings of either predictor, so
the keyword risk checks never fire. The checkout has no mission history, so the latent forecast is the
cold-start constant `roi_score=0.5`, which is not below the 0.5 threshold. The LeWM simulator returns
`SKIPPED` on this host (no checkpoint, no `torch`). A history with large token averages, or task text
containing two risk substrings, would change the gate; that is covered by the unit tests, not by this run.

## Limits

- Fixtures are synthetic single-file bugs; they say nothing about production tasks.
- The decision-site probe exercises the predictors on fixture text, not inside a model-driven
  coordinator run. The coordinator needs a full engine stack, and no entry point reaches it with
  these fixtures.
- Single run, 24 pairs, no statistical claim. Local heal also wrote `.nexus/belief_state.json` in the
  worktree during the run (flagged by the harness `StateGuard`); the file is git-ignored and not part of
  the change.
- Classification stays `LAB_ONLY`: the measurement shows no uplift.
