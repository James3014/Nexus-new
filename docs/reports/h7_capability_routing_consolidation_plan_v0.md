# H7 Capability Routing Consolidation Plan v0

Status: `PLANNING_ONLY_NOT_STARTED`
Created: 2026-06-24
Updated: 2026-06-25 (H7-0A status cleanup)
Scope: H7 and later, after H6 provider safety boundary closure
Runtime posture: `NO_RUNTIME_BEHAVIOR_CHANGE`
Provider posture: `NO_PROVIDER_CALL`, `NO_MODEL_LOAD`, `NO_MODEL_CALL`, `NO_PROCESS_SPAWN`, `NO_NETWORK_CALL`
Public claim posture: `INTERNAL_ONLY`, `PUBLIC_CLAIM_ALLOWED=false`
H7 started: `false` — this document is a planning-only artifact; H7 implementation has NOT begun

---

## 0. Executive Summary

H7 is not a new ACRouter-style subsystem and not a new router built from scratch.

H7 is a consolidation stage: it turns Nexus' already existing routing, receipt, learning, self-healing, and anti-hallucination primitives into a single governed capability routing center.

The central correction from earlier external planning is:

```text
Do not implement a parallel learning/router loop.
Consolidate the existing Nexus primitives:
- CapabilityPlanner
- CapabilitySignalSet
- CapabilityPlan / RouteDecision
- CapabilityReceipt / SkillReceipt
- S2TTraceEvent / S2TAdoptionDecision
- OutcomeMemory
- HallucinationGuard
- ClaimGate / ArtifactGate / public telemetry boundary
- RLM bounded receipts
- Lesson retrieval/writeback
```

The target is to make Nexus move from a collection of many capabilities into a meta-framework that can decide which capabilities to use, verify what actually happened, write back lessons safely, and become stronger without bypassing governance.

---

## 1. Non-Negotiable Boundary

H7 must start only after H6 safety closure is sealed.

H7 must not interrupt or replace:

```text
H6-13 Controlled Provider Probe Denylist
H6-14 Controlled Probe Preflight Replay
H6-15 H6 Safety Closure / Claim Lock
```

H7 must not perform:

```text
Qwen call
Ollama call
Gemini call
Codex call
cloud provider call
network call
process spawn
model load
model call
real provider probe
runtime policy promotion
public benchmark claim
production readiness claim
```

H7 begins as projection-only, shadow-only, and receipt-only.

---

## 2. Current Code Reality Map

The repo already contains many primitives that map to the proposed intelligent routing architecture.

### 2.1 Existing Routing and Capability Core

Observed source files:

```text
nexus/engine/capability_planner.py
nexus/engine/capability_signals.py
nexus/engine/capability_contracts.py
nexus/engine/capability_executor_controls.py
nexus/engine/capability_receipts.py
nexus/engine/capability_receipt_policy.py
nexus/engine/learning_policy_loader.py
nexus/engine/autonomic_router.py
nexus/core/capability_registry.py
nexus/core/capability_selector.py
nexus/core/capability_signal_set.py
nexus/core/capability_constraints.py
```

Findings:

```text
CapabilityPlanner already contains a default capability registry through default_capability_nodes().
CapabilitySignalSet already collects route, task, risk, memory, LanceDB, CodeIntel, skills, MSA, and many task signals.
CapabilityPlan already records selected / required / optional / conditional / pending / forbidden capabilities.
RouteDecision already exists in capability_contracts.py and is the better source of route rationale.
CapabilityExecutionPlan and ExecutorControls exist, but currently remain shallow flag bridges.
AutonomicRouter still has mode-changing behavior and should become signal-only or facade.
```

### 2.2 Existing Learning Loop Pieces

Observed source files:

```text
nexus/learning/outcome_memory.py
nexus/contracts/s2t_policy.py
nexus/contracts/s2t_trace.py
scripts/bench/s2t_shadow_report.py
scripts/bench/export_s2t_shadow_policy.py
scripts/ops/lesson_writeback_check.py
nexus/services/lesson_retrieval.py
nexus/services/lesson_resolver.py
nexus/services/federated_lessons.py
```

Findings:

```text
OutcomeMemory already stores episode outcomes and computes promoted / penalized capability scores.
OutcomeMemory excludes trust_mismatch rows from eligible learning.
Dynamic learning policy exists but currently has enforce_penalties=false.
S2T shadow report already emits shadow-only trace events and promotion gates.
S2TAdoptionDecision already requires override lift, no trust mismatch regression, public claim precision non-regression, and heldout win rate.
Lesson retrieval/writeback exists but is not yet unified with RouteDecision + CapabilityReceipt + S2TTraceEvent.
```

