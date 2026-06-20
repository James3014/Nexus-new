# Five-Task Claim Separation — Phase 5

## Classification Buckets

| Bucket | Description | Claim Eligible | Public Claim | Training |
|--------|-------------|----------------|--------------|----------|
| verifier_passed_by_execution | Full execution chain verified | true | false | false |
| verifier_passed_by_code_review_parity | Code review confirms parity | false | false | false |
| env_blocked_but_review_verified | Env blocked, review confirms | false | false | false |

## Special Cases

| Task | Bucket | Reason |
|------|--------|--------|
| concurrency_bug_01 | env_blocked_but_review_verified | Requires specific runtime conditions not in test env |

## Rules

1. `public_claim_allowed=false` for ALL buckets
2. `training_eligible=false` for ALL buckets (no training export)
3. `concurrency_bug_01` must NOT be merged into execution-verified green class
4. Code-review parity ≠ execution-verified

## Internal Capability Statement

Nexus local 7B/14B repair pipeline can:
- Produce patches that pass verifier in controlled execution environments
- Classify execution outcomes by authority and eligibility
- Separate model success from canonical recovery from tool demonstration

Nexus local 7B/14B repair pipeline cannot (yet):
- Make public claims about capability
- Export training data without human review
- Guarantee execution-verified results across all task types

## Residual Caveats

1. All classifications are internal-only — no public claims
2. Training export requires separate human review approval
3. concurrency_bug_01 is classified separately due to runtime dependency
4. Code-review parity is not equivalent to execution verification
