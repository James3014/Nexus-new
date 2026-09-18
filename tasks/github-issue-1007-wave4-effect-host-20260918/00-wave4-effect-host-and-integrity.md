# Task Card: Issue #1007 Wave 4 — effect-authority host wiring and code-integrity evidence

artifact_authority: current
task_id: `issue-1007-wave4-effect-host-and-integrity-20260918`
owner: James Chen
status: ACTIVE
contract_kind: TRACKED_TASK_CARD
execution_lane: GOVERNED
AUTO_CHAIN: false
worker_may_commit: true
worker_may_approve: false
worker_may_integrate: false
worker_may_push: false

## Objective

Complete the current cross-repository architecture plan's Wave 4 inside Nexus-new without creating a second permission authority:

1. bind the already-accepted nexus-runtime Wave 1 effect authorization / tool projection contracts into the canonical Nexus host execution paths;
2. fail closed at the Nexus worker boundary when an effect-authorized execution reaches an adapter that cannot physically consume the projection;
3. carry the already-existing Open SWE exposure receipt back to Nexus readback/reconciliation without creating another exposure truth;
4. add the bounded `code_integrity_v1` verifier evidence lane for Candidate-changed Python source/tests; and
5. make the legacy phase `CapabilityGate` explicitly compatibility projection only.

This Task Card is unrelated to the historical #982 task named “Wave 4 / G2 closure”, which is already terminal.

## Source fence

- Durable owner: `James3014/Nexus-new#1007`
- Nexus-new authority/source base: `17c80122d2ad850d875b77e18a80534212b9b806`
- Nexus-new current nexus-runtime pin: `b48fbd7abe96041bffcea31fa31fa90e78582f02`
- Accepted nexus-runtime Wave 1 commit: `d621922`
- Current nexus-runtime default-branch head containing Wave 1: `632e1a18d164d7dadf6bb98caa9c4e9d17c436f3`
- Current nexus-open-swe-runtime main: `2876090d026fd60f2a164e038be50418c0ffd51c`
- DevSpace Wave 3 merge: `2739781d70b54008e887af743b8bdef1cfab6764`
- Fast Start cache #549 has no #1007 entry; fresh source/Issue evidence governs this task.

## Architecture invariant

Authority monotonicity is mandatory:

`canonical authority -> EffectAuthorization -> ToolProjectionManifest -> backend/native narrowing -> derived exposure/effect receipt`

Every downstream layer may preserve or narrow authority, never widen or mint it.

`ToolProjectionManifest`, Open SWE `execution_exposure_receipt`, DevSpace `effectEnforcementReceipt`, and `code_integrity_v1` are evidence/projection artifacts only. None may become Planner, Workforce, Completion, merge, release, or production authority.

## Allowed Nexus-new mutation scope

Production source / dependency:
- `pyproject.toml`
- `uv.lock`
- `nexus/orchestrator/managed_local_agent.py`
- `nexus/orchestrator/self_hosted_task_service.py`
- `nexus/executors/worker_registry.py`
- `nexus/executors/worker_contract.py`
- `nexus/services/open_swe_external_intelligence.py`
- `nexus/services/external_intelligence_fanout.py`
- `nexus/orchestrator/candidate_verifier.py`
- `nexus/orchestrator/code_integrity_verifier.py` (new)
- `nexus/governance/capability_gate.py`

Tests:
- `tests/nexus/orchestrator/test_managed_local_agent.py`
- `tests/nexus/orchestrator/test_self_hosted_task_service.py`
- `tests/nexus/orchestrator/test_candidate_verifier.py`
- `tests/nexus/orchestrator/test_code_integrity_verifier.py` (new)
- `tests/services/test_open_swe_external_intelligence.py`
- `tests/services/test_open_swe_worker_transport.py`
- the existing worker-registry test file, if fresh discovery identifies one; otherwise a new bounded `tests/nexus/executors/test_worker_effect_projection.py`
- the existing capability-gate test file, if fresh discovery identifies one; otherwise a new bounded `tests/nexus/governance/test_capability_gate_authority_boundary.py`

Maximum changed files: 19.

## Wave 4A required behavior

