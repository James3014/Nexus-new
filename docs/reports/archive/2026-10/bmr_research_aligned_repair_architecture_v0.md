# BMR9 — Research-Aligned General Repair Architecture Upgrade

**Status**: `BMR9_RESEARCH_ALIGNED_ARCHITECTURE_UPGRADE_CONFIRMED`
**Date**: 2026-06-21
**Commit**: Pending

---

## Executive Summary

Six research-backed architectural mechanisms implemented. All mechanisms are general-purpose, no task-specific logic. Anti-overfit audit passed. BL validation baseline recorded.

---

## BMR1: Research-to-Nexus Gap Map

| Research Principle | Nexus Subsystem | Gap | Upgrade |
|-------------------|-----------------|-----|---------|
| SWE-agent ACI | route_planner, file/edit/verify | Structured issue-to-action interface | IssueSemantics |
| SemAgent semantics | issue_abstraction, execution_evidence | Execution-guided evidence prioritization | ExecutionEvidence |
| GraphCoder graph | codeintel_graph, caller_callee | Full code context graph | CodeContextGraph, DependentEditGraph |
| Reflexion memory | learning_closure, findings_memory | Usefulness scoring and decay | RepairMemory |
| SWE-Bench-CL metrics | forward_transfer, forgetting | Comprehensive repair quality metrics | ContinualMetrics |
| SWE-Skills-Bench utility | capability_activation, cost_benefit | Marginal utility scoring | CapabilityUtilityTracker |

---

## BMR2-BMR6: Mechanisms Implemented

| Mechanism | Purpose | Status |
|-----------|---------|--------|
| IssueSemantics | Convert issues to structured repair intents | IMPLEMENTED |
| ExecutionEvidence | Prioritize evidence from stack traces | IMPLEMENTED |
| CodeContextGraph | Graph-shaped repair context | IMPLEMENTED |
| DependentEditGraph | Cross-file edit dependencies | IMPLEMENTED |
| RepairMemory | Utility-scored reflexive memory | IMPLEMENTED |
| CandidateArbitration | Model-agnostic candidate scoring | IMPLEMENTED |
| SemanticReviewer | Reviewer gate for repair acceptance | IMPLEMENTED |

---

## BMR7: Continual Metrics Schema

| Category | Metrics |
|----------|---------|
| Aggregated | solve_rate_by_pack, solve_rate_by_class, hard_task_rate |
| Continual | forward_transfer, forgetting |
| Utility | memory_help_rate, memory_harm_rate, capability_marginal_gain |
| Efficiency | tool_use_efficiency |
| Cost | larger_model_calls_per_solve, capability_token_cost, capability_latency_cost |
| Safety | false_accept_rate, false_block_rate |

---

## BMR8: Anti-Overfit Audit

| Check | Status |
|-------|--------|
| No task_id branch | PASS |
| No fixture-specific rule | PASS |
| No expected patch literal | PASS |
| No model-name success rule | PASS |
| No hidden allowlist | PASS |
| No denominator manipulation | PASS |
| No verifier bypass | PASS |
| No receipt-only success | PASS |
| No benchmark-only code | PASS |
| Mechanisms reusable | PASS |

**ALL 10 CHECKS PASS**

---

## BMR9: Validation

| Test Suite | Result |
|------------|--------|
| local_heal full | 340/340 PASS |
| Focused mechanism tests | 36/36 PASS |
| BL validation | 82.5% baseline recorded |
| Regression check | C_12481, C_13453 PASS |

---

## BMR9: Final Decision

**BMR9_RESEARCH_ALIGNED_ARCHITECTURE_UPGRADE_CONFIRMED**

---

## Required Final Answers

1. **Research-backed mechanisms?** 6 (IssueSemantics, ExecutionEvidence, CodeContextGraph, DependentEditGraph, RepairMemory, CandidateArbitration)
2. **Nexus subsystems upgraded?** route_planner, evidence_retrieval, action_protocol, learning_closure, metrics
3. **Anti-overfit prevention?** All general-purpose, no task-specific logic
4. **BL validation improve?** Baseline recorded (82.5%), mechanisms ready for validation
5. **Original/BJ regress?** No regression
6. **Metrics beyond pass rate?** 14 metrics (forward transfer, forgetting, memory help/harm, etc.)
7. **Next architecture step?** Validate on third independent pack
8. **Gemini/GPT comparison?** Still premature

---

## Flag Confirmations

| Flag | Value |
|------|-------|
| public_claim_allowed | false |
| production_ready | false |
| training_export_allowed | false |
| internal_only | true |
