# NEXUS_LOCAL_MODEL_ARMOR_WIRING_PLAN_v1.1

Status: REVISED_AFTER_CODEX_AUDIT
Date: 2026-06-28
Owner: James Chen / Nexus
Purpose: Provide a corrected end-to-end wiring plan for Local Model Nexus Armor, grounded in the May 2026 routing analysis and the 2026-06-28 MCP/codebase audit.

---

## 0. Revision note

This v1.1 replaces the incorrect assumption in v1.0 that P4 was mainly a confirmation step.

The codebase audit confirmed the key correction:

- `scripts/bench/capability_ab_runner.py` currently has zero references to `LocalHealCapabilityAdapter`, `LocalHealCapabilityRequest`, `capability_adapter`, `isolated_local`, or `run_isolated_local_solve_loop`.
- Therefore P4 is the actual implementation step: connect the existing LocalHeal capability adapter into the A-side runner path.
- P1 is considered completed by the external verification report.
- P2 is simplified because `nexus/contracts/hybrid_route.py` already hard-blocks most safety invariants in `HybridRouteDecision.__post_init__()` via `validate_hybrid_route_decision()`.
- P3 is changed from vague field propagation to an explicit adapter-to-runner row mapping specification.

This document is a planning artifact only. It does not claim implementation is complete.

---

## 1. Ground truth: four execution paths

### Path A — May CapabilityPlanner / with_nexus mainline

Definition:

- Primary verified Nexus route from May 2026 Gemini+Nexus benchmark results.
- Entry point: `scripts/bench/capability_ab_runner.py`.
- Route planner: `nexus/engine/capability_planner.py`.
- Evidence producer: `write_evidence_bundle()` in `capability_ab_runner.py`.
- Governance includes S,P,X,D,R,A,C, MemPalace, Artifact Gate, Claim Gate, Delivery Gate, Belief, evidence bundle, public-safe outcome.

Current status:

- EXISTS.
- VERIFIED historically by May benchmark route analysis.
- MUST NOT be rebuilt.
- MUST remain the route truth source.

Invariant:

```text
route_truth_source = CapabilityPlanner
```

### Path B — June LocalHeal / local model pipeline

Definition:

- Local Qwen / Ollama repair pipeline.
- Main modules include:
  - `nexus/services/local_heal/orchestrator.py`
  - `nexus/services/local_heal/native_route_adapter.py`
  - `nexus/services/local_heal/capability_adapter.py`
  - `nexus/services/local_heal/committee_orchestrator.py`
  - `nexus/services/local_heal/isolated_local_solve_loop.py`
  - `nexus/services/local_heal/isolated_workspace_apply.py`

Current status:

- EXISTS.
- Can call local model behind explicit env gates.
- Has its own five-phase repair pipeline.
- Is not equivalent to Path A.

### Path C — H5-H8 Local-to-Capability bridge

Definition:

- Existing bridge/scaffold for connecting Path B local output into Path A governance, with strict fail-closed semantics.
- Core modules:
  - `nexus/contracts/hybrid_route.py`
  - `nexus/services/local_heal/capability_adapter.py`
  - `nexus/services/local_heal/local_guard_fail_closed.py`
  - H5/H6 rows and evidence bundle fields inside `scripts/bench/capability_ab_runner.py`.

Current status:

- EXISTS.
- Trace-only / report-only / test-only in the current boundary.
- Hard locked:
  - `public_claim_allowed=false`
  - `production_ready=false`
  - `adapter_output_is_route_truth=false`
  - route truth source is Path A / CapabilityPlanner.

### Path D — isolated diagnostics / probe scripts

Definition:

- Offline probe and regression scripts, including:
  - `scripts/local_heal/run_june_regression_pack.py`
  - real Qwen small batch eval scripts
  - isolated memory eval scripts
  - previous real_model_probe/FakePhase work

Current status:

- Useful for diagnostics only.
- MUST NOT be treated as the Local Model Armor mainline.
- MUST NOT be used to claim A/B/C integration.

---

## 2. Non-negotiable invariants

These invariants are already largely encoded in `nexus/contracts/hybrid_route.py` and must remain true through the full integration.

### 2.1 Route truth

```text
Path A / CapabilityPlanner is the route truth.
Adapter output is never route truth.
```

Required invariant:

