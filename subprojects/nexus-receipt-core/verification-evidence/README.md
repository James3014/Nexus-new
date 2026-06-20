# Verification Evidence Bundle

This directory contains the minimal reproducible evidence package for `nexus-receipt-core` v0.1 release candidate.

## Files

| File | Purpose |
|------|---------|
| `README.md` | This file |
| `build-info.txt` | Environment snapshot: commit SHA, date, Rust/Python versions, OS |
| `cargo-test.txt` | Raw `cargo test` output (proves unit tests actually ran) |
| `integration-test.txt` | Raw integration test output (proves fixture paths and CLI/library wiring) |
| `parity-report.json` | Rust ↔ Python canonicalization alignment result |
| `mismatch-report.json` | Mismatch ledger (0 mismatches is itself evidence) |
| `fixture-manifest.md` | Inventory of all fixtures with expected behavior |
| `release-verification-summary.md` | Human-readable summary of all test results |

## How to Reproduce

```bash
cd subprojects/nexus-receipt-core
cargo test --lib > verification-evidence/cargo-test.txt
cargo test --test integration > verification-evidence/integration-test.txt
python3 schemas/python/check_parity.py > verification-evidence/parity-report.json
python3 schemas/generate_mismatch_report.py ... > verification-evidence/mismatch-report.json
```

## Design Principle

> Place the minimum evidence bundle that supports the claim "v0.1 is complete."
> Not just a summary, not every CI dump. Reproducible, verifiable, traceable.
