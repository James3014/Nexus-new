# N30R-R4 Closeout: Single-Capability Diagnostic Wave

**Status**: N30R_R4_C1_SMOKE_PASS

## run ID
20260710T101416Z

## exact one-variable difference
C1 arm adds one bounded verifier-evidence retry after first candidate fails deterministic verifier.

## retry eligibility
Only triggered when: applied patch succeeds but verifier returns non-zero exit code.

## retry count bound
Exactly 1 retry per task. No retry for: provider failure, empty output, model timeout, infra-invalid.

## evidence packet fields
- verifier exit code
- stdout excerpt (max 500 chars)
- stderr excerpt (max 500 chars)
- target file
- previous patch hash
- previous apply status

## golden leakage audit
- Evidence packet contains no golden patch
- Evidence packet contains no golden source
- Retry prompt contains no golden content

## final verifier authority
Deterministic verifier remains final authority. Retry only re-prompts with evidence; verifier still decides pass/fail.

## model used
qwen2.5-coder:7b-instruct (same as core and bare)

## tests
48 passed (13 contracts + 18 runner + 17 real core bridge)

## smoke rows
8 (4 core baseline + 4 C1)

## C1 results
- C1 solved: 0/4 (same 7B model, verifier-evidence retry did not fix bugs)
- C1 retries triggered: 4/4 (all tasks got evidence retry)
- Core solved: 0/4

## no 3B / no alternate proposer / no critic / no 14B
## no heldout execution
## production_ready=false
## public_claim_allowed=false