```text
route_truth_source == "CapabilityPlanner"
adapter_output_is_route_truth == false
```

### 2.2 Claim and production locks

```text
public_claim_allowed == false
production_ready == false
```

These remain locked until a separate promotion plan explicitly changes public-claim policy. This wiring plan does not unlock them.

### 2.3 Behavior change lock

Default:

```text
behavior_changed == false
```

Behavior change is not allowed during trace-only, advisory-only, dry-run, or shadow local adapter stages.

### 2.4 Local-only executed requirements

`LOCAL_ONLY_EXECUTED` is forbidden unless all conditions are met:

```text
local_model_called == true
verifier_result == pass
evidence_refs present
candidate_output_isolated == true
selected_candidate_hash present
applied_patch_hash present
selected_candidate_hash_matches_applied == true
```

### 2.5 No route substitution

The integration must not create a fifth route system.

Forbidden:

```text
new runner replacing capability_ab_runner.py
Path D promoted to mainline
LocalHeal bypassing CapabilityPlanner as route truth
adapter public claim gate independent of Path A
```

---

## 3. Corrected phase sequence

## P0 — Freeze wrong-path usage

Status: READY / documentation-only

Goal:

- Explicitly classify Path D as diagnostic-only.
- Stop using `run_june_regression_pack.py`, `test_real_model_probe.py`, or FakePhase as proof of A/B/C integration.

Allowed changes:

- Documentation/report only.

Forbidden changes:

- No production code changes.
- No benchmark behavior change.

Acceptance:

- A short report states:
  - Path D is diagnostic-only.
  - Path A remains the mainline.
  - Path B connects only through Path C into Path A.

Suggested artifact:

```text
docs/reports/local_model_armor_path_freeze_p0.md
```

---

## P1 — Four-path reality audit

Status: DONE by external verification report

External verification conclusion:

- A/B/C/D four-path definition is correct.
- Path A owns route truth.
- Path B owns local model execution capability.
- Path C owns the Local-to-Capability bridge contract.
- Path D is diagnostic-only.

No immediate code work required.

Recommended action:

- Save the external verification report as an audit artifact.

Suggested artifact:

```text
docs/reports/local_model_armor_four_path_audit_p1.md
```

---

## P2 — Simplified safety invariant test closure

Status: PARTIAL; simplify from v1.0

Reason for simplification:

`nexus/contracts/hybrid_route.py` already hard-blocks most violations through `HybridRouteDecision.__post_init__()` and `validate_hybrid_route_decision()`.

Already protected by contract:

```text
public_claim_allowed=true -> ValueError
production_ready=true -> ValueError
adapter_output_is_route_truth=true -> ValueError
route_truth_source != CapabilityPlanner -> ValueError
LOCAL_ONLY_EXECUTED missing model call -> ValueError
LOCAL_ONLY_EXECUTED missing verifier pass -> ValueError
LOCAL_ONLY_EXECUTED missing evidence refs -> ValueError
LOCAL_ONLY_EXECUTED missing candidate isolation -> ValueError
LOCAL_ONLY_EXECUTED missing selected hash -> ValueError
LOCAL_ONLY_EXECUTED missing applied hash -> ValueError
LOCAL_ONLY_EXECUTED hash mismatch -> ValueError
TRACE_ONLY with behavior_changed=true -> ValueError
ADVISORY_ONLY with behavior_changed=true -> ValueError
TRACE_ONLY authority mismatch -> ValueError
ADVISORY_ONLY authority mismatch -> ValueError
```

Correct P2 goal:

- Do not rewrite all invariant tests from zero.
- First run existing tests.
- Add only missing edge-case tests, especially behavior_changed and authority mismatch coverage if not already covered.

Target files:

```text
tests/contracts/test_hybrid_route_contract.py
```

Focused test command:

```bash
python3 -m pytest tests/contracts/test_hybrid_route_contract.py -q -rs
```

Acceptance:

- Existing contract test suite passes.
- Missing edge cases are added only if coverage is absent.
- No production code change unless a real contract gap is discovered.

Commit message if tests added:

```text
Harden hybrid route contract edge cases
```

---

## P3 — Define adapter-to-runner row mapping schema

Status: REQUIRED before P4

Correction from v1.0:

P3 is not just field propagation. Because Path A currently does not consume `LocalHealCapabilityAdapter`, P3 must first define the exact mapping from adapter output to `capability_ab_runner.py` row/evidence fields.

Goal:

- Define how `LocalHealCapabilityResponse.capability_payload` and `HybridRouteDecision.to_dict()` are represented inside Path A row metadata.
- Keep all locks in place:
  - `public_claim_allowed=false`
  - `production_ready=false`
  - `behavior_changed=false` unless future promotion explicitly allows otherwise.
  - `adapter_output_is_route_truth=false`

Proposed row schema additions under Path A rows:

```json
{
  "local_model_adapter": {
    "schema": "nexus.local_model_adapter_row.v1",
    "enabled": false,
    "adapter_invoked": false,
    "route_mode": "cloud_assisted_by_local_trace_only",
    "authority": "trace_only",
    "route_truth_source": "CapabilityPlanner",
    "adapter_output_is_route_truth": false,
    "public_claim_allowed": false,
    "production_ready": false,
    "behavior_changed": false,
    "local_model_called": false,
    "candidate_output_isolated": true,
    "selected_candidate_hash": "",
    "applied_patch_hash": "",
    "selected_candidate_hash_matches_applied": false,
    "verifier_result": "not_run",
    "evidence_refs": [],
    "fallback_block_reason": "",
    "blockers": [],
    "metadata": {}
  }
}
```

Relationship with existing `h5_route`:

- `h5_route` remains the H5 trace scaffold.
- `local_model_adapter` is the adapter bridge row.
- Do not overload `h5_route` with adapter payload unless an explicit mapping function documents it.
- Evidence bundle may summarize both, but they must remain distinguishable.

Mapping source:

```text
LocalHealCapabilityResponse.hybrid_route.to_dict()
LocalHealCapabilityResponse.capability_payload
```

Mapping destination:

```text
row["local_model_adapter"]
payload["local_model_adapter_summary"]
```

Acceptance:

- A small mapping spec exists before code integration.
- Tests can validate mapping without invoking local model.
- Public/production/behavior locks remain false.

Suggested artifact:

```text
docs/reports/local_model_adapter_runner_row_mapping_p3.md
```

---

## P4 — Implement adapter invocation inside Path A runner

Status: CRITICAL IMPLEMENTATION STEP

Correction from v1.0:

P4 is not a confirmation step. MCP/codebase audit confirms `scripts/bench/capability_ab_runner.py` currently has zero direct references to:

```text
LocalHealCapabilityAdapter
LocalHealCapabilityRequest
capability_adapter
isolated_local
run_isolated_local_solve_loop
```

Therefore this is the real missing wire.

Goal:

- Add a minimal, guarded invocation seam from Path A row finalization into `LocalHealCapabilityAdapter.run()`.
- The seam must be opt-in, disabled by default, and non-mutating unless explicit env gates allow mutation.

Design constraints:

1. The import must be lazy/local to avoid increasing normal runner import cost.
2. The adapter must be invoked only when a dedicated flag is enabled.
3. The adapter response must be recorded under the P3 mapping schema.
4. Adapter output must not replace Path A route truth.
5. Adapter output must not set public claim or production readiness.
6. Default mode must be trace-only / dry-run.

Proposed env gate:

```text
NEXUS_WITH_LOCAL_MODEL_ADAPTER=1
```

Existing adapter env gates remain authoritative:

```text
NEXUS_LOCAL_MODEL_ADVISORY_ENABLE
NEXUS_LOCAL_MODEL_CANDIDATE_ENABLE
NEXUS_LOCAL_MODEL_CALL_ALLOWED
NEXUS_LOCAL_SOLVE_ISOLATED_ENABLE
NEXUS_LOCAL_SOLVE_MUTATION_ALLOWED
NEXUS_LOCAL_SOLVE_VERIFIER_ALLOWED
NEXUS_LOCAL_GUARD_FAIL_CLOSED_ENABLE
```

Proposed runner hook location:

- Inside `scripts/bench/capability_ab_runner.py`, after row has enough task/evidence context but before evidence bundle write.
- Candidate location must be selected by Codex after reading `_finalize_with_nexus_row`, `run_with_nexus`, and `write_evidence_bundle` flow.

Pseudo-flow:

```python
if os.environ.get("NEXUS_WITH_LOCAL_MODEL_ADAPTER") == "1":
    from nexus.services.local_heal.capability_adapter import (
        LocalHealCapabilityAdapter,
        LocalHealCapabilityRequest,
    )

    req = LocalHealCapabilityRequest(
        task_id=task.id,
        problem_statement=task.prompt_or_desc,
        evidence_refs=tuple(existing_evidence_refs),
        executor_controls=build_local_adapter_controls(row, task, route_context),
        dry_run=True,
    )
    resp = LocalHealCapabilityAdapter.run(req)
    row["local_model_adapter"] = map_adapter_response_to_row(resp)
else:
    row["local_model_adapter"] = disabled_local_model_adapter_row()
```

Important:

- `dry_run=True` is the default.
- Do not pass mutation controls unless explicitly enabled.
- Do not call local model unless `NEXUS_LOCAL_MODEL_CALL_ALLOWED=1` and related adapter flags are enabled.

Acceptance:

- With env disabled: row contains disabled adapter metadata or no adapter metadata, and existing tests do not regress.
- With env enabled but no model call allowed: adapter row appears, `adapter_invoked` may be true or false depending on mode, `local_model_called=false`, blockers explain why.
- With advisory enabled and injected provider in tests: local advisory path can be exercised without real Ollama.
- With candidate isolated dry-run: no repo mutation, no public claim, no production readiness.

Suggested tests:

```text
tests/benchmark/test_capability_ab_runner.py
```

Focused command:

```bash
python3 -m pytest tests/benchmark/test_capability_ab_runner.py -k "hybrid_route or local_guard or local_model_adapter" -q -rs
```

Commit message:

```text
Wire local model adapter into capability runner trace path
```

---

## P5 — Real local model smoke through Path A, guarded

Status: DEPENDS ON P4

Goal:

- Run a minimal local model smoke through Path A runner, not through Path D.
- Confirm the row/evidence bundle records local adapter activity correctly.

Allowed:

- One synthetic or controlled fixture.
- Ollama/Qwen call only with explicit env gates.
- No production mutation.
- No public claim.

Required env example:

```bash
NEXUS_WITH_LOCAL_MODEL_ADAPTER=1
NEXUS_LOCAL_MODEL_ADVISORY_ENABLE=1
NEXUS_LOCAL_MODEL_CALL_ALLOWED=1
NEXUS_LOCAL_MODEL_PROVIDER=ollama
NEXUS_LOCAL_MODEL_NAME=qwen2.5-coder:7b
```

Acceptance:

- Path A runner executes.
- Evidence bundle includes `local_model_adapter` or summary fields.
- `route_truth_source=CapabilityPlanner`.
- `adapter_output_is_route_truth=false`.
- `public_claim_allowed=false`.
- `production_ready=false`.
- `behavior_changed=false`.

No allowed claim:

```text
Qwen solved
production ready
public benchmark ready
local-only executed
```

---

## P6 — Candidate mode through Path A, dry-run only

Status: DEPENDS ON P4/P5

Goal:

- Exercise candidate generation path from Path A runner through the adapter, but still without mutation.

Required locks:

```text
NEXUS_LOCAL_SOLVE_MUTATION_ALLOWED != 1
NEXUS_LOCAL_SOLVE_VERIFIER_ALLOWED may remain 0 unless test specifically verifies safe verifier path
```

Acceptance:

- Adapter can produce candidate metadata.
- Candidate remains isolated.
- No repo mutation.
- No behavior change.
- No public claim.
- No production readiness.

---

## P7 — Isolated solve mode through Path A, mutation allowed only in isolated workspace

Status: DEPENDS ON P6

Goal:

- Exercise isolated local solve loop through Path A runner.
- Mutation is allowed only inside isolated workspace.
- Verifier is allowed only under explicit env gate.

Required env gates:

```text
NEXUS_WITH_LOCAL_MODEL_ADAPTER=1
NEXUS_LOCAL_MODEL_CANDIDATE_ENABLE=1
NEXUS_LOCAL_SOLVE_ISOLATED_ENABLE=1
NEXUS_LOCAL_SOLVE_MUTATION_ALLOWED=1
NEXUS_LOCAL_SOLVE_VERIFIER_ALLOWED=1
NEXUS_LOCAL_GUARD_FAIL_CLOSED_ENABLE=1
```