1. Repin Nexus-new to an exact nexus-runtime revision containing accepted Wave 1 `EffectAuthorization` and `ToolProjectionManifest` semantics.
2. Managed execution accepts an externally supplied effect authorization plus provider-specific projection request. Nexus-new must not infer or mint the effect ceiling from prompt text, provider defaults, `CapabilityGate`, or tool discovery.
3. The managed binding and durable runtime request preserve exact operation/attempt/repository/base/workspace/target identity. For effect-authorized managed execution, the runtime attempt identity must equal the authorization attempt identity; no post-start regeneration is permitted.
4. Runtime-provided `effect_authorization` / `tool_projection_manifest` reach the worker adapter boundary intact.
5. Existing legacy adapters that cannot prove consumption of the projection fail closed before provider execution. Do not silently drop unknown effect/projection kwargs and run a broader CLI surface.
6. Open SWE request transport may carry the exact Wave 1 authorization/projection pair and returns the existing `nexus.open_swe_runtime.execution_exposure_receipt.v1`; Nexus validates/readbacks its identity/hash relationship without creating a new exposure authority.
7. Open SWE reconcile preserves the same operation/projection identity and never substitutes a different projection.
8. Nexus-new must not create a DevSpace worker adapter in this task. Current source explicitly classifies that route as `UNKNOWN_BLOCKED`; DevSpace remains the owner of its existing `devspace.local_effect_enforcement_receipt.v1` path.
9. Retry/fallback/restart cannot widen or regenerate authorization after execution may have begun.
10. Calls without Wave 1 authority preserve legacy behavior and must not be labeled hard-enforced.

## Wave 4A negative controls

- effect authorization without projection request: block before provider;
- projection request without effect authorization: block;
- stale/tampered authorization: block;
- operation/attempt/repository/base/workspace/target mismatch: block;
- projection selected effects wider than authorization: block;
- provider/backend mismatch: block;
- effect-authorized execution reaching legacy direct CLI adapter: block with provider call count zero;
- fallback provider missing its own projection: block instead of reusing another provider projection;
- downstream exposure receipt whose authorization/projection hash or actual tool set disagrees with the request: treat as unknown/invalid evidence, never success;
- legacy no-effect request remains compatible.

## Wave 4B required behavior

Add one explicit verifier command ID, `code_integrity_v1`, handled by CandidateVerifier without shell execution.

It is scoped only to the Candidate changed/untracked Python source/tests supplied to that CandidateVerifier invocation. It produces structured derived evidence and fails the verifier gate on bounded findings:

- executable implementation body that is only `pass` and/or `...` where the changed production function/class method is expected to contain implementation;
- standalone tautological test assertions such as `assert True` in changed test code;
- when only tests changed and production behavior is claimed, no target reference/reachability witness must not be upgraded into proof. The verifier reports this as bounded evidence/failure; it does not prove full semantic coverage.

Do not scan the whole repository by default. Do not flag fixture strings/comments/docstrings as executable findings.

## Legacy CapabilityGate boundary

`nexus/governance/capability_gate.py` remains backward-compatible legacy presentation/compatibility projection. Add an explicit machine-readable authority-boundary marker and regression evidence that it cannot issue or validate Wave 1 EffectAuthorization/ToolProjectionManifest and is not execution authority.

Do not remove existing callers in this task.

## Verification

At minimum, exact Candidate evidence must include:

- dependency pin contains nexus-runtime Wave 1 commit;
- managed-local-agent hostile effect-authority tests;
- self-hosted service attempt/retry identity tests;
- worker adapter zero-provider-call fail-closed tests;
- Open SWE request/result/reconcile projection and exposure-receipt tests;
- `code_integrity_v1` positive and negative controls;
- legacy CapabilityGate compatibility/authority-boundary tests;
- existing managed-local-agent regression suite;
- existing CandidateVerifier regression suite;
- affected SelfHostedTaskService tests;
- affected Open SWE tests;
- `git diff --check`;
- changed-path audit against this Task Card;
- repository CI / required workflow evidence on the exact Candidate;
- independent acceptance against this exact Task Card before governed merge.

## Forbidden scope

- no CapabilityPlanner route/capability authority change;
- no Workforce Admission/model/worker selection policy change;
- no new Tool Registry, ToolAuthorityStore, authority database, or parallel Completion verifier;
- no nexus-core semantic change;
- no provider implementation changes in nexus-runtime, nexus-open-swe-runtime, or DevSpace;
- no new DevSpace worker transport;
- no release, deployment, runtime reload, or production activation;
- no benchmark/canary expansion unrelated to this exact Wave 4 source contract;
- no automatic successor work.

## Claim ceiling

Implementation may claim only an exact source Candidate. Independent acceptance may authorize a governed merge of that exact Candidate. A merged source change proves neither runtime reload nor production activation nor system-wide Wave 1–4 production certification.

## Exit criterion

Wave 4 source work is complete when the exact accepted Candidate is merged, merged-tree identity equals the accepted Candidate tree, post-merge bounded regression is green, and Issue #1007 contains a closure receipt that explicitly separates source merge from runtime/release/production claims. Then STOP; `AUTO_CHAIN=false`.
