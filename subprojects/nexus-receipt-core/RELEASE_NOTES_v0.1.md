# Release Notes — `nexus-receipt-core` v0.1

> **Release Date**: 2026-06-16
> **Status**: Release Candidate (Frozen Contract)

## What This Is

`nexus-receipt-core` v0.1 is a deterministic receipt verifier for AI execution logs. It checks:
1. **Hash integrity** — whether the receipt content matches its claimed hash
2. **Schema validity** — whether all required fields are present
3. **Evidence completeness** — whether evidence entries have required sub-fields
4. **Claimability** — final verdict: pass only when ALL checks pass

## CLI Usage

```bash
# Full verification (default)
cargo run -- verify ./receipt.json

# Skip hash check (schema + evidence only)
cargo run -- verify ./receipt.json --skip-hash
```

## Result Schema (v0.1 Frozen)

The verifier emits a JSON result with these fields:

| Field | Type | Description |
|-------|------|-------------|
| `hashmatch` | `Option<bool>` | `Some(true)` = passed, `Some(false)` = failed, `None` = skipped |
| `schemamatch` | `bool` | Required fields present |
| `evidencecomplete` | `bool` | Evidence entries complete |
| `claimabilityconfirmed` | `bool` | Final verdict (true only if ALL checks pass) |
| `errorcode` | `Option<String>` | First failing check, or `null` if valid |

### Error Code Priority

1. `parse_error` — JSON cannot be parsed
2. `hash_mismatch` — computed hash ≠ claimed hash
3. `hash_not_checked` — hash skipped (`--skip-hash`) or missing
4. `schema_mismatch` — missing required fields
5. `evidence_incomplete` — evidence entries incomplete

### Fail-Closed Rule

`claimabilityconfirmed` is `true` **if and only if**:
- `hashmatch == Some(true)`
- `schemamatch == true`
- `evidencecomplete == true`

Any deviation → `false`.

### Hash Not Checked

When `hashmatch == None`, the verifier **must not** set `claimabilityconfirmed = true`. Instead, `errorcode` is set to `"hash_not_checked"`.

## Test Coverage

| Category | Count | Status |
|----------|-------|--------|
| Unit Tests | 7/7 | ✅ Pass |
| Integration Tests | 12/12 | ✅ Pass |
| Python-Rust Parity | 0 mismatches | ✅ Verified |

### Fixture Categories Tested

- ✅ Valid receipt (clean)
- ✅ Tampered receipt (hash mismatch)
- ✅ Missing claimed hash
- ✅ Invalid UTF-8 bytes
- ✅ Unicode normalization (NFC/NFD)
- ✅ Numeric normalization (int vs float)
- ✅ Large nested objects (1000 keys)
- ✅ Empty object
- ✅ Missing required fields
- ✅ Incomplete evidence entries
- ✅ Malformed JSON
- ✅ Extra unknown fields (ignored)

## Known Limits

- **Not a full Nexus release** — this is a core verification primitive only
- **No network calls** — operates on local files only
- **No policy decisions** — does not route, plan, or make capability judgments
- **Schema v0.1 frozen** — future versions may add fields but will not remove or rename existing ones

## Dependencies

- `serde` — serialization
- `serde_json` — JSON parsing
- `sha2` — SHA-256 hashing
- `hex` — hex encoding

All dependencies are public crates with no internal Nexus coupling.

## What's NOT Included

This project does **not** handle:
- Task routing (`autonomicrouter.py`)
- Capability planning
- Public claim gate
- Model selection or training data export
- Private benchmark data

These remain internal to Nexus.

## Next Steps (v0.2+)

- [ ] FlowMachine transition validation
- [ ] Matcher parity (regex)
- [ ] S2T/3B data contract
- [ ] Shadow evaluation metrics

## Verification Evidence

All test transcripts and parity reports are stored in `verification-evidence/`.
