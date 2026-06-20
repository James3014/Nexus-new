# Release Verification Summary — nexus-receipt-core v0.1

## Test Results

| Category | Total | Passed | Failed |
|----------|-------|--------|--------|
| Unit Tests | 7 | 7 | 0 |
| Integration Tests | 12 | 12 | 0 |
| Python-Rust Parity | 12 | 12 | 0 |

## Mismatch Ledger

- Total comparisons: 12
- Mismatches: 0

## Known Limitations

1. **No network calls** — operates on local files only
2. **No policy decisions** — does not route, plan, or make capability judgments
3. **Schema v0.1 frozen** — future versions may add fields but will not remove or rename existing ones
4. **Does not handle FlowMachine transitions** — transition validation is a future phase
5. **Does not implement regex matching** — matcher parity is a future phase
6. **Does not include 3B selector evaluation** — shadow evaluation is a future phase

## What This Proves

- Deterministic receipt verification works correctly across all fixture categories
- Rust verifier and Python canonicalizer produce aligned results (0 mismatches)
- Fail-closed logic is enforced: `hashmatch == None` never produces `claimabilityconfirmed == true`
- Error code priority chain is correctly implemented

## What This Does NOT Prove

- Production-scale performance (no benchmark data in v0.1)
- Compatibility with FlowMachine state transitions
- Matcher regex parity
- 3B selector improvement over rule baseline
- End-to-end Nexus integration stability
