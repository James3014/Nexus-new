# Task Card — campaign-scoped OpenCLI ChatGPT Workforce onboarding

- task_id: `open-swe-chatgpt-workforce-onboarding-20260908`
- campaign_id: `open-swe-chatgpt-workforce-onboarding-20260908`
- status: `ACTIVE`
- owner: `James Chen`
- commit_required: `true`
- candidate_required: `true`
- worker_may_commit: `false`
- worker_may_approve: `false`
- worker_may_integrate: `false`
- worker_may_push: `false`
- AUTO_CHAIN: `false`

## Objective

Register `opencli_chatgpt_balanced_web` as a conditional L1 bounded candidate worker and route only the exact `open-swe-resident-five-repo-canary-20260908` campaign to it. Preserve the global Agy/Gemini default and reject caller-supplied or forged worker identity.

## Owner-approved evidence interpretation

- `balanced` is a mutable ChatGPT UI capability alias; the underlying backend model revision is not claimed.
- Calibration remains statistically incomplete for global promotion. Owner approval is limited to campaign-scoped L1 Candidate execution under exact Task Card, parser, verifier, isolated workspace, independent acceptance, and no-fallback controls.
- Existing Web worker v7, r4-r7 transport, OpenCLI 1.8.7, Browser Bridge 1.0.24, current adapter/runtime identity, and runtime PR #15 are bounded transport/tool evidence only.

## Allowed files

- `nexus/config/model_workforce.yaml`
- `docs/arch/MODEL_WORKFORCE_POLICY.md`
- `nexus/engine/canonical_task_seam.py`
- `tests/contracts/test_model_workforce_policy.py`
- `tests/nexus/orchestrator/test_unified_mcp_gateway.py`
- `tests/services/test_external_intelligence_automation.py`
- `tasks/open-swe-resident-five-repo-canary-20260908/00-canary.md`
- `tasks/open-swe-chatgpt-workforce-onboarding-20260908/INDEX.md`
- `tasks/open-swe-chatgpt-workforce-onboarding-20260908/00-onboarding.md`

No deletion is allowed.

## Required behavior

1. Add worker `opencli_chatgpt_balanced_web` with provider `opencli_chatgpt`, model `opencli_chatgpt/balanced`, state `REGISTERED_CONDITIONAL`, availability `AVAILABLE`, autonomy `L1`, role `fast_bounded_implementation`, and `default_route: false`.
2. Add only one campaign override: `open-swe-resident-five-repo-canary-20260908.fast_bounded_implementation -> opencli_chatgpt_balanced_web`.
3. Preserve global `fast_bounded_implementation -> agy_flash_37_medium`.
4. Derive the canary campaign only from the exact verified Task Card bytes/hash. Blank, unrelated, prefixed, forged, or hash-mismatched identities must use the global route or fail closed.
5. Canonical Workforce Admission must return one ALLOW binding for `opencli_chatgpt/balanced`, and External Intelligence must reject transport provider/model substitution before semantic dispatch.
6. Existing r1-r7 operations remain immutable and are never resent.

## Verification

```bash
uv run pytest -q tests/contracts/test_model_workforce_policy.py tests/nexus/orchestrator/test_unified_mcp_gateway.py tests/services/test_external_intelligence_automation.py tests/services/test_external_intelligence_service.py tests/services/test_open_swe_worker_transport.py
uv run ruff check nexus/engine/canonical_task_seam.py tests/contracts/test_model_workforce_policy.py tests/nexus/orchestrator/test_unified_mcp_gateway.py tests/services/test_external_intelligence_automation.py
git diff --check
```

## Exit

- PASS: exact campaign route produces a canonical single-ALLOW `opencli_chatgpt/balanced` binding; global route remains Agy; all verifiers pass; independent coordinator accepts exact Candidate.
- BLOCK: identity, evidence, campaign, role, transport, scope, verifier, or global-default drift.
