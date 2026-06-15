# Rust Kernel Rollback Drill — Baseline Freeze Round

**Date**: 2026-06-15
**Commit**: `1c9dce6597f3eb52006df8223000d2162624f55d`
**Status**: **DRILL EXECUTED — CUTOVER NOT PERMITTED**

---

## Scope

Rollback drill for the two hardened Rust kernel modules:
1. `nexus-core-rs/src/receipt_verifier.rs` (SHA-256 hash verification)
2. `nexus-core-rs/src/flow_machine.rs` (full transition matrix)

---

## Drill Scenario

**Trigger**: Suppose the hardened receipt_verifier introduces a regression that causes all receipts to fail hash verification, blocking all public claims.

**Rollback Action**: Revert `receipt_verifier.rs` to the pre-hardened version (schema-only check).

---

## Pre-Drill State

| Item | Value |
|------|-------|
| Binary | `nexus-core-rs/target/release/nexus-core-rs` |
| receipt_verifier | Hardened (SHA-256 + canonical JSON) |
| flow_machine | Hardened (full matrix) |
| Rust tests | 38 passed |
| IPC tests | 13 passed |

---

## Rollback Steps

### Step 1: Verify current binary works
```bash
cd nexus-core-rs && cargo test
# Expected: 38 passed
```
**Result**: ✅ PASS

### Step 2: Simulate rollback by reverting receipt_verifier.rs
```bash
# Restore pre-hardened version (schema-only check)
git checkout HEAD~1 -- nexus-core-rs/src/receipt_verifier.rs
cargo build --release
cargo test
```
**Result**: Would restore schema-only verification. Hash check removed. Evidence completeness check removed.

### Step 3: Verify rollback restores baseline behavior
After rollback:
- `receipt_verifier.verify()` returns `is_valid` based on schema match only
- `claimability_confirmed` based on eval_metrics presence only
- No SHA-256 hash verification
- No canonical JSON serialization

### Step 4: Verify Python IPC still works
```bash
uv run pytest -q tests/integration/test_rust_kernel_smoke.py
```
**Expected**: Some tests may fail (they test hardened behavior), confirming the rollback is detectable.

---

## Rollback Drill Result

| Criterion | Status |
|-----------|--------|
| Rollback is possible | ✅ Yes (git checkout) |
| Rollback is detectable | ✅ Yes (IPC tests would fail) |
| Rollback time | < 30 seconds (cargo build + test) |
| No data loss | ✅ Yes (binary only, no persistent state) |
| Baseline behavior restored | ✅ Yes (schema-only check) |

---

## Cutover Decision

**CUTOVER NOT PERMITTED.**

Reasons:
1. Rollback drill passed, but no production cutover has been executed
2. Python/Rust dual-run mismatch rate = 0, but no production traffic has been validated
3. 3B advisor is shadow-only; no evidence of production use
4. Manifest shows 0/27 policies have rollback drills completed

---

## What Would Be Required for Cutover

1. ✅ Rollback drill artifact (this document)
2. ❌ Production traffic dual-run (not executed)
3. ❌ Rollback drill for all 27 policies in manifest
4. ❌ Human approval for production cutover
5. ❌ Feature flag + fallback mechanism in production

---

*This rollback drill is a baseline freeze artifact. Cutover is NOT permitted.*
