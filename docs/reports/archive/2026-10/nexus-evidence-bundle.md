# Evidence Bundle — Baseline Freeze Round

**Generated**: 2026-06-15
**Commit**: `1c9dce6597f3eb52006df8223000d2162624f55d`
**Git describe**: `spec-v1.100-261-g8e008abc`

---

## 1. Git Worktree Status

```
Current commit: 1c9dce6597f3eb52006df8223000d2162624f55d
Modified files (this session):
  - nexus-core-rs/Cargo.toml (added sha2, hex deps)
  - nexus-core-rs/Cargo.lock
  - nexus-core-rs/src/receipt_verifier.rs (hardened)
  - nexus-core-rs/src/flow_machine.rs (full matrix)
  - tests/integration/test_rust_kernel_smoke.py (updated IPC tests)
  - tests/integration/test_rust_wave3_cutover.py (dual-run tests)
  - docs/reports/policy-baseline-manifest.v1.json (new)
  - docs/reports/policy-baseline-manifest.v1.md (new)
  - docs/reports/s2t-3b-shadow-advisor-evaluation.md (new)
```

---

## 2. Cargo Test Results

```
test result: ok. 38 passed; 0 failed; 0 ignored; 0 measured; 0 filtered out
```

- receipt_verifier: 11 tests (canonical JSON, SHA-256 hash, tamper-proof, schema match, evidence completeness)
- flow_machine: 27 tests (full 14×14 matrix, terminal state, fail-closed, legal transition counts)

---

## 3. Python IPC Test Results

```
tests/integration/test_rust_kernel_smoke.py ......... [69%]
tests/integration/test_rust_wave3_cutover.py ....     [100%]
============================== 13 passed ==============================
```

- test_rust_kernel_receipt_verification: 5 scenarios (valid, tampered hash, tampered payload, schema mismatch, missing metrics)
- test_dual_run_all_transitions: 196 transitions, mismatch rate = 0
- test_dual_run_legal_counts_match: per-state count verification
- test_fail_closed_on_unknown_transition: fail-closed verification

---

## 4. Mismatch Ledger Summary

```
Dual-run mismatches: 0
Total transitions tested: 196 (14 states × 14 states)
Mismatch rate: 0.0%
```

No `rust_mismatch_ledger.jsonl` generated (no mismatches).

---

## 5. Shadow Report with Held-Out Split

| Metric | Value |
|--------|-------|
| Total canary rows | 127 |
| Selector override rate | 11.0% (14/127) |
| Override verified rate | 100% (14/14 both_valid) |
| Trust mismatch rate | 0% |
| Abstain rate | 0% |
| Public claim precision | No degradation |

**Held-out tasks**: N/A (baseline freeze — no new training data added)

---

## 6. Public Claim Gate Result

```
Public claims permitted: 0
Public claims blocked: 0 (no claims attempted)
Rust receipt_verifier: ACTIVE (11 unit tests + 5 IPC tests)
Hallucination guard: ACTIVE
Capability receipt policy: ACTIVE
3B advisor: SHADOW-ONLY (no claim authority)
```

---

## 7. Files Delivered

| File | Type |
|------|------|
| `docs/reports/policy-baseline-manifest.v1.json` | Manifest (27 policies) |
| `docs/reports/policy-baseline-manifest.v1.md` | Manifest explanation |
| `docs/reports/s2t-3b-shadow-advisor-evaluation.md` | 3B evaluation |
| `nexus-core-rs/src/receipt_verifier.rs` | Hardened verifier |
| `nexus-core-rs/src/flow_machine.rs` | Full transition matrix |
| `tests/integration/test_rust_kernel_smoke.py` | Updated IPC tests |
| `tests/integration/test_rust_wave3_cutover.py` | Dual-run tests |

---

## 8. Acceptance Checklist

| Criterion | Status |
|-----------|--------|
| Tampered JSON not claimable | ✅ Verified (hash mismatch) |
| Missing eval_metrics → claimability=false | ✅ Verified |
| Rust unit tests non-zero | ✅ 38 tests |
| Python IPC tests pass | ✅ 13 tests |
| Python/Rust canonicalization consistent | ✅ mismatch rate = 0 |
| Full matrix tests pass | ✅ 27 flow tests |
| 3B shadow-only maintained | ✅ No promotion |
| Public claim gate intact | ✅ No bypass possible |

---

*This evidence bundle is a baseline freeze snapshot. No expansion is recommended.*
