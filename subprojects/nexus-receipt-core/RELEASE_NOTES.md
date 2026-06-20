# Release Notes — v0.1

> **Date**: 2026-06-16  
> **Status**: Release Candidate

## What's Included

### Core Functionality

- **Receipt Verification**: Rust-based verifier that checks AI execution receipts for integrity, schema compliance, and evidence completeness.
- **Fail-Closed Design**: `claimabilityconfirmed` is `true` only when ALL checks pass (hash + schema + evidence). Any deviation → `false`.
- **Canonical JSON**: Deterministic key sorting + canonicalization for reproducible SHA-256 hashing.
- **CLI Interface**: `cargo run -- verify <file>` (full verification) and `--skip-hash` (debug mode).

### Result Schema (Frozen Contract)

| Field | Type | Description |
|-------|------|-------------|
| `hashmatch` | `Option<bool>` | `Some(true)` = passed, `Some(false)` = failed, `None` = skipped |
| `schemamatch` | `bool` | Receipt contains all required fields |
| `evidencecomplete` | `bool` | All evidence entries have required sub-fields |
| `claimabilityconfirmed` | `bool` | Final verdict: true only when ALL checks pass |
| `errorcode` | `Option<String>` | First failing check, or `null` if valid |

### Error Code Priority

1. `parse_error` — JSON cannot be parsed
2. `hash_mismatch` — computed hash ≠ claimed hash
3. `hash_not_checked` — hash was skipped (`--skip-hash`) or missing
4. `schema_mismatch` — missing required fields
5. `evidence_incomplete` — evidence entries missing required sub-fields

### Test Coverage

**12 integration tests** covering:

| Fixture | Scenario | Expected |
|---------|----------|----------|
| `clean_receipt` | Valid receipt with correct hash | schemamatch=true, evidencecomplete=true, claimabilityconfirmed=true |
| `tampered_receipt` | Modified payload | hash_mismatch |
| `missing_evidence` | Evidence entries missing required fields | hash_not_checked (priority blocks evidence check) |
| `schema_mismatch` | Missing required fields | hash_not_checked (priority blocks schema check) |
| `edge_null_values` | All values are null | Parses correctly, hash_not_checked |
| `edge_unicode` | Multi-language strings (zh, ja, ru, ar) | schemamatch=true |
| `edge_nested_objects` | 10-level deep nested objects | schemamatch=true |
| `edge_empty_arrays` | Empty arrays in fields | evidence_incomplete |
| `edge_invalid_utf8` | Raw invalid UTF-8 bytes (0xFF 0xFE) | parse_error |
| `edge_numeric_normalization` | Int, float, scientific notation, negative numbers | schemamatch=true |
| `edge_large_nested` | Large deeply nested structures | schemamatch=true, evidencecomplete=true |
| `edge_parse_error` | Malformed JSON (unquoted keys) | parse_error |

### Rust ↔ Python Canonicalization Parity

All 12 fixtures produce identical canonical JSON output from both Rust and Python implementations. Verified via `generate_mismatch_report.py`.

## CLI Behavior

```bash
# Full verification (default)
cargo run -- verify ./receipt.json

# Skip hash check (debug mode)
cargo run -- verify ./receipt.json --skip-hash
```

### `--skip-hash` Behavior

- Sets `hashmatch` to `null`
- Sets `errorcode` to `"hash_not_checked"`
- Does NOT set `claimabilityconfirmed` to `true`
- Still validates schema and evidence completeness

## Exclusions

This release does NOT include:

- Router or capability planner (Python scope, out of band)
- FlowMachine integration
- Public/internal schema separation
- Version negotiation protocol
- Any SDK bindings beyond CLI

## Known Limitations

- `parse_error` handling for invalid UTF-8 requires `include_bytes!` workaround in tests (cannot use `include_str!` for non-UTF-8 fixtures)
- No streaming/large-file support (loads entire file into memory)

## Directory Structure

```
nexus/subprojects/nexus-receipt-core/
├── rust/receipt_verifier/      # Rust verifier crate
│   ├── src/lib.rs              # Core verification logic
│   ├── src/main.rs             # CLI entry point
│   └── tests/integration.rs    # Integration tests
├── schemas/python/             # Python canonicalization + fixtures
│   ├── canonicalize.py
│   └── fixtures/               # 12 test fixtures
├── schemas/generate_mismatch_report.py  # Rust↔Python parity checker
├── RESULT_SCHEMA.md            # v0.1 frozen result contract
├── README.md                   # User-facing documentation
├── INSTALL.md                  # Installation guide
└── RELEASE_NOTES.md            # This file
```
