---
campaign_id: CAMPAIGN-NEXUS-401-SEMANTIC-AUTHORITY-DELTA-20260817
issue: 401
repository: James3014/Nexus-new
status: READY_FOR_EXECUTION
baseline_revision: 0de07f518538d8f5ec9049f3f2ab04ebb3f92168
rebind_base_revision: 0de07f518538d8f5ec9049f3f2ab04ebb3f92168
historical_candidate_head: f37242f8e58f09826fa6b0e817b6e97b6a5bf5f1
current_frontier: ISSUE-401-SEMANTIC-AUTHORITY-DELTA-01
AUTO_CHAIN: false
claim_ceiling: SEMANTIC_AUTHORITY_DELTA_CANDIDATE_ONLY
---

# Issue #401 semantic authority delta campaign — current-main rebind

This campaign preserves the historical #402 design lineage while rebuilding it against current main. It remains governed because it changes execution-lane classification semantics; the new predicate cannot downgrade this campaign itself.

| Task | Status | Outcome | Verification | Claim ceiling |
|---|---|---|---|---|
| `ISSUE-401-SEMANTIC-AUTHORITY-DELTA-01` | `ACTIVE` | pure semantic predicate + current normative authority wording + positive/negative tests | focused pytest, compileall, strict boundary, path/deletion audit, diff check, independent review | `SEMANTIC_AUTHORITY_DELTA_CANDIDATE_ONLY` |

No fourth lane, no Planner/Workforce/lifecycle selector change, no retroactive history rewrite, no protected merge/release/production authority. `AUTO_CHAIN=false`.
