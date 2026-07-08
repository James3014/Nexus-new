# P6-A0 Quota-Aware Degradation Design Gate

## Problem Statement

P5 diversity selector works but has no quota awareness. When cloud/local/model budgets are insufficient, the system should degrade gracefully rather than fail hard. P6 defines this degradation behavior.

## Design Decisions

### Q1: When budget insufficient → degrade model?

**Decision**: Yes. Degrade from cloud model to local model when cloud budget exhausted.

**Rationale**: Local models (Ollama) have no external cost. Degrading to local preserves repair capability at lower quality.

**Implementation**:
- Track `cloud_budget_remaining` (tokens/cost)
- When `cloud_budget_remaining < threshold`: route to local-only
- Log degradation reason in receipt

### Q2: Decrease candidate count?

**Decision**: Yes, but with minimum floor.

**Rationale**: Fewer candidates = faster execution but reduced diversity. Set minimum floor of 2 candidates.

**Implementation**:
- `max_candidates = max(2, floor(budget_ratio * default_max))`
- Where `budget_ratio = cloud_budget / default_budget`
- Minimum 2, maximum 10

### Q3: Switch to local-only?

**Decision**: Yes, when cloud completely unavailable.

**Rationale**: Local-only is better than no repair attempt.

**Implementation**:
- When `cloud_budget_remaining <= 0`: force `execution_topology = "local_only"`
- Skip all cloud stages (stage1-3)
- Go directly to local model execution

### Q4: Skip committee?

**Decision**: Yes, when committee budget exhausted.

**Rationale**: Committee requires multiple model calls. If budget insufficient, skip to save resources.

**Implementation**:
- When `committee_budget_remaining <= 0`: skip committee invocation
- Fallback to single-model selection
- Log degradation reason

### Q5: Diagnosis only, no patch?

**Decision**: No. Always attempt patch generation.

**Rationale**: Even degraded, a patch attempt provides more value than no attempt. The verifier will reject bad patches.

**Implementation**:
- Always run stage1 (diagnosis)
- Always attempt stage4 (local retry)
- Let verifier/claim gate handle quality

### Q6: Fail-closed?

**Decision**: Yes, when no repair path available.

**Rationale**: If no model can be called (cloud + local both unavailable), fail closed.

**Implementation**:
- When `cloud_budget_remaining <= 0 AND local_unavailable`: fail_closed
- Log reason in receipt

### Q7: Does degradation interact with P5 selection?

**Decision**: No. P5 selection operates on whatever candidates are produced.

**Rationale**: P5 selection is orthogonal to quota state. Quota affects candidate generation, not selection.

**Implementation**:
- P5 receives candidates from producer regardless of quota state
- P5 scoring/selection unchanged
- Quota state logged separately in receipt

### Q8: Does degradation relax P2/P4 gates?

**Decision**: Must NOT.

**Rationale**: P2/P4 gates ensure quality. Relaxing them under quota pressure would allow bad patches through.

**Implementation**:
- P2 claim gate unchanged
- P4 committee gate unchanged
- Quota degradation only affects candidate generation, not validation

## Integration Points

### Before candidate_producer (committee path)

```
if committee_budget_remaining <= 0:
    skip committee
    fallback to single-model
    log: p6_degradation_action="skip_committee"
```

### Before committee invocation

```
if committee_budget_remaining <= 0:
    return CommitteeRoutedToolResult(invoked=False, blocked_reason="committee_budget_exhausted")
```

### Before P5 selection

```
# P5 selection is quota-unaware
# Quota affects candidate generation, not selection
```

### After P5 selection (receipt)

```
receipt.p6_quota_state_known = True
receipt.p6_budget_class = "sufficient" | "degraded" | "exhausted"
receipt.p6_degradation_action = "none" | "degrade_model" | "skip_committee" | "local_only"
receipt.p6_degradation_reason = "cloud_budget_exhausted" | "committee_budget_exhausted" | etc.
```

## Receipt Fields

| Field | Type | Description |
|-------|------|-------------|
| `p6_quota_state_known` | bool | Whether quota state was evaluated |
| `p6_budget_class` | str | "sufficient", "degraded", or "exhausted" |
| `p6_degradation_action` | str | Action taken: "none", "degrade_model", "skip_committee", "local_only" |
| `p6_degradation_reason` | str | Reason for degradation |

## Gate Conditions

P6 implementation requires:
- [ ] Quota state tracking infrastructure
- [ ] Budget class calculation
- [ ] Degradation action logic
- [ ] Receipt field integration
- [ ] P5 selection unaffected
- [ ] P2/P4 gates unchanged

## What P6 Does NOT Cover

- P5 scoring/selection changes
- P2/P4 gate relaxation
- Solve-rate improvement claims
- Production-ready status
- Public claim eligibility
- Real cloud endpoint integration (deferred to P7)