### 2.3 Existing Self-Healing Loop Pieces

Observed source files:

```text
nexus/engine/self_healing_selector.py
nexus/engine/rlm_controller.py
nexus/contracts/rlm_budget.py
nexus/contracts/rlm_trace.py
nexus/services/local_heal/receipt.py
nexus/services/local_heal/shadow_receipt.py
nexus/services/local_heal/claim_delivery_gate.py
nexus/app/nightshift_runner_service.py
```

Findings:

```text
SelfHealingSelector / ASH exists.
Nightshift service exists.
RLM bounded receipts exist.
RLM currently states bounded_adapter_not_dispatch and runtime_update_allowed=false.
Self-healing exists as material and receipts, but not yet a fully unified phase replan loop.
```

### 2.4 Existing Anti-Hallucination Loop Pieces

Observed source files:

```text
nexus/governance/hallucination_guard.py
nexus/evidence/claim_boundary.py
nexus/core/public_telemetry_boundary_contract.py
nexus/engine/capability_receipt_policy.py
nexus/engine/capability_receipts.py
scripts/ops/verify_report_claims.py
scripts/bench/public_gate_bundle.py
```

Findings:

```text
HallucinationGuard checks evidence absence, verified claim without evidence, benchmark threshold mismatch, failed artifact contradiction, and logic mismatch.
Claim boundary and public telemetry boundary already enforce public claim safety.
CapabilityReceipt.public_claim_safe is strict and telemetry-aware.
The anti-hallucination loop is relatively mature, but claimability protocol is still distributed across several modules.
```

---

## 3. Corrected Architecture Principle

The new routing center must be built as consolidation, not duplication.

### 3.1 Single Source of Truth Targets

```text
Capability definitions:
  Source of truth -> CapabilityRegistry / CapabilityNode
  Current location -> default_capability_nodes() in capability_planner.py

Route decision:
  Source of truth -> RouteDecision / CapabilityPlan
  Not route_rationale as a new primary object

Capability outcome:
  Source of truth -> CapabilityReceipt
  Not ad hoc report fields

Skill outcome:
  Source of truth -> SkillReceipt
  Skill router must not override capability mode

Learning trace:
  Source of truth -> S2TTraceEvent + OutcomeMemory episode

Adoption:
  Source of truth -> S2TAdoptionDecision + learning_policy_loader promotion gate

Claimability:
  Source of truth -> CapabilityReceipt.public_claim_safe + ClaimGate + ArtifactGate + public telemetry boundary
```

### 3.2 Main Correction

Do not add a standalone `route_rationale` schema as the runtime source.

Instead add:

```text
RouteDecision -> LearningRouteRationaleView
```

This view may be used by shadow learning and reports, but the runtime route source remains RouteDecision / CapabilityPlan.

---

## 4. SPXDRAC Target Flow

Nexus' capability route should eventually map all major capabilities into:

```text
Task / Code Change / User Intent
  -> S: Scope & Constraints
  -> P: Capability + Skill Plan
  -> X: Recon / Research / CodeIntel
  -> D: Decide / Govern / Belief
  -> R: Repair / Execute / Self-heal
  -> A: Audit / Artifact / Claim
  -> C: Closure / Learning / Rule Lifecycle
  -> next routing decision becomes more informed
```

H7 only consolidates and audits this flow.

Runtime behavior changes are deferred until strict opt-in later stages.

---

## 5. Six Pillars, Not Five

The prior planning called this the five pillars, but the current architecture should treat these as six distinct pillars:

| Pillar | Role | Current posture |
|---|---|---|
| LanceDB | Tactical semantic retrieval and similar case lookup | Existing, must stay signal/evidence source |
| Memory | Long-term experience and lesson retrieval | Existing, needs unification with OutcomeMemory |
| MemPalace | Hard governance constraints and blocked actions | Existing as gate/dependency, needs hard constraint layer |
| Belief | Confidence and escalation controller | Existing, needs stronger planner integration |
| Artifact | Objective evidence boundary | Existing, should remain required gate |
| Claim | Public/internal claimability boundary | Existing, must remain separate from Artifact |

Claim must not be collapsed into Artifact. Claimability is an independent safety boundary.

---

## 6. H7-H10 Roadmap

## H7: Routing Consolidation / No Behavior Change

