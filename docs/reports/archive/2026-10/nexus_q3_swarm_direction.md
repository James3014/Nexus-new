# Q3: Swarm Policy Decision

## Status: Q3_KEEP_SINGLE_7B_PRIMARY

## Q2 Swarm Benchmark Results

| Arm | Task | Mechanism | Notes |
|-----|------|-----------|-------|
| A (single 7B) | C_12481 | ❌ | Baseline |
| A (single 7B) | C_13453 | ❌ | Baseline |
| A (single 7B) | geo_distance | ✅ | Baseline |
| B (self-consistency) | all 3 | 0/3 unique | Same model, same wrong action |
| C (candidate forest) | all 3 | 0/3 best | Forest worse than single |

## Key Findings

1. **Same-model self-consistency doesn't help**: Model produces same wrong action 3 times — no diversity.

2. **Candidate forest performs worse**: Best candidate still wrong mechanism, best_ev_ids=0.

3. **Swarm adds cost but reduces quality**: More model calls = more wrong actions, not better selection.

4. **Single 7B remains best**: 1/3 mechanism correct vs 0/3 for swarm methods.

## Why Swarm Fails Here

- **Same model, same knowledge**: All candidates come from same model with same evidence — no diversity
- **No new information**: Swarming doesn't add new reasoning capacity
- **Cost without benefit**: 3x model calls for worse results
- **Root cause not addressed**: The bottleneck is model action selection accuracy, not candidate diversity

## Q3 Decision

**Q3_KEEP_SINGLE_7B_PRIMARY**

### Rationale

- Swarm methods do not improve mechanism identification
- Same-model self-consistency produces same wrong actions
- Candidate forest performs worse than single 7B
- Single 7B + S1_ranked prompt is already optimal for current task set
- The bottleneck is model action selection accuracy, not swarm/debate

### What to Do Instead

1. **Improve action candidate ranking** (N1) — make top candidates more accurate
2. **Improve S1Ranked prompt** — add mechanism hints that 7B follows
3. **Expand task supply** — more real repair tasks for stable measurement
4. **Strong bare model comparison** — measure target gap
5. **Consider model upgrade** — if 7B ceiling is reached, test 14B with GPU

### When Swarm Might Be Useful

- Hard cross-function tasks where evidence is ambiguous
- Tasks with multiple plausible action candidates
- When diverse local models available (different reasoning styles)
- When 7B consistently abstains on medium-complexity tasks
- When verifier is cheap enough for multi-candidate verification

## Public Claim

**public_claim_allowed=false**
**production_ready=false**
**training_export_allowed=false**
**internal_only=true**
