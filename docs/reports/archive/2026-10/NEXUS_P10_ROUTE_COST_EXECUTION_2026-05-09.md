# Nexus P10 Route Cost Execution Report

## Final Target

Make Gemini 3 Flash / Gemini 3.1 Pro wearing Nexus approach GPT-5.5 direct on fixed public tasks while preserving:

- verified delivery
- trust mismatch = 0
- defensible cost per verified success

## P1-P10 Status

| Phase | Status | Evidence |
| --- | --- | --- |
| P1 cost attribution | DONE | Flash/Pro 12x1 summaries show cost concentrated in hidden/context/governance/trust lanes. |
| P2 route contract slimming | DONE for hidden bugfix lane | `public_bugfix` now routes through supervised bare-first when Local Reflex marks low risk. |
| P3 Local Reflex admission | DONE | Token-aware risk matching prevents `rm` false positives inside `normalization` / `verification`. |
| P4 deterministic fixture generalization | PARTIAL | Hidden parser and trust classifier now have explicit decision tables; next step is generator-based contracts. |
| P5 GPT-5.5 reference | DONE from existing worker artifact | `p10_gpt55_bare_rlm4`: GPT-5.5 direct verified 3/4. |
| P6 same-model A/B | PARTIAL | Flash/Pro 12x1 passed; hidden lane single-task reruns passed after slimming. 12x2 still needed for public claim. |
| P7 Autodata/S2T feedback | DONE for gate | pre-flash Autodata manifest gate passes for Flash/Pro manifests. |
| P8 cost policy promotion | DONE for hidden bugfix feature rule | Added `feature:public-bugfix-hard-neutral-fixture-supervised-bare-first`. |
| P9 public report readiness | PARTIAL | Evidence exists, but public claim still needs 12x2 same-model denominator. |
| P10 DFlash / inference adapter | DEFERRED | Current endpoint bottleneck is route/phase/prompt work, not decoder loop; DFlash remains adapter-only future work. |

## Measured Improvement

| Task | Model | Previous Nexus | New Nexus | Result |
| --- | --- | ---: | ---: | --- |
| hidden-001 | Flash | 43.7395s / phase 26.9985s | 16.0080s / phase 0.0s | VERIFIED, trust=0 |
| hidden-002 | Flash | 57.4761s / phase 49.0694s | 30.8559s / phase 0.0s | VERIFIED, trust=0 |
| hidden-001 | Pro | 100.2940s / phase 92.0946s | 23.3416s / phase 0.0s | VERIFIED, trust=0 |
| hidden-002 | Pro | 57.9925s / phase 49.7167s | 34.4740s / phase 0.0s | VERIFIED, trust=0 |

## Root Cause

Local Reflex matched high-risk term `rm` as a raw substring. That made safe words like `normalization` and `verification` look destructive, incorrectly forcing heavy Nexus paths.

## Fix Boundary

The fix stays in route admission and promoted policy:

- token-aware high-risk term matching in Local Reflex
- low-risk public hidden bugfix admission
- supervised bare-first policy under hidden verifier
- no reduction of governance gates for high-risk tasks

## DFlash Decision

DFlash-style acceleration is not the next best fix yet. It speeds decoding, but current Nexus cost is still dominated by:

- route materialization
- phase wall time
- prompt/context payload
- unnecessary full Nexus invocation on low-risk tasks

The correct next DFlash step is only an interface/feature-flag ADR after route/phase cost is no longer the dominant bottleneck.

## P11-P20 Continuation

| Phase | Status | Evidence |
| --- | --- | --- |
| P11 Flash hidden 2x2 | DONE | Nexus 4/4 verified, bare 3/4, trust=0, avg wall 24.7991s, phase 0.0s. |
| P12 Pro hidden 2x2 | DONE | Nexus 4/4 verified, bare 2/4, trust=0, avg wall 34.9716s. One trial escalated and recovered. |
| P13 Hot-lane policy probe | DONE | Flash hot4 before runtime pruning: Nexus 4/4 verified but avg wall 59.23s and selected full stack. |
| P14 Context/refactor policy rules | DONE | Added feature rules for `context_sync_capped` and `governance_hardened_capped`. |
| P15 Regression found | DONE | Policy source appeared, but runtime `capability_plan_selected` still reopened full-stack capabilities. |
| P16 Planner seam fix | DONE | Route-cost capped lanes now prune research/multi-agent/nightshift/report expansion while preserving artifact/claim/delivery/mempalace gates. |
| P17 Runtime route proof | DONE | Manual route payload for governance capped reduced to `codeintel, belief, delivery_gate, mempalace_gate, artifact_gate, claim_gate`. |
| P18 Tests | DONE | Targeted planner and app route tests pass. |
| P19 Flash hot4 after pruning | DONE | Nexus 4/4 verified, bare 2/4, trust=0, selected capabilities no longer full-stack. |
| P20 Closure | DONE | Residual bottleneck is R-phase wall time inside verified hyper execution, not capability over-selection. |

## P19 Flash Hot4 Result

| Task | Nexus result | Nexus wall / phase | Bare result | Route lane | Selected capability plan |
| --- | --- | ---: | --- | --- | --- |
| gov-002 | VERIFIED, trust=0 | 70.85s / 62.53s | SUCCESS | governance_hardened_capped | codeintel, belief, delivery_gate, mempalace_gate, artifact_gate, claim_gate |
| context-002 | VERIFIED, trust=0 | 32.19s / 24.27s | FAILED | context_sync_capped | codeintel, belief, delivery_gate, mempalace_gate, artifact_gate, claim_gate |
| trust-001 | VERIFIED, trust=0 | 35.47s / 27.68s | SUCCESS | governance_hardened | codeintel, belief, delivery_gate, mempalace_gate, artifact_gate, claim_gate |
| trust-002 | VERIFIED, trust=0 | 52.63s / 44.29s | FAILED | governance_hardened | codeintel, belief, delivery_gate, mempalace_gate, artifact_gate, claim_gate |

Aggregate:

- Flash Nexus hot4: 4/4 verified, semantic_verified_rate=1.0, trust_mismatch_rate=0.0, avg wall=47.788s, avg phase=39.6911s.
- Flash bare hot4: 2/4 verified, semantic_verified_rate=0.5, trust_mismatch_rate=0.0, avg wall=37.947s.

## Lessons

- Policy source is not enough. Route-cost policy must be reconciled at the planner selected-capability seam, or runtime can silently reopen expensive capabilities.
- The next cost bottleneck is not selected capability breadth for hot4. After pruning, selected plans are lean, but R phase still dominates wall time.
- `context_sync_capped` is a strong candidate lane: it preserved verified delivery where bare failed and avoided the old context outlier.

## Next Long Plan

Final target: Gemini 3 Flash / Gemini 3.1 Pro wearing Nexus should approach GPT-5.5 direct on fixed public tasks, with verified delivery preserved, trust mismatch at 0, and cost per verified success defensible enough for public reporting.

1. P21: Split R-phase timing inside hyper execution into model call, patch apply, hidden verifier, receipt generation, and closeout.
2. P22: Add a route-quality gate that fails if capped lanes select any forbidden high-cost expansion capability.
3. P23: Run Pro hot4 after the same pruning to verify this is not Flash-specific.
4. P24: Run Flash hidden2 + hot4 combined 6-task suite, one fail stops and triages trace.
5. P25: If P24 passes, expand Flash to 12-task fixed public suite and compare against GPT-5.5 direct reference.
6. P26: If cost is still high with lean selected plans, optimize hyper R-phase execution rather than planner rules.
