# Result Schema — `nexus-receipt-core`

> **Version**: v1  
> **Status**: Frozen (minimal public contract)  
> **Date**: 2026-06-16

## Overview

This document defines the result schema emitted by the `nexus-receipt-core` verifier.  
It is the **only** public interface contract for verification results.

## Fields

| Field | Type | Description |
|-------|------|-------------|
| `hashmatch` | `Option<bool>` | Hash verification result. `Some(true)` = passed, `Some(false)` = failed, `None` = skipped (via `--skip-hash`). |
| `schemamatch` | `bool` | Whether the receipt contains all required fields. |
| `evidencecomplete` | `bool` | Whether all evidence entries contain required sub-fields. |
| `claimabilityconfirmed` | `bool` | Final verdict: `true` only when **all** checks pass. |
| `errorcode` | `Option<String>` | First failing check. One of: "hash_mismatch", "hash_not_checked", "schema_mismatch", "evidence_incomplete", "parse_error". `None` if valid. |

## Rules

### Fail-Closed

`claimabilityconfirmed` is `true` **if and only if**:

1. `hashmatch == Some(true)`
2. `schemamatch == true`
3. `evidencecomplete == true`

Any deviation → `claimabilityconfirmed = false`.

### Error Code Priority

When multiple checks fail, `errorcode` is set to the **first** failing check in order:

1. `parse_error` — JSON cannot be parsed
2. `hash_mismatch` — computed hash ≠ claimed hash
3. `hash_not_checked` — hash was skipped (`--skip-hash`) or missing
4. `schema_mismatch` — missing required fields
5. `evidence_incomplete` — evidence entries missing required sub-fields

### Hash Not Checked

When `hashmatch == None`, the verifier **must not** set `claimabilityconfirmed = true`.  
Instead, `errorcode` is set to `"hash_not_checked"` and the result is treated as invalid.

This prevents the semantic bug where a receipt without hash verification could appear to pass.

## Example Outputs

### Valid Receipt

```json
{
  "hashmatch": true,
  "schemamatch": true,
  "evidencecomplete": true,
  "claimabilityconfirmed": true,
  "errorcode": null
}
```

### Tampered Receipt

```json
{
  "hashmatch": false,
  "schemamatch": true,
  "evidencecomplete": true,
  "claimabilityconfirmed": false,
  "errorcode": "hash_mismatch"
}
```

### Skipped Hash Check

```json
{
  "hashmatch": null,
  "schemamatch": true,
  "evidencecomplete": true,
  "claimabilityconfirmed": false,
  "errorcode": "hash_not_checked"
}
```

### Parse Error

```json
{
  "hashmatch": null,
  "schemamatch": false,
  "evidencecomplete": false,
  "claimabilityconfirmed": false,
  "errorcode": "parse_error"
}
```

## Stability

This schema is **frozen** for v0.1. Future versions may:

- Add new fields (never remove or rename existing ones)
- Add new error codes (never remove existing ones)
- Introduce version negotiation

Breaking changes require a new major version.
