# ARCHIVED 2026-10-16 (answer-table module)

Physical deletion of `nexus/research/local_sprint_mutator.py`, the deterministic local "answer
table", and every route into it. Tracking issue: #2363. Owner decision: James, 2026-10-16, in chat
(「刪」), as a follow-up to #2339 / #2347 and #2358.

Originals are preserved on branch `archive/2026-10-16-answer-table-module` at `958b991b4d6a`. That
commit is the main commit this stack was cut from. The deleted files are byte-identical there and
at this change's parent (`274be5763`, PR-5c-2).

## Why

Every patcher in the module recognises a specific benchmark fixture (function name, file name or
task phrase) and writes the known answer. The 2026-10-16 zero-model proof showed that this solved P16
tasks under a NOOP model (`ARCHIVED_2026-10-16-hidden-contract-fast-path.md`). #2347 and #2358
removed its routes into model-run delivery. This change removes the table itself and its remaining
consumers:

- no-model local mode (sprint and baseline flow);
- the nightshift deterministic bundle shortcut (scored 1.0 before any model was tried);
- the bench local arms: the deterministic hidden pre-retry, the failed-tests and pre-model
  pre-rescue, the bare-mode local patch, and the file-task "without Nexus" arm.

## Deleted files

| File | Lines | Test ids |
| --- | --- | --- |
| `nexus/research/local_sprint_mutator.py` | 1254 | - |
| `tests/research/test_local_mutator_safety.py` | 351 | 20 (all test the deleted module only) |
| `tests/research/test_local_mutator_rate_limiter.py` | 119 | 7 (all test the deleted module only) |

## Deleted functions and the fixtures they were keyed on

| Function | Lines | Keyed on (fixture function / file / task phrase) |
| --- | --- | --- |
| `_deadlock_lock_order_patch` | 37 | `transfer()` |
| `_patch_vip_discount` | 18 | `calculate_discount()`, `is_vip` |
| `_patch_rate_limiter_prune` | 46 | `allow()`, `window_sec` |
| `_patch_normalize_hosts` | 17 | `normalize_hosts()` |
| `_patch_parser_purity` | 23 | `parse_pairs()` |
| `_feature_discount_patch` | 10 | `apply_discount()`, `pass` |
| `_refactor_parser_patch` | 16 | `import random`, `random.randint(0, 100)` (parser-purity demo fixture) |
| `_structural_placeholder_patch` | 10 | `raise NotImplementedError` (replaced by `return None`) |
| `_structural_feature_patch` | 16 | `pass` |
| `_patch_normalize_flag` | 22 | `normalize_flag()` |
| `_patch_compute_backoff` | 28 | `compute_backoff()` |
| `_patch_compute_backoff_conservative` | 24 | `compute_backoff()` |
| `_patch_rlm_belief_budget` | 27 | `rlm_harder_v2_repair_budget()` |
| `_patch_rlm_governance_filter_action` | 25 | `delete_file`, `governance_block`, `rlm_harder_v2_filter_action()` |
| `_patch_rlm_governance_scope_decision` | 19 | `approved`, `read_only`, `rlm_harder_v2_scope_decision()`, `scope_block` |
| `_patch_pricing_invoice` | 11 | `tax_for`, `total()` |
| `_patch_pricing_tax` | 11 | `tax_for()` |
| `_patch_nightshift_runner` | 23 | `execute()`, `persist_state` |
| `_patch_nightshift_store` | 18 | `persist_state()`, `trigger_reason` |
| `_patch_nightshift_bridge_runner` | 18 | `build_audit_payload`, `execute()` |
| `_patch_nightshift_bridge_store` | 18 | `audit_tag`, `persist_state()`, `trigger_reason` |
| `_patch_nightshift_audit_bridge` | 18 | `build_audit_payload()`, `nightshift_repair`, `stage1_no_passing_candidate` |
| `_patch_phase_ready_contract` | 26 | `phase_ready()` |
| `_patch_apply_events_idempotent` | 33 | `apply_events()`, `seen_ids` |
| `_patch_response_result_field` | 21 | `FIELD`, `build_response()` |
| `_patch_overall_status_requires_evidence` | 24 | `overall_status()` |
| `_patch_parse_config_defaults` | 24 | `parse_config()` |
| `_replace_simple_function` | 14 | helper: swaps a named function body for a canned one |
| `_patch_normalize_key_boundaries` | 13 | `normalize_key()` |
| `_patch_merge_limits_preserve_inputs` | 16 | `merge_limits()` |
| `_patch_rlm_merge_settings_preserve_inputs` | 16 | `rlm_harder_v2_merge_settings()` |
| `_patch_remaining_ms_elapsed` | 13 | `remaining_ms()` |
| `_patch_redact_secret_fields` | 16 | `redact()` |
| `_patch_can_access_deny_default` | 16 | `can_access()` |
| `_patch_verified_claims_require_artifact` | 12 | `verified_claims()` |
| `_patch_rlm_verified_claims_require_artifact` | 17 | `rlm_harder_v2_verified_claims()` |
| `_patch_rlm_accept_receipt_requires_replay` | 17 | `exit_code`, `replay_command`, `rlm_harder_v2_accept_receipt()` |
| `_patch_rlm_select_memory_hits_keyword_overlap` | 20 | `item_keywords`, `keyword_set`, `rlm_harder_v2_select_memory_hits()` |
| `_patch_classify_requires_semantic_evidence` | 14 | `classify()`, `needs_evidence` |
| `_patch_swarm_report_requires_distinct_evidence` | 20 | `rlm_harder_v2_accept_swarm_report()` |
| `_patch_ultra_report_requires_repro_evidence` | 17 | `negative_exit_code`, `repro_command`, `rlm_harder_v2_accept_ultra_report()` |
| `_patch_semantic_refs_require_source_gate` | 19 | `rlm_harder_v2_select_semantic_refs()` |
| `_patch_rlm_choose_candidate_supported` | 21 | `evidence_refs`, `rlm_harder_v2_choose_candidate()`, `status` |
| `_patch_rlm_prune_candidates_risk_first` | 22 | `rlm_harder_v2_prune_candidates()` |
| `_patch_rlm_choose_research_claim_cited` | 20 | `citation`, `rlm_harder_v2_choose_research_claim()` |
| `_patch_rlm_select_vector_hits_source_gate` | 18 | `rlm_harder_v2_select_vector_hits()`, `source_id`, `topic_pack` |
| `_patch_rlm_accept_drone_artifacts` | 14 | `expected_count`, `owner`, `path`, `rlm_harder_v2_accept_drone_artifacts()` |
| `_patch_rlm_accept_nightshift_report` | 17 | `invoked`, `report_path`, `rlm_harder_v2_accept_nightshift()` |
| `_patch_rlm_accept_quiet_moment_contract` | 18 | `rlm_harder_v2_accept_quiet_moment()` |
| `generate_local_companion_edits` | 46 | `"nightshift"`, `"trigger"`, `invoice.py`, `runner.py`, `tax.py` |
| `generate_nightshift_bundle_edits` | 38 | `"audit bridge"` |
| `generate_local_candidate` | 118 | `"discount"`, `"feature"`, `"host"`, `"limit"`, `"normalize"`, `"parser"`, `"purity"`, `"rate"`, `"refactor"`, `compute_backoff()` |

