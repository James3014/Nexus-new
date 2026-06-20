# Fixture Manifest — nexus-receipt-core v0.1

## Valid Receipts

| Fixture | Expected Result | Checks Passed |
|---------|----------------|---------------|
| `clean_receipt.json` | PASS | hashmatch=true, schemamatch=true, evidencecomplete=true |
| `unicode_normalization.json` | PASS | NFC/NFD canonicalization handled |
| `numeric_normalization.json` | PASS | int/float canonicalization handled |
| `large_nested_object.json` | PASS | 1000-key object, deterministic ordering |
| `extra_fields.json` | PASS | Unknown fields ignored gracefully |

## Invalid Receipts

| Fixture | Expected Result | Error Code |
|---------|----------------|------------|
| `tampered_receipt.json` | FAIL | `hash_mismatch` |
| `missing_claimed_hash.json` | FAIL | `hash_not_checked` |
| `edge_invalid_utf8.json` | FAIL | `parse_error` |
| `empty_object.json` | FAIL | `schema_mismatch` |
| `missing_required_field.json` | FAIL | `schema_mismatch` |
| `incomplete_evidence.json` | FAIL | `evidence_incomplete` |
| `malformed_json.json` | FAIL | `parse_error` |

## Edge Cases

| Fixture | Expected Result | Notes |
|---------|----------------|-------|
| `unicode_edge_cases.json` | PASS | Various Unicode codepoints |

Total fixtures: 12
Pass (valid): 5
Fail (invalid): 6
Edge case: 1