Goal: establish a single map of routing truth without changing runtime behavior.

### H7-0 Capability Routing Reality Map

Purpose:

```text
Audit the current routing/capability/learning/self-heal/anti-hallucination primitives.
Create a source-of-truth map.
Identify duplicate routers, facades, signal providers, and runtime decision sources.
```

Allowed output:

```text
docs/reports/h7_0_capability_routing_reality_map_v0.md
```

Must include:

```text
Capability definitions source map
Route decision source map
Capability receipt source map
Skill receipt source map
Learning loop source map
Self-heal loop source map
Anti-hallucination loop source map
Legacy router / facade map
Runtime-change risk map
```

Acceptance:

```text
No code behavior change.
No runtime policy change.
No provider call.
No model call.
Report identifies the current source of truth for every routing primitive.
```

### H7-1 Extract CapabilityRegistry From Planner

Purpose:

```text
Move the data-only capability node registry out of CapabilityPlanner if safe.
Do not change selected capabilities.
```

Candidate source:

```text
nexus/engine/capability_planner.py::default_capability_nodes()
```

Target posture:

```text
CapabilityPlanner consumes registry.
CapabilityRegistry owns definitions.
Behavior remains identical.
```

Acceptance:

```text
All existing planner tests pass.
Serialized capability list matches before/after.
No change in selected/required/conditional/forbidden capabilities for fixtures.
```

### H7-2 RouteDecision / CapabilityPlan Single Source Map

Purpose:

```text
Prevent route_rationale duplication.
Define projection-only LearningRouteRationaleView derived from RouteDecision / CapabilityPlan.
```

Rules:

```text
RouteDecision remains runtime source.
LearningRouteRationaleView is projection-only.
runtime_effect=false.
```

Acceptance:

```text
Projection is deterministic.
Projection cannot override selected capabilities.
Projection cannot set runtime policy.
```

### H7-3 AutonomicRouter Downgrade Plan

Purpose:

```text
Convert AutonomicRouter from mode-deciding parallel router into signal provider / compatibility facade.
```

Current risk:

```text
AutonomicRouter can still influence mode directly.
This creates a fourth routing source beside CapabilityPlanner, CapabilityRouter, and route policy loaders.
```

Acceptance:

```text
AutonomicRouter output is represented as autonomic_signals.
CapabilityPlanner / CapabilitySelector remains the only capability decision path.
Existing compatibility tests still pass.
```

### H7-4 CapabilitySignalSet Gap Audit

Purpose:

```text
Audit which signals enter CapabilitySignalSet today and which are still missing or inconsistent.
```

Must check:

```text
CodeIntel
JIT
Memory
LanceDB
Belief
Skill signals
MSA
Artifact/Claim signals
OutcomeMemory
S2T policy draft
RLM bounded receipts
```

Acceptance:

```text
Report lists fields already present, missing fields, duplicated fields, and unsafe shortcut fields.
```

### H7-5 CapabilityConstraints Hard Boundary Spec

Purpose:

```text
Define hard constraints that selector cannot downgrade.
```

Required hard constraints:

```text
mempalace_fail_closed
artifact_evidence_required
claim_fail_closed
provider_safety_boundary
runtime_effect_lock
public_claim_lock
path_scope_lock
budget_lock
```

Acceptance:

```text
Spec only. No runtime enforcement until later unless tests already cover existing behavior.
```

---

## H8: Receipt Coverage / Evidence Unification

Goal: make selected/invoked/evidence/gate/outcome consistent across capabilities.

### H8-0 CapabilityReceipt Coverage Audit

Purpose:

```text
For every CapabilityNode, verify whether there is a receipt adapter or runtime receipt source.
```

Must classify:

```text
receipt_backed
selected_only
pending_executor
shadow_only
runtime_receipt_only
public_claim_safe_possible
public_claim_forbidden
```

Acceptance:

```text
No capability may be called active unless invoked/evidence/gate/outcome are receipt-backed.
```

### H8-1 Autoreason Receipt Hardening

Required evidence:

```text
votes
winner
stop_reason
candidate_count
gate_verdict
evidence_refs
```

Acceptance:

```text
selected-only Autoreason is not public_claim_safe.
```

### H8-2 DDTree Receipt Hardening

Required evidence:

```text
eligible
pruned_candidates
saved_steps
original_candidate_count
remaining_candidate_count
correctness_gate
```

Acceptance:

```text
DDTree only counts as effective if pruning happened and correctness gate stayed clean.
```