## Behaviour after the change

- **Sprint without a model**: FAILED, reason and winner `no_local_candidate_generator`, zero attempts,
  no patch. With a model, a failed model call leaves the round without a candidate
  (`no_model_candidate`). The local fallback, the DDTree local support pool, the local guard fallback,
  the emergency valve and companion edits are gone.
- **Baseline flow without a model**: `no_local_candidate_generator`, original code, no companion edits.
- **Nightshift**: a round needs the model. With no gateway the round returns
  `nightshift_gateway_unavailable`.
- **Bench**: `_deterministic_hidden_pre_retry` and `_deterministic_failed_tests_pre_rescue` return
  `{"used": False, "reason": "no_local_candidate_generator"}`. The bare mode is verification-only.
  The file-task "without Nexus" arm submits the unchanged source.
- **CLI**: `nexus research:auto-flow` defaults to `--no-llm-mode`. Without `--llm-mode` it now
  reports `no_local_candidate_generator` instead of delivering an answer-table patch.

## Kept on purpose

- `candidate_pool_policy` still reports its `local_support_*` settings in the learning trace. They no
  longer drive anything (follow-up: retire the fields).
- Docs, reports and wiki pages that mention the module are history and are left as they are.

## Tests

- Every surviving test id is kept. Tests whose fakes stood in for the local generator now drive the
  same fake as the model, or assert the honest no-candidate outcome.
- Guard: `tests/research/test_archived_answer_table_module_2026_10_16.py` checks that the module is
  not importable, that no `local_sprint_mutator*` file exists under `nexus/` or `scripts/`, and that
  no reference (imports, `importlib` strings, `.py`/`.json`/`.txt`/`.toml`/`.yaml` config) to the module
  or its entry points exists. It also checks the no-model outcomes of the sprint, the baseline and
  the bench helpers.
