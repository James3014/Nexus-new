# SF2 ddtree Route Fit Spec

Purpose: candidate-only route-fit skill for `ddtree`.

Capability keywords: ddtree, decision tree, prune, candidate selection
Phases: P, X, D

Use when:
- The route capability is `ddtree`.
- The bounded probe requires selected / injected / used / evidence / gate / outcome receipts.

Evidence contract:
- Emit receipt evidence for route fit.
- Preserve gate evidence and outcome contribution notes.
- Never update runtime defaults from this candidate-only asset.

runtime_eligible: false
public_benchmark_allowed: false
