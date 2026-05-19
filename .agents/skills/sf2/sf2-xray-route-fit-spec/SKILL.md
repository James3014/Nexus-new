# SF2 xray Route Fit Spec

Purpose: candidate-only route-fit skill for `xray`.

Capability keywords: xray, inspect, diagnose, root cause, probe, investigate
Phases: S, X, R

Use when:
- The route capability is `xray`.
- The bounded probe requires selected / injected / used / evidence / gate / outcome receipts.

Evidence contract:
- Emit receipt evidence for route fit.
- Preserve gate evidence and outcome contribution notes.
- Never update runtime defaults from this candidate-only asset.

runtime_eligible: false
public_benchmark_allowed: false