### H8-3 Ultra Review Receipt Hardening

Required evidence:

```text
sandbox/repro mode
verified_findings
gate_verdict
risk tier
review scope
claim boundary
```

Acceptance:

```text
dry review and full review must be distinct.
```

### H8-4 Swarm / Drone / Nightshift Receipt Boundary

Purpose:

```text
Stop claiming collaboration capabilities from labels alone.
```

Required evidence:

```text
Swarm: role findings, consensus, owner, evidence refs
Drone: subtask artifact, worker id, parent task, gate result
Nightshift: recommended, invoked, recovered, artifact path, closure result
```

Acceptance:

```text
If recommended but not invoked, receipt must say recommended_only.
If invoked without evidence, gate must fail.
```

### H8-5 SkillSlot + SkillReceipt

Purpose:

```text
Skills become capability-internal operation manuals.
They must not become global mode routers.
```

Rules:

```text
Skill router provides candidates.
CapabilitySelector chooses capability.
SkillSlot mounts skill only inside selected capability and allowed phase.
SkillReceipt records selected/injected/used/evidence/outcome.
```

Acceptance:

```text
Skill selected without injected is not success.
Skill injected but unused is not outcome_contributed.
Skill used without evidence fails receipt.
```

### H8-6 CapabilityReport Read-Only From Receipts

Purpose:

```text
Reports must not infer capability effectiveness from semantic labels.
```

Acceptance:

```text
CapabilityReport reads receipts only.
No capability lambda.
No selected == active shortcut.
No public claim without public_claim_safe.
```

---

## H9: Learning / Self-Heal / Anti-Hallucination Loop Bridge

Goal: unify existing loops into one evidence pipeline.

### H9-0 OutcomeMemory + S2TTraceEvent Bridge

Purpose:

```text
Bridge CapabilityReceipt and S2TTraceEvent into OutcomeMemory episode records.
```

Rules:

```text
trust_mismatch=true rows are excluded from positive learning.
public_claim unsafe rows cannot become public-facing records.
training eligibility must be explicit.
```

Acceptance:

```text
OutcomeMemory episode can cite route decision, capability receipts, S2T event, and verifier evidence.
```

### H9-1 LessonCandidate Gate

Purpose:

```text
Create a gated intermediate object before lesson writeback or training export.
```

Allowed destinations:

```text
observation_only
negative_memory
shadow_export_queue
lesson_writeback_candidate
training_export_candidate
```

Required fields:

```text
source_route_decision_id
source_capability_receipt_ids
source_s2t_trace_event_id
source_verifier_result
trust_mismatch
public_claim_safe
runtime_effect
training_eligible
lesson_candidate_type
allowed_destination
```

Acceptance:

```text
No direct lesson writeback from unverified evidence.
No training export without gate result.
```

### H9-2 Rule Lifecycle

Purpose:

```text
Make rules evolve through a governed lifecycle.
```

Lifecycle:

```text
observation -> recommendation -> shadow_candidate -> strict_opt_in -> active -> deprecated
```

Hard rules:

```text
Governance rules cannot auto-delete.
Claim gates cannot be weakened by learning policy.
Artifact gates cannot be bypassed by route cost policy.
```

### H9-3 Self-Heal Replan Receipt Bridge

Purpose:

```text
Connect A gate reject, timeout, low belief, semantic failure, and artifact failure into a replan receipt path.
```

Inputs:

```text
A gate reject
test failure
timeout
low belief
semantic failure sensor
RLM budget receipt
Nightshift handoff receipt
```

Outputs:

```text
replan_trace
selected recovery path
blocked recovery path
escalation reason
```

Acceptance:

```text
Replan must be explainable and receipt-backed.
No direct pass-through from self-heal recommendation to success.
```

### H9-4 RLM Bounded Preflight, Not Dispatch

Purpose:

```text
Keep RLM in bounded, receipt-only mode until strict runtime opt-in.
```

Current known boundary:

```text
orchestration_mode=bounded_adapter_not_dispatch
runtime_update_allowed=false
public_benchmark_allowed=false
```

Acceptance:

```text
RLM X/R decisions are recorded but do not dispatch recursive work.
```

### H9-5 Unified Claimability Protocol

Purpose:

```text
Unify HallucinationGuard, ClaimGate, ArtifactGate, CapabilityReceipt.public_claim_safe, and public telemetry boundary.
```

Acceptance:

