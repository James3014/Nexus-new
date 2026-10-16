# U3-1 Candidate Identity Contract Report

**日期**: 2026-06-22
**狀態**: `U3_1_CANDIDATE_IDENTITY_CONTRACT_PASS`
**Commit**: `bfa5672e local-heal: add committee candidate identity contract`
**治理**: `public_claim_allowed=false`, `production_ready=false`, `internal_only=true`

---

## Scope

U3-1 only. Introduce stable candidate_id contract and judge selection mapping by candidate_id.

## Files Changed

| File | Change |
|------|--------|
| `nexus/services/local_heal/committee_orchestrator.py` | +candidate_id to snapshot/proposals, judge mapping by candidate_id, legacy fallback, new fail-closed path |
| `nexus/services/local_heal/receipt.py` | +committee trace extraction, +committee field in receipt |
| `tests/unit/local_heal/test_committee_route_trace.py` | +5 tests (2 existing updated, 3 new) |

## Candidate Schema (implemented)

```json
{
  "candidate_id": "C_12481#candidate-1",
  "candidate_key": "C_12481#proposer-1",
  "model": "qwen2.5-coder:7b-instruct",
  "role": "primary",
  "attempt": 1,
  "raw_label": "r:0,d:0,p:3,c:0",
  "patch_sha256": "...",
  "patch_length": 123,
  "selected": false,
  "applied": false
}
```

## Judge Selection Mapping

```text
judge_selection = {
  "selected_candidate_id": "C_12481#candidate-2",
  "candidate_id_mapping_mode": "legacy_winner_id_prefix",
  ...
}
```

Mapping modes:
- `candidate_id` — receipt.winner_id matches proposal's candidate_id directly
- `legacy_winner_id_prefix` — fallback: match by winner_id prefix against proposal metadata
- `missing` — no mapping found → fail-closed

## Compile & Test

```
python3 -m py_compile nexus/services/local_heal/committee_orchestrator.py nexus/services/local_heal/receipt.py tests/unit/local_heal/test_committee_route_trace.py
→ OK

pytest tests/unit/local_heal/test_committee_route_trace.py -v
→ 5 passed

pytest tests/unit/local_heal/test_native_route_adapter.py tests/unit/local_heal/test_role_contract.py -q
→ 21 passed
```

## Tests

| Test | What it verifies |
|------|-----------------|
| `test_committee_orchestrator_records_two_candidate_trace` | candidate_id, selected_candidate_id, candidate_id_mapping_mode, candidate_key legacy |
| `test_committee_trace_is_persisted_into_repair_receipt` | committee trace in receipt has candidate_id fields |
| `test_committee_route_fails_closed_when_selected_candidate_is_not_applied` | non-last candidate fail-closed still works, candidate_id resolved |
| `test_committee_route_fails_closed_when_candidate_mapping_missing` | unrecognized winner_id → mapping_mode="missing", fail-closed |
| `test_committee_candidate_ids_are_deterministic` | candidate_id = `{instance_id}#candidate-{N}`, deterministic |

## What U3-1 Does NOT Do

```text
No candidate isolation store (U3-2)
No selected-candidate re-apply (U3-3)
No hash comparison (not yet)
No H5 / local-first / local-only
No production_ready / public_claim_allowed
```
