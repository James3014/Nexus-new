---
name: sf2-codeintel-route-fit-spec
description: Use when Nexus route capability is codeintel and the task needs code scanning, impact analysis, symbol context, dependency graph, and code intelligence receipts; return receipt/evidence/gate/outcome-backed guidance for SF or runtime review. Do not use for unrelated one-off writing or tasks without runtime evidence needs.
---

# SF2 codeintel Route Fit Spec

Purpose: candidate-only route-fit skill for `codeintel`.

Capability keywords: codeintel, code scan, impact, symbol, ast, repo graph, dependency graph, architecture, api, interface, schema-analysis, code simplification
Phases: S, P, X

Use when:
- The route capability is `codeintel`.
- The bounded probe requires selected / injected / used / evidence / gate / outcome receipts.

Evidence contract:
- Emit receipt evidence for route fit.
- Preserve gate evidence and outcome contribution notes.
- Never update runtime defaults from this candidate-only asset.

runtime_eligible: false
public_benchmark_allowed: false
