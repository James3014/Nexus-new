# N30R-V1 Live Qwen 7B Armor Validation Closure

## Deterministic Oracle Validation

- **Trace**: `docs/bench/n30r/v1_full_armor_trace_1783731744.json`
- **Oracle status**: `DETERMINISTIC_PATH_ACCEPTED_LIVE_PENDING`
- **Accepted**: `true`
- **Missing fields**: none
- **Hash mismatches**: none

## Provider Preflight

| Field | Value |
|-------|-------|
| endpoint | `http://localhost:11434` |
| provider | Ollama |
| version | 0.31.1 |
| model requested | `qwen2.5-coder:7b-instruct` |
| model available | `true` |
| preflight timestamp | `2026-07-11T09:07:29+0800` |

## Live Prompt

| Field | Value |
|-------|-------|
| hash | computed per prompt_contract |
| task | `n30r_smoke_semantic` |
| target symbol | `is_even` |
| locked search | `return n % 2 == 1` |
| source anchor | present |
| protocol | SEARCH/REPLACE |
| verifier expectation | present |

## Live Response

| Field | Value |
|-------|-------|
| received | `true` |
| length | > 0 |
| hash | computed |
| latency | 79.4 sec |

## Candidate Lifecycle

| Phase | Status |
|-------|--------|
| parser | completed |
| candidate created | `true` |
| candidate hash | `a2cb8991...` |
| candidate isolated | `true` |
| apply | `applied` |
| verifier | `fail` |
| retry triggered | `true` |
| second candidate | `true` (differs) |
| final verifier | `fail` |

## Live Result

| Field | Value |
|-------|-------|
| solved | `false` |
| terminal status | `LIVE_VERTICAL_SLICE_VERIFIED_FAIL` |
| exact failure family | verifier fail after retry |

## A1 Live Validation

| Field | Value |
|-------|-------|
| trace | `v1_live_7b_trace_1783732358.json` |
| oracle status | `FULL_ARMOR_PATH_ACCEPTED` |
| accepted | `true` |

## Tests

```
collected: 367
passed: 367
failed: 0
duration: 6.89s
```

## Commits

- A1 cherry-pick: `2ed6c3ce6`
- Deterministic validation + oracle fix: `(pending)`
- Live validation: `(pending)`

## Claim Boundary

| Item | Value |
|------|-------|
| Deterministic retry closed | `true` |
| Live Qwen executed | `true` |
| Full armor path accepted | `true` |
| Effectiveness measured | `false` |
| V2 executed | `false` |
| Production ready | `false` |
