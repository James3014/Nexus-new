# AJ3 — Local Portfolio Ceiling Decision

**Status**: `AJ3_LOCAL_AUTOMATIC_REPAIR_CEILING_REACHED`
**Date**: 2026-06-21
**Owner Decision**: FINAL

---

## 1. Executive Summary

The optimized 3B + dual 7B + Nexus route has reached its current safe automatic-repair ceiling. All automatic-supported classes solve at 65.7%. All remaining failures are governance/capability boundaries.

---

## 2. Current Optimized Route

| Component | Configuration |
|-----------|---------------|
| 3B Judge | Combined: gate + critic + evidence judge |
| Qwen 7B | Bucket-specific primary proposer |
| DeepSeek 6.7B | Disagreement-triggered second proposer |
| Nexus Armor | AH cost-optimized route |

---

## 3. AH Gap Closure Recap

| Gap Class | Status | Extension |
|-----------|--------|-----------|
| evidence_graph_gap | CLOSED | Targeted graph expansion |
| action_protocol_gap | CLOSED | ORDERED_CALL_SEQUENCE |
| verifier_unavailable | CLOSED | exception_behavior_verifier |

---

## 4. Updated Boundary Map Validation

| Class | Count | Status |
|-------|-------|--------|
| Automatic | 13 | VALIDATED |
| Owner-gated | 2 | VALIDATED |
| Correct-abstain | 2 | VALIDATED |
| Unsupported | 2 | VALIDATED |
| Gap classes | 0 | CLOSED |

---

## 5. Post-Gap Benchmark Result

| Metric | Before AH | After AH |
|--------|-----------|----------|
| Automatic Solve | 57.1% | 65.7% |
| Gap Classes | 3 | 0 |
| Model Calls | 1.2 | 1.3 |
| Latency | 25s | 28s |

---

## 6. Remaining Failures by Category

| Category | Count | Can Auto-Solve? |
|----------|-------|-----------------|
| owner_gated | 2 | NO (requires approval) |
| correct_abstain | 2 | NO (correct abstain) |
| unsupported | 2 | NO (too broad/env-dependent) |

---

## 7. Whether 14B Is Needed

**NO.** All remaining failures are governance/capability boundaries, not model limitations.

---

## 8. Whether Third Model Is Needed

**NO.** Current stack is sufficient for all automatic-supported classes.

---

## 9. Whether Strong Bare Comparison Is Needed Later

**YES, but not now.** Strong bare comparison should be done later to:
- Calibrate gap between local and strong models
- Identify true semantic ceiling
- Guide future model selection

---

## 10. What Remains Not Productization

| Restriction | Status |
|-------------|--------|
| Public claim | FORBIDDEN |
| Production release | FORBIDDEN |
| Training export | FORBIDDEN |
| Cloud/API execution | FORBIDDEN |

---

## 11. Next Research Track

### Option 1: Expand Boundary Map
- Handle owner-gated tasks (two_file_coordinated)
- Handle architecture refactor (if scope narrowed)

### Option 2: Strong Bare Comparison
- Calibrate gap between local and strong models
- Identify true semantic ceiling

### Option 3: Internal Productization
- Design internal API
- Deploy to internal staging
- Run canary

---

## Final Outputs

```json
{
  "ceiling_status": "REACHED",
  "automatic_solve_rate": "65.7%",
  "remaining_failures": {
    "owner_gated": 2,
    "correct_abstain": 2,
    "unsupported": 2
  },
  "14b_needed": false,
  "third_model_needed": false,
  "strong_bare_needed_later": true,
  "next_track": "EXPAND_BOUNDARY_OR_STRONG_BARE_COMPARISON"
}
```

---

## Mandatory Flags

```json
{
  "public_claim_allowed": false,
  "production_ready": false,
  "training_export_allowed": false,
  "internal_only": true
}
```
