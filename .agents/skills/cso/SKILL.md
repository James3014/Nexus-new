---
name: cso
description: Load when a governance route needs security-officer style review of policy, credential, auth, or risk-gate evidence.
capability: governance_and_trust
source_status: runtime_review_candidate
runtime_eligible: false
ablation_eligible: true
sf_materialized_from: governance_mutant_alternate
---

# Chief Security Officer Review

## Load When

- A task touches credentials, auth, access control, policy gates, or security-sensitive delivery.
- A governance mutant tests whether missing policy evidence is incorrectly accepted.
- SF governance ablation needs a security-risk candidate with fail-closed behavior.

## Do Not Load When

- The task is ordinary implementation with no security or policy boundary.
- The task asks to bypass, weaken, or ignore a gate.
- Runtime default mounting is requested without SF promotion review.

## Required Receipts

- `security_risk_refs`
- `policy_gate_verdict`
- `credential_or_auth_surface`
- `receipt_path`
- `evidence_path`

## Procedure

1. Identify security-sensitive resources, credentials, auth surfaces, and policy gates.
2. Verify that each acceptance claim has explicit security evidence.
3. Fail closed on missing policy evidence, ambiguous auth behavior, or stale security claims.
4. Emit a risk verdict and any required remediation before acceptance.

## Boundary

This repo-local asset was materialized from SF governance mutant evidence. It is eligible for ablation and runtime review, but not runtime default mounting until a separate promotion gate passes.
