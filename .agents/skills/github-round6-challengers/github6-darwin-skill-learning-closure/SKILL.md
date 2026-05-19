---
name: github6-darwin-skill-learning-closure
description: Use for Nexus learning_closure work that compares a skill before and after changes with a rubric, test prompts, and keep/revert decision. Do not use to auto-edit production runtime policy or to accept self-scored improvements without evidence.
metadata: {"source_repo":"https://github.com/alchaincyf/darwin-skill","source_commit":"2056abfccd924d68ae6baa9193cafff0f666260b","source_status":"github_round6_prompt_only_rewrite","runtime_eligible":false,"ablation_eligible":true}
---

# GitHub Round6 Darwin Skill Learning Closure

Use this skill as a prompt-only learning-closure discipline for skill improvement loops.

## Boundary

- Do not edit runtime defaults.
- Do not keep a change only because wording looks better.
- Do not self-certify improvements without before/after evidence.

## Workflow

1. Define the skill asset, capability, current baseline, and candidate change.
2. Score the current and candidate versions on:
   - trigger fit
   - scope clarity
   - negative triggers
   - evidence requirements
   - output contract
   - operational risk
   - testability
   - measured task outcome
3. Require at least two test prompts or receipt-backed rows.
4. Compare before/after:
   - behavior quality
   - token cost
   - wall time
   - failure rate
   - evidence completeness
5. Return `keep`, `hold`, or `revert`.

## Output Contract

Return:

- `baseline`
- `candidate`
- `rubric_scores`
- `test_evidence`
- `delta`
- `decision`
- `next_action`

Prefer `hold` when evidence is incomplete.
