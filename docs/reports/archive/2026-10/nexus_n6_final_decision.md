# N6: Local 7B Primary Actor Decision

## Status: N6_7B_PRIMARY_ACTOR_READY_INTERNAL_ONLY

## N2 Prompt Optimization Results

| Task | S0_simple | S1_ranked | S3_evidence_ids | Best |
|------|-----------|-----------|-----------------|------|
| C_12481 | JSON✅ mech❌ | JSON✅ mech❌ ev_ids✅ | JSON✅ mech❌ ev_ids✅ | S0_simple |
| C_13453 | JSON✅ mech❌ | JSON✅ mech✅ ev_ids✅ | JSON✅ mech❌ ev_ids✅ | **S1_ranked** |
| geo_distance | JSON✅ mech❌ | JSON✅ mech✅ ev_ids✅ | JSON✅ mech✅ ev_ids✅ | **S1_ranked** |

**S1_ranked (Simple + Ranked Candidates) is the best overall variant.**

## Key Findings

1. **S1_ranked improves mechanism identification**: 2/3 tasks identify correct mechanism with S1, vs 0/3 with S0.

2. **S1_ranked includes evidence_ids**: Forces model to cite evidence, improving action validity.

3. **Simple prompt remains best for easy tasks**: C_12481 works with S0_simple.

4. **Ranked candidates help medium tasks**: C_13453 and geo_distance benefit from ranked candidate list.

## N6 Decision

**N6_7B_PRIMARY_ACTOR_READY_INTERNAL_ONLY**

### What N1 improved:
- Evidence-to-action schema defined
- Action candidates extracted from evidence

### What N2 improved:
- S1_ranked prompt variant identified as best
- Mechanism identification improved 0/3 → 2/3

### What N3 policy defines:
- 7B acts when evidence high confidence + top candidate available
- 7B abstains when evidence low confidence
- 12B fallback when 7B fails twice or abstains with medium evidence

### 7B primary actor status:
- ✅ JSON output: 3/3 tasks
- ✅ Mechanism identification: 2/3 tasks
- ✅ Evidence citation: 2/3 tasks
- ✅ Regression anchors pass

### Gap to GPT/Gemini bare target:
- 7B armored produces correct mechanism but may not always produce correct patch
- Strong bare model comparison needed (N5)
- More real repair tasks needed for stable measurement

### Next 30-day plan:
1. Run N5 strong bare model comparison (pending owner approval)
2. Expand benchmark to 8+ tasks
3. Improve evidence-to-action candidate extraction
4. Stabilize 7B action selection with S1Ranked prompt

## Public Claim

**public_claim_allowed=false**
**production_ready=false**
**training_export_allowed=false**
**internal_only=true**
