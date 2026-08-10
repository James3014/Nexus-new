---
artifact_authority: current
owner: James Chen
status: active
campaign_id: github-issue-82-learning-impact-map-20260810
source_issue: https://github.com/James3014/Nexus-new/issues/82
baseline_main: 84eaa6886e0388a4e15f5b837c89e37768b14307
ordered_cards:
  - 01-map-learning-modules.md
current_frontier: null
completed_cards:
  - 01-map-learning-modules.md
blocked_cards: []
AUTO_CHAIN: false
---

# Issue 82 Learning Impact Mapping

Add a conservative subsystem impact-map rule so otherwise-unmapped
`nexus/learning/*` production changes select the complete `tests/learning`
suite, while more-specific existing learning rules retain precedence.

Pre-mutation card SHA-256:
`3fb0756d08e04568cd446eae36d77c9227ffcb290822ae38643647301d8e2c23`.

Owner directive comment:
https://github.com/James3014/Nexus-new/issues/82#issuecomment-5235660460

Completion receipt:

- implementation head: `713273bb3`
- Task Card authorization commit: `03ce9d453`
- PR #83: https://github.com/James3014/Nexus-new/pull/83
- exact two-file source scope plus Task Card binding
- tests: 14 select_tests + 20 impact-gate/index + 6 impact-service/wiki-sync + 61 ops sweep
- production selector for PR #80 learning module maps to `tests/learning`,
  high risk, reason `learning_contract`, no unmatched path
- `git diff --check`: clean
- reached `CANDIDATE_PR_READY` (PR opened to `main`; no self-approve/merge)
