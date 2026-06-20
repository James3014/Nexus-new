# Rust main Packet Only Commit Gate v0

## Summary
Commit: `3c22eada3af0ccf3177d3a60ae22d6b0da51e7ae`

## File Committed
| File | diff_stat | Risk |
|------|----------|------|
| nexus-core-rs/src/main.rs | +31/-0 | MEDIUM |

## Changes
Added two new Request variants:
- `GetLegalTransitions { current: FlowState }` — returns legal next states and terminal status
- `IsTerminal { state: FlowState }` — returns whether a state is terminal
Both are pure metadata queries with no execution/routing effect.

## Verification
- cargo check: PASS (1 pre-existing warning, 0 errors)
- staging_verification_status: PASS

## Governance
archive_status: PAUSED_ARCHIVED | no model_calls | no verifier_rerun | no s2t_export
