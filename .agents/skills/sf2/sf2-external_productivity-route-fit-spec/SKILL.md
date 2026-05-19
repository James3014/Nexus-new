---
name: sf2-external_productivity-route-fit-spec
description: Use when Nexus route capability is external_productivity and the task needs external productivity tools, docs, sheets, calendar, mail, and connector-safe receipts; return receipt/evidence/gate/outcome-backed guidance for SF or runtime review. Do not use for unrelated one-off writing or tasks without runtime evidence needs.
---

# SF2 external_productivity Route Fit Spec

Purpose: candidate-only route-fit skill for `external_productivity`.

Capability keywords: gmail, calendar, sheets, docs, slides, airtable, creative, image, video
Phases: S, D

Use when:
- The route capability is `external_productivity`.
- The bounded probe requires selected / injected / used / evidence / gate / outcome receipts.

Evidence contract:
- Emit receipt evidence for route fit.
- Preserve gate evidence and outcome contribution notes.
- Never update runtime defaults from this candidate-only asset.

runtime_eligible: false
public_benchmark_allowed: false
