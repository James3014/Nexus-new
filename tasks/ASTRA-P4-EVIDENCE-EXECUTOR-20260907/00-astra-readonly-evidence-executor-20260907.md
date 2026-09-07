# Task Card: astra-readonly-evidence-executor-20260907

artifact_authority: current
task_id: `astra-readonly-evidence-executor-20260907`
owner: James Chen
status: ACTIVE
commit_required: true
candidate_required: true
worker_may_commit: true
worker_may_approve: false
worker_may_integrate: false
worker_may_push: false
AUTO_CHAIN: false

## Objective

Implement a distinct closed nexus_evidence_execute source action for owner-bound NONCANONICAL_EVIDENCE_ONLY cards, after independently accepted readonly metadata repair e6933dedf55f7fa7b48a2e85d2c9e4fd95ae4fe5. Base qualified4887d8f6a3faf50d6b600f2c170526e08d4bf408; coordinator may transport exact metadata-repair delta/card/INDEX into isolated source. Source implementation only by Luna, no actual model/provider/API-key/SDK/Agy/Gemini/network call, deployment/main/push/merge/state activation. Required request only owner_confirmation/task_id/card_path/card_hash/evidence_root; deny extra fields including caller objective/verifier/worker/provider/model/route/capability/planner overrides. Read objective/verifiers/root/empty product paths/all six false mutation flags/AUTO_CHAIN=false from physically verified tracked card. Preserve strict hash/path/symlink/header controls. Add verified evidence identity adapter without relabeling it TRACKED_TASK_CARD or inventing lifecycle Candidate. Sole CapabilityPlanner selects from truthful read-only task facts, canonical policy resolves workforce, actual controls derive from installed adapter/card/verifier evidence, canonical Admission decides; no caller-selected worker or fabricated controls. No Candidate/Target/adoption/approval/integration side effects. Durable source-owned execution record only under fixed evidence root /private/tmp/astra-p4-realprovider-canary-20260907/, one attempt and at most one model invocation, zero retry/fallback. Reserve intent before call; duplicate/restart pending/unknown returns UNKNOWN/readback without redispatch; completed replay returns exact bound receipt. Bind card/source/tree/policy/Planner/Admission/CLI binary/model/auth/readiness/execution/digests. Missing readiness/admission/identity/result fails closed with zero new call and false completion/public claims. Reuse CodexCliExecutor/cli_worker through additive evidence-only strict mode preserving ordinary paths: official Codex executable resolved/hash checked, model must agree with canonical policy-selected Luna, --ignore-user-config and official OpenAI provider, ephemeral session, safe inherited-env allowlist excluding API keys and endpoint/provider overrides, ChatGPT login-status gate before execution; no CODEX_HOME/auth/global config mutation or credential copying. CLI timeout/process cleanup bounded; actual provider result must be observed, never synthetic success. Prove selector-override denial, candidate metadata false, actual Planner selection (not fixture policy), admission deny zero-call, readiness/key-auth denial, one-call/readback/replay/UNKNOWN, malformed result, path escape, cross-card/digest tamper, timeout; local fake CLI only for source tests, label fixtures honestly. Preserve existing task/Candidate/runtime semantics. Independent root full diff and verifier required; real one-call canary is a later separately bound execution and not implied by unit PASS.

## Allowed files

- `nexus/orchestrator/unified_mcp_gateway.py`
- `nexus/engine/canonical_task_seam.py`
- `nexus/orchestrator/self_hosted_task_service.py`
- `nexus/orchestrator/task_contract.py`
- `nexus/executors/codex_executor.py`
- `nexus/executors/cli_worker.py`
- `tests/nexus/orchestrator/test_unified_mcp_gateway.py`
- `tests/nexus/orchestrator/test_self_hosted_task_service.py`
- `tests/engine/test_canonical_task_seam.py`
- `tests/nexus/executors/test_codex_executor.py`

## Verification commands

```bash
python3 -m pytest tests/nexus/orchestrator/test_unified_mcp_gateway.py tests/nexus/orchestrator/test_self_hosted_task_service.py tests/engine/test_canonical_task_seam.py tests/nexus/executors/test_codex_executor.py -q
python3 -m pytest tests/services/test_runtime_workforce_admission.py tests/contracts/test_main_engineering_route_binding.py tests/nexus/orchestrator/test_lifecycle_authority_convergence.py -q
python3 -m py_compile nexus/orchestrator/unified_mcp_gateway.py nexus/orchestrator/self_hosted_task_service.py nexus/engine/canonical_task_seam.py nexus/orchestrator/task_contract.py nexus/executors/codex_executor.py nexus/executors/cli_worker.py
git diff --check
```

## Exit criteria

Owner review of the exact scoped commit.

## Block classification

Unverifiable or out-of-scope mutation is a HARD_BLOCK.
