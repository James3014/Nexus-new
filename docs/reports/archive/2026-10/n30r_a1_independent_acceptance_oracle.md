# N30R-A1 Independent Full Armor Acceptance Oracle

## 1. Worktree and Baseline

| Field | Value |
|-------|-------|
| path | `/Users/jameschen/Workspace/nexus-n30r-v1-acceptance` |
| branch | `feat/n30r-v1-independent-acceptance` |
| baseline | `3bce7105d bench: seal W1C2 runtime projection evidence` |
| new worktree created | yes (from baseline) |
| Agent B worktree accessed | false |
| production files modified | false |

## 2. Non-overlap Proof with Agent B

Agent A exclusively created:

```
scripts/bench/n30r_v1_acceptance_oracle.py
tests/bench/test_n30r_v1_acceptance_oracle.py
docs/bench/n30r/a1_task_evidence_n30r_smoke_semantic.json
docs/bench/n30r/a1_acceptance_contract_v1.json
docs/reports/n30r_a1_independent_acceptance_oracle.md
```

Agent A did NOT modify:

```
nexus/services/local_heal/*
scripts/bench/n30r_real_core_bridge.py
scripts/bench/n30r_w1c_projection_trace.py
scripts/bench/n30r_v1_full_armor_trace.py
```

Agent B worktree at `/Users/jameschen/Workspace/nexus-n30r-real-core` was not read or modified.

## 3. Existing Contract Reuse

A0 discovered and reused:

- `_REQUIRED_FIELDS` from `local_model_armor_receipt_gate.py` (line 11-24)
- `N30RAttemptReceipt` fields from `n30r_contracts.py` (line 82-131)
- `CapabilityExecutionResult` from `local_model_capability_context.py` (line 31-57)
- `verify_hash_chain()` from `output_understanding.py` (line 59-67) — confirmed it only checks non-empty
- `validate_capability_causality()` from `local_model_armor_receipt_gate.py` (line 76-137)
- Smoke manifest schema from `docs/bench/n30r/smoke_manifest.json`

No second schema invented. All field names match production source.

## 4. n30r_smoke_semantic Evidence Pack

| Field | Value |
|-------|-------|
| task_id | `n30r_smoke_semantic` |
| source | `tests/fixtures/n30r/smoke/semantic_task.py` |
| source hash | `810f8dc57fa3502b3f19aa0252769779186957132067876b76cc3f6b8ad520ae` |
| target_symbol | `is_even` |
| locked_search | `return n % 2 == 1` |
| locked_search occurrence | 1 |
| source_anchor_hash | `fc407e42db2a5682206db18b200ac4647a7799f2d61b8a3a2b98357ae9934281` |
| verifier | `python3 -c "from f import is_even; assert is_even(4) is True; assert is_even(3) is False"` |
| pre_fix expected | failure (exit code 1) |
| evidence_refs | 0 (no answer included) |
| golden patch included | NO |

## 5. Acceptance Gate Definitions

| Gate | Key Checks |
|------|-----------|
| P Gate | planner snapshot hash valid, projection hash valid, unknown=0, dependency_errors=0 |
| D Gate | target_file exists, source hash recomputable, locked_search in source (count=1), evidence refs resolvable |
| X Gate | provider called, response received, prompt contains task/file/symbol/search, candidate isolated, apply successful |
| R Gate | verifier exit code exists, workspace consistent, retry without feedback rejected, timeout not inferred from wall_time |
| A Gate | shadow outcome, promotion_eligible=false, global_learning_mutated=false, capability contributions evidence-backed |
| C Gate | final receipt exists, all hashes valid SHA-256, no placeholders, no snapshot-as-receipt, hash chain complete |
| Live Gate | accepts VERIFIED_SOLVE/VERIFIED_FAIL, rejects CONTRACT_INVALID, requires provider called for solved |

## 6. Hash Recomputation Policy

The oracle independently recomputes:

- `source_sha256` — reads file from disk, computes SHA-256
- `locked_search` — verifies exact substring in source, counts occurrences
- `source_anchor_hash` — matches production logic (locked_search hash)
- `evidence artifact hashes` — reads referenced files, recomputes
- `prompt hash` — validates format (not content, since prompt is reconstructed)

The oracle does NOT trust `verify_hash_chain()` which only checks non-empty (confirmed at `output_understanding.py:59-67`).

## 7. Negative Tamper Cases

| Tamper | Result |
|--------|--------|
| Missing target_symbol | REJECTED |
| locked_search not in source | REJECTED |
| locked_search count != 1 | REJECTED |
| source hash mismatch | REJECTED |
| Unresolvable evidence ref | REJECTED |
| Evidence hash mismatch | REJECTED |
| Prompt missing locked_search | REJECTED |
| Response flag without output | REJECTED |
| Empty candidate hash | REJECTED |
| False candidate isolation | REJECTED |
| Workspace mismatch | REJECTED |
| Retry without verifier feedback | REJECTED |
| Global learning mutation | REJECTED |
| promotion_eligible=true | REJECTED |
| Placeholder hash | REJECTED |
| Snapshot hash as receipt | REJECTED |
| Hardcoded gate booleans | recomputed, ignored |

## 8. Test Results

```
pytest tests/bench/test_n30r_v1_acceptance_oracle.py -q
```

35 behavioral tests covering:

- Task evidence: source hash, target symbol, locked search, verifier, refs
- D Gate: missing symbol, search absent, search count mismatch, hash mismatch, unresolvable ref, evidence hash mismatch
- X Gate: prompt without search, response without output, empty candidate, false isolation
- R Gate: workspace mismatch, retry without feedback, timeout inference
- A Gate: global mutation, promotion eligible, capability without evidence
- C Gate: placeholder hash, incomplete chain, snapshot as receipt, hardcoded booleans
- Live Gate: verified solve, contract invalid, solved without provider
- Hash utilities: valid/invalid SHA-256, placeholder detection, determinism

## 9. Agent B Artifact Validation

Agent B trace not yet produced. Status:

```
ORACLE_READY_PRODUCER_ARTIFACT_PENDING
```

Oracle is ready to validate Agent B trace when available:

```bash
python scripts/bench/n30r_v1_acceptance_oracle.py \
    --trace <agent_b_trace.json> \
    --repo-root /Users/jameschen/Workspace/nexus-n30r-v1-acceptance \
    --contract docs/bench/n30r/a1_acceptance_contract_v1.json \
    --json-out docs/bench/n30r/a1_independent_validation_<run_id>.json
```

## 10. Merge Instructions

```bash
cd /Users/jameschen/Workspace/nexus-n30r-v1-acceptance
git add \
    scripts/bench/n30r_v1_acceptance_oracle.py \
    tests/bench/test_n30r_v1_acceptance_oracle.py \
    docs/bench/n30r/a1_task_evidence_n30r_smoke_semantic.json \
    docs/bench/n30r/a1_acceptance_contract_v1.json \
    docs/reports/n30r_a1_independent_acceptance_oracle.md
git commit -m "test(bench): add independent N30R armor acceptance oracle"
```

Expected conflicts: none (only new files).

## 11. Claim Boundary

| Claim | Value |
|-------|-------|
| Production path implemented by A | false |
| Effectiveness measured | false |
| Production ready | false |
| Public claim allowed | false |
| No live model executed | true |
| Oracle correctness tested | true |
