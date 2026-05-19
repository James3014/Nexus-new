---
name: github7-first-principles-autoreason
description: Prompt-only autoreason challenger derived from first-principles-skill. Use for reasoning/decision capability comparisons only.
source_repo: https://github.com/awesome-skills/first-principles-skill
source_commit: 5623c2fa7c5a6ab47eee0d308431437f52c6ff1e
runtime_mount_candidate: false
sf_challenger_only: true
---

# First Principles Autoreason

Use this skill only as a Nexus SF challenger for `autoreason`. It converts first-principles analysis into a bounded reasoning receipt.

## Boundaries

- Do not replace policy gates, hidden verifiers, or runtime receipts.
- Do not turn philosophical analysis into a delivery claim without evidence.

## Method

1. State the decision, constraint, and desired outcome.
2. Break the problem into primitives that must be true regardless of convention.
3. Separate facts, assumptions, and guesses.
4. Score candidate actions by causal path, evidence strength, failure mode, and reversibility.
5. Pick the smallest action that preserves the core capability while reducing risk or cost.
6. Emit the reasoning as receipt-friendly fields: claim, evidence, assumption, chosen_action, rejected_alternatives, and outcome contribution.
