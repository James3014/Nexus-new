---
artifact_authority: current
owner: James Chen
status: active
campaign_id: github-issue-54-duplicate-modules-20260810
source_issue: https://github.com/James3014/Nexus-new/issues/54
baseline_main: 84eaa6886e0388a4e15f5b837c89e37768b14307
ordered_cards:
  - 01-remove-duplicate-modules.md
current_frontier: null
completed_cards:
  - 01-remove-duplicate-modules.md
blocked_cards: []
AUTO_CHAIN: false
---

# Issue 54 Duplicate Orphan Module Removal

Remove three duplicate module paths whose canonical counterparts have current
callers and whose duplicate paths have none.

Pre-mutation card SHA-256:
`36f6d05a3711f205ff3a4b46d83ac53806d0040d5d4a2b2b72d1d1d532f347af`.

Owner directive comment:
https://github.com/James3014/Nexus-new/issues/54#issuecomment-5235664084

Terminal marker: `DUPLICATE_MODULE_CLEANUP_PROVEN`.

Serialization: never run concurrently with #52 (both mutate
`muse_nexus.egg-info/SOURCES.txt`).

Completion receipt:

- Task Card authorization commit: `baf2ef096`
- implementation head: `IMPLEMENTATION_COMMIT`
- PR: https://github.com/James3014/Nexus-new/pull/PENDING
- deleted 3 duplicate module paths + 2 SOURCES.txt rows
- fresh-main rebind + caller/path/entrypoint checks: zero refs
- canonical callers intact (ContextHub, migrationsafetyvalidator, DrClaw)
- exact-base/post-deletion regression: identical 16-failure set (zero
  regression); Ruff identical pre-existing; `git diff --check` clean
- reached `CANDIDATE_PR_READY`