```text
Any public-facing claim must trace to receipt evidence and claim gate result.
Evidence gap, logic mismatch, failed artifact contradiction, or benchmark threshold failure must fail closed.
```

---

## H10: Runtime Policy / External Benchmark

Goal: only after H7-H9 are stable, allow strict opt-in runtime learning and external comparisons.

### H10-0 Strict Opt-In Runtime Learning Policy

Purpose:

```text
Promote learning policy only when S2TAdoptionDecision and learning_policy_loader gates pass.
```

Minimum gate:

```text
eligible_rows >= 30
selector_override_verified_rate > original_top1_verified_rate
trust_mismatch_delta <= 0
public_claim_precision_delta >= 0
heldout_win_rate > 0.5
rollback_policy present
kill switch present
```

### H10-1 Rollback + Kill Switch

Required controls:

```text
NEXUS_DISABLE_PROMOTED_ROUTE_COST_POLICY
NEXUS_DISABLE_S2T_POLICY_DRAFT
explicit policy status demotion
rollback artifact
```

### H10-2 Nexus-Only Benchmark

Purpose:

```text
Benchmark routing and receipt coverage before external model comparisons.
```

Acceptance:

```text
Selected capabilities all have receipt coverage.
No public claim unless claim gate passes.
```

### H10-3 Gemini Smoke Internal Only

Purpose:

```text
Small internal comparison, not public claim.
```

Rules:

```text
3 tasks max at first.
Internal only.
No public benchmark claim.
Receipt and claim gates required.
```

### H10-4 Public Claim Gate Review

Purpose:

```text
Decide whether external benchmark data is publishable.
```

Acceptance:

```text
Only public claim gate PASS can produce public-facing report language.
```

---

## 7. Corrected Mapping From Original P1-P34

### Already partially present, consolidate rather than rebuild

```text
P1 Capability contract freeze
P2 CapabilityRegistry extraction
P3 CapabilitySignalSet
P5 CapabilitySelector
P8 CapabilityExecutionPlan
P10 CapabilityReceipt
P11 SkillReceipt
P12 LanceDB/Memory
P13 Belief
P15 Artifact/Claim
P26 OutcomeMemory
P28 Report de-semanticization
P30 AutonomicRouter downgrade
```

### Real implementation gaps

```text
P4 CapabilityConstraints hard layer
P6 SkillSignalSet standard auxiliary signal
P7 SkillSlot
P9 ExecutorControls phase control graph
P14 MemPalace unified capability/skill review
P16 CodeIntel/JIT selector integration hardening
P17-P22 executor receipt coverage
P25 Dynamic replan phase trace
P27 Rule lifecycle
P29 legacy router facade
P31 research_flow_service slimming
```

### Defer until after safety and receipt bridge

```text
P23 RLM X-loop dispatch
P24 RLM R-loop dispatch
P33 Gemini smoke
P34 Gemini full public report
```

---

## 8. Agent Execution Rule

Agent must follow this rule:

```text
Do not implement a new ACRouter-style loop.
Do not create duplicate route_rationale, capability_receipt, or shadow_eval sources of truth.
First map and consolidate existing Nexus learning primitives:
RouteDecision, CapabilityPlan, CapabilityReceipt, SkillReceipt, S2TTraceEvent, OutcomeMemory, HallucinationGuard, RLM receipts, lesson retrieval/writeback, and S2TAdoptionDecision.
H7 must be projection-only and shadow-only until H6 safety closure is sealed.
```

---

## 9. Acceptance Posture For H7 Start

H7 can start only when:

```text
H6 provider safety closure sealed
no H6 report lock violations
no production_ready=true in H5/H6 reports
no public_claim_allowed=true in H5/H6 reports
no provider/model/network/process call introduced by H6
```

H7-0 acceptance target (Expected state after review, not current accepted state):

```text
H7_0_CAPABILITY_ROUTING_REALITY_MAP_PENDING_REVIEW
```

Current state: H7-0 is draft and has NOT been accepted. The above string is the target state
identifier to be assigned only after reviewer approval. Do not treat this as a PASS claim.

But this must not imply:

```text
runtime learning enabled
local provider ready
Qwen ready
Ollama ready
Gemini benchmark ready
production ready
public claim allowed
```

---

## 10. One-Sentence Product Direction

Nexus H7 turns existing scattered intelligence into a governed capability routing center: it learns from receipts, self-heals through gated replans, rejects hallucinated claims through evidence boundaries, and improves routing only through shadow-tested, rollback-safe, strict opt-in policy promotion.

---

