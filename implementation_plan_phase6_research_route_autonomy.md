# Phase 6 Implementation Plan: Research Isolation, Route Decision Intelligence, and Cost-Aware Autonomy

> Status: Proposed
> Promotion effect: none
> Execution mode: fail-closed, evidence-bound, observation-first
> Scope type: governance + orchestration + research/policy intelligence
> Precondition: Phase 5 controlled canary closed with explicit verdict and sealed evidence bundle

## 1. Position

Phase 6 is the next long-horizon milestone after controlled patch canary closure. Its purpose is not to widen production authority, but to harden the upstream layers that determine whether Nexus studies the right problem, chooses the right route, and spends model budget in the right place.

This milestone focuses on three tightly connected capabilities:
1. Research Isolation formalization.
2. Route Decision Intelligence.
3. Cost-Aware Autonomy for local and mixed-model execution.

The intended outcome is a more objective, explainable, and auditable execution chain:
**Research isolation -> route rationale -> cost-aware execution -> hardened patch synthesis -> fail-closed verification.**

## 2. Preconditions

Phase 6 must not start unless Phase 5 has been closed with:
- Sealed evidence bundle.
- Explicit closeout verdict.
- No unresolved claim-boundary ambiguity.
- No hidden dependency on unreviewed production behavior.

## 3. Blast Radius

This milestone is limited to:
- Research isolation policy and receipts.
- Route rationale and route decision evidence.
- Pre-patch preparation contracts.
- Observation-only autonomy benchmarking.

It does not authorize:
- Production promotion.
- Public benchmark claim expansion.
- Automatic route mutation based on benchmark output.
- Governance downgrades of any existing fail-closed barrier.

## 4. Goals

### G1. Formalize Research Isolation as a governed capability
Convert the current isolation implementation into a durable policy layer with explicit levels, receipt contracts, contamination checks, and artifact rules. Planner-visible information must remain minimal, and research artifacts must remain fact-oriented rather than design-prescriptive.

### G2. Make route choice explainable
Every significant route decision must emit machine-readable rationale and evidence hooks. The system must be able to explain why it used receipt-lite rescue, why research isolation was required, why a model patch route was necessary, and why a safer route overrode a cheaper route.

### G3. Make autonomy cost-aware without relaxing governance
Establish an observation-first way to decide which task classes can safely use smaller local models, deterministic rescue, or lighter execution profiles. Cost savings must never override fail-closed rules, sealed evidence requirements, or public claim boundaries.

## 5. Workstreams

### Workstream A — Research Isolation Formalization
- **Objective**: Turn existing research isolation patterns into a first-class governance capability.
- **Deliverables**: `RESEARCH_ISOLATION_POLICY.md`, `research_receipt.v1` schema, contamination guard test suite.
- **Policy Levels**: L0_DIRECT, L1_MASKED, L2_DUAL_ISOLATION.

### Workstream B — Route Decision Intelligence
- **Objective**: Upgrade route choice into an explicit decision contract with rationale and reason codes.
- **Deliverables**: `route_decision_receipt.v1`, route reason code registry, route rationale writeback in evidence bundle.

### Workstream C — Pre-Patch Preparation Layer
- **Objective**: Insert a governed preparation layer before patch synthesis to intercept avoidable failures.
- **Deliverables**: `pre_patch_contract.v1`, syntax-shape sanitizer, refusal/empty response classifier.

### Workstream D — Cost-Aware Autonomy Benchmarking
- **Objective**: Build an observation-only benchmark to measure model suitability per task class.
- **Deliverables**: `local_model_suitability_matrix.csv`, `cost_aware_autonomy_report.md`, observation benchmark runner.

## 6. Execution Order
1. Close Phase 5 with sealed evidence and explicit verdict.
2. Formalize Research Isolation policy and receipts.
3. Add Route Decision rationale schema and writeback.
4. Build Pre-Patch Preparation contract and reject taxonomy.
5. Run observation-only Cost-Aware Autonomy benchmark.
6. Compare results across at least two rounds.
7. Write Learning Closure Matrix entries and residual debt.
8. Produce closeout with no promotion effect.

## 7. Acceptance Criteria
- Research Isolation implemented with fail-closed receipts.
- Route decisions emit auditable rationale and reason codes.
- Pre-patch preparation catches malformed inputs before patch synthesis.
- Observation-only autonomy benchmark produces repeatable evidence.
- No public claim or production promotion boundary is crossed.

---
**NEXUS IDENTITY: 384c6fd02 + v2.9 RUNTIME-ALIGNED**
