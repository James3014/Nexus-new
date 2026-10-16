# P2-EF Target File and Committee Bridge

## Status

`P2_EF_TARGET_FILE_AND_COMMITTEE_BRIDGE_PASS`

## Summary

Two small changes to close out P2: target_file presence check in claim gate + committee path hash_match bridge to route_context.

## Files Changed

| File | Action |
|------|--------|
| `nexus/services/local_heal/claim_delivery_gate.py` | Modified — added `candidate_target_file` check + context field |
| `nexus/services/local_heal/local_model_executor.py` | Modified — added route_context store in committee + pipeline paths |
| `tests/unit/local_heal/test_claim_delivery_gate.py` | Modified — added 3 P2-E tests |

## Commands Run

```bash
python3 -m py_compile nexus/services/local_heal/claim_delivery_gate.py nexus/services/local_heal/local_model_executor.py
pytest tests/unit/local_heal/test_claim_delivery_gate.py -v -q
```

## Test Counts

- `test_claim_delivery_gate.py`: 10/10 passed

## P2-E: Target File Presence Check

### In `validate()` (line ~35)

```python
candidate_target_file = str(payload.get("candidate_target_file", "") or "")
source_hash_present = bool(str(payload.get("source_hash", "") or "").strip())
if source_hash_present and not candidate_target_file.strip():
    reasons.append("missing_candidate_target_file")
```

### In `validate_context_claim_delivery()` (line ~82)

```python
"candidate_target_file": str(getattr(op, "candidate_target_file", "") or ""),
```

## P2-F: Committee Path Bridge

### Committee path (line ~1391)

```python
if isinstance(request.route_context, dict):
    request.route_context["candidate_hash_matches_applied"] = hash_match
```

### Pipeline path (line ~2400)

```python
if isinstance(request.route_context, dict):
    request.route_context["candidate_hash_matches_applied"] = hash_match
```

## Explicit Statements

- P2-E is presence-only, no mismatch comparison
- Committee path now stores hash_match on route_context
- P2 is complete
- `public_claim_allowed=false`, `production_ready=false`
- Nothing is claimed about solve rate