## 11. Integration Notes: Nexus Routing v2 + ACRouter

This plan integrates two inputs:

```text
1. Nexus intelligent routing v2
   Primary architecture source.
   Provides SPXDRAC, six pillars, capability registry/selector/receipt, skill slots,
   executor controls, OutcomeMemory, rule lifecycle, and claimability boundaries.

2. ACRouter-style feedback loop
   Reference pattern only.
   Provides route feedback, historical trace learning, shadow evaluation,
   abstain/fallback learning signals, and gated policy improvement.
```

ACRouter is not the target runtime architecture.

Nexus remains the target architecture. ACRouter ideas are absorbed only when they can be expressed through existing Nexus primitives.

### 11.1 Adopt From ACRouter

The following ACRouter ideas are useful and should be absorbed:

```text
feedback loop from route outcomes
historical route trace analysis
shadow evaluation before policy adoption
abstain/fallback as valid learning signals
policy improvement from verified historical data
cost/error-aware routing recommendations
```

Nexus implementation targets:

```text
RouteDecision / CapabilityPlan -> route source
CapabilityReceipt / SkillReceipt -> what actually happened
S2TTraceEvent -> normalized shadow learning trace
OutcomeMemory -> episode memory and capability score draft
S2TAdoptionDecision -> promotion gate
learning_policy_loader -> strict opt-in runtime policy loader
```

### 11.2 Reject From ACRouter

The following ACRouter-style interpretations are explicitly rejected:

```text
replacing Nexus routing with a separate learned router
direct runtime route update from historical traces
model/provider selection as the first H7 target
weakening verifier, claim gate, artifact gate, or MemPalace gate
allowing learned policy to override governance boundaries
creating another route_rationale source of truth
creating another capability_receipt source of truth
creating another shadow_eval pipeline beside S2TTraceEvent
```

### 11.3 Mapping Table

| ACRouter concept | Nexus implementation | H-stage |
|---|---|---|
| Route feedback | RouteDecision + CapabilityPlan projection | H7-2 |
| Historical route trace | S2TTraceEvent + OutcomeMemory episode | H9-0 |
| Shadow evaluation | Existing S2T shadow report and policy draft | H9-0 / H10-0 |
| Runtime policy adoption | S2TAdoptionDecision + learning_policy_loader strict opt-in | H10-0 |
| Abstain learning | LessonCandidate destination: negative_memory / observation_only | H9-1 |
| Cost-aware route update | Route cost policy candidate, shadow-only first | H9 / H10 |
| Error-aware route update | CapabilityReceipt failure_reason + verifier result | H8 / H9 |
| Learned route selector | Not accepted as primary router; may become strict opt-in policy overlay | H10+ |

### 11.4 Nexus Routing v2 Mapping

| Nexus Routing v2 item | Current code reality | Plan action |
|---|---|---|
| CapabilityRegistry | Partly inside `default_capability_nodes()` | Extract/centralize in H7-1 |
| CapabilitySignalSet | Exists in `capability_signals.py` | Gap audit in H7-4 |
| CapabilityConstraints | Exists but thin | Hard-boundary spec in H7-5 |
| CapabilitySelector | Multiple routing seams still exist | Single-source consolidation in H7 |
| CapabilityExecutionPlan | Exists but shallow | Upgrade after H7 inventory |
| ExecutorControls | Flag bridge exists | Phase control graph later |
| CapabilityReceipt | Exists and strict | Coverage audit in H8-0 |
| SkillReceipt | Exists as primitive | Formal SkillSlot flow in H8-5 |
| OutcomeMemory | Exists | Bridge to S2TTraceEvent in H9-0 |
| Rule lifecycle | Exists in fragments | Formal lifecycle in H9-2 |
| Hallucination loop | Exists through HallucinationGuard / Claim / Artifact | Unified claimability protocol in H9-5 |
| Self-heal loop | Exists in ASH / Nightshift / RLM receipts | Replan receipt bridge in H9-3 |

### 11.5 Agent Guardrail

Agent must read this section before implementing H7.

```text
ACRouter is an inspiration for learning-loop structure, not a replacement router.
Nexus Routing v2 is the main architecture.
All ACRouter ideas must enter through RouteDecision, CapabilityReceipt, S2TTraceEvent, OutcomeMemory, S2TAdoptionDecision, and strict opt-in policy loading.
If an implementation requires a new parallel router, new primary route_rationale, new primary receipt, or direct runtime update, it is out of scope for H7.
```

---

