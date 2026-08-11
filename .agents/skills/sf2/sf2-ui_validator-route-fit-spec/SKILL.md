---
name: sf2-ui_validator-route-fit-spec
description: Candidate-only route-fit specification for ui_validator.
runtime_eligible: false
---

# SF2 ui_validator Route Fit Spec

Purpose: candidate-only route-fit skill for `ui_validator`.

Capability keywords: ui, browser, frontend, visual, playwright
Phases: D, A, C

Use when:
- The route capability is `ui_validator`.
- The bounded probe requires selected / injected / used / evidence / gate / outcome receipts.

Evidence contract:
- Emit receipt evidence for route fit.
- Preserve gate evidence and outcome contribution notes.
- Never update runtime defaults from this candidate-only asset.

runtime_eligible: false
public_benchmark_allowed: false
