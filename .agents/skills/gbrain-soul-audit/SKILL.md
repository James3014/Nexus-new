---
name: gbrain-soul-audit
description: Load when a governance route needs values, policy, and intent audit before accepting a high-impact claim or action.
capability: governance_and_trust
source_status: runtime_review_candidate
runtime_eligible: false
ablation_eligible: true
sf_materialized_from: governance_mutant_alternate
---

# Governance Values Audit

## Load When

- A task needs policy, intent, or values alignment before final acceptance.
- A claim passes ordinary delivery checks but may still violate a governance or user-intent boundary.
- SF governance ablation needs a candidate that catches false-positive acceptance under incomplete governance evidence.

## Do Not Load When

- The task is a low-risk mechanical edit with no governance boundary.
- The user explicitly asks for runtime default mounting without promotion evidence.
- No receipt path can be produced.

## Required Receipts

- `governance_intent_refs`
- `policy_alignment_verdict`
- `blocked_or_allowed_reason`
- `receipt_path`
- `evidence_path`

## Procedure

1. Identify the claim, action, or route decision that needs governance review.
2. Compare it against user intent, policy gates, and available evidence.
3. Fail closed when intent or policy evidence is missing, contradictory, or stale.
4. Emit a governance verdict with exact blocked or allowed reasons.

## Boundary

This repo-local asset was materialized from SF governance mutant evidence. It is eligible for ablation and runtime review, but not runtime default mounting until a separate promotion gate passes.
