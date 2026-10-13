# Memory A/B runner: armor axis (#1821)

`scripts/eval/run_memory_ab_v1.py` (issue #1639) ran every attempt through the bare `HealPipeline`.
All 502 local receipts under `artifacts/runtime/memory_ab_v1/*/reports/local_heal/*/receipt.json`
show `receipt_base.with_nexus_armor=false`, `p4_committee_invoked=false`,
`p4_candidate_producer_invoked=false` and a `consumption_chain` holding only `local_heal_repair`.
Any "memory helps / does not help" result from those runs is about a bare local model. The armor
axis lets the same task and memory arm run through the planner-selected capability stack instead.

## Flags

| Flag | Values | Default | Effect |
| --- | --- | --- | --- |
| `--armor` | `off`, `on` | `off` | `off` is the previous behaviour: bare `HealPipeline`. `on` runs the armor path below. |
| `--armor-profile` | `LITE`, `STANDARD`, `FULL` | `FULL` when `--armor on` | Local armor execution profile. Rejected with `--armor off`. |

`--armor` is orthogonal to `--arms off,on` (the memory arms), which behave as before.

## What `--armor on` does

1. `CapabilityPlanner` plans the task inside `run_mainchain(..., with_nexus_armor=True)` on a
   local-only route (`recommended_flow=local_only`, `local_enabled=True`, online disabled).
   The route carries the planner-native signals `route_features.deterministic_verifier_available`
   (repro.py) and `memory_hits`.
2. The selected capabilities run through the mainchain executor registry
   (`build_mainchain_capability_invokers`). Postflight gates, preflight/plan gates and the
   mempalace gate leave their own receipt entries.
3. The local stage runs `LocalAssistService` -> `LocalModelExecutor` (topology
   `localheal_pipeline`, model calls through the Ollama endpoint, `127.0.0.1:11434` by default).
   `FULL` is forced with the supported `NEXUS_FORCE_FULL_ARMOR=1`. `LITE` sets `NEXUS_FAST_MODE=1`.
   `STANDARD` sets nothing. For `LITE` and `STANDARD` the planner's own signals still decide, so the
   profile the executor actually used is read back and a mismatch marks the attempt ineligible
   (`armor_profile_not_applied`).
4. The executor never edits the real workspace. The runner copies the isolated, hash-matched
   candidate result into the attempt work dir, then re-runs `repro.py`. The verdict is still the
   independent repro rerun, exactly as in armor off.

Memory arm: the off arm never queries memory (`memory_hits=0`) and the executor never lists
`memory`. The on arm sends the real lesson count from `MemoryRetrievalAdapter` as `memory_hits`; the
planner decides whether `memory` is selected. If the learning store has no lessons the on arm is
equivalent to off, which is what Nexus would do.

### Model identity

Armor on goes through Workforce Admission, which pins the local model per worker. `--model` must be
the model of an admitted `bounded_code_candidate` ollama worker (today `local_coder_7b` ->
`qwen2.5-coder:7b-instruct`). Anything else exits with code 2 and nothing is substituted. The round 9
model `incoai/Qwen3.6-35B-A3B-Splash` has no admitted worker, so armor on cannot run it until the
policy in nexus-runtime registers one.

## What the receipts prove

Every row in `rows.jsonl` carries these columns, in both modes. `armor_evidence` holds the detail.
Rows are still contract-valid for `normalize_attempt_row`, which already accepts extra columns.

| Column | Source |
| --- | --- |
| `armor` | `off` or `on` |
| `armor_profile` | requested profile, `none` when armor is off |
| `capabilities_selected` | on: `receipt.selected_capabilities` from CapabilityPlanner. off: `consumption_chain` of the HealPipeline `receipt.json` |
| `capabilities_invoked` | only capabilities with real invocation evidence (below) |
| `committee_invoked` | on: executor `p4_committee_invoked`. off: `receipt.json` `p4_committee_invoked` |
| `with_nexus_armor` | `receipt_base.with_nexus_armor` of the receipt, never set by the runner |

`capabilities_invoked` rules (armor on): a unified-receipt capability counts when `invoked=true`,
not skipped, `evidence_present`, status `INVOKED` or `SUCCEEDED`, and its physical callable is not an
explicit skip or stub. `local_model_executor` counts when the local stage ran the executor with at
least one model call; `repair_loop` when the executor reports the pipeline ran. `ddtree` and
`autoreason` count only with candidate or judge evidence. With an empty candidate pool the
`localheal_pipeline` executors report `invoked=true` as an advisory stub; those are listed in
`armor_evidence.advisory_stub_capabilities` instead.

The scorecard gets an `armor_axis` block (per-attempt columns plus roll-ups) and `validation.json`
gets `armor`, `armor_profile` and `with_nexus_armor_verified`.

Default rows (`--armor off`) keep every previous key and value. The only change is the added columns
above plus `armor_evidence`.

## Smoke run

Run on 2026-10-12 from this branch, endpoint `127.0.0.1:11434` (SSH tunnel to the M5 Ollama; no model
was started on the M4). Model `qwen2.5-coder:7b-instruct`, tasks `consumed_iterator-a` and
`bit_width_overflow-a` from `memory_ab_tasks_v3`, memory off, `--armor-profile FULL`.
Artifacts: `artifacts/runtime/memory_ab_v1/armor-smoke-20261012T041024Z/{armor-off,armor-on}/`
(untracked).

| Task | armor | outcome | model calls | `with_nexus_armor` | `capabilities_invoked` |
| --- | --- | --- | --- | --- | --- |
| bit_width_overflow-a | off | SUCCEEDED | 3 | false | `local_heal_repair` |
| consumed_iterator-a | off | FAILED | 7 | false | `local_heal_repair` |
| bit_width_overflow-a | on | FAILED | 8 | true | `harness_preflight_sensor`, `repair_loop`, `delivery_gate`, `pregate`, `plan_quality_gate`, `mempalace_gate`, `artifact_gate`, `claim_gate`, `local_model_executor` |
| consumed_iterator-a | on | FAILED | 7 | true | the same nine |

Observed profile `FULL` in both armor-on attempts (from the executor and the provider ledger).
`committee_invoked=false`. The planner selected `research_route` but it was an explicit skip.
`codeintel`, `ddtree`, `autoreason`, `belief`, `lancedb` and the committee were not selected for
these low-risk single-file tasks. `ddtree` and `autoreason` ran as advisory stubs and are excluded.
So even with armor on, these fixtures exercise gates, the repair loop and semantic retry, not the
heavier capabilities. A harder or multi-candidate task set is needed to exercise those.

Two armor-on failures worth knowing about: the executor's World C receipt validator reports
`canonical_execution_world_mismatch` (planner world `product_runtime` versus the validator's
`local_armor`), and with this 7B model the final patch failed verification
(`LOGIC_REGRESSION:VERIFICATION_FAILED`, 3 patch attempts). Two attempts per mode say nothing about
effectiveness.

Both modes end with `STATE_LEAK` on `.nexus/belief_state.json` (exit 3). The state guard watches
`<repo>/.nexus`, and the pipeline's belief trace writes there. This is existing behaviour and is not
changed here.

## Tests

`tests/eval/test_memory_ab_armor_axis.py` runs one task in both modes. Armor on uses the real
CapabilityPlanner, `run_mainchain` and `LocalAssistService`; only the `LocalModelExecutor` call is a
fake. It asserts `with_nexus_armor` is true only in armor-on mode, `capabilities_invoked` is
non-empty and excludes advisory stubs, off rows keep the legacy key set, and an unadmitted model is
refused. `tests/eval/test_memory_ab_v1.py` is unchanged.

## Armor-on lane fix (#1915)

The first full armor-on run, `armor-on-full-v1-7b-20261013T223335Z` (7B, FULL, `memory_ab_tasks_v1`),
solved 0/12 in both arms. The bare-pipeline 4/12 it was compared with came from a different task set
(`memory_ab_tasks_v2`) and model tag (`qwen2.5-coder:7b`). On the same tasks and model the bare lane
solves 11/12 and 10/12 (`bare-v1-7b-instruct-20261012T233503Z`).

The Ollama payloads were traced for the same task in both lanes. The armor lane's first patch was
correct, and four defects threw it away:

1. The World C workspace (`prepare_world_c_workspace`) and the isolated apply workspace
   (`run_isolated_workspace_apply`) copied only the target file of a synthetic task. `python repro.py`
   then failed with "can't open file" for every candidate. The parse failures in the 0/12 run
   (fenced_output, SEARCH mismatch and so on) come from the later retries after these false failures.
2. The delegated semantic retry ran `HealPipeline` with `repo_dir=request.repo_root`, so it patched the
   caller's source tree. The later isolated apply of the same candidate then failed with "patch does
   not apply".
3. The repair_loop provider bridge put the system prompt into the user prompt and dropped the bare
   lane's Ollama options (temperature 0, num_ctx 4096, num_predict 768).
4. The runner planned in the default world `product_runtime`. The World C receipt validator requires
   `local_armor`, so a verified candidate was never delivered (`canonical_execution_world_mismatch`).

Fix: the verifier's input files (`verifier_input_files`) are copied into both workspaces. The delegated
retry runs in its own World C copy. The bridge sends the system and user prompts separately
(`LocalModelProviderRequest.system_prompt/user_prompt`) with `default_heal_generation_options()`.
The runner declares `canonical_context={"execution_world": "local_armor", "transport_ingress": "bench"}`,
as `scripts/bench/n30r_v1_full_armor_trace.py` already does. No gate was loosened. The validator still
rejects every world other than `local_armor`. A product-runtime (World A) task therefore still cannot
deliver a World C local candidate. That needs a World A to World C bridge, which is out of scope here.

| Run | Lane | memory off | memory on | model calls | `with_nexus_armor_verified` | World C mismatch |
| --- | --- | --- | --- | --- | --- | --- |
| `armor-on-full-v1-7b-20261013T223335Z` | armor on (before) | 0/12 | 0/12 | 185 | true | 24/24 |
| `bare-v1-7b-instruct-20261012T233503Z` | bare | 11/12 | 10/12 | 86 | false | n/a |
| `armor-on-full-v2-7b-fix-20261012T235634Z` | armor on (after) | 10/12 | 11/12 | 84 | true | 0/24 |

After the fix, all 21 armor-on solves have an isolated, hash-matched candidate
(`candidate_materialized=applied`) that passes the local verifier, and the World C receipt is valid
for each of them. The three failures are both `mutable_default_argument` variants
(`SEARCH_REPLACE_SEARCH_MISMATCH`). The bare lane also fails on these tasks, and their World C
receipts correctly show `patch_synthesis_not_completed`. Remaining difference between the lanes: the
armor lane passes no repro script content, so its planner sees the problem statement as reproduction
evidence where the bare lane sees the traceback.
