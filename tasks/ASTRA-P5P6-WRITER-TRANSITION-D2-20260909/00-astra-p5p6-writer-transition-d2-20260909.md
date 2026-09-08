# Task Card: astra-p5p6-writer-transition-d2-20260909

artifact_authority: current
task_id: `astra-p5p6-writer-transition-d2-20260909`
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

Repair only the existing eight subprocess replan lifecycle fixtures required by Card D. All eight fail identically on the exact D base before any Python fixture child dispatch because current Workforce Admission inputs are absent. Preserve real CapabilityPlanner, Workforce Admission, Runtime invocation authority, physical subprocess execution, strict receipt lineage, budget/tamper stops and all eight lifecycle assertions. Supply an actual policy-admitted fixture worker binding and required controls; generated Python-only executable must validate the exact declared exec/model protocol, ledger PID/stdin/argv and fixture-only identity. Add missing-binding denial proving zero child dispatch. No admission/planner/policy mocks, forced ALLOW, disabling controls, production code, real model/provider/API-key/SDK/Agy/Gemini/Codex native call or network operation. The only executed child is generated fixture Python. Follow reviewed plan SHA256 f7b0c4bda7bdd3eba6aa7490e9432c027e3a90e9240db53ba5eb9d7f5e6279eb. This is a test-only repair under the original P0-P8 goal, not a claim that D already passed its full verifier. No main/push/merge/live/release/cleanup. AUTO_CHAIN=false. Worker may exact-scoped commit only after independent controller review.

## Allowed files

- `tests/integration/test_unified_runtime_replan_subprocess.py`

## Verification commands

```bash
python3 -B -m pytest -q tests/integration/test_unified_runtime_replan_subprocess.py tests/services/test_loaded_runtime_owner_chain.py tests/integration/test_canonical_runtime_writer_activation.py tests/services/test_unified_runtime.py
git diff --check
```

## Exit criteria

Owner review of the exact scoped commit.

## Block classification

Unverifiable or out-of-scope mutation is a HARD_BLOCK.
