---
name: sf2-policy_capability_gate-route-fit-spec
description: Candidate-only SF route-fit skill for policy_capability_gate. Use when SF needs to evaluate whether a skill helps enforce policy, capability gate, learning gate, governance, trust, and fail-closed routing evidence without granting runtime mount permission.
---

# SF2 Policy Capability Gate Route-Fit Spec

Use this candidate only inside SF ablation or bucket classification. It is not a runtime default.

## Load when

- A task needs policy gate, capability gate, learning gate, governance, trust, or fail-closed evidence.
- A route must prove selected / invoked / evidence / gate / outcome before any skill value claim.

## Do not load when

- The task is ordinary coding, research gathering, or public benchmark reporting.
- The skill would bypass runtime receipt confirmation.

## Evidence required

- `capability_id=policy_capability_gate`
- policy or capability gate receipt
- fail-closed reason when evidence is missing
- outcome contribution distinct from planner selection

