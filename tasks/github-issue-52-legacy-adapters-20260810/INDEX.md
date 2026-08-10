---
artifact_authority: current
owner: James Chen
status: active
campaign_id: github-issue-52-legacy-adapters-20260810
source_issue: https://github.com/James3014/Nexus-new/issues/52
task_id: GITHUB-ISSUE-52-LEGACY-ADAPTERS
baseline_main: 84eaa6886e0388a4e15f5b837c89e37768b14307
ordered_cards:
  - 01-remove-legacy-adapters.md
current_frontier: 01-remove-legacy-adapters.md
completed_cards: []
blocked_cards: []
AUTO_CHAIN: false
---

# Issue 52 Legacy Adapter Removal

Issue: https://github.com/James3014/Nexus-new/issues/52
Owner directive: queue 5/5B (DeepSeek may self-claim only after #54 is no
longer an active conflicting SOURCES.txt mutation owner).
Terminal marker: `LEGACY_ADAPTER_REMOVAL_PROVEN`.

Serialization: never mutate `muse_nexus.egg-info/SOURCES.txt` concurrently
with #54/#55.
