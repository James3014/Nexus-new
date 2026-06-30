# NEXUS_LOCAL_MODEL_ARMOR_P_TASKS_v1.1

Status: TASK_CARD_EXPANSION_FOR_CODEX_REVIEW
Date: 2026-06-28
Source Plan: NEXUS_LOCAL_MODEL_ARMOR_WIRING_PLAN_v1.1
Purpose: Expand each P-phase into executable, reviewable Codex task cards without inventing unverified wiring.

---

## Global framing

Four execution paths must remain separate:

```text
A = May CapabilityPlanner / with_nexus mainline
B = June LocalHeal / local Qwen pipeline
C = H5-H8 Local-to-Capability bridge
D = isolated diagnostics / probe scripts
```

Primary strategy:

```text
Do not rebuild A.
Do not promote D.
Do not assume C is missing.
Use C as the bridge.
Implement only the missing A-side invocation seam from capability_ab_runner.py to LocalHealCapabilityAdapter.
Keep public_claim_allowed=false, production_ready=false, and behavior_changed=false until a separate promotion plan.
```

Hard invariants:

```text
route_truth_source == "CapabilityPlanner"
adapter_output_is_route_truth == false
public_claim_allowed == false
production_ready == false
behavior_changed == false for trace/advisory/dry-run/shadow stages
Path D cannot prove A/B/C integration
No new runner
No run_june_regression_pack.py mainline promotion
No public Qwen solved claim
```

Current MCP/codebase audit anchors:

```text
scripts/bench/capability_ab_runner.py has zero references to LocalHealCapabilityAdapter / capability_adapter / isolated_local.
nexus/contracts/hybrid_route.py already enforces most fail-closed invariants.
nexus/services/local_heal/capability_adapter.py already has env gates for advisory/candidate/call/isolated/mutation/verifier.
Relevant tests already exist under tests/contracts, tests/unit/local_heal, tests/integration, tests/engine, and tests/benchmark.
```

---

# P0 — Freeze wrong-path usage

## Objective

Classify Path D as diagnostic-only and stop treating LocalHeal probe scripts, FakePhase, or June regression replay as proof of Local Model Armor mainline integration.

## Scope

Documentation/report only.

## Allowed files

```text
docs/reports/local_model_armor_path_freeze_p0.md
```

## Forbidden

```text
Do not edit scripts/local_heal/run_june_regression_pack.py.
Do not edit tests/integration/test_real_model_probe.py.
Do not edit capability_ab_runner.py.
Do not change benchmark behavior.
Do not create a new runner.
Do not claim Qwen solved.
```

## Task steps

1. Record the four-path model:

```text
A = CapabilityPlanner / capability_ab_runner.py / with_nexus mainline
B = LocalHeal / Qwen / Ollama local repair pipeline
C = H5-H8 Local-to-Capability bridge
D = isolated diagnostic/probe scripts
```

2. State explicitly that Path D includes:

```text
scripts/local_heal/run_june_regression_pack.py
scripts/local_heal/run_real_qwen_small_batch_eval.py
real_model_probe / FakePhase artifacts
isolated memory eval scripts
```

3. State that Path D may be used for diagnostics, regression, and local model probing only.

4. State that Path D must not be cited as:

```text
A-side integration evidence
CapabilityPlanner evidence
with_nexus evidence
public benchmark evidence
production readiness evidence
Qwen solved evidence
```

5. Add a small decision table:

| Evidence source | Allowed claim |
|---|---|
| Path A with_nexus row/evidence bundle | A-side route evidence |
| Path B LocalHeal receipt | local repair pipeline evidence |
| Path C hybrid route decision / adapter row | bridge evidence |
| Path D probe | diagnostic-only evidence |

## Verification commands

Read-only only:

```bash
git status --short
rg -n "run_june_regression_pack|real_model_probe|FakePhase|Path D|diagnostic-only" docs/reports/local_model_armor_path_freeze_p0.md
```

## Acceptance criteria

```text
Report exists.
Report clearly says Path D is diagnostic-only.
Report says Path A remains route truth.
Report says Path B reaches Path A only through Path C bridge.
No production code changed.
```

## Expected final report format

```text
1. current HEAD
2. git status --short
3. file created/updated
4. Path D freeze statement
5. COMMIT_READY / HOLD
6. proposed commit message
```

## Commit message

```text
Document local model diagnostic path freeze
```

---

# P1 — Four-path reality audit

## Objective

Persist the completed external/codebase verification as the official four-path audit artifact.

## Status

