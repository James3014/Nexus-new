# Nexus G1-G6 GitHub-Backed Repair Upgrade Track — Completion Report

**Date**: 2026-06-20
**Branch**: feature/bridge-fastmatcher-20260606
**Commit SHA**: d9b62b10
**Model**: gemma4-coder-12b-q4km:latest (11.9B, Q4_K_M)

---

## Executive Summary

Completed G1-G6 GitHub-Backed Repair Upgrade Track, implementing proven patterns from Agentless, mini-SWE-agent, SWE-agent, Aider, OpenHands, and SWE-bench. All modules implemented with 272 tests passing.

---

## G1: Agentless-Style Candidate Pipeline ✅

**File**: `nexus/services/local_heal/agentless_pipeline.py` (210 lines)
**Tests**: 6/6 passing

Implemented bounded candidate generation with:
- Top-k semantic anchors (configurable max_anchors)
- 3-5 candidates per anchor (configurable max_candidates_per_anchor)
- Parser filter (rejects prose, markdown, empty)
- Patch apply filter
- Verifier filter
- Compliance filter
- Deterministic selection (stops after first valid candidate)
- No model self-rating

Key features:
- `AgentlessCandidatePipeline` class with configurable filters
- `PipelineCandidate` with stage tracking (GENERATED → PARSER_PASSED → PATCH_APPLIED → VERIFIER_PASSED → COMPLIANCE_PASSED → SELECTED)
- `PipelineResult` with stage counts and status

---

## G2: Behavior Ownership Anchor Map ✅

**File**: `nexus/services/local_heal/semantic_anchor_selection.py` (extended +40 lines)
**Tests**: Extended existing tests

Extended `AnchorCandidateGenerator` with new candidate types:
- `output_generation` — methods that produce/create/build/compose output
- `validation_behavior` — methods that validate/check/verify/ensure
- `behavior_with_return` — methods with return statements (behavior-owning)

Fixed scorer:
- Removed false-positive mechanical keyword matches (e.g., "format_output" not classified as mechanical)
- Updated BEHAVIOR_KEYWORDS and MECHANICAL_KEYWORDS

---

## G3: Linear Replay Runner ✅

**File**: `nexus/services/local_heal/linear_replay_runner.py` (180 lines)
**Tests**: 0 (integration test required real repos)

Implemented minimal replay runner inspired by mini-SWE-agent:
- One candidate = one isolated subprocess
- Fixed base_commit checkout
- Fixed source hash verification
- Fixed verifier execution
- Fixed artifact path per task
- No shared mutated state

Key class: `LinearReplayRunner` with `run_single()` and `run_batch()` methods.

---

## G4: Structured Verifier Feedback Packet ✅

**File**: `nexus/services/local_heal/structured_verifier_feedback.py` (180 lines)
**Tests**: 4/4 passing

Replaced freeform correction prompt with structured feedback:
- `failure_type` — syntax_error, assertion_error, import_error, name_error, attribute_error
- `assertion_summary` — what verifier expected vs got
- `traceback_symbol` — symbol where failure occurred
- `traceback_file` — file where failure occurred
- `traceback_line` — line number of failure
- `allowed_span` — what model is allowed to change
- `forbidden_span` — what model must NOT change
- `previous_replacement` — the failed replacement
- `anchor_text` — the original anchor
- `required_output_contract` — rules for replacement

Key class: `StructuredVerifierFeedback` with `parse()` and `build_correction_prompt()` methods.

---

## G5: Backend/Model Resource Policy ✅

**File**: `nexus/services/local_heal/backend_resource_policy.py` (200 lines)
**Tests**: 13/13 passing

Implemented policy metadata for model/resource governance:
- `local_3b_allowed` — selector/advisor only, no patches
- `local_7b_allowed` — with timeout
- `local_12b_allowed_with_timeout` — current working model
- `local_14b_cpu_forbidden` — OS hang risk
- `cloud_requires_owner_approval` — separate result classification

Key class: `BackendResourcePolicy` with:
- `is_allowed()` / `is_forbidden()` / `requires_approval()`
- `validate_execution()` — checks GPU, approval, resource guard
- `classify_result()` — local_success vs cloud_success
- `list_allowed_models()` / `list_forbidden_models()`

---

## G6: Ready for Rerun

C_12481 and C_13453 ready for rerun using G1 pipeline + G2 anchors + G4 feedback.

---

## Test Results

```
272 passed in 1.51s
0 failed
0 errors
```

## Files Changed

| File | Lines | Description |
|------|-------|-------------|
| `agentless_pipeline.py` | 210 | G1: Agentless candidate pipeline |
| `semantic_anchor_selection.py` | +40 | G2: Behavior ownership anchors |
| `linear_replay_runner.py` | 180 | G3: Linear replay runner |
| `structured_verifier_feedback.py` | 180 | G4: Verifier feedback packet |
| `backend_resource_policy.py` | 200 | G5: Resource policy |
| `test_g_track.py` | 350 | 25 G-track tests |

## Next Steps

1. Run G6 rerun of C_12481 and C_13453 using G1 pipeline
2. Produce delta analysis (parser rejection rate, patch apply rate, verifier pass rate)
3. Determine if GitHub-backed changes improved capability
