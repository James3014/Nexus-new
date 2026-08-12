---
task_id: TC-WF-AGY-MEDIUM
campaign_id: CAMPAIGN-WORKFORCE-AGY-MEDIUM-20260812
issue: 179
status: active
auto_chain: false
claim_ceiling: agy_flash_medium_registered_conditional_l1_candidate_only
---

# TC-WF-AGY-MEDIUM — Register Gemini 3.6 Flash Medium as a bounded Agy sibling

## Objective

Register `agy / gemini-3.6-flash-medium` as a distinct workforce identity so exact-Medium Task Cards can obtain fail-closed Workforce Admission without substituting `gemini-3.6-flash-high` or inheriting High calibration evidence.

## Inputs / evidence

- Issue `#179` is the bounded Owner-approved implementation contract.
- Existing worker `agy_flash` remains `agy / gemini-3.6-flash-high` and is not redefined by this task.
- `tasks/epistemic-research-profile-foundation/00-nexus-epistemic-profile-foundation.md` contains physically distinct prior Agy Medium execution lineage and explicitly says that task did not promote workforce status.
- Phase 1A G1-G4 cards explicitly select Medium and prohibit High substitution / sibling evidence inheritance.
- Current Agy CLI/model catalog evidence shows the exact Medium model is available in the Owner environment, but provider model revision is unresolved.

## Required behavior

1. Add worker id `agy_flash_medium` with provider `agy` and exact model `gemini-3.6-flash-medium`.
2. Initial state must be `REGISTERED_CONDITIONAL`, autonomy ceiling `L1`, preferred context `nexus_bounded`.
3. Admit only bounded candidate/implementation and focused-verification work with exact Task Card, allowed-files, mandatory-command, parser/verifier, and independent-verification controls.
4. Medium output remains Candidate-only; no route, approval, integration, push, release, production/public-claim authority.
5. Keep `agy_flash` High identity/evidence/roles unchanged.
6. Keep `routing.online.fast_bounded_implementation: agy_flash` unchanged.
7. Do not copy, relabel, or inherit High benchmark/calibration evidence as Medium evidence.
8. Exact worker/provider/model mismatches fail closed in both directions.
9. L2-or-higher request for Medium must not be admitted under this task.

## Allowed mutation scope

- `nexus/config/model_workforce.yaml`
- `docs/arch/MODEL_WORKFORCE_POLICY.md`
- `tests/contracts/test_model_workforce_policy.py`
- `tests/services/test_model_workforce_policy_loader.py`
- this Task Card and campaign INDEX only

## Forbidden scope

- No `CapabilityPlanner` or `HybridRouteDecision` change.
- No worker adapter / Gateway / provider runtime change.
- No change to `nexus/config/model_three_arm_matrix.yaml` historical snapshot.
- No default routing change.
- No Phase 1A implementation change.
- No High worker downgrade/rebinding.
- No L2/stable promotion claim.
- No runtime activation, release, or production/public claim.

## Verification

Run at minimum:

```bash
uv run pytest -q tests/contracts/test_model_workforce_policy.py tests/services/test_model_workforce_policy_loader.py
uv run python scripts/ops/select_tests.py --json nexus/config/model_workforce.yaml
uv run ruff check tests/contracts/test_model_workforce_policy.py tests/services/test_model_workforce_policy_loader.py
uv run ruff format --check --preview tests/contracts/test_model_workforce_policy.py tests/services/test_model_workforce_policy_loader.py
git diff --check
```

Also prove with explicit admission tests:

- existing High request still ALLOWs its current role and controls;
- exact Medium worker-id request ALLOWs only the new L1 bounded role/context/controls;
- exact `agy + gemini-3.6-flash-medium` resolves to `agy_flash_medium`;
- Medium requested through `agy_flash` BLOCKs;
- High requested through `agy_flash_medium` BLOCKs;
- Medium L2 request ESCALATEs or BLOCKs;
- missing mandatory controls BLOCKs;
- default route remains `agy_flash`.

## Candidate / acceptance

Implementation must produce a scoped Candidate commit. Independent exact-head acceptance is required before merge. The implementer cannot self-accept.

Maximum Candidate claim:

`agy_flash_medium_registered_conditional_l1_candidate_only`

After independent acceptance + protected merge + post-merge readback only:

`agy_flash_medium_registered_conditional_l1`

No stable promotion, L2 equivalence, default routing, release, runtime, or production claim is implied.
