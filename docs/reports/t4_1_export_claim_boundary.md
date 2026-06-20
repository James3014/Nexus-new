# T4.1 Export / Claim Boundary

**Date**: 2026-06-18

---

## Hard Rules

1. **public_claim_allowed = false** for ALL candidates
2. **export_as_public_claim = false** for ALL candidates
3. Focused internal results cannot become public benchmark claims
4. Source hygiene blockers are NOT model failures
5. Stored-output replay is NOT fresh model success
6. model_calls=0 is NOT model patch success
7. deterministic fallback is NOT model success
8. Historical clean is NOT current replay success

## Export Classification

| Category | Count | Export Allowed |
|----------|-------|---------------|
| active_replayable | 12 | Internal training review only |
| historical_clean_source_stale | 8 | Historical evidence with source caveat |
| stored_output_replay_verified | 0 | Historical evidence only |
| model_patch_success_candidate | 0 | requires_human_review |

## Non-Claims

This is NOT:
- A public benchmark
- A Qwen solve rate
- Comparable to official SWE-bench
- Evidence of production-ready patching

This IS:
- Internal controlled model-candidate evidence
- Source-revision-hygiene-classified
- Attribution-safe
- Human review required before training/export