P1 is already substantively done by the provided verification report. This phase is mainly archival and normalization.

## Allowed files

```text
docs/reports/local_model_armor_four_path_audit_p1.md
```

## Forbidden

```text
Do not edit production code.
Do not re-run full benchmark.
Do not reinterpret Path D as mainline.
Do not add new routing design.
```

## Task steps

1. Save the verified conclusions:

```text
A/B/C/D four-path definition is correct.
A owns route truth.
B owns local model execution capability.
C owns bridge/contract/fail-closed semantics.
D is diagnostic-only.
```

2. Include codebase facts:

```text
capability_ab_runner.py exists and is the A-side runner.
capability_planner.py exists and is route planner.
capability_adapter.py exists and is B/C adapter seam.
hybrid_route.py exists and validates fail-closed route decisions.
capability_ab_runner.py currently has no LocalHealCapabilityAdapter import/reference.
```

3. Include the four required corrections from the verification report:

```text
P4 is implementation, not confirmation.
P2 is simplified because hybrid_route.py already guards most invariants.
P3 must define adapter-to-runner row mapping schema.
P1 can be marked DONE after archival.
```

4. Include a status table:

| Path | Status | Main file | Integration state |
|---|---|---|---|
| A | verified mainline | scripts/bench/capability_ab_runner.py | route truth |
| B | exists | nexus/services/local_heal/* | local pipeline |
| C | exists | nexus/contracts/hybrid_route.py + capability_adapter.py | bridge scaffold |
| D | exists | scripts/local_heal/* | diagnostic only |

## Verification commands

```bash
git status --short
rg -n "A owns route truth|P4 is implementation|diagnostic-only|LocalHealCapabilityAdapter" docs/reports/local_model_armor_four_path_audit_p1.md
```

## Acceptance criteria

```text
P1 report exists.
The report marks P1 as DONE.
The report preserves P4 as CRITICAL IMPLEMENTATION STEP.
No production code changed.
```

## Commit message

```text
Archive local model armor four path audit
```

---

# P2 — Simplified safety invariant test closure

## Objective

Close missing edge-case tests around `nexus/contracts/hybrid_route.py` without rewriting already-covered invariants.

## Scope

Contract tests first. Production code only changes if tests reveal a real missing invariant.

## Target files

Primary:

```text
tests/contracts/test_hybrid_route_contract.py
```

Production file, only if a real contract bug is found:

```text
nexus/contracts/hybrid_route.py
```

## Pre-check

Run:

```bash
git status --short
python3 -m pytest tests/contracts/test_hybrid_route_contract.py -q -rs
rg -n "behavior_changed|trace_only_requires|advisory_requires|public_claim_allowed_must_be_false|production_ready_must_be_false|adapter_output_is_route_truth_must_be_false|local_only_executed_requires" tests/contracts/test_hybrid_route_contract.py nexus/contracts/hybrid_route.py
```

## Task steps

1. Inspect existing test coverage in `tests/contracts/test_hybrid_route_contract.py`.

2. Confirm whether these cases already exist:

```text
public_claim_allowed=true rejected
production_ready=true rejected
adapter_output_is_route_truth=true rejected
route_truth_source != CapabilityPlanner rejected
LOCAL_ONLY_EXECUTED without local_model_called rejected
LOCAL_ONLY_EXECUTED without verifier pass rejected
LOCAL_ONLY_EXECUTED without evidence_refs rejected
LOCAL_ONLY_EXECUTED without candidate isolation rejected
LOCAL_ONLY_EXECUTED without selected hash rejected
LOCAL_ONLY_EXECUTED without applied hash rejected
LOCAL_ONLY_EXECUTED with hash mismatch rejected
TRACE_ONLY with behavior_changed=true rejected
ADVISORY_ONLY with behavior_changed=true rejected
TRACE_ONLY with non-trace authority rejected
ADVISORY_ONLY with non-advisory authority rejected
```

3. Add only absent tests. Suggested test names:

```text
test_trace_only_rejects_behavior_changed_true
test_advisory_only_rejects_behavior_changed_true
test_trace_only_rejects_non_trace_authority
test_advisory_only_rejects_non_advisory_authority
test_local_only_executed_rejects_hash_mismatch
```

4. Prefer asserting `ValueError` through `HybridRouteDecision(...)` or `hybrid_route_decision_from_payload(...)`, because `__post_init__()` is the actual enforcement seam.

5. Do not loosen any invariant to make tests pass.

## Verification commands

```bash
python3 -m pytest tests/contracts/test_hybrid_route_contract.py -q -rs
python3 -m pytest tests/unit/local_heal/test_local_guard_fail_closed.py -q -rs
```

## Acceptance criteria

```text
Existing contract tests pass.
Any missing behavior_changed/authority mismatch edge cases are covered.
No production code changed unless a real contract gap is proven.
No invariant is loosened.
```

## HOLD conditions

```text
A test requires weakening public_claim_allowed or production_ready lock.
A test requires route_truth_source other than CapabilityPlanner.
LOCAL_ONLY_EXECUTED can be constructed without hash/verifier/evidence.
```

## Expected final report format

```text
1. current HEAD
2. git status --short
3. existing tests run
4. new tests added, or "no new tests needed"
5. contract gaps found: yes/no
6. production code changed: yes/no
7. test output summary
8. COMMIT_READY / HOLD
9. proposed files
10. proposed commit message
```

## Commit message

```text
Harden hybrid route contract edge cases
```

---

# P3 — Define adapter-to-runner row mapping schema

## Objective

Define the exact schema that maps `LocalHealCapabilityAdapter` output into `capability_ab_runner.py` rows and evidence bundle summaries before implementing P4.

## Scope

Documentation and optionally pure test fixtures. No A-side production hook yet.

## Target files

Primary:

```text
docs/reports/local_model_adapter_runner_row_mapping_p3.md
```

Optional tests if Codex chooses to formalize fixture expectations without production hook:

```text
tests/benchmark/test_capability_ab_runner.py
```

## Forbidden

```text
Do not import LocalHealCapabilityAdapter into capability_ab_runner.py yet.
Do not implement P4 in P3.
Do not call Ollama.
Do not mutate repos.
Do not overload h5_route with adapter payload without a documented mapping rule.
```

## Task steps

1. Define row field:

```text
row["local_model_adapter"]
```

2. Define disabled default row:

```json
{
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
```

3. Define mapping from `HybridRouteDecision.to_dict()`:

| Source | Destination |
|---|---|
| route_mode | row.local_model_adapter.route_mode |
| authority | row.local_model_adapter.authority |
| route_truth_source | row.local_model_adapter.route_truth_source |
| adapter_output_is_route_truth | row.local_model_adapter.adapter_output_is_route_truth |
| public_claim_allowed | row.local_model_adapter.public_claim_allowed |
| production_ready | row.local_model_adapter.production_ready |
| behavior_changed | row.local_model_adapter.behavior_changed |
| local_model_called | row.local_model_adapter.local_model_called |
| candidate_output_isolated | row.local_model_adapter.candidate_output_isolated |
| selected_candidate_hash | row.local_model_adapter.selected_candidate_hash |
| applied_patch_hash | row.local_model_adapter.applied_patch_hash |
| selected_candidate_hash_matches_applied | row.local_model_adapter.selected_candidate_hash_matches_applied |
| verifier_result | row.local_model_adapter.verifier_result |
| evidence_refs | row.local_model_adapter.evidence_refs |
| fallback_block_reason | row.local_model_adapter.fallback_block_reason |
| blockers | row.local_model_adapter.blockers |
| metadata | row.local_model_adapter.metadata |

4. Define mapping from `LocalHealCapabilityResponse`:

| Source | Destination |
|---|---|
| response.invoked | row.local_model_adapter.adapter_invoked |
| response.capability_payload | row.local_model_adapter.metadata.capability_payload_summary or metadata.adapter_payload |
| response.hybrid_route | row.local_model_adapter route fields |

5. Define summary payload for evidence bundle:

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

6. Define relationship with `h5_route`:

```text
h5_route remains H5 trace scaffold.
local_model_adapter is the adapter bridge row.
Evidence bundle may summarize both separately.
Do not merge the two fields until a later explicit mapping phase.
```

7. Define required blockers:

```text
missing_adapter_context
model_call_not_allowed
mutation_not_allowed
verifier_not_allowed
missing_required_control
local_guard_fail_closed
invalid_route_truth_source
public_claim_allowed_must_be_false
production_ready_must_be_false
behavior_changed_true
```

## Verification commands

```bash
rg -n "local_model_adapter|adapter_trace_count|route_truth_source|behavior_changed|public_claim_allowed" docs/reports/local_model_adapter_runner_row_mapping_p3.md
python3 -m pytest tests/contracts/test_hybrid_route_contract.py -q -rs
python3 -m pytest tests/unit/local_heal/test_capability_adapter.py tests/unit/local_heal/test_local_guard_fail_closed.py -q -rs
```

## Acceptance criteria

```text
Mapping spec exists.
Spec distinguishes h5_route from local_model_adapter.
Spec preserves all public/production/behavior locks.
Spec does not claim P4 is implemented.
Focused tests pass.
```

## Commit message

```text
Document local adapter runner row mapping contract
```

---

# P4 — Implement adapter invocation inside Path A runner

## Objective

Implement the missing A-side invocation seam from `scripts/bench/capability_ab_runner.py` to `LocalHealCapabilityAdapter.run()`.

## Status

CRITICAL IMPLEMENTATION STEP.

## Why this is critical

MCP audit confirms `capability_ab_runner.py` currently has zero direct references to:

```text
LocalHealCapabilityAdapter
LocalHealCapabilityRequest
capability_adapter
isolated_local
run_isolated_local_solve_loop
```

Therefore P4 is not confirmation. It is the real missing wire.

## Target files

Likely:

```text
scripts/bench/capability_ab_runner.py
tests/benchmark/test_capability_ab_runner.py
```

Optional only if needed:

```text
docs/reports/local_model_adapter_runner_row_mapping_p3.md
```

## Forbidden

```text
Do not create a new runner.
Do not modify run_june_regression_pack.py.
Do not loosen hybrid_route.py invariants.
Do not allow adapter output to become route truth.
Do not set public_claim_allowed=true.
Do not set production_ready=true.
Do not set behavior_changed=true.
Do not call local model by default.
Do not mutate repo by default.
```

## Pre-check

```bash
git status --short
rg -n "LocalHealCapabilityAdapter|LocalHealCapabilityRequest|capability_adapter|isolated_local|run_isolated_local_solve_loop" scripts/bench/capability_ab_runner.py || true
rg -n "def _finalize_with_nexus_row|def run_with_nexus|def write_evidence_bundle|h5_route|local_guard" scripts/bench/capability_ab_runner.py
python3 -m pytest tests/contracts/test_hybrid_route_contract.py -q -rs
```

## Task steps

1. Locate the safest A-side hook.

Codex must inspect these flows before editing:

```text
run_with_nexus(...)
_finalize_with_nexus_row(...)
write_evidence_bundle(...)
h5_route finalization block
hybrid_route_summary block
```

2. Add disabled default helper, preferably pure:

```python
def _disabled_local_model_adapter_row(reason: str = "disabled") -> dict[str, Any]:
    return {
        "schema": "nexus.local_model_adapter_row.v1",
        "enabled": False,
        "adapter_invoked": False,
        "route_mode": "cloud_assisted_by_local_trace_only",
        "authority": "trace_only",
        "route_truth_source": "CapabilityPlanner",
        "adapter_output_is_route_truth": False,
        "public_claim_allowed": False,
        "production_ready": False,
        "behavior_changed": False,
        "local_model_called": False,
        "candidate_output_isolated": True,
        "selected_candidate_hash": "",
        "applied_patch_hash": "",
        "selected_candidate_hash_matches_applied": False,
        "verifier_result": "not_run",
        "evidence_refs": [],
        "fallback_block_reason": reason,
        "blockers": [reason] if reason else [],
        "metadata": {},
    }
```

3. Add adapter response mapping helper, preferably pure:

```python
def _map_local_model_adapter_response_to_row(resp) -> dict[str, Any]:
    route = resp.hybrid_route.to_dict()
    return {
        "schema": "nexus.local_model_adapter_row.v1",
        "enabled": True,
        "adapter_invoked": bool(resp.invoked),
        "route_mode": route.get("route_mode", "cloud_assisted_by_local_trace_only"),
        "authority": route.get("authority", "trace_only"),
        "route_truth_source": route.get("route_truth_source", "CapabilityPlanner"),
        "adapter_output_is_route_truth": bool(route.get("adapter_output_is_route_truth", False)),
        "public_claim_allowed": bool(route.get("public_claim_allowed", False)),
        "production_ready": bool(route.get("production_ready", False)),
        "behavior_changed": bool(route.get("behavior_changed", False)),
        "local_model_called": bool(route.get("local_model_called", False)),
        "candidate_output_isolated": bool(route.get("candidate_output_isolated", True)),
        "selected_candidate_hash": str(route.get("selected_candidate_hash", "") or ""),
        "applied_patch_hash": str(route.get("applied_patch_hash", "") or ""),
        "selected_candidate_hash_matches_applied": bool(route.get("selected_candidate_hash_matches_applied", False)),
        "verifier_result": str(route.get("verifier_result", "not_run") or "not_run"),
        "evidence_refs": list(route.get("evidence_refs", []) or []),
        "fallback_block_reason": str(route.get("fallback_block_reason", "") or ""),
        "blockers": list(route.get("blockers", []) or []),
        "metadata": dict(route.get("metadata", {}) or {}),
    }
```

4. Add opt-in runner seam with lazy import:

```text
Gate: NEXUS_WITH_LOCAL_MODEL_ADAPTER=1
Default: disabled row or no-op row
Import: local/lazy inside helper only
```

5. Build adapter request only from existing A-side row/task/evidence context.

Minimum request fields:

```text
task_id
problem_statement
evidence_refs
executor_controls
dry_run=True
```

6. If required adapter context is missing, do not crash. Record disabled/fail-closed metadata:

```text
fallback_block_reason = missing_adapter_context
local_model_called = false
behavior_changed = false
public_claim_allowed = false
production_ready = false
```

7. Do not pass mutation controls unless explicit env gates are present:

```text
NEXUS_LOCAL_SOLVE_MUTATION_ALLOWED=1
NEXUS_LOCAL_SOLVE_VERIFIER_ALLOWED=1
```

8. Add row assignment:

```python
row["local_model_adapter"] = ...
```

9. Add tests in `tests/benchmark/test_capability_ab_runner.py`:

Required tests:

```text
test_local_model_adapter_disabled_by_default
test_local_model_adapter_env_enabled_no_model_call_records_blocker
test_local_model_adapter_does_not_change_route_truth
test_local_model_adapter_keeps_public_and_production_false
test_local_model_adapter_keeps_behavior_changed_false
```

10. Use injected/fake provider only in tests. Do not require real Ollama for P4 tests.

## Verification commands

```bash
python3 -m pytest tests/benchmark/test_capability_ab_runner.py -k "local_model_adapter or hybrid_route or local_guard" -q -rs
python3 -m pytest tests/contracts/test_hybrid_route_contract.py -q -rs
python3 -m pytest tests/unit/local_heal/test_capability_adapter.py tests/unit/local_heal/test_local_guard_fail_closed.py -q -rs
```

## Acceptance criteria

```text
Env disabled path has no behavior regression.
Env enabled path creates local_model_adapter row.
Adapter import is lazy/local.
No model call occurs unless NEXUS_LOCAL_MODEL_CALL_ALLOWED=1 and adapter mode env is enabled.
route_truth_source remains CapabilityPlanner.
adapter_output_is_route_truth remains false.
public_claim_allowed remains false.
production_ready remains false.
behavior_changed remains false.
Focused tests pass.
```

## HOLD conditions

```text
Need to rewrite run_with_nexus extensively.
Need to change hybrid_route.py invariant to pass tests.
Adapter row can set public_claim_allowed=true.
Adapter row can set production_ready=true.
Adapter row can set behavior_changed=true in trace/advisory/dry-run.
Real Ollama is required for unit/benchmark tests.
```

## Expected final report format

```text
1. current HEAD
2. git status --short
3. hook location chosen and why
4. files changed
5. env disabled behavior
6. env enabled no-call behavior
7. route_truth_source result
8. public_claim_allowed / production_ready / behavior_changed results
9. tests passed
10. COMMIT_READY / HOLD
11. proposed files
12. proposed commit message
```

## Commit message

```text
Wire local model adapter into capability runner trace path
```

---

# P5 — Real local model smoke through Path A, guarded

## Objective

Run a minimal local model smoke through Path A runner after P4, using the A-side adapter seam, not Path D.

## Dependencies

```text
P4 complete
local_model_adapter row exists in A-side runner
focused P4 tests pass
```

## Scope

Advisory or no-mutation local call first. Real Ollama only when explicitly enabled and available.

## Forbidden

```text
Do not use run_june_regression_pack.py as proof.
Do not claim solve.
Do not mutate source repo.
Do not enable production/public claim.
Do not run large benchmark.
```

## Task steps

1. Select one minimal controlled fixture already supported by `tests/benchmark/test_capability_ab_runner.py`.

2. Run A-side runner path with adapter env enabled and advisory-only mode.

Suggested env:

```bash
NEXUS_WITH_LOCAL_MODEL_ADAPTER=1
NEXUS_LOCAL_MODEL_ADVISORY_ENABLE=1
NEXUS_LOCAL_MODEL_CALL_ALLOWED=1
NEXUS_LOCAL_MODEL_PROVIDER=ollama
NEXUS_LOCAL_MODEL_NAME=qwen2.5-coder:7b
```

3. If Ollama is unavailable, do not fake success. Record:

```text
status = INFRA_BLOCKED or LOCAL_PROVIDER_UNAVAILABLE
local_model_called=false
public_claim_allowed=false
production_ready=false
behavior_changed=false
```

4. Confirm the A-side row/evidence contains:

```text
local_model_adapter.enabled=true
route_truth_source=CapabilityPlanner
adapter_output_is_route_truth=false
public_claim_allowed=false
production_ready=false
behavior_changed=false
local_model_called true only if provider actually called
```

5. Do not require verifier pass or solve in P5.

## Verification commands

Codex must choose the exact runner command from existing test/benchmark patterns. Minimum tests:

```bash
python3 -m pytest tests/benchmark/test_capability_ab_runner.py -k "local_model_adapter or hybrid_route or local_guard" -q -rs
python3 -m pytest tests/integration/test_local_model_ollama_smoke_contract.py -q -rs
```

## Acceptance criteria

```text
A-side runner path used.
Path D not used.
Adapter row/evidence visible.
Provider unavailable is reported honestly as blocked, not pass.
No public claim.
No production readiness.
No behavior change.
```

## Expected final report format

```text
1. current HEAD
2. command/env used
3. A-side runner evidence path
4. local_model_called true/false
5. provider status
6. local_model_adapter row excerpt
7. public/production/behavior locks
8. test results
9. COMMIT_READY / HOLD
```

## Commit policy

Prefer no commit unless test/docs changed.

---

# P6 — Candidate mode through Path A, dry-run only

## Objective

Exercise local candidate generation through the A-side runner seam without mutation.

## Dependencies

```text
P4 complete
P5 advisory/no-call smoke understood
```

## Required env shape

```bash
NEXUS_WITH_LOCAL_MODEL_ADAPTER=1
NEXUS_LOCAL_MODEL_CANDIDATE_ENABLE=1
NEXUS_LOCAL_MODEL_CALL_ALLOWED=1  # only for real provider smoke; tests should use injected provider
NEXUS_LOCAL_SOLVE_MUTATION_ALLOWED=0
NEXUS_LOCAL_SOLVE_VERIFIER_ALLOWED=0
```

## Forbidden

```text
No repo mutation.
No isolated solve loop mutation.
No verifier-required pass.
No public claim.
No production readiness.
No behavior change.
```

## Task steps

1. Add/extend benchmark test to run candidate path through A-side runner using injected provider.

2. Ensure candidate metadata appears under:

```text
row["local_model_adapter"]
```

3. Expected candidate fields:

```text
local_model_called
candidate_output_isolated
selected_candidate_hash
applied_patch_hash
selected_candidate_hash_matches_applied
verifier_result=not_run
fallback_block_reason/blockers
```

4. Because mutation is disabled, expected route mode should remain blocked/candidate/trace style, not production/executed.

5. Confirm no source files changed after test run except intentional test/docs changes.

## Verification commands

```bash
git status --short
python3 -m pytest tests/benchmark/test_capability_ab_runner.py -k "local_model_adapter or candidate" -q -rs
python3 -m pytest tests/unit/local_heal/test_capability_adapter.py tests/unit/local_heal/test_candidate_isolation_gate.py -q -rs
git status --short
```

## Acceptance criteria

```text
Candidate path is reachable from A-side runner.
Candidate remains isolated.
Mutation remains disabled.
Verifier remains not_run unless explicitly enabled in later P7.
public_claim_allowed=false.
production_ready=false.
behavior_changed=false.
```

## HOLD conditions

```text
Candidate path mutates repo.
Candidate path requires real Ollama in test.
Candidate path sets behavior_changed=true.
Adapter row is not present in A-side output.
```

## Commit message

```text
Exercise local adapter candidate dry run in capability runner
```

---

# P7 — Isolated solve mode through Path A

## Objective

Exercise isolated local solve loop through A-side runner while allowing mutation only inside isolated workspace and verifier only under explicit env gate.

## Dependencies

```text
P4 complete
P6 candidate dry-run path verified
isolated_local_solve_loop tests pass
```

## Required env gates

```bash
NEXUS_WITH_LOCAL_MODEL_ADAPTER=1
NEXUS_LOCAL_MODEL_CANDIDATE_ENABLE=1
NEXUS_LOCAL_SOLVE_ISOLATED_ENABLE=1
NEXUS_LOCAL_SOLVE_MUTATION_ALLOWED=1
NEXUS_LOCAL_SOLVE_VERIFIER_ALLOWED=1
NEXUS_LOCAL_GUARD_FAIL_CLOSED_ENABLE=1
```

## Forbidden

```text
No mutation of main repo.
No public claim.
No production readiness.
No behavior_changed=true in A-side benchmark row.
No LOCAL_ONLY_EXECUTED unless all hybrid_route.py requirements are met.
```

## Task steps

1. Use injected deterministic provider or tiny controlled local fixture first.

2. Ensure `executor_controls` passed to adapter include required fields:

```text
source_root
target_file
target_symbol
locked_search
verifier_command
work_dir
evidence_refs
```

3. If controls are missing, expected result:

```text
route_mode=local_only_blocked or fail_closed
fallback_block_reason includes missing_required_control
```

4. If controls are present, isolated solve may run inside temp/isolated workspace only.

5. Verify required evidence:

```text
selected_candidate_hash
applied_patch_hash
selected_candidate_hash_matches_applied
verifier_result
evidence_refs
```

6. Verify fail-closed behavior:

```text
missing hash -> blocked
hash mismatch -> blocked
verifier fail -> blocked/no claim
missing evidence_refs -> blocked
main repo mutated -> HOLD
```

## Verification commands

```bash
git status --short
python3 -m pytest tests/integration/test_abc_local_heal_full_isolated_solve_seam.py -q -rs
python3 -m pytest tests/integration/test_isolated_local_solve_loop_seam.py -q -rs
python3 -m pytest tests/unit/local_heal/test_isolated_local_solve_loop.py tests/unit/local_heal/test_local_guard_fail_closed.py -q -rs
git status --short
```

## Acceptance criteria

```text
Isolated workspace mutation only.
Main repo remains clean except intended test/docs changes.
Verifier result is recorded.
Hash evidence is recorded.
Fail-closed works when evidence incomplete.
public_claim_allowed=false.
production_ready=false.
behavior_changed=false in A-side route row.
```

## HOLD conditions

```text
Main repo source changes during isolated solve test.
Hash mismatch still passes.
Verifier fail still appears as success.
Adapter output becomes route truth.
Any public/production lock is loosened.
```

## Commit message

```text
Validate isolated local solve through capability runner seam
```

---

# P8 — Evidence bundle integration

## Objective

Add evidence bundle summary counts for `local_model_adapter` rows, separate from existing H5/H6 summaries.

## Dependencies

```text
P4 complete
P6/P7 row fields stable
```

## Target files

Likely:

```text
scripts/bench/capability_ab_runner.py
tests/benchmark/test_capability_ab_runner.py
```

## Forbidden

```text
Do not merge local_model_adapter summary into h5_route summary without explicit tested mapping.
Do not change public claim gate.
Do not set behavior_changed/public/production counts above 0 in safe phases.
```

## Task steps

1. Add summary builder for A-side evidence payload:

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

2. Summary rules:

```text
adapter_trace_count = rows with local_model_adapter present/enabled
adapter_invoked_count = adapter_invoked true
local_model_called_count = local_model_called true
candidate_isolated_count = candidate_output_isolated true in enabled rows
hash_match_count = selected_candidate_hash_matches_applied true
verifier_pass_count = verifier_result == pass
fail_closed_count = route_mode/fallback/blockers indicate fail-closed or blocked
behavior_changed_count = behavior_changed true
public_claim_allowed_count = public_claim_allowed true
production_ready_count = production_ready true
```

3. Add tests that verify:

```text
summary exists when rows contain local_model_adapter
summary counts disabled rows correctly
summary counts enabled rows correctly
public_claim_allowed_count remains 0
production_ready_count remains 0
behavior_changed_count remains 0 in safe cases
```

4. Ensure existing `hybrid_route_summary` tests still pass.

## Verification commands

```bash
python3 -m pytest tests/benchmark/test_capability_ab_runner.py -k "evidence_bundle or hybrid_route_summary or local_model_adapter" -q -rs
python3 -m pytest tests/contracts/test_hybrid_route_contract.py -q -rs
```

## Acceptance criteria

```text
Evidence bundle includes local_model_adapter_summary.
H5/H6 summaries remain unchanged unless deliberately tested.
All counts deterministic.
Safety counts remain zero in non-promoted phases.
Focused tests pass.
```

## HOLD conditions

```text
Summary hides public_claim_allowed=true.
Summary mixes h5_route and local_model_adapter ambiguously.
Existing hybrid_route_summary regresses.
```

## Commit message

```text
Summarize local model adapter evidence in capability bundle
```

---

# P9 — Promotion readiness report, not promotion

## Objective

Produce final readiness report stating whether Path B is safely wired through Path C into Path A. This is not production promotion and not public benchmark promotion.

## Dependencies

```text
P4 complete
P8 evidence bundle summary complete
P5/P6/P7 relevant smoke/dry-run/isolation checks completed or honestly blocked
```

## Target file

```text
docs/reports/local_model_armor_wiring_readiness_p9.md
```

## Forbidden

```text
Do not unlock public_claim_allowed.
Do not unlock production_ready.
Do not claim Qwen solved unless a separate benchmark/evidence gate proves it.
Do not claim local-only production execution.
Do not remove Path D diagnostic-only classification.
```

## Required questions to answer

1. Does Path A remain route truth?
2. Does Path A invoke adapter only behind env gates?
3. Are adapter outputs recorded in runner rows?
4. Are adapter outputs included in evidence bundle summaries?
5. Are public/production locks still enforced?
6. Is behavior_changed still false outside future promotion?
7. Is LocalHeal forbidden from independently setting route truth?
8. Are Path D diagnostics excluded from mainline claims?
9. Which P phases are complete, partial, blocked, or not started?
10. What exact evidence paths support the status?

## Required report structure

```text
1. Executive verdict
2. Four-path status
3. P0-P9 completion table
4. Evidence files and commands
5. Safety invariant table
6. Adapter invocation status
7. Evidence bundle summary status
8. Residual blockers
9. Not allowed claims
10. Next promotion plan required before any production/public unlock
```

## Verification commands

```bash
git status --short
rg -n "local_model_adapter|local_model_adapter_summary|LocalHealCapabilityAdapter|NEXUS_WITH_LOCAL_MODEL_ADAPTER" scripts/bench/capability_ab_runner.py tests/benchmark/test_capability_ab_runner.py docs/reports/local_model_armor_wiring_readiness_p9.md
python3 -m pytest tests/contracts/test_hybrid_route_contract.py -q -rs
python3 -m pytest tests/benchmark/test_capability_ab_runner.py -k "local_model_adapter or hybrid_route or evidence_bundle" -q -rs
```

## Acceptance criteria

```text
Readiness report exists.
Report does not claim production readiness.
Report does not claim public benchmark readiness.
Report clearly lists incomplete or blocked items.
Report includes commands and evidence paths.
Report confirms Path A remains route truth.
```

## Commit message

```text
Report local model armor wiring readiness
```

---

# Suggested execution order and batching

## Batch 1 — docs/tests only

```text
P0 + P1 + P2 + P3
```

Purpose:

```text
Freeze wrong path.
Archive audit.
Close contract test edge cases.
Define adapter row mapping.
```

Expected files:

```text
docs/reports/local_model_armor_path_freeze_p0.md
docs/reports/local_model_armor_four_path_audit_p1.md
docs/reports/local_model_adapter_runner_row_mapping_p3.md
tests/contracts/test_hybrid_route_contract.py  # only if missing edge cases
```

## Batch 2 — critical A-side seam

```text
P4
```

Purpose:

```text
Implement the missing capability_ab_runner.py -> LocalHealCapabilityAdapter seam.
```

Expected files:

```text
scripts/bench/capability_ab_runner.py
tests/benchmark/test_capability_ab_runner.py
```

## Batch 3 — guarded local execution validation

```text
P5 + P6 + P7
```

Purpose:

```text
Advisory smoke, candidate dry-run, isolated solve validation.
```

Expected files depend on whether code changes are needed or tests already cover behavior.

## Batch 4 — evidence and readiness

```text
P8 + P9
```

Purpose:

```text
Evidence bundle summary and readiness report.
```

Expected files:

```text
scripts/bench/capability_ab_runner.py
tests/benchmark/test_capability_ab_runner.py
docs/reports/local_model_armor_wiring_readiness_p9.md
```

---

# Universal Codex report template per P

Every P-phase response must include:

```text
1. Phase:
2. current HEAD:
3. git status --short before:
4. Files inspected:
5. Files changed:
6. Commands run:
7. Key evidence:
8. Safety locks checked:
   - route_truth_source:
   - adapter_output_is_route_truth:
   - public_claim_allowed:
   - production_ready:
   - behavior_changed:
9. Test results:
10. Residual blockers:
11. git status --short after:
12. COMMIT_READY / HOLD:
13. Proposed commit message:
```
