# P3: Small Model Council Policy Decision

## Status: P3_USE_SINGLE_7B_PRIMARY

## P2 Council Benchmark Results

| Arm | Task | JSON | Mechanism | Critic |
|-----|------|------|-----------|--------|
| A (single 7B) | C_12481 | ✅ | ❌ | — |
| A (single 7B) | C_13453 | ✅ | ❌ | — |
| A (single 7B) | geo_distance | ✅ | ✅ | — |
| B (3B+7B) | C_12481 | ✅ | ❌ | judge=high |
| B (3B+7B) | C_13453 | ✅ | ❌ | judge=high |
| B (3B+7B) | geo_distance | ✅ | ✅ | judge=high |
| C (7B+7B) | C_12481 | ✅ | ❌ | accept |
| C (7B+7B) | C_13453 | ✅ | ❌ | accept |
| C (7B+7B) | geo_distance | ✅ | ✅ | accept |

## Key Findings

1. **Council does NOT improve mechanism identification**: All arms have same mechanism correctness (1/3)

2. **3B judge correctly identifies high evidence**: All 3 tasks get "high" sufficiency — useful for routing

3. **7B critic accepts all actions**: No false rejects, but also no catches of wrong actions

4. **Council adds cost but not pass rate**: Extra model calls without improvement

## P3 Decision

**P3_USE_SINGLE_7B_PRIMARY**

### Rationale

- Council adds 2-3x model calls without improving mechanism identification
- 3B judge is useful for evidence sufficiency but doesn't improve action selection
- 7B critic doesn't catch wrong actions (accepts all)
- Single 7B + S1_ranked prompt is already producing valid JSON
- The bottleneck is model action selection accuracy, not debate/consensus

### What Council Provides

| Component | Value | Evidence |
|-----------|-------|----------|
| 3B Judge | **LOW** — correct evidence sufficiency | All tasks get "high" |
| 7B Critic | **NONE** — accepts all actions | No false rejects, no catches |
| Council overhead | **NEGATIVE** — adds cost | 2-3x model calls |

### What to Do Instead

1. **Improve action candidate ranking** (N1) — make top candidates more accurate
2. **Improve S1Ranked prompt** — add mechanism hints that 7B follows
3. **Expand task supply** — more real repair tasks for stable measurement
4. **Strong bare model comparison** — measure target gap

### When Council Might Be Useful

- Hard cross-function tasks where evidence is ambiguous
- Tasks with multiple plausible action candidates
- When 7B consistently abstains on medium-complexity tasks
- When diverse 7B models available (different reasoning styles)

## Public Claim

**public_claim_allowed=false**
**production_ready=false**
**training_export_allowed=false**
**internal_only=true**
