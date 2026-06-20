# StructuredPacket Retry Wiring Packet — Phase 3

## Summary

Wired StructuredPacket into retry prompting for all major failure types, not just LOGIC_REGRESSION.

## Changes

1. **orchestrator.py**: StructuredPacket now created for LOGIC_REGRESSION, SEARCH_MISMATCH, SYNTAX_ERROR
2. **corrector.py**: SYNTAX_ERROR and SEARCH_MISMATCH retry paths now use `structured_packet.to_prompt_text()`
3. **receipt.py**: Added `structured_packet_used` field for observability

## Files Modified

- `nexus/services/local_heal/orchestrator.py`
- `nexus/services/local_heal/corrector.py`
- `nexus/services/local_heal/receipt.py`

## Test Results

- `test_evidence_compactor.py`: 9 passed
- `test_receipt_v1_schema.py`: 19 passed