## 12. Integration Notes: Reconstructable Runtime Timing

Reconstructable Runtime is directionally correct, but it must not be implemented as a new runtime lane during H6/H7.

It must be treated as a horizontal recovery capability derived from existing Nexus evidence, not as a new source of truth.

The corrected timing is:

```text
Now: R0 / R1 inventory and schema draft only
After H6-14 / H6-15: attach recovery mapping to H7-0 / H7-4
After U3 candidate isolation: candidate-level reconstruction can begin
After H8 receipt coverage: checkpoint writer can become shadow-only
After H9 self-heal bridge: resume CLI and runtime recovery can be considered
Before H10: no public claim
```

Plain-language boundary:

```text
Now design and map recovery state.
Do not change runtime behavior.
Do not add resume CLI.
Do not write phase checkpoint writer.
Do not let recovery state affect routing.
```

### 12.1 Why Reconstructable Runtime Cannot Start As Runtime Work Now

Current blockers:

| Prerequisite | Current state | Decision |
|---|---|---|
| Route / capability single source of truth | H7 is about to consolidate it | Not stable yet |
| Receipt / evidence coverage | H8 is planned to audit and harden it | Not stable yet |
| Candidate isolation / hash match | U3 preflight says key pieces are missing | Not ready |

U3 candidate isolation preflight explicitly identifies these missing pieces:

```text
candidate isolation store missing
selected_candidate_hash missing
applied_patch_hash missing
hash mismatch detection missing
hash mismatch fail-closed missing
non-last candidate re-apply unsupported
```

Therefore, full runtime resume would be unsafe because Nexus cannot yet prove:

```text
which candidate was selected
which candidate patch hash was selected
which patch hash was actually applied
whether selected patch == applied patch
whether a crash can replay the same candidate without drift
```

### 12.2 Core Principle

Reconstructable Runtime must be a projection from existing Nexus truth sources:

```text
RouteDecision
CapabilityPlan
CapabilityReceipt
SkillReceipt
EvidenceBundle
S2TTraceEvent
OutcomeMemory
LocalHeal receipt
Committee candidate trace
Verifier result
```

It must not create:

```text
a new router
a new route truth source
a new receipt truth source
a recovery state that overrides RouteDecision
a recovery state that overrides CapabilityReceipt
a runtime resume path without hash-verified candidate isolation
```

### 12.3 New Recovery Subline: H7-R / H8-R / H9-R

Reconstructable Runtime should be inserted as a subline of the existing H roadmap.

It is not an independent stage before H7.

#### H7-R: Recovery Reality Map

Attach to:

```text
H7-0 Capability Routing Reality Map
H7-4 CapabilitySignalSet Gap Audit
```

Add report:

```text
docs/reports/h7_r0_reconstructable_runtime_reality_map_v0.md
```

Purpose:

```text
Map which existing records can support reconstruction and which are audit-only.
```

Must inspect:

```text
RouteDecision
CapabilityPlan
CapabilityReceipt
SkillReceipt
EvidenceBundle
S2TTraceEvent
OutcomeMemory
LocalHeal receipt
committee candidate trace
verifier result
RLM bounded receipt
Nightshift handoff receipt
```

Classify every source as:

```text
route_truth_source
receipt_truth_source
evidence_source
recovery_projection_candidate
audit_only
unsafe_to_resume
missing_hash
missing_phase_pointer
missing_next_action
```

H7-R acceptance:

```text
No runtime behavior change.
No checkpoint writer.
No resume CLI.
No recovery policy adoption.
No provider/model/network/process call.
Only report and schema draft allowed.
```

#### H7-R1: TaskRecoveryState Schema Draft

Add draft schema only. No runtime writer.

Suggested report or schema path:

```text
docs/reports/h7_r1_task_recovery_state_schema_draft_v0.md
```

Suggested fields:

```text
schema_version
run_id
task_id
phase
phase_index
route_decision_id
capability_plan_id
capability_receipt_ids
skill_receipt_ids
evidence_bundle_id
s2t_trace_event_id
outcome_memory_episode_id
candidate_id
selected_candidate_hash
applied_patch_hash
verifier_result_id
artifact_gate_status
claim_gate_status
belief_confidence
next_allowed_action
recovery_classification
runtime_effect=false
projection_only=true
resume_allowed=false
public_claim_allowed=false
```

The schema must explicitly distinguish:

```text
audit_only
resume_candidate
reconstructable
unsafe_to_resume
```

#### H7-R2: RouteDecision -> RecoveryState Projection Adapter