Required evidence:

```text
selected_candidate_hash
applied_patch_hash
selected_candidate_hash_matches_applied
verifier_result
evidence_refs
fallback_block_reason / blockers
```

Acceptance:

- If any required evidence is missing, route becomes fail-closed or local-only-blocked.
- If verifier fails, no solved claim.
- If hash mismatch occurs, no behavior_changed and no claim.
- `public_claim_allowed=false` remains locked.
- `production_ready=false` remains locked.

---

## P8 — Evidence bundle integration

Status: DEPENDS ON P4-P7

Goal:

- Add evidence bundle summaries for local model adapter rows.
- Keep the summary separate from existing H5/H6 summaries unless deliberately unified by a tested mapping layer.

Proposed payload addition:

```json
{
  "local_model_adapter_summary": {
    "adapter_trace_count": 0,
    "adapter_invoked_count": 0,
    "local_model_called_count": 0,
    "candidate_isolated_count": 0,
    "hash_match_count": 0,
    "verifier_pass_count": 0,
    "fail_closed_count": 0,
    "behavior_changed_count": 0,
    "public_claim_allowed_count": 0,
    "production_ready_count": 0
  }
}
```

Acceptance:

- Summary counts are deterministic.
- `behavior_changed_count` remains 0 for all non-promoted phases.
- `public_claim_allowed_count` remains 0.
- `production_ready_count` remains 0.

---

## P9 — Promotion readiness report, not promotion

Status: FINAL REVIEW STEP

Goal:

- Produce a readiness report stating whether Path B is safely wired through Path C into Path A.
- This step does not unlock production or public claims.

Report must answer:

1. Does Path A remain route truth?
2. Does Path A invoke the adapter only behind env gates?
3. Are adapter outputs recorded in runner rows?
4. Are adapter outputs included in evidence bundle summaries?
5. Are public/production locks still enforced?
6. Is behavior_changed still false outside explicit future promotion?
7. Is LocalHeal still forbidden from independently setting route truth?
8. Are Path D diagnostics excluded from mainline claims?

Suggested artifact:

```text
docs/reports/local_model_armor_wiring_readiness_p9.md
```

---

## 4. Codex execution rules

Before editing:

```bash
git status --short
rg -n "LocalHealCapabilityAdapter|capability_adapter|isolated_local|run_isolated_local_solve_loop" scripts/bench/capability_ab_runner.py || true
python3 -m pytest tests/contracts/test_hybrid_route_contract.py -q -rs
```

When editing:

- Touch at most 3-5 files per phase.
- Do not use `git add -A`.
- Do not commit artifacts.
- Do not modify Path D as part of the mainline wiring task.
- Do not introduce a new runner.
- Do not loosen `hybrid_route.py` invariants.

Allowed likely files:

```text
scripts/bench/capability_ab_runner.py
tests/benchmark/test_capability_ab_runner.py
tests/contracts/test_hybrid_route_contract.py
docs/reports/*.md
```

Use additional files only after reporting why.

---

## 5. Minimal next Codex task

Task:

```text
P2-P3 only. Do not implement P4 yet.

1. Run existing hybrid route contract tests.
2. Add only missing edge-case tests for behavior_changed and authority mismatch if not already covered.
3. Create adapter-to-runner row mapping spec.
4. Do not touch capability_ab_runner.py production code yet.
```

Commands:

```bash
python3 -m pytest tests/contracts/test_hybrid_route_contract.py -q -rs
python3 -m pytest tests/unit/local_heal/test_capability_adapter.py tests/unit/local_heal/test_local_guard_fail_closed.py -q -rs
```

Expected output:

```text
1. current HEAD
2. git status --short
3. whether P2 needed new tests
4. adapter-to-runner row mapping spec path
5. test results
6. COMMIT_READY or HOLD
7. proposed files
8. proposed commit message
```

Commit message if only docs/tests:

```text
Document local adapter runner row mapping contract
```

---

## 6. Final corrected strategy

Correct strategy:

```text
Do not rebuild A.
Do not promote D.
Do not assume C is missing.
Use C as the bridge.
Implement only the missing A-side invocation seam from capability_ab_runner.py to LocalHealCapabilityAdapter.
Keep all locks false until a separate promotion plan.
```

The real engineering breakpoint is P4.
