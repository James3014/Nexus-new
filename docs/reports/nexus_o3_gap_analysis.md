# O3: Gap Analysis and Optimization Decision

## Status: O3_ACTION_SELECTION_IS_MAIN_GAP

## O2 Local-Only Comparison Results

| Task | JSON | Mechanism | Evidence IDs | Markdown |
|------|------|-----------|--------------|----------|
| C_12481 | ✅ | ❌ | ✅ | ❌ |
| C_13453 | ✅ | ❌ | ✅ | ❌ |
| geo_distance | ✅ | ✅ | ✅ | ❌ |
| perm_inverse | ✅ | ❌ | ✅ | ❌ |

**JSON valid: 4/4 (100%)**
**Mechanism correct: 1/4 (25%)**
**Evidence cited: 4/4 (100%)**

## Gap-to-Target Analysis

### Local 7B Armored
- ✅ JSON output: consistent (4/4)
- ⚠️ Mechanism identification: 1/4 (25%)
- ✅ Evidence citation: 4/4 (100%)
- ⚠️ Patch generation: not measured (requires applier)

### Gap to GPT/Gemini Bare
- GPT/Gemini likely produces correct patch directly
- Local 7B armored produces correct JSON but mechanism is often wrong
- Deterministic applier bridges gap when mechanism is correct
- **Main gap: action selection accuracy**

### Remaining Gaps
1. **Action selection accuracy**: Model produces JSON but selects wrong mechanism/action
2. **Task supply**: Only 2 real repair tasks available
3. **Strong bare model comparison**: Not yet executed

## Failure Taxonomy

| Category | Count | Notes |
|----------|-------|-------|
| BARE_FORMAT_FAILURE | 0 | All produce JSON |
| BARE_WRONG_MECHANISM | 3 | C_12481, C_13453, perm_inverse |
| ACTION_SELECTION_ERROR | 3 | Same as wrong mechanism |
| EVIDENCE_GAP | 0 | All cite evidence |
| ACTION_DSL_GAP | 0 | DSL sufficient |
| TASK_SUPPLY_LIMITATION | 1 | Only 2 real repair tasks |

## What Nexus Contributes

| Component | Contribution | Evidence |
|-----------|-------------|----------|
| Constrained Action DSL | **PRIMARY** — forces JSON | 4/4 JSON valid |
| Evidence Packet | **HIGH** — mechanism context | 4/4 evidence cited |
| Deterministic Applier | **HIGH** — intent → patch | Requires correct mechanism |
| S1Ranked Prompt | **MEDIUM** — helps mechanism | 1/4 mechanism correct |
| Bounded Refinement | **MEDIUM** — corrects args | N/A measured |

## What Still Blocks Local Qwen

1. **Action selection accuracy**: Model selects wrong mechanism/action even with evidence
2. **Task supply**: Only 2 real repair tasks available for stable measurement
3. **Strong bare comparison**: Not executed — cannot measure target gap

## Next Optimization Frontier

**O3_ACTION_SELECTION_IS_MAIN_GAP**

1. Improve action candidate ranking (N1)
2. Improve S1Ranked prompt with more mechanism hints
3. Expand task supply with real repair tasks
4. Strong bare model comparison (pending owner approval)

## 30-Day Plan

1. Week 1: Action candidate ranking improvement
2. Week 2: Expanded benchmark with more tasks
3. Week 3: Strong bare model comparison design
4. Week 4: Strategy refinement based on results

## Public Claim

**public_claim_allowed=false**
**production_ready=false**
**training_export_allowed=false**
**internal_only=true**