Allowed only after H7-R0/H7-R1.

Boundary:

```text
projection_only=true
runtime_effect=false
resume_allowed=false
```

Purpose:

```text
Generate a read-only TaskRecoveryState projection from RouteDecision / CapabilityPlan.
```

It must not affect routing.

#### H8-R: Recovery Receipt Coverage Matrix

Attach to:

```text
H8-0 CapabilityReceipt Coverage Audit
H8-6 CapabilityReport Read-Only From Receipts
```

Add report:

```text
docs/reports/h8_r1_recovery_receipt_coverage_matrix_v0.md
```

Classify each capability receipt:

| Classification | Meaning |
|---|---|
| `audit_only` | Good for audit, not sufficient for resume |
| `resume_candidate` | Has enough evidence to become resume input after extra gates |
| `reconstructable` | Can reconstruct phase input/output deterministically |
| `unsafe_to_resume` | Missing hash/evidence/verifier/phase pointer |

Required finding:

```text
selected=true is not enough for recovery.
invoked/evidence/gate/outcome/hash/verifier alignment must exist.
```

#### H9-R: Self-Heal Replan / Recovery Bridge

Attach to:

```text
H9-3 Self-Heal Replan Receipt Bridge
```

Only here may Nexus begin approaching runtime recovery.

Candidate objects:

```text
TaskRecoveryState
RecoveryPolicy
ReplanReceipt
CrashRecoveryReceipt
```

Still start shadow-only.

No automatic resume until:

```text
candidate_id exists
selected_candidate_hash exists
applied_patch_hash exists
hash mismatch fail-closed exists
candidate isolation store exists
receipt coverage matrix marks the source reconstructable
artifact gate and claim gate are traceable
```

### 12.4 Deferred Runtime Work

Do not implement these before H8/H9 gates are ready:

```text
nexus resume --run-id
phase checkpoint writer
crash simulation tests
automatic recovery policy
runtime replan adoption
candidate replay into worktree
```

When later allowed, sequence should be:

```text
R2 phase checkpoint writer shadow-only
R3 resume CLI dry-run only
R4 recovery policy shadow-only
R5 crash simulation tests
R6 guarded runtime resume strict opt-in
```

### 12.5 Relationship To Nexus Routing v2 + ACRouter

The combined model is now:

```text
Nexus Routing v2 = main architecture
ACRouter = feedback-loop reference pattern
Reconstructable Runtime = recovery projection and later recovery executor
```

Integration rule:

```text
ACRouter teaches how route outcomes improve future policy.
Reconstructable Runtime teaches how verified state can be resumed after failure.
Both must derive from Nexus truth sources and gates.
Neither may become a new runtime truth source during H7.
```

Mapping:

| Concept | Nexus source | Reconstructable use | Stage |
|---|---|---|---|
| Route decision | RouteDecision / CapabilityPlan | Recovery route pointer | H7-R |
| Capability execution | CapabilityReceipt | Recovery evidence and eligibility | H8-R |
| Candidate identity | U3 candidate isolation store | Candidate replay safety | After U3-1 |
| Patch identity | selected/applied hash | Hash match / mismatch fail-closed | After U3-1 |
| Verifier result | Verifier receipt / evidence bundle | Resume safety gate | H8-R / H9-R |
| Learning trace | S2TTraceEvent / OutcomeMemory | Recovery outcome memory | H9-R |
| Replan | RLM / Nightshift / self-heal receipts | Recovery policy candidate | H9-R |

### 12.6 Agent Guardrail For Recovery Work

Agent must treat all H7 recovery work as report/schema/projection-only.

```text
Do not implement full Reconstructable Runtime in H7.
Do not implement resume CLI in H7.
Do not implement checkpoint writer in H7.
Do not modify pipeline runtime in H7.
Do not let TaskRecoveryState influence routing in H7.
Do not claim reconstructable runtime ready.
```

Acceptable H7 recovery outputs:

```text
h7_r0_reconstructable_runtime_reality_map_v0.md
h7_r1_task_recovery_state_schema_draft_v0.md
projection-only adapter plan
recovery coverage gap list
U3 dependency list
```

Final H7 recovery status must be one of:

```text
H7_R0_RECOVERY_REALITY_MAP_PASS
H7_R1_TASK_RECOVERY_STATE_SCHEMA_DRAFT_PASS
```

It must not be:

```text
reconstructable runtime ready
resume ready
crash recovery ready
production ready
public claim allowed
```
