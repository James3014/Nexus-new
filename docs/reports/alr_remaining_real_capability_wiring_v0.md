# ALR Remaining Real Capability Wiring v0

Status: `ALR_PARTIAL_IMPLEMENTATION_REMAINS`

Date: 2026-06-21

## Scope

This pass implemented bounded source-level wiring for the remaining local_heal capability gaps without redoing AL-R1 Runtime AST Evidence Graph work.

Implemented:

- Memory retrieval-backed anchor scoring via provenance-filtered `MemoryRetrievalAdapter`.
- Autoreason advisory bridge invoked from local_heal finalization, recorded as advisory-only/no-override.
- Belief trace bridge invoked from local_heal finalization, recording `belief_before`, `belief_after`, and `uncertainty_delta`.
- Strict local_heal claim/delivery gate requiring verifier artifact, source hash, patch application, and artifact refs.
- Capability receipt adapters hardened so caller-provided claim/delivery flags cannot create success without strict proof.
- Learning closure writeback bridge for internal-only lessons with `training_export_allowed=false`.
- Legacy context normalization for dict plans and tuple localized files, preserving older local_heal tests while newer phases use structured contracts.

Not completed in this pass:

- Full runtime artifact directory `artifacts/runtime/alr_remaining_real_wiring_v0/`.
- Complete sentinel matrix.
- Complete ablation matrix.
- Live C_12481 / C_13453 task regressions; no matching pytest files exist under `tests/` in this checkout.

## Changed Files

- `nexus/services/local_heal/memory_retrieval_adapter.py`: added provenance-backed local memory retrieval fallback and no-match metadata.
- `nexus/services/local_heal/reasoning_advisory_bridge.py`: added Autoreason advisory and Belief confidence bridge.
- `nexus/services/local_heal/claim_delivery_gate.py`: added strict proof-backed claim/delivery validator.
- `nexus/services/local_heal/learning_closure_bridge.py`: added internal-only learning writeback.
- `nexus/services/local_heal/semantic_anchor_selection.py`: replaced hardcoded prior lesson pattern scoring with retrieval-backed memory contribution.
- `nexus/services/local_heal/orchestrator.py`: invokes Autoreason, Belief, Claim/Delivery, and Learning Closure bridges during finalization.
- `nexus/services/local_heal/receipt.py`: records capability wiring telemetry and keeps public/production/training claims disabled.
- `nexus/engine/capability_receipt_adapters.py`: blocks receipt-only claim/delivery success.
- `nexus/services/local_heal/context_guard.py`: normalizes legacy tuple localized-file entries.
- `tests/unit/local_heal/test_real_capability_wiring.py`: covers memory provenance rejection, score deltas, no-match metadata, no-override advisory, belief trace, strict gate rejection, receipt-only rejection, learning writeback, and internal-only receipt flags.
- `nexus_wiki_vault/06_Ops/Ops - Learning Closure Matrix.md`: added failure lesson for GitNexus refresh hang and legacy local_heal context drift.

## Verification Evidence

Passed:

```text
uv run pytest tests/unit/local_heal/test_real_capability_wiring.py tests/unit/local_heal/test_semantic_anchor_selection.py tests/unit/local_heal/test_receipt_v1_schema.py -q
45 passed, 1 warning
```

```text
uv run pytest tests/unit/local_heal -q
328 passed, 1 warning
```

Independent cheap-model read-only audit:

- Agent `Averroes` found two risks: `match_authority` being accepted as source hash, and claim eligibility not being fail-closed when bridge data is absent.
- Both were fixed.
- Post-fix focused verification: `45 passed, 1 warning`.
- Post-fix local_heal suite: `328 passed, 1 warning`.

Partially failed adjacent slice:

```text
uv run pytest tests/unit/test_s1_prep.py tests/unit/test_local_heal_receipt.py tests/unit/test_orchestrator.py tests/unit/test_prompt_hardening.py tests/unit/test_t1_6a_attribution.py -q
20 passed, 3 failed
```

Failure classification:

- `tests/unit/test_orchestrator.py::test_orchestrator_runs_patch_and_verification_phases`: patch reaches file edit, but MicroVerifier blocks because no task-scoped interpreter/verifier command is available.
- `tests/unit/test_prompt_hardening.py::test_system_prompt_contains_anti_apology`: existing prompt text drift, not caused by current wiring.
- `tests/unit/test_prompt_hardening.py::test_system_prompt_contains_senior_engineering_rules`: existing prompt text drift, not caused by current wiring.

GitNexus evidence:

- `npx --no-install gitnexus status`: stale index, indexed commit `bf58123`, current commit `72eb684`.
- `npx --no-install gitnexus analyze`: stopped after 120s with no completion; emitted external generated-source scope extraction warnings.
- Stale impact fallback:
  - `HealOrchestrator`: LOW risk, 3 direct affected imports/callers.
  - `build_repair_receipt`: LOW risk, 1 direct caller.
  - `ClaimGateReceiptAdapter`: LOW risk, 2 direct import files.
  - `DeliveryGateReceiptAdapter`: LOW risk, 2 direct import files.
- `npx --no-install gitnexus detect-changes --repo actionlint`: medium risk, affected processes: 4.

## Residual Debt

- Build the requested runtime artifact bundle:
  - `capability_invocation_matrix.json`
  - `influence_delta_summary.json`
  - `sentinel_results.json`
  - `ablation_results.json`
  - `regression_results.json`
  - `runtime_trace_examples.json`
- Add or restore live C_12481 / C_13453 pytest entrypoints if those regressions are still required as executable gates.
- Decide separately whether to repair `test_prompt_hardening.py` prompt contract drift.
- Decide separately whether the legacy MicroVerifier bare-python block in `test_orchestrator.py` should be updated as a test fixture issue or a product compatibility issue.

## Claim Boundary

- `public_claim_allowed=false`
- `production_ready=false`
- `training_export_allowed=false`
- `internal_only=true`

This report does not claim full Nexus armor completion. It claims bounded source wiring plus local_heal unit evidence only.
