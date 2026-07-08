# P5 Diversity Selection Engine Closure Report

## Status: P5_CLOSED_FOR_CONTROLLED_DIVERSITY_SELECTION_EFFECT

Scope:
- Controlled candidate-selection counterfactuals
- P4 committee routed tool integration
- Trace, fuzzy, metadata receipt evidence
- `production_ready=false`, `public_claim_allowed=false`

## Four Gates (P5-V1–V4) — Effect Evidence

### 1. Counterfactual Selection Gate ✅

| Scenario | P5 off | P5 on | Evidence |
|----------|--------|-------|----------|
| A: first bad → second good | selected_model=bad-model, index=0 | selected_model=good-model, index=1 | P5 beats first-valid ✅ |
| B: duplicate majority + unique | selected_model=qwen, index=0 | selected_model=deepseek, index=2, trap detected | P5 detects trap ✅ |
| C: all unsafe | winner_found=true (no safety check) | winner_found=false, fail_closed=true | P5 blocks unsafe ✅ |

**Scenario A detail:**
- P5 off: `winner = valid_candidates[0]` → bad-model selected
- P5 on: `select_diverse_candidate()` scores candidates → good-model (syntax_score=1.0) beats bad-model (syntax_score=0.2)
- `p5_selected_candidate_index == 1`
- `p5_score_breakdown[1].final_score > p5_score_breakdown[0].final_score`

**Scenario B detail:**
- P5 off: first-valid → qwen duplicate selected
- P5 on: duplicate detection groups qwen candidates → popularity trap detected → deepseek unique selected
- `p5_popularity_trap_detected == True`
- `p5_duplicate_group_count >= 1`
- `p5_selected_candidate_index == 2`

**Scenario C detail:**
- P5 off: no safety check → winner_found=true (unsafe candidate)
- P5 on: all candidates have safety_penalty > 0 → final_score negative → fail_closed
- `winner_found == false`
- `failure_reasons` includes `p5_selection_failed:all_candidates_unsafe`

### 2. Trace Evidence Gate ✅

P5 on receipts contain trace events:
- `p5_trace_event_count > 0`
- Event types produced:
  - `candidate_feature_extracted` (per candidate)
  - `candidate_duplicate_grouped` (when groups exist)
  - `popularity_trap_detected` (trap check)
  - `candidate_scored` (winner selection)
  - `selection_fail_closed` (all-unsafe path)

### 3. Fuzzy Backend Gate ✅

- `p5_score_breakdown` includes `fuzzy_function` dict per candidate
- Functions consumed:
  - `candidate_quality_v1` → quality_score
  - `duplicate_similarity_v1` → near duplicate detection
  - `popularity_trap_risk_v1` → trap risk scoring
- All deterministic backend, no model call, no embedding

### 4. Metadata Consistency Gate ✅ (P5-V4)

| Field | Before V4 | After V4 |
|-------|-----------|----------|
| selected_model (Scenario A) | bad-model ✗ | good-model ✓ |
| selected_model (Scenario B) | qwen ✗ | deepseek ✓ |
| p5_hash == p4_hash | — | consistent ✓ |
| raw_index_map after rejection | — | correct ✓ |

## E2E Scenarios Verified

| Scenario | Description | Result |
|----------|-------------|--------|
| A | One valid candidate → single_candidate selection | ✅ |
| B | Three candidates, first lower-quality → second selected | ✅ |
| C | Three near-duplicate unsafe + one safer unique | ✅ |
| D | All candidates malformed/unsafe → fail_closed | ✅ |
| E | P5 disabled → P4 first-valid regression | ✅ |

## What P5 Proves

- Diversity selector beats first-valid in counterfactual tests
- Duplicate detection groups exact and near-duplicates
- Popularity trap detection avoids homogenous majority
- All-unsafe fail-closed prevents false success
- SelectionTrace baked into runtime receipt
- FuzzyFunctionRegistry consumed by scoring backend
- Selected index / hash / model consistent in receipt

## What P5 Does NOT Prove

- Quota-aware routing (P6 deferred)
- Production cloud endpoint
- Solve-rate improvement on benchmark
- P2/P4 gate relaxation
- Embeddings / model calls / PAW / LoRA
- MemoryAction learning benefit

## Files Changed Across I1–I9 + V1–V4

| Pkg | Files |
|-----|-------|
| I1 | `diversity_selector.py` (DiversityCandidate, DiversitySelectionResult, select_diverse_candidate) |
| I2 | `diversity_selector.py` (CandidateFeatures, extract_features) |
| I3 | `diversity_selector.py` (DuplicateGroup, group_near_duplicates) |
| I4 | `diversity_selector.py` (PopularityTrapDecision, detect_popularity_trap) |
| I5 | `diversity_selector.py` (diversity scoring, _score_candidate) |
| F0 | `fuzzy_functions.py` (registry + 3 backends) |
| I7 | `committee_routed_tool.py` (P5 integration, env guard) |
| I8 | `receipt.py` (P5 fields) |
| I9 | `test_p5_e2e_scenarios.py`, closure report |
| V1 | `diversity_selector.py` (scoring fixes), `test_p5_benefit_gate.py` |
| V2 | `diversity_selector.py` (SelectionTrace), `committee_routed_tool.py` (trace merge), `test_p5_v2*.py` |
| V3 | `diversity_selector.py` (fuzzy function consumption), `test_p5_v3*.py` |
| V4 | `committee_routed_tool.py` (winner_source_model fix, raw_index_map), `test_p5_metadata_consistency.py` |

## Effect Summary by V Stage

```
Stage    Effect                                                     Evidence
I1–I9    Scaffold + basic P4 integration                            Passing tests
V1       Scoring granularity, counterfactual off/on proof           47/47
V2       SelectionTrace → runtime receipt                           trace_event_count > 0
V3       FuzzyFunction → selector backend                           score_breakdown fuzzy_function
V4       Metadata consistency (selected_model fix)                  111/111
```

## Statements

- P5 closed = diversity selector in P4 candidate selection with effect evidence
- P5 not closed = quota-aware, production cloud, solve-rate improvement
- No real cloud endpoint
- No P2/P4 gate relaxation
- No embeddings / model calls
- No benchmark
- MemoryActionReceipt remains contract-only
- `production_ready=false`
- `public_claim_allowed=false`
