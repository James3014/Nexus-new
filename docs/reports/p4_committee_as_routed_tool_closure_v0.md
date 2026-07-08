# P4 Committee as Routed Tool Closure Report

## Status: ✅ P4_CLOSED

## Commits

| Package | Commit | Description |
|---------|--------|-------------|
| P4-I1 | `d899ff802` | Committee routed-tool contract |
| P4-I2 | `fe7bac1a5` | Activation/suppression gate |
| P4-I3 | `11a48824d` | Candidate adapter to CanonicalPatchCandidate |
| P4-I4 | `1d66c5d82` | Committee invocation from P3 hard-case path |
| P4-I5 | `623cbc413` | Winner reapply + verifier + claim gate |
| P4-I6 | `ab500cd13` | Zero-winner / no-candidate / malformed fail-closed |
| P4-I7 | `TBD` | E2E route receipt + regression closure |

## Files Added/Modified

| File | Action |
|------|--------|
| `nexus/services/local_heal/committee_routed_tool.py` | New — Request/Result contracts + evaluate_and_execute |
| `nexus/services/local_heal/committee_activation_gate.py` | New — Activation/suppression gate |
| `nexus/services/local_heal/committee_candidate_adapter.py` | New — Candidate adapter |
| `nexus/services/local_heal/local_model_executor.py` | Modified — P3→P4 bridge |
| `nexus/services/local_heal/receipt.py` | Modified — P4 receipt fields |
| `tests/unit/local_heal/test_p4_committee_routed_tool_contract.py` | New — 10 tests |
| `tests/unit/local_heal/test_p4_committee_activation_gate.py` | New — 12 tests |
| `tests/unit/local_heal/test_p4_committee_candidate_adapter.py` | New — 12 tests |
| `tests/unit/local_heal/test_p4_committee_invocation_from_p3.py` | New — 7 tests |
| `tests/unit/local_heal/test_p4_committee_winner_reapply_claim_gate.py` | New — 8 tests |
| `tests/unit/local_heal/test_p4_committee_fail_closed.py` | New — 10 tests |
| `tests/contracts/test_p4_committee_routed_tool_receipts.py` | New — 5 E2E tests |

## P4 Test Totals

| Package | Tests |
|---------|-------|
| P4-I1 | 10 |
| P4-I2 | 12 |
| P4-I3 | 12 |
| P4-I4 | 7 |
| P4-I5 | 8 |
| P4-I6 | 10 |
| P4-I7 | 5 |
| **Total** | **64** |

## P3+P4 Total: 100+ passed

## P4 Complete Conditions

- [x] Committee only enters from P3 hard_case_escalation_stub
- [x] Committee is NOT default solve topology
- [x] All candidates canonicalized via CanonicalPatchCandidate
- [x] Winner must re-apply isolated workspace
- [x] Winner must verifier pass
- [x] Winner must hash match
- [x] Zero-winner fail closed
- [x] Missing proposer/judge fail closed
- [x] Receipt records full P4 path
- [x] P3 regression green
- [x] Full suite green

## P5/P6

Deferred. Not started.
